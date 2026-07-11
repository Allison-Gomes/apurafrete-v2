'''
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📁 ARQUIVO : validacao_service.py
📦 MÓDULO  : Embarque / Importação de NF
🎯 OBJETIVO: Service PURO (sem I/O) que valida e enriquece
             linhas de importação de NF, aplicando as regras
             de negócio e produzindo o relatório do lote.
             Arquitetura de status (decisão B):
               - Só linhas válidas viram NotaFiscalCreate.
               - Linhas inválidas viram NFImportError (StatusNF).
               - StatusNF NÃO persiste; vive só no relatório.
📐 REGRA    : peso_total_kg = QTD_CX × produto.peso_real_kg
🔗 DEPENDE  : app/schemas/nf_schema.py
             app/exceptions/validacao_exceptions.py
📅 CRIADO   : 07/07/2026
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
'''

from __future__ import annotations

import re
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel

from app.schemas.nf_schema import (
    NFImportRow,
    NFImportError,
    NFImportResult,
    NotaFiscalCreate,
)
from app.exceptions.validacao_exceptions import (
    NFValidationError,
    SemProdutoError,
    ErroCnpjError,
    ErroCampoError,
)


# ─────────────────────────────────────────────────
# 🗂️ SCHEMA AUXILIAR: ProdutoInfo
# Snapshot do catálogo em memória (SKU → peso + ativo).
# ─────────────────────────────────────────────────
class ProdutoInfo(BaseModel):
    '''
    🎯 O QUE FAZ:
        Representa o mínimo do Produto necessário para
        validar e enriquecer a NF, sem acoplar o service
        ao ORM (mantém o service puro/testável).

    📐 REGRA DE NEGÓCIO:
        - peso_real_kg é unitário (por caixa).
        - ativo=False → produto não pode ser usado.
    '''
    sku: str
    peso_real_kg: Decimal
    ativo: bool = True


# ─────────────────────────────────────────────────
# 🔧 HELPERS DE VALIDAÇÃO
# ─────────────────────────────────────────────────
def _limpar_cnpj_cpf(valor: str | None, campo: str) -> str:
    '''
    🎯 O QUE FAZ:
        Remove máscara (pontos, barras, traços) do CNPJ/CPF,
        deixando apenas dígitos.

    📐 REGRA DE NEGÓCIO:
        - Vazio/None → ErroCampoError (obrigatório).
        - 11 (CPF) ou 14 (CNPJ) dígitos → válido.
        - Caso contrário → ErroCnpjError.
    '''
    if not valor or not valor.strip():
        raise ErroCampoError(campo=campo, valor_original=valor)

    somente_digitos = re.sub(r'\D', '', valor)

    if len(somente_digitos) not in (11, 14):
        raise ErroCnpjError(campo=campo, valor_original=valor)
    return somente_digitos


def _exigir(valor, campo: str):
    '''
    🎯 O QUE FAZ:
        Garante presença de campo obrigatório.
        Vazio/None → ErroCampoError.
    '''
    if valor is None or (isinstance(valor, str) and not valor.strip()):
        raise ErroCampoError(campo=campo, valor_original=valor)
    return valor


# ─────────────────────────────────────────────────
# 🧩 VALIDAÇÃO DE UMA LINHA
# ─────────────────────────────────────────────────
def _validar_linha(
    row: NFImportRow,
    embarque_id: UUID,
    catalogo: dict[str, ProdutoInfo],
) -> NotaFiscalCreate:
    '''
    🎯 O QUE FAZ:
        Valida e enriquece UMA linha de importação.
        Retorna NotaFiscalCreate pronto para persistir
        OU lança uma NFValidationError (StatusNF).

    📐 REGRA DE NEGÓCIO (ordem):
        1. numero_nf obrigatório       → ErroCampoError
        2. QTD_CX obrigatório (>0)      → ErroCampoError
        3. CNPJ/CPF válido              → ErroCnpjError/ErroCampoError
        4. cod_produto obrigatório      → ErroCampoError
        5. SKU existe no catálogo       → SemProdutoError
        6. produto ativo                → SemProdutoError
        7. peso = QTD_CX × peso_unit.
    '''
    # 1. número da NF
    numero_nf = _exigir(row.numero_nf, 'numero_nf')

    # 2. QTD_CX obrigatório (decisão: peso depende dele)
    if row.quantidade_volumes is None or row.quantidade_volumes <= 0:
        raise ErroCampoError(campo='quantidade_volumes',
                             valor_original=row.quantidade_volumes)
    qtd_cx = row.quantidade_volumes

    # 3. CNPJ/CPF do destinatário
    cnpj_limpo = _limpar_cnpj_cpf(
        row.destinatario_cnpj_cpf,
        campo='destinatario_cnpj_cpf',
    )

    # 4. cod_produto
    sku = _exigir(row.cod_produto, 'cod_produto')

    # 5. SKU existe?
    produto = catalogo.get(sku)
    if produto is None:
        raise SemProdutoError(sku=sku)

    # 6. produto ativo?
    if not produto.ativo:
        raise SemProdutoError(sku=sku)

    # 7. peso total = QTD_CX × peso unitário
    peso_total = Decimal(qtd_cx) * produto.peso_real_kg

    return NotaFiscalCreate(
        embarque_id=embarque_id,
        numero_nf=numero_nf,
        serie_nf=row.serie_nf,
        chave_nfe=row.chave_nfe,
        data_emissao=row.data_emissao,
        destinatario_nome=row.destinatario_nome,
        destinatario_cnpj_cpf=cnpj_limpo,
        destinatario_cidade=row.destinatario_cidade,
        destinatario_uf=row.destinatario_uf,
        nf_valor=row.nf_valor,
        peso_real_kg=peso_total,
        quantidade_volumes=qtd_cx,
        observacao=row.observacao,
    )


# ─────────────────────────────────────────────────
# 🚀 ENTRYPOINT: processar_importacao
# ─────────────────────────────────────────────────
def processar_importacao(
    linhas: list[NFImportRow],
    embarque_id: UUID,
    catalogo: dict[str, ProdutoInfo],
) -> tuple[list[NotaFiscalCreate], NFImportResult]:
    '''
    🎯 O QUE FAZ:
        Processa o LOTE de importação. Para cada linha:
          - válida  → acumula em `criadas` (NotaFiscalCreate)
          - inválida → acumula em `erros` (NFImportError)
        Nunca interrompe o lote por causa de uma linha ruim.

    📐 REGRA DE NEGÓCIO:
        - StatusNF só existe no relatório (decisão B).
        - Numeração de linha é 1-based (linha 1 = primeira NF).
    '''
    criadas: list[NotaFiscalCreate] = []
    erros: list[NFImportError] = []

    for indice, row in enumerate(linhas, start=1):
        try:
            criadas.append(_validar_linha(row, embarque_id, catalogo))
        except NFValidationError as exc:
            erros.append(
                NFImportError(
                    linha=indice,
                    numero_nf=row.numero_nf,
                    status=exc.status,
                    campo=exc.campo,
                    mensagem=exc.mensagem,
                )
            )

    resultado = NFImportResult(
        total_linhas=len(linhas),
        total_importadas=len(criadas),
        total_erros=len(erros),
        erros=erros,
    )
    return criadas, resultado
