'''
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📁 ARQUIVO : embarque.py
📦 MÓDULO  : Embarque
🎯 OBJETIVO: Define o model Embarque — lote de NFs
             agrupadas para despacho com uma transportadora.
             Unidade central de cálculo de frete.
🔗 DEPENDE  : app/models/base.py, empresa.py,
             transportadora.py, tabela_frete.py, usuario.py
📅 CRIADO  : 24/06/2026
📅 ATUALIZADO: 04/07/2026 — relacionamentos ativados
📅 ATUALIZADO: 11/07/2026 — removido total_peso_cubado_kg
               (MVP sem cubagem, decisão 06/07/2026).
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
'''

import enum

from sqlalchemy import (
    Column, String, Date, Numeric, Integer, Enum,
    ForeignKey, Text, UniqueConstraint
)
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID

from app.models.base import Base, AuditMixin


class StatusEmbarque(str, enum.Enum):
    '''
    🎯 O QUE FAZ:
        Define os estados possíveis de um embarque.

    📐 REGRA DE NEGÓCIO:
        RASCUNHO  → Editável, NFs importadas.
        CALCULADO → Frete calculado, em revisão.
        ENVIADO   → Confirmado, sem edição de NFs.
        AUDITADO  → CT-e importado e auditado.
        CANCELADO → Sem operações adicionais.

    ⚠️  ATENÇÃO:
        Transições somente via serviço autorizado.
    '''
    RASCUNHO  = "rascunho"
    CALCULADO = "calculado"
    ENVIADO   = "enviado"
    AUDITADO  = "auditado"
    CANCELADO = "cancelado"


class Embarque(Base, AuditMixin):
    '''
    🎯 O QUE FAZ:
        Representa um embarque — agrupamento de NFs
        destinadas a uma transportadora em uma data.
        Unidade principal de cálculo, revisão e
        auditoria de frete.

    📐 REGRA DE NEGÓCIO:
        - Pertence a exatamente uma Empresa (multi-tenant).
        - Vinculado a uma Transportadora e à TabelaFrete
          ativa no momento da criação (congelada).
        - Status controla ciclo de vida (ver StatusEmbarque).
        - Totalizadores desnormalizados para performance,
          recalculados a cada alteração de NF.
        - ENVIADO/AUDITADO bloqueiam edição de NFs.
        - MVP sem cubagem: apenas peso real (06/07/2026).

    🗂️  TABELA: embarques

    ⚠️  ATENÇÃO:
        Não modificar sem autorização de Allison.
    '''

    __tablename__ = "embarques"

    # ─────────────────────────────────────────────
    # 🔗 Vínculos
    # ─────────────────────────────────────────────
    empresa_id = Column(
        UUID(as_uuid=True), ForeignKey("empresas.id", ondelete="CASCADE"),
        nullable=False, index=True,
        comment="Empresa à qual este embarque pertence"
    )
    transportadora_id = Column(
        UUID(as_uuid=True), ForeignKey("transportadoras.id", ondelete="RESTRICT"),
        nullable=False, index=True,
        comment="Transportadora responsável pelo embarque"
    )
    tabela_frete_id = Column(
        UUID(as_uuid=True), ForeignKey("tabelas_frete.id", ondelete="RESTRICT"),
        nullable=False,
        comment="Tabela de frete congelada no momento da criação"
    )
    criado_por_id = Column(
        UUID(as_uuid=True), ForeignKey("usuarios.id", ondelete="SET NULL"),
        nullable=True, index=True,
        comment="Usuário que criou o embarque"
    )

    # ─────────────────────────────────────────────
    # 📋 Identificação e Ciclo de Vida
    # ─────────────────────────────────────────────
    codigo = Column(
        String(50), nullable=False, index=True,
        comment="Código único por empresa. Ex: EMB-2026-0001"
    )
    data_embarque = Column(
        Date, nullable=False,
        comment="Data prevista/realizada do embarque"
    )
    status = Column(
        Enum(StatusEmbarque), nullable=False, default=StatusEmbarque.RASCUNHO,
        index=True,
        comment="Status atual do ciclo de vida"
    )

    # ─────────────────────────────────────────────
    # 📊 Totalizadores (desnormalizados)
    # ─────────────────────────────────────────────
    total_nfs = Column(
        Integer, nullable=False, default=0,
        comment="Quantidade de NFs no embarque"
    )
    total_peso_real_kg = Column(
        Numeric(12, 3), nullable=False, default=0,
        comment="Soma do peso real de todas as NFs em kg"
    )
    total_frete_calculado = Column(
        Numeric(14, 2), nullable=False, default=0,
        comment="Soma do frete calculado de todas as NFs em R$"
    )
    total_valor_nfs = Column(
        Numeric(14, 2), nullable=False, default=0,
        comment="Soma do valor fiscal de todas as NFs em R$"
    )

    # ─────────────────────────────────────────────
    # 📝 Observações
    # ─────────────────────────────────────────────
    observacao = Column(
        Text, nullable=True,
        comment="Observações livres sobre o embarque"
    )

    # ─────────────────────────────────────────────
    # 🔗 Relacionamentos
    # ─────────────────────────────────────────────
    empresa = relationship(
        "Empresa", back_populates="embarques", lazy="select",
    )
    transportadora = relationship(
        "Transportadora", back_populates="embarques", lazy="select",
    )
    tabela_frete = relationship(
        "TabelaFrete", lazy="select",
    )
    criado_por = relationship(
        "Usuario", back_populates="embarques_criados", lazy="select",
    )
    notas_fiscais = relationship(
        "NotaFiscal", back_populates="embarque",
        cascade="all, delete-orphan", lazy="select",
    )
    ctes = relationship(
        "Cte", back_populates="embarque", lazy="select",
    )

    # ─────────────────────────────────────────────
    # ✅ Constraints
    # ─────────────────────────────────────────────
    __table_args__ = (
        UniqueConstraint(
            "empresa_id", "codigo",
            name="uq_embarque_empresa_codigo"
        ),
    )

    # ─────────────────────────────────────────────
    # 🔍 Representação
    # ─────────────────────────────────────────────
    def __repr__(self):
        return (
            f"<Embarque [{self.codigo}] {self.status} "
            f"— {self.total_nfs} NFs>"
        )
