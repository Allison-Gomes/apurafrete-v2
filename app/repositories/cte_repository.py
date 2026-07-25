'''
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📁 ARQUIVO : cte_repository.py
📦 MÓDULO  : Auditoria / Repository
🎯 OBJETIVO: Acesso a dados do domínio CT-e.
             Consultas de leitura com eager loading +
             verificações de existência e unicidade.
📐 REGRA    : Acesso ao banco SOMENTE via repository
             (Regra de Ouro).
📅 CRIADO   : 25/07/2026
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
'''

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models.cte import Cte, ItemCte


# ─────────────────────────────────────────────────
# 🔍 Consultas de leitura com eager loading
# ─────────────────────────────────────────────────

def buscar_cte_com_itens(db: Session, cte_id: UUID) -> Cte | None:
    '''
    Busca CT-e por ID com itens de rateio + NFs eager-loaded.
    Evita N+1 ao carregar transportadora e notas fiscais.

    Parâmetros:
        db: Sessão SQLAlchemy (injetada via Depends)
        cte_id: UUID do CT-e a buscar

    Retorna:
        Cte com itens populados (ItemCte + NotaFiscal carregados),
        ou None se não encontrado.
    '''
    stmt = (
        select(Cte)
        .options(
            joinedload(Cte.transportadora),
            joinedload(Cte.itens)
            .joinedload(ItemCte.nota_fiscal),
        )
        .where(Cte.id == cte_id)
    )
    return db.execute(stmt).unique().scalar_one_or_none()


def buscar_ctes_por_embarque(db: Session, embarque_id: UUID) -> list[Cte]:
    '''
    Lista todos os CT-es vinculados a um embarque,
    com transportadora eager-loaded.

    Parâmetros:
        db: Sessão SQLAlchemy
        embarque_id: UUID do embarque

    Retorna:
        Lista de Cte vinculados (vazia se nenhum).
        CT-es cancelados NÃO são excluídos da lista —
        a filtragem fica a cargo do service.
    '''
    stmt = (
        select(Cte)
        .options(joinedload(Cte.transportadora))
        .where(Cte.embarque_id == embarque_id)
        .order_by(Cte.data_emissao)
    )
    return list(db.execute(stmt).unique().scalars().all())


# ─────────────────────────────────────────────────
# 🏗️ Repository class
# ─────────────────────────────────────────────────

class CteRepository:
    '''
    🎯 Repository orientado a objetos para CT-e.
       Usado pelos services de auditoria para validar
       pré-condições e persistir alterações.

    📐 Segue o mesmo padrão de EmbarqueRepository:
       recebe Session no __init__ e expõe métodos
       de consulta e persistência.
    '''

    def __init__(self, session: Session) -> None:
        self.session = session

    # ── 🔍 Consultas ──────────────────────────

    def buscar_por_id(self, cte_id: UUID) -> Cte | None:
        '''
        🎯 Busca CT-e simples por ID (sem eager loading).

        📥 cte_id (UUID)

        📤 Cte | None
        '''
        return self.session.get(Cte, cte_id)

    def buscar_por_chave(self, chave_cte: str) -> Cte | None:
        '''
        🎯 Busca CT-e pela chave de acesso (44 dígitos).
           Usado para verificar duplicidade na importação.

        📥 chave_cte (str): chave de 44 dígitos

        📤 Cte | None: o CT-e existente, ou None se inédito.
        '''
        return (
            self.session.query(Cte)
            .filter(Cte.chave_cte == chave_cte)
            .first()
        )

    def listar_por_status(
        self, status: str, limit: int = 50
    ) -> list[Cte]:
        '''
        🎯 Lista CT-es por status, ordenados por data de emissão.

        📐 Útil para:
           - Listar CT-es IMPORTADO aguardando vinculação.
           - Listar CT-es DIVERGENTE para revisão.

        📥 status (str): valor do enum StatusCte
        📥 limit (int): máximo de registros (default 50)

        📤 list[Cte]
        '''
        return (
            self.session.query(Cte)
            .filter(Cte.status == status)
            .order_by(Cte.data_emissao.desc())
            .limit(limit)
            .all()
        )

    # ── ✅ Verificações ───────────────────────

    def existe_por_chave(self, chave_cte: str) -> bool:
        '''
        🎯 Verifica se uma chave_cte já existe no sistema.

        📐 Usado como pré-condição antes de importar XML.
           Se True → CteDuplicadoError.

        📥 chave_cte (str)

        📤 bool
        '''
        return (
            self.session.query(Cte)
            .filter(Cte.chave_cte == chave_cte)
            .first()
            is not None
        )

    def esta_vinculado(self, cte_id: UUID) -> bool:
        '''
        🎯 Verifica se o CT-e já possui embarque_id.

        📐 Usado como pré-condição antes de vincular.
           Se True → CteJaVinculadoError.

        📥 cte_id (UUID)

        📤 bool
        '''
        cte = self.session.get(Cte, cte_id)
        return cte is not None and cte.embarque_id is not None

    def esta_cancelado(self, cte_id: UUID) -> bool:
        '''
        🎯 Verifica se o CT-e está com status CANCELADO.

        📐 Usado como pré-condição antes de qualquer
           operação de negócio (vincular, auditar, ratear).
           Se True → CteCanceladoError.

        📥 cte_id (UUID)

        📤 bool
        '''
        from app.models.cte import StatusCte
        cte = self.session.get(Cte, cte_id)
        return cte is not None and cte.status == StatusCte.CANCELADO

    # ── 💾 Persistência ───────────────────────

    def salvar(self, cte: Cte) -> Cte:
        '''
        🎯 Persiste um CT-e (novo ou alterado).

        📐 Usa session.merge para suportar tanto inserts
           quanto updates, com flush para obter o ID.

        📥 cte (Cte): instância a persistir

        📤 Cte: mesma instância, com ID populado se novo.
        '''
        cte = self.session.merge(cte)
        self.session.flush()
        return cte

    def excluir_itens(self, cte_id: UUID) -> None:
        '''
        🎯 Remove todos os ItemCte vinculados a um CT-e.

        📐 Usado antes de refazer o rateio (auditoria),
           garantindo consistência entre total_rateado
           e a soma dos itens.

        📥 cte_id (UUID)
        '''
        (
            self.session.query(ItemCte)
            .filter(ItemCte.cte_id == cte_id)
            .delete()
        )
        self.session.flush()
