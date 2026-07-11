'''
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📁 ARQUIVO : app/core/config.py
📦 MÓDULO  : Core / Configuração
🎯 OBJETIVO: Centraliza todas as variáveis de ambiente
             do sistema via Pydantic BaseSettings.
             Garante validação automática na inicialização
             da aplicação — falha rápido se algo estiver
             mal configurado.
🔗 DEPENDE  : pydantic-settings
             arquivo .env na raiz do projeto
📅 CRIADO  : 24/06/2026
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
'''

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    '''
    🎯 O QUE FAZ:
        Lê e valida todas as variáveis de ambiente
        necessárias para o funcionamento do ApuraFrete.
        Qualquer variável ausente ou com tipo inválido
        causa erro na inicialização — comportamento
        intencional (fail fast).

    📐 REGRA DE NEGÓCIO:
        - Todas as variáveis sensíveis (SECRET_KEY,
          DATABASE_URL) devem estar no .env.
        - O .env NUNCA deve ser versionado no git.
        - Em produção, usar variáveis de ambiente
          reais (não .env).

    ⚠️  ATENÇÃO:
        Não adicionar valores default para variáveis
        sensíveis como SECRET_KEY e DATABASE_URL.
        Não modificar sem autorização de Allison.
    '''

    model_config = SettingsConfigDict(
        env_file='.env',
        env_file_encoding='utf-8',
        case_sensitive=False,
    )

    # ─────────────────────────────────────────────
    # 🗄️  BANCO DE DADOS
    # ─────────────────────────────────────────────
    DATABASE_URL: str
    '''
    Formato esperado (PostgreSQL assíncrono):
    postgresql+asyncpg://usuario:senha@host:porta/nome_banco

    Exemplo .env:
    DATABASE_URL=postgresql+asyncpg://apura:senha123@localhost:5432/apurafrete
    '''

    DB_ECHO: bool = False
    '''
    Ativa o log SQL no console (echo=True do SQLAlchemy).
    Padrão: False.
    Em desenvolvimento, definir DB_ECHO=True no .env
    para visualizar todas as queries executadas.
    Em staging/produção manter False.
    '''

    # ─────────────────────────────────────────────
    # 🔐 JWT / AUTENTICAÇÃO
    # ─────────────────────────────────────────────
    SECRET_KEY: str
    '''
    Chave secreta para assinar os tokens JWT.
    Gerar com: openssl rand -hex 32
    Nunca reutilizar entre ambientes (dev/staging/prod).
    '''

    ALGORITHM: str = 'HS256'
    '''
    Algoritmo de assinatura do JWT.
    Padrão: HS256.
    Não alterar sem autorização de Allison.
    '''

    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480
    '''
    Tempo de expiração do access token em minutos.
    Padrão: 480 min (8 horas) — jornada de trabalho.
    Ajustar conforme política de segurança definida
    por Allison.
    '''

    # ─────────────────────────────────────────────
    # 🌍 AMBIENTE
    # ─────────────────────────────────────────────
    ENVIRONMENT: str = 'development'
    '''
    Valores válidos: development | staging | production
    Controla comportamentos como:
    - Exibição de erros detalhados
    - Criação automática de tabelas (apenas development)
    - Logs verbosos
    '''

    DEBUG: bool = False
    '''
    Ativa modo debug do FastAPI/Uvicorn.
    Nunca True em produção.
    '''

    # ─────────────────────────────────────────────
    # 🏢 APLICAÇÃO
    # ─────────────────────────────────────────────
    APP_NAME: str = 'ApuraFrete'
    APP_VERSION: str = '1.0.0'
    API_PREFIX: str = '/api/v1'

    # ─────────────────────────────────────────────
    # 🌐 CORS
    # ─────────────────────────────────────────────
    CORS_ORIGINS: list[str] = ['http://localhost:3000']
    '''
    Lista de origens permitidas para CORS.
    Em produção, substituir pelo domínio real do frontend.

    Exemplo .env:
    CORS_ORIGINS=["https://apurafrete.com.br","https://app.apurafrete.com.br"]
    '''


# ─────────────────────────────────────────────────
# ✅ INSTÂNCIA GLOBAL
# Importar em todo o projeto via:
#   from app.core.config import settings
# ─────────────────────────────────────────────────
settings = Settings()
