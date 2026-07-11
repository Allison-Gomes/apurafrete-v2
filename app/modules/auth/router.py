'''
Rotas de autenticação: login e me.
POST /auth/login  → retorna JWT
GET  /auth/me     → retorna dados do usuário autenticado
'''

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_usuario_atual
from app.core.security import criar_access_token
from app.models.usuario import Usuario
from app.modules.auth.schemas import LoginRequest, LoginResponse, UsuarioOut
from app.modules.auth.service import autenticar_usuario

router = APIRouter(prefix='/auth', tags=['Autenticação'])


@router.post('/login', response_model=LoginResponse)
async def login(
    body: LoginRequest,
    db: AsyncSession = Depends(get_db),
):
    '''
    Autentica o usuário e retorna um token JWT.
    '''
    usuario = await autenticar_usuario(db, body.email, body.senha)

    if usuario is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='E-mail ou senha inválidos.',
        )

    # Atualiza último login
    usuario.ultimo_login = datetime.now(timezone.utc)
    await db.commit()

    access_token = criar_access_token({'sub': str(usuario.id)})

    return LoginResponse(
        access_token=access_token,
        usuario=UsuarioOut.model_validate(usuario),
    )


@router.get('/me', response_model=UsuarioOut)
async def me(
    usuario: Usuario = Depends(get_usuario_atual),
):
    '''
    Retorna os dados do usuário autenticado.
    '''
    return UsuarioOut.model_validate(usuario)
