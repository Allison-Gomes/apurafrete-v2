'''
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📁 ARQUIVO : tabela_frete.py
📦 MÓDULO  : Cadastros
🎯 OBJETIVO: Define os models TabelaFrete e FaixaFrete,
             que representam a estrutura de precificação
             de frete por transportadora.

             REGRA DE NEGÓCIO (MVP):
               Se peso_total_kg ≤ 30:
                 frete = valor_minimo_faixa (faixa 0→30)
               Se peso_total_kg > 30:
                 frete = valor_minimo_faixa + (peso_total_kg − 30) × valor_kg (faixa 30→∞)

             A TabelaFrete agrupa as faixas de peso e
             seus respectivos valores unitários.

             SEPARAÇÃO DE RESPONSABILIDADES:
               TabelaFrete + FaixaFrete → O QUANTO se cobra.
               RotaFrete                → PARA ONDE a tabela vale.
🔗 DEPENDE  : app/models/base.py
             app/models/transportadora.py
             app/models/rota_frete.py (relationship 'rotas')
📅 CRIADO  : 24/06/2026
📅 ATUALIZADO: 11/07/2026 — refatoração MVP: removidos
               cubagem e adicionais; docstrings em aspas
               triplas simples; regra de negócio explícita.
📅 ATUALIZADO: 28/07/2026 — adicionado relationship 'rotas'
               (RotaFrete, opção B). A resolução da tabela
               passa a considerar UF/cidade de destino da NF.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
'''

import enum

from sqlalchemy import (
    Boolean, CheckConstraint, Column, ForeignKey, Numeric, String,
    Enum as SAEnum,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.models.base import AuditMixin, Base


# ─────────────────────────────────────────────────
# 🔑 ENUM: ModalidadeFrete
# Define como o frete é calculado na tabela.
# ─────────────────────────────────────────────────
class ModalidadeFrete(str, enum.Enum):
    '''
    🎯 O QUE FAZ:
        Define a modalidade de cálculo da tabela de frete.

    📐 REGRA DE NEGÓCIO (MVP):
        - PROGRESSIVO : Até 30 kg cobra-se o valor fixo da
                        primeira faixa. Acima de 30 kg,
                        cobra-se o valor fixo + adicional
                        por kg excedente.

                        frete = valor_minimo_faixa + max(0, peso − 30) × valor_kg

        - POR_FAIXA   : O peso cai em uma faixa e o valor
                        da faixa é aplicado integralmente
                        (uso futuro, fora do MVP).

    ⚠️  ATENÇÃO:
        Modalidades novas somente com autorização de Allison.
        A lógica de cálculo em services/calculo_frete_service.py
        deve respeitar estritamente este enum.
    '''
    POR_FAIXA = "por_faixa"
    PROGRESSIVO = "progressivo"


# ─────────────────────────────────────────────────
# 📋 MODEL: TabelaFrete
# Cabeçalho da tabela de frete de uma transportadora.
# ─────────────────────────────────────────────────
class TabelaFrete(Base, AuditMixin):
    '''
    🎯 O QUE FAZ:
        Representa o cabeçalho de uma tabela de frete
        vinculada a uma transportadora.

    📐 REGRA DE NEGÓCIO (MVP):
        - Cada transportadora pode ter múltiplas tabelas,
          mas apenas UMA pode estar ativa (tabela_ativa=True)
          por transportadora por vez.
        - A modalidade define como o engine de cálculo
          interpreta as faixas de peso.
        - A resolução da tabela no cálculo é feita por
          transportadora_id + tabela_ativa=True + RotaFrete
          que atenda a UF/cidade de destino da NF.
        - Fator de cubagem, GRIS, Ad Valorem, despacho e
          emissão de CT-e estão FORA do escopo MVP (#28).

    🗂️  TABELA: tabelas_frete

    ⚠️  ATENÇÃO:
        Não modificar sem autorização de Allison.
    '''

    __tablename__ = "tabelas_frete"

    # ── Vínculo com Transportadora ───────────────
    transportadora_id = Column(
        UUID(as_uuid=True),
        ForeignKey("transportadoras.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Transportadora à qual esta tabela pertence"
    )

    # ── Identificação ────────────────────────────
    nome = Column(
        String(150),
        nullable=False,
        comment="Nome descritivo da tabela. Ex: 'Tabela SP 2026'"
    )

    modalidade = Column(
        SAEnum(ModalidadeFrete),
        nullable=False,
        default=ModalidadeFrete.PROGRESSIVO,
        comment="Modalidade de cálculo: por_faixa | progressivo"
    )

    tabela_ativa = Column(
        Boolean,
        nullable=False,
        default=False,
        comment="True = tabela vigente para cálculo de frete. "
                "Apenas uma tabela ativa por transportadora."
    )

    # ── Observações ──────────────────────────────
    observacao = Column(
        String(500),
        nullable=True,
        comment="Observações livres sobre a tabela de frete"
    )

    # ── Relacionamentos ──────────────────────────
    transportadora = relationship(
        "Transportadora",
        back_populates="tabelas_frete",
        lazy="select",
    )

    # OBS: relacionamento com faixas mantido ativo
    # pois FaixaFrete está no mesmo arquivo e não gera
    # dependência circular.
    faixas = relationship(
        "FaixaFrete",
        back_populates="tabela",
        cascade="all, delete-orphan",
        order_by="FaixaFrete.peso_ate_kg",
        lazy="select",
    )

    # 🆕 28/07/2026 — dimensão geográfica (opção B).
    # Resolvido por string para evitar import circular
    # entre tabela_frete.py e rota_frete.py.
    rotas = relationship(
        "RotaFrete",
        back_populates="tabela",
        cascade="all, delete-orphan",
        order_by="RotaFrete.uf",
        lazy="select",
    )

    # ── Representação ────────────────────────────
    def __repr__(self):
        '''
        🎯 O QUE FAZ:
            Retorna representação legível da TabelaFrete
            para logs e debugging.

        📤 RETORNO:
            str: Ex: <TabelaFrete [ATIVA] Tabela SP 2026>
        '''
        status = "ATIVA" if self.tabela_ativa else "inativa"
        return f"<TabelaFrete [{status}] {self.nome}>"


# ─────────────────────────────────────────────────
# 📊 MODEL: FaixaFrete
# Faixas de peso vinculadas a uma TabelaFrete.
# ─────────────────────────────────────────────────
class FaixaFrete(Base, AuditMixin):
    '''
    🎯 O QUE FAZ:
        Representa uma faixa de peso dentro de uma
        TabelaFrete, com o valor unitário aplicado
        para aquele intervalo de peso.

    📐 REGRA DE NEGÓCIO (MVP):
        - São esperadas exatamente DUAS faixas por tabela:

          Faixa 1: peso_de_kg=0  | peso_ate_kg=30
            → valor_minimo_faixa = preço fixo para fretes ≤ 30 kg
            → valor_kg = ignorado no cálculo (MVP)

          Faixa 2: peso_de_kg=30 | peso_ate_kg=NULL
            → valor_kg = preço por kg adicional acima de 30 kg
            → valor_minimo_faixa = ignorado no cálculo (MVP)

        - Fórmula aplicada:
            Se peso_total_kg ≤ 30:
              frete = faixa_1.valor_minimo_faixa
            Se peso_total_kg > 30:
              frete = faixa_1.valor_minimo_faixa + (peso_total_kg − 30) × faixa_2.valor_kg

        - As faixas não podem se sobrepor dentro da
          mesma tabela.
        - A primeira faixa deve ter peso_de_kg = 0.
        - peso_ate_kg = NULL indica faixa aberta
          (acima do último limite definido).

    🗂️  TABELA: faixas_frete

    ⚠️  ATENÇÃO:
        Não modificar sem autorização de Allison.
        A lógica de seleção de faixa está em
        services/calculo_frete_service.py.
    '''

    __tablename__ = "faixas_frete"

    # ── Vínculo com TabelaFrete ──────────────────
    tabela_id = Column(
        UUID(as_uuid=True),
        ForeignKey("tabelas_frete.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Tabela de frete à qual esta faixa pertence"
    )

    # ── Intervalo de Peso ────────────────────────
    peso_de_kg = Column(
        Numeric(10, 3),
        nullable=False,
        comment="Limite inferior da faixa (exclusivo) em kg. "
                "Primeira faixa deve ser 0."
    )

    peso_ate_kg = Column(
        Numeric(10, 3),
        nullable=True,
        comment="Limite superior da faixa (inclusivo) em kg. "
                "NULL = faixa aberta (sem limite superior)."
    )

    # ── Precificação ─────────────────────────────
    valor_kg = Column(
        Numeric(10, 4),
        nullable=False,
        comment="Valor por kg nesta faixa em reais. "
                "No MVP, usado apenas na faixa 2 (30 kg → ∞) "
                "como adicional por kg excedente."
    )

    valor_minimo_faixa = Column(
        Numeric(10, 2),
        nullable=True,
        comment="Valor mínimo cobrado nesta faixa em reais. "
                "No MVP, usado apenas na faixa 1 (0 → 30 kg) "
                "como preço fixo para fretes até 30 kg."
    )

    # ── Relacionamento ───────────────────────────
    tabela = relationship(
        "TabelaFrete",
        back_populates="faixas",
        lazy="select",
    )

    # ── Constraints ──────────────────────────────
    __table_args__ = (
        CheckConstraint(
            "peso_de_kg >= 0",
            name="ck_faixa_peso_de_nao_negativo"
        ),
        CheckConstraint(
            "peso_ate_kg IS NULL OR peso_ate_kg > peso_de_kg",
            name="ck_faixa_peso_ate_maior_que_de"
        ),
        CheckConstraint(
            "valor_kg >= 0",
            name="ck_faixa_valor_kg_nao_negativo"
        ),
    )

    # ── Representação ────────────────────────────
    def __repr__(self):
        '''
        🎯 O QUE FAZ:
            Retorna representação legível da FaixaFrete
            para logs e debugging.

        📤 RETORNO:
            str: Ex: <FaixaFrete [0kg → 30kg] R$ 2.5000/kg>
        '''
        ate = f"{self.peso_ate_kg}kg" if self.peso_ate_kg else "∞"
        return f"<FaixaFrete [{self.peso_de_kg}kg → {ate}] R$ {self.valor_kg}/kg>"
