'''
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📁 ARQUIVO : nota_fiscal_repository.py
📦 MÓDULO  : Embarque / Persistência de NF
🎯 OBJETIVO: Camada de acesso a dados (R1 — síncrona) da
             NotaFiscal. Isola o ORM do restante da aplicação:
             recebe Session, executa CRUD e devolve models.
             NÃO faz commit (isso é responsabilidade da UoW/
             service que orquestra a transação).
📐 REGRA    : Respeita soft delete (ativo=True) nas leituras.
             Dedup pela UniqueConstraint (embarque_id,
             numero_nf, serie_nf).
🔗 DEPENDE  : app/models/nota_fiscal.py
             app/schemas/nota_fiscal.py
             app/services/calculo_frete_service.py (ResultadoFrete)
📅 CRIADO   : 07/07/2026
📅 ATUALIZADO: 11/07/2026 — + atualizar_resultado_frete (aceita
              ResultadoFrete direto); frete_cte/frete_total opcionais
              no atualizar_calculo; wrappers de módulo para service.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
'''

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.nota_fiscal import NotaFiscal, StatusCalculoNF
from app.schemas.nota_fiscal import NotaFiscalCreate


class NotaFiscalRepository:
    '''
    🎯 O QUE FAZ:
        Encapsula todo o acesso a dados da NotaFiscal.
        O service injeta a Session e chama estes métodos.

    📐 REGRA DE NEGÓCIO:
        - flush() para materializar IDs SEM encerrar a
          transação (commit fica a cargo do orquestrador).
        - Leituras filtram ativo=True (soft delete).

    📥 PARÂMETROS:
        session (Session): sessão SQLAlchemy síncrona.
    '''

    def __init__(self, session: Session):
        self.session = session

    # ─────────────────────────────────────────────
    # 💾 CRIAÇÃO EM LOTE
    # ─────────────────────────────────────────────
    def criar_em_lote(
        self, notas: list[NotaFiscalCreate]
    ) -> list[NotaFiscal]:
        '''
        🎯 O QUE FAZ:
            Persiste várias NFs de uma vez (add_all + flush).
            status_calculo NÃO é setado aqui — usa o default
            PENDENTE do model.

        📐 REGRA DE NEGÓCIO:
            - Retorna os models já com id preenchido (flush).
            - Não faz commit.

        📤 RETORNO:
            list[NotaFiscal]: models persistidos (com id).
        '''
        objetos = [
            NotaFiscal(**dados.model_dump(exclude_none=False))
            for dados in notas
        ]
        self.session.add_all(objetos)
        self.session.flush()
        return objetos

    # ─────────────────────────────────────────────
    # 🔍 LEITURA: por ID
    # ─────────────────────────────────────────────
    def buscar_por_id(self, nf_id: UUID) -> NotaFiscal | None:
        '''
        🎯 O QUE FAZ:
            Busca uma NF ativa pelo id.

        📤 RETORNO:
            NotaFiscal | None
        '''
        stmt = (
            select(NotaFiscal)
            .where(NotaFiscal.id == nf_id)
            .where(NotaFiscal.ativo.is_(True))
        )
        return self.session.execute(stmt).scalar_one_or_none()

    # ─────────────────────────────────────────────
    # 🔍 LEITURA: por embarque
    # ─────────────────────────────────────────────
    def listar_por_embarque(
        self,
        embarque_id: UUID,
        status: StatusCalculoNF | None = None,
    ) -> list[NotaFiscal]:
        '''
        🎯 O QUE FAZ:
            Lista NFs ativas de um embarque, opcionalmente
            filtrando por status_calculo.

        📥 PARÂMETROS:
            embarque_id (UUID)
            status (StatusCalculoNF | None): filtro opcional.

        📤 RETORNO:
            list[NotaFiscal]
        '''
        stmt = (
            select(NotaFiscal)
            .where(NotaFiscal.embarque_id == embarque_id)
            .where(NotaFiscal.ativo.is_(True))
            .order_by(NotaFiscal.numero_nf)
        )
        if status is not None:
            stmt = stmt.where(NotaFiscal.status_calculo == status)

        return list(self.session.execute(stmt).scalars().all())

    # ─────────────────────────────────────────────
    # 🔍 DEDUP: chaves já existentes no embarque
    # ─────────────────────────────────────────────
    def buscar_chaves_existentes(
        self, embarque_id: UUID
    ) -> set[tuple[str, str | None]]:
        '''
        🎯 O QUE FAZ:
            Retorna o conjunto de chaves (numero_nf, serie_nf)
            já cadastradas e ativas no embarque, para o service
            filtrar duplicatas ANTES do insert (evita violar a
            UniqueConstraint uq_nf_embarque_numero_serie).

        📤 RETORNO:
            set[tuple[str, str | None]]
        '''
        stmt = (
            select(NotaFiscal.numero_nf, NotaFiscal.serie_nf)
            .where(NotaFiscal.embarque_id == embarque_id)
            .where(NotaFiscal.ativo.is_(True))
        )
        return {
            (numero, serie)
            for numero, serie in self.session.execute(stmt).all()
        }

    # ─────────────────────────────────────────────
    # ✏️ ATUALIZAÇÃO: resultado do cálculo
    # ─────────────────────────────────────────────
    def atualizar_calculo(
        self,
        nf: NotaFiscal,
        *,
        frete_peso = None,
        frete_cte = None,
        frete_total = None,
        status: StatusCalculoNF,
        erro_calculo: str | None = None,
    ) -> NotaFiscal:
        '''
        🎯 O QUE FAZ:
            Grava o resultado do engine de cálculo na NF.

        📐 REGRA DE NEGÓCIO:
            - Em caso de ERRO, frete_* pode vir None e
              erro_calculo deve descrever o problema.
            - frete_cte e frete_total são opcionais: no MVP
              só o frete_peso (frete calculado) é preenchido;
              os demais vêm na etapa de auditoria do CT-e.
            - Não faz commit (só flush).

        📤 RETORNO:
            NotaFiscal atualizada.
        '''
        nf.frete_peso = frete_peso
        nf.frete_cte = frete_cte
        nf.frete_total = frete_total
        nf.status_calculo = status
        nf.erro_calculo = erro_calculo
        self.session.flush()
        return nf

    # ─────────────────────────────────────────────
    # ✏️ ATUALIZAÇÃO: a partir de ResultadoFrete
    # ─────────────────────────────────────────────
    def atualizar_resultado_frete(
        self,
        nf: NotaFiscal,
        resultado,           # ResultadoFrete (TypedDict)
        status: StatusCalculoNF | None = None,
        erro: str | None = None,
    ) -> NotaFiscal:
        '''
        🎯 O QUE FAZ:
            Atalho para atualizar_calculo que recebe um
            ResultadoFrete direto do engine de cálculo e
            faz o mapeamento automaticamente.

        📥 PARÂMETROS:
            nf        : instância NotaFiscal a atualizar.
            resultado : ResultadoFrete (TypedDict do engine).
                        Se None, grava status de erro.
            status    : StatusCalculoNF (default: CALCULADO se
                        resultado, ERRO se erro).
            erro      : mensagem de erro (None se sucesso).

        📤 RETORNO:
            NotaFiscal atualizada.
        '''
        if resultado is not None:
            return self.atualizar_calculo(
                nf,
                frete_peso=resultado["valor_frete"],
                status=status or StatusCalculoNF.CALCULADO,
                erro_calculo=None,
            )

        return self.atualizar_calculo(
            nf,
            frete_peso=None,
            status=status or StatusCalculoNF.ERRO,
            erro_calculo=erro,
        )

    # ─────────────────────────────────────────────
    # 🗑️ SOFT DELETE
    # ─────────────────────────────────────────────
    def soft_delete(self, nf: NotaFiscal) -> None:
        '''
        🎯 O QUE FAZ:
            Marca a NF como inativa (ativo=False).
            Nunca deleta fisicamente (política do projeto).
        '''
        nf.ativo = False
        self.session.flush()


# ═════════════════════════════════════════════════
# 🧩 WRAPPERS DE MÓDULO
# Funções de conveniência para services que não
# querem instanciar o Repository manualmente.
# ═════════════════════════════════════════════════

def buscar_por_embarque(db: Session, embarque_id: str) -> list[NotaFiscal]:
    '''
    🎯 O QUE FAZ:
        Wrapper de módulo que retorna todas as NFs ativas
        de um embarque. Usado pelo engine de cálculo em lote.

    📤 RETORNO:
        list[NotaFiscal] ordenadas por numero_nf.
    '''
    repo = NotaFiscalRepository(db)
    return repo.listar_por_embarque(UUID(embarque_id))


def atualizar_resultado_frete(
    db: Session,
    nf: NotaFiscal,
    resultado = None,
    status: StatusCalculoNF | None = None,
    erro: str | None = None,
) -> NotaFiscal:
    '''
    🎯 O QUE FAZ:
        Wrapper de módulo que atualiza os campos de frete
        e status de uma NF após o cálculo. Só dá flush —
        o commit é feito pelo orquestrador.

    📥 PARÂMETROS:
        db        : Session ativa.
        nf        : Instância da NF a atualizar.
        resultado : ResultadoFrete do cálculo (se sucesso).
        status    : Novo StatusCalculoNF.
        erro      : Mensagem de erro (se falha).

    📤 RETORNO:
        A própria instância NotaFiscal atualizada.
    '''
    repo = NotaFiscalRepository(db)
    return repo.atualizar_resultado_frete(
        nf=nf,
        resultado=resultado,
        status=status,
        erro=erro,
    )
