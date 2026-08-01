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
              app/utils/normalizacao.py (properties de rota)
📅 CRIADO   : 24/06/2026
📅 ATUALIZADO: 28/07/2026 — Decisão #75 (revisada).
               O revert do commit 6428d13 foi ABANDONADO:
               inspeção do banco (\\d notas_fiscais) provou que
               a desnormalização nunca chegou ao Postgres.
               Model realinhado ao schema REAL do banco:
                 - origem/destino desnormalizados NOT NULL
                   (cliente_*, cnpj_*, cidade_*, uf_*);
                 - SEM empresa_id / remetente_id / destinatario_id
                   (tenant herdado via embarques.empresa_id);
                 - qtd_cx e peso_total_kg (nomes canônicos);
                 - apenas as constraints que existem no banco.
📅 ATUALIZADO: 28/07/2026 — Opção B (RotaFrete):
                 - novo status SEM_ROTA no enum StatusCalculoNF
                   (exige ALTER TYPE na migration b1a2c3d4e5f6);
                 - properties de leitura: destino_normalizado,
                   entra_no_calculo, calculo_concluido;
                 - documentado que peso_total_kg é o ÚNICO nome
                   canônico do peso (não existe peso_real_kg
                   nesta tabela — ele vive em produtos).
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
'''

from __future__ import annotations

import enum

from sqlalchemy import (
    CheckConstraint, Column, Date, Enum, ForeignKey,
    Integer, Numeric, String, Text, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.models.base import AuditMixin, Base
from app.utils.normalizacao import normalizar_cidade, normalizar_uf


# ── ENUM: StatusCalculoNF ────────────────────────
class StatusCalculoNF(str, enum.Enum):
    '''
    🎯 O QUE FAZ:
        Enumera os estados do cálculo de frete de cada NF.

    📐 REGRA DE NEGÓCIO (MVP v2.8 — Seção 6.7):
        PENDENTE            → NF importada, aguardando cálculo
                              (estado inicial).
        CALCULADO           → Frete calculado com sucesso.
                              valor_calculado + snapshot preenchidos.
        SEM_ROTA            → 🆕 Nenhuma RotaFrete ativa da
                              transportadora atende o destino
                              (uf_destino/cidade_destino). Nem
                              rota específica, nem curinga da UF.
        SEM_TABELA          → A rota existe, mas a transportadora
                              não tem tabela com tabela_ativa=True
                              vinculada a ela (§6.3).
        SEM_TRANSPORTADORA  → Nenhuma transportadora selecionada
                              manualmente para esta NF.
        ERRO                → Falha genérica (peso, destino ou
                              faixas inválidas). Motivo em
                              erro_calculo.
        IGNORADA            → NF marcada para exclusão lógica.
                              Não entra em cálculo nem auditoria.

    📐 DISTINÇÃO SEM_ROTA vs SEM_TABELA:
        SEM_ROTA   → problema de COBERTURA geográfica.
                     Ação: cadastrar a rota (UF ou cidade).
        SEM_TABELA → problema de VIGÊNCIA da precificação.
                     Ação: ativar a tabela da transportadora.

    ⚠️  ATENÇÃO:
        Os 6 valores originais estão persistidos desde a
        migration 28aaa21c70c2 (09/07/2026 — Decisão #43).
        SEM_ROTA foi adicionado em 28/07/2026 e EXIGE:
            ALTER TYPE statuscalculonf
            ADD VALUE IF NOT EXISTS 'SEM_ROTA';
        PostgreSQL NÃO suporta remoção de valor de enum.
        Não modificar sem autorização de Allison.
    '''
    PENDENTE           = "pendente"
    CALCULADO          = "calculado"
    SEM_ROTA           = "sem_rota"            # 🆕 28/07/2026
    SEM_TABELA         = "sem_tabela"
    SEM_TRANSPORTADORA = "sem_transportadora"
    ERRO               = "erro"
    IGNORADA           = "ignorada"


# ─────────────────────────────────────────────────
# 🔎 CONJUNTOS DE STATUS
# Usados pelos services e repositories para evitar
# comparações soltas espalhadas pelo código.
# ─────────────────────────────────────────────────
STATUS_CALCULAVEIS = frozenset({
    StatusCalculoNF.PENDENTE,
    StatusCalculoNF.CALCULADO,
    StatusCalculoNF.SEM_ROTA,
    StatusCalculoNF.SEM_TABELA,
    StatusCalculoNF.SEM_TRANSPORTADORA,
    StatusCalculoNF.ERRO,
})
'''
🎯 Status que PERMITEM (re)cálculo de frete.
   IGNORADA está deliberadamente fora: NF ignorada
   nunca deve ser recalculada nem auditada.
'''

STATUS_PENDENTES_DE_ACAO = frozenset({
    StatusCalculoNF.PENDENTE,
    StatusCalculoNF.SEM_ROTA,
    StatusCalculoNF.SEM_TABELA,
    StatusCalculoNF.SEM_TRANSPORTADORA,
    StatusCalculoNF.ERRO,
})
'''
🎯 Status que BLOQUEIAM o fechamento do embarque.
   Toda NF precisa estar CALCULADO ou IGNORADA
   antes da exportação.
'''


# ── MODEL: NotaFiscal ────────────────────────────
class NotaFiscal(Base, AuditMixin):
    '''
    🎯 O QUE FAZ:
        Representa uma nota fiscal importada em um embarque.

    📐 REGRAS (MVP v2.8):
        - O tenant é herdado via embarque.empresa_id. A NF NÃO
          possui empresa_id próprio — todo filtro multi-tenant
          deve passar por JOIN em embarques (§1.4).
        - Vinculada a exatamente 1 Embarque (ondelete=CASCADE).
        - Remetente e destinatário ficam DESNORMALIZADOS aqui
          (cliente_*, cnpj_*, cidade_*, uf_*). Não há FK para
          empresas: a planilha é a fonte da verdade da rota e o
          model Empresa não possui campos de endereço.
        - `cidade_*_raw` preserva o texto original da planilha
          ("CIDADE - UF ..."), de onde cidade_* e uf_* são
          derivados na importação (§4.2).
        - Chave de deduplicação operacional:
          (embarque_id, numero_nf, serie_nf) — uq_nf_embarque_numero_serie.
        - Peso total derivado do catálogo:
          peso_total_kg = qtd_cx × produto.peso_real_kg (§3.1).
          Não há cubagem — apenas peso real (Decisão #28, Opção B).

    📐 RESOLUÇÃO DE ROTA (🆕 Opção B — 28/07/2026):
        O par (uf_destino, cidade_destino) é a chave que o engine
        usa para localizar a RotaFrete da transportadora:
          1. rota com cidade_normalizada = normalizar_cidade(cidade_destino)
          2. rota curinga da UF (cidade_normalizada IS NULL)
          3. nenhuma → status_calculo = SEM_ROTA
        A normalização acontece em RUNTIME (não há coluna
        cidade_destino_normalizada). Ver property
        destino_normalizado.

    📐 FÓRMULA DE FRETE (§6.4):
        Se peso_total_kg ≤ 30:
          frete = preco_ate_30kg
        Se peso_total_kg > 30:
          frete = preco_ate_30kg +
                  (peso_total_kg − 30) × valor_kg_adicional
        Depois: frete = max(frete, rota.valor_minimo_rota)

    📐 SNAPSHOT PARA AUDITORIA (§6.6):
        preco_ate_30kg_usado, valor_kg_adicional_usado,
        peso_kg_usado — congelam a precificação no instante
        do cálculo, permitindo auditar o CT-e mesmo após a
        tabela mudar.

    🗂️  TABELA: notas_fiscais

    ⚠️  ATENÇÃO:
        Este model reflete 1:1 o schema físico do banco.
        O peso desta tabela chama-se peso_total_kg — NÃO
        existe peso_real_kg aqui (esse nome pertence ao
        catálogo de produtos).
        Lógica de cálculo em services/calculo_frete_service.py.
        Não modificar sem autorização de Allison.
    '''

    __tablename__ = "notas_fiscais"

    # ── Vínculo com Embarque (portador do tenant) ─
    embarque_id = Column(
        UUID(as_uuid=True),
        ForeignKey("embarques.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Embarque ao qual esta NF pertence. "
                "Portador do tenant (embarques.empresa_id).",
    )

    # ── Identificação da NF ──────────────────────
    numero_nf = Column(
        String(50),
        nullable=False,
        comment="Número do documento/NF. "
                "Origem: coluna DOCUMENTO da planilha (Seção 4.1).",
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

    # ── Remetente / ORIGEM (§4.1 col. 6-9 | §6.2) ─
    cod_remetente = Column(
        String(50),
        nullable=False,
        comment="Código do remetente. "
                "Origem: coluna COD REMETENTE (Seção 4.1).",
    )

    cliente_remetente = Column(
        String(200),
        nullable=False,
        comment="Razão social do remetente. "
                "Origem: coluna CLIENTE REMETENTE (Seção 4.1).",
    )

    cnpj_remetente = Column(
        String(14),
        nullable=False,
        comment="CNPJ do remetente, somente dígitos (14). "
                "Origem: coluna CNPJ REMETENTE (Seção 4.1).",
    )

    cidade_remetente = Column(
        String(100),
        nullable=False,
        comment="Cidade de origem, derivada de cidade_remetente_raw. "
                "Informativa no MVP: a rota é resolvida apenas "
                "pelo DESTINO (Seção 5.4 / 6.2).",
    )

    uf_remetente = Column(
        String(2),
        nullable=False,
        comment="UF de origem (2 letras), derivada de "
                "cidade_remetente_raw. Informativa no MVP.",
    )

    cidade_remetente_raw = Column(
        String(200),
        nullable=True,
        comment="Valor original da coluna 'CIDADE - UF REMETENTE', "
                "preservado como veio na planilha (Seção 4.2).",
    )

    # ── Destinatário / DESTINO (§4.1 col. 2-5) ────
    cod_cliente = Column(
        String(50),
        nullable=False,
        comment="Código do cliente destino. "
                "Origem: coluna COD CLIENTE (Seção 4.1).",
    )

    cliente_destino = Column(
        String(200),
        nullable=False,
        comment="Razão social do destinatário. "
                "Origem: coluna CLIENTE DESTINO (Seção 4.1).",
    )

    cnpj_destino = Column(
        String(14),
        nullable=False,
        comment="CNPJ do destinatário, somente dígitos (14). "
                "Origem: coluna CNPJ DESTINO (Seção 4.1).",
    )

    cidade_destino = Column(
        String(100),
        nullable=False,
        comment="Cidade de destino, derivada de cidade_destino_raw. "
                "CHAVE DE ROTA: casada contra "
                "rotas_frete.cidade_normalizada (Seção 5.4 / 6.2).",
    )

    uf_destino = Column(
        String(2),
        nullable=False,
        comment="UF de destino (2 letras), derivada de "
                "cidade_destino_raw. CHAVE DE ROTA obrigatória: "
                "casada contra rotas_frete.uf (Seção 5.4).",
    )

    cidade_destino_raw = Column(
        String(200),
        nullable=True,
        comment="Valor original da coluna 'CIDADE - UF DESTINO', "
                "preservado como veio na planilha (Seção 4.2).",
    )

    # ── Produto e Quantidade ─────────────────────
    cod_produto = Column(
        String(100),
        nullable=False,
        comment="SKU do produto (catálogo). "
                "Origem: coluna COD PRODUTO. "
                "Deve existir no cadastro (Seção 1.2).",
    )

    qtd_cx = Column(
        Integer,
        nullable=False,
        comment="Quantidade de caixas/volumes. "
                "Origem: coluna QTD CX. Deve ser ≥ 1 (Seção 4.2).",
    )

    # ── Peso (derivado do catálogo — §3.1) ───────
    peso_total_kg = Column(
        Numeric(10, 3),
        nullable=False,
        comment="Peso total da NF em kg. NOME CANÔNICO — não "
                "existe peso_real_kg nesta tabela. "
                "Fórmula: qtd_cx × produto.peso_real_kg "
                "(Seção 3.1 / 4.3). "
                "Armazenado para auditoria e reprocessabilidade.",
    )

    # ── Dados Fiscais ────────────────────────────
    nf_valor = Column(
        Numeric(14, 2),
        nullable=True,
        comment="Valor total da nota fiscal em R$ (informativo).",
    )

    # ── Transportadora (§1.3 e §6.1) ─────────────
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
                "(fórmula da Seção 6.4, já com piso da rota).",
    )

    prazo_dias = Column(
        Integer,
        nullable=True,
        comment="Prazo de entrega em dias, copiado de "
                "rotas_frete.prazo_dias no cálculo "
                "(informativo — Seção 7.2).",
    )

    # ── Snapshot para Auditoria (§6.6) ───────────
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
                "(= peso_total_kg no momento do cálculo).",
    )

    # ── Status e Rastreabilidade ─────────────────
    status_calculo = Column(
        Enum(StatusCalculoNF),
        nullable=False,
        default=StatusCalculoNF.PENDENTE,
        index=True,
        comment="Status do cálculo de frete (Seção 6.7). "
                "Nasce como 'pendente' após importação válida.",
    )

    erro_calculo = Column(
        Text,
        nullable=True,
        comment="Descrição do erro. Preenchido nos status "
                "ERRO, SEM_ROTA, SEM_TABELA e SEM_TRANSPORTADORA.",
    )

    # ── Campos Opcionais da Planilha (§4.1) ──────
    observacao = Column(
        Text,
        nullable=True,
        comment="Campo livre, sem validação. "
                "Origem: coluna OBSERVAÇÃO (Seção 4.1).",
    )

    centro_custo = Column(
        Text,
        nullable=True,
        comment="Campo livre, sem validação. "
                "Origem: coluna CENTRO DE CUSTO (Seção 4.1).",
    )

    # ── Relacionamentos ──────────────────────────
    # Não há FK para "empresas": o tenant é alcançado por
    # nota_fiscal.embarque.empresa_id (sem ambiguidade de mapper).
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
    # ⚠️ Espelham EXATAMENTE o que existe no banco. Checks de
    #    qtd_cx / peso_total_kg / valor_calculado / prazo_dias
    #    NÃO existem fisicamente — se forem desejados, exigem
    #    migration própria. Declará-los aqui sem criá-los faria
    #    o `alembic check` acusar drift permanente.
    __table_args__ = (
        UniqueConstraint(
            "embarque_id",
            "numero_nf",
            "serie_nf",
            name="uq_nf_embarque_numero_serie",
        ),
        CheckConstraint(
            "nf_valor >= 0",
            name="ck_nf_valor_nao_negativo",
        ),
    )

    # ─────────────────────────────────────────────
    # 🔎 PROPERTIES DE LEITURA
    # Somente cálculo em memória — nunca acessam o banco.
    # ─────────────────────────────────────────────

    @property
    def destino_normalizado(self) -> tuple[str | None, str | None]:
        '''
        🎯 O QUE FAZ:
            Retorna o par (uf, cidade) normalizado do destino,
            pronto para casar com rotas_frete.

        📐 REGRA DE NEGÓCIO:
            Usa app.utils.normalizacao — a MESMA função aplicada
            ao gravar rotas_frete.cidade_normalizada. Divergir
            daqui quebra a resolução de rota silenciosamente.

        📤 RETORNO:
            tuple[str | None, str | None]:
              Ex: ('SP', 'SAO JOSE DOS CAMPOS')
        '''
        return (
            normalizar_uf(self.uf_destino),
            normalizar_cidade(self.cidade_destino),
        )

    @property
    def rota_label(self) -> str:
        '''
        🎯 O QUE FAZ:
            Monta o rótulo legível do destino para logs,
            mensagens de erro e telas de revisão.

        📤 RETORNO:
            str: Ex: 'SP/CAMPINAS'
        '''
        uf, cidade = self.destino_normalizado
        return f"{uf or '??'}/{cidade or '*'}"

    @property
    def entra_no_calculo(self) -> bool:
        '''
        🎯 O QUE FAZ:
            Indica se esta NF deve participar do cálculo
            de frete em lote.

        📐 REGRA DE NEGÓCIO:
            NFs com status IGNORADA são excluídas do cálculo
            e da auditoria de CT-e.

        📤 RETORNO:
            bool
        '''
        return self.status_calculo in STATUS_CALCULAVEIS

    @property
    def calculo_concluido(self) -> bool:
        '''
        🎯 O QUE FAZ:
            Indica se a NF já está resolvida do ponto de vista
            operacional, liberando o fechamento do embarque.

        📐 REGRA DE NEGÓCIO:
            Resolvida = CALCULADO (com valor) ou IGNORADA.

        📤 RETORNO:
            bool
        '''
        if self.status_calculo == StatusCalculoNF.IGNORADA:
            return True
        return (
            self.status_calculo == StatusCalculoNF.CALCULADO
            and self.valor_calculado is not None
        )

    # ── Representação ────────────────────────────
    def __repr__(self):
        '''
        🎯 O QUE FAZ:
            Retorna representação legível da NotaFiscal
            para logs e debugging.

        📤 RETORNO:
            str: Ex: <NotaFiscal NF-12345 | SP/CAMPINAS |
                      SKU=ABC | 45.000kg | calculado>
        '''
        status = getattr(self.status_calculo, "value", self.status_calculo)
        return (
            f"<NotaFiscal NF-{self.numero_nf} | "
            f"{self.rota_label} | "
            f"SKU={self.cod_produto} | "
            f"{self.peso_total_kg}kg | "
            f"{status}>"
        )
