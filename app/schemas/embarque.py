'''
Schema: Embarque

Schemas Pydantic específicos do módulo Embarque:
- Exportação de planilha (metadados)
- Respostas auxiliares
'''

from pydantic import BaseModel


class ExportarEmbarqueResponse(BaseModel):
    '''Metadados da exportação de um embarque.'''
    nome_arquivo: str
    total_nfs: int
    tamanho_bytes: int
