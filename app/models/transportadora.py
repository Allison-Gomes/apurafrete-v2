'''
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📁 ARQUIVO : transportadora.py
📦 MÓDULO  : Cadastros
🎯 OBJETIVO: Define o model Transportadora, cadastrada
             por empresa, com suas tabelas de frete,
             embarques, CT-es e notas fiscais vinculadas.
🔗 DEPENDE  : app/models/base.py
             app/models/empresa.py
📅 CRIADO   : 24/06/2026
📅 ATUALIZADO: 04/07/2026 — relacionamentos ativados
📅 ATUALIZADO: 04/07/2026 — campo 'ativo' adicionado
📅 ATUALIZADO: 11/07/2026 — adicionado relationship
               notas_fiscais (MVP v2.3 — Seção 1.3).
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
'''

from sqlalchemy import Column, String, Boolean, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID

from app.models.base import Base, AuditMixin


class Transportadora(Base, AuditMixin):
    '''
    🎯 O QUE FAZ:
        Representa uma transportadora cadastrada por
        uma empresa cliente, com suas tabelas de frete,
        embarques, CT-es e notas fiscais vinculadas.

    📐 REGRA DE NEGÓCIO:
        - Pertence a exatamente uma Empresa (multi-tenant).
        - CNPJ único por Empresa.
        - codigo_interno é referência usada nas planilhas
          de importação (MVP Seção 4.1 — coluna TRANSPORTADORA).
        - Transportadora inativa (ativo=False) não pode
          ser selecionada em novos embarques (Seção 1.3).
        - A seleção manual de transportadora para cada NF
          é feita via NotaFiscal.transportadora_id (Seção 6.1).

    🗂️  TABELA: transportadoras

    ⚠️  ATENÇÃO:
        Não modificar sem autorização de Allison.
    '''

    __tablename__ = "transportadoras"

    # ─────────────────────────────────────────────
    # 🔗 Vínculo com Empresa (multi-tenant)
    # ─────────────────────────────────────────────
    empresa_id = Column(
        UUID(as_uuid=True),
        ForeignKey("empresas.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Empresa à qual esta transportadora pertence",
    )

    # ─────────────────────────────────────────────
    # 📋 Identificação
    # ─────────────────────────────────────────────
    razao_social = Column(
        String(200),
        nullable=False,
        comment="Razão social da transportadora",
    )

    nome_fantasia = Column(
        String(200),
        nullable=True,
        comment="Nome fantasia da transportadora",
    )

    cnpj = Column(
        String(18),
        nullable=True,
        index=True,
        comment="CNPJ formatado (XX.XXX.XXX/XXXX-XX)",
    )

    codigo_interno = Column(
        String(50),
        nullable=True,
        index=True,
        comment="Código interno usado na importação de planilhas. "
                "Origem: coluna TRANSPORTADORA (MVP Seção 4.1).",
    )

    # ─────────────────────────────────────────────
    # 📞 Contato
    # ─────────────────────────────────────────────
    email_contato = Column(
        String(255),
        nullable=True,
        comment="E-mail de contato da transportadora",
    )

    telefone = Column(
        String(20),
        nullable=True,
        comment="Telefone de contato da transportadora",
    )

    # ─────────────────────────────────────────────
    # 📝 Informações Adicionais
    # ─────────────────────────────────────────────
    observacao = Column(
        String(500),
        nullable=True,
        comment="Observações livres sobre a transportadora",
    )

    ativo = Column(
        Boolean,
        nullable=False,
        default=True,
        comment="Se False, transportadora não pode ser "
                "selecionada em novos embarques (Seção 1.3).",
    )

    # ─────────────────────────────────────────────
    # 🔗 Relacionamentos
    # ─────────────────────────────────────────────
    empresa = relationship(
        "Empresa",
        back_populates="transportadoras",
        lazy="select",
    )

    tabelas_frete = relationship(
        "TabelaFrete",
        back_populates="transportadora",
        lazy="select",
    )

    embarques = relationship(
        "Embarque",
        back_populates="transportadora",
        lazy="select",
    )

    ctes = relationship(
        "Cte",
        back_populates="transportadora",
        lazy="select",
    )

    notas_fiscais = relationship(
        "NotaFiscal",
        back_populates="transportadora",
        lazy="select",
    )

    # ─────────────────────────────────────────────
    # ✅ Constraints
    # ─────────────────────────────────────────────
    __table_args__ = (
        UniqueConstraint(
            "empresa_id",
            "cnpj",
            name="uq_transportadora_empresa_cnpj",
        ),
        UniqueConstraint(
            "empresa_id",
            "codigo_interno",
            name="uq_transportadora_empresa_codigo",
        ),
    )

    # ─────────────────────────────────────────────
    # 🔍 Representação
    # ─────────────────────────────────────────────
    def __repr__(self):
        '''
        🎯 O QUE FAZ:
            Retorna representação legível da Transportadora
            para logs e debugging.

        📤 RETORNO:
            str: Ex: <Transportadora [XPTO] TRANSPORTES XPTO LTDA>
        '''
        return (
            f"<Transportadora [{self.codigo_interno}] {self.razao_social}>"
        )
