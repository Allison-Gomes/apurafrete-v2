'''
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📁 ARQUIVO : services/cte_parser_service.py
📦 MÓDULO  : CT-e / Parser de XML
🎯 OBJETIVO: Extrair dados estruturados de um XML de
             CT-e (Conhecimento de Transporte Eletrônico)
             seguindo o layout oficial da SEFAZ
             (namespace: http://www.portalfiscal.inf.br/cte).

             Campos extraídos:
               - Identificação (chave, número, série, tipo, data)
               - Emitente (CNPJ, razão social)
               - Remetente (CNPJ, razão social)
               - Destinatário (CNPJ, razão social)
               - Valores (frete total, peso)
               - Trajeto (UF/município início e fim)

             Retorna um CTeData (TypedDict) pronto para
             persistência ou auditoria.

             NUNCA acessa o banco — camada pura de parse.
🔗 DEPENDE  : xml.etree.ElementTree (stdlib)
             decimal.Decimal
📅 CRIADO   : 18/07/2026
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
'''

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import TypedDict

# Namespace oficial do CT-e
_NS_CTE = 'http://www.portalfiscal.inf.br/cte'
_NS = {'cte': _NS_CTE}


# ═════════════════════════════════════════════════
# ❌ EXCEÇÕES
# ═════════════════════════════════════════════════

class CTeParseError(Exception):
    '''Erro base de parse de XML de CT-e.'''
    pass


class XMLMalformadoError(CTeParseError):
    '''XML não é válido ou não pôde ser parseado.'''
    pass


class CTENaoEncontradoError(CTeParseError):
    '''XML não contém elemento <CTe> ou <infCte>.'''
    pass


class CampoObrigatorioError(CTeParseError):
    '''Campo obrigatório ausente ou inválido no XML.'''
    pass


# ═════════════════════════════════════════════════
# 📦 TIPO DE RETORNO
# ═════════════════════════════════════════════════

class CTeData(TypedDict):
    '''
    🎯 Estrutura de dados extraída de um CT-e.
    Todos os campos normalizados para tipos Python nativos.
    '''
    chave_acesso: str
    numero_cte: str
    serie: str
    tipo_cte: int
    data_emissao: datetime
    emitente_cnpj: str
    emitente_nome: str
    remetente_cnpj: str
    remetente_nome: str
    destinatario_cnpj: str
    destinatario_nome: str
    valor_frete: Decimal
    peso_total_kg: Decimal
    uf_inicio: str
    uf_fim: str
    municipio_inicio: str
    municipio_fim: str


# ═════════════════════════════════════════════════
# 🧮 HELPERS INTERNOS
# ═════════════════════════════════════════════════

def _extrair_texto(
    parent: ET.Element,
    tag: str,
    *,
    obrigatorio: bool = True,
    default: str | None = None,
) -> str | None:
    '''
    🎯 Extrai texto de um elemento filho.
    📐 REGRA:
        - obrigatorio=True + ausente/vazio → CampoObrigatorioError.
        - obrigatorio=False + ausente → retorna default.
    '''
    elemento = parent.find(f'cte:{tag}', _NS)
    if elemento is None or not (elemento.text or '').strip():
        if obrigatorio:
            raise CampoObrigatorioError(
                f"Campo obrigatório '{tag}' ausente ou vazio."
            )
        return default
    return elemento.text.strip()


def _extrair_decimal(
    parent: ET.Element,
    tag: str,
    *,
    obrigatorio: bool = True,
    default: Decimal | None = None,
) -> Decimal | None:
    '''
    🎯 Extrai texto e converte para Decimal.
    📐 REGRA: aceita formato BR (1234,56) e internacional (1234.56).
    '''
    texto = _extrair_texto(parent, tag, obrigatorio=obrigatorio)
    if texto is None:
        return default
    try:
        return Decimal(texto.replace(',', '.'))
    except InvalidOperation:
        if obrigatorio:
            raise CampoObrigatorioError(
                f"Campo '{tag}' com valor inválido: '{texto}'."
            )
        return default


def _extrair_int(
    parent: ET.Element,
    tag: str,
    *,
    obrigatorio: bool = True,
    default: int | None = None,
) -> int | None:
    '''🎯 Extrai texto e converte para int.'''
    texto = _extrair_texto(parent, tag, obrigatorio=obrigatorio)
    if texto is None:
        return default
    try:
        return int(texto)
    except ValueError:
        if obrigatorio:
            raise CampoObrigatorioError(
                f"Campo '{tag}' com valor inválido: '{texto}'."
            )
        return default


def _extrair_data(parent: ET.Element, tag: str) -> datetime:
    '''
    🎯 Extrai data/hora ISO 8601 (dhEmi).
    📐 REGRA: YYYY-MM-DDTHH:MM:SS-03:00.
    '''
    texto = _extrair_texto(parent, tag, obrigatorio=True)
    try:
        return datetime.fromisoformat(texto)
    except ValueError:
        raise CampoObrigatorioError(
            f"Campo '{tag}' com formato de data inválido: '{texto}'."
        ) from None


def _limpar_cnpj(cnpj_bruto: str) -> str:
    '''
    🎯 Remove máscara, valida 14 dígitos.
    '''
    digitos = re.sub(r'\D', '', cnpj_bruto)
    if len(digitos) != 14:
        raise CampoObrigatorioError(
            f"CNPJ inválido (esperado 14 dígitos): '{cnpj_bruto}'."
        )
    return digitos


# ═════════════════════════════════════════════════
# 🚀 PARSER PRINCIPAL (função pública)
# ═════════════════════════════════════════════════

def parsear_cte_xml(conteudo_xml: str | bytes) -> CTeData:
    '''
    🎯 Parser principal de XML de CT-e.

    Args:
        conteudo_xml: string XML ou bytes (UTF-8).

    Returns:
        CTeData com todos os campos normalizados.

    Raises:
        XMLMalformadoError:      XML sintaticamente inválido.
        CTENaoEncontradoError:   <CTe> ou <infCte> ausente.
        CampoObrigatorioError:   campo obrigatório faltando/inválido.
    '''
    # ── 1. Parse do XML ──
    try:
        if isinstance(conteudo_xml, str):
            conteudo_xml = conteudo_xml.encode('utf-8')
        root = ET.fromstring(conteudo_xml)
    except ET.ParseError as exc:
        raise XMLMalformadoError(str(exc)) from exc

    # ── 2. Localizar <CTe> ──
    cte = root if root.tag == f'{{{_NS_CTE}}}CTe' else root.find('.//cte:CTe', _NS)
    if cte is None:
        raise CTENaoEncontradoError("Elemento <CTe> não encontrado.")

    # ── 3. <infCte> ──
    inf = cte.find('cte:infCte', _NS)
    if inf is None:
        raise CTENaoEncontradoError("Elemento <infCte> ausente.")

    # ── 4. Chave de acesso ──
    chave = _extrair_chave(inf)

    # ── 5. <ide> ──
    ide = _exigir(inf, 'ide')
    numero = _extrair_texto(ide, 'nCT')
    serie = _extrair_texto(ide, 'serie')
    tipo = _extrair_int(ide, 'tpCTe')
    data_emi = _extrair_data(ide, 'dhEmi')
    uf_ini = _extrair_texto(ide, 'UFIni')
    uf_fim = _extrair_texto(ide, 'UFFim')
    mun_ini = _extrair_texto(ide, 'cMunIni')
    mun_fim = _extrair_texto(ide, 'cMunFim')

    # ── 6. <emit> ──
    emit = _exigir(inf, 'emit')
    emit_cnpj = _limpar_cnpj(_extrair_texto(emit, 'CNPJ'))
    emit_nome = _extrair_texto(emit, 'xNome')

    # ── 7. <rem> ──
    rem = _exigir(inf, 'rem')
    rem_cnpj = _limpar_cnpj(_extrair_texto(rem, 'CNPJ'))
    rem_nome = _extrair_texto(rem, 'xNome')

    # ── 8. <dest> ──
    dest = _exigir(inf, 'dest')
    dest_cnpj = _limpar_cnpj(_extrair_texto(dest, 'CNPJ'))
    dest_nome = _extrair_texto(dest, 'xNome')

    # ── 9. <vPrest> ──
    vprest = _exigir(inf, 'vPrest')
    valor = _extrair_decimal(vprest, 'vTPrest')

    # ── 10. <infCarga> ──
    carga = _exigir(inf, 'infCarga')
    peso = _extrair_decimal(carga, 'pesoB')

    # ── 11. Retorno ──
    return CTeData(
        chave_acesso=chave,
        numero_cte=numero,
        serie=serie,
        tipo_cte=tipo,
        data_emissao=data_emi,
        emitente_cnpj=emit_cnpj,
        emitente_nome=emit_nome,
        remetente_cnpj=rem_cnpj,
        remetente_nome=rem_nome,
        destinatario_cnpj=dest_cnpj,
        destinatario_nome=dest_nome,
        valor_frete=valor,
        peso_total_kg=peso,
        uf_inicio=uf_ini,
        uf_fim=uf_fim,
        municipio_inicio=mun_ini,
        municipio_fim=mun_fim,
    )


# ═════════════════════════════════════════════════
# 🔧 HELPERS AUXILIARES
# ═════════════════════════════════════════════════

def _exigir(parent: ET.Element, tag: str) -> ET.Element:
    '''🎯 Encontra elemento filho obrigatório ou lança erro.'''
    el = parent.find(f'cte:{tag}', _NS)
    if el is None:
        raise CTENaoEncontradoError(f"Elemento <{tag}> ausente.")
    return el


def _extrair_chave(inf_cte: ET.Element) -> str:
    '''🎯 Extrai chave de acesso do atributo Id.'''
    id_attr = inf_cte.get('Id', '')
    chave = id_attr[3:] if id_attr.startswith('CTe') else id_attr
    if len(chave) != 44:
        raise CampoObrigatorioError(
            f"Chave de acesso inválida: '{chave}' (esperado 44 dígitos)."
        )
    return chave


# ═════════════════════════════════════════════════
# 🏷️  UTILITÁRIOS DE CLASSIFICAÇÃO
# ═════════════════════════════════════════════════

def is_cte_anulacao(dados: CTeData) -> bool:
    '''🎯 CT-e de Anulação? (tpCTe = 2 ou 4).'''
    return dados['tipo_cte'] in (2, 4)


def is_cte_normal(dados: CTeData) -> bool:
    '''🎯 CT-e Normal? (tpCTe = 0).'''
    return dados['tipo_cte'] == 0
