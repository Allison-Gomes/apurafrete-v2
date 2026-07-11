"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📁 ARQUIVO : (nome gerado pelo alembic)
📦 MÓDULO  : Embarque
🎯 OBJETIVO: Adiciona os valores SEM_TABELA e
             SEM_TRANSPORTADORA ao enum PostgreSQL
             'statuscalculonf', usado pela coluna
             status_calculo da tabela notas_fiscais.
             Pré-requisito para a Etapa 3 (Cálculo de
             Frete), conforme REGRAS_DE_NEGOCIO.md v2.3
             - Secao 6.7.
🔗 DEPENDE  : Migration anterior que criou notas_fiscais
📅 CRIADO   : 09/07/2026
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
from alembic import op


# revision identifiers, used by Alembic.
revision = "f3a8c9d2e711"
down_revision = "525c87ab03c2"
branch_labels = None
depends_on = None



def upgrade() -> None:
    '''
    🎯 O QUE FAZ:
        Adiciona os valores 'sem_tabela' e
        'sem_transportadora' ao tipo enum
        'statuscalculonf' no PostgreSQL.

    📐 REGRA DE NEGÓCIO:
        Alteracao aditiva - nao remove nem altera
        valores existentes (pendente, calculado, erro,
        ignorada). Nao afeta dados ja persistidos.

    ⚠️  ATENÇÃO:
        ALTER TYPE ... ADD VALUE precisa rodar fora da
        transacao padrao do Alembic (autocommit_block).
        Nao modificar sem autorizacao de Allison.
    '''
    with op.get_context().autocommit_block():
        op.execute(
            "ALTER TYPE statuscalculonf ADD VALUE IF NOT EXISTS 'sem_tabela'"
        )
        op.execute(
            "ALTER TYPE statuscalculonf ADD VALUE IF NOT EXISTS "
            "'sem_transportadora'"
        )


def downgrade() -> None:
    '''
    🎯 O QUE FAZ:
        Downgrade NAO suportado.

    📐 REGRA DE NEGÓCIO:
        PostgreSQL nao permite remover valores de um
        enum. Reverter exigiria recriar o tipo do zero -
        fora do escopo desta migration (decisao de
        Allison, 09/07/2026).
    '''
    raise NotImplementedError(
        "Downgrade nao suportado: PostgreSQL nao permite "
        "remover valores de ENUM."
    )
