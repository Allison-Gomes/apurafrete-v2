'''
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📁 ARQUIVO : app/utils/normalizacao.py
📦 MÓDULO  : Utils
🎯 OBJETIVO: Unica fonte de verdade da normalizacao
             geografica (cidade e UF) do ApuraFrete.
📅 CRIADO  : 01/08/2026
📌 REGRAS  : Decisao #73 | RN v2.9 secao 1.9
⚠️ CRITICO : Deve ser usada TANTO ao gravar
             rotas_frete.cidade_normalizada QUANTO ao
             resolver a rota no calculo. Divergir quebra
             o calculo silenciosamente (falso SEM_ROTA).
🚫 PROIBIDO: Normalizar cidade/UF ad-hoc em qualquer
             outro ponto do sistema.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
'''

import re
import unicodedata
from typing import Optional

__all__ = ['normalizar_cidade', 'normalizar_uf']


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CONSTANTES
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

'''
Caracteres preservados na cidade apos a limpeza:
letras, digitos, espaco, hifen e apostrofo.
Ex.: "Santa Barbara d'Oeste", "Mogi-Mirim".
'''
_RE_CIDADE_INVALIDOS = re.compile(r"[^A-Z0-9 \-']")

'''Colapsa qualquer sequencia de espacos em um unico espaco.'''
_RE_ESPACOS = re.compile(r'\s+')

'''UF aceita apenas letras.'''
_RE_UF_INVALIDOS = re.compile(r'[^A-Z]')


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HELPER INTERNO
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _remover_acentos(texto: str) -> str:
    '''
    Remove acentos via decomposicao NFKD, descartando os
    caracteres combinantes (categoria Unicode "Mn").

    Ex.: 'São' -> 'Sao' | 'Bárbara' -> 'Barbara'
    '''
    decomposto = unicodedata.normalize('NFKD', texto)
    return ''.join(c for c in decomposto if not unicodedata.combining(c))


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# API PUBLICA
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def normalizar_cidade(valor: Optional[str]) -> Optional[str]:
    '''
    Normaliza o nome de uma cidade para uso como chave de rota.

    Pipeline (RN v2.9 secao 1.9):
        1. None ou nao-string  -> None
        2. NFKD, remove acentos
        3. MAIUSCULA
        4. Remove caracteres nao permitidos
           (mantem espaco, hifen e apostrofo)
        5. Colapsa espacos e aplica trim
        6. Resultado vazio -> None

    Args:
        valor: nome da cidade como veio da planilha ou do cadastro.

    Returns:
        Cidade normalizada em maiusculas, ou None se vazia/invalida.

    Exemplos:
        'Sao josé dos Campos '     -> 'SAO JOSE DOS CAMPOS'
        "Santa Bárbara d'Oeste"    -> "SANTA BARBARA D'OESTE"
        'Mogi   Mirim'             -> 'MOGI MIRIM'
        '  '                       -> None
        None                       -> None
    '''
    if valor is None or not isinstance(valor, str):
        return None

    texto = _remover_acentos(valor).upper()
    texto = _RE_CIDADE_INVALIDOS.sub('', texto)
    texto = _RE_ESPACOS.sub(' ', texto).strip()

    return texto or None


def normalizar_uf(valor: Optional[str]) -> Optional[str]:
    '''
    Normaliza a sigla de UF para uso como chave de rota.

    Pipeline (RN v2.9 secao 1.9):
        1. None ou nao-string -> None
        2. NFKD, remove acentos
        3. MAIUSCULA
        4. Remove tudo que nao for letra
        5. Trunca em 2 caracteres
        6. Resultado vazio -> None

    ⚠️ Nao valida se a UF pertence ao conjunto oficial de 27
    unidades federativas — apenas normaliza a forma. A validacao
    de dominio e responsabilidade do service de cadastro de rota.

    Args:
        valor: sigla da UF como veio da planilha ou do cadastro.

    Returns:
        UF normalizada com 2 letras maiusculas, ou None se vazia.

    Exemplos:
        'sp '   -> 'SP'
        'S.P.'  -> 'SP'
        'sao'   -> 'SA'   (truncado — validacao de dominio e do service)
        ''      -> None
        None    -> None
    '''
    if valor is None or not isinstance(valor, str):
        return None

    texto = _remover_acentos(valor).upper()
    texto = _RE_UF_INVALIDOS.sub('', texto)[:2]

    return texto or None
