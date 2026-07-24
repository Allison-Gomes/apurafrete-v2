# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 📁 ARQUIVO : router.py
# 📦 MÓDULO  : Embarque
# 🎯 OBJETIVO: Rotas HTTP do módulo de embarque:
#                - Importação de NFs (planilha)  ← NOVO
#                - Cálculo de frete (individual e lote)
#                - Exportação de embarque
# 🔗 DEPENDE  : app.services.import_service
#              app.services.calculo_frete_service
#              app.services.exportacao_service
#              app.schemas.nf_schema
#              app.core.deps
# 📅 CRIADO   : 07/07/2026
# 📅 ATUALIZADO: 18/07/2026 — adicionado endpoint de
#               importação (Etapa 5) + exportação
#               (Etapa 4); try/except no exportar.
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

from io import BytesIO
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.deps import get_db
from app.exceptions.embarque_exceptions import EmbarqueNaoEncontradoError
from app.schemas.nf_schema import (
    CalcularFreteItemResponse,
    CalcularFreteLoteResponse,
)
from app.services.calculo_frete_service import (
    NFPertenceEmbarqueError,
    calcular_frete_em_lote,
    calcular_frete_nf_no_embarque,
)
from app.services.exportacao_service import exportar_embarque
from app.services.import_service import (
    ImportLoteResult,
    carregar_catalogo_produtos,
    importar_nfs,
    parse_planilha_nf,
)

router = APIRouter(prefix='/embarques', tags=['Embarque'])


# ─────────────────────────────────────────────────
# 🩺 Health check
# ─────────────────────────────────────────────────
@router.get('/health')
async def health():
    '''Health check do módulo.'''
    return {'modulo': 'embarque', 'status': 'ok'}


# ══════════════════════════════════════════════════
# 📥 POST /embarques/{embarque_id}/importar
# ══════════════════════════════════════════════════
@router.post(
    '/{embarque_id}/importar',
    response_model=ImportLoteResult,
    summary="Importar NFs de planilha Excel",
    description=(
        "Faz upload de uma planilha .xlsx com NFs e as importa "
        "para o embarque informado. Linhas válidas viram NFs; "
        "erros de validação são reportados linha a linha. "
        "Duplicatas são ignoradas silenciosamente."
    ),
)
async def importar_planilha_nf(
    embarque_id: UUID,
    arquivo: UploadFile = File(..., description="Planilha .xlsx com as NFs"),
    db: Session = Depends(get_db),
) -> ImportLoteResult:
    '''
    🎯 O QUE FAZ:
        Recebe um arquivo .xlsx, faz o parse, carrega o catálogo
        de produtos e dispara o pipeline de importação.

    📐 REGRA (#59):
        - Valida extensão .xlsx → HTTP 400.
        - Parse do Excel → HTTP 400 em caso de erro.
        - Catálogo de produtos carregado aqui (evita N+1).
        - importar_nfs() faz toda a lógica de negócio.
        - EmbarqueNaoEncontradoError → HTTP 404.
        - Falha genérica → HTTP 500.

    📥 PARÂMETROS:
        embarque_id (UUID): ID do embarque alvo.
        arquivo (UploadFile): planilha .xlsx.

    📤 ImportLoteResult: total_linhas, total_importadas,
        total_erros, duplicatas_ignoradas, erros[].
    '''
    # ── Valida extensão ────────────────────────
    if not arquivo.filename or not arquivo.filename.lower().endswith('.xlsx'):
        raise HTTPException(
            status_code=400,
            detail='Apenas arquivos .xlsx são aceitos.',
        )

    # ── Lê conteúdo do upload ──────────────────
    conteudo = await arquivo.read()

    # ── Parse da planilha ──────────────────────
    try:
        linhas = parse_planilha_nf(conteudo)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=f'Erro ao processar a planilha: {exc}',
        ) from exc

    # ── Carrega catálogo de produtos ───────────
    catalogo = carregar_catalogo_produtos(db)

    # ── Pipeline de importação ─────────────────
    try:
        _nfs, resultado = importar_nfs(db, linhas, embarque_id, catalogo)
    except EmbarqueNaoEncontradoError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f'Erro interno ao processar a importação: {exc}',
        ) from exc

    return resultado


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


# ─────────────────────────────────────────────────
# 📤 GET /embarques/{embarque_id}/exportar
# ─────────────────────────────────────────────────
@router.get(
    '/{embarque_id}/exportar',
    summary="Exportar embarque para Excel",
)
def exportar(
    embarque_id: UUID,
    db: Session = Depends(get_db),
):
    '''
    Gera planilha Excel (.xlsx) com as NFs do embarque.

    📎 Retorna arquivo para download com nome:
        embarque_{id}_{data}.xlsx

    📤 Retorna 404 se o embarque não for encontrado.
    '''
    try:
        bytes_xlsx, filename = exportar_embarque(db, embarque_id)
    except EmbarqueNaoEncontradoError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc

    return StreamingResponse(
        BytesIO(bytes_xlsx),
        media_type=(
            'application/vnd.openxmlformats-officedocument'
            '.spreadsheetml.sheet'
        ),
        headers={'Content-Disposition': f'attachment; filename="{filename}"'},
    )
