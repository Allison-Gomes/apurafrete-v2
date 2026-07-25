'''
app/modules/auditoria/schemas.py
=================================

Schemas Pydantic v2 para o módulo de Auditoria de CT-e.
--------------------------------------------------------

🎯 OBJETIVO:
    Definir contratos de entrada (request) e saída (response) para
    todos os endpoints de auditoria: upload de XML, listagem, detalhe,
    vinculação ao embarque, rateio igualitário e conciliação ±5%.

📐 REGRA:
    - Nenhuma lógica de negócio — apenas validação de formato e tipagem
    - Nenhum acesso a banco de dados
    - Campos monetários: Decimal com 2 casas
    - empresa_id em todos os schemas que representam entidade do tenant
    - from_attributes=True para conversão de models SQLAlchemy
    - Docstrings com 🎯 (objetivo) e 📐 (restrições)

📋 ENDPOINTS COBERTOS:
    - POST   /ctes/upload          → CTeUploadResponse
    - GET    /ctes                 → CTeListResponse  (+ CTeListQuery)
    - GET    /ctes/{cte_id}        → CTeDetailResponse
    - POST   /ctes/{cte_id}/vincular  → CTeVincularResponse
    - POST   /ctes/{cte_id}/ratear    → CTeRateioResponse
    - POST   /ctes/{cte_id}/auditar   → CTeAuditoriaResponse

📦 DEPENDÊNCIAS:
    - app/models/cte.py            (CTe)
    - app/models/item_cte.py       (ItemCte)
    - app/services/auditoria_cte_service.py  (AuditoriaCteService)

📅 DATAS:
    - Criação:  25/07/2026
    - Refatoração: 25/07/2026 (alinhamento ao Master v4.7)
    - Autor: ADillTech — ApuraFrete
'''

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


# ============================================================
# ENUMS
# ============================================================

class CTeStatus(str, Enum):
    '''
    🎯 Status do CT-e no fluxo de auditoria.

    📐 Fluxo normal:
        IMPORTADO → VINCULADO → RATEADO → AUDITADO

    📐 Estados terminais / erro:
        CANCELADO → CT-e de anulação (tpCTe ∈ {2, 4}) ou cancelado
        ERRO      → Falha no processamento

    📐 Regra de negócio (Seção 3.8):
        CT-e cancelado não pode ser vinculado, rateado ou auditado
        (CteCanceladoError → HTTP 422)
    '''
    IMPORTADO = "IMPORTADO"
    VINCULADO = "VINCULADO"
    RATEADO = "RATEADO"
    AUDITADO = "AUDITADO"
    CANCELADO = "CANCELADO"
    ERRO = "ERRO"


class AuditoriaStatus(str, Enum):
    '''
    🎯 Resultado da conciliação por NF vinculada ao CT-e.

    📐 Regra de negócio (Seção 3.7):
        - CONFORME:    |rateio − calculado| ≤ 5% × calculado
        - DIVERGENTE:  |rateio − calculado| > 5% × calculado
        - SEM_BASE:    NF rateada mas sem valor_calculado
        - SEM_VINCULO: CT-e sem NFs vinculadas (nível do CT-e)
    '''
    CONFORME = "CONFORME"
    DIVERGENTE = "DIVERGENTE"
    SEM_BASE = "SEM_BASE"
    SEM_VINCULO = "SEM_VINCULO"


# ============================================================
# SCHEMAS DE RESPOSTA — CT-e (LISTAGEM E DETALHE)
# ============================================================

class CTeResponse(BaseModel):
    '''
    🎯 Dados resumidos de um CT-e para listagem (GET /ctes).

    📐 Contém apenas campos essenciais para visualização em tabela.
        Detalhes completos → CTeDetailResponse.
    '''
    id: UUID = Field(..., description="Identificador único do CT-e (UUID v4)")
    empresa_id: UUID = Field(..., description="ID do tenant proprietário")
    chave_acesso: str = Field(
        ..., max_length=44,
        description="Chave de acesso SEFAZ (44 dígitos numéricos)"
    )
    numero: int = Field(..., description="Número do CT-e")
    serie: int = Field(..., description="Série do CT-e")
    data_emissao: datetime = Field(..., description="Data de emissão do CT-e")
    emitente_nome: str = Field(..., description="Nome da transportadora emitente")
    destinatario_nome: Optional[str] = Field(
        None, description="Nome do destinatário do CT-e"
    )
    valor_total: Decimal = Field(
        ..., max_digits=12, decimal_places=2,
        description="Valor total do frete do CT-e (R$)"
    )
    status: CTeStatus = Field(..., description="Status atual no fluxo de auditoria")
    embarque_id: Optional[UUID] = Field(
        None, description="ID do embarque vinculado (null se não vinculado)"
    )
    qtd_nfs_vinculadas: int = Field(
        0, ge=0, description="Quantidade de NFs vinculadas ao CT-e (via embarque)"
    )
    criado_em: datetime = Field(..., description="Timestamp de criação do registro")

    model_config = {
        "from_attributes": True,
        "json_schema_extra": {
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "empresa_id": "660e8400-e29b-41d4-a716-446655440001",
                "chave_acesso": "35251044687723000186570010000026811000061267",
                "numero": 2681,
                "serie": 1,
                "data_emissao": "2026-07-20T10:30:00",
                "emitente_nome": "TransExemplo Ltda",
                "destinatario_nome": "Destinatário S.A.",
                "valor_total": 1523.45,
                "status": "IMPORTADO",
                "embarque_id": None,
                "qtd_nfs_vinculadas": 0,
                "criado_em": "2026-07-25T14:00:00",
            }
        },
    }

    @field_validator("chave_acesso")
    @classmethod
    def validar_chave_acesso(cls, v: str) -> str:
        '''📐 Chave de acesso SEFAZ: exatamente 44 dígitos numéricos.'''
        if not v.isdigit() or len(v) != 44:
            raise ValueError("Chave de acesso deve conter exatamente 44 dígitos numéricos")
        return v

    @field_validator("valor_total")
    @classmethod
    def validar_valor_positivo(cls, v: Decimal) -> Decimal:
        '''📐 Valor total do CT-e não pode ser negativo.'''
        if v < 0:
            raise ValueError("Valor total do CT-e não pode ser negativo")
        return v


class CTeItemResponse(BaseModel):
    '''
    🎯 Item de rateio vinculado ao CT-e (NF participante).

    📐 Representa uma NF vinculada ao embarque que recebeu
        parcela do rateio do CT-e.
    '''
    id: UUID = Field(..., description="Identificador do ItemCte")
    nf_id: UUID = Field(..., description="ID da Nota Fiscal vinculada")
    nf_numero: str = Field(..., description="Número do documento da NF")
    valor_rateado: Optional[Decimal] = Field(
        None, max_digits=12, decimal_places=2,
        description="Parcela rateada do CT-e para esta NF (R$)"
    )
    ordem: int = Field(..., ge=1, description="Ordem da NF no rateio (1-based)")
    is_primeira: bool = Field(
        False, description="Indica se é a primeira NF (recebe resíduo de centavos)"
    )
    nf_valor_calculado: Optional[Decimal] = Field(
        None, max_digits=12, decimal_places=2,
        description="Valor do frete calculado para esta NF (R$)"
    )
    nf_status_calculo: Optional[str] = Field(
        None, description="Status do cálculo de frete da NF"
    )

    model_config = {"from_attributes": True}


class CTeDetailResponse(CTeResponse):
    '''
    🎯 Detalhe completo de um CT-e (GET /ctes/{cte_id}).

    📐 Estende CTeResponse com campos do parser (Seção 12.1)
        e lista de itens de rateio.
    '''
    tipo_cte: int = Field(..., ge=0, description="Tipo do CT-e (0=Normal, 2=Anulação, 4=Substituto)")
    emitente_cnpj: str = Field(..., max_length=14, description="CNPJ da transportadora emitente")
    remetente_nome: Optional[str] = Field(None, description="Nome do remetente da carga")
    remetente_cnpj: Optional[str] = Field(None, max_length=14, description="CNPJ do remetente da carga")
    destinatario_cnpj: Optional[str] = Field(None, max_length=14, description="CNPJ do destinatário")
    peso_total_kg: Optional[Decimal] = Field(
        None, max_digits=10, decimal_places=2,
        description="Peso total da carga no CT-e (kg)"
    )
    uf_inicio: Optional[str] = Field(None, max_length=2, description="UF de início do trajeto")
    uf_fim: Optional[str] = Field(None, max_length=2, description="UF de fim do trajeto")
    municipio_inicio: Optional[str] = Field(None, description="Município de início do trajeto")
    municipio_fim: Optional[str] = Field(None, description="Município de fim do trajeto")
    itens: List[CTeItemResponse] = Field(
        default_factory=list, description="Lista de NFs vinculadas com parcelas do rateio"
    )

    model_config = {
        "from_attributes": True,
        "json_schema_extra": {
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "empresa_id": "660e8400-e29b-41d4-a716-446655440001",
                "chave_acesso": "35251044687723000186570010000026811000061267",
                "numero": 2681,
                "serie": 1,
                "data_emissao": "2026-07-20T10:30:00",
                "emitente_nome": "TransExemplo Ltda",
                "emitente_cnpj": "44687723000186",
                "destinatario_nome": "Destinatário S.A.",
                "destinatario_cnpj": "12345678000199",
                "remetente_nome": "Remetente Ltda",
                "remetente_cnpj": "98765432000100",
                "valor_total": 1523.45,
                "tipo_cte": 0,
                "peso_total_kg": 850.50,
                "uf_inicio": "SP",
                "uf_fim": "RJ",
                "municipio_inicio": "Campinas",
                "municipio_fim": "Rio de Janeiro",
                "status": "IMPORTADO",
                "embarque_id": None,
                "qtd_nfs_vinculadas": 0,
                "criado_em": "2026-07-25T14:00:00",
                "itens": [],
            }
        },
    }


# ============================================================
# SCHEMAS — UPLOAD DE XML DE CT-e
# ============================================================

class CTeUploadResponse(BaseModel):
    '''
    🎯 Resposta do endpoint POST /ctes/upload.

    📐 Representa o resultado do parsing e persistência de
        um arquivo XML de CT-e (padrão SEFAZ).
    '''
    sucesso: bool = Field(..., description="True se o CT-e foi importado com sucesso")
    cte: Optional[CTeResponse] = Field(
        None, description="Dados do CT-e importado (null em caso de erro)"
    )
    mensagem: str = Field(
        "", description="Mensagem descritiva do resultado da operação"
    )
    erros: List[str] = Field(
        default_factory=list, description="Lista de erros de parsing/validação"
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "sucesso": True,
                "cte": {"id": "550e8400-...", "chave_acesso": "352510...", "status": "IMPORTADO"},
                "mensagem": "CT-e importado com sucesso.",
                "erros": [],
            }
        }
    }


# ============================================================
# SCHEMAS — VINCULAÇÃO CT-e → EMBARQUE
# ============================================================

class CTeVincularRequest(BaseModel):
    '''
    🎯 Request para vincular um CT-e a um embarque (POST /ctes/{cte_id}/vincular).

    📐 Regra de negócio (Seção 3.8):
        - CT-e é vinculado a um embarque, herdando suas NFs
        - CT-e não pode já estar vinculado (CteJaVinculadoError → HTTP 409)
        - CT-e não pode estar cancelado (CteCanceladoError → HTTP 422)
    '''
    embarque_id: UUID = Field(
        ..., description="ID do embarque ao qual o CT-e será vinculado"
    )

    model_config = {
        "json_schema_extra": {
            "example": {"embarque_id": "770e8400-e29b-41d4-a716-446655440002"}
        }
    }


class CTeVincularResponse(BaseModel):
    '''
    🎯 Resposta da vinculação CT-e → Embarque.

    📐 Confirma o vínculo criado e a quantidade de NFs
        que participarão do rateio.
    '''
    sucesso: bool = Field(..., description="True se a vinculação foi bem-sucedida")
    cte_id: UUID = Field(..., description="ID do CT-e vinculado")
    embarque_id: UUID = Field(..., description="ID do embarque vinculado")
    qtd_nfs_vinculadas: int = Field(
        ..., ge=0, description="Quantidade de NFs do embarque que participam do rateio"
    )
    mensagem: str = Field("", description="Mensagem descritiva")

    model_config = {
        "from_attributes": True,
        "json_schema_extra": {
            "example": {
                "sucesso": True,
                "cte_id": "550e8400-e29b-41d4-a716-446655440000",
                "embarque_id": "770e8400-e29b-41d4-a716-446655440002",
                "qtd_nfs_vinculadas": 3,
                "mensagem": "CT-e vinculado ao embarque com sucesso.",
            }
        },
    }


# ============================================================
# SCHEMAS — RATEIO IGUALITÁRIO
# ============================================================

class RateioItemResponse(BaseModel):
    '''
    🎯 Parcela do rateio para uma NF individual.

    📐 Regra de negócio (Seção 3.6 — Decisão #42):
        - valor_rateado_por_nf = valor_total_cte / qtd_nfs_vinculadas
        - Arredondamento: 2 casas decimais por parcela
        - Resíduo de centavos → primeira NF (is_primeira=True)
        - Σ de todas as parcelas = valor_total_cte
    '''
    nf_id: UUID = Field(..., description="ID da NF")
    nf_numero: str = Field(..., description="Número do documento da NF")
    valor_rateado: Decimal = Field(
        ..., max_digits=12, decimal_places=2,
        description="Parcela rateada para esta NF (R$)"
    )
    ordem: int = Field(..., ge=1, description="Ordem da NF no rateio (1-based, por DOCUMENTO)")
    is_primeira: bool = Field(
        False, description="True se esta é a primeira NF (recebe o resíduo de centavos)"
    )

    model_config = {"from_attributes": True}


class CTeRateioResponse(BaseModel):
    '''
    🎯 Resposta do rateio igualitário (POST /ctes/{cte_id}/ratear).

    📐 Contém o resumo do rateio e o detalhamento por NF.
    '''
    sucesso: bool = Field(..., description="True se o rateio foi executado com sucesso")
    cte_id: UUID = Field(..., description="ID do CT-e rateado")
    valor_total_cte: Decimal = Field(
        ..., max_digits=12, decimal_places=2,
        description="Valor total do CT-e que foi rateado (R$)"
    )
    qtd_nfs: int = Field(..., ge=0, description="Quantidade de NFs participantes do rateio")
    valor_por_nf: Decimal = Field(
        ..., max_digits=12, decimal_places=2,
        description="Valor base rateado por NF antes do resíduo (R$)"
    )
    residuo: Decimal = Field(
        ..., max_digits=12, decimal_places=2,
        description="Resíduo de centavos adicionado à primeira NF"
    )
    itens: List[RateioItemResponse] = Field(
        default_factory=list, description="Detalhamento do rateio por NF"
    )
    mensagem: str = Field("", description="Mensagem descritiva")

    model_config = {
        "json_schema_extra": {
            "example": {
                "sucesso": True,
                "cte_id": "550e8400-e29b-41d4-a716-446655440000",
                "valor_total_cte": 1523.45,
                "qtd_nfs": 3,
                "valor_por_nf": 507.81,
                "residuo": 0.02,
                "itens": [],
                "mensagem": "Rateio igualitário concluído. 3 NFs rateadas.",
            }
        }
    }


# ============================================================
# SCHEMAS — AUDITORIA / CONCILIAÇÃO ±5%
# ============================================================

class AuditoriaItemResponse(BaseModel):
    '''
    🎯 Resultado da conciliação para uma NF individual.

    📐 Regra de negócio (Seção 3.7):
        - divergencia = valor_rateado − valor_calculado (R$)
        - percentual   = (divergencia / valor_calculado) × 100 (%)
        - CONFORME:    |percentual| ≤ 5%
        - DIVERGENTE:  |percentual| > 5%
        - SEM_BASE:    valor_calculado é None
    '''
    nf_id: UUID = Field(..., description="ID da NF auditada")
    nf_numero: str = Field(..., description="Número do documento da NF")
    valor_calculado: Optional[Decimal] = Field(
        None, max_digits=12, decimal_places=2,
        description="Valor do frete calculado pelo sistema (R$)"
    )
    valor_rateado: Optional[Decimal] = Field(
        None, max_digits=12, decimal_places=2,
        description="Valor rateado do CT-e para esta NF (R$)"
    )
    divergencia: Optional[Decimal] = Field(
        None, max_digits=12, decimal_places=2,
        description="Diferença absoluta: rateado − calculado (R$)"
    )
    percentual: Optional[Decimal] = Field(
        None, max_digits=8, decimal_places=2,
        description="Percentual de divergência: (divergencia / calculado) × 100"
    )
    status: AuditoriaStatus = Field(
        ..., description="Status da conciliação desta NF"
    )
    observacao: Optional[str] = Field(
        None, description="Observação complementar (ex.: motivo de SEM_BASE)"
    )

    model_config = {"from_attributes": True}


class CTeAuditoriaResponse(BaseModel):
    '''
    🎯 Resposta completa da auditoria (POST /ctes/{cte_id}/auditar).

    📐 Contém o resumo da conciliação e o resultado individual por NF.
    '''
    sucesso: bool = Field(..., description="True se a auditoria foi executada com sucesso")
    cte_id: UUID = Field(..., description="ID do CT-e auditado")
    chave_acesso: str = Field(..., description="Chave de acesso SEFAZ do CT-e")
    valor_total_cte: Decimal = Field(
        ..., max_digits=12, decimal_places=2,
        description="Valor total do CT-e (R$)"
    )
    qtd_nfs_auditedas: int = Field(..., ge=0, description="Total de NFs conciliadas")
    qtd_conforme: int = Field(0, ge=0, description="NFs dentro da tolerância (±5%)")
    qtd_divergente: int = Field(0, ge=0, description="NFs com divergência acima de ±5%")
    qtd_sem_base: int = Field(0, ge=0, description="NFs sem valor calculado (SEM_BASE)")
    itens: List[AuditoriaItemResponse] = Field(
        default_factory=list, description="Resultado individual por NF"
    )
    mensagem: str = Field("", description="Resumo textual da auditoria")

    model_config = {
        "json_schema_extra": {
            "example": {
                "sucesso": True,
                "cte_id": "550e8400-e29b-41d4-a716-446655440000",
                "chave_acesso": "35251044687723000186570010000026811000061267",
                "valor_total_cte": 1523.45,
                "qtd_nfs_auditedas": 3,
                "qtd_conforme": 2,
                "qtd_divergente": 1,
                "qtd_sem_base": 0,
                "itens": [],
                "mensagem": "Auditoria concluída: 2 conforme, 1 divergente, 0 sem base.",
            }
        }
    }


# ============================================================
# SCHEMAS — LISTAGEM PAGINADA
# ============================================================

class CTeListQuery(BaseModel):
    '''
    🎯 Parâmetros de consulta para GET /ctes.

    📐 Query params opcionais para filtrar e paginar a listagem.
        Validação mínima: page ≥ 1, size entre 1 e 100.
    '''
    page: int = Field(1, ge=1, description="Número da página (inicia em 1)")
    size: int = Field(20, ge=1, le=100, description="Quantidade de itens por página (máx. 100)")
    status: Optional[CTeStatus] = Field(None, description="Filtrar por status do CT-e")
    chave_acesso: Optional[str] = Field(
        None, description="Buscar por chave de acesso (exata ou parcial, até 44 dígitos)"
    )
    data_inicio: Optional[datetime] = Field(
        None, description="Filtrar CT-es emitidos a partir desta data"
    )
    data_fim: Optional[datetime] = Field(
        None, description="Filtrar CT-es emitidos até esta data"
    )


class CTeListResponse(BaseModel):
    '''
    🎯 Resposta paginada da listagem de CT-es.

    📐 Formato padrão de paginação do projeto.
    '''
    total: int = Field(..., ge=0, description="Total de registros encontrados")
    page: int = Field(..., ge=1, description="Página atual")
    size: int = Field(..., ge=1, description="Itens por página")
    total_paginas: int = Field(..., ge=0, description="Total de páginas disponíveis")
    itens: List[CTeResponse] = Field(
        default_factory=list, description="Lista de CT-es da página atual"
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "total": 42,
                "page": 1,
                "size": 20,
                "total_paginas": 3,
                "itens": [],
            }
        }
    }


# ============================================================
# SCHEMA DE ERRO PADRÃO
# ============================================================

class ErrorResponse(BaseModel):
    '''
    🎯 Schema padrão de resposta de erro da API.

    📐 Usado em respostas HTTP 4xx e 5xx.
        - detail: mensagem amigável
        - codigo: código interno para debug (ex.: CTE_NAO_ENCONTRADO)
        - campos: campos específicos relacionados ao erro (opcional)
    '''
    detail: str = Field(..., description="Mensagem descritiva do erro")
    codigo: Optional[str] = Field(
        None, description="Código interno do erro (ex.: CTE_DUPLICADO)"
    )
    campos: Optional[List[str]] = Field(
        None, description="Campos relacionados ao erro (quando aplicável)"
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "detail": "CT-e não encontrado para a empresa informada.",
                "codigo": "CTE_NAO_ENCONTRADO",
                "campos": None,
            }
        }
    }
