'''
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📁 ARQUIVO : calculo_frete_service.py
📦 MÓDULO  : Services
🎯 OBJETIVO: Engine de cálculo de frete por NF.
             Resolve a ROTA do destino da NF, localiza a
             tabela ativa da transportadora vinculada a
             essa rota e aplica a fórmula progressiva do MVP.

             REGRA DE NEGÓCIO (MVP):
               Se peso_total_kg ≤ 30:
                 frete = valor_minimo_faixa (faixa 0→30)
               Se peso_total_kg > 30:
                 frete = valor_minimo_faixa +
                         (peso_total_kg − 30) × valor_kg (faixa 30→∞)

               Após a fórmula, aplica-se o piso da rota:
                 frete = max(frete, valor_minimo_rota)

             RESOLUÇÃO DE ROTA (cascata):
               1. rota da tabela ativa cuja cidade_normalizada
                  seja igual à cidade de destino da NF;
               2. rota curinga da UF (cidade_normalizada IS NULL);
               3. nenhuma rota ativa → RotaNaoEncontradaError.

             Camada de orquestração:
               calcular_frete_nf_no_embarque — individual com
                 validação de pertencimento ao embarque.
               calcular_frete_por_nf — individual, uso interno.
               calcular_frete_em_lote — lote inteiro do embarque.
🔗 DEPENDE  : app.models.tabela_frete
             app.models.rota_frete
             app.models.nota_fiscal
             app.repositories.nota_fiscal_repository
             app.utils.normalizacao
📅 CRIADO   : 11/07/2026
📅 ATUALIZADO: 18/07/2026 — _calcular_e_persistir usa
              nf.transportadora_id (campo direto) e grava
              snapshots de auditoria.
📅 ATUALIZADO: 28/07/2026 — opção B: dimensão geográfica via
              RotaFrete. Novas exceções DestinoInvalidoError e
              RotaNaoEncontradaError. Piso valor_minimo_rota.
              Snapshots de rota no ResultadoFrete. Novo status
              SEM_ROTA no lote.
📅 ATUALIZADO: 28/07/2026 (v2) — alinhamento ao schema REAL:
                 - peso lido de nf.peso_total_kg (nome canônico);
                   nf.peso_real_kg NÃO existe;
                 - _obter_faixas sem filtro f.ativo (FaixaFrete
                   não possui essa coluna);
                 - NFs com status IGNORADA são puladas e contadas
                   separadamente (nunca recalculadas);
                 - prazo_dias da rota persistido na NF;
                 - arredondamento monetário explícito
                   (2 casas, ROUND_HALF_UP) — evita drift de
                   centavos na auditoria do CT-e;
                 - _resolver_rota com order_by determinístico.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
'''

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import TypedDict

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.nota_fiscal import NotaFiscal, StatusCalculoNF
from app.models.rota_frete import RotaFrete
from app.models.tabela_frete import FaixaFrete, TabelaFrete
from app.repositories.nota_fiscal_repository import (
    NotaFiscalRepository,
    atualizar_resultado_frete,
    buscar_por_embarque,
    buscar_por_embarque_e_id,
)
from app.utils.normalizacao import normalizar_cidade, normalizar_uf

# ═════════════════════════════════════════════════
# 📐 CONSTANTES DE NEGÓCIO (MVP)
# ═════════════════════════════════════════════════

PESO_LIMITE_FAIXA_FIXA = Decimal("30")
'''🎯 Divisor das duas faixas obrigatórias do MVP (kg).'''

ZERO = Decimal("0")
'''🎯 Neutro monetário/ponderal reutilizado no engine.'''

CENTAVO = Decimal("0.01")
'''🎯 Precisão de arredondamento monetário (2 casas).'''

CURINGA = "*"
'''🎯 Rótulo do destino curinga (cidade_normalizada IS NULL).'''


# ═════════════════════════════════════════════════
# ❌ EXCEÇÕES DE NEGÓCIO
# Erros específicos do cálculo de frete.
# ═════════════════════════════════════════════════

class CalculoFreteError(Exception):
    '''Exceção base para erros do engine de cálculo de frete.'''
    pass


class TransportadoraSemTabelaError(CalculoFreteError):
    '''
    A rota existe, mas a tabela vinculada não está com
    tabela_ativa=True. Problema de VIGÊNCIA da precificação.
    '''
    pass


class TabelaSemFaixasError(CalculoFreteError):
    '''Tabela ativa não possui faixas de peso configuradas.'''
    pass


class PesoInvalidoError(CalculoFreteError):
    '''Peso da NF é inválido (None, zero ou negativo).'''
    pass


class FaixaIncompletaError(CalculoFreteError):
    '''Tabela não possui as duas faixas obrigatórias do MVP (0→30 e 30→∞).'''
    pass


class DestinoInvalidoError(CalculoFreteError):
    '''
    🆕 28/07/2026
    NF sem UF de destino válida — impossível resolver a rota.
    '''
    pass


class RotaNaoEncontradaError(CalculoFreteError):
    '''
    🆕 28/07/2026
    Nenhuma rota ativa da transportadora atende o destino da
    NF (nem cidade específica, nem curinga da UF). Problema
    de COBERTURA geográfica.
    '''
    pass


class NFPertenceEmbarqueError(Exception):
    '''
    🆕 16/07/2026
    NF não pertence ao embarque informado.
    Lançada por calcular_frete_nf_no_embarque e
    capturada pelo router para retornar HTTP 404.
    '''
    pass


# ═════════════════════════════════════════════════
# 📦 TIPOS DE RETORNO
# ═════════════════════════════════════════════════

class ResultadoFrete(TypedDict):
    '''
    🎯 O QUE FAZ:
        Contrato de saída do engine de cálculo, com o valor
        final e todos os snapshots necessários para a
        auditoria posterior do CT-e.

    📐 REGRA DE NEGÓCIO:
        Os campos valor_* já vêm arredondados em 2 casas
        (ROUND_HALF_UP). peso_* preservam 3 casas.
    '''
    valor_frete: Decimal
    peso_utilizado_kg: Decimal
    tabela_id: str
    tabela_nome: str
    modalidade: str
    rota_id: str
    rota_uf: str
    rota_cidade: str | None
    rota_curinga: bool
    prazo_dias: int | None
    faixa_fixa_id: str
    valor_fixo: Decimal
    faixa_adicional_id: str | None
    valor_adicional: Decimal
    peso_excedente_kg: Decimal
    valor_minimo_rota: Decimal | None
    piso_aplicado: bool


class ResultadoCalculoNF(TypedDict):
    '''
    🎯 O QUE FAZ:
        Contrato de saída da orquestração por NF.

    📐 REGRA DE NEGÓCIO:
        Nunca propaga exceção: o motivo vem em 'status'
        e o detalhe em 'erro'.

        status ∈ { calculado, ignorada, sem_rota,
                   sem_tabela, sem_transportadora, erro }
    '''
    nf_id: str
    numero_nf: str
    status: str
    valor_frete: Decimal | None
    peso_utilizado_kg: Decimal | None
    tabela_nome: str | None
    rota: str | None
    prazo_dias: int | None
    erro: str | None


class ResultadoCalculoLote(TypedDict):
    '''
    🎯 O QUE FAZ:
        Contrato de saída do cálculo em lote, com contadores
        por status e o detalhe de cada NF.

    📐 REGRA DE NEGÓCIO:
        total_nfs = calculadas + ignoradas + sem_rota +
                    sem_tabela + sem_transportadora + erro
    '''
    embarque_id: str
    total_nfs: int
    calculadas: int
    ignoradas: int
    sem_rota: int
    sem_tabela: int
    sem_transportadora: int
    erro: int
    resultados: list[ResultadoCalculoNF]


# ═════════════════════════════════════════════════
# 🧮 ENGINE DE CÁLCULO (NÍVEL BAIXO)
# ═════════════════════════════════════════════════

def calcular_frete_nf(
    db: Session,
    transportadora_id: str,
    peso_total_kg: Decimal,
    uf_destino: str,
    cidade_destino: str | None = None,
    nf_id: str | None = None,
) -> ResultadoFrete:
    '''
    🎯 O QUE FAZ:
        Calcula o valor do frete de uma NF resolvendo a rota
        do destino e aplicando a tabela ativa da transportadora.

    📐 REGRA DE NEGÓCIO:
        1. Valida peso e destino.
        2. Resolve a rota (cidade específica → curinga da UF).
        3. Obtém a tabela vinculada à rota vencedora.
        4. Identifica as faixas obrigatórias do MVP.
        5. Aplica a fórmula progressiva.
        6. Aplica o piso valor_minimo_rota, se houver.
        7. Arredonda o valor final em 2 casas.

    📥 PARÂMETROS:
        db: Session              — sessão SQLAlchemy.
        transportadora_id: str   — transportadora da NF.
        peso_total_kg: Decimal   — peso total da NF em kg.
        uf_destino: str          — UF de destino da NF.
        cidade_destino: str|None — cidade de destino da NF.
        nf_id: str|None          — usado apenas nas mensagens.

    📤 RETORNO:
        ResultadoFrete: valor final + snapshots de auditoria.

    ❌ EXCEÇÕES:
        PesoInvalidoError, DestinoInvalidoError,
        RotaNaoEncontradaError, TransportadoraSemTabelaError,
        TabelaSemFaixasError, FaixaIncompletaError.

    ⚠️  ATENÇÃO:
        Função de LEITURA: consulta o banco, mas NÃO grava
        nada. A persistência é responsabilidade da camada
        de orquestração.
    '''
    _validar_peso(peso_total_kg, nf_id)
    uf, cidade = _validar_destino(uf_destino, cidade_destino, nf_id)

    rota = _resolver_rota(db, transportadora_id, uf, cidade)
    tabela = rota.tabela

    if tabela is None or not tabela.tabela_ativa:
        raise TransportadoraSemTabelaError(
            f"Transportadora {transportadora_id} não possui tabela "
            f"de frete ativa para o destino {uf}/{cidade or CURINGA}."
        )

    faixas = _obter_faixas(tabela)
    faixa_fixa, faixa_adicional = _identificar_faixas_mvp(faixas, tabela)

    return _aplicar_formula_progressiva(
        peso_total_kg=peso_total_kg,
        faixa_fixa=faixa_fixa,
        faixa_adicional=faixa_adicional,
        tabela=tabela,
        rota=rota,
    )


# ─────────────────────────────────────────────────
# 🔒 HELPERS DO ENGINE
# ─────────────────────────────────────────────────

def _quantizar_reais(valor: Decimal) -> Decimal:
    '''
    🎯 O QUE FAZ:
        Arredonda um valor monetário para 2 casas decimais.

    📐 REGRA DE NEGÓCIO:
        ROUND_HALF_UP — mesma convenção usada no rateio do
        CT-e. Divergir daqui gera falso positivo de
        divergência na auditoria.

    📥 PARÂMETROS:
        valor: Decimal — valor bruto do cálculo.

    📤 RETORNO:
        Decimal: valor com exatamente 2 casas.
    '''
    return valor.quantize(CENTAVO, rounding=ROUND_HALF_UP)


def _validar_peso(peso_total_kg: Decimal | None, nf_id: str | None) -> None:
    '''
    🎯 O QUE FAZ:
        Garante que o peso da NF é utilizável no cálculo.

    📐 REGRA DE NEGÓCIO:
        Peso deve ser informado e estritamente maior que 0.
        O campo de origem é notas_fiscais.peso_total_kg.

    ❌ EXCEÇÕES:
        PesoInvalidoError — peso None, zero ou negativo.
    '''
    if peso_total_kg is None:
        raise PesoInvalidoError(
            f"NF {nf_id or 'N/I'}: peso_total_kg é obrigatório."
        )
    if peso_total_kg <= ZERO:
        raise PesoInvalidoError(
            f"NF {nf_id or 'N/I'}: peso_total_kg deve ser > 0. "
            f"Informado: {peso_total_kg}."
        )


def _validar_destino(
    uf_destino: str | None,
    cidade_destino: str | None,
    nf_id: str | None,
) -> tuple[str, str | None]:
    '''
    🎯 O QUE FAZ:
        Normaliza a UF e a cidade de destino da NF usando
        app.utils.normalizacao.

    📐 REGRA DE NEGÓCIO:
        - UF é OBRIGATÓRIA (2 letras).
        - Cidade é opcional: sem cidade, apenas a rota
          curinga da UF pode ser resolvida.

    📤 RETORNO:
        tuple[str, str | None]: (uf, cidade_normalizada)

    ❌ EXCEÇÕES:
        DestinoInvalidoError — UF ausente ou inválida.

    ⚠️  ATENÇÃO:
        A normalização aqui DEVE ser idêntica à aplicada ao
        gravar rotas_frete.cidade_normalizada.
    '''
    uf = normalizar_uf(uf_destino)
    if uf is None or len(uf) != 2:
        raise DestinoInvalidoError(
            f"NF {nf_id or 'N/I'}: uf_destino é obrigatória para "
            f"resolver a rota. Informado: {uf_destino!r}."
        )

    return uf, normalizar_cidade(cidade_destino)


def _resolver_rota(
    db: Session,
    transportadora_id: str,
    uf: str,
    cidade: str | None,
) -> RotaFrete:
    '''
    🎯 O QUE FAZ:
        Resolve qual RotaFrete atende o destino informado.

    📐 REGRA DE NEGÓCIO:
        - Considera apenas rotas com ativo=True e tabelas
          com tabela_ativa=True da transportadora.
        - Precedência: rota com cidade específica SEMPRE
          vence a rota curinga da UF.
        - Se a NF não tem cidade, só o curinga é elegível.
        - Ordenação determinística: cidade preenchida antes
          do curinga; empate desfeito por criado_em.

    📥 PARÂMETROS:
        transportadora_id: str — transportadora da NF.
        uf: str                — UF normalizada.
        cidade: str | None     — cidade normalizada.

    📤 RETORNO:
        RotaFrete: rota vencedora, com 'tabela' acessível.

    ❌ EXCEÇÕES:
        RotaNaoEncontradaError — nenhuma rota atende.
    '''
    filtro_cidade = (
        or_(
            RotaFrete.cidade_normalizada == cidade,
            RotaFrete.cidade_normalizada.is_(None),
        )
        if cidade is not None
        else RotaFrete.cidade_normalizada.is_(None)
    )

    rotas = (
        db.query(RotaFrete)
        .join(TabelaFrete, TabelaFrete.id == RotaFrete.tabela_id)
        .filter(
            RotaFrete.ativo.is_(True),
            TabelaFrete.tabela_ativa.is_(True),
            TabelaFrete.transportadora_id == transportadora_id,
            RotaFrete.uf == uf,
            filtro_cidade,
        )
        .order_by(
            # NULLS LAST: rota específica vem primeiro
            RotaFrete.cidade_normalizada.is_(None).asc(),
            RotaFrete.criado_em.asc(),
        )
        .all()
    )

    if not rotas:
        raise RotaNaoEncontradaError(
            f"Transportadora {transportadora_id} não possui rota ativa "
            f"para o destino {uf}/{cidade or CURINGA}."
        )

    # A ordenação acima já garante a precedência da rota
    # específica sobre o curinga da UF.
    return rotas[0]


def _obter_faixas(tabela: TabelaFrete) -> list[FaixaFrete]:
    '''
    🎯 O QUE FAZ:
        Retorna as faixas da tabela ordenadas por peso_ate_kg,
        com a faixa aberta (NULL) sempre no fim.

    📤 RETORNO:
        list[FaixaFrete]: faixas ordenadas.

    ❌ EXCEÇÕES:
        TabelaSemFaixasError — tabela sem nenhuma faixa.

    ⚠️  ATENÇÃO:
        FaixaFrete NÃO possui coluna 'ativo' no schema
        físico. Desativar precificação = desativar a
        tabela inteira (tabela_ativa=False).
    '''
    faixas = sorted(
        tabela.faixas,
        key=lambda f: (f.peso_ate_kg is None, f.peso_ate_kg or ZERO),
    )
    if not faixas:
        raise TabelaSemFaixasError(
            f"Tabela '{tabela.nome}' (id={tabela.id}) não possui "
            f"faixas de peso configuradas."
        )
    return faixas


def _identificar_faixas_mvp(
    faixas: list[FaixaFrete],
    tabela: TabelaFrete,
) -> tuple[FaixaFrete, FaixaFrete]:
    '''
    🎯 O QUE FAZ:
        Identifica as duas faixas obrigatórias do MVP.

    📐 REGRA DE NEGÓCIO:
        - Faixa fixa      : peso_ate_kg = 30
        - Faixa adicional : peso_de_kg = 30 e peso_ate_kg IS NULL

    📤 RETORNO:
        tuple[FaixaFrete, FaixaFrete]: (fixa, adicional)

    ❌ EXCEÇÕES:
        FaixaIncompletaError — faltando uma das faixas.
    '''
    faixa_fixa = None
    faixa_adicional = None

    for faixa in faixas:
        if faixa.peso_ate_kg == PESO_LIMITE_FAIXA_FIXA:
            faixa_fixa = faixa
        elif (faixa.peso_ate_kg is None
              and faixa.peso_de_kg == PESO_LIMITE_FAIXA_FIXA):
            faixa_adicional = faixa

    if faixa_fixa is None:
        raise FaixaIncompletaError(
            f"Tabela '{tabela.nome}' (id={tabela.id}) não possui "
            f"faixa fixa (0 → 30 kg)."
        )
    if faixa_adicional is None:
        raise FaixaIncompletaError(
            f"Tabela '{tabela.nome}' (id={tabela.id}) não possui "
            f"faixa adicional (30 kg → ∞)."
        )

    return faixa_fixa, faixa_adicional


def _aplicar_formula_progressiva(
    peso_total_kg: Decimal,
    faixa_fixa: FaixaFrete,
    faixa_adicional: FaixaFrete,
    tabela: TabelaFrete,
    rota: RotaFrete,
) -> ResultadoFrete:
    '''
    🎯 O QUE FAZ:
        Aplica a fórmula progressiva do MVP, o piso da rota
        e o arredondamento monetário.

    📐 REGRA DE NEGÓCIO:
        peso ≤ 30 → frete = valor_minimo_faixa
        peso > 30 → frete = valor_minimo_faixa +
                            (peso − 30) × valor_kg
        Depois    → frete = max(frete, valor_minimo_rota)
        Por fim   → frete arredondado em 2 casas.

    📥 PARÂMETROS:
        faixa_fixa      — faixa 0 → 30 kg.
        faixa_adicional — faixa 30 kg → ∞.
        rota            — rota vencedora (piso e prazo).

    📤 RETORNO:
        ResultadoFrete: valor + snapshots de auditoria.
    '''
    valor_fixo = _quantizar_reais(faixa_fixa.valor_minimo_faixa or ZERO)

    if peso_total_kg <= PESO_LIMITE_FAIXA_FIXA:
        peso_excedente = ZERO
        valor_adicional = ZERO
        faixa_adicional_id = None
    else:
        peso_excedente = peso_total_kg - PESO_LIMITE_FAIXA_FIXA
        valor_adicional = _quantizar_reais(
            peso_excedente * (faixa_adicional.valor_kg or ZERO)
        )
        faixa_adicional_id = str(faixa_adicional.id)

    valor_frete = valor_fixo + valor_adicional

    # ── Piso da rota ─────────────────────────────
    piso = rota.valor_minimo_rota
    piso_aplicado = piso is not None and piso > valor_frete
    if piso_aplicado:
        valor_frete = piso

    return ResultadoFrete(
        valor_frete=_quantizar_reais(valor_frete),
        peso_utilizado_kg=peso_total_kg,
        tabela_id=str(tabela.id),
        tabela_nome=tabela.nome,
        modalidade=tabela.modalidade.value,
        rota_id=str(rota.id),
        rota_uf=rota.uf,
        rota_cidade=rota.cidade_normalizada,
        rota_curinga=rota.cidade_normalizada is None,
        prazo_dias=rota.prazo_dias,
        faixa_fixa_id=str(faixa_fixa.id),
        valor_fixo=valor_fixo,
        faixa_adicional_id=faixa_adicional_id,
        valor_adicional=valor_adicional,
        peso_excedente_kg=peso_excedente,
        valor_minimo_rota=piso,
        piso_aplicado=piso_aplicado,
    )


# ═════════════════════════════════════════════════
# 🎯 ORQUESTRAÇÃO (NÍVEL ALTO)
# ═════════════════════════════════════════════════

def calcular_frete_nf_no_embarque(
    db: Session,
    embarque_id: str,
    nf_id: str,
) -> ResultadoCalculoNF:
    '''
    🎯 O QUE FAZ:
        Ponto de entrada do endpoint individual. Valida o
        pertencimento NF ↔ embarque antes de calcular.

    📥 PARÂMETROS:
        embarque_id: str — embarque da requisição.
        nf_id: str       — NF a calcular.

    📤 RETORNO:
        ResultadoCalculoNF

    ❌ EXCEÇÕES:
        NFPertenceEmbarqueError — NF não pertence ao
        embarque (router → HTTP 404).

    📐 Demais falhas viram status no ResultadoCalculoNF
    (ignorada, sem_transportadora, sem_rota, sem_tabela, erro).
    '''
    nf = buscar_por_embarque_e_id(db, embarque_id, nf_id)
    if nf is None:
        raise NFPertenceEmbarqueError(
            f"NF {nf_id} não encontrada no embarque {embarque_id}."
        )

    return _calcular_e_persistir(db, nf)


def calcular_frete_por_nf(
    db: Session,
    nf_id: str,
) -> ResultadoCalculoNF:
    '''
    🎯 O QUE FAZ:
        Orquestra o cálculo de UMA NF sem validar embarque.

    📤 RETORNO:
        ResultadoCalculoNF

    ⚠️  ATENÇÃO:
        USO INTERNO (scripts, reprocessamento em massa).
        Não expor diretamente em rota HTTP: sem a validação
        de embarque não há isolamento de tenant.
    '''
    repo = NotaFiscalRepository(db)
    nf = repo.buscar_por_id(nf_id)
    if nf is None:
        return _erro_individual(
            nf_id=nf_id,
            numero_nf="N/I",
            status="erro",
            erro="NF não encontrada ou inativa.",
        )
    return _calcular_e_persistir(db, nf)


def calcular_frete_em_lote(
    db: Session,
    embarque_id: str,
) -> ResultadoCalculoLote:
    '''
    🎯 O QUE FAZ:
        Orquestra o cálculo de TODAS as NFs de um embarque.

    📐 REGRA DE NEGÓCIO:
        - Erro em uma NF NÃO interrompe o lote: cada NF
          recebe seu próprio status e mensagem.
        - NFs com status IGNORADA são contabilizadas mas
          NÃO recalculadas.

    📤 RETORNO:
        ResultadoCalculoLote: contadores + detalhe por NF.
    '''
    nfs = buscar_por_embarque(db, embarque_id)

    if not nfs:
        return _lote_vazio(embarque_id)

    resultados: list[ResultadoCalculoNF] = []
    contadores: dict[str, int] = {
        "calculado": 0,
        "ignorada": 0,
        "sem_rota": 0,
        "sem_tabela": 0,
        "sem_transportadora": 0,
        "erro": 0,
    }

    for nf in nfs:
        item = _calcular_e_persistir(db, nf)
        # .get evita KeyError se um status novo escapar
        # sem atualização deste dicionário.
        chave = item["status"] if item["status"] in contadores else "erro"
        contadores[chave] += 1
        resultados.append(item)

    return ResultadoCalculoLote(
        embarque_id=embarque_id,
        total_nfs=len(nfs),
        calculadas=contadores["calculado"],
        ignoradas=contadores["ignorada"],
        sem_rota=contadores["sem_rota"],
        sem_tabela=contadores["sem_tabela"],
        sem_transportadora=contadores["sem_transportadora"],
        erro=contadores["erro"],
        resultados=resultados,
    )


# ─────────────────────────────────────────────────
# 🔒 HELPERS DA ORQUESTRAÇÃO
# ─────────────────────────────────────────────────

def _lote_vazio(embarque_id: str) -> ResultadoCalculoLote:
    '''
    🎯 O QUE FAZ:
        Monta o retorno padrão para embarque sem NFs.

    📤 RETORNO:
        ResultadoCalculoLote: todos os contadores em zero.
    '''
    return ResultadoCalculoLote(
        embarque_id=embarque_id,
        total_nfs=0,
        calculadas=0,
        ignoradas=0,
        sem_rota=0,
        sem_tabela=0,
        sem_transportadora=0,
        erro=0,
        resultados=[],
    )


def _calcular_e_persistir(
    db: Session,
    nf: NotaFiscal,
) -> ResultadoCalculoNF:
    '''
    🎯 O QUE FAZ:
        Núcleo compartilhado da orquestração: pula NFs
        ignoradas, valida a transportadora, chama o engine
        com o destino da NF e persiste valor, prazo e
        snapshots de auditoria.

    📐 REGRA DE NEGÓCIO:
        - status IGNORADA → retorna sem tocar no banco.
        - transportadora_id é campo DIRETO da NF (populado
          na importação ou herdado do embarque).
        - O peso vem de nf.peso_total_kg (nome canônico do
          schema). NÃO existe nf.peso_real_kg.
        - prazo_dias é copiado da rota vencedora.

    📤 RETORNO:
        ResultadoCalculoNF

    ⚠️  ATENÇÃO:
        NUNCA lança exceção — toda falha é convertida em
        status persistido na NF.
    '''
    # ── NF ignorada não entra em cálculo (§6.7) ──
    if not nf.entra_no_calculo:
        return _erro_individual(
            nf_id=str(nf.id),
            numero_nf=nf.numero_nf,
            status="ignorada",
            erro="NF marcada como ignorada — cálculo não aplicável.",
        )

    # ── Sem transportadora: não há o que resolver ──
    if nf.transportadora_id is None:
        mensagem = "NF sem transportadora definida."
        _persistir_erro(db, nf, StatusCalculoNF.SEM_TRANSPORTADORA, mensagem)
        return _erro_individual(
            nf_id=str(nf.id),
            numero_nf=nf.numero_nf,
            status="sem_transportadora",
            erro=mensagem,
        )

    try:
        resultado = calcular_frete_nf(
            db=db,
            transportadora_id=str(nf.transportadora_id),
            peso_total_kg=nf.peso_total_kg,
            uf_destino=nf.uf_destino,
            cidade_destino=nf.cidade_destino,
            nf_id=str(nf.id),
        )

    except RotaNaoEncontradaError as exc:
        _persistir_erro(db, nf, StatusCalculoNF.SEM_ROTA, str(exc))
        return _erro_individual(
            nf_id=str(nf.id),
            numero_nf=nf.numero_nf,
            status="sem_rota",
            erro=str(exc),
        )

    except TransportadoraSemTabelaError as exc:
        _persistir_erro(db, nf, StatusCalculoNF.SEM_TABELA, str(exc))
        return _erro_individual(
            nf_id=str(nf.id),
            numero_nf=nf.numero_nf,
            status="sem_tabela",
            erro=str(exc),
        )

    except (PesoInvalidoError, DestinoInvalidoError,
            TabelaSemFaixasError, FaixaIncompletaError) as exc:
        _persistir_erro(db, nf, StatusCalculoNF.ERRO, str(exc))
        return _erro_individual(
            nf_id=str(nf.id),
            numero_nf=nf.numero_nf,
            status="erro",
            erro=str(exc),
        )

    # ── Sucesso: prazo + valor + snapshots ───────
    # prazo_dias é informativo e não faz parte do contrato
    # de atualizar_resultado_frete — gravado direto.
    nf.prazo_dias = resultado["prazo_dias"]

    atualizar_resultado_frete(
        db=db,
        nf=nf,
        valor_calculado=resultado["valor_frete"],
        preco_ate_30kg_usado=resultado["valor_fixo"],
        valor_kg_adicional_usado=resultado["valor_adicional"],
        peso_kg_usado=resultado["peso_utilizado_kg"],
        status=StatusCalculoNF.CALCULADO,
    )

    return ResultadoCalculoNF(
        nf_id=str(nf.id),
        numero_nf=nf.numero_nf,
        status="calculado",
        valor_frete=resultado["valor_frete"],
        peso_utilizado_kg=resultado["peso_utilizado_kg"],
        tabela_nome=resultado["tabela_nome"],
        rota=f"{resultado['rota_uf']}/{resultado['rota_cidade'] or CURINGA}",
        prazo_dias=resultado["prazo_dias"],
        erro=None,
    )


def _persistir_erro(
    db: Session,
    nf: NotaFiscal,
    status: StatusCalculoNF,
    mensagem: str,
) -> None:
    '''
    🎯 O QUE FAZ:
        Zera os campos de resultado da NF e grava o status
        de erro junto da mensagem explicativa.

    📐 REGRA DE NEGÓCIO:
        Nenhum resíduo de cálculo anterior pode permanecer
        quando o recálculo falha — evita auditar CT-e contra
        um valor obsoleto.

    📥 PARÂMETROS:
        status: StatusCalculoNF — motivo da falha.
        mensagem: str           — texto exibido ao operador.
    '''
    nf.prazo_dias = None

    atualizar_resultado_frete(
        db=db,
        nf=nf,
        valor_calculado=None,
        preco_ate_30kg_usado=None,
        valor_kg_adicional_usado=None,
        peso_kg_usado=None,
        status=status,
        erro=mensagem,
    )


def _erro_individual(
    *,
    nf_id: str,
    numero_nf: str,
    status: str,
    erro: str,
) -> ResultadoCalculoNF:
    '''
    🎯 O QUE FAZ:
        Monta o ResultadoCalculoNF padrão de falha,
        garantindo que todos os campos de valor fiquem None.

    📥 PARÂMETROS:
        status: str — ignorada | sem_rota | sem_tabela |
                      sem_transportadora | erro

    📤 RETORNO:
        ResultadoCalculoNF
    '''
    return ResultadoCalculoNF(
        nf_id=nf_id,
        numero_nf=numero_nf,
        status=status,
        valor_frete=None,
        peso_utilizado_kg=None,
        tabela_nome=None,
        rota=None,
        prazo_dias=None,
        erro=erro,
    )
