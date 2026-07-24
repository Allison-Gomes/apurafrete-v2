'''
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📁 ARQUIVO : embarque_exceptions.py
📦 MÓDULO  : Embarque / Exceções de Negócio
🎯 OBJETIVO: Exceções específicas do domínio Embarque,
             capturadas pelo router → HTTPException.
📐 REGRA    : - Exceções de negócio são levantadas pelo
               service e capturadas pelo router.
             - NÃO importar models/repos aqui.
📅 CRIADO   : 18/07/2026
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
'''

from __future__ import annotations

from uuid import UUID


class EmbarqueNaoEncontradoError(Exception):
    '''
    🎯 Levantada quando um embarque_id não existe
       ou está inativo durante a importação.
    📐 Router captura → HTTP 404.
    '''
    def __init__(self, embarque_id: UUID) -> None:
        self.embarque_id = embarque_id
        super().__init__(f"Embarque {embarque_id} não encontrado ou inativo.")
