'''
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📁 ARQUIVO : services/auditoria_cte_service.py
📦 MÓDULO  : Auditoria / Service
🎯 OBJETIVO: Orquestra o fluxo completo de auditoria
             de CT-e:
               1. Importa XML de CT-e (via cte_parser_service)
               2. Vincula CT-e a um embarque
               3. Rateia valor do CT-e entre as NFs
               4. Compara valor_rateado vs valor_calculado
               5. Determina status (AUDITADO ou DIVERGENTE)

             Regras de negócio (MVP v2.3 - Seção 8):
               - Rateio igualitário: valor_total / qtd_nfs
               - Resíduo na 1ª NF (garante soma exata)
               - Tolerância de ±5% para considerar OK
               - CT-e cancelado não entra em auditoria
               - NF com status CALCULADO é pré-requisito
🔗 DEPENDE  : app/services/cte_parser_service.py
             app/repositories/cte_repository.py
             app/models/cte.py
             app/models/embarque.py
             app/models/nota_fiscal.py
📅 CRIADO   : 25/07/2026
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
'''

from __future__ import annotations

import logging
from decimal import Decimal, ROUND_HALF_UP
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.cte import Cte, ItemCte, StatusCte, OrigemCte
from app.models.embarque import Embarque, StatusEmbarque
from app.models.nota_fiscal import NotaFiscal, StatusCalculoNF
from app.repositories.cte_repository import CteRepository
from app.services.cte_parser_service import (
    parsear_cte_xml,
    CTeData,
    CTeParseError,
)

logger = logging.getLogger(__name__)


# ═════════════════════════════════════════════════
# ❌ EXCEÇÕES DO SERVICE
# ═════════════════════════════════════════════════

class AuditoriaCteError(Exception):
    '''Erro base do service de auditoria de CT-e.'''
    pass


class CteDuplicadoError(AuditoriaCteError):
    '''CT-e com chave de acesso já existente no sistema.'''
    pass


class CteJaVinculadoError(AuditoriaCteError):
    '''CT-e já vinculado a outro embarque.'''
    pass


class CteCanceladoError(AuditoriaCteError):
    '''Operação não permitida em CT-e cancelado.'''
    pass


class EmbarqueNaoEnviadoError(AuditoriaCteError):
    '''Embarque precisa estar com status ENVIADO para auditoria.'''
    pass


class NfSemCalculoError(AuditoriaCteError):
    '''NF sem cálculo de frete (status != CALCULADO).'''
    pass


# ═════════════════════════════════════════════════
# 🔧 CONSTANTES
# ═════════════════════════════════════════════════

# Tolerância de ±5% para considerar divergência aceitável (Seção 8.4)
TOLERANCIA_DIVERGENCIA_PERCENTUAL = Decimal('5.00')

# Precisão para cálculos monetários (2 casas decimais)
PRECISAO_DECIMAL = Decimal('0.01')


# ═════════════════════════════════════════════════
# 🚀 SERVICE PRINCIPAL
# ═════════════════════════════════════════════════

class AuditoriaCteService:
    '''
    🎯 Orquestra o fluxo completo de auditoria de CT-e.

    📐 RESPONSABILIDADES:
        - Importar XML de CT-e (parse + persistência)
        - Vincular CT-e a embarque (validações)
        - Ratear valor entre NFs (igualitário + resíduo)
        - Calcular divergências (snapshot imutável)
        - Determinar status final (AUDITADO ou DIVERGENTE)

    ⚠️ ATENÇÃO:
        Não modificar sem autorização de Allison.
    '''

    def __init__(self, session: Session) -> None:
        self.session = session
        self.repo = CteRepository(session)

    # ─────────────────────────────────────────────
    # 📥 1. IMPORTAR CT-e DE XML
    # ─────────────────────────────────────────────

    def importar_xml(
        self,
        conteudo_xml: str | bytes,
        transportadora_id: UUID,
        nome_arquivo: str | None = None,
    ) -> Cte:
        '''
        🎯 Importa CT-e a partir de XML.

        📐 FLUXO:
            1. Parse do XML (cte_parser_service)
            2. Verifica duplicidade (chave_cte)
            3. Cria model Cte com dados extraídos
            4. Persiste no banco

        🎯 PARÂMETROS:
            conteudo_xml: conteúdo do XML (string ou bytes)
            transportadora_id: UUID da transportadora emissora
            nome_arquivo: nome do arquivo XML (opcional)

        🎯 RETORNA:
            Cte recém-criado com status = IMPORTADO

        ❌ LANÇA:
            CTeParseError: XML inválido ou campos obrigatórios ausentes
            CteDuplicadoError: chave_cte já existe no sistema
        '''
        logger.info(f"Importando CT-e de XML: {nome_arquivo or 'stream'}")

        # 1. Parse do XML
        dados: CTeData = parsear_cte_xml(conteudo_xml)
        chave_cte = dados['chave_acesso']

        # 2. Verifica duplicidade
        if self.repo.existe_por_chave(chave_cte):
            raise CteDuplicadoError(
                f"CT-e com chave {chave_cte} já existe no sistema."
            )

        # 3. Cria model Cte
        cte = Cte(
            transportadora_id=transportadora_id,
            chave_cte=chave_cte,
            numero_cte=dados['numero_cte'],
            serie_cte=dados['serie'],
            data_emissao=dados['data_emissao'].date(),
            valor_total_cte=dados['valor_frete'],
            valor_frete_cte=dados['valor_frete'],
            origem=OrigemCte.XML,
            arquivo_origem=nome_arquivo,
            status=StatusCte.IMPORTADO,
            total_rateado=Decimal('0.00'),
        )

        # 4. Persiste
        cte = self.repo.salvar(cte)
        self.session.commit()

        logger.info(
            f"CT-e {cte.numero_cte} importado com sucesso "
            f"(ID: {cte.id}, chave: {chave_cte})"
        )

        return cte

    # ─────────────────────────────────────────────
    # 🔗 2. VINCULAR CT-e A EMBARQUE
    # ─────────────────────────────────────────────

    def vincular_a_embarque(
        self,
        cte_id: UUID,
        embarque_id: UUID,
    ) -> Cte:
        '''
        🎯 Vincula CT-e a um embarque para auditoria.

        📐 VALIDAÇÕES:
            - CT-e existe e não está cancelado
            - CT-e ainda não está vinculado a outro embarque
            - Embarque existe e está com status ENVIADO

        🎯 PARÂMETROS:
            cte_id: UUID do CT-e a vincular
            embarque_id: UUID do embarque destino

        🎯 RETORNA:
            Cte com embarque_id preenchido e status = VINCULADO

        ❌ LANÇA:
            CteCanceladoError: CT-e está cancelado
            CteJaVinculadoError: CT-e já vinculado a outro embarque
            EmbarqueNaoEnviadoError: embarque não está ENVIADO
        '''
        logger.info(f"Vinculando CT-e {cte_id} ao embarque {embarque_id}")

        # 1. Busca CT-e
        cte = self.repo.buscar_por_id(cte_id)
        if cte is None:
            raise AuditoriaCteError(f"CT-e {cte_id} não encontrado.")

        # 2. Verifica se está cancelado
        if cte.status == StatusCte.CANCELADO:
            raise CteCanceladoError(
                f"CT-e {cte.numero_cte} está cancelado."
            )

        # 3. Verifica se já está vinculado
        if cte.embarque_id is not None:
            raise CteJaVinculadoError(
                f"CT-e {cte.numero_cte} já está vinculado ao "
                f"embarque {cte.embarque_id}."
            )

        # 4. Busca embarque
        embarque = self.session.get(Embarque, embarque_id)
        if embarque is None:
            raise AuditoriaCteError(f"Embarque {embarque_id} não encontrado.")

        # 5. Verifica status do embarque
        if embarque.status != StatusEmbarque.ENVIADO:
            raise EmbarqueNaoEnviadoError(
                f"Embarque {embarque.codigo} precisa estar com status "
                f"ENVIADO para auditoria (atual: {embarque.status.value})."
            )

        # 6. Vincula
        cte.embarque_id = embarque_id
        cte.status = StatusCte.VINCULADO

        cte = self.repo.salvar(cte)
        self.session.commit()

        logger.info(
            f"CT-e {cte.numero_cte} vinculado ao embarque "
            f"{embarque.codigo} com sucesso."
        )

        return cte

    # ─────────────────────────────────────────────
    # 🧮 3. AUDITAR (RATEAR + COMPARAR)
    # ─────────────────────────────────────────────

    def auditar(self, cte_id: UUID) -> Cte:
        '''
        🎯 Executa auditoria completa do CT-e.

        📐 FLUXO:
            1. Valida pré-condições (CT-e vinculado, NFs calculadas)
            2. Remove itens anteriores (se houver)
            3. Rateia valor_total_cte entre NFs do embarque
            4. Para cada NF: cria ItemCte com divergência
            5. Atualiza total_rateado do CT-e
            6. Determina status final (AUDITADO ou DIVERGENTE)
            7. Atualiza status do embarque para AUDITADO

        🎯 PARÂMETROS:
            cte_id: UUID do CT-e a auditar

        🎯 RETORNA:
            Cte com itens populados e status atualizado

        ❌ LANÇA:
            CteCanceladoError: CT-e está cancelado
            AuditoriaCteError: CT-e não está vinculado
            NfSemCalculoError: alguma NF não tem cálculo
        '''
        logger.info(f"Iniciando auditoria do CT-e {cte_id}")

        # 1. Busca CT-e com embarque
        cte = self.repo.buscar_por_id(cte_id)
        if cte is None:
            raise AuditoriaCteError(f"CT-e {cte_id} não encontrado.")

        if cte.status == StatusCte.CANCELADO:
            raise CteCanceladoError(
                f"CT-e {cte.numero_cte} está cancelado."
            )

        if cte.embarque_id is None:
            raise AuditoriaCteError(
                f"CT-e {cte.numero_cte} não está vinculado a nenhum embarque."
            )

        # 2. Busca embarque com NFs
        embarque = self.session.get(Embarque, cte.embarque_id)
        nfs = (
            self.session.query(NotaFiscal)
            .filter(
                NotaFiscal.embarque_id == embarque.id,
                NotaFiscal.status_calculo != StatusCalculoNF.IGNORADA,
            )
            .all()
        )

        if not nfs:
            raise AuditoriaCteError(
                f"Embarque {embarque.codigo} não possui NFs para auditoria."
            )

        # 3. Valida se todas as NFs têm cálculo
        for nf in nfs:
            if nf.status_calculo != StatusCalculoNF.CALCULADO:
                raise NfSemCalculoError(
                    f"NF {nf.numero_nf} não tem cálculo de frete "
                    f"(status: {nf.status_calculo.value})."
                )

        # 4. Remove itens anteriores (se houver)
        self.repo.excluir_itens(cte.id)

        # 5. Rateia valor entre NFs
        itens_criados = self._ratear_valor_entre_nfs(cte, nfs)

        # 6. Atualiza total_rateado
        cte.total_rateado = sum(
            item.valor_rateado for item in itens_criados
        )

        # 7. Determina status final
        tem_divergencia = any(
            abs(item.divergencia_percentual or 0) > TOLERANCIA_DIVERGENCIA_PERCENTUAL
            for item in itens_criados
        )

        cte.status = (
            StatusCte.DIVERGENTE if tem_divergencia else StatusCte.AUDITADO
        )

        # 8. Persiste CT-e
        cte = self.repo.salvar(cte)

        # 9. Atualiza status do embarque
        embarque.status = StatusEmbarque.AUDITADO
        self.session.flush()

        self.session.commit()

        logger.info(
            f"Auditoria do CT-e {cte.numero_cte} concluída. "
            f"Status: {cte.status.value}, "
            f"Total rateado: R$ {cte.total_rateado}, "
            f"Divergências: {sum(1 for i in itens_criados if abs(i.divergencia_percentual or 0) > TOLERANCIA_DIVERGENCIA_PERCENTUAL)}"
        )

        return cte

    # ─────────────────────────────────────────────
    # 🔧 MÉTODOS PRIVADOS
    # ─────────────────────────────────────────────

    def _ratear_valor_entre_nfs(
        self,
        cte: Cte,
        nfs: list[NotaFiscal],
    ) -> list[ItemCte]:
        '''
        🎯 Rateia valor_total_cte entre as NFs.

        📐 REGRA (Seção 8.3):
            - Rateio igualitário: valor / qtd_nfs
            - Resíduo na 1ª NF (garante soma exata)
            - Snapshot imutável do valor_calculado

        🎯 PARÂMETROS:
            cte: CT-e com valor_total_cte
            nfs: lista de NFs do embarque

        🎯 RETORNA:
            Lista de ItemCte criados (não persistidos ainda)
        '''
        valor_total = cte.valor_total_cte
        qtd_nfs = len(nfs)

        # Rateio igualitário
        valor_por_nf = (valor_total / qtd_nfs).quantize(
            PRECISAO_DECIMAL, rounding=ROUND_HALF_UP
        )

        itens: list[ItemCte] = []

        for idx, nf in enumerate(nfs):
            # 1ª NF recebe o resíduo para garantir soma exata
            if idx == 0:
                valor_rateado = valor_total - (valor_por_nf * (qtd_nfs - 1))
            else:
                valor_rateado = valor_por_nf

            # Snapshot do valor calculado
            valor_calculado = nf.valor_calculado or Decimal('0.00')

            # Divergência
            divergencia = valor_rateado - valor_calculado

            # Divergência percentual
            if valor_calculado > 0:
                divergencia_percentual = (
                    (divergencia / valor_calculado) * 100
                ).quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP)
            else:
                divergencia_percentual = None

            # Cria ItemCte
            item = ItemCte(
                cte_id=cte.id,
                nota_fiscal_id=nf.id,
                valor_rateado=valor_rateado,
                valor_calculado=valor_calculado,
                divergencia=divergencia,
                divergencia_percentual=divergencia_percentual,
            )

            # Persiste item
            self.session.add(item)
            itens.append(item)

        self.session.flush()

        return itens


# ═════════════════════════════════════════════════
# 🏷️  FUNÇÕES AUXILIARES (facade)
# ═════════════════════════════════════════════════

def importar_cte_xml(
    session: Session,
    conteudo_xml: str | bytes,
    transportadora_id: UUID,
    nome_arquivo: str | None = None,
) -> Cte:
    '''
    🎯 Facade para importar CT-e de XML.

    📐 Uso simplificado:
        cte = importar_cte_xml(session, xml, transportadora_id)
    '''
    service = AuditoriaCteService(session)
    return service.importar_xml(conteudo_xml, transportadora_id, nome_arquivo)


def vincular_cte_a_embarque(
    session: Session,
    cte_id: UUID,
    embarque_id: UUID,
) -> Cte:
    '''
    🎯 Facade para vincular CT-e a embarque.

    📐 Uso simplificado:
        cte = vincular_cte_a_embarque(session, cte_id, embarque_id)
    '''
    service = AuditoriaCteService(session)
    return service.vincular_a_embarque(cte_id, embarque_id)


def auditar_cte(session: Session, cte_id: UUID) -> Cte:
    '''
    🎯 Facade para auditar CT-e.

    📐 Uso simplificado:
        cte = auditar_cte(session, cte_id)
    '''
    service = AuditoriaCteService(session)
    return service.auditar(cte_id)
