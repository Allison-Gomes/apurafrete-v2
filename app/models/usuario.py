'''
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📁 ARQUIVO : usuario.py
📦 MÓDULO  : Core / Autenticação e Acesso
🎯 OBJETIVO: Define o model Usuario, que representa
             os usuários do sistema ApuraFrete.
🔗 DEPENDE  : app/models/base.py
             app/models/empresa.py
📅 CRIADO   : 24/06/2026
📅 ATUALIZADO: 11/07/2026 — refatoração de docstrings
               e padronização de comentários.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
'''

import enum

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.models.base import AuditMixin, Base


class PerfilAcesso(str, enum.Enum):
    '''
    🎯 O QUE FAZ:
        Enumera os perfis de acesso (roles) disponíveis
        no ApuraFrete, seguindo o modelo RBAC.

    📐 REGRA DE NEGÓCIO:
        - ADMIN    : Acesso total à empresa.
        - OPERADOR : Cria e gerencia embarques e NFs.
        - AUDITOR  : Somente leitura da auditoria CT-e.
        - VIEWER   : Visualização geral, sem escrita.

    ⚠️  ATENÇÃO:
        Novos perfis somente com autorização de Allison.
    '''
    ADMIN = "admin"
    OPERADOR = "operador"
    AUDITOR = "auditor"
    VIEWER = "viewer"


class Usuario(Base, AuditMixin):
    '''
    🎯 O QUE FAZ:
        Representa um usuário autenticado no sistema,
        vinculado a uma Empresa e com um perfil RBAC.

    📐 REGRA DE NEGÓCIO:
        - Todo usuário pertence a exatamente uma
          Empresa.
        - E-mail único por Empresa (não globalmente).
        - Senha nunca em texto puro — sempre hash
          bcrypt.
        - Usuário inativo (ativo=False) não autentica.
        - primeiro_acesso=True força redefinição de
          senha.

    🗂️  TABELA: usuarios

    ⚠️  ATENÇÃO:
        Não modificar sem autorização de Allison.
    '''

    __tablename__ = "usuarios"

    # ─────────────────────────────────────────────
    # 🔗 Vínculo com Empresa (multi-tenant)
    # ─────────────────────────────────────────────
    empresa_id = Column(
        UUID(as_uuid=True),
        ForeignKey("empresas.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Empresa à qual este usuário pertence",
    )

    # ─────────────────────────────────────────────
    # 👤 Dados do Usuário
    # ─────────────────────────────────────────────
    nome = Column(
        String(150),
        nullable=False,
        comment="Nome completo do usuário",
    )

    email = Column(
        String(255),
        nullable=False,
        index=True,
        comment="E-mail do usuário — único por empresa",
    )

    # ─────────────────────────────────────────────
    # 🔐 Segurança
    # ─────────────────────────────────────────────
    senha_hash = Column(
        String(255),
        nullable=False,
        comment="Hash bcrypt da senha. Nunca texto puro.",
    )

    perfil = Column(
        Enum(PerfilAcesso),
        nullable=False,
        default=PerfilAcesso.OPERADOR,
        comment="Perfil de acesso: admin | operador | auditor | viewer",
    )

    primeiro_acesso = Column(
        Boolean,
        default=True,
        nullable=False,
        comment="True = usuário deve redefinir senha no "
                "próximo login",
    )

    # ─────────────────────────────────────────────
    # 🕒 Controle de Acesso
    # ─────────────────────────────────────────────
    ultimo_login = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="Data e hora do último login bem-sucedido",
    )

    # ─────────────────────────────────────────────
    # 🔗 Relacionamentos
    # ─────────────────────────────────────────────
    empresa = relationship(
        "Empresa",
        back_populates="usuarios",
        lazy="select",
    )

    embarques_criados = relationship(
        "Embarque",
        back_populates="criado_por",
        lazy="select",
    )

    # ─────────────────────────────────────────────
    # ✅ Constraints
    # ─────────────────────────────────────────────
    __table_args__ = (
        UniqueConstraint(
            "empresa_id",
            "email",
            name="uq_usuario_empresa_email",
        ),
    )

    def __repr__(self):
        return f"<Usuario [{self.perfil}] {self.email}>"
