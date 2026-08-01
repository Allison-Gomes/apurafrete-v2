'''
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📁 ARQUIVO : rota_frete.py
📦 MÓDULO  : Cadastros
🎯 OBJETIVO: Define o model RotaFrete, que adiciona a
             dimensão geográfica (UF/cidade de destino)
             à precificação de frete, SEM alterar a
             estrutura de faixas de peso existente.

             REGRA DE NEGÓCIO (MVP):
               TabelaFrete → O QUANTO se cobra (faixas).
               RotaFrete   → PARA ONDE a tabela é válida.

               Resolução em cascata:
                 1. rota com cidade_normalizada = cidade da NF
                 2. rota curinga da UF (cidade_normalizada IS NULL)
                 3. nenhuma rota ativa → status SEM_ROTA

               Após a fórmula progressiva da tabela,
               aplica-se o piso valor_minimo_rota:
                 frete = max(frete, valor_minimo_rota)
🔗 DEPENDE  : app/models/base.py
             app/models/tabela_frete.py
             app/utils/normalizacao.py (gravação da cidade)
📅 CRIADO  : 28/07/2026
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
'''

from __future__ import annotations

from sqlalchemy import (
    Boolean, CheckConstraint, Column, ForeignKey,
    Integer, Numeric, String,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.models.base import AuditMixin, Base


# ─────────────────────────────────────────────────
# 🗺️  MODEL: RotaFrete
# Vincula uma TabelaFrete a um destino (UF/cidade).
# ─────────────────────────────────────────────────
class RotaFrete(Base, AuditMixin):
    '''
    🎯 O QUE FAZ:
        Representa a abrangência geográfica de uma
        TabelaFrete: para qual UF e, opcionalmente,
        para qual cidade de destino ela se aplica.

    📐 REGRA DE NEGÓCIO (MVP):
        - cidade_normalizada preenchida → rota específica.
        - cidade_normalizada = NULL     → curinga da UF
                                          (vale para toda a UF).
        - A rota específica SEMPRE vence a curinga.
        - Não pode haver duas rotas com a mesma combinação
          (tabela_id, uf, cidade_normalizada). O curinga é
          tratado como valor único '*' no índice único.
        - valor_minimo_rota é um PISO opcional aplicado
          APÓS a fórmula progressiva da tabela.
        - prazo_dias é informativo e NÃO afeta o cálculo.
        - Rotas com ativo=False são ignoradas na resolução.

    🗂️  TABELA: rotas_frete

    ⚠️  ATENÇÃO:
        cidade_normalizada DEVE ser gravada usando
        app.utils.normalizacao.normalizar_cidade().
        Gravar texto bruto quebra a resolução da rota
        silenciosamente. Não modificar sem autorização
        de Allison.
    '''

    __tablename__ = "rotas_frete"

    # ── Vínculo com TabelaFrete ──────────────────
    tabela_id = Column(
        UUID(as_uuid=True),
        ForeignKey("tabelas_frete.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Tabela de frete que atende esta rota"
    )

    # ── Destino ──────────────────────────────────
    uf = Column(
        String(2),
        nullable=False,
        index=True,
        comment="UF de destino em maiúsculas. Ex: 'SP'"
    )

    cidade_normalizada = Column(
        String(120),
        nullable=True,
        index=True,
        comment="Cidade de destino normalizada (maiúsculas, "
                "sem acento). NULL = curinga válido para "
                "toda a UF."
    )

    # ── Parâmetros da rota ───────────────────────
    prazo_dias = Column(
        Integer,
        nullable=True,
        comment="Prazo de entrega em dias corridos. "
                "Informativo, não afeta o cálculo."
    )

    valor_minimo_rota = Column(
        Numeric(10, 2),
        nullable=True,
        comment="Piso de frete desta rota em reais. "
                "Aplicado após a fórmula progressiva."
    )

    ativo = Column(
        Boolean,
        nullable=False,
        default=True,
        comment="True = rota considerada na resolução de tarifa"
    )

    # ── Relacionamento ───────────────────────────
    tabela = relationship(
        "TabelaFrete",
        back_populates="rotas",
        lazy="select",
    )

    # ── Constraints ──────────────────────────────
    __table_args__ = (
        CheckConstraint(
            "char_length(uf) = 2",
            name="ck_rota_uf_tamanho"
        ),
        CheckConstraint(
            "uf = upper(uf)",
            name="ck_rota_uf_maiuscula"
        ),
        CheckConstraint(
            "cidade_normalizada IS NULL "
            "OR cidade_normalizada = upper(cidade_normalizada)",
            name="ck_rota_cidade_maiuscula"
        ),
        CheckConstraint(
            "prazo_dias IS NULL OR prazo_dias >= 0",
            name="ck_rota_prazo_nao_negativo"
        ),
        CheckConstraint(
            "valor_minimo_rota IS NULL OR valor_minimo_rota >= 0",
            name="ck_rota_minimo_nao_negativo"
        ),
    )

    # ── Propriedades ─────────────────────────────
    @property
    def eh_curinga(self) -> bool:
        '''
        🎯 O QUE FAZ:
            Indica se a rota é curinga da UF.

        📤 RETORNO:
            bool: True quando cidade_normalizada é NULL.
        '''
        return self.cidade_normalizada is None

    @property
    def destino(self) -> str:
        '''
        🎯 O QUE FAZ:
            Monta o rótulo do destino para logs e auditoria.

        📤 RETORNO:
            str: Ex: 'SP/CAMPINAS' ou 'SP/*'
        '''
        return f"{self.uf}/{self.cidade_normalizada or '*'}"

    # ── Representação ────────────────────────────
    def __repr__(self):
        '''
        🎯 O QUE FAZ:
            Retorna representação legível da RotaFrete
            para logs e debugging.

        📤 RETORNO:
            str: Ex: <RotaFrete SP/CAMPINAS>
        '''
        return f"<RotaFrete {self.destino}>"
