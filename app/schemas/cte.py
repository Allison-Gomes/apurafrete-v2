'''
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📁 ARQUIVO : cte.py
📦 MÓDULO  : Schemas — Auditoria CT-e
🎯 OBJETIVO: Schemas Pydantic para importação,
             rateio e conciliação de CT-e.
📅 CRIADO  : 18/07/2026
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
'''

from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


# ─────────────────────────────────────────────────
# 📤 Response — Item de Rateio (NF individual)
# ─────────────────────────────────────────────────

class ItemCteAuditoriaOut(BaseModel):
    '''
    🎯 O QUE FAZ:
        Representa o rateio de uma NF vinculada ao CT-e
        e o resultado da conciliação (calculado vs cobrado).

    📐 REGRA DE NEGÓCIO (MVP v2.5 — Seção 8.4):
        - OK: divergência ≤ ±5%
        - DIVERGENTE: divergência > ±5%
        - SEM_BASE: NF vinculada mas sem valor_calculado
        - SEM_VINCULO: NF não vinculada ao CT-e
    '''
    id: UUID
    nota_fiscal_id: UUID
    numero_nf: str
    valor_rateado: Decimal = Field(
        ...,
        description='Parcela do CT-e atribuída a esta NF em R$',
    )
    valor_calculado: Optional[Decimal] = Field(
        None,
        description='Frete calculado pelo sistema (snapshot) em R$',
    )
    divergencia: Optional[Decimal] = Field(
        None,
        description='valor_rateado − valor_calculado. Positivo = cobrado a mais.',
    )
    divergencia_percentual: Optional[Decimal] = Field(
        None,
        description='(divergencia / valor_calculado) × 100',
    )
    status_conciliacao: str = Field(
        ...,
        description='OK | DIVERGENTE | SEM_BASE | SEM_VINCULO',
    )

    model_config = {'from_attributes': True}


# ─────────────────────────────────────────────────
# 📤 Response — CT-e importado
# ─────────────────────────────────────────────────

class CteOut(BaseModel):
    '''
    🎯 O QUE FAZ:
        Representa os dados de um CT-e após importação,
        com todos os campos fiscais e de auditoria.
    '''
    id: UUID
    chave_cte: Optional[str] = None
    numero_cte: str
    serie_cte: Optional[str] = None
    data_emissao: date
    valor_total_cte: Decimal
    valor_frete_cte: Optional[Decimal] = None
    valor_pedagio: Optional[Decimal] = None
    valor_outros: Optional[Decimal] = None
    total_rateado: Decimal
    status: str
    origem: str
    transportadora_id: UUID
    embarque_id: Optional[UUID] = None
    criado_em: datetime

    model_config = {'from_attributes': True}


# ─────────────────────────────────────────────────
# 📤 Response — Resultado completo (importação + auditoria)
# ─────────────────────────────────────────────────

class CteImportResponse(BaseModel):
    '''
    🎯 O QUE FAZ:
        Relatório final da importação de CT-e com auditoria.
        Agrega o CT-e, itens rateados e resumo da conciliação.

    📐 REGRA DE NEGÓCIO (MVP v2.5 — Seção 8):
        - nfs_ok: NFs dentro da tolerância de ±5%
        - nfs_divergentes: NFs fora da tolerância
        - nfs_sem_base: NFs vinculadas mas sem valor_calculado
    '''
    cte: CteOut
    status_auditoria: str = Field(
        ...,
        description='OK | DIVERGENTE | SEM_VINCULO',
    )
    nfs_vinculadas: int = Field(
        ...,
        description='Total de NFs vinculadas ao CT-e',
    )
    nfs_ok: int = Field(0, description='NFs dentro da tolerância de 5%')
    nfs_divergentes: int = Field(0, description='NFs fora da tolerância de 5%')
    nfs_sem_base: int = Field(0, description='NFs vinculadas sem valor_calculado')
    itens: list[ItemCteAuditoriaOut] = Field(default_factory=list)

    model_config = {'from_attributes': True}


# ─────────────────────────────────────────────────
# 📤 Response — Erro de importação
# ─────────────────────────────────────────────────

class CteImportError(BaseModel):
    '''
    🎯 O QUE FAZ:
        Representa um erro durante a importação de CT-e.
    '''
    erro: str
    detalhe: Optional[str] = None
    chave_cte: Optional[str] = None
