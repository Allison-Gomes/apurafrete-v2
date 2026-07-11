'''
Schemas Pydantic para o módulo de autenticação.
'''

from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    '''Schema para requisição de login.'''
    email: EmailStr = Field(..., description='E-mail do usuário')
    senha: str = Field(..., min_length=4, description='Senha em texto plano')


class UsuarioOut(BaseModel):
    '''Schema de saída com dados públicos do usuário.'''
    id: str
    nome: str
    email: str
    perfil: str
    empresa_id: str

    model_config = {'from_attributes': True}


class LoginResponse(BaseModel):
    '''Schema de resposta do login.'''
    access_token: str
    token_type: str = 'bearer'
    usuario: UsuarioOut
