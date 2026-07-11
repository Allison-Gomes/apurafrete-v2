"""fix_statuscalculonf_enum_case

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📁 ARQUIVO : 28aaa21c70c2_fix_statuscalculonf_enum_case.py
📦 MÓDULO  : Notas Fiscais / Cálculo de Frete
🎯 OBJETIVO: Corrigir divergência de case entre os valores do
             enum PostgreSQL 'statuscalculonf' e o .value definido
             na classe Python StatusCalculoNF. Os valores
             PENDENTE, CALCULADO, ERRO, IGNORADA estavam em
             maiúsculo no banco, mas em minúsculo no Python
             (pendente, calculado, erro, ignorada), o que geraria
             erro de "invalid input value for enum" em runtime.
🔗 DEPENDE  : f3a8c9d2e711 (revisão anterior)
📅 CRIADO  : 09/07/2026

Revision ID: 28aaa21c70c2
Revises: f3a8c9d2e711
Create Date: 2026-07-09 13:32:54.621979

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '28aaa21c70c2'
down_revision: Union[str, None] = 'f3a8c9d2e711'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    🎯 O QUE FAZ:
        Renomeia os 4 valores do enum 'statuscalculonf' que estavam
        em maiúsculo (herdados do schema inicial) para minúsculo,
        alinhando com o .value da classe Python StatusCalculoNF.

    ⚠️  ATENÇÃO:
        Executado fora de bloco transacional (autocommit) por
        exigência do PostgreSQL para alteração de tipos ENUM.
        Tabela notas_fiscais estava vazia no momento da criação
        desta migration — sem risco de perda de dados.
    """
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE statuscalculonf RENAME VALUE 'PENDENTE' TO 'pendente'")
        op.execute("ALTER TYPE statuscalculonf RENAME VALUE 'CALCULADO' TO 'calculado'")
        op.execute("ALTER TYPE statuscalculonf RENAME VALUE 'ERRO' TO 'erro'")
        op.execute("ALTER TYPE statuscalculonf RENAME VALUE 'IGNORADA' TO 'ignorada'")


def downgrade() -> None:
    """
    🎯 O QUE FAZ:
        Reverte os valores do enum 'statuscalculonf' de volta para
        maiúsculo, restaurando o estado original do schema inicial.

    ⚠️  ATENÇÃO:
        Reversão simétrica ao upgrade(). Só deve ser usada em
        rollback controlado.
    """
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE statuscalculonf RENAME VALUE 'pendente' TO 'PENDENTE'")
        op.execute("ALTER TYPE statuscalculonf RENAME VALUE 'calculado' TO 'CALCULADO'")
        op.execute("ALTER TYPE statuscalculonf RENAME VALUE 'erro' TO 'ERRO'")
        op.execute("ALTER TYPE statuscalculonf RENAME VALUE 'ignorada' TO 'IGNORADA'")
