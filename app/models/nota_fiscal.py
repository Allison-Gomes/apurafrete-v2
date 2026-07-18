'''
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📁 ARQUIVO : nota_fiscal.py
📦 MÓDULO  : Embarque
🎯 OBJETIVO: Define o model NotaFiscal, que representa
             cada nota fiscal importada dentro de um
             embarque, com seus dados de origem/destino,
             produto, peso derivado do catálogo e snapshot
             de auditoria do cálculo de frete.
🔗 DEPENDE  : app/models/base.py
              app/models/embarque.py
              app/models/transportadora.py
📅 CRIADO   : 24/06/2026
📅 ATUALIZADO: 18/07/2026 — Simplificação para alinhar
               com nf_schema.py (Opção B). Removidos
               campos de remetente, cod_cliente, cidade_*_raw.
               Renomeados: qtd_cx → quantidade_volumes,
               peso_total_kg → peso_real_kg,
               cliente_destino → destinatario_nome, etc.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
'''

import enum

from sqlalchemy import (
    Column, String, Numeric, Date, Integer, Enum,
    ForeignKey, Text, CheckConstraint, UniqueConstraint,
)
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID

from app.models.base import Base, AuditMixin


# ── ENUM: StatusCalculoNF ────────────────────────
class StatusCalculoNF(str, enum.Enum):
    '''
    🎯 O QUE FAZ:
        Enumera os estados do cálculo de frete de cada NF.

    📐 REGRA DE NEGÓCIO (MVP v2.3 — Seção 6.7):
        PENDENTE            → NF importada, aguardando cálculo
                              (estado inicial).
        CALCULADO           → Frete calculado com sucesso.
                              valor_calculado + snapshot preenchidos.
        SEM_TABELA          → Rota não encontrada na tabela de frete
                              da transportadora selecionada.
        SEM_TRANSPORTADORA  → Nenhuma transportadora selecionada
                              manualmente para esta NF.
        ERRO                → Falha genérica. Motivo em erro_calculo.
        IGNORADA            → NF marcada para exclusão lógica.
                              Não entra em cálculo nem auditoria.

    ⚠️  ATENÇÃO:
        Não modificar sem autorização de Allison.
    '''
    PENDENTE           = "pendente"
    CALCULADO          = "calculado"
    SEM_TABELA         = "sem_tabela"
    SEM_TRANSPORTADORA = "sem_transportadora"
    ERRO               = "erro"
    IGNORADA           = "ignorada"


# ── MODEL: NotaFiscal ────────────────────────────
class NotaFiscal(Base, AuditMixin):
    '''
    🎯 O QUE FAZ:
        Representa uma nota fiscal importada em um embarque.

    📐 REGRAS (MVP v2.3):
        - Vinculada a exatamente 1 Embarque.
        - Chave de deduplicação: (numero_nf, serie_nf) dentro do
          embarque (Seção 4.7).
        - Peso total derivado do catálogo:
          peso_real_kg = QTD_CX × produto.peso_real_kg (Seção 3.1).
          Não há cubagem — apenas peso real.
        - Fórmula de frete (Seção 6.4):
          Se ≤ 30kg → frete = preco_ate_30kg
          Se > 30kg → frete = preco_ate_30kg +
                             (peso_real_kg − 30) × valor_kg_adicional
        - Snapshot para auditoria (Seção 6.6):
          preco_ate_30kg_usado, valor_kg_adicional_usado, peso_kg_usado.

    🗂️  TABELA: notas_fiscais

    ⚠️  ATENÇÃO:
        Lógica de cálculo em services/calculo_frete.py.
        Não modificar sem autorização de Allison.
    '''

    __tablename__ = "notas_fiscais"

    # ── Vínculo com Embarque ─────────────────────
    embarque_id = Column(
        UUID(as_uuid=True),
        ForeignKey("embarques.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Embarque ao qual esta NF pertence",
    )

    # ── Identificação da NF ──────────────────────
    numero_nf = Column(
        String(50),
        nullable=False,
        comment="Número do documento/NF. "
                "Origem: coluna DOCUMENTO da planilha.",
    )

    serie_nf = Column(
        String(10),
        nullable=True,
        comment="Série da nota fiscal. Ex: 001, A, B.",
    )

    chave_nfe = Column(
        String(44),
        nullable=True,
        index=True,
        comment="Chave de acesso da NF-e (44 dígitos). "
                "Usada na auditoria CT-e (Seção 8.2).",
    )

    data_emissao = Column(
        Date,
        nullable=True,
        comment="Data de emissão da nota fiscal",
    )

    # ── Destinatário ─────────────────────────────
    destinatario_nome = Column(
        String(200),
        nullable=True,
        comment="Nome do destinatário. "
                "Origem: coluna DESTINATÁRIO da planilha.",
    )

    destinatario_cnpj_cpf = Column(
        String(14),
        nullable=True,
        comment="CNPJ/CPF do destinatário (sem máscara). "
                "Origem: coluna CNPJ/CPF DESTINATÁRIO.",
    )

    destinatario_cidade = Column(
        String(100),
        nullable=True,
        comment="Cidade de destino. "
                "Origem: coluna CIDADE DESTINO.",
    )

    destinatario_uf = Column(
        String(2),
        nullable=True,
        comment="UF de destino (2 letras). Ex: SP, RJ, MG. "
                "Origem: coluna UF DESTINO.",
    )

    # ── Produto e Quantidade ─────────────────────
    cod_produto = Column(
        String(50),
        nullable=False,
        comment="SKU do produto (catálogo). "
                "Origem: coluna COD PRODUTO. "
                "Deve existir no cadastro (Seção 1.2).",
    )

    quantidade_volumes = Column(
        Integer,
        nullable=False,
        comment="Quantidade de caixas/volumes. "
                "Origem: coluna QTD CX. Deve ser ≥ 1 (Seção 4.2).",
    )

    # ── Peso (derivado do catálogo) ──────────────
    peso_real_kg = Column(
        Numeric(10, 3),
        nullable=False,
        comment="Peso total da NF em kg. "
                "Fórmula: QTD_CX × produto.peso_real_kg (Seção 3.1). "
                "Armazenado para auditoria e reprocessabilidade.",
    )

    # ── Dados Fiscais ────────────────────────────
    nf_valor = Column(
        Numeric(14, 2),
        nullable=True,
        comment="Valor total da nota fiscal em R$ (informativo).",
    )

    # ── Transportadora (Seção 1.3 e 6.1) ─────────
    transportadora_id = Column(
        UUID(as_uuid=True),
        ForeignKey("transportadoras.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Transportadora selecionada manualmente. "
                "NULL = ainda não selecionada (Seção 6.1).",
    )

    # ── Resultado do Cálculo de Frete ────────────
    valor_calculado = Column(
        Numeric(12, 2),
        nullable=True,
        comment="Valor do frete calculado em R$ "
                "(fórmula da Seção 6.4).",
    )

    prazo_dias = Column(
        Integer,
        nullable=True,
        comment="Prazo de entrega em dias, conforme tabela "
                "(informativo — Seção 7.2).",
    )

    # ── Snapshot para Auditoria (Seção 6.6) ──────
    preco_ate_30kg_usado = Column(
        Numeric(12, 2),
        nullable=True,
        comment="Snapshot: preço até 30kg usado no cálculo.",
    )

    valor_kg_adicional_usado = Column(
        Numeric(12, 2),
        nullable=True,
        comment="Snapshot: valor do kg adicional usado no cálculo.",
    )

    peso_kg_usado = Column(
        Numeric(10, 3),
        nullable=True,
        comment="Snapshot: peso em kg usado no cálculo "
                "(= peso_real_kg no momento do cálculo).",
    )

    # ── Status e Rastreabilidade ─────────────────
    status_calculo = Column(
        Enum(StatusCalculoNF),
        nullable=False,
        default=StatusCalculoNF.PENDENTE,
        index=True,
        comment="Status do cálculo de frete (Seção 6.7).",
    )

    erro_calculo = Column(
        Text,
        nullable=True,
        comment="Descrição do erro (status_calculo = ERRO).",
    )

    # ── Campos Opcionais da Planilha (Seção 4.1) ─
    observacao = Column(
        Text,
        nullable=True,
        comment="Campo livre. Origem: coluna OBSERVAÇÃO.",
    )

    # ── Relacionamentos ──────────────────────────
    embarque = relationship(
        "Embarque",
        back_populates="notas_fiscais",
        lazy="select",
    )

    transportadora = relationship(
        "Transportadora",
        back_populates="notas_fiscais",
        lazy="select",
        foreign_keys=[transportadora_id],
    )

    itens_cte = relationship(
        "ItemCte",
        back_populates="nota_fiscal",
        lazy="select",
    )

    # ── Constraints ──────────────────────────────
    __table_args__ = (
        UniqueConstraint(
            "embarque_id",
            "numero_nf",
            "serie_nf",
            name="uq_nf_embarque_numero_serie",
        ),
        CheckConstraint(
            "quantidade_volumes >= 1",
            name="ck_nf_quantidade_volumes_positiva",
        ),
        CheckConstraint(
            "peso_real_kg > 0",
            name="ck_nf_peso_real_positivo",
        ),
        CheckConstraint(
            "nf_valor IS NULL OR nf_valor >= 0",
            name="ck_nf_valor_nao_negativo",
        ),
        CheckConstraint(
            "valor_calculado IS NULL OR valor_calculado >= 0",
            name="ck_nf_valor_calculado_nao_negativo",
        ),
        CheckConstraint(
            "prazo_dias IS NULL OR prazo_dias >= 0",
            name="ck_nf_prazo_dias_nao_negativo",
        ),
    )

    # ── Representação ────────────────────────────
    def __repr__(self):
        return (
            f"<NotaFiscal NF-{self.numero_nf} | "
            f"SKU={self.cod_produto} | "
            f"{self.peso_real_kg}kg | "
            f"{self.status_calculo}>"
        )
