'''
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📁 ARQUIVO : app/core/database.py
📦 MÓDULO  : Core / Infraestrutura
🎯 OBJETIVO: Configura a conexão assíncrona com o
             banco de dados PostgreSQL via SQLAlchemy.
             Expõe a engine, a session factory e a
             dependência get_db para injeção nas
             rotas FastAPI via Depends().
🔗 DEPENDE  : app/core/config.py (settings.DATABASE_URL,
                                  settings.DB_ECHO)
             app/models/base.py  (Base.metadata)
📅 CRIADO  : 24/06/2026
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
'''

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.core.config import settings


# ─────────────────────────────────────────────────
# ⚙️  ENGINE ASSÍNCRONA
# ─────────────────────────────────────────────────
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DB_ECHO,      # True apenas em desenvolvimento
    pool_pre_ping=True,         # Verifica a conexão antes de usar
    poolclass=NullPool,         # Recomendado para Alembic e workers
)
'''
⚠️  ATENÇÃO:
    NullPool desativa o pool de conexões persistentes.
    Em produção com alta concorrência, avaliar troca
    para AsyncAdaptedQueuePool com pool_size adequado.
    Não alterar sem autorização de Allison.
'''


# ─────────────────────────────────────────────────
# ⚙️  SESSION FACTORY
# ─────────────────────────────────────────────────
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,     # Evita DetachedInstanceError após commit
    autocommit=False,
    autoflush=False,
)
'''
⚠️  ATENÇÃO:
    expire_on_commit=False é essencial para evitar erros
    ao acessar atributos do model após o commit dentro
    de uma rota async.
    Não alterar sem autorização de Allison.
'''


# ─────────────────────────────────────────────────
# 🔌 DEPENDÊNCIA: get_db
# Injeção de sessão nas rotas FastAPI via Depends()
# ─────────────────────────────────────────────────
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    '''
    🎯 O QUE FAZ:
        Abre uma sessão assíncrona com o banco de dados
        e a injeta nas rotas FastAPI via Depends().
        Garante fechamento correto ao final de cada
        requisição, mesmo em caso de exceção.

    📐 REGRA DE NEGÓCIO:
        - Cada requisição recebe sua própria sessão isolada.
        - O commit deve ser feito explicitamente no service
          ou rota responsável pela operação.
        - O rollback é executado automaticamente em caso
          de exceção não tratada.

    📤 RETORNO:
        AsyncGenerator[AsyncSession, None]: Sessão ativa
        do SQLAlchemy, liberada ao final da requisição.

    📋 USO NAS ROTAS:
        from fastapi import Depends
        from sqlalchemy.ext.asyncio import AsyncSession
        from app.core.database import get_db

        @router.get('/exemplo')
        async def exemplo(db: AsyncSession = Depends(get_db)):
            ...

    ⚠️  ATENÇÃO:
        Nunca instanciar AsyncSessionLocal diretamente
        nas rotas. Sempre usar Depends(get_db).
        Não modificar sem autorização de Allison.
    '''
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# ─────────────────────────────────────────────────
# 🏗️  UTILITÁRIO: create_tables
# Exclusivo para desenvolvimento e testes.
# Em produção usar SOMENTE Alembic.
# ─────────────────────────────────────────────────
async def create_tables() -> None:
    '''
    🎯 O QUE FAZ:
        Cria todas as tabelas registradas no metadata
        do SQLAlchemy. Uso restrito a desenvolvimento
        e testes automatizados.

    📐 REGRA DE NEGÓCIO:
        - NÃO usar em produção.
        - Em produção todas as migrações devem ser
          executadas exclusivamente via Alembic.
        - Requer que todos os models estejam importados
          via app/models/__init__.py antes da chamada.

    ⚠️  ATENÇÃO:
        Uso exclusivo em dev/testes.
        Não modificar sem autorização de Allison.
    '''
    import app.models  # noqa: F401 — garante registro no metadata

    from app.models.base import Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


'''
O que testar/validar:
    - Importar o módulo sem erros: from app.core.database import get_db
    - Verificar se settings.DATABASE_URL está
      definido em app/core/config.py
    - Verificar se settings.DB_ECHO está definido

Pontos de atenção:
    - NullPool ativo — adequado para dev e Alembic
    - expire_on_commit=False — obrigatório para async
'''
