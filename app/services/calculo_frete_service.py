'''
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📁 ARQUIVO : calculo_frete_service.py
📦 MÓDULO  : Services
🎯 OBJETIVO: Engine de cálculo de frete por NF.
             Recebe uma NF, localiza a tabela ativa
             da transportadora e aplica a fórmula
             progressiva definida no MVP:

               Se peso_total_kg ≤ 30:
                 frete = valor_minimo_faixa (faixa 0→30)
               Se peso_total_kg > 30:
                 frete = valor_minimo_faixa +
                         (peso_total_kg − 30) × valor_kg (faixa 30→∞)

             Retorna o valor calculado + metadados
             para auditoria (tabela, faixas, pesos).

             Camada de orquestração (calcular_frete_por_nf
             e calcular_frete_em_lote): busca a NF,
             navega até a transportadora, chama o engine,
             trata erros e persiste o resultado.
🔗 DEPENDE  : app.models.tabela_frete
             app.models.transportadora
             app.models.nota_fiscal
             app.repositories.nota_fiscal_repository
             app.core.exceptions
📅 CRIADO   : 11/07/2026
📅 ATUALIZADO: 11/07/2026 — criação inicial (MVP)
              11/07/2026 — + calcular_frete_por_nf,
              calcular_frete_em_lote (orquestração).
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
'''

from __future__ import annotations

from decimal import Decimal
from typing import TypedDict

from sqlalchemy.orm import Session

from app.models.nota_fiscal import NotaFiscal, StatusCalculoNF
from app.models.tabela_frete import (
    FaixaFrete,
    ModalidadeFrete,
    TabelaFrete,
)
from app.repositories.nota_fiscal_repository import (
    NotaFiscalRepository,
    atualizar_resultado_frete,
    buscar_por_embarque,
)


# ═════════════════════════════════════════════════
# ❌ EXCEÇÕES DE NEGÓCIO
# Erros específicos do cálculo de frete.
# ═════════════════════════════════════════════════

class CalculoFreteError(Exception):
    '''
    🎯 O QUE FAZ:
        Exceção base para erros do engine de cálculo
        de frete. Herde dela para erros específicos.
    '''
    pass


class TransportadoraSemTabelaError(CalculoFreteError):
    '''
    🎯 O QUE FAZ:
        Lançada quando a transportadora da NF não
        possui nenhuma tabela com tabela_ativa=True.
    '''
    pass


class TabelaSemFaixasError(CalculoFreteError):
    '''
    🎯 O QUE FAZ:
        Lançada quando a tabela ativa não possui
        faixas de peso configuradas.
    '''
    pass


class PesoInvalidoError(CalculoFreteError):
    '''
    🎯 O QUE FAZ:
        Lançada quando o peso informado na NF é
        inválido (None, zero ou negativo).
    '''
    pass


class FaixaIncompletaError(CalculoFreteError):
    '''
    🎯 O QUE FAZ:
        Lançada quando a tabela não possui as duas
        faixas obrigatórias do MVP (0→30 e 30→∞).
    '''
    pass


# ═════════════════════════════════════════════════
# 📦 TIPOS DE RETORNO
# Estruturas devolvidas pelo engine e pela camada
# de orquestração.
# ═════════════════════════════════════════════════

class ResultadoFrete(TypedDict):
    '''
    🎯 O QUE FAZ:
        Tipagem do dicionário retornado por
        calcular_frete_nf. Contém o valor final
        e todos os metadados necessários para
        auditoria e rastreabilidade.

    📐 CAMPOS:
        - valor_frete        : Decimal — valor final do frete
        - peso_utilizado_kg  : Decimal — peso efetivamente usado
        - tabela_id          : str    — UUID da tabela aplicada
        - tabela_nome        : str    — nome da tabela
        - modalidade         : str    — progressivo | por_faixa
        - faixa_fixa_id      : str    — UUID da faixa 0→30 usada
        - valor_fixo         : Decimal — valor_minimo_faixa da faixa 1
        - faixa_adicional_id : str|None — UUID da faixa 30→∞
        - valor_adicional    : Decimal — valor do adicional (se houver)
        - peso_excedente_kg  : Decimal — kg acima de 30 (se houver)
    '''
    valor_frete: Decimal
    peso_utilizado_kg: Decimal
    tabela_id: str
    tabela_nome: str
    modalidade: str
    faixa_fixa_id: str
    valor_fixo: Decimal
    faixa_adicional_id: str | None
    valor_adicional: Decimal
    peso_excedente_kg: Decimal


class ResultadoCalculoNF(TypedDict):
    '''
    🎯 O QUE FAZ:
        Resultado da orquestração para UMA NF:
        contém o status final e, se calculado,
        os valores de frete e metadados.

    📐 CAMPOS:
        - nf_id              : str  — UUID da NF
        - numero_nf          : str  — número fiscal
        - status             : str  — calculado | sem_tabela
                                      | sem_transportadora | erro
        - valor_frete        : Decimal|None
        - peso_utilizado_kg  : Decimal|None
        - tabela_nome        : str|None
        - erro               : str|None
    '''
    nf_id: str
    numero_nf: str
    status: str
    valor_frete: Decimal | None
    peso_utilizado_kg: Decimal | None
    tabela_nome: str | None
    erro: str | None


class ResultadoCalculoLote(TypedDict):
    '''
    🎯 O QUE FAZ:
        Resultado da orquestração para um EMBARQUE
        inteiro (lote). Agrega os contadores e a
        lista de ResultadoCalculoNF.

    📐 CAMPOS:
        - embarque_id        : str  — UUID do embarque
        - total_nfs          : int
        - calculadas         : int
        - sem_tabela         : int
        - sem_transportadora : int
        - erro               : int
        - resultados         : list[ResultadoCalculoNF]
    '''
    embarque_id: str
    total_nfs: int
    calculadas: int
    sem_tabela: int
    sem_transportadora: int
    erro: int
    resultados: list[ResultadoCalculoNF]


# ═════════════════════════════════════════════════
# 🧮 ENGINE DE CÁLCULO (NÍVEL BAIXO)
# Funções puras: recebem parâmetros, devolvem
# ResultadoFrete ou lançam exceção.
# ═════════════════════════════════════════════════

def calcular_frete_nf(
    db: Session,
    transportadora_id: str,
    peso_total_kg: Decimal,
    nf_id: str | None = None,
) -> ResultadoFrete:
    '''
    🎯 O QUE FAZ:
        Calcula o valor do frete de uma NF aplicando
        a tabela ativa da transportadora.

    📥 PARÂMETROS:
        db                : Session SQLAlchemy ativa.
        transportadora_id : UUID da transportadora da NF.
        peso_total_kg     : Peso total da NF em kg.
        nf_id             : (opcional) ID da NF, apenas
                            para mensagens de erro mais
                            claras.

    📤 RETORNO:
        ResultadoFrete — dicionário com o valor calculado
        e todos os metadados de rastreabilidade.

    ❌ EXCEÇÕES:
        PesoInvalidoError              — peso ≤ 0 ou None.
        TransportadoraSemTabelaError   — sem tabela ativa.
        TabelaSemFaixasError           — tabela sem faixas.
        FaixaIncompletaError           — faltam faixas do MVP.

    📐 FLUXO:
        1. Valida peso_total_kg.
        2. Busca tabela ativa da transportadora.
        3. Busca faixas ordenadas por peso_ate_kg.
        4. Identifica faixa fixa (0→30) e faixa adicional (30→∞).
        5. Aplica fórmula progressiva.
        6. Retorna ResultadoFrete.

    ⚠️  ATENÇÃO:
        Não modificar sem autorização de Allison.
    '''
    # ── 1. Validação do peso ─────────────────────
    _validar_peso(peso_total_kg, nf_id)

    # ── 2. Busca da tabela ativa ─────────────────
    tabela = _obter_tabela_ativa(db, transportadora_id)

    # ── 3. Busca das faixas ──────────────────────
    faixas = _obter_faixas(tabela)

    # ── 4. Identificação das faixas do MVP ───────
    faixa_fixa, faixa_adicional = _identificar_faixas_mvp(faixas, tabela)

    # ── 5. Cálculo do frete ──────────────────────
    return _aplicar_formula_progressiva(
        peso_total_kg=peso_total_kg,
        faixa_fixa=faixa_fixa,
        faixa_adicional=faixa_adicional,
        tabela=tabela,
    )


# ─────────────────────────────────────────────────
# 🔒 HELPERS DO ENGINE
# ─────────────────────────────────────────────────

def _validar_peso(peso_total_kg: Decimal, nf_id: str | None) -> None:
    if peso_total_kg is None:
        raise PesoInvalidoError(
            f"NF {nf_id or 'N/I'}: peso_total_kg é obrigatório."
        )
    if peso_total_kg <= 0:
        raise PesoInvalidoError(
            f"NF {nf_id or 'N/I'}: peso_total_kg deve ser > 0. "
            f"Informado: {peso_total_kg}."
        )


def _obter_tabela_ativa(db: Session, transportadora_id: str) -> TabelaFrete:
    tabela = (
        db.query(TabelaFrete)
        .filter(
            TabelaFrete.transportadora_id == transportadora_id,
            TabelaFrete.tabela_ativa.is_(True),
        )
        .first()
    )
    if tabela is None:
        raise TransportadoraSemTabelaError(
            f"Transportadora {transportadora_id} não possui "
            f"tabela de frete ativa. Cadastre uma tabela e "
            f"marque-a como ativa antes de calcular o frete."
        )
    return tabela


def _obter_faixas(tabela: TabelaFrete) -> list[FaixaFrete]:
    faixas = sorted(
        tabela.faixas,
        key=lambda f: (f.peso_ate_kg is None, f.peso_ate_kg or 0),
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
    faixa_fixa = None
    faixa_adicional = None

    for faixa in faixas:
        if faixa.peso_ate_kg is not None and faixa.peso_ate_kg == Decimal("30"):
            faixa_fixa = faixa
        elif faixa.peso_ate_kg is None and faixa.peso_de_kg == Decimal("30"):
            faixa_adicional = faixa

    if faixa_fixa is None:
        raise FaixaIncompletaError(
            f"Tabela '{tabela.nome}' (id={tabela.id}) não possui "
            f"faixa fixa (0 → 30 kg). Cadastre a faixa com "
            f"peso_de_kg=0 e peso_ate_kg=30."
        )
    if faixa_adicional is None:
        raise FaixaIncompletaError(
            f"Tabela '{tabela.nome}' (id={tabela.id}) não possui "
            f"faixa adicional (30 kg → ∞). Cadastre a faixa com "
            f"peso_de_kg=30 e peso_ate_kg=NULL."
        )

    return faixa_fixa, faixa_adicional


def _aplicar_formula_progressiva(
    peso_total_kg: Decimal,
    faixa_fixa: FaixaFrete,
    faixa_adicional: FaixaFrete,
    tabela: TabelaFrete,
) -> ResultadoFrete:
    valor_fixo = faixa_fixa.valor_minimo_faixa or Decimal("0")
    peso_limite = Decimal("30")

    # ── Caso 1: peso dentro da faixa fixa ────────
    if peso_total_kg <= peso_limite:
        return ResultadoFrete(
            valor_frete=valor_fixo,
            peso_utilizado_kg=peso_total_kg,
            tabela_id=str(tabela.id),
            tabela_nome=tabela.nome,
            modalidade=tabela.modalidade.value,
            faixa_fixa_id=str(faixa_fixa.id),
            valor_fixo=valor_fixo,
            faixa_adicional_id=None,
            valor_adicional=Decimal("0"),
            peso_excedente_kg=Decimal("0"),
        )

    # ── Caso 2: peso excede a faixa fixa ─────────
    peso_excedente = peso_total_kg - peso_limite
    valor_adicional = peso_excedente * faixa_adicional.valor_kg
    valor_frete = valor_fixo + valor_adicional

    return ResultadoFrete(
        valor_frete=valor_frete,
        peso_utilizado_kg=peso_total_kg,
        tabela_id=str(tabela.id),
        tabela_nome=tabela.nome,
        modalidade=tabela.modalidade.value,
        faixa_fixa_id=str(faixa_fixa.id),
        valor_fixo=valor_fixo,
        faixa_adicional_id=str(faixa_adicional.id),
        valor_adicional=valor_adicional,
        peso_excedente_kg=peso_excedente,
    )


# ═════════════════════════════════════════════════
# 🎯 ORQUESTRAÇÃO (NÍVEL ALTO)
# Funções que o router chama. Cuidam de:
#   - buscar NF e navegar até transportadora
#   - tratar exceções do engine → status
#   - persistir resultado via repository
# ═════════════════════════════════════════════════

def calcular_frete_por_nf(
    db: Session,
    nf_id: str,
) -> ResultadoCalculoNF:
    '''
    🎯 O QUE FAZ:
        Orquestra o cálculo de frete para UMA NF:
        busca a NF, obtém a transportadora do embarque,
        chama o engine e persiste o resultado.

    📥 PARÂMETROS:
        db    : Session SQLAlchemy ativa.
        nf_id : UUID da NotaFiscal.

    📤 RETORNO:
        ResultadoCalculoNF com status e, se sucesso,
        valor_frete + metadados. NUNCA lança exceção
        — erros viram status + campo erro preenchido.

    📐 STATUS POSSÍVEIS:
        - "calculado"          : frete calculado com sucesso.
        - "sem_transportadora" : embarque não tem transportadora.
        - "sem_tabela"         : transportadora sem tabela ativa.
        - "erro"               : peso inválido, faixas incompletas, etc.
    '''
    repo = NotaFiscalRepository(db)

    # ── 1. Busca a NF ────────────────────────────
    nf = repo.buscar_por_id(nf_id)
    if nf is None:
        return _erro_individual(
            nf_id=nf_id,
            numero_nf="N/I",
            status="erro",
            erro="NF não encontrada ou inativa.",
        )

    # ── 2. Navega até a transportadora ───────────
    if nf.embarque is None or nf.embarque.transportadora_id is None:
        _persistir_erro(db, nf, StatusCalculoNF.SEM_TRANSPORTADORA,
                        "Embarque sem transportadora definida.")
        return _erro_individual(
            nf_id=str(nf.id),
            numero_nf=nf.numero_nf,
            status="sem_transportadora",
            erro="Embarque sem transportadora definida.",
        )

    transportadora_id = str(nf.embarque.transportadora_id)

    # ── 3. Chama o engine ────────────────────────
    try:
        resultado = calcular_frete_nf(
            db=db,
            transportadora_id=transportadora_id,
            peso_total_kg=nf.peso_real_kg,
            nf_id=str(nf.id),
        )
    except TransportadoraSemTabelaError as exc:
        _persistir_erro(db, nf, StatusCalculoNF.SEM_TABELA, str(exc))
        return _erro_individual(
            nf_id=str(nf.id),
            numero_nf=nf.numero_nf,
            status="sem_tabela",
            erro=str(exc),
        )
    except (PesoInvalidoError, TabelaSemFaixasError, FaixaIncompletaError) as exc:
        _persistir_erro(db, nf, StatusCalculoNF.ERRO, str(exc))
        return _erro_individual(
            nf_id=str(nf.id),
            numero_nf=nf.numero_nf,
            status="erro",
            erro=str(exc),
        )

    # ── 4. Persiste o sucesso ────────────────────
    atualizar_resultado_frete(
        db=db,
        nf=nf,
        resultado=resultado,
        status=StatusCalculoNF.CALCULADO,
    )

    return ResultadoCalculoNF(
        nf_id=str(nf.id),
        numero_nf=nf.numero_nf,
        status="calculado",
        valor_frete=resultado["valor_frete"],
        peso_utilizado_kg=resultado["peso_utilizado_kg"],
        tabela_nome=resultado["tabela_nome"],
        erro=None,
    )


def calcular_frete_em_lote(
    db: Session,
    embarque_id: str,
) -> ResultadoCalculoLote:
    '''
    🎯 O QUE FAZ:
        Orquestra o cálculo de frete para TODAS as
        NFs de um embarque. Itera sobre cada NF,
        chama o engine, trata erros individualmente
        e persiste cada resultado.

    📥 PARÂMETROS:
        db          : Session SQLAlchemy ativa.
        embarque_id : UUID do embarque.

    📤 RETORNO:
        ResultadoCalculoLote com contadores agregados
        e lista detalhada de ResultadoCalculoNF.

    📐 REGRA DE NEGÓCIO:
        - O erro em uma NF NÃO interrompe o lote.
        - Cada NF tem seu resultado individual.
        - O commit é feito pelo chamador (router),
          normalmente ao final do lote inteiro.
    '''
    # ── 1. Busca todas as NFs do embarque ────────
    nfs = buscar_por_embarque(db, embarque_id)

    if not nfs:
        return ResultadoCalculoLote(
            embarque_id=embarque_id,
            total_nfs=0,
            calculadas=0,
            sem_tabela=0,
            sem_transportadora=0,
            erro=0,
            resultados=[],
        )

    # ── 2. Itera sobre cada NF ───────────────────
    resultados: list[ResultadoCalculoNF] = []
    contadores = {
        "calculadas": 0,
        "sem_tabela": 0,
        "sem_transportadora": 0,
        "erro": 0,
    }

    for nf in nfs:
        item = _calcular_uma_nf_no_lote(db, nf)
        contadores[item["status"]] += 1
        resultados.append(item)

    return ResultadoCalculoLote(
        embarque_id=embarque_id,
        total_nfs=len(nfs),
        calculadas=contadores["calculadas"],
        sem_tabela=contadores["sem_tabela"],
        sem_transportadora=contadores["sem_transportadora"],
        erro=contadores["erro"],
        resultados=resultados,
    )


# ─────────────────────────────────────────────────
# 🔒 HELPERS DA ORQUESTRAÇÃO
# ─────────────────────────────────────────────────

def _calcular_uma_nf_no_lote(
    db: Session,
    nf: NotaFiscal,
) -> ResultadoCalculoNF:
    '''
    🎯 O QUE FAZ:
        Orquestra o cálculo de UMA NF dentro do lote.
        Similar a calcular_frete_por_nf, mas recebe
        o model já carregado (evita query extra).

    📐 REGRA:
        NUNCA lança exceção — todo erro vira status.
    '''
    # ── Verifica transportadora ──────────────────
    if nf.embarque is None or nf.embarque.transportadora_id is None:
        _persistir_erro(db, nf, StatusCalculoNF.SEM_TRANSPORTADORA,
                        "Embarque sem transportadora definida.")
        return _erro_individual(
            nf_id=str(nf.id),
            numero_nf=nf.numero_nf,
            status="sem_transportadora",
            erro="Embarque sem transportadora definida.",
        )

    transportadora_id = str(nf.embarque.transportadora_id)

    # ── Chama o engine ───────────────────────────
    try:
        resultado = calcular_frete_nf(
            db=db,
            transportadora_id=transportadora_id,
            peso_total_kg=nf.peso_real_kg,
            nf_id=str(nf.id),
        )
    except TransportadoraSemTabelaError as exc:
        _persistir_erro(db, nf, StatusCalculoNF.SEM_TABELA, str(exc))
        return _erro_individual(
            nf_id=str(nf.id),
            numero_nf=nf.numero_nf,
            status="sem_tabela",
            erro=str(exc),
        )
    except (PesoInvalidoError, TabelaSemFaixasError, FaixaIncompletaError) as exc:
        _persistir_erro(db, nf, StatusCalculoNF.ERRO, str(exc))
        return _erro_individual(
            nf_id=str(nf.id),
            numero_nf=nf.numero_nf,
            status="erro",
            erro=str(exc),
        )

    # ── Persiste o sucesso ───────────────────────
    atualizar_resultado_frete(
        db=db,
        nf=nf,
        resultado=resultado,
        status=StatusCalculoNF.CALCULADO,
    )

    return ResultadoCalculoNF(
        nf_id=str(nf.id),
        numero_nf=nf.numero_nf,
        status="calculado",
        valor_frete=resultado["valor_frete"],
        peso_utilizado_kg=resultado["peso_utilizado_kg"],
        tabela_nome=resultado["tabela_nome"],
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
        Atualiza a NF com status de erro e mensagem,
        usando o wrapper do repository.
    '''
    atualizar_resultado_frete(
        db=db,
        nf=nf,
        resultado=None,
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
        Fabrica um ResultadoCalculoNF de falha,
        com todos os campos de sucesso zerados.

    📐 REGRA:
        Evita repetição de código nos handlers de erro.
    '''
    return ResultadoCalculoNF(
        nf_id=nf_id,
        numero_nf=numero_nf,
        status=status,
        valor_frete=None,
        peso_utilizado_kg=None,
        tabela_nome=None,
        erro=erro,
    )
