'''
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📁 ARQUIVO : log_auditoria.py
📦 MÓDULO  : Auditoria / Rastreabilidade
🎯 OBJETIVO: Define o model AuditoriaLog, que registra
             toda ação relevante realizada no sistema,
             garantindo trilha de auditoria completa e
             imutável para fins operacionais, contábeis
             e de compliance.
🔗 DEPENDE  : app/models/base.py, empresa.py, usuario.py
📅 CRIADO  : 24/06/2026
📅 ATUALIZADO: 04/07/2026 — padronização de docstrings
📅 ATUALIZADO: 11/07/2026 — removido CLIENTE do enum
               EntidadeLog (model Cliente fora do MVP)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
'''

import enum

from sqlalchemy import Column, String, ForeignKey, Enum, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship

from app.models.base import Base, AuditMixin


class AcaoLog(str, enum.Enum):
    '''
    📐 REGRA DE NEGÓCIO:
        CRIAR, ATUALIZAR, DELETAR, IMPORTAR, EXPORTAR,
        CALCULAR, AUDITAR, VINCULAR, CANCELAR, LOGIN,
        LOGOUT, ERRO.

    ⚠️  ATENÇÃO: Não alterar sem autorização de Allison.
    '''
    CRIAR     = "criar"
    ATUALIZAR = "atualizar"
    DELETAR   = "deletar"
    IMPORTAR  = "importar"
    EXPORTAR  = "exportar"
    CALCULAR  = "calcular"
    AUDITAR   = "auditar"
    VINCULAR  = "vincular"
    CANCELAR  = "cancelar"
    LOGIN     = "login"
    LOGOUT    = "logout"
    ERRO      = "erro"


class EntidadeLog(str, enum.Enum):
    '''
    📐 REGRA DE NEGÓCIO:
        Identifica qual entidade/tabela foi afetada.
        CLIENTE removido (v2.3) — fora do escopo do MVP.

    ⚠️  ATENÇÃO: Não alterar sem autorização de Allison.
    '''
    EMPRESA        = "empresa"
    USUARIO        = "usuario"
    TRANSPORTADORA = "transportadora"
    TABELA_FRETE   = "tabela_frete"
    FAIXA_PESO     = "faixa_peso"
    EMBARQUE       = "embarque"
    NOTA_FISCAL    = "nota_fiscal"
    CTE            = "cte"
    ITEM_CTE       = "item_cte"
    SISTEMA        = "sistema"


class AuditoriaLog(Base, AuditMixin):
    '''
    🎯 O QUE FAZ:
        Registra toda ação relevante realizada no
        ApuraFrete, formando uma trilha de auditoria
        completa e imutável.

    📐 REGRA DE NEGÓCIO:
        - Registros são IMUTÁVEIS (append-only).
        - dados_anteriores = estado ANTES da alteração.
        - dados_novos = estado APÓS a alteração.
        - CRIAR: dados_anteriores = NULL.
        - DELETAR: dados_novos = NULL.
        - LOGIN/LOGOUT/ERRO de sistema: entidade_id = NULL.
        - detalhes: contexto livre em JSON.
        - Multi-tenant via empresa_id.
        - atualizado_em e ativo (do AuditMixin) sem uso
          funcional aqui, mantidos por padronização.

    🗂️  TABELA: auditoria_logs

    ⚠️  ATENÇÃO:
        Tabela APPEND-ONLY. Nunca UPDATE ou DELETE.
        Não modificar sem autorização de Allison.
    '''

    __tablename__ = "auditoria_logs"

    empresa_id = Column(
        UUID(as_uuid=True), ForeignKey("empresas.id", ondelete="CASCADE"),
        nullable=False, index=True,
        comment="Empresa (tenant) à qual este log pertence"
    )
    usuario_id = Column(
        UUID(as_uuid=True), ForeignKey("usuarios.id", ondelete="SET NULL"),
        nullable=True, index=True,
        comment="Usuário que realizou a ação. NULL = ação automática."
    )
    usuario_email = Column(
        String(255), nullable=True,
        comment="Snapshot do e-mail do usuário no momento da ação"
    )
    acao = Column(
        Enum(AcaoLog), nullable=False, index=True,
        comment="Tipo de ação realizada"
    )
    entidade = Column(
        Enum(EntidadeLog), nullable=False, index=True,
        comment="Entidade afetada pela ação"
    )
    entidade_id = Column(
        UUID(as_uuid=True), nullable=True, index=True,
        comment="ID do registro afetado. NULL para ações sem entidade."
    )
    entidade_descricao = Column(
        String(255), nullable=True,
        comment="Descrição legível da entidade afetada"
    )
    dados_anteriores = Column(JSONB, nullable=True, comment="Estado do registro ANTES da alteração")
    dados_novos = Column(JSONB, nullable=True, comment="Estado do registro APÓS a alteração")
    detalhes = Column(JSONB, nullable=True, comment="Contexto adicional livre em JSON")
    ip_origem = Column(String(45), nullable=True, comment="IP de origem da requisição")
    user_agent = Column(String(512), nullable=True, comment="User-Agent do cliente HTTP")

    # ── Relacionamentos ──────────────────────────
    empresa = relationship("Empresa", lazy="select")
    usuario = relationship("Usuario", lazy="select")

    __table_args__ = (
        Index("ix_auditoria_logs_empresa_acao", "empresa_id", "acao"),
        Index("ix_auditoria_logs_empresa_entidade", "empresa_id", "entidade", "entidade_id"),
        Index("ix_auditoria_logs_empresa_usuario", "empresa_id", "usuario_id"),
        Index("ix_auditoria_logs_criado_em", "criado_em"),
    )

    def __repr__(self):
        return (
            f"<AuditoriaLog {self.acao} | {self.entidade} | "
            f"{self.usuario_email or 'sistema'} | {self.criado_em}>"
        )
