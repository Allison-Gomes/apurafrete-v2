'''
Rotas do módulo de auditoria (placeholder).
'''

from fastapi import APIRouter

router = APIRouter(prefix='/auditoria', tags=['Auditoria'])


@router.get('/health')
async def health():
    '''Health check do módulo.'''
    return {'modulo': 'auditoria', 'status': 'ok'}
