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
📅 ATUALIZADO: 16/07/2026 — lógica movida p/ service;
              router agora só faz HTTP in/out.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
'''

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.deps import get_db
from app.schemas.nf_schema import (
    CalcularFreteItemResponse,
    CalcularFreteLoteResponse,
)
from app.services.calculo_frete_service import (
    calcular_frete_em_lote,
    calcular_frete_nf_no_embarque,
    NFPertenceEmbarqueError,
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
    '''Dispara cálculo de frete para todas as NFs pendentes do embarque.'''
    return calcular_frete_em_lote(
        db=db,
        embarque_id=str(embarque_id),
    )


# ─────────────────────────────────────────────────
# 🧮 POST /embarques/{embarque_id}/notas/{nf_id}/calcular-frete
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
    Calcula o frete de uma única NF do embarque.

    📤 Retorna 404 se a NF não pertencer ao embarque.
    '''
    try:
        return calcular_frete_nf_no_embarque(
            db=db,
            embarque_id=str(embarque_id),
            nf_id=str(nf_id),
        )
    except NFPertenceEmbarqueError:
        raise HTTPException(
            status_code=404,
            detail=f"NF {nf_id} não encontrada no embarque {embarque_id}.",
        )
