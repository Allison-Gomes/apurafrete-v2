'''
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📁 ARQUIVO : app/core/deps.py
📦 MÓDULO  : Core / Infraestrutura
🎯 OBJETIVO: Centraliza as dependências reutilizáveis
             do FastAPI via Depends().
             Expõe: sessão de banco, usuário autenticado
             e verificação de permissões (RBAC).
🔗 DEPENDE  : app/core/database.py  (get_db)
             app/core/security.py   (decode_access_token)
             app/models/usuario.py  (Usuario)
             app/core/config.py     (settings)
📅 CRIADO  : 24/06/2026
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
'''

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.database import get_db
from app.core.security import decode_access_token
from app.models.usuario import Usuario

# ─────────────────────────────────────────────────
# 🔐 ESQUEMA OAuth2
# ─────────────────────────────────────────────────
oauth2_scheme = OAuth2PasswordBearer(tokenUrl='/api/v1/auth/login')
'''
⚠️  ATENÇÃO:
    tokenUrl deve coincidir com a rota de login definida
    em app/api/v1/rotas/auth.py.
    Não alterar sem autorização de Allison.
'''


# ─────────────────────────────────────────────────
# 👤 DEPENDÊNCIA: get_usuario_atual
# ─────────────────────────────────────────────────
async def get_usuario_atual(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> Usuario:
    '''
    🎯 O QUE FAZ:
        Decodifica o JWT recebido no header Authorization,
        valida o payload e retorna o usuário autenticado.

    📐 REGRA DE NEGÓCIO:
        - Token inválido ou expirado → 401 Unauthorized
        - Usuário não encontrado no banco → 401 Unauthorized
        - Usuário inativo (ativo=False) → 403 Forbidden

    📥 PARÂMETROS:
        token (str)          : JWT extraído pelo oauth2_scheme
        db    (AsyncSession) : Sessão injetada via get_db

    📤 RETORNO:
        Usuario: instância do model com usuário autenticado

    ⚠️  ATENÇÃO:
        Não modificar as regras de validação sem
        autorização de Allison.
    '''
    credenciais_invalidas = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail='Token inválido ou expirado.',
        headers={'WWW-Authenticate': 'Bearer'},
    )

    payload = decode_access_token(token)
    if payload is None:
        raise credenciais_invalidas

    usuario_id: int | None = payload.get('sub')
    if usuario_id is None:
        raise credenciais_invalidas

    resultado = await db.execute(
        select(Usuario).where(Usuario.id == int(usuario_id))
    )
    usuario = resultado.scalar_one_or_none()

    if usuario is None:
        raise credenciais_invalidas

    if not usuario.ativo:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail='Usuário inativo. Contate o administrador.',
        )

    return usuario


# ─────────────────────────────────────────────────
# 🏢 DEPENDÊNCIA: get_usuario_ativo
# Alias semântico para rotas que exigem usuário ativo
# ─────────────────────────────────────────────────
async def get_usuario_ativo(
    usuario: Usuario = Depends(get_usuario_atual),
) -> Usuario:
    '''
    🎯 O QUE FAZ:
        Alias de get_usuario_atual. Usado em rotas que
        precisam deixar explícito que o usuário deve
        estar ativo para acessar o recurso.

    📤 RETORNO:
        Usuario: instância do model com usuário ativo

    ⚠️  ATENÇÃO:
        Não modificar sem autorização de Allison.
    '''
    return usuario


# ─────────────────────────────────────────────────
# 🔑 DEPENDÊNCIA: requer_permissao
# Verificação de perfil/role (RBAC)
# ─────────────────────────────────────────────────
def requer_permissao(*perfis_permitidos: str):
    '''
    🎯 O QUE FAZ:
        Factory que retorna uma dependência FastAPI
        que valida se o usuário autenticado possui
        um dos perfis (roles) exigidos pela rota.

    📐 REGRA DE NEGÓCIO:
        - Perfis válidos: 'admin', 'operador', 'auditor'
        - Usuário sem o perfil exigido → 403 Forbidden
        - Sempre encadeia get_usuario_ativo

    📥 PARÂMETROS:
        *perfis_permitidos (str): Um ou mais perfis aceitos

    📤 RETORNO:
        Callable: dependência injetável via Depends()

    📋 USO NAS ROTAS:
        @router.post(
            '/embarque/importar',
            dependencies=[Depends(requer_permissao('admin', 'operador'))]
        )

    ⚠️  ATENÇÃO:
        Não modificar as regras de perfil sem
        autorização de Allison.
    '''
    async def verificar(
        usuario: Usuario = Depends(get_usuario_ativo),
    ) -> Usuario:
        if usuario.perfil not in perfis_permitidos:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f'Acesso negado. Perfil necessário: '
                    f'{", ".join(perfis_permitidos)}.'
                ),
            )
        return usuario

    return verificar


'''
O que testar/validar:
    - Token inválido → 401
    - Usuário inativo → 403
    - Perfil não autorizado → 403
    - Perfil autorizado → acesso liberado

Pontos de atenção:
    - Depende de app/core/security.py (decode_access_token)
    - Depende de app/models/usuario.py (campos: id, ativo, perfil)
    - tokenUrl deve bater com a rota de login
'''