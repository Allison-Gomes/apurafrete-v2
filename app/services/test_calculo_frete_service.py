'''
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📁 ARQUIVO : test_calculo_frete_service.py
📦 MÓDULO  : Tests
🎯 OBJETIVO: Testar o engine de cálculo de frete
             (calculo_frete_service.py) em todos os
             cenários possíveis:
               - Cálculo correto (peso ≤ 30 e > 30)
               - Validações (peso inválido)
               - Erros de configuração (tabela/faixas)
             Usa mocks para isolar o banco de dados.
🔗 DEPENDE  : app.services.calculo_frete_service
             app.models.tabela_frete
📅 CRIADO  : 11/07/2026
📅 ATUALIZADO: 11/07/2026 — criação inicial
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
'''

from decimal import Decimal
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.models.tabela_frete import (
    TabelaFrete,
    FaixaFrete,
    ModalidadeFrete,
)
from app.services.calculo_frete_service import (
    calcular_frete_nf,
    PesoInvalidoError,
    TransportadoraSemTabelaError,
    TabelaSemFaixasError,
    FaixaIncompletaError,
)


# ─────────────────────────────────────────────────
# 🏗️ FIXTURES
# Objetos mock reutilizáveis nos testes.
# ─────────────────────────────────────────────────
@pytest.fixture
def db_mock():
    '''
    🎯 O QUE FAZ:
        Simula uma Session SQLAlchemy com query mockada.
        Não conecta no banco real.
    '''
    return MagicMock()


@pytest.fixture
def transportadora_id():
    '''
    🎯 O QUE FAZ:
        Gera um UUID fictício para a transportadora.
    '''
    return str(uuid4())


@pytest.fixture
def tabela_frete_completa(transportadora_id):
    '''
    🎯 O QUE FAZ:
        Cria uma TabelaFrete com as duas faixas
        obrigatórias do MVP (0→30 e 30→∞).

    📐 DADOS:
        - Faixa 1: 0 → 30 kg, valor_minimo = R$ 150,00
        - Faixa 2: 30 → ∞ kg, valor_kg = R$ 2,50
    '''
    faixa_fixa = FaixaFrete(
        id=uuid4(),
        tabela_id=uuid4(),
        peso_de_kg=Decimal("0"),
        peso_ate_kg=Decimal("30"),
        valor_minimo_faixa=Decimal("150.00"),
        valor_kg=None,
    )

    faixa_adicional = FaixaFrete(
        id=uuid4(),
        tabela_id=uuid4(),
        peso_de_kg=Decimal("30"),
        peso_ate_kg=None,  # Aberta
        valor_minimo_faixa=None,
        valor_kg=Decimal("2.50"),
    )

    tabela = TabelaFrete(
        id=uuid4(),
        transportadora_id=transportadora_id,
        nome="Tabela Teste MVP",
        modalidade=ModalidadeFrete.PROGRESSIVO,
        tabela_ativa=True,
        faixas=[faixa_fixa, faixa_adicional],
    )

    return tabela


@pytest.fixture
def tabela_sem_faixas(transportadora_id):
    '''
    🎯 O QUE FAZ:
        Cria uma TabelaFrete sem nenhuma faixa.
    '''
    return TabelaFrete(
        id=uuid4(),
        transportadora_id=transportadora_id,
        nome="Tabela Vazia",
        modalidade=ModalidadeFrete.PROGRESSIVO,
        tabela_ativa=True,
        faixas=[],
    )


@pytest.fixture
def tabela_sem_faixa_fixa(transportadora_id):
    '''
    🎯 O QUE FAZ:
        Cria uma TabelaFrete apenas com a faixa
        adicional (30→∞), sem a faixa fixa (0→30).
    '''
    faixa_adicional = FaixaFrete(
        id=uuid4(),
        tabela_id=uuid4(),
        peso_de_kg=Decimal("30"),
        peso_ate_kg=None,
        valor_minimo_faixa=None,
        valor_kg=Decimal("2.50"),
    )

    return TabelaFrete(
        id=uuid4(),
        transportadora_id=transportadora_id,
        nome="Tabela Incompleta (sem fixa)",
        modalidade=ModalidadeFrete.PROGRESSIVO,
        tabela_ativa=True,
        faixas=[faixa_adicional],
    )


@pytest.fixture
def tabela_sem_faixa_adicional(transportadora_id):
    '''
    🎯 O QUE FAZ:
        Cria uma TabelaFrete apenas com a faixa
        fixa (0→30), sem a faixa adicional (30→∞).
    '''
    faixa_fixa = FaixaFrete(
        id=uuid4(),
        tabela_id=uuid4(),
        peso_de_kg=Decimal("0"),
        peso_ate_kg=Decimal("30"),
        valor_minimo_faixa=Decimal("150.00"),
        valor_kg=None,
    )

    return TabelaFrete(
        id=uuid4(),
        transportadora_id=transportadora_id,
        nome="Tabela Incompleta (sem adicional)",
        modalidade=ModalidadeFrete.PROGRESSIVO,
        tabela_ativa=True,
        faixas=[faixa_fixa],
    )


# ─────────────────────────────────────────────────
# ✅ TESTES DE CÁLCULO CORRETO
# Cenários onde o cálculo deve funcionar.
# ─────────────────────────────────────────────────
class TestCalculoCorreto:
    '''
    🎯 O QUE TESTA:
        Cenários de cálculo bem-sucedido, onde
        a tabela está completa e o peso é válido.
    '''

    def test_peso_dentro_da_faixa_fixa(
        self, db_mock, transportadora_id, tabela_frete_completa
    ):
        '''
        🎯 CENÁRIO:
            Peso = 25 kg (≤ 30 kg).
        📐 EXPECTATIVA:
            Retorna apenas o valor fixo (R$ 150,00).
            Não usa a faixa adicional.
        '''
        # Arrange: configura o mock para retornar a tabela
        db_mock.query.return_value.filter.return_value.first.return_value = (
            tabela_frete_completa
        )

        # Act
        resultado = calcular_frete_nf(
            db=db_mock,
            transportadora_id=transportadora_id,
            peso_total_kg=Decimal("25.000"),
            nf_id="nf-teste-001",
        )

        # Assert
        assert resultado["valor_frete"] == Decimal("150.00")
        assert resultado["peso_utilizado_kg"] == Decimal("25.000")
        assert resultado["faixa_adicional_id"] is None
        assert resultado["valor_adicional"] == Decimal("0")
        assert resultado["peso_excedente_kg"] == Decimal("0")

    def test_peso_no_limite_da_faixa_fixa(
        self, db_mock, transportadora_id, tabela_frete_completa
    ):
        '''
        🎯 CENÁRIO:
            Peso = 30 kg (limite exato da faixa fixa).
        📐 EXPECTATIVA:
            Retorna apenas o valor fixo (R$ 150,00).
            Não calcula adicional.
        '''
        db_mock.query.return_value.filter.return_value.first.return_value = (
            tabela_frete_completa
        )

        resultado = calcular_frete_nf(
            db=db_mock,
            transportadora_id=transportadora_id,
            peso_total_kg=Decimal("30.000"),
        )

        assert resultado["valor_frete"] == Decimal("150.00")
        assert resultado["faixa_adicional_id"] is None
        assert resultado["peso_excedente_kg"] == Decimal("0")

    def test_peso_acima_da_faixa_fixa(
        self, db_mock, transportadora_id, tabela_frete_completa
    ):
        '''
        🎯 CENÁRIO:
            Peso = 80 kg (> 30 kg).
        📐 FÓRMULA:
            150,00 + (80 − 30) × 2,50 = 150 + 125 = R$ 275,00
        📐 EXPECTATIVA:
            Retorna valor fixo + adicional.
        '''
        db_mock.query.return_value.filter.return_value.first.return_value = (
            tabela_frete_completa
        )

        resultado = calcular_frete_nf(
            db=db_mock,
            transportadora_id=transportadora_id,
            peso_total_kg=Decimal("80.000"),
        )

        assert resultado["valor_frete"] == Decimal("275.00")
        assert resultado["peso_excedente_kg"] == Decimal("50.000")
        assert resultado["valor_adicional"] == Decimal("125.00")
        assert resultado["faixa_adicional_id"] is not None

    def test_peso_pouco_acima_do_limite(
        self, db_mock, transportadora_id, tabela_frete_completa
    ):
        '''
        🎯 CENÁRIO:
            Peso = 31 kg (apenas 1 kg acima do limite).
        📐 FÓRMULA:
            150,00 + (31 − 30) × 2,50 = 150 + 2,50 = R$ 152,50
        📐 EXPECTATIVA:
            Calcula adicional mínimo.
        '''
        db_mock.query.return_value.filter.return_value.first.return_value = (
            tabela_frete_completa
        )

        resultado = calcular_frete_nf(
            db=db_mock,
            transportadora_id=transportadora_id,
            peso_total_kg=Decimal("31.000"),
        )

        assert resultado["valor_frete"] == Decimal("152.50")
        assert resultado["peso_excedente_kg"] == Decimal("1.000")
        assert resultado["valor_adicional"] == Decimal("2.50")


# ─────────────────────────────────────────────────
# ❌ TESTES DE VALIDAÇÃO DE PESO
# Cenários onde o peso é inválido.
# ─────────────────────────────────────────────────
class TestValidacaoPeso:
    '''
    🎯 O QUE TESTA:
        Validações do peso_total_kg antes do cálculo.
    '''

    def test_peso_zero(self, db_mock, transportadora_id):
        '''
        🎯 CENÁRIO:
            Peso = 0 kg.
        📐 EXPECTATIVA:
            Lança PesoInvalidoError.
        '''
        with pytest.raises(PesoInvalidoError) as exc_info:
            calcular_frete_nf(
                db=db_mock,
                transportadora_id=transportadora_id,
                peso_total_kg=Decimal("0"),
                nf_id="nf-teste-peso-zero",
            )

        assert "deve ser > 0" in str(exc_info.value)

    def test_peso_negativo(self, db_mock, transportadora_id):
        '''
        🎯 CENÁRIO:
            Peso = -10 kg.
        📐 EXPECTATIVA:
            Lança PesoInvalidoError.
        '''
        with pytest.raises(PesoInvalidoError) as exc_info:
            calcular_frete_nf(
                db=db_mock,
                transportadora_id=transportadora_id,
                peso_total_kg=Decimal("-10.000"),
            )

        assert "deve ser > 0" in str(exc_info.value)

    def test_peso_none(self, db_mock, transportadora_id):
        '''
        🎯 CENÁRIO:
            Peso = None.
        📐 EXPECTATIVA:
            Lança PesoInvalidoError.
        '''
        with pytest.raises(PesoInvalidoError) as exc_info:
            calcular_frete_nf(
                db=db_mock,
                transportadora_id=transportadora_id,
                peso_total_kg=None,
            )

        assert "obrigatório" in str(exc_info.value)


# ─────────────────────────────────────────────────
# ❌ TESTES DE CONFIGURAÇÃO DA TABELA
# Cenários onde a tabela está mal configurada.
# ─────────────────────────────────────────────────
class TestConfiguracaoTabela:
    '''
    🎯 O QUE TESTA:
        Erros de configuração da tabela de frete
        (ausência de tabela ativa, faixas faltando).
    '''

    def test_transportadora_sem_tabela_ativa(
        self, db_mock, transportadora_id
    ):
        '''
        🎯 CENÁRIO:
            Transportadora não possui tabela ativa.
        📐 EXPECTATIVA:
            Lança TransportadoraSemTabelaError.
        '''
        # Arrange: mock retorna None (sem tabela)
        db_mock.query.return_value.filter.return_value.first.return_value = None

        with pytest.raises(TransportadoraSemTabelaError) as exc_info:
            calcular_frete_nf(
                db=db_mock,
                transportadora_id=transportadora_id,
                peso_total_kg=Decimal("50.000"),
            )

        assert "não possui tabela de frete ativa" in str(exc_info.value)

    def test_tabela_sem_faixas(
        self, db_mock, transportadora_id, tabela_sem_faixas
    ):
        '''
        🎯 CENÁRIO:
            Tabela ativa existe, mas não tem faixas.
        📐 EXPECTATIVA:
            Lança TabelaSemFaixasError.
        '''
        db_mock.query.return_value.filter.return_value.first.return_value = (
            tabela_sem_faixas
        )

        with pytest.raises(TabelaSemFaixasError) as exc_info:
            calcular_frete_nf(
                db=db_mock,
                transportadora_id=transportadora_id,
                peso_total_kg=Decimal("50.000"),
            )

        assert "não possui faixas" in str(exc_info.value)

    def test_tabela_sem_faixa_fixa(
        self, db_mock, transportadora_id, tabela_sem_faixa_fixa
    ):
        '''
        🎯 CENÁRIO:
            Tabela tem apenas a faixa adicional (30→∞),
            falta a faixa fixa (0→30).
        📐 EXPECTATIVA:
            Lança FaixaIncompletaError.
        '''
        db_mock.query.return_value.filter.return_value.first.return_value = (
            tabela_sem_faixa_fixa
        )

        with pytest.raises(FaixaIncompletaError) as exc_info:
            calcular_frete_nf(
                db=db_mock,
                transportadora_id=transportadora_id,
                peso_total_kg=Decimal("50.000"),
            )

        assert "não possui faixa fixa" in str(exc_info.value)

    def test_tabela_sem_faixa_adicional(
        self, db_mock, transportadora_id, tabela_sem_faixa_adicional
    ):
        '''
        🎯 CENÁRIO:
            Tabela tem apenas a faixa fixa (0→30),
            falta a faixa adicional (30→∞).
        📐 EXPECTATIVA:
            Lança FaixaIncompletaError.
        '''
        db_mock.query.return_value.filter.return_value.first.return_value = (
            tabela_sem_faixa_adicional
        )

        with pytest.raises(FaixaIncompletaError) as exc_info:
            calcular_frete_nf(
                db=db_mock,
                transportadora_id=transportadora_id,
                peso_total_kg=Decimal("50.000"),
            )

        assert "não possui faixa adicional" in str(exc_info.value)


# ─────────────────────────────────────────────────
# 📊 TESTES DE METADADOS DO RESULTADO
# Garante que o ResultadoFrete está completo.
# ─────────────────────────────────────────────────
class TestMetadadosResultado:
    '''
    🎯 O QUE TESTA:
        Se o dicionário ResultadoFrete contém todos
        os campos esperados para auditoria.
    '''

    def test_resultado_contem_todos_os_campos(
        self, db_mock, transportadora_id, tabela_frete_completa
    ):
        '''
        🎯 CENÁRIO:
            Cálculo bem-sucedido.
        📐 EXPECTATIVA:
            Resultado contém todos os campos do TypedDict.
        '''
        db_mock.query.return_value.filter.return_value.first.return_value = (
            tabela_frete_completa
        )

        resultado = calcular_frete_nf(
            db=db_mock,
            transportadora_id=transportadora_id,
            peso_total_kg=Decimal("50.000"),
        )

        # Verifica se todos os campos estão presentes
        campos_esperados = [
            "valor_frete",
            "peso_utilizado_kg",
            "tabela_id",
            "tabela_nome",
            "modalidade",
            "faixa_fixa_id",
            "valor_fixo",
            "faixa_adicional_id",
            "valor_adicional",
            "peso_excedente_kg",
        ]

        for campo in campos_esperados:
            assert campo in resultado, f"Campo '{campo}' ausente no resultado"

    def test_metadados_corretos(
        self, db_mock, transportadora_id, tabela_frete_completa
    ):
        '''
        🎯 CENÁRIO:
            Cálculo bem-sucedido.
        📐 EXPECTATIVA:
            Metadados (tabela_id, tabela_nome, modalidade)
            batem com os dados da tabela.
        '''
        db_mock.query.return_value.filter.return_value.first.return_value = (
            tabela_frete_completa
        )

        resultado = calcular_frete_nf(
            db=db_mock,
            transportadora_id=transportadora_id,
            peso_total_kg=Decimal("50.000"),
        )

        assert resultado["tabela_id"] == str(tabela_frete_completa.id)
        assert resultado["tabela_nome"] == tabela_frete_completa.nome
        assert resultado["modalidade"] == "progressivo"


'''
Como executar os testes:

# Executar todos os testes
pytest app/tests/test_calculo_frete_service.py -v

# Executar apenas uma classe
pytest app/tests/test_calculo_frete_service.py::TestCalculoCorreto -v

# Executar com cobertura
pytest app/tests/test_calculo_frete_service.py --cov=app.services.calculo_frete_service

'''
