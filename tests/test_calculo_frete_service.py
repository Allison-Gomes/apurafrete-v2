'''
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📁 ARQUIVO : tests/test_calculo_frete_service.py
🎯 OBJETIVO: Cobrir calcular_frete_nf() após a Decisão #73
             (resolução por rota UF+cidade, piso da rota).
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
    DestinoInvalidoError,
    RotaNaoEncontradaError,
    TabelaSemFaixasError,
    FaixaIncompletaError,
)

UF = 'SP'
CIDADE = 'Campinas'


# ─────────────────────────────────────────────────
# 🏗️ FIXTURES
# ─────────────────────────────────────────────────
def _faixa_fixa():
    return FaixaFrete(
        id=uuid4(),
        tabela_id=uuid4(),
        peso_de_kg=Decimal('0'),
        peso_ate_kg=Decimal('30'),
        valor_minimo_faixa=Decimal('150.00'),
        valor_kg=None,
    )


def _faixa_adicional():
    return FaixaFrete(
        id=uuid4(),
        tabela_id=uuid4(),
        peso_de_kg=Decimal('30'),
        peso_ate_kg=None,
        valor_minimo_faixa=None,
        valor_kg=Decimal('2.50'),
    )


def _tabela(transportadora_id, nome, faixas):
    return TabelaFrete(
        id=uuid4(),
        transportadora_id=transportadora_id,
        nome=nome,
        modalidade=ModalidadeFrete.PROGRESSIVO,
        tabela_ativa=True,
        faixas=faixas,
    )


@pytest.fixture
def transportadora_id():
    return str(uuid4())


@pytest.fixture
def rota_factory():
    '''
    🎯 O QUE FAZ:
        Constrói uma RotaFrete mockada com a tabela
        vinculada, piso e prazo configuráveis.

    ⚠️ ATENÇÃO:
        MagicMock em vez do model real: o teste não deve
        quebrar se colunas novas entrarem em RotaFrete.
    '''
    def _make(tabela, *, cidade='CAMPINAS', piso=None, prazo=3):
        rota = MagicMock()
        rota.id = uuid4()
        rota.uf = UF
        rota.cidade_normalizada = cidade
        rota.valor_minimo_rota = piso
        rota.prazo_dias = prazo
        rota.tabela = tabela
        return rota
    return _make


@pytest.fixture
def db_factory():
    '''
    🎯 O QUE FAZ:
        Session mockada cuja chain de _resolver_rota
        (query→join→filter→order_by→all) devolve a lista
        de rotas informada.
    '''
    def _make(rotas):
        db = MagicMock()
        (db.query.return_value
           .join.return_value
           .filter.return_value
           .order_by.return_value
           .all.return_value) = rotas
        return db
    return _make


@pytest.fixture
def tabela_completa(transportadora_id):
    return _tabela(
        transportadora_id,
        'Tabela Teste MVP',
        [_faixa_fixa(), _faixa_adicional()],
    )


# ─────────────────────────────────────────────────
# ✅ CÁLCULO CORRETO
# ─────────────────────────────────────────────────
class TestCalculoCorreto:
    '''
    🎯 O QUE TESTA:
        Fórmula progressiva com rota resolvida e tabela
        completa.
    '''

    @pytest.mark.parametrize(
        'peso,frete,excedente,adicional,tem_faixa_ad',
        [
            ('25.000', '150.00', '0', '0', False),
            ('30.000', '150.00', '0', '0', False),
            ('31.000', '152.50', '1.000', '2.50', True),
            ('80.000', '275.00', '50.000', '125.00', True),
        ],
        ids=['25kg', '30kg-limite', '31kg', '80kg'],
    )
    def test_formula_progressiva(
        self, db_factory, rota_factory, tabela_completa,
        transportadora_id, peso, frete, excedente,
        adicional, tem_faixa_ad,
    ):
        '''
        🎯 CENÁRIO:
            Pesos abaixo, no limite e acima de 30 kg.
        📐 FÓRMULA:
            peso ≤ 30 → 150,00
            peso > 30 → 150,00 + (peso − 30) × 2,50
        '''
        rota = rota_factory(tabela_completa)
        db = db_factory([rota])

        resultado = calcular_frete_nf(
            db=db,
            transportadora_id=transportadora_id,
            peso_total_kg=Decimal(peso),
            uf_destino=UF,
            cidade_destino=CIDADE,
            nf_id='nf-001',
        )

        assert resultado['valor_frete'] == Decimal(frete)
        assert resultado['peso_utilizado_kg'] == Decimal(peso)
        assert resultado['peso_excedente_kg'] == Decimal(excedente)
        assert resultado['valor_adicional'] == Decimal(adicional)
        assert (resultado['faixa_adicional_id'] is not None) is tem_faixa_ad
        assert resultado['piso_aplicado'] is False


# ─────────────────────────────────────────────────
# 🛣️ PISO E PRECEDÊNCIA DA ROTA
# ─────────────────────────────────────────────────
class TestRota:
    '''
    🎯 O QUE TESTA:
        Regras introduzidas na Decisão #73: piso
        valor_minimo_rota e snapshots de auditoria.
    '''

    def test_piso_da_rota_eleva_o_frete(
        self, db_factory, rota_factory, tabela_completa,
        transportadora_id,
    ):
        '''
        🎯 CENÁRIO:
            Fórmula dá R$ 150,00; piso da rota é R$ 200,00.
        📐 EXPECTATIVA:
            frete = max(150, 200) = 200,00, piso_aplicado.
        '''
        rota = rota_factory(tabela_completa, piso=Decimal('200.00'))
        db = db_factory([rota])

        resultado = calcular_frete_nf(
            db=db,
            transportadora_id=transportadora_id,
            peso_total_kg=Decimal('25.000'),
            uf_destino=UF,
            cidade_destino=CIDADE,
        )

        assert resultado['valor_frete'] == Decimal('200.00')
        assert resultado['piso_aplicado'] is True
        assert resultado['valor_minimo_rota'] == Decimal('200.00')

    def test_piso_menor_nao_altera_o_frete(
        self, db_factory, rota_factory, tabela_completa,
        transportadora_id,
    ):
        '''
        🎯 CENÁRIO:
            Piso R$ 100,00 < fórmula R$ 150,00.
        📐 EXPECTATIVA:
            Piso NÃO é aplicado.
        '''
        rota = rota_factory(tabela_completa, piso=Decimal('100.00'))
        db = db_factory([rota])

        resultado = calcular_frete_nf(
            db=db,
            transportadora_id=transportadora_id,
            peso_total_kg=Decimal('25.000'),
            uf_destino=UF,
            cidade_destino=CIDADE,
        )

        assert resultado['valor_frete'] == Decimal('150.00')
        assert resultado['piso_aplicado'] is False

    def test_rota_curinga_marcada_no_resultado(
        self, db_factory, rota_factory, tabela_completa,
        transportadora_id,
    ):
        '''
        🎯 CENÁRIO:
            Rota vencedora tem cidade_normalizada = None.
        📐 EXPECTATIVA:
            rota_curinga=True e rota_cidade=None.
        '''
        rota = rota_factory(tabela_completa, cidade=None)
        db = db_factory([rota])

        resultado = calcular_frete_nf(
            db=db,
            transportadora_id=transportadora_id,
            peso_total_kg=Decimal('25.000'),
            uf_destino=UF,
            cidade_destino=CIDADE,
        )

        assert resultado['rota_curinga'] is True
        assert resultado['rota_cidade'] is None

    def test_precedencia_usa_a_primeira_rota_ordenada(
        self, db_factory, rota_factory, tabela_completa,
        transportadora_id,
    ):
        '''
        🎯 CENÁRIO:
            Query devolve [específica, curinga] — a ordenação
            NULLS LAST é responsabilidade do SQL.
        📐 EXPECTATIVA:
            O service consome rotas[0] (a específica).
        '''
        especifica = rota_factory(tabela_completa, cidade='CAMPINAS')
        curinga = rota_factory(tabela_completa, cidade=None)
        db = db_factory([especifica, curinga])

        resultado = calcular_frete_nf(
            db=db,
            transportadora_id=transportadora_id,
            peso_total_kg=Decimal('25.000'),
            uf_destino=UF,
            cidade_destino=CIDADE,
        )

        assert resultado['rota_id'] == str(especifica.id)
        assert resultado['rota_curinga'] is False

    def test_sem_rota_ativa(self, db_factory, transportadora_id):
        '''
        🎯 CENÁRIO:
            Nenhuma rota ativa atende o destino.
        📐 EXPECTATIVA:
            Lança RotaNaoEncontradaError.

        ⚠️ ATENÇÃO:
            Tabela inativa também cai aqui: o filtro
            tabela_ativa está no JOIN de _resolver_rota.
        '''
        db = db_factory([])

        with pytest.raises(RotaNaoEncontradaError) as exc:
            calcular_frete_nf(
                db=db,
                transportadora_id=transportadora_id,
                peso_total_kg=Decimal('50.000'),
                uf_destino=UF,
                cidade_destino=CIDADE,
            )

        assert 'não possui rota ativa' in str(exc.value)


# ─────────────────────────────────────────────────
# ❌ VALIDAÇÃO DE PESO E DESTINO
# ─────────────────────────────────────────────────
class TestValidacoes:
    '''
    🎯 O QUE TESTA:
        Guardas de entrada: peso e UF de destino.
    '''

    @pytest.mark.parametrize(
        'peso,trecho',
        [
            (Decimal('0'), 'deve ser > 0'),
            (Decimal('-10.000'), 'deve ser > 0'),
            (None, 'obrigatório'),
        ],
        ids=['zero', 'negativo', 'none'],
    )
    def test_peso_invalido(
        self, db_factory, transportadora_id, peso, trecho,
    ):
        '''
        🎯 CENÁRIO:
            Peso zero, negativo ou ausente.
        📐 EXPECTATIVA:
            Lança PesoInvalidoError antes de tocar no banco.
        '''
        db = db_factory([])

        with pytest.raises(PesoInvalidoError) as exc:
            calcular_frete_nf(
                db=db,
                transportadora_id=transportadora_id,
                peso_total_kg=peso,
                uf_destino=UF,
                cidade_destino=CIDADE,
            )

        assert trecho in str(exc.value)

    @pytest.mark.parametrize(
        'uf', [None, '', '   ', '!!'], ids=['none', 'vazia', 'espacos', 'simbolos'],
    )
    def test_uf_destino_invalida(
        self, db_factory, transportadora_id, uf,
    ):
        '''
        🎯 CENÁRIO:
            UF de destino ausente ou sem letras.
        📐 EXPECTATIVA:
            Lança DestinoInvalidoError — impossível resolver
            a rota.
        '''
        db = db_factory([])

        with pytest.raises(DestinoInvalidoError):
            calcular_frete_nf(
                db=db,
                transportadora_id=transportadora_id,
                peso_total_kg=Decimal('50.000'),
                uf_destino=uf,
                cidade_destino=CIDADE,
            )

    def test_cidade_destino_opcional(
        self, db_factory, rota_factory, tabela_completa,
        transportadora_id,
    ):
        '''
        🎯 CENÁRIO:
            NF sem cidade de destino.
        📐 EXPECTATIVA:
            Não levanta erro — resolve pelo curinga da UF.
        '''
        rota = rota_factory(tabela_completa, cidade=None)
        db = db_factory([rota])

        resultado = calcular_frete_nf(
            db=db,
            transportadora_id=transportadora_id,
            peso_total_kg=Decimal('25.000'),
            uf_destino=UF,
            cidade_destino=None,
        )

        assert resultado['valor_frete'] == Decimal('150.00')


# ─────────────────────────────────────────────────
# ❌ CONFIGURAÇÃO DA TABELA
# ─────────────────────────────────────────────────
class TestConfiguracaoTabela:
    '''
    🎯 O QUE TESTA:
        Tabela vinculada à rota com faixas faltando.
    '''

    def test_tabela_sem_faixas(
        self, db_factory, rota_factory, transportadora_id,
    ):
        '''
        🎯 CENÁRIO:
            Tabela da rota não tem nenhuma faixa.
        📐 EXPECTATIVA:
            Lança TabelaSemFaixasError.
        '''
        tabela = _tabela(transportadora_id, 'Tabela Vazia', [])
        db = db_factory([rota_factory(tabela)])

        with pytest.raises(TabelaSemFaixasError) as exc:
            calcular_frete_nf(
                db=db,
                transportadora_id=transportadora_id,
                peso_total_kg=Decimal('50.000'),
                uf_destino=UF,
                cidade_destino=CIDADE,
            )

        assert 'não possui' in str(exc.value)

    def test_tabela_sem_faixa_fixa(
        self, db_factory, rota_factory, transportadora_id,
    ):
        '''
        🎯 CENÁRIO:
            Só a faixa adicional (30→∞).
        📐 EXPECTATIVA:
            Lança FaixaIncompletaError.
        '''
        tabela = _tabela(
            transportadora_id, 'Sem fixa', [_faixa_adicional()],
        )
        db = db_factory([rota_factory(tabela)])

        with pytest.raises(FaixaIncompletaError) as exc:
            calcular_frete_nf(
                db=db,
                transportadora_id=transportadora_id,
                peso_total_kg=Decimal('50.000'),
                uf_destino=UF,
                cidade_destino=CIDADE,
            )

        assert 'faixa fixa' in str(exc.value)

    def test_tabela_sem_faixa_adicional(
        self, db_factory, rota_factory, transportadora_id,
    ):
        '''
        🎯 CENÁRIO:
            Só a faixa fixa (0→30).
        📐 EXPECTATIVA:
            Lança FaixaIncompletaError.
        '''
        tabela = _tabela(
            transportadora_id, 'Sem adicional', [_faixa_fixa()],
        )
        db = db_factory([rota_factory(tabela)])

        with pytest.raises(FaixaIncompletaError) as exc:
            calcular_frete_nf(
                db=db,
                transportadora_id=transportadora_id,
                peso_total_kg=Decimal('50.000'),
                uf_destino=UF,
                cidade_destino=CIDADE,
            )

        assert 'faixa adicional' in str(exc.value)


# ─────────────────────────────────────────────────
# 📊 METADADOS DO RESULTADO
# ─────────────────────────────────────────────────
class TestMetadadosResultado:
    '''
    🎯 O QUE TESTA:
        Contrato completo do ResultadoFrete — o que a
        auditoria de CT-e vai consumir.
    '''

    CAMPOS = [
        'valor_frete', 'peso_utilizado_kg', 'tabela_id',
        'tabela_nome', 'modalidade', 'rota_id', 'rota_uf',
        'rota_cidade', 'rota_curinga', 'prazo_dias',
        'faixa_fixa_id', 'valor_fixo', 'faixa_adicional_id',
        'valor_adicional', 'peso_excedente_kg',
        'valor_minimo_rota', 'piso_aplicado',
    ]

    def test_resultado_contem_todos_os_campos(
        self, db_factory, rota_factory, tabela_completa,
        transportadora_id,
    ):
        '''
        🎯 CENÁRIO:
            Cálculo bem-sucedido.
        📐 EXPECTATIVA:
            Todos os campos do TypedDict presentes.
        '''
        db = db_factory([rota_factory(tabela_completa)])

        resultado = calcular_frete_nf(
            db=db,
            transportadora_id=transportadora_id,
            peso_total_kg=Decimal('50.000'),
            uf_destino=UF,
            cidade_destino=CIDADE,
        )

        for campo in self.CAMPOS:
            assert campo in resultado, f"Campo '{campo}' ausente"

    def test_snapshots_batem_com_a_origem(
        self, db_factory, rota_factory, tabela_completa,
        transportadora_id,
    ):
        '''
        🎯 CENÁRIO:
            Cálculo bem-sucedido.
        📐 EXPECTATIVA:
            Snapshots refletem tabela e rota vencedoras.
        '''
        rota = rota_factory(tabela_completa, prazo=5)
        db = db_factory([rota])

        resultado = calcular_frete_nf(
            db=db,
            transportadora_id=transportadora_id,
            peso_total_kg=Decimal('50.000'),
            uf_destino=UF,
            cidade_destino=CIDADE,
        )

        assert resultado['tabela_id'] == str(tabela_completa.id)
        assert resultado['tabela_nome'] == tabela_completa.nome
        assert resultado['modalidade'] == 'progressivo'
        assert resultado['rota_id'] == str(rota.id)
        assert resultado['rota_uf'] == UF
        assert resultado['prazo_dias'] == 5
