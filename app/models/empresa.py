'''
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📁 ARQUIVO : empresa.py
📦 MÓDULO  : Core / Multi-Tenant
🎯 OBJETIVO: Define o model Empresa, que representa
             tanto o tenant (quem usa o SaaS) quanto
             os terceiros (CLIENTE REMETENTE /
             DESTINO que aparecem nas NFs). Toda
             entidade do sistema possui um empresa_id
             vinculado a este model, garantindo
             isolamento total de dados.
🔗 DEPENDE  : app/models/base.py
📅 CRIADO  : 24/06/2026
📅 ATUALIZADO: 11/07/2026 — unificado com terceiros
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
'''

from sqlalchemy import Column, String, Boolean, Index
from sqlalchemy.orm import relationship

from app.models.base import Base, AuditMixin


class Empresa(Base, AuditMixin):
    '''
    🎯 O QUE FAZ:
        Representa tanto o tenant (quem contrata o SaaS)
        quanto os terceiros (CLIENTE REMETENTE / DESTINO
        que aparecem nas NFs e CT-es).

    📐 REGRA DE NEGÓCIO:
        - tipo="tenant"   → empresa cliente do SaaS
                            (tem plano, trial, slug)
        - tipo="terceiro" → pessoa jurídica que aparece
                            na NF como remetente/destino
                            (tem codigo_terceiro, tipo_pessoa)
        - CNPJ é único no sistema (garante sem duplicidade
          entre tenants e terceiros).
        - Terceiros são compartilhados entre todos os
          tenants (cadastro único global).

    🗂️  TABELA: empresas

    ⚠️  ATENÇÃO:
        Não modificar sem autorização de Allison.
    '''

    __tablename__ = "empresas"

    # ── Campos comuns ─────────────────────────────
    razao_social = Column(
        String(200), nullable=False,
        comment="Razão social (tenant ou terceiro)"
    )
    nome_fantasia = Column(
        String(200), nullable=True,
        comment="Nome fantasia"
    )
    cnpj = Column(
        String(18), nullable=False, unique=True, index=True,
        comment="CNPJ formatado: 00.000.000/0000-00 (único global)"
    )
    email_contato = Column(
        String(255), nullable=True,
        comment="E-mail principal de contato"
    )
    telefone = Column(
        String(20), nullable=True,
        comment="Telefone de contato"
    )

    # ── Campos exclusivos de TENANT ───────────────
    tipo = Column(
        String(20), nullable=False, default="tenant",
        index=True,
        comment="tenant | terceiro"
    )
    slug = Column(
        String(100), nullable=True, unique=True, index=True,
        comment="Identificador URL do tenant. Ex: acme-logistica (NULL para terceiros)"
    )
    plano = Column(
        String(50), nullable=True, default="basico",
        comment="Plano do tenant: basico | profissional | enterprise (NULL para terceiros)"
    )
    trial = Column(
        Boolean, nullable=True, default=False,
        comment="True = tenant em período de trial (NULL para terceiros)"
    )

    # ── Campos exclusivos de TERCEIRO ─────────────
    codigo_terceiro = Column(
        String(50), nullable=True, index=True,
        comment="COD CLIENTE da planilha (ex: 000123)"
    )
    tipo_pessoa = Column(
        String(20), nullable=True,
        comment="remetente | destinatario | ambos (apenas para terceiros)"
    )

    # ── Relacionamentos (ATIVOS) ──────────────────
    usuarios = relationship(
        "Usuario", back_populates="empresa", lazy="select",
    )
    transportadoras = relationship(
        "Transportadora", back_populates="empresa", lazy="select",
    )
    embarques = relationship(
        "Embarque", back_populates="empresa", lazy="select",
    )

    def __repr__(self):
        prefix = "🏢" if self.tipo == "tenant" else "👤"
        return f"{prefix} Empresa [{self.cnpj}] {self.razao_social}"


# ── Índice composto para buscas frequentes ────────
Index(
    "ix_empresas_tipo_codigo_terceiro",
    Empresa.tipo,
    Empresa.codigo_terceiro,
    unique=False,
)
