'''
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📁 ARQUIVO : base.py
📦 MÓDULO  : Core / Base
🎯 OBJETIVO: Define a classe Base do SQLAlchemy e o
             Mixin de auditoria com campos padrão
             (id, criado_em, atualizado_em, ativo)
             que serão herdados por TODOS os models
             do sistema ApuraFrete.
🔗 DEPENDE  : sqlalchemy
📅 CRIADO  : 24/06/2026
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
'''

import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.sql import func


# ─────────────────────────────────────────────────
# 🏗️  CLASSE BASE — SQLAlchemy DeclarativeBase
# Todos os models herdam desta classe.
# O Alembic usa ela para detectar as tabelas.
# ─────────────────────────────────────────────────
class Base(DeclarativeBase):
    '''
    🎯 O QUE FAZ:
        Classe raiz do SQLAlchemy ORM.
        Todos os models do ApuraFrete herdam desta Base.

    📐 REGRA DE NEGÓCIO:
        - Deve ser importada em TODOS os models
        - O Alembic usa esta Base para gerar migrations
        - Não adicionar lógica de negócio aqui

    ⚠️  ATENÇÃO:
        Não modificar sem autorização de Allison.
    '''
    pass


# ─────────────────────────────────────────────────
# 🧩 MIXIN DE AUDITORIA — AuditMixin
# Adiciona campos padrão de rastreabilidade em
# qualquer model que o herde junto com Base.
# ─────────────────────────────────────────────────
class AuditMixin:
    '''
    🎯 O QUE FAZ:
        Mixin reutilizável que injeta automaticamente
        os campos de auditoria em todos os models
        que o herdarem.

    📐 CAMPOS INCLUÍDOS:
        id          → UUID gerado automaticamente (PK)
        criado_em   → Timestamp de criação (automático)
        atualizado_em → Timestamp da última atualização
        ativo       → Soft delete (True = ativo)

    📐 REGRA DE NEGÓCIO:
        - `id` nunca é informado manualmente
        - `criado_em` é preenchido 1x na inserção
        - `atualizado_em` é atualizado a cada UPDATE
        - `ativo = False` equivale a registro excluído
          (nunca deletar fisicamente registros)

    ⚠️  ATENÇÃO:
        Não modificar sem autorização de Allison.
    '''

    # ── Chave primária universal (UUID v4) ──────
    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
        comment="Identificador único universal (UUID v4)"
    )

    # ── Timestamp de criação ────────────────────
    criado_em = Column(
        DateTime(timezone=True),
        server_default=func.now(),  # gerado pelo banco
        nullable=False,
        comment="Data e hora de criação do registro"
    )

    # ── Timestamp de atualização ────────────────
    atualizado_em = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),        # atualizado automaticamente
        nullable=False,
        comment="Data e hora da última atualização"
    )

    # ── Soft delete ─────────────────────────────
    ativo = Column(
        Boolean,
        default=True,
        nullable=False,
        comment="False = registro inativo (soft delete)"
    )

'''
Explicação detalhada
Por que DeclarativeBase e não declarative_base()?
O DeclarativeBase é a forma moderna do SQLAlchemy 2.0+. Mais tipado, mais seguro e compatível com as versões atuais.

Por que UUID como PK?
Em um sistema multi-tenant (várias empresas), UUIDs evitam colisão de IDs entre tenants e são mais seguros que inteiros sequenciais.

Por que AuditMixin separado?
Porque nem toda tabela auxiliar futura precisará de todos esses campos. Separando, você tem flexibilidade para herdar só o que precisar.

Como os outros models vão usar?
'''