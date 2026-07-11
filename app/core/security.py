'''
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📁 ARQUIVO : app/core/security.py
📦 MÓDULO  : Core / Segurança
🎯 OBJETIVO: Centraliza toda a lógica de segurança
             do sistema: hashing de senha, geração
             e decodificação de JWT (access token).
🔗 DEPENDE  : app/core/config.py (settings.SECRET_KEY,
                                  settings.ALGORITHM,
                                  settings.ACCESS_TOKEN_EXPIRE_MINUTES)
             python-jose[cryptography]
             passlib[bcrypt]
📅 CRIADO  : 24/06/2026
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
'''

from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings


# ─────────────────────────────────────────────────
# 🔒 CONTEXTO DE HASH — bcrypt
# ─────────────────────────────────────────────────
pwd_context = CryptContext(schemes=['bcrypt'], deprecated='auto')
'''
⚠️  ATENÇÃO:
    Algoritmo fixado em bcrypt.
    Não alterar sem autorização de Allison.
'''


# ─────────────────────────────────────────────────
# 🔑 FUNÇÕES DE SENHA
# ─────────────────────────────────────────────────
def hash_senha(senha_plana: str) -> str:
    '''
    🎯 O QUE FAZ:
        Gera o hash bcrypt de uma senha em texto plano.

    📐 REGRA DE NEGÓCIO:
        - Nunca armazenar senha em texto plano no banco.
        - Usar esta função SEMPRE antes de persistir
          um novo usuário ou ao alterar senha.

    📥 PARÂMETROS:
        senha_plana (str): Senha em texto plano

    📤 RETORNO:
        str: Hash bcrypt da senha

    ⚠️  ATENÇÃO:
        Não modificar sem autorização de Allison.
    '''
    return pwd_context.hash(senha_plana)


def verificar_senha(senha_plana: str, hash_armazenado: str) -> bool:
    '''
    🎯 O QUE FAZ:
        Compara uma senha em texto plano com o hash
        armazenado no banco de dados.

    📐 REGRA DE NEGÓCIO:
        - Retorna True apenas se a senha corresponder
          ao hash armazenado.
        - Retorna False em qualquer outro caso,
          sem lançar exceção.

    📥 PARÂMETROS:
        senha_plana      (str): Senha informada pelo usuário
        hash_armazenado  (str): Hash bcrypt do banco de dados

    📤 RETORNO:
        bool: True se válida, False se inválida

    ⚠️  ATENÇÃO:
        Não modificar sem autorização de Allison.
    '''
    return pwd_context.verify(senha_plana, hash_armazenado)


# ─────────────────────────────────────────────────
# 🪙 FUNÇÕES DE JWT
# ─────────────────────────────────────────────────
def criar_access_token(
    data: dict[str, Any],
    expires_delta: timedelta | None = None,
) -> str:
    '''
    🎯 O QUE FAZ:
        Gera um JWT assinado com as informações do
        usuário autenticado.

    📐 REGRA DE NEGÓCIO:
        - O campo "sub" deve conter o ID do usuário
          como string.
        - O campo "exp" é calculado automaticamente
          com base em ACCESS_TOKEN_EXPIRE_MINUTES
          ou no expires_delta informado.
        - Timezone sempre UTC para consistência.

    📥 PARÂMETROS:
        data          (dict)     : Payload do token.
                                   Obrigatório: {"sub": str(usuario.id)}
        expires_delta (timedelta): Tempo de expiração customizado.
                                   Se None, usa o valor de settings.

    📤 RETORNO:
        str: JWT assinado em formato Bearer

    ⚠️  ATENÇÃO:
        Não incluir dados sensíveis (senha, CPF, etc.)
        no payload do token.
        Não modificar sem autorização de Allison.
    '''
    payload = data.copy()

    expira_em = datetime.now(timezone.utc) + (
        expires_delta
        if expires_delta
        else timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )

    payload.update({'exp': expira_em})

    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any] | None:
    '''
    🎯 O QUE FAZ:
        Decodifica e valida um JWT.
        Retorna o payload se válido, None se inválido
        ou expirado.

    📐 REGRA DE NEGÓCIO:
        - Token expirado → retorna None (sem exceção)
        - Token malformado → retorna None (sem exceção)
        - A exceção é responsabilidade de get_usuario_atual
          em app/core/deps.py, que lança 401.

    📥 PARÂMETROS:
        token (str): JWT recebido no header Authorization

    📤 RETORNO:
        dict[str, Any] | None: Payload decodificado ou None

    ⚠️  ATENÇÃO:
        Não lançar HTTPException aqui.
        Esta função é utilitária — agnóstica ao FastAPI.
        Não modificar sem autorização de Allison.
    '''
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
        )
        return payload
    except JWTError:
        return None


'''
O que testar/validar:
    - hash_senha('123456') → retorna hash bcrypt
    - verificar_senha('123456', hash) → True
    - verificar_senha('errada', hash) → False
    - criar_access_token({'sub': '1'}) → JWT válido
    - decode_access_token(token_valido) → dict com sub
    - decode_access_token('token_invalido') → None
    - decode_access_token(token_expirado) → None

Pontos de atenção:
    - Depende de settings.SECRET_KEY (deve ser longa
      e aleatória — nunca hardcoded)
    - Depende de settings.ALGORITHM (ex: 'HS256')
    - Depende de settings.ACCESS_TOKEN_EXPIRE_MINUTES
    - Instalar: pip install python-jose[cryptography] passlib[bcrypt]
'''
