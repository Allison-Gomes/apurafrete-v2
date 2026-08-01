'''
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📁 ARQUIVO : app/utils/normalizacao.py
📦 MÓDULO  : Utils
🎯 OBJETIVO: Unica fonte de verdade da normalizacao
             geografica (cidade e UF) do ApuraFrete.
📅 CRIADO  : 01/08/2026
📝 ALTERADO: 01/08/2026 — Decisao #73 Acao 2:
             caractere invalido na cidade passa a virar
             ESPACO em vez de ser removido.
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
Mapeia variantes tipograficas para o ASCII canonico ANTES
da limpeza.

⚠️ Sem esta etapa, trocar o caractere invalido por espaco
quebraria "Santa Barbara d’Oeste" (apostrofo curvo U+2019)
em "SANTA BARBARA D OESTE", pois o apostrofo curvo nao
pertence a lista de permitidos.
'''
_TIPOGRAFICOS = str.maketrans({
    '\u2018': "'", '\u2019': "'",   # ‘ ’
    '\u02bc': "'", '\u00b4': "'",   # ʼ ´
    '\u2010': '-', '\u2011': '-',   # ‐ ‑
    '\u2012': '-', '\u2013': '-',   # ‒ –
    '\u2014': '-', '\u2015': '-',   # — ―
})

'''
Caracteres preservados na cidade apos a limpeza:
letras, digitos, espaco, hifen e apostrofo.
Ex.: "Santa Barbara d'Oeste", "Mogi-Mirim".

Todo o resto e substituido por ESPACO (nunca por vazio):
"Embu(SP)" deve render "EMBU SP", jamais "EMBUSP".
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
        2. Canoniza apostrofos e hifens tipograficos
        3. NFKD, remove acentos
        4. MAIUSCULA
        5. Caractere nao permitido -> ESPACO
        6. Colapsa espacos e aplica trim
        7. Resultado vazio -> None

    ⚠️ MUDANCA (Decisao #73 Acao 2): o passo 5 substitui por
    espaco em vez de remover. Antes, "Embu(SP)" gerava "EMBUSP"
    e "Sto.Andre" gerava "STOANDRE" — chaves que nunca casavam
    com a rota cadastrada, produzindo falso SEM_ROTA.

    Args:
        valor: nome da cidade como veio da planilha ou do cadastro.

    Returns:
        Cidade normalizada em maiusculas, ou None se vazia/invalida.

    Exemplos:
        'Sao josé dos Campos '     -> 'SAO JOSE DOS CAMPOS'
        "Santa Bárbara d'Oeste"    -> "SANTA BARBARA D'OESTE"
        'Santa Bárbara d’Oeste'    -> "SANTA BARBARA D'OESTE"
        'Embu(SP)'                 -> 'EMBU SP'
        'Sto.Andre'                -> 'STO ANDRE'
        'Mogi   Mirim'             -> 'MOGI MIRIM'
        '  '                       -> None
        None                       -> None
    '''
    if valor is None or not isinstance(valor, str):
        return None

    texto = valor.translate(_TIPOGRAFICOS)
    texto = _remover_acentos(texto).upper()
    texto = _RE_CIDADE_INVALIDOS.sub(' ', texto)
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

    ⚠️ A Acao 2 NAO altera esta funcao: UF nao possui separador
    interno legitimo, portanto remover continua correto aqui.

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
