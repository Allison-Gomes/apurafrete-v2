'''
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ARQUIVO : e5a1c9f4b7d2_add_ativo_transportadoras.py
MÓDULO  : Cadastros / Transportadoras
OBJETIVO: Adicionar coluna 'ativo' na tabela transportadoras
DEPENDE  : d3df23d1bb95 (initial schema)
CRIADO  : 04/07/2026
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
'''
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'e5a1c9f4b7d2'
down_revision = 'd3df23d1bb95'
branch_labels = None
depends_on = None


def upgrade() -> None:
    '''
    🎯 O QUE FAZ:
        Adiciona a coluna 'ativo' (booleana) na tabela 'transportadoras',
        com valor padrão TRUE para não quebrar registros já existentes.

    📐 REGRA DE NEGÓCIO:
        - Toda transportadora criada passa a ter status ativo/inativo
        - Registros já existentes recebem ativo=TRUE por padrão

    ⚠️ ATENÇÃO:
        Não remover o server_default sem migrar os dados antes.
    '''
    op.add_column(
        'transportadoras',
        sa.Column(
            'ativo',
            sa.Boolean(),
            nullable=False,
            server_default=sa.text('true'),
        ),
    )


def downgrade() -> None:
    '''
    🎯 O QUE FAZ:
        Remove a coluna 'ativo' da tabela 'transportadoras'.

    ⚠️ ATENÇÃO:
        Operação destrutiva — dados de ativo/inativo serão perdidos.
    '''
    op.drop_column('transportadoras', 'ativo')
