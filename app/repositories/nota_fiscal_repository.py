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
📅 CRIADO   : 07/07/2026
📅 ATUALIZADO: 18/07/2026 — substituídos campos frete_peso,
              frete_cte, frete_total por valor_calculado,
              preco_ate_30kg_usado, valor_kg_adicional_usado,
              peso_kg_usado. atualizar_resultado_frete agora
              recebe os snapshots de auditoria diretamente
              (sem TypedDict intermediário).
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
'''

from __future__ import annotations

from decimal import Decimal
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
    # 🔍 LEITURA: por embarque E id (pertencimento)
    # ─────────────────────────────────────────────
    def buscar_por_embarque_e_id(
        self, embarque_id: UUID, nf_id: UUID
    ) -> NotaFiscal | None:
        '''
        🎯 O QUE FAZ:
            Busca uma NF ativa pelo id, validando que
            ela pertence ao embarque informado. Usado
            pelo endpoint individual de cálculo para
            garantir que a NF é do embarque da URL.

        📥 PARÂMETROS:
            embarque_id (UUID): ID do embarque dono.
            nf_id       (UUID): ID da nota fiscal.

        📤 RETORNO:
            NotaFiscal | None
        '''
        stmt = (
            select(NotaFiscal)
            .where(NotaFiscal.id == nf_id)
            .where(NotaFiscal.embarque_id == embarque_id)
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
        valor_calculado: Decimal | None = None,
        preco_ate_30kg_usado: Decimal | None = None,
        valor_kg_adicional_usado: Decimal | None = None,
        peso_kg_usado: Decimal | None = None,
        status: StatusCalculoNF,
        erro_calculo: str | None = None,
    ) -> NotaFiscal:
        '''
        🎯 O QUE FAZ:
            Grava o resultado do engine de cálculo na NF,
            incluindo snapshots de auditoria.

        📐 REGRA DE NEGÓCIO:
            - Em caso de ERRO, os valores calculados podem
              vir None e erro_calculo deve descrever o problema.
            - Os snapshots (preco_ate_30kg_usado,
              valor_kg_adicional_usado, peso_kg_usado) permitem
              auditoria futura contra o CT-e.
            - Não faz commit (só flush).

        📤 RETORNO:
            NotaFiscal atualizada.
        '''
        nf.valor_calculado = valor_calculado
        nf.preco_ate_30kg_usado = preco_ate_30kg_usado
        nf.valor_kg_adicional_usado = valor_kg_adicional_usado
        nf.peso_kg_usado = peso_kg_usado
        nf.status_calculo = status
        nf.erro_calculo = erro_calculo
        self.session.flush()
        return nf

    # ─────────────────────────────────────────────
    # ✏️ ATUALIZAÇÃO: atalho para o engine de cálculo
    # ─────────────────────────────────────────────
    def atualizar_resultado_frete(
        self,
        nf: NotaFiscal,
        *,
        valor_calculado: Decimal | None = None,
        preco_ate_30kg_usado: Decimal | None = None,
        valor_kg_adicional_usado: Decimal | None = None,
        peso_kg_usado: Decimal | None = None,
        status: StatusCalculoNF | None = None,
        erro: str | None = None,
    ) -> NotaFiscal:
        '''
        🎯 O QUE FAZ:
            Atalho que recebe os snapshots de auditoria
            diretamente do engine de cálculo e repassa
            para atualizar_calculo.

        📥 PARÂMETROS:
            nf                      : instância NotaFiscal.
            valor_calculado         : frete calculado pelo engine.
            preco_ate_30kg_usado    : valor fixo da faixa 0→30.
            valor_kg_adicional_usado: valor do kg excedente usado.
            peso_kg_usado           : peso total utilizado no cálculo.
            status                  : StatusCalculoNF.
            erro                    : mensagem de erro (None se sucesso).

        📤 RETORNO:
            NotaFiscal atualizada.
        '''
        if valor_calculado is not None:
            return self.atualizar_calculo(
                nf,
                valor_calculado=valor_calculado,
                preco_ate_30kg_usado=preco_ate_30kg_usado,
                valor_kg_adicional_usado=valor_kg_adicional_usado,
                peso_kg_usado=peso_kg_usado,
                status=status or StatusCalculoNF.CALCULADO,
                erro_calculo=None,
            )

        return self.atualizar_calculo(
            nf,
            valor_calculado=None,
            preco_ate_30kg_usado=None,
            valor_kg_adicional_usado=None,
            peso_kg_usado=None,
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


def buscar_por_embarque_e_id(
    db: Session, embarque_id: str, nf_id: str
) -> NotaFiscal | None:
    '''
    🎯 O QUE FAZ:
        Wrapper de módulo que busca uma NF validando
        pertencimento ao embarque. Usado pelo endpoint
        individual de cálculo.

    📤 RETORNO:
        NotaFiscal | None
    '''
    repo = NotaFiscalRepository(db)
    return repo.buscar_por_embarque_e_id(UUID(embarque_id), UUID(nf_id))


def atualizar_resultado_frete(
    db: Session,
    nf: NotaFiscal,
    *,
    valor_calculado: Decimal | None = None,
    preco_ate_30kg_usado: Decimal | None = None,
    valor_kg_adicional_usado: Decimal | None = None,
    peso_kg_usado: Decimal | None = None,
    status: StatusCalculoNF | None = None,
    erro: str | None = None,
) -> NotaFiscal:
    '''
    🎯 O QUE FAZ:
        Wrapper de módulo que atualiza os campos de frete,
        snapshots de auditoria e status de uma NF após o
        cálculo. Só dá flush — o commit é feito pelo orquestrador.

    📥 PARÂMETROS:
        db                      : Session ativa.
        nf                      : Instância da NF a atualizar.
        valor_calculado         : frete calculado (None se erro).
        preco_ate_30kg_usado    : snapshot do valor fixo da faixa.
        valor_kg_adicional_usado: snapshot do valor do kg excedente.
        peso_kg_usado           : snapshot do peso usado no cálculo.
        status                  : StatusCalculoNF.
        erro                    : Mensagem de erro (None se sucesso).

    📤 RETORNO:
        A própria instância NotaFiscal atualizada.
    '''
    repo = NotaFiscalRepository(db)
    return repo.atualizar_resultado_frete(
        nf=nf,
        valor_calculado=valor_calculado,
        preco_ate_30kg_usado=preco_ate_30kg_usado,
        valor_kg_adicional_usado=valor_kg_adicional_usado,
        peso_kg_usado=peso_kg_usado,
        status=status,
        erro=erro,
    )
