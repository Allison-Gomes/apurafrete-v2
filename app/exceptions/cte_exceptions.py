'''
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📁 ARQUIVO : cte_exceptions.py
📦 MÓDULO  : Auditoria / Exceções de Negócio
🎯 OBJETIVO: Exceções específicas do domínio CT-e,
             capturadas pelo router → HTTPException.
📐 REGRA    : - Exceções de negócio são levantadas pelo
               service e capturadas pelo router.
             - NÃO importar models/repos aqui.
📅 CRIADO   : 25/07/2026
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
'''

from __future__ import annotations

from uuid import UUID


class CteNaoEncontradoError(Exception):
    '''
    🎯 Levantada quando um cte_id não existe
       ou não pertence ao tenant atual.
    📐 Router captura → HTTP 404.
    '''
    def __init__(self, cte_id: UUID) -> None:
        self.cte_id = cte_id
        super().__init__(f"CT-e {cte_id} não encontrado.")


class CteDuplicadoError(Exception):
    '''
    🎯 Levantada quando uma chave_cte já existe no sistema,
       evitando importação duplicada do mesmo XML.
    📐 Router captura → HTTP 409.
    '''
    def __init__(self, chave_cte: str) -> None:
        self.chave_cte = chave_cte
        super().__init__(
            f"CT-e com chave {chave_cte[:10]}... já importado."
        )


class CteJaVinculadoError(Exception):
    '''
    🎯 Levantada ao tentar vincular um CT-e que já
       possui embarque_id (ciclo: VINCULADO ou posterior).
    📐 Router captura → HTTP 409.
    '''
    def __init__(self, cte_id: UUID, embarque_id: UUID) -> None:
        self.cte_id = cte_id
        self.embarque_id = embarque_id
        super().__init__(
            f"CT-e {cte_id} já vinculado ao embarque {embarque_id}."
        )


class CteCanceladoError(Exception):
    '''
    🎯 Levantada ao tentar operar sobre um CT-e com
       status = CANCELADO (auditoria, vinculação, rateio).
    📐 Router captura → HTTP 422.
    '''
    def __init__(self, cte_id: UUID) -> None:
        self.cte_id = cte_id
        super().__init__(
            f"Operação não permitida: CT-e {cte_id} está cancelado."
        )
