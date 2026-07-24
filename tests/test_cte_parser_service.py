'''
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📁 ARQUIVO : tests/test_cte_parser_service.py
📦 MÓDULO  : CT-e / Testes Unitários
🎯 OBJETIVO: 10 cenários de teste para cte_parser_service.py
📐 REGRA   : Decisão #61 — parser como camada pura de parse
📐 REGRA   : Master v4.5 Seção 21 — roteiro de testes
📐 REGRA   : Decisão #46 — pytest + sem conexão com banco
📅 CRIADO  : 23/07/2026
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
'''
from __future__ import annotations

import xml.etree.ElementTree as ET
from decimal import Decimal

import pytest

from app.services.cte_parser_service import (
    CampoObrigatorioError,
    CTENaoEncontradoError,
    XMLMalformadoError,
    _extrair_decimal,
    _limpar_cnpj,
    is_cte_anulacao,
    is_cte_normal,
    parsear_cte_xml,
)


# ═══════════════════════════════════════════════════════════════
# 📦 XMLs DE TESTE (inline, autocontidos)
# ═══════════════════════════════════════════════════════════════

XML_CTE_NORMAL = '''<?xml version="1.0" encoding="UTF-8"?>
<CTe xmlns="http://www.portalfiscal.inf.br/cte">
  <infCte Id="CTe35260712345678000195570010000123450123456780" versao="3.00">
    <ide>
      <cUF>35</cUF>
      <cCT>12345678</cCT>
      <CFOP>6353</CFOP>
      <natOp>PRESTACAO DE SERVICOS DE TRANSPORTE</natOp>
      <mod>57</mod>
      <serie>1</serie>
      <nCT>12345</nCT>
      <dhEmi>2026-07-18T10:00:00-03:00</dhEmi>
      <tpImp>1</tpImp>
      <tpEmis>1</tpEmis>
      <cDV>0</cDV>
      <tpAmb>2</tpAmb>
      <tpCTe>0</tpCTe>
      <procEmi>0</procEmi>
      <verProc>3.00</verProc>
      <cMunFG>3550308</cMunFG>
      <tpServ>0</tpServ>
      <cMunIni>3550308</cMunIni>
      <xMunIni>Sao Paulo</xMunIni>
      <UFIni>SP</UFIni>
      <cMunFim>3304557</cMunFim>
      <xMunFim>Rio de Janeiro</xMunFim>
      <UFFim>RJ</UFFim>
    </ide>
    <compl/>
    <emit>
      <CNPJ>12.345.678/0001-95</CNPJ>
      <IE>123456789</IE>
      <xNome>TRANSPORTADORA TESTE LTDA</xNome>
      <xFant>TRANSPORTADORA TESTE</xFant>
      <enderEmit>
        <xLgr>RUA TESTE</xLgr>
        <nro>100</nro>
        <xBairro>CENTRO</xBairro>
        <cMun>3550308</cMun>
        <xMun>Sao Paulo</xMun>
        <CEP>01000000</CEP>
        <UF>SP</UF>
      </enderEmit>
    </emit>
    <rem>
      <CNPJ>98.765.432/0001-99</CNPJ>
      <IE>987654321</IE>
      <xNome>REMETENTE TESTE LTDA</xNome>
      <xFant>REMETENTE TESTE</xFant>
      <enderReme>
        <xLgr>AV TESTE</xLgr>
        <nro>200</nro>
        <xBairro>CENTRO</xBairro>
        <cMun>3550308</cMun>
        <xMun>Sao Paulo</xMun>
        <CEP>01000000</CEP>
        <UF>SP</UF>
      </enderReme>
    </rem>
    <dest>
      <CNPJ>11.222.333/0001-44</CNPJ>
      <IE>112223334</IE>
      <xNome>DESTINATARIO TESTE LTDA</xNome>
      <enderDest>
        <xLgr>RUA DESTINO</xLgr>
        <nro>300</nro>
        <xBairro>CENTRO</xBairro>
        <cMun>3304557</cMun>
        <xMun>Rio de Janeiro</xMun>
        <CEP>20000000</CEP>
        <UF>RJ</UF>
      </enderDest>
    </dest>
    <vPrest>
      <vTPrest>1250,50</vTPrest>
      <vRec>1250,50</vRec>
    </vPrest>
    <infCarga>
      <vCarga>50000,00</vCarga>
      <proPred>MERCADORIA TESTE</proPred>
      <pesoB>500,0000</pesoB>
    </infCarga>
  </infCte>
</CTe>'''

XML_CTE_ANULACAO = XML_CTE_NORMAL.replace(
    '<tpCTe>0</tpCTe>', '<tpCTe>2</tpCTe>'
)

XML_MALFORMADO = '''<?xml version="1.0" encoding="UTF-8"?>
<CTe xmlns="http://www.portalfiscal.inf.br/cte">
  <infCte>
    <ide>
      <tpCTe>0</tpCTe>
    </ide>
  <!-- Tag não fechada propositalmente -->
</CTe>'''

XML_SEM_TAG_CTE = '''<?xml version="1.0" encoding="UTF-8"?>
<outro xmlns="http://www.portalfiscal.inf.br/cte">
  <infCte Id="CTe35260712345678000195570010000123450123456780" versao="3.00">
    <ide>
      <tpCTe>0</tpCTe>
    </ide>
  </infCte>
</outro>'''

# XML com campo obrigatório removido (tpCTe deletado do <ide>)
XML_CAMPO_AUSENTE = XML_CTE_NORMAL.replace('<tpCTe>0</tpCTe>', '')


# ═══════════════════════════════════════════════════════════════
# 🧪 GRUPO 1 — Parse completo (5 cenários)
# ═══════════════════════════════════════════════════════════════

class TestParseCompleto:
    '''🎯 Testes de parsear_cte_xml() com XMLs válidos e inválidos.'''

    def test_parse_cte_normal_valido(self):
        '''
        📐 REGRA: XML CT-e Normal (tpCTe=0) → CTeData com 16 campos.
        '''
        resultado = parsear_cte_xml(XML_CTE_NORMAL)

        # Identificação
        assert resultado['chave_acesso'] == (
            '35260712345678000195570010000123450123456780'
        )
        assert resultado['numero_cte'] == '12345'
        assert resultado['serie'] == '1'
        assert resultado['tipo_cte'] == 0

        # Emitente
        assert resultado['emitente_cnpj'] == '12345678000195'
        assert resultado['emitente_nome'] == 'TRANSPORTADORA TESTE LTDA'

        # Remetente
        assert resultado['remetente_cnpj'] == '98765432000199'
        assert resultado['remetente_nome'] == 'REMETENTE TESTE LTDA'

        # Destinatário
        assert resultado['destinatario_cnpj'] == '11222333000144'
        assert resultado['destinatario_nome'] == 'DESTINATARIO TESTE LTDA'

        # Valores (formato BR: vírgula → Decimal)
        assert resultado['valor_frete'] == Decimal('1250.50')
        assert resultado['peso_total_kg'] == Decimal('500.0000')

        # Trajeto
        assert resultado['uf_inicio'] == 'SP'
        assert resultado['uf_fim'] == 'RJ'
        assert resultado['municipio_inicio'] == '3550308'
        assert resultado['municipio_fim'] == '3304557'

    def test_parse_cte_anulacao(self):
        '''
        📐 REGRA: CT-e Anulação (tpCTe=2) → tipo_cte=2.
        '''
        resultado = parsear_cte_xml(XML_CTE_ANULACAO)
        assert resultado['tipo_cte'] == 2

    def test_parse_xml_malformado(self):
        '''
        📐 REGRA: XML malformado → XMLMalformadoError.
        '''
        with pytest.raises(XMLMalformadoError):
            parsear_cte_xml(XML_MALFORMADO)

    def test_parse_xml_sem_tag_cte(self):
        '''
        📐 REGRA: XML sem <CTe> → CTENaoEncontradoError.
        '''
        with pytest.raises(CTENaoEncontradoError):
            parsear_cte_xml(XML_SEM_TAG_CTE)

    def test_parse_xml_campo_obrigatorio_ausente(self):
        '''
        📐 REGRA: Campo obrigatório removido → CampoObrigatorioError.
        '''
        with pytest.raises(CampoObrigatorioError):
            parsear_cte_xml(XML_CAMPO_AUSENTE)


# ═══════════════════════════════════════════════════════════════
# 🧪 GRUPO 2 — Classificação (5 cenários)
# ═══════════════════════════════════════════════════════════════

class TestClassificacao:
    '''🎯 is_cte_normal() e is_cte_anulacao().'''

    def test_is_cte_anulacao_tipo_2(self):
        '''📐 REGRA: tipo_cte=2 → True.'''
        assert is_cte_anulacao({'tipo_cte': 2}) is True

    def test_is_cte_anulacao_tipo_4(self):
        '''📐 REGRA: tipo_cte=4 → True.'''
        assert is_cte_anulacao({'tipo_cte': 4}) is True

    def test_is_cte_anulacao_tipo_0(self):
        '''📐 REGRA: tipo_cte=0 → False.'''
        assert is_cte_anulacao({'tipo_cte': 0}) is False

    def test_is_cte_normal_tipo_0(self):
        '''📐 REGRA: tipo_cte=0 → True.'''
        assert is_cte_normal({'tipo_cte': 0}) is True

    def test_is_cte_normal_tipo_2(self):
        '''📐 REGRA: tipo_cte=2 → False.'''
        assert is_cte_normal({'tipo_cte': 2}) is False


# ═══════════════════════════════════════════════════════════════
# 🧪 GRUPO 3 — Helpers (6 cenários)
# ═══════════════════════════════════════════════════════════════

class TestHelpers:
    '''🎯 _limpar_cnpj() e _extrair_decimal().'''

    # ── _limpar_cnpj ──

    def test_limpar_cnpj_com_mascara(self):
        '''📐 REGRA: CNPJ com máscara → 14 dígitos.'''
        assert _limpar_cnpj('12.345.678/0001-95') == '12345678000195'

    def test_limpar_cnpj_sem_mascara(self):
        '''📐 REGRA: CNPJ sem máscara → idem.'''
        assert _limpar_cnpj('12345678000195') == '12345678000195'

    def test_limpar_cnpj_invalido(self):
        '''📐 REGRA: CNPJ ≠14 dígitos → CampoObrigatorioError.'''
        with pytest.raises(CampoObrigatorioError):
            _limpar_cnpj('1234567800019')  # 13 dígitos

    # ── _extrair_decimal (requer ET.Element) ──

    def test_extrair_decimal_virgula_br(self):
        '''
        📐 REGRA: formato BR (vírgula) → Decimal correto.
        🔧 Usa ET.Element pois _extrair_decimal recebe parent + tag.
        🎯 Namespace CT-e obrigatório para _extrair_texto() localizar.
        '''
        xml = (
            '<root xmlns="http://www.portalfiscal.inf.br/cte">'
            '<valor>1250,50</valor>'
            '</root>'
        )
        root = ET.fromstring(xml)
        assert _extrair_decimal(root, 'valor') == Decimal('1250.50')

    def test_extrair_decimal_ponto(self):
        '''
        📐 REGRA: formato internacional (ponto) → Decimal correto.
        🎯 Namespace CT-e obrigatório para _extrair_texto() localizar.
        '''
        xml = (
            '<root xmlns="http://www.portalfiscal.inf.br/cte">'
            '<valor>1250.50</valor>'
            '</root>'
        )
        root = ET.fromstring(xml)
        assert _extrair_decimal(root, 'valor') == Decimal('1250.50')

    def test_extrair_decimal_sem_casas(self):
        '''
        📐 REGRA: inteiro → Decimal sem casas decimais.
        🎯 Namespace CT-e obrigatório para _extrair_texto() localizar.
        '''
        xml = (
            '<root xmlns="http://www.portalfiscal.inf.br/cte">'
            '<valor>1250</valor>'
            '</root>'
        )
        root = ET.fromstring(xml)
        assert _extrair_decimal(root, 'valor') == Decimal('1250')
