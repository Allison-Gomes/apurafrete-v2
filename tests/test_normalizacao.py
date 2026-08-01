'''
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📁 ARQUIVO : tests/test_normalizacao.py
🎯 OBJETIVO: Blindar a chave de casamento de rota.
📌 REGRAS  : Decisao #73 Acao 2 | RN v2.9 secao 1.9
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
'''

import pytest

from app.utils.normalizacao import normalizar_cidade, normalizar_uf


class TestSeparadorViraEspaco:
    '''
    🎯 O QUE TESTA:
        Regressao da Acao 2: separador colado NAO pode
        fundir palavras.
    '''

    @pytest.mark.parametrize('entrada,esperado', [
        ('Embu(SP)', 'EMBU SP'),
        ('Embu (SP)', 'EMBU SP'),
        ('Sto.Andre', 'STO ANDRE'),
        ('Sao Paulo/SP', 'SAO PAULO SP'),
        ('Rio,Janeiro', 'RIO JANEIRO'),
        ('Embu   (  SP  )', 'EMBU SP'),
    ])
    def test_nao_funde_palavras(self, entrada, esperado):
        assert normalizar_cidade(entrada) == esperado


class TestPreservaCaracteresLegitimos:
    '''
    🎯 O QUE TESTA:
        Apostrofo e hifen sobrevivem, inclusive nas
        variantes tipograficas.
    '''

    @pytest.mark.parametrize('entrada,esperado', [
        ("Santa Bárbara d'Oeste", "SANTA BARBARA D'OESTE"),
        ('Santa Bárbara d\u2019Oeste', "SANTA BARBARA D'OESTE"),
        ('Mogi-Mirim', 'MOGI-MIRIM'),
        ('Mogi\u2013Mirim', 'MOGI-MIRIM'),
    ])
    def test_preserva(self, entrada, esperado):
        assert normalizar_cidade(entrada) == esperado


class TestIdempotencia:
    '''
    🎯 O QUE TESTA:
        f(f(x)) == f(x). Sem isso, regravar a chave
        muda o valor e a rota deixa de casar.
    '''

    @pytest.mark.parametrize('entrada', [
        'Embu(SP)', "Santa Bárbara d'Oeste", 'Sao josé dos Campos ',
        'Mogi   Mirim', 'Sto.Andre',
    ])
    def test_idempotente(self, entrada):
        uma = normalizar_cidade(entrada)
        assert normalizar_cidade(uma) == uma


class TestVaziosENulos:
    '''
    🎯 O QUE TESTA:
        Entradas sem conteudo util viram None (curinga
        de UF), nunca string vazia.
    '''

    @pytest.mark.parametrize('entrada', [
        None, '', '   ', '...', '()', '///', 123, [],
    ])
    def test_retorna_none(self, entrada):
        assert normalizar_cidade(entrada) is None


class TestUF:
    '''
    🎯 O QUE TESTA:
        normalizar_uf permanece intacta — a Acao 2 nao
        a altera (UF nao tem separador interno legitimo).
    '''

    @pytest.mark.parametrize('entrada,esperado', [
        ('sp ', 'SP'), ('S.P.', 'SP'), ('sao', 'SA'),
        ('', None), (None, None), ('!!', None),
    ])
    def test_uf(self, entrada, esperado):
        assert normalizar_uf(entrada) == esperado
