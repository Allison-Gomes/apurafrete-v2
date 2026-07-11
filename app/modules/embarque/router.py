'''
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📁 ARQUIVO : router.py
📦 MÓDULO  : Embarque
🎯 OBJETIVO: Rotas HTTP do módulo de embarque:
               - Importação de NFs (planilha)
               - Cálculo de frete (individual e lote)
               - Exportação de embarque
🔗 DEPENDE  : app.services.calculo_frete_service
             app.schemas.nf_schema
             app.core.deps
📅 CRIADO   : 07/07/2026
📅 ATUALIZADO: 11/07/2026 — rotas de cálculo de frete
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
'''

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.deps import get_db
from app.schemas.nf_schema import (
    CalcularFreteItemResponse,
    CalcularFreteLoteResponse,
    NotaFiscalRead,
)
from app.services.calculo_frete_service import (
    calcular_frete_embarque,
    calcular_frete_nf,
    PesoInvalidoError,
    TransportadoraSemTabelaError,
    TabelaSemFaixasError,
    FaixaIncompletaError,
)
from app.models.nota_fiscal import NotaFiscal, StatusCalculoNF
from app.repositories.nota_fiscal_repository import (
    atualizar_resultado_frete,
)

router = APIRouter(prefix='/embarques', tags=['Embarque'])


# ─────────────────────────────────────────────────
# 🩺 Health check
# ─────────────────────────────────────────────────
@router.get('/health')
async def health():
    '''Health check do módulo.'''
    return {'modulo': 'embarque', 'status': 'ok'}


# ─────────────────────────────────────────────────
# 🧮 POST /embarques/{embarque_id}/calcular-frete
# Cálculo em lote de todas as NFs pendentes.
# ─────────────────────────────────────────────────
@router.post(
    '/{embarque_id}/calcular-frete',
    response_model=CalcularFreteLoteResponse,
    summary="Calcular frete de todas as NFs do embarque",
)
def calcular_frete_lote(
    embarque_id: UUID,
    db: Session = Depends(get_db),
):
    '''
    🎯 O QUE FAZ:
        Dispara o cálculo de frete para todas as NFs
        com status_calculo = PENDENTE do embarque.

    📐 REGRA DE NEGÓCIO:
        - NFs já CALCULADAS são ignoradas.
        - NF sem transportadora → SEM_TRANSPORTADORA.
        - Transportadora sem tabela ativa → SEM_TABELA.
        - Erro de peso/configuração → ERRO.
        - Commit único no final do lote.

    📤 RETORNO:
        CalcularFreteLoteResponse com resumo consolidado.
    '''
    resultado = calcular_frete_embarque(
        db=db,
        embarque_id=str(embarque_id),
    )
    return resultado


# ─────────────────────────────────────────────────
# 🧮 POST /embarques/{embarque_id}/notas/{nf_id}/calcular-frete
# Cálculo individual de uma NF específica.
# ─────────────────────────────────────────────────
@router.post(
    '/{embarque_id}/notas/{nf_id}/calcular-frete',
    response_model=CalcularFreteItemResponse,
    summary="Calcular frete de uma NF específica",
)
def calcular_frete_nf_individual(
    embarque_id: UUID,
    nf_id: UUID,
    db: Session = Depends(get_db),
):
    '''
    🎯 O QUE FAZ:
        Calcula o frete de uma única NF do embarque.

    📐 REGRA DE NEGÓCIO:
        - NF deve pertencer ao embarque informado.
        - Mesmas validações do cálculo em lote.
        - Atualiza a NF e commita.

    📤 RETORNO:
        CalcularFreteItemResponse com o resultado.
    '''
    nf = db.query(NotaFiscal).filter(
        NotaFiscal.id == nf_id,
        NotaFiscal.embarque_id == embarque_id,
    ).first()

    if nf is None:
        raise HTTPException(
            status_code=404,
            detail=f"NF {nf_id} não encontrada no embarque {embarque_id}.",
        )

    # ── Validações pré-cálculo ────────────────────
    if nf.transportadora_id is None:
        atualizar_resultado_frete(
            db, nf,
            status=StatusCalculoNF.SEM_TRANSPORTADORA,
            erro="NF sem transportadora definida.",
        )
        db.commit()
        return CalcularFreteItemResponse(
            nf_id=nf.id,
            numero_nf=nf.numero_nf,
            status="sem_transportadora",
            erro="NF sem transportadora definida.",
        )

    if nf.peso_real_kg is None or nf.peso_real_kg <= 0:
        atualizar_resultado_frete(
            db, nf,
            status=StatusCalculoNF.ERRO,
            erro="Peso da NF inválido (None, zero ou negativo).",
        )
        db.commit()
        return CalcularFreteItemResponse(
            nf_id=nf.id,
            numero_nf=nf.numero_nf,
            status="erro",
            erro="Peso da NF inválido (None, zero ou negativo).",
        )

    # ── Cálculo ───────────────────────────────────
    try:
        resultado = calcular_frete_nf(
            db=db,
            transportadora_id=str(nf.transportadora_id),
            peso_total_kg=nf.peso_real_kg,
            nf_id=str(nf.id),
        )
        atualizar_resultado_frete(
            db, nf,
            resultado=resultado,
            status=StatusCalculoNF.CALCULADO,
        )
        db.commit()
        return CalcularFreteItemResponse(
            nf_id=nf.id,
            numero_nf=nf.numero_nf,
            status="calculado",
            valor_frete=resultado["valor_frete"],
            peso_utilizado_kg=resultado["peso_utilizado_kg"],
            tabela_nome=resultado["tabela_nome"],
        )

    except TransportadoraSemTabelaError as e:
        atualizar_resultado_frete(
            db, nf,
            status=StatusCalculoNF.SEM_TABELA,
            erro=str(e),
        )
        db.commit()
        return CalcularFreteItemResponse(
            nf_id=nf.id,
            numero_nf=nf.numero_nf,
            status="sem_tabela",
            erro=str(e),
        )

    except (PesoInvalidoError, TabelaSemFaixasError, FaixaIncompletaError) as e:
        atualizar_resultado_frete(
            db, nf,
            status=StatusCalculoNF.ERRO,
            erro=str(e),
        )
        db.commit()
        return CalcularFreteItemResponse(
            nf_id=nf.id,
            numero_nf=nf.numero_nf,
            status="erro",
            erro=str(e),
        )
