'''
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📁 ARQUIVO : tests/test_split_cidade_uf.py
📦 MÓDULO  : Testes / Embarque - Importação de NF
🎯 OBJETIVO: Blindar o contrato de normalização geográfica
             da importação de NF (_split_cidade_uf).
📐 REGRA    : Decisao #73 (opção 1) | RN v2.9 secao 1.9
             A chave de rota gravada na NF deve ser IDENTICA
             a gravada em rotas_frete.cidade_normalizada.
⚠️ CRITICO : Se algum teste aqui quebrar, o calculo de frete
             passa a gerar falso SEM_ROTA SILENCIOSO.
🔗 DEPENDE  : app/services/validacao_service.py
             app/utils/normalizacao.py
📅 CRIADO   : 01/08/2026
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
'''

from __future__ import annotations

import pytest

from app.exceptions.validacao_exceptions import ErroCampoError
from app.services.validacao_service import _split_cidade_uf
from app.utils.normalizacao import normalizar_cidade


# ─────────────────────────────────────────────────
# ✅ CASOS VÁLIDOS
# ─────────────────────────────────────────────────
CASOS_VALIDOS = [
    # (entrada, cidade_esperada, uf_esperada, motivo)
    ('Mogi-Mirim - SP', 'MOGI-MIRIM', 'SP',
     'hifen SEM espaco pertence a cidade'),
    ('Mogi-Mirim SP', 'MOGI-MIRIM', 'SP',
     'fallback sem separador explicito'),
    ('Sao Jose dos Campos/SP', 'SAO JOSE DOS CAMPOS', 'SP',
     'barra e separador'),
    ('Santa Barbara d Oeste, SP', 'SANTA BARBARA D OESTE', 'SP',
     'virgula e separador'),
    ('Santana do L. Paraiso - MG', 'SANTANA DO L PARAISO', 'MG',
     'ponto e removido pela fonte unica'),
    ('Embu (SP) - SP', 'EMBU SP', 'SP',
     'parenteses sao removidos'),
    ('São josé dos Campos  -  sp', 'SAO JOSE DOS CAMPOS', 'SP',
     'acento, caixa e espacos multiplos'),
    ('  Campinas - sp  ', 'CAMPINAS', 'SP',
     'trim nas bordas'),
    ('Espigão D Oeste – RO', 'ESPIGAO D OESTE', 'RO',
     'travessao com espaco e separador'),
]


@pytest.mark.parametrize(
    'entrada,cidade,uf,motivo',
    CASOS_VALIDOS,
    ids=[c[0] for c in CASOS_VALIDOS],
)
def test_split_cidade_uf_valido(entrada, cidade, uf, motivo):
    '''
    🎯 O QUE FAZ:
        Garante que entradas aceitas produzem a cidade
        normalizada e a UF esperadas.

    📐 REGRA DE NEGÓCIO:
        - Hifen sem espaco NAO separa (fica na cidade).
        - Ponto, parenteses e acento sao removidos.
        - O 3o retorno e sempre o valor RAW original.
    '''
    resultado_cidade, resultado_uf, raw = _split_cidade_uf(
        entrada, campo='cidade_uf_destino'
    )

    assert resultado_cidade == cidade, motivo
    assert resultado_uf == uf, motivo
    assert raw == entrada.strip(), 'raw deve preservar o original'


# ─────────────────────────────────────────────────
# ❌ CASOS INVÁLIDOS
# ─────────────────────────────────────────────────
CASOS_INVALIDOS = [
    ('Cidade - SPX', 'UF com 3 letras nao pode ser truncada p/ SP'),
    ('Cidade - S', 'UF com 1 letra'),
    ('Cidade - XX', 'UF fora das 27 unidades federativas'),
    ('SP', 'somente UF, sem cidade'),
    ('Campinas', 'somente cidade, sem UF'),
    ('- SP', 'cidade vazia antes do separador'),
    ('!!! - SP', 'cidade sem nenhum caractere valido'),
    ('   ', 'string em branco'),
    (None, 'valor ausente'),
]


@pytest.mark.parametrize(
    'entrada,motivo',
    CASOS_INVALIDOS,
    ids=[str(c[0]) for c in CASOS_INVALIDOS],
)
def test_split_cidade_uf_invalido(entrada, motivo):
    '''
    🎯 O QUE FAZ:
        Garante que entradas malformadas levantam
        ErroCampoError (StatusNF.ERRO_CAMPO), rejeitando
        apenas a LINHA e nunca o lote.

    ⚠️ ATENÇÃO:
        'Cidade - SPX' e o caso da GUARDA ANTITRUNCAMENTO:
        normalizar_uf() truncaria para 'SP' silenciosamente.
    '''
    with pytest.raises(ErroCampoError):
        _split_cidade_uf(entrada, campo='cidade_uf_destino')


# ─────────────────────────────────────────────────
# 🔒 CONTRATO COM O CADASTRO DE ROTAS (Decisão #73)
# ─────────────────────────────────────────────────
CIDADES_CADASTRO = [
    'Mogi-Mirim',
    'São José dos Campos',
    'Espigão D Oeste',
    'Santana do L. Paraiso',
]


@pytest.mark.parametrize('cidade_cadastro', CIDADES_CADASTRO)
def test_chave_da_nf_bate_com_chave_da_rota(cidade_cadastro):
    '''
    🎯 O QUE FAZ:
        Teste de REGRESSAO do bug original: compara a chave
        gerada pela IMPORTACAO DE NF ("CIDADE - UF") com a
        chave gerada pelo CADASTRO DE ROTA (cidade isolada
        passando direto por normalizar_cidade).

    📐 REGRA DE NEGÓCIO:
        As duas chaves DEVEM ser identicas. Divergencia =
        falso SEM_ROTA silencioso no calculo de frete.
    '''
    chave_rota = normalizar_cidade(cidade_cadastro)
    chave_nf, _uf, _raw = _split_cidade_uf(
        f'{cidade_cadastro} - SP', campo='cidade_uf_destino'
    )

    assert chave_nf == chave_rota, (
        f'Divergencia de chave: NF={chave_nf!r} vs ROTA={chave_rota!r}'
    )
