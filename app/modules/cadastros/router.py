'''
Rotas do módulo de cadastros (placeholder).
'''

from fastapi import APIRouter

router = APIRouter(prefix='/cadastros', tags=['Cadastros'])


@router.get('/health')
async def health():
    '''Health check do módulo.'''
    return {'modulo': 'cadastros', 'status': 'ok'}
