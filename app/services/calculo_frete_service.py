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

             Camada de orquestração:
               calcular_frete_nf_no_embarque — individual com
                 validação de pertencimento ao embarque.
               calcular_frete_em_lote — lote inteiro do embarque.
🔗 DEPENDE  : app.models.tabela_frete
             app.models.transportadora
             app.models.nota_fiscal
             app.repositories.nota_fiscal_repository
             app.core.exceptions
📅 CRIADO   : 11/07/2026
📅 ATUALIZADO: 16/07/2026 — +NFPertenceEmbarqueError;
              calcular_frete_nf_no_embarque agora lança
              exceção; router só trata HTTP.
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
    buscar_por_embarque_e_id,
)


# ═════════════════════════════════════════════════
# ❌ EXCEÇÕES DE NEGÓCIO
# Erros específicos do cálculo de frete.
# ═════════════════════════════════════════════════

class CalculoFreteError(Exception):
    '''Exceção base para erros do engine de cálculo de frete.'''
    pass


class TransportadoraSemTabelaError(CalculoFreteError):
    '''Transportadora da NF não possui tabela com tabela_ativa=True.'''
    pass


class TabelaSemFaixasError(CalculoFreteError):
    '''Tabela ativa não possui faixas de peso configuradas.'''
    pass


class PesoInvalidoError(CalculoFreteError):
    '''Peso informado na NF é inválido (None, zero ou negativo).'''
    pass


class FaixaIncompletaError(CalculoFreteError):
    '''Tabela não possui as duas faixas obrigatórias do MVP (0→30 e 30→∞).'''
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
    nf_id: str
    numero_nf: str
    status: str
    valor_frete: Decimal | None
    peso_utilizado_kg: Decimal | None
    tabela_nome: str | None
    erro: str | None


class ResultadoCalculoLote(TypedDict):
    embarque_id: str
    total_nfs: int
    calculadas: int
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
    nf_id: str | None = None,
) -> ResultadoFrete:
    '''
    🎯 Calcula o valor do frete de uma NF aplicando
    a tabela ativa da transportadora.

    ❌ EXCEÇÕES:
        PesoInvalidoError, TransportadoraSemTabelaError,
        TabelaSemFaixasError, FaixaIncompletaError.
    '''
    _validar_peso(peso_total_kg, nf_id)
    tabela = _obter_tabela_ativa(db, transportadora_id)
    faixas = _obter_faixas(tabela)
    faixa_fixa, faixa_adicional = _identificar_faixas_mvp(faixas, tabela)
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
            f"tabela de frete ativa."
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
) -> ResultadoFrete:
    valor_fixo = faixa_fixa.valor_minimo_faixa or Decimal("0")
    peso_limite = Decimal("30")

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
# ═════════════════════════════════════════════════

def calcular_frete_nf_no_embarque(
    db: Session,
    embarque_id: str,
    nf_id: str,
) -> ResultadoCalculoNF:
    '''
    🎯 Ponto de entrada do endpoint individual.
    Valida pertencimento NF↔embarque.

    ❌ EXCEÇÕES:
        NFPertenceEmbarqueError — NF não pertence ao embarque
        (capturada pelo router → HTTP 404).

    📐 Demais erros viram status no ResultadoCalculoNF
    (sem_transportadora, sem_tabela, erro).
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
    🎯 Orquestra cálculo para UMA NF (sem validação de embarque).
    ⚠️ USO INTERNO.
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
    🎯 Orquestra cálculo para TODAS as NFs de um embarque.
    Erro em uma NF NÃO interrompe o lote.
    '''
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

    resultados: list[ResultadoCalculoNF] = []
    contadores = {
        "calculadas": 0,
        "sem_tabela": 0,
        "sem_transportadora": 0,
        "erro": 0,
    }

    for nf in nfs:
        item = _calcular_e_persistir(db, nf)
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

def _calcular_e_persistir(
    db: Session,
    nf: NotaFiscal,
) -> ResultadoCalculoNF:
    '''
    🎯 Núcleo compartilhado: recebe model NotaFiscal,
    navega até transportadora, chama engine e persiste.
    NUNCA lança exceção — todo erro vira status.
    '''
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
    return ResultadoCalculoNF(
        nf_id=nf_id,
        numero_nf=numero_nf,
        status=status,
        valor_frete=None,
        peso_utilizado_kg=None,
        tabela_nome=None,
        erro=erro,
    )
