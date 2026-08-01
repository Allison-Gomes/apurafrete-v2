'''
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📁 ARQUIVO : alembic/versions/b1a2c3d4e5f6_cria_rotas_frete.py
📦 MÓDULO  : Alembic / Migrations
🎯 OBJETIVO: Cria a tabela rotas_frete, adicionando a dimensao
             geografica a precificacao de frete SEM alterar
             tabelas_frete nem faixas_frete.
             Adiciona o valor 'sem_rota' ao enum statuscalculonf.

📅 ATUALIZADO: 01/08/2026
   • down_revision corrigido: placeholder -> '266a68ac8352'
     (head real confirmada via SELECT * FROM alembic_version)
   • ALTER TYPE ADD VALUE usa 'sem_rota' MINUSCULO
     (confirmado via \\dT+ statuscalculonf: enum grava VALUE)
   • Removido server_default gen_random_uuid() do id:
     pgcrypto NAO esta instalado (SELECT extname FROM pg_extension
     retornou apenas plpgsql). UUID gerado no Python pelo AuditMixin,
     igual ao padrao de tabelas_frete.
   • ADD VALUE executado em bloco autocommit isolado

📌 REGRAS  : Decisao #72 (Opcao B) | #73 | RN v2.9 secoes 1.8, 5.4, 6.7

⚠️ ATENCAO :
   1. Postgres NAO suporta DROP VALUE em enum. O downgrade
      dropa rotas_frete, mas 'sem_rota' PERMANECE no tipo.
      Isso e inofensivo: nenhuma linha o referenciara apos o drop.
   2. ALTER TYPE ... ADD VALUE nao pode rodar dentro de um bloco
      transacional que depois USE o novo valor. Aqui usamos
      autocommit_block() para garantir o commit imediato.
   3. uq_rota_tabela_uf_cidade e INDICE DE EXPRESSAO com
      coalesce(cidade_normalizada,'*'). Um UNIQUE comum NAO
      detectaria colisao entre dois curingas (NULL != NULL).
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
'''

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# IDENTIFICADORES DA REVISAO
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

revision = 'b1a2c3d4e5f6'
down_revision = '266a68ac8352'
branch_labels = None
depends_on = None


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# UPGRADE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def upgrade() -> None:
    '''
    Etapa 1 — Adiciona 'sem_rota' ao enum statuscalculonf
              (autocommit obrigatorio).
    Etapa 2 — Cria a tabela rotas_frete com 5 checks.
    Etapa 3 — Cria 3 indices btree + 1 indice unico de expressao.
    '''

    # ── ETAPA 1 ─ Enum: novo valor 'sem_rota' (RN v2.9 secao 6.7) ──
    with op.get_context().autocommit_block():
        op.execute(
            "ALTER TYPE statuscalculonf ADD VALUE IF NOT EXISTS 'sem_rota'"
        )

    # ── ETAPA 2 ─ Tabela rotas_frete (RN v2.9 secao 1.8) ──
    op.create_table(
        'rotas_frete',

        # PK — UUID gerado no Python (AuditMixin). Sem server_default:
        # pgcrypto nao instalado neste banco.
        sa.Column(
            'id',
            postgresql.UUID(as_uuid=True),
            nullable=False,
            comment='PK UUID v4 gerada pela aplicacao (AuditMixin)',
        ),

        # FK para a tabela de precos
        sa.Column(
            'tabela_id',
            postgresql.UUID(as_uuid=True),
            nullable=False,
            comment='FK -> tabelas_frete.id (O QUANTO se cobra)',
        ),

        # Dimensao geografica de DESTINO
        sa.Column(
            'uf',
            sa.String(length=2),
            nullable=False,
            comment='UF de destino, maiuscula. Origem NAO participa (Decisao #72)',
        ),
        sa.Column(
            'cidade_normalizada',
            sa.String(length=120),
            nullable=True,
            comment='Cidade normalizada (app/utils/normalizacao.py). NULL = curinga da UF',
        ),

        # Atributos comerciais da rota
        sa.Column(
            'prazo_dias',
            sa.Integer(),
            nullable=True,
            comment='Prazo informativo, copiado para nf.prazo_dias no calculo',
        ),
        sa.Column(
            'valor_minimo_rota',
            sa.Numeric(precision=10, scale=2),
            nullable=True,
            comment='Piso do frete, aplicado APOS a formula progressiva',
        ),

        # AuditMixin
        sa.Column(
            'ativo',
            sa.Boolean(),
            nullable=False,
            server_default=sa.text('true'),
            comment='Soft delete. Somente rotas ativas sao elegiveis',
        ),
        sa.Column(
            'criado_em',
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text('now()'),
            comment='Usado no tie-break do order_by da resolucao de rota',
        ),
        sa.Column(
            'atualizado_em',
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text('now()'),
        ),

        # ── Constraints ──
        sa.PrimaryKeyConstraint('id', name='rotas_frete_pkey'),
        sa.ForeignKeyConstraint(
            ['tabela_id'],
            ['tabelas_frete.id'],
            name='rotas_frete_tabela_id_fkey',
            ondelete='CASCADE',
        ),
        sa.CheckConstraint(
            'char_length(uf) = 2',
            name='ck_rota_uf_tamanho',
        ),
        sa.CheckConstraint(
            'uf = upper(uf)',
            name='ck_rota_uf_maiuscula',
        ),
        sa.CheckConstraint(
            'cidade_normalizada IS NULL '
            'OR cidade_normalizada = upper(cidade_normalizada)',
            name='ck_rota_cidade_maiuscula',
        ),
        sa.CheckConstraint(
            'prazo_dias IS NULL OR prazo_dias >= 0',
            name='ck_rota_prazo_nao_negativo',
        ),
        sa.CheckConstraint(
            'valor_minimo_rota IS NULL OR valor_minimo_rota >= 0',
            name='ck_rota_minimo_nao_negativo',
        ),

        comment='Dimensao geografica do frete: PARA ONDE a tabela e valida (Decisao #72)',
    )

    # ── ETAPA 3 ─ Indices ──
    op.create_index(
        'ix_rotas_frete_tabela_id',
        'rotas_frete',
        ['tabela_id'],
    )
    op.create_index(
        'ix_rotas_frete_uf',
        'rotas_frete',
        ['uf'],
    )
    op.create_index(
        'ix_rotas_frete_cidade_normalizada',
        'rotas_frete',
        ['cidade_normalizada'],
    )

    '''
    Indice UNICO de EXPRESSAO.
    Motivo: em Postgres, NULL != NULL, logo um UNIQUE comum sobre
    (tabela_id, uf, cidade_normalizada) permitiria DOIS curingas
    para a mesma UF/tabela. O coalesce(...,'*') resolve isso.
    Criado via op.execute porque op.create_index nao suporta
    expressoes de forma portavel.
    '''
    op.execute(
        '''
        CREATE UNIQUE INDEX uq_rota_tabela_uf_cidade
        ON rotas_frete (
            tabela_id,
            uf,
            coalesce(cidade_normalizada, '*')
        )
        '''
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# DOWNGRADE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def downgrade() -> None:
    '''
    Dropa rotas_frete (indices caem em cascata com a tabela).

    ⚠️ O valor 'sem_rota' do enum statuscalculonf NAO e removido:
    Postgres nao suporta ALTER TYPE ... DROP VALUE. Remover exigiria
    recriar o tipo e reescrever a coluna em notas_fiscais — risco
    desnecessario. O valor orfao e inofensivo.
    '''
    op.drop_index('uq_rota_tabela_uf_cidade', table_name='rotas_frete')
    op.drop_index('ix_rotas_frete_cidade_normalizada', table_name='rotas_frete')
    op.drop_index('ix_rotas_frete_uf', table_name='rotas_frete')
    op.drop_index('ix_rotas_frete_tabela_id', table_name='rotas_frete')
    op.drop_table('rotas_frete')
