'''
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📁 ARQUIVO : alembic/env.py
📦 MÓDULO  : Infraestrutura / Migrations
🎯 OBJETIVO: Configura o ambiente de execução das
             migrations Alembic para o ApuraFrete.
             Usa engine assíncrona (asyncpg) compatível
             com DATABASE_URL definida em settings, e
             importa todos os models via app.models
             para que o Alembic detecte automaticamente
             o schema (autogenerate).
🔗 DEPENDE  : app.core.config.settings
             app.models (Base + todos os models)
📅 CRIADO  : 02/07/2026
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
'''

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.core.config import settings
from app.models import Base  # noqa: F401 — importa também todos os models registrados no __init__.py

# ─────────────────────────────────────────────────
# Configuração base do Alembic (logging etc.)
# ─────────────────────────────────────────────────
config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ─────────────────────────────────────────────────
# Metadata alvo — usado pelo autogenerate para
# comparar o estado dos models com o banco real
# ─────────────────────────────────────────────────
target_metadata = Base.metadata

# ─────────────────────────────────────────────────
# Injeta a URL do banco vinda do .env (settings),
# sobrescrevendo o que estiver (ou não) no alembic.ini
# ─────────────────────────────────────────────────
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)


def run_migrations_offline() -> None:
    '''
    🎯 O QUE FAZ:
        Executa migrations em modo 'offline' — gera apenas
        o SQL, sem conectar de fato ao banco. Útil para
        revisar scripts antes de aplicar.

    ⚠️ ATENÇÃO:
        Modo raramente usado no dia a dia do ApuraFrete.
        Mantido por padrão do Alembic.
    '''
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    '''
    🎯 O QUE FAZ:
        Recebe uma conexão síncrona (via run_sync) e
        executa de fato as migrations configuradas.

    📥 PARÂMETROS:
        connection (Connection): conexão ativa fornecida
        pelo engine assíncrono via run_sync
    '''
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    '''
    🎯 O QUE FAZ:
        Executa migrations em modo 'online' (conectando
        de fato ao banco PostgreSQL via asyncpg), conforme
        exigido pela DATABASE_URL assíncrona do projeto.

    📐 REGRA DE NEGÓCIO:
        - Usa async_engine_from_config pois settings.DATABASE_URL
          é postgresql+asyncpg://...
        - A conexão async é adaptada para o Alembic (que é
          sincrono internamente) via connection.run_sync()

    ⚠️ ATENÇÃO:
        Não trocar para engine síncrono sem autorização de
        Allison — quebraria compatibilidade com asyncpg.
    '''
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
