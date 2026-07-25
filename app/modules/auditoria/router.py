'''
app/modules/auditoria/router.py
================================

Router HTTP do módulo de Auditoria de CT-e.
--------------------------------------------

🎯 OBJETIVO:
    Expor endpoints REST para importação, vinculação, rateio e auditoria
    de CT-es (Conhecimentos de Transporte Eletrônico).

📐 PADRÃO RIGOROSO ROUTER (Decisão #59):
    - ZERO lógica de negócio
    - ZERO imports de models, repositories ou exceções do engine
    - Única exceção: captura de exceções do service → HTTPException
    - Validação de entrada via schemas Pydantic
    - Resposta HTTP padronizada

📋 ENDPOINTS:
    - POST   /ctes/upload             → Importa XML de CT-e
    - GET    /ctes                    → Lista CT-es (paginado)
    - GET    /ctes/{cte_id}           → Detalhe de um CT-e
    - POST   /ctes/{cte_id}/vincular  → Vincula CT-e a embarque
    - POST   /ctes/{cte_id}/ratear    → Rateia valor do CT-e entre NFs
    - POST   /ctes/{cte_id}/auditar   → Audita divergências (±5%)

📦 DEPENDÊNCIAS:
    - app/modules/auditoria/schemas.py (schemas Pydantic)
    - app/services/auditoria_cte_service.py (AuditoriaCteService)
    - app/exceptions/cte_exceptions.py (exceções de negócio)
    - app/core/deps.py (get_db)

📅 DATAS:
    - Criação: 25/07/2026
    - Autor: ADillTech — ApuraFrete
'''

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.deps import get_db
from app.exceptions.cte_exceptions import (
    CteCanceladoError,
    CteDuplicadoError,
    CteJaVinculadoError,
    CteNaoEncontradoError,
)
from app.modules.auditoria.schemas import (
    AuditoriaItemResponse,
    CTeAuditoriaResponse,
    CTeDetailResponse,
    CTeItemResponse,
    CTeListQuery,
    CTeListResponse,
    CTeRateioResponse,
    CTeResponse,
    CTeUploadResponse,
    CTeVincularRequest,
    CTeVincularResponse,
    RateioItemResponse,
)
from app.services.auditoria_cte_service import AuditoriaCteService


router = APIRouter(
    prefix="/ctes",
    tags=["Auditoria CT-e"],
)


# ============================================================
# ENDPOINT: UPLOAD DE XML DE CT-e
# ============================================================

@router.post(
    "/upload",
    response_model=CTeUploadResponse,
    status_code=201,
    summary="Importar XML de CT-e",
    description="Faz upload e parseia um arquivo XML de CT-e (padrão SEFAZ), "
                "persistindo o registro no sistema.",
)
async def upload_cte_xml(
    file: Annotated[UploadFile, File(description="Arquivo XML do CT-e")],
    db: Annotated[Session, Depends(get_db)],
    empresa_id: UUID,
):
    '''
    🎯 Endpoint de upload de XML de CT-e.

    📐 Validações:
        - Arquivo deve ser XML (content-type ou extensão)
        - XML deve seguir padrão SEFAZ (namespace CT-e)
        - Chave de acesso não pode já existir (CteDuplicadoError → 409)

    📐 Fluxo:
        1. Lê conteúdo do arquivo (bytes)
        2. Chama service.importar_cte()
        3. Retorna CTeUploadResponse com dados do CT-e importado
    '''
    # Validação básica do arquivo
    if not file.filename or not file.filename.lower().endswith(".xml"):
        raise HTTPException(
            status_code=400,
            detail="Arquivo deve ser um XML válido (extensão .xml)",
        )

    # Lê conteúdo do arquivo
    xml_content = await file.read()

    # Chama service
    service = AuditoriaCteService(db)
    try:
        cte_data = service.importar_cte(
            xml_content=xml_content,
            empresa_id=empresa_id,
            nome_arquivo=file.filename,
        )

        # Converte para schema de resposta
        cte_response = CTeResponse.model_validate(cte_data)

        return CTeUploadResponse(
            sucesso=True,
            cte=cte_response,
            mensagem="CT-e importado com sucesso.",
            erros=[],
        )

    except CteDuplicadoError as e:
        raise HTTPException(
            status_code=409,
            detail=f"CT-e já existe no sistema: {e}",
        )
    except Exception as e:
        # Erro genérico de parsing ou validação
        raise HTTPException(
            status_code=422,
            detail=f"Erro ao processar XML do CT-e: {str(e)}",
        )


# ============================================================
# ENDPOINT: LISTAGEM DE CT-es
# ============================================================

@router.get(
    "/",
    response_model=CTeListResponse,
    summary="Listar CT-es",
    description="Lista CT-es do tenant com paginação e filtros opcionais.",
)
def listar_ctes(
    db: Annotated[Session, Depends(get_db)],
    empresa_id: UUID,
    query: CTeListQuery = Depends(),
):
    '''
    🎯 Endpoint de listagem paginada de CT-es.

    📐 Filtros opcionais:
        - status (IMPORTADO, VINCULADO, RATEADO, AUDITADO, CANCELADO)
        - chave_acesso (exata ou parcial)
        - data_inicio / data_fim (range de emissão)

    📐 Paginação:
        - page (padrão: 1)
        - size (padrão: 20, máx: 100)
    '''
    service = AuditoriaCteService(db)

    # Busca paginada
    total, ctes = service.listar_ctes(
        empresa_id=empresa_id,
        page=query.page,
        size=query.size,
        status=query.status,
        chave_acesso=query.chave_acesso,
        data_inicio=query.data_inicio,
        data_fim=query.data_fim,
    )

    # Converte para schemas
    ctes_response = [CTeResponse.model_validate(cte) for cte in ctes]
    total_paginas = (total + query.size - 1) // query.size

    return CTeListResponse(
        total=total,
        page=query.page,
        size=query.size,
        total_paginas=total_paginas,
        itens=ctes_response,
    )


# ============================================================
# ENDPOINT: DETALHE DE UM CT-e
# ============================================================

@router.get(
    "/{cte_id}",
    response_model=CTeDetailResponse,
    summary="Detalhe de um CT-e",
    description="Retorna dados completos de um CT-e, incluindo itens de rateio.",
)
def obter_cte(
    cte_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    empresa_id: UUID,
):
    '''
    🎯 Endpoint de detalhe de um CT-e.

    📐 Retorna todos os campos do parser (Seção 12.1) + itens de rateio.

    📐 Erros:
        - CT-e não encontrado ou não pertence ao tenant → 404
    '''
    service = AuditoriaCteService(db)

    try:
        cte = service.buscar_cte_com_itens(cte_id=cte_id, empresa_id=empresa_id)

        # Converte itens
        itens_response = [
            CTeItemResponse.model_validate(item) for item in cte.itens
        ]

        # Converte CT-e
        cte_response = CTeDetailResponse.model_validate(cte)
        cte_response.itens = itens_response

        return cte_response

    except CteNaoEncontradoError as e:
        raise HTTPException(
            status_code=404,
            detail=f"CT-e não encontrado: {e}",
        )


# ============================================================
# ENDPOINT: VINCULAR CT-e → EMBARQUE
# ============================================================

@router.post(
    "/{cte_id}/vincular",
    response_model=CTeVincularResponse,
    summary="Vincular CT-e a embarque",
    description="Vincula um CT-e a um embarque, herdando suas NFs para rateio.",
)
def vincular_cte_a_embarque(
    cte_id: UUID,
    request: CTeVincularRequest,
    db: Annotated[Session, Depends(get_db)],
    empresa_id: UUID,
):
    '''
    🎯 Endpoint de vinculação CT-e → Embarque.

    📐 Regra de negócio (Seção 3.8):
        - CT-e não pode já estar vinculado (CteJaVinculadoError → 409)
        - CT-e não pode estar cancelado (CteCanceladoError → 422)

    📐 Fluxo:
        1. Service valida pré-condições
        2. Vincula CT-e ao embarque
        3. Retorna quantidade de NFs vinculadas
    '''
    service = AuditoriaCteService(db)

    try:
        resultado = service.vincular_ao_embarque(
            cte_id=cte_id,
            embarque_id=request.embarque_id,
            empresa_id=empresa_id,
        )

        return CTeVincularResponse(
            sucesso=True,
            cte_id=cte_id,
            embarque_id=request.embarque_id,
            qtd_nfs_vinculadas=resultado["qtd_nfs"],
            mensagem="CT-e vinculado ao embarque com sucesso.",
        )

    except CteNaoEncontradoError as e:
        raise HTTPException(
            status_code=404,
            detail=f"CT-e não encontrado: {e}",
        )
    except CteJaVinculadoError as e:
        raise HTTPException(
            status_code=409,
            detail=f"CT-e já está vinculado a um embarque: {e}",
        )
    except CteCanceladoError as e:
        raise HTTPException(
            status_code=422,
            detail=f"CT-e está cancelado e não pode ser vinculado: {e}",
        )


# ============================================================
# ENDPOINT: RATEAR VALOR DO CT-e
# ============================================================

@router.post(
    "/{cte_id}/ratear",
    response_model=CTeRateioResponse,
    summary="Ratear valor do CT-e",
    description="Rateia o valor total do CT-e entre as NFs vinculadas (igualitário).",
)
def ratear_cte(
    cte_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    empresa_id: UUID,
):
    '''
    🎯 Endpoint de rateio igualitário (Decisão #42).

    📐 Regra de negócio (Seção 3.6):
        - valor_rateado_por_nf = valor_total_cte / qtd_nfs_vinculadas
        - Arredondamento: 2 casas decimais
        - Resíduo de centavos → primeira NF (ordem por DOCUMENTO)
        - Σ de todas as parcelas = valor_total_cte

    📐 Pré-condições:
        - CT-e deve estar VINCULADO
        - CT-e não pode estar cancelado
    '''
    service = AuditoriaCteService(db)

    try:
        resultado = service.ratear_valor(cte_id=cte_id, empresa_id=empresa_id)

        # Converte itens
        itens_response = [
            RateioItemResponse(
                nf_id=item["nf_id"],
                nf_numero=item["nf_numero"],
                valor_rateado=item["valor_rateado"],
                ordem=item["ordem"],
                is_primeira=item["is_primeira"],
            )
            for item in resultado["itens"]
        ]

        return CTeRateioResponse(
            sucesso=True,
            cte_id=cte_id,
            valor_total_cte=resultado["valor_total_cte"],
            qtd_nfs=resultado["qtd_nfs"],
            valor_por_nf=resultado["valor_por_nf"],
            residuo=resultado["residuo"],
            itens=itens_response,
            mensagem=f"Rateio igualitário concluído. {resultado['qtd_nfs']} NFs rateadas.",
        )

    except CteNaoEncontradoError as e:
        raise HTTPException(
            status_code=404,
            detail=f"CT-e não encontrado: {e}",
        )
    except CteCanceladoError as e:
        raise HTTPException(
            status_code=422,
            detail=f"CT-e está cancelado e não pode ser rateado: {e}",
        )
    except ValueError as e:
        # CT-e não está vinculado ou não tem NFs
        raise HTTPException(
            status_code=422,
            detail=str(e),
        )


# ============================================================
# ENDPOINT: AUDITAR DIVERGÊNCIAS
# ============================================================

@router.post(
    "/{cte_id}/auditar",
    response_model=CTeAuditoriaResponse,
    summary="Auditar divergências",
    description="Compara valor rateado × valor calculado com tolerância ±5%.",
)
def auditar_cte(
    cte_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    empresa_id: UUID,
):
    '''
    🎯 Endpoint de auditoria de divergências (Seção 3.7).

    📐 Regra de negócio:
        - divergencia = valor_rateado − valor_calculado
        - percentual = (divergencia / valor_calculado) × 100
        - CONFORME:    |percentual| ≤ 5%
        - DIVERGENTE:  |percentual| > 5%
        - SEM_BASE:    valor_calculado é None

    📐 Pré-condições:
        - CT-e deve estar RATEADO
        - CT-e não pode estar cancelado
    '''
    service = AuditoriaCteService(db)

    try:
        resultado = service.auditar_divergencias(cte_id=cte_id, empresa_id=empresa_id)

        # Converte itens
        itens_response = [
            AuditoriaItemResponse(
                nf_id=item["nf_id"],
                nf_numero=item["nf_numero"],
                valor_calculado=item.get("valor_calculado"),
                valor_rateado=item.get("valor_rateado"),
                divergencia=item.get("divergencia"),
                percentual=item.get("percentual"),
                status=item["status"],
                observacao=item.get("observacao"),
            )
            for item in resultado["itens"]
        ]

        return CTeAuditoriaResponse(
            sucesso=True,
            cte_id=cte_id,
            chave_acesso=resultado["chave_acesso"],
            valor_total_cte=resultado["valor_total_cte"],
            qtd_nfs_auditedas=resultado["qtd_nfs"],
            qtd_conforme=resultado["qtd_conforme"],
            qtd_divergente=resultado["qtd_divergente"],
            qtd_sem_base=resultado["qtd_sem_base"],
            itens=itens_response,
            mensagem=(
                f"Auditoria concluída: "
                f"{resultado['qtd_conforme']} conforme, "
                f"{resultado['qtd_divergente']} divergente, "
                f"{resultado['qtd_sem_base']} sem base."
            ),
        )

    except CteNaoEncontradoError as e:
        raise HTTPException(
            status_code=404,
            detail=f"CT-e não encontrado: {e}",
        )
    except CteCanceladoError as e:
        raise HTTPException(
            status_code=422,
            detail=f"CT-e está cancelado e não pode ser auditado: {e}",
        )
    except ValueError as e:
        # CT-e não está rateado
        raise HTTPException(
            status_code=422,
            detail=str(e),
        )
