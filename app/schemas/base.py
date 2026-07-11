'''
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📁 ARQUIVO : base.py
📦 MÓDULO  : Schemas / Base
🎯 OBJETIVO: Schemas Pydantic (v2) compartilhados —
             mixins de timestamp, paginação e respostas
             padrão, herdados por todos os schemas do
             sistema.
📐 PADRÃO  : from_attributes=True (antigo orm_mode)
             UUID como UUID, Decimal como Decimal,
             datetime como datetime — nada de string.
🔗 DEPENDE  : Nenhuma (módulo raiz dos schemas)
📅 CRIADO   : 11/07/2026
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
'''

from __future__ import annotations

from datetime import datetime
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field, field_validator

# ─────────────────────────────────────────────────
# 🧬 TYPEVAR GENÉRICO
# ─────────────────────────────────────────────────
T = TypeVar('T')


# ─────────────────────────────────────────────────
# ⏱️ SCHEMA: TimestampsMixin
# Mixin de timestamps — herdar em todo *Response.
# ─────────────────────────────────────────────────
class TimestampsMixin(BaseModel):
    '''
    🎯 O QUE FAZ:
        Adiciona os campos de auditoria temporal
        a qualquer schema de resposta.

    📐 REGRA DE NEGÓCIO:
        - Herdado por todos os *Response.
        - from_attributes=True garante leitura direta
          do ORM (criado_em / atualizado_em).
        - NÃO usar em *Create e *Update — esses campos
          são gerados automaticamente pelo banco.
    '''
    model_config = ConfigDict(from_attributes=True)

    criado_em: datetime
    atualizado_em: datetime


# ─────────────────────────────────────────────────
# 📄 SCHEMA: PaginacaoQuery
# Parâmetros de paginação vindos da query string.
# ─────────────────────────────────────────────────
class PaginacaoQuery(BaseModel):
    '''
    🎯 O QUE FAZ:
        Recebe e valida os parâmetros de paginação
        enviados pelo frontend via query string.

    📐 REGRA DE NEGÓCIO:
        - page começa em 1 (não 0), mínimo 1, default 1.
        - page_size entre 1 e 100, default 20.
        - order_by: nome do campo para ordenar
          (default "criado_em").
        - order_dir: "asc" ou "desc" (default "desc").
          Validado por field_validator que força
          lowercase e rejeita valores inválidos.
    '''
    model_config = ConfigDict(str_strip_whitespace=True)

    page: int = Field(default=1, ge=1, description='Número da página (base 1)')
    page_size: int = Field(default=20, ge=1, le=100, description='Itens por página')
    order_by: str = Field(default='criado_em', min_length=1, description='Campo de ordenação')
    order_dir: str = Field(default='desc', description='Direção: asc ou desc')

    @field_validator('order_dir')
    @classmethod
    def normalizar_order_dir(cls, v: str) -> str:
        v = v.strip().lower()
        if v not in ('asc', 'desc'):
            raise ValueError('order_dir deve ser "asc" ou "desc"')
        return v


# ─────────────────────────────────────────────────
# 📊 SCHEMA: PaginacaoResponse[T]
# Envelope genérico de resposta paginada.
# ─────────────────────────────────────────────────
class PaginacaoResponse(BaseModel, Generic[T]):
    '''
    🎯 O QUE FAZ:
        Envelope padrão para toda resposta paginada
        da API. Carrega a lista de itens e metadados
        de navegação.

    📐 REGRA DE NEGÓCIO:
        - items: lista tipada (genérico T).
        - total: contagem total de registros
          (sem paginação).
        - page / page_size: eco da requisição.
        - total_pages: teto(total / page_size),
          calculado.
        - O frontend usa total_pages para renderizar
          os controles de navegação.
    '''
    items: list[T] = Field(default_factory=list)
    total: int = Field(..., ge=0)
    page: int = Field(..., ge=1)
    page_size: int = Field(..., ge=1)
    total_pages: int = Field(..., ge=0)


# ─────────────────────────────────────────────────
# 📬 SCHEMA: RespostaPadrao
# Resposta genérica para endpoints sem payload.
# ─────────────────────────────────────────────────
class RespostaPadrao(BaseModel):
    '''
    🎯 O QUE FAZ:
        Mensagem padronizada de sucesso/erro para
        endpoints que não retornam entidade (ex.: delete,
        ações em lote, atualizações de status).

    📐 REGRA DE NEGÓCIO:
        - sucesso: bool para o frontend decidir
          entre toast verde ou vermelho.
        - mensagem: texto amigável para exibição.
        - detalhes: payload opcional (ex.: id criado,
          contagem de linhas afetadas).
    '''
    sucesso: bool = True
    mensagem: str
    detalhes: dict | None = None
