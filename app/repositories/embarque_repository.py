'''
Repository de Embarque — Etapa 4 (Exportação)
Responsabilidade: consultas de leitura com eager loading.
Acesso ao banco SOMENTE via repository (Regra de Ouro).
'''

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models.embarque import Embarque


def buscar_embarque_com_nfs(db: Session, embarque_id: UUID) -> Embarque | None:
    '''
    Busca embarque por ID com NFs + relacionamentos eager-loaded.
    Evita N+1 ao carregar transportadora junto com cada NF.
    
    Parâmetros:
        db: Sessão SQLAlchemy (injetada via Depends)
        embarque_id: UUID do embarque a buscar
    
    Retorna:
        Embarque com notas_fiscais populadas, ou None se não encontrado.
    
    Observação:
        Multi-tenant: o embarque já está vinculado à empresa via FK.
        Busca por ID é segura no contexto do tenant autenticado.
    '''
    stmt = (
        select(Embarque)
        .options(
            joinedload(Embarque.notas_fiscais)
            .joinedload("transportadora")
        )
        .where(Embarque.id == embarque_id)
    )
    return db.execute(stmt).unique().scalar_one_or_none()
