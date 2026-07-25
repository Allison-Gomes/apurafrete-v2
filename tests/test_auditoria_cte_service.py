'''
tests/test_auditoria_cte_service.py
====================================

Testes unitários do service de auditoria de CT-e.
--------------------------------------------------

🎯 OBJETIVO:
    Cobrir todos os métodos públicos de AuditoriaCteService com pytest + mock,
    sem conexão com banco de dados real.

📐 COBERTURA:
    - importar_xml(): sucesso, duplicidade, parsing error
    - vincular_a_embarque(): sucesso, já vinculado, cancelado, embarque não enviado
    - auditar(): conforme, divergente, NF sem cálculo, não vinculado, cancelado

📋 GRUPOS DE TESTES:
    - TestImportarXml (2 cenários)
    - TestVincularAEmbarque (4 cenários)
    - TestAuditar (7 cenários)

📦 DEPENDÊNCIAS REAIS:
    - app/services/auditoria_cte_service.py (AuditoriaCteService)
    - app/services/cte_parser_service.py (parsear_cte_xml)
    - app/models/cte.py (Cte, ItemCte, StatusCte, OrigemCte)
    - app/models/embarque.py (Embarque, StatusEmbarque)
    - app/models/nota_fiscal.py (NotaFiscal, StatusCalculoNF)
    - app/repositories/cte_repository.py (CteRepository)

📅 DATAS:
    - Criação: 25/07/2026
    - Atualização: 25/07/2026 (correções: data_emissao datetime,
      side_effect no mock_repo.salvar, StatusEmbarque.RASCUNHO)
    - Autor: ADillTech — ApuraFrete
'''

from datetime import date, datetime
from decimal import Decimal
from unittest.mock import MagicMock, Mock, PropertyMock, patch
from uuid import uuid4

import pytest

from app.models.cte import Cte, StatusCte, OrigemCte
from app.models.embarque import Embarque, StatusEmbarque
from app.models.nota_fiscal import NotaFiscal, StatusCalculoNF
from app.services.auditoria_cte_service import (
    AuditoriaCteService,
    AuditoriaCteError,
    CteDuplicadoError,
    CteJaVinculadoError,
    CteCanceladoError,
    EmbarqueNaoEnviadoError,
    NfSemCalculoError,
    TOLERANCIA_DIVERGENCIA_PERCENTUAL,
)


# ============================================================
# FIXTURES
# ============================================================

@pytest.fixture
def mock_db():
    '''🎯 Mock da Session do SQLAlchemy.'''
    session = MagicMock()
    session.commit = MagicMock()
    session.flush = MagicMock()
    session.add = MagicMock()
    return session


@pytest.fixture
def transportadora_id():
    '''🎯 UUID da transportadora para testes.'''
    return uuid4()


@pytest.fixture
def cte_id():
    '''🎯 UUID de CT-e para testes.'''
    return uuid4()


@pytest.fixture
def embarque_id():
    '''🎯 UUID de embarque para testes.'''
    return uuid4()


@pytest.fixture
def valid_cte_xml():
    '''🎯 XML de CT-e válido (bytes).'''
    return b"<CTe xmlns='http://www.portalfiscal.inf.br/cte'>...</CTe>"


@pytest.fixture
def valid_cte_data():
    '''🎯 Dicionário CTeData retornado pelo parser.'''
    return {
        'chave_acesso': '35251044687723000186570010000026811000061267',
        'numero_cte': 2681,
        'serie': 1,
        # ✅ Correção: datetime em vez de date (service chama .date())
        'data_emissao': datetime(2026, 7, 20, 10, 0, 0),
        'valor_frete': Decimal('1523.45'),
    }


# ============================================================
# HELPERS
# ============================================================

def _patch_repo(mock_db):
    '''
    🎯 Configura o mock do CteRepository no __init__ do service.
    📐 Retorna (mock_repo, service) prontos.

    ⚠️  salvar() usa side_effect=lambda obj: obj para que:
        - self.repo.salvar(cte) retorne o próprio objeto passado
        - os atributos alterados pelo service (status, embarque_id, etc.)
          persistam no objeto retornado
    '''
    with patch('app.services.auditoria_cte_service.CteRepository') as MockRepo:
        mock_repo = MagicMock()
        # ✅ Correção: side_effect garante que salvar() devolve o mesmo objeto
        mock_repo.salvar.side_effect = lambda obj: obj
        MockRepo.return_value = mock_repo
        service = AuditoriaCteService(mock_db)
        return mock_repo, service


def _mock_session_get(mock_db, model_class, return_value):
    '''
    🎯 Configura mock_db.get() para retornar um objeto mockado.
    📐 Ex: _mock_session_get(mock_db, Embarque, embarque_mock)
    '''
    def get_side_effect(model, obj_id):
        if model is model_class:
            return return_value
        return None
    mock_db.get = MagicMock(side_effect=get_side_effect)


def _mock_nf_query(mock_db, nfs):
    '''
    🎯 Configura mock_db.query(NotaFiscal).filter(...).all() → nfs.
    '''
    mock_filter = MagicMock()
    mock_filter.all.return_value = nfs
    mock_query = MagicMock()
    mock_query.filter.return_value = mock_filter

    def query_side_effect(model):
        if model is NotaFiscal:
            return mock_query
        return MagicMock()

    mock_db.query = MagicMock(side_effect=query_side_effect)


# ============================================================
# GRUPO 1: IMPORTAR XML
# ============================================================

class TestImportarXml:
    '''🎯 Testes do método importar_xml().'''

    def test_importar_xml_sucesso(
        self, mock_db, transportadora_id, valid_cte_xml, valid_cte_data
    ):
        '''
        🎯 Cenário: XML válido, chave única.
        📐 Esperado: CT-e persistido com status IMPORTADO.
        '''
        mock_repo, service = _patch_repo(mock_db)

        cte_persistido = MagicMock(spec=Cte)
        cte_persistido.numero_cte = 2681
        cte_persistido.id = uuid4()

        mock_repo.existe_por_chave.return_value = False
        # ✅ Sobrescreve side_effect para retornar o mock específico
        mock_repo.salvar.side_effect = None
        mock_repo.salvar.return_value = cte_persistido

        with patch(
            'app.services.auditoria_cte_service.parsear_cte_xml'
        ) as mock_parsear:
            mock_parsear.return_value = valid_cte_data

            # Act
            resultado = service.importar_xml(
                conteudo_xml=valid_cte_xml,
                transportadora_id=transportadora_id,
                nome_arquivo='cte_2681.xml',
            )

        # Assert
        assert resultado is cte_persistido
        mock_parsear.assert_called_once_with(valid_cte_xml)
        mock_repo.existe_por_chave.assert_called_once_with(
            '35251044687723000186570010000026811000061267'
        )
        mock_repo.salvar.assert_called_once()
        mock_db.commit.assert_called_once()

        # Verifica que o Cte foi criado com status IMPORTADO
        cte_criado = mock_repo.salvar.call_args[0][0]
        assert cte_criado.status == StatusCte.IMPORTADO
        assert cte_criado.origem == OrigemCte.XML
        assert cte_criado.arquivo_origem == 'cte_2681.xml'
        assert cte_criado.valor_total_cte == Decimal('1523.45')

    def test_importar_xml_duplicado(
        self, mock_db, transportadora_id, valid_cte_xml, valid_cte_data
    ):
        '''
        🎯 Cenário: Chave de acesso já existe.
        📐 Esperado: CteDuplicadoError.
        '''
        mock_repo, service = _patch_repo(mock_db)
        mock_repo.existe_por_chave.return_value = True

        with patch(
            'app.services.auditoria_cte_service.parsear_cte_xml'
        ) as mock_parsear:
            mock_parsear.return_value = valid_cte_data

            # Act & Assert
            with pytest.raises(CteDuplicadoError, match='já existe'):
                service.importar_xml(
                    conteudo_xml=valid_cte_xml,
                    transportadora_id=transportadora_id,
                )

        # NÃO deve chamar salvar
        mock_repo.salvar.assert_not_called()


# ============================================================
# GRUPO 2: VINCULAR A EMBARQUE
# ============================================================

class TestVincularAEmbarque:
    '''🎯 Testes do método vincular_a_embarque().'''

    def test_vincular_sucesso(
        self, mock_db, cte_id, embarque_id
    ):
        '''
        🎯 Cenário: CT-e válido, não vinculado, não cancelado.
        📐 Esperado: CT-e vinculado ao embarque, status VINCULADO.
        '''
        mock_repo, service = _patch_repo(mock_db)

        # CT-e mockado
        cte_mock = MagicMock(spec=Cte)
        cte_mock.id = cte_id
        cte_mock.numero_cte = 2681
        cte_mock.status = StatusCte.IMPORTADO
        cte_mock.embarque_id = None

        # Embarque mockado
        embarque_mock = MagicMock(spec=Embarque)
        embarque_mock.codigo = 'EMB-001'
        embarque_mock.status = StatusEmbarque.ENVIADO

        mock_repo.buscar_por_id.return_value = cte_mock
        _mock_session_get(mock_db, Embarque, embarque_mock)

        # Act
        resultado = service.vincular_a_embarque(cte_id, embarque_id)

        # Assert
        assert resultado is cte_mock
        assert cte_mock.embarque_id == embarque_id
        assert cte_mock.status == StatusCte.VINCULADO
        mock_repo.buscar_por_id.assert_called_once_with(cte_id)
        mock_repo.salvar.assert_called_once_with(cte_mock)
        mock_db.commit.assert_called_once()

    def test_vincular_cte_ja_vinculado(
        self, mock_db, cte_id, embarque_id
    ):
        '''
        🎯 Cenário: CT-e já possui embarque_id preenchido.
        📐 Esperado: CteJaVinculadoError.
        '''
        mock_repo, service = _patch_repo(mock_db)

        outro_embarque_id = uuid4()

        cte_mock = MagicMock(spec=Cte)
        cte_mock.numero_cte = 2681
        cte_mock.status = StatusCte.VINCULADO
        cte_mock.embarque_id = outro_embarque_id

        mock_repo.buscar_por_id.return_value = cte_mock

        # Act & Assert
        with pytest.raises(CteJaVinculadoError, match='já está vinculado'):
            service.vincular_a_embarque(cte_id, embarque_id)

        mock_repo.salvar.assert_not_called()

    def test_vincular_cte_cancelado(
        self, mock_db, cte_id, embarque_id
    ):
        '''
        🎯 Cenário: CT-e com status CANCELADO.
        📐 Esperado: CteCanceladoError.
        '''
        mock_repo, service = _patch_repo(mock_db)

        cte_mock = MagicMock(spec=Cte)
        cte_mock.numero_cte = 2681
        cte_mock.status = StatusCte.CANCELADO

        mock_repo.buscar_por_id.return_value = cte_mock

        # Act & Assert
        with pytest.raises(CteCanceladoError, match='cancelado'):
            service.vincular_a_embarque(cte_id, embarque_id)

    def test_vincular_embarque_nao_enviado(
        self, mock_db, cte_id, embarque_id
    ):
        '''
        🎯 Cenário: Embarque com status diferente de ENVIADO.
        📐 Esperado: EmbarqueNaoEnviadoError.
        '''
        mock_repo, service = _patch_repo(mock_db)

        cte_mock = MagicMock(spec=Cte)
        cte_mock.numero_cte = 2681
        cte_mock.status = StatusCte.IMPORTADO
        cte_mock.embarque_id = None

        embarque_mock = MagicMock(spec=Embarque)
        embarque_mock.codigo = 'EMB-001'
        # ✅ Correção: RASCUNHO é um status válido da enum StatusEmbarque
        embarque_mock.status = StatusEmbarque.RASCUNHO

        mock_repo.buscar_por_id.return_value = cte_mock
        _mock_session_get(mock_db, Embarque, embarque_mock)

        # Act & Assert
        with pytest.raises(EmbarqueNaoEnviadoError, match='ENVIADO'):
            service.vincular_a_embarque(cte_id, embarque_id)


# ============================================================
# GRUPO 3: AUDITAR (RATEIO + COMPARAÇÃO)
# ============================================================

class TestAuditar:
    '''🎯 Testes do método auditar().'''

    def _setup_cte_e_nfs(
        self, mock_db, cte_id, embarque_id,
        valor_total=Decimal('1000.00'),
        status_cte=StatusCte.VINCULADO,
        status_embarque=StatusEmbarque.ENVIADO,
    ):
        '''
        🎯 Helper: configura CT-e vinculado + embarque + NFs para auditoria.
        📐 Retorna (service, cte_mock, embarque_mock).
        '''
        mock_repo, service = _patch_repo(mock_db)

        cte_mock = MagicMock(spec=Cte)
        cte_mock.id = cte_id
        cte_mock.numero_cte = 2681
        cte_mock.status = status_cte
        cte_mock.embarque_id = embarque_id
        cte_mock.valor_total_cte = valor_total
        cte_mock.total_rateado = Decimal('0.00')

        embarque_mock = MagicMock(spec=Embarque)
        embarque_mock.id = embarque_id
        embarque_mock.codigo = 'EMB-001'
        embarque_mock.status = status_embarque

        mock_repo.buscar_por_id.return_value = cte_mock
        mock_repo.excluir_itens = MagicMock()
        _mock_session_get(mock_db, Embarque, embarque_mock)

        return mock_repo, service, cte_mock, embarque_mock

    def _criar_nf_mock(self, numero, valor_calculado, status=StatusCalculoNF.CALCULADO):
        '''🎯 Cria mock de NotaFiscal para testes de auditoria.'''
        nf = MagicMock(spec=NotaFiscal)
        nf.id = uuid4()
        nf.numero_nf = numero
        nf.valor_calculado = valor_calculado
        nf.status_calculo = status
        nf.embarque_id = None  # será preenchido pelo contexto
        return nf

    # ──────────────────────────────────
    # Cenário 1: CONFORME (divergência ≤ 5%)
    # ──────────────────────────────────

    def test_auditar_conforme(self, mock_db, cte_id, embarque_id):
        '''
        🎯 Cenário: CT-e 1000,00 com 2 NFs (500,00 cada).
        📐 Rateado: 500,00 + 500,00 → divergência 0%.
        📐 Esperado: status = AUDITADO, embarque = AUDITADO.
        '''
        mock_repo, service, cte_mock, embarque_mock = self._setup_cte_e_nfs(
            mock_db, cte_id, embarque_id, valor_total=Decimal('1000.00')
        )

        nf1 = self._criar_nf_mock('001', Decimal('500.00'))
        nf2 = self._criar_nf_mock('002', Decimal('500.00'))
        _mock_nf_query(mock_db, [nf1, nf2])

        # Act
        resultado = service.auditar(cte_id)

        # Assert
        assert resultado.status == StatusCte.AUDITADO
        assert embarque_mock.status == StatusEmbarque.AUDITADO

        # Verifica que 2 itens foram criados
        assert mock_db.add.call_count == 2

        # Verifica os valores rateados nos itens (iguais, sem resíduo)
        chamadas = mock_db.add.call_args_list
        item1 = chamadas[0][0][0]
        item2 = chamadas[1][0][0]
        assert item1.valor_rateado == Decimal('500.00')
        assert item2.valor_rateado == Decimal('500.00')
        assert item1.divergencia == Decimal('0.00')

        # total_rateado deve ser 1000.00
        assert cte_mock.total_rateado == Decimal('1000.00')

    # ──────────────────────────────────
    # Cenário 2: DIVERGENTE (> 5%)
    # ──────────────────────────────────

    def test_auditar_divergente(self, mock_db, cte_id, embarque_id):
        '''
        🎯 Cenário: CT-e 1000,00 com NF única de 850,00.
        📐 Rateado: 1000,00 → divergência 150,00 (17,6%).
        📐 Esperado: status = DIVERGENTE.
        '''
        mock_repo, service, cte_mock, embarque_mock = self._setup_cte_e_nfs(
            mock_db, cte_id, embarque_id, valor_total=Decimal('1000.00')
        )

        nf1 = self._criar_nf_mock('001', Decimal('850.00'))
        _mock_nf_query(mock_db, [nf1])

        # Act
        resultado = service.auditar(cte_id)

        # Assert
        assert resultado.status == StatusCte.DIVERGENTE

        # Verifica item
        item = mock_db.add.call_args[0][0]
        assert item.valor_rateado == Decimal('1000.00')
        assert item.divergencia == Decimal('150.00')
        assert item.divergencia_percentual > TOLERANCIA_DIVERGENCIA_PERCENTUAL

    # ──────────────────────────────────
    # Cenário 3: NF sem cálculo
    # ──────────────────────────────────

    def test_auditar_nf_sem_calculo(self, mock_db, cte_id, embarque_id):
        '''
        🎯 Cenário: Uma das NFs não tem status CALCULADO.
        📐 Esperado: NfSemCalculoError.
        '''
        mock_repo, service, cte_mock, embarque_mock = self._setup_cte_e_nfs(
            mock_db, cte_id, embarque_id, valor_total=Decimal('1000.00')
        )

        nf1 = self._criar_nf_mock('001', Decimal('500.00'))
        nf2 = self._criar_nf_mock('002', Decimal('500.00'), status=StatusCalculoNF.PENDENTE)
        _mock_nf_query(mock_db, [nf1, nf2])

        # Act & Assert
        with pytest.raises(NfSemCalculoError, match='002'):
            service.auditar(cte_id)

    # ──────────────────────────────────
    # Cenário 4: CT-e não vinculado
    # ──────────────────────────────────

    def test_auditar_cte_nao_vinculado(self, mock_db, cte_id):
        '''
        🎯 Cenário: CT-e sem embarque_id.
        📐 Esperado: AuditoriaCteError.
        '''
        mock_repo, service = _patch_repo(mock_db)

        cte_mock = MagicMock(spec=Cte)
        cte_mock.numero_cte = 2681
        cte_mock.status = StatusCte.IMPORTADO
        cte_mock.embarque_id = None

        mock_repo.buscar_por_id.return_value = cte_mock

        # Act & Assert
        with pytest.raises(AuditoriaCteError, match='não está vinculado'):
            service.auditar(cte_id)

    # ──────────────────────────────────
    # Cenário 5: CT-e cancelado
    # ──────────────────────────────────

    def test_auditar_cte_cancelado(self, mock_db, cte_id):
        '''
        🎯 Cenário: CT-e com status CANCELADO.
        📐 Esperado: CteCanceladoError.
        '''
        mock_repo, service = _patch_repo(mock_db)

        cte_mock = MagicMock(spec=Cte)
        cte_mock.numero_cte = 2681
        cte_mock.status = StatusCte.CANCELADO

        mock_repo.buscar_por_id.return_value = cte_mock

        # Act & Assert
        with pytest.raises(CteCanceladoError, match='cancelado'):
            service.auditar(cte_id)

    # ──────────────────────────────────
    # Cenário 6: Rateio com resíduo
    # ──────────────────────────────────

    def test_auditar_rateio_com_residuo(self, mock_db, cte_id, embarque_id):
        '''
        🎯 Cenário: CT-e 100,00 com 3 NFs.
        📐 Rateado: 33,34 + 33,33 + 33,33 = 100,00.
        📐 Regra (Seção 8.3): resíduo na 1ª NF (ordem do embarque).
        '''
        mock_repo, service, cte_mock, embarque_mock = self._setup_cte_e_nfs(
            mock_db, cte_id, embarque_id, valor_total=Decimal('100.00')
        )

        nf1 = self._criar_nf_mock('001', Decimal('33.33'))
        nf2 = self._criar_nf_mock('002', Decimal('33.33'))
        nf3 = self._criar_nf_mock('003', Decimal('33.33'))
        _mock_nf_query(mock_db, [nf1, nf2, nf3])

        # Act
        resultado = service.auditar(cte_id)

        # Assert
        chamadas = mock_db.add.call_args_list
        assert len(chamadas) == 3

        item1 = chamadas[0][0][0]
        item2 = chamadas[1][0][0]
        item3 = chamadas[2][0][0]

        # 1ª NF recebe o resíduo
        assert item1.valor_rateado == Decimal('33.34')
        assert item2.valor_rateado == Decimal('33.33')
        assert item3.valor_rateado == Decimal('33.33')

        # Soma exata
        total = item1.valor_rateado + item2.valor_rateado + item3.valor_rateado
        assert total == Decimal('100.00')

        # total_rateado do CT-e correto
        assert cte_mock.total_rateado == Decimal('100.00')

    # ──────────────────────────────────
    # Cenário 7: Sem NFs no embarque
    # ──────────────────────────────────

    def test_auditar_embarque_sem_nfs(self, mock_db, cte_id, embarque_id):
        '''
        🎯 Cenário: Embarque sem NFs para auditoria.
        📐 Esperado: AuditoriaCteError.
        '''
        mock_repo, service, cte_mock, embarque_mock = self._setup_cte_e_nfs(
            mock_db, cte_id, embarque_id, valor_total=Decimal('1000.00')
        )

        _mock_nf_query(mock_db, [])  # zero NFs

        # Act & Assert
        with pytest.raises(AuditoriaCteError, match='não possui NFs'):
            service.auditar(cte_id)


# ============================================================
# GRUPO 4: EXCEÇÕES (hierarquia)
# ============================================================

class TestExcecoes:
    '''🎯 Testes da hierarquia de exceções do service.'''

    def test_cte_duplicado_eh_auditoria_cte_error(self):
        '''🎯 CteDuplicadoError herda de AuditoriaCteError.'''
        assert issubclass(CteDuplicadoError, AuditoriaCteError)

    def test_cte_ja_vinculado_eh_auditoria_cte_error(self):
        '''🎯 CteJaVinculadoError herda de AuditoriaCteError.'''
        assert issubclass(CteJaVinculadoError, AuditoriaCteError)

    def test_cte_cancelado_eh_auditoria_cte_error(self):
        '''🎯 CteCanceladoError herda de AuditoriaCteError.'''
        assert issubclass(CteCanceladoError, AuditoriaCteError)

    def test_embarque_nao_enviado_eh_auditoria_cte_error(self):
        '''🎯 EmbarqueNaoEnviadoError herda de AuditoriaCteError.'''
        assert issubclass(EmbarqueNaoEnviadoError, AuditoriaCteError)

    def test_nf_sem_calculo_eh_auditoria_cte_error(self):
        '''🎯 NfSemCalculoError herda de AuditoriaCteError.'''
        assert issubclass(NfSemCalculoError, AuditoriaCteError)

    def test_tolerancia_padrao_eh_5_porcento(self):
        '''🎯 TOLERANCIA_DIVERGENCIA_PERCENTUAL = 5.00.'''
        assert TOLERANCIA_DIVERGENCIA_PERCENTUAL == Decimal('5.00')
