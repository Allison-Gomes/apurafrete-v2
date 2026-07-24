'''
Repository de Embarque — Etapa 4 (Exportação) + Etapa 5 (Importação)
Responsabilidade: consultas de leitura com eager loading (exportação)
                 + verificações de existência (importação).
Acesso ao banco SOMENTE via repository (Regra de Ouro).
'''

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models.embarque import Embarque


# ─────────────────────────────────────────────────
# 🔍 Consulta de leitura (Etapa 4: Exportação)
# ─────────────────────────────────────────────────

def buscar_embarque_com_nfs(db: Session, embarque_id: UUID) -> Embarque | None:
    '''
    Busca embarque por ID com NFs + relacionamentos eager-loaded.
    Evita N+1 ao carregar transportadora e remetente junto com cada NF.

    Parâmetros:
        db: Sessão SQLAlchemy (injetada via Depends)
        embarque_id: UUID do embarque a buscar

    Retorna:
        Embarque com notas_fiscais populadas (transportadora e
        remetente já carregados), ou None se não encontrado.

    Observação:
        Multi-tenant: o embarque já está vinculado à empresa via FK.
        Busca por ID é segura no contexto do tenant autenticado.
    '''
    stmt = (
        select(Embarque)
        .options(
            joinedload(Embarque.notas_fiscais)
            .joinedload("transportadora"),
            joinedload(Embarque.notas_fiscais)
            .joinedload("remetente"),
        )
        .where(Embarque.id == embarque_id)
    )
    return db.execute(stmt).unique().scalar_one_or_none()


# ─────────────────────────────────────────────────
# 🏗️ Repository class (Etapa 5: Importação)
# ─────────────────────────────────────────────────

class EmbarqueRepository:
    '''
    🎯 Repository orientado a objetos para Embarque.
       Usado pelo import_service para validar pré-condições.

    📐 Segue o mesmo padrão de NotaFiscalRepository:
       recebe Session no __init__ e expõe métodos de consulta.
    '''

    def __init__(self, session: Session) -> None:
        self.session = session

    def existe(self, embarque_id: UUID) -> bool:
        '''
        🎯 Verifica se um embarque ativo existe.

        📐 Usado pelo import_service como pré-condição
           antes de processar qualquer linha do lote.
           Se False → EmbarqueNaoEncontradoError.

        📥 embarque_id (UUID)

        📤 bool: True se o embarque existe e está ativo.
        '''
        return (
            self.session.query(Embarque)
            .filter(
                Embarque.id == embarque_id,
                Embarque.ativo == True,  # noqa: E712
            )
            .first()
            is not None
        )
