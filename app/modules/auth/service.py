'''
Lógica de negócio para autenticação.
'''

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.security import verificar_senha
from app.models.usuario import Usuario


async def autenticar_usuario(
    db: AsyncSession,
    email: str,
    senha: str,
) -> Usuario | None:
    '''
    Autentica um usuário por e-mail e senha.
    Retorna o Usuario se válido e ativo, None caso contrário.
    '''
    resultado = await db.execute(
        select(Usuario).where(Usuario.email == email)
    )
    usuario = resultado.scalar_one_or_none()

    if usuario is None:
        return None
    if not usuario.ativo:
        return None
    if not verificar_senha(senha, usuario.senha_hash):
        return None

    return usuario
