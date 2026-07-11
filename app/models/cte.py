'''
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📁 ARQUIVO : cte.py
📦 MÓDULO  : Auditoria
🎯 OBJETIVO: Define os models Cte e ItemCte, que
             representam o CT-e importado e o rateio
             de seus valores por NF, permitindo a
             auditoria de divergências entre o frete
             calculado e o cobrado.
🔗 DEPENDE  : app/models/base.py, embarque.py,
             transportadora.py, nota_fiscal.py
📅 CRIADO  : 24/06/2026
📅 ATUALIZADO: 04/07/2026 — padronização de docstrings
📅 ATUALIZADO: 11/07/2026 — removido campo cancelado
               (redundante com status=CANCELADO);
               removido total_calculado_nfs e
               divergencia_total (desnormalização
               calculável via itens).
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
'''

import enum

from sqlalchemy import (
    Column, String, Numeric, Date,
    ForeignKey, Text, Enum,
    CheckConstraint, UniqueConstraint,
)
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID

from app.models.base import Base, AuditMixin


class StatusCte(str, enum.Enum):
    '''
    📐 REGRA DE NEGÓCIO (MVP v2.3 — Seção 8):
        IMPORTADO   → CT-e importado, aguardando vinculação.
        VINCULADO   → Associado a um embarque.
        AUDITADO    → Rateio concluído, sem divergências.
        DIVERGENTE  → Ao menos uma NF com divergência > 5%.
        CANCELADO   → CT-e descartado (sem operações adicionais).

    ⚠️  ATENÇÃO: Não alterar sem autorização de Allison.
    '''
    IMPORTADO  = "importado"
    VINCULADO  = "vinculado"
    AUDITADO   = "auditado"
    DIVERGENTE = "divergente"
    CANCELADO  = "cancelado"


class OrigemCte(str, enum.Enum):
    '''
    📐 REGRA DE NEGÓCIO:
        XML | PLANILHA | MANUAL — origem da importação.

    ⚠️  ATENÇÃO: Não alterar sem autorização de Allison.
    '''
    XML      = "xml"
    PLANILHA = "planilha"
    MANUAL   = "manual"


class Cte(Base, AuditMixin):
    '''
    🎯 O QUE FAZ:
        Representa um CT-e emitido pela transportadora,
        contendo o valor total cobrado e dados fiscais.
        Após vinculação com um embarque, seus valores
        são rateados entre as NFs via ItemCte.

    📐 REGRA DE NEGÓCIO (MVP v2.3 — Seção 8):
        - Pertence a uma Transportadora.
        - Pode ser vinculado a no máximo um Embarque.
        - valor_total_cte é o valor efetivamente cobrado.
        - chave_cte (44 dígitos) evita importação duplicada.
        - Cancelamento via status = CANCELADO (sem campo
          booleano separado — fonte única de verdade).
        - total_rateado: soma dos itens vinculados.
        - CT-es cancelados não entram na auditoria.

    🗂️  TABELA: ctes

    ⚠️  ATENÇÃO:
        Não modificar sem autorização de Allison.
        Lógica de rateio em services/auditoria_cte.py.
    '''

    __tablename__ = "ctes"

    # ─────────────────────────────────────────────
    # 🔗 Vínculos
    # ─────────────────────────────────────────────
    transportadora_id = Column(
        UUID(as_uuid=True),
        ForeignKey("transportadoras.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        comment="Transportadora emissora do CT-e",
    )
    embarque_id = Column(
        UUID(as_uuid=True),
        ForeignKey("embarques.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Embarque ao qual este CT-e está vinculado",
    )

    # ─────────────────────────────────────────────
    # 📋 Identificação Fiscal
    # ─────────────────────────────────────────────
    chave_cte = Column(
        String(44),
        nullable=True,
        unique=True,
        index=True,
        comment="Chave de acesso do CT-e (44 dígitos). Única no sistema.",
    )
    numero_cte = Column(
        String(20),
        nullable=False,
        comment="Número do CT-e",
    )
    serie_cte = Column(
        String(5),
        nullable=True,
        comment="Série do CT-e. Ex: 001",
    )
    data_emissao = Column(
        Date,
        nullable=False,
        comment="Data de emissão do CT-e",
    )

    # ─────────────────────────────────────────────
    # 💰 Valores do CT-e
    # ─────────────────────────────────────────────
    valor_total_cte = Column(
        Numeric(14, 2),
        nullable=False,
        comment="Valor total cobrado em R$. Base da auditoria.",
    )
    valor_frete_cte = Column(
        Numeric(14, 2),
        nullable=True,
        comment="Valor do frete destacado no CT-e em R$",
    )
    valor_pedagio = Column(
        Numeric(12, 2),
        nullable=True,
        comment="Valor de pedágio destacado no CT-e em R$",
    )
    valor_outros = Column(
        Numeric(12, 2),
        nullable=True,
        comment="Outros valores cobrados no CT-e em R$",
    )

    # ─────────────────────────────────────────────
    # 📊 Totalizador (desnormalizado)
    # ─────────────────────────────────────────────
    total_rateado = Column(
        Numeric(14, 2),
        nullable=False,
        default=0,
        comment="Soma dos valores já rateados via ItemCte em R$. "
                "Deve ser ≤ valor_total_cte.",
    )

    # ─────────────────────────────────────────────
    # 🏷️ Status e Origem
    # ─────────────────────────────────────────────
    status = Column(
        Enum(StatusCte),
        nullable=False,
        default=StatusCte.IMPORTADO,
        index=True,
        comment="Status do CT-e no ciclo de vida. "
                "CANCELADO substitui o antigo campo booleano 'cancelado'.",
    )
    origem = Column(
        Enum(OrigemCte),
        nullable=False,
        default=OrigemCte.XML,
        comment="Como o CT-e foi inserido no sistema",
    )
    arquivo_origem = Column(
        String(255),
        nullable=True,
        comment="Nome do arquivo de origem (XML ou planilha)",
    )

    # ─────────────────────────────────────────────
    # 📝 Observações
    # ─────────────────────────────────────────────
    observacao = Column(
        Text,
        nullable=True,
        comment="Observações livres sobre o CT-e",
    )

    # ─────────────────────────────────────────────
    # 🔗 Relacionamentos
    # ─────────────────────────────────────────────
    transportadora = relationship(
        "Transportadora",
        back_populates="ctes",
        lazy="select",
    )
    embarque = relationship(
        "Embarque",
        back_populates="ctes",
        lazy="select",
    )
    itens = relationship(
        "ItemCte",
        back_populates="cte",
        cascade="all, delete-orphan",
        lazy="select",
    )

    # ─────────────────────────────────────────────
    # ✅ Constraints
    # ─────────────────────────────────────────────
    __table_args__ = (
        CheckConstraint(
            "valor_total_cte >= 0",
            name="ck_cte_valor_total_nao_negativo",
        ),
        CheckConstraint(
            "total_rateado >= 0",
            name="ck_cte_total_rateado_nao_negativo",
        ),
    )

    # ─────────────────────────────────────────────
    # 🔍 Representação
    # ─────────────────────────────────────────────
    def __repr__(self):
        return (
            f"<Cte [{self.numero_cte}] "
            f"R$ {self.valor_total_cte} | {self.status}>"
        )


class ItemCte(Base, AuditMixin):
    '''
    🎯 O QUE FAZ:
        Representa o rateio de um CT-e para uma NF
        específica, registrando o valor cobrado pela
        transportadora e a divergência em relação ao
        frete calculado pelo ApuraFrete.

    📐 REGRA DE NEGÓCIO (MVP v2.3 — Seção 8.3 e 8.4):
        - Vincula um CT-e a uma NotaFiscal.
        - Uma NF aparece em no máximo um ItemCte por CT-e.
        - valor_rateado: parcela do CT-e atribuída à NF
          (rateio igualitário com resíduo na 1ª NF).
        - valor_calculado: snapshot imutável do frete
          calculado no momento da auditoria.
        - divergencia = valor_rateado - valor_calculado.
        - divergencia_percentual = (divergencia / valor_calculado) × 100.
        - Tolerância de ±5% para considerar OK (Seção 8.4).

    🗂️  TABELA: itens_cte

    ⚠️  ATENÇÃO:
        Não modificar sem autorização de Allison.
        Lógica de rateio em services/auditoria_cte.py.
    '''

    __tablename__ = "itens_cte"

    # ─────────────────────────────────────────────
    # 🔗 Vínculos
    # ─────────────────────────────────────────────
    cte_id = Column(
        UUID(as_uuid=True),
        ForeignKey("ctes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="CT-e ao qual este item pertence",
    )
    nota_fiscal_id = Column(
        UUID(as_uuid=True),
        ForeignKey("notas_fiscais.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="NF vinculada a este item de rateio",
    )

    # ─────────────────────────────────────────────
    # 💰 Valores do Rateio
    # ─────────────────────────────────────────────
    valor_rateado = Column(
        Numeric(12, 2),
        nullable=False,
        comment="Valor do CT-e rateado para esta NF em R$",
    )
    valor_calculado = Column(
        Numeric(12, 2),
        nullable=False,
        comment="Snapshot do frete calculado pelo ApuraFrete para esta NF",
    )

    # ─────────────────────────────────────────────
    # 📊 Divergência
    # ─────────────────────────────────────────────
    divergencia = Column(
        Numeric(12, 2),
        nullable=False,
        comment="valor_rateado - valor_calculado. Positivo = cobrado a mais.",
    )
    divergencia_percentual = Column(
        Numeric(8, 4),
        nullable=True,
        comment="(divergencia / valor_calculado) × 100",
    )

    # ─────────────────────────────────────────────
    # 📝 Observações
    # ─────────────────────────────────────────────
    observacao = Column(
        Text,
        nullable=True,
        comment="Observações ou justificativa da divergência",
    )

    # ─────────────────────────────────────────────
    # 🔗 Relacionamentos
    # ─────────────────────────────────────────────
    cte = relationship(
        "Cte",
        back_populates="itens",
        lazy="select",
    )
    nota_fiscal = relationship(
        "NotaFiscal",
        back_populates="itens_cte",
        lazy="select",
    )

    # ─────────────────────────────────────────────
    # ✅ Constraints
    # ─────────────────────────────────────────────
    __table_args__ = (
        UniqueConstraint(
            "cte_id",
            "nota_fiscal_id",
            name="uq_item_cte_cte_nf",
        ),
        CheckConstraint(
            "valor_rateado >= 0",
            name="ck_item_cte_valor_rateado_nao_negativo",
        ),
        CheckConstraint(
            "valor_calculado >= 0",
            name="ck_item_cte_valor_calculado_nao_negativo",
        ),
    )

    # ─────────────────────────────────────────────
    # 🔍 Representação
    # ─────────────────────────────────────────────
    def __repr__(self):
        return (
            f"<ItemCte rateado=R$ {self.valor_rateado} | "
            f"calculado=R$ {self.valor_calculado} | "
            f"divergencia=R$ {self.divergencia}>"
        )
