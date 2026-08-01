'''
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📁 ARQUIVO : app/services/validacao_service.py
📦 MÓDULO  : Embarque / Importação de NF
🎯 OBJETIVO: Service PURO (sem I/O) que valida e enriquece
             linhas de importação de NF, aplicando as regras
             de negócio e produzindo o relatório do lote.
             Arquitetura de status (decisão B):
               - Só linhas válidas viram NotaFiscalCreate.
               - Linhas inválidas viram NFImportError (StatusNF).
               - StatusNF NÃO persiste; vive só no relatório.
📐 REGRA    : peso_total_kg = qtd_cx × produto.peso_real_kg (§3.1)
             cidade_uf_* → cidade + uf + *_raw preservado (§4.2)
             Normalização geográfica: SOMENTE app/utils/normalizacao
🔗 DEPENDE  : app/schemas/nota_fiscal.py
             app/exceptions/validacao_exceptions.py
             app/utils/normalizacao.py
📅 CRIADO   : 07/07/2026
📅 ATUALIZ. : 28/07/2026 — Decisão #75. Realinhado ao schema real:
                           quantidade_volumes → qtd_cx
                           destinatario_*     → *_destino
                           peso_real_kg       → peso_total_kg
                           +bloco remetente completo
                           +split cidade_uf_* (§4.2)
                           +cod_cliente, cod_produto, centro_custo
                           +rede de segurança p/ ValidationError
             01/08/2026 — Decisão #73 (opção 1). FONTE UNICA de
                           normalização geográfica:
                           - _normalizar_cidade local REMOVIDA;
                             delega a utils.normalizar_cidade.
                           - UF via utils.normalizar_uf + guarda
                             de domínio (_UFS_VALIDAS).
                           - Hífen SEM espaço deixa de ser
                             separador: "Mogi-Mirim - SP" agora
                             produz "MOGI-MIRIM", alinhado ao
                             cadastro de rotas_frete.
             01/08/2026 — Fix regressão do teste "- SP": cidade
                           formada só por hífen/apóstrofo passava
                           pela guarda. Agora exige ao menos um
                           caractere alfanumérico.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
'''

from __future__ import annotations

import re
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ValidationError

from app.schemas.nota_fiscal import (
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
    StatusNF,
)
from app.utils.normalizacao import normalizar_cidade, normalizar_uf


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
# 🔧 CONSTANTES
# ─────────────────────────────────────────────────
'''
Separadores aceitos entre cidade e UF (§4.2 / Decisão #73):

    - "/" e ","  → sempre separadores.
    - "-" e "–"  → APENAS quando cercados por espaço (" - ").

⚠️ CRÍTICO: hífen SEM espaço NÃO é separador. Ele pertence ao
nome da cidade, porque app/utils/normalizacao.normalizar_cidade
PRESERVA hífen ("Mogi-Mirim" → "MOGI-MIRIM"). Se o split
quebrasse aqui, a NF gravaria "MOGI MIRIM" enquanto a rota
gravaria "MOGI-MIRIM" → falso SEM_ROTA silencioso.
'''
_SEP_CIDADE_UF = re.compile(r'\s*[/,]\s*|\s+[-–]\s+')

'''
Fallback para planilhas SEM separador explícito: captura as
2 últimas letras precedidas de espaço. Ex.: "Mogi-Mirim SP".
'''
_RE_CIDADE_UF_SEM_SEP = re.compile(r'^(?P<cidade>.+?)\s+(?P<uf>[A-Za-z]{2})$')

'''
Um nome de cidade só é aceito se contiver ao menos UMA letra
ou dígito. normalizar_cidade() PRESERVA hífen e apóstrofo, logo
entradas como "-" ou "'" sobreviveriam à normalização e seriam
gravadas como chave de rota inválida.
'''
_RE_CIDADE_TEM_CONTEUDO = re.compile(r'[A-Z0-9]')

_UFS_VALIDAS: frozenset[str] = frozenset({
    'AC', 'AL', 'AP', 'AM', 'BA', 'CE', 'DF', 'ES', 'GO', 'MA',
    'MT', 'MS', 'MG', 'PA', 'PB', 'PR', 'PE', 'PI', 'RJ', 'RN',
    'RS', 'RO', 'RR', 'SC', 'SP', 'SE', 'TO',
})


# ─────────────────────────────────────────────────
# 🔧 HELPERS DE VALIDAÇÃO
# ─────────────────────────────────────────────────
def _exigir(valor, campo: str):
    '''
    🎯 O QUE FAZ:
        Garante presença de campo obrigatório.
        Vazio/None → ErroCampoError.

    📤 RETORNO:
        O valor já com strip() aplicado (se string).
    '''
    if valor is None or (isinstance(valor, str) and not valor.strip()):
        raise ErroCampoError(campo=campo, valor_original=valor)
    return valor.strip() if isinstance(valor, str) else valor


def _limpar_cnpj_cpf(valor: str | None, campo: str) -> str:
    '''
    🎯 O QUE FAZ:
        Remove máscara (pontos, barras, traços) do CNPJ/CPF,
        deixando apenas dígitos.

    📐 REGRA DE NEGÓCIO:
        - Vazio/None → ErroCampoError (obrigatório).
        - 11 (CPF) ou 14 (CNPJ) dígitos → válido.
        - CPF (11) é left-padded para 14, pois a coluna do
          banco é VARCHAR(14) NOT NULL.
        - Caso contrário → ErroCnpjError.
    '''
    if valor is None or not str(valor).strip():
        raise ErroCampoError(campo=campo, valor_original=valor)

    somente_digitos = re.sub(r'\D', '', str(valor))

    if len(somente_digitos) not in (11, 14):
        raise ErroCnpjError(campo=campo, valor_original=valor)

    return somente_digitos.rjust(14, '0')


def _normalizar_uf_validada(bruto: str, campo: str, valor_original) -> str:
    '''
    🎯 O QUE FAZ:
        Normaliza a UF via app.utils.normalizacao.normalizar_uf e
        valida o DOMÍNIO contra as 27 unidades federativas.

    📐 REGRA DE NEGÓCIO:
        - normalizar_uf() apenas normaliza a FORMA e TRUNCA em 2
          letras; o docstring dela delega a validação de domínio
          ao service. Esta função é essa validação.
        - GUARDA ANTITRUNCAMENTO: se o texto original tiver
          número de letras != 2, rejeita ANTES do truncamento.
          Sem essa guarda, "SPX" viraria "SP" silenciosamente.
        - UF fora de _UFS_VALIDAS → ErroCampoError.

    📤 RETORNO:
        str: UF com 2 letras maiúsculas, garantidamente válida.
    '''
    # Guarda: conta letras do bruto antes de qualquer truncamento.
    if len(re.sub(r'[^A-Za-z]', '', bruto)) != 2:
        raise ErroCampoError(campo=campo, valor_original=valor_original)

    uf = normalizar_uf(bruto)

    if uf is None or uf not in _UFS_VALIDAS:
        raise ErroCampoError(campo=campo, valor_original=valor_original)

    return uf


def _normalizar_cidade_validada(bruto: str, campo: str, valor_original) -> str:
    '''
    🎯 O QUE FAZ:
        Normaliza o nome da cidade pela FONTE UNICA
        (app.utils.normalizacao.normalizar_cidade) e garante que
        o resultado é um nome utilizável como chave de rota.

    📐 REGRA DE NEGÓCIO:
        - Resultado None (nada sobrou) → ErroCampoError.
        - Resultado sem nenhuma letra/dígito → ErroCampoError.
          ⚠️ normalizar_cidade PRESERVA hífen e apóstrofo, então
          entradas como "- SP" produziriam cidade "-", que passa
          por None mas é lixo. Este é o caso de regressão do
          teste 'invalido[- SP]'.

    📤 RETORNO:
        str: cidade normalizada, garantidamente com conteúdo.
    '''
    cidade = normalizar_cidade(bruto)

    if cidade is None or not _RE_CIDADE_TEM_CONTEUDO.search(cidade):
        raise ErroCampoError(campo=campo, valor_original=valor_original)

    return cidade


def _split_cidade_uf(valor: str | None, campo: str) -> tuple[str, str, str]:
    '''
    🎯 O QUE FAZ:
        Quebra o campo composto "CIDADE - UF" em suas partes (§4.2)
        e normaliza cada parte pela FONTE UNICA (Decisão #73).

    📐 REGRA DE NEGÓCIO:
        - Separadores: "/", "," (sempre) e " - ", " – " (com espaço).
        - Hífen SEM espaço pertence à cidade ("Mogi-Mirim").
        - Sem separador, aceita o padrão "CIDADE UF" (2 letras finais).
        - A UF é sempre o ÚLTIMO segmento.
        - UF deve ter 2 letras e estar entre as 27 UFs válidas.
        - Cidade deve conter ao menos uma letra ou dígito.
        - Formato inválido ou UF desconhecida → ErroCampoError.
        - O valor original é preservado em cidade_*_raw.

    ⚠️ ATENÇÃO:
        A normalização aqui é a MESMA de calculo_frete_service e do
        cadastro de rotas_frete, pois todas chamam
        app/utils/normalizacao. Divergir reintroduz falso SEM_ROTA.

    📤 RETORNO:
        tuple[cidade_normalizada, uf, valor_raw_original]
    '''
    raw = _exigir(valor, campo)

    partes = [p for p in _SEP_CIDADE_UF.split(raw) if p and p.strip()]

    if len(partes) >= 2:
        uf_bruta = partes[-1]
        cidade_bruta = ' '.join(p.strip() for p in partes[:-1])
    else:
        # Fallback: "CIDADE UF" sem separador explícito.
        casado = _RE_CIDADE_UF_SEM_SEP.match(raw)
        if casado is None:
            raise ErroCampoError(campo=campo, valor_original=valor)
        uf_bruta = casado.group('uf')
        cidade_bruta = casado.group('cidade')

    uf = _normalizar_uf_validada(uf_bruta, campo=campo, valor_original=valor)
    cidade = _normalizar_cidade_validada(
        cidade_bruta, campo=campo, valor_original=valor
    )

    return cidade, uf, raw


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
        1. numero_nf obrigatório      → ErroCampoError
        2. qtd_cx obrigatório (>0)    → ErroCampoError
        3. bloco DESTINO validado     → ErroCampoError/ErroCnpjError
        4. bloco REMETENTE validado   → ErroCampoError/ErroCnpjError
        5. cod_produto obrigatório    → ErroCampoError
        6. SKU existe no catálogo     → SemProdutoError
        7. produto ativo              → SemProdutoError
        8. peso_total_kg = qtd_cx × peso_real_kg
    '''
    # ── 1. Identificação da NF ──────────────────
    numero_nf = _exigir(row.numero_nf, 'numero_nf')

    # ── 2. Quantidade de caixas ─────────────────
    # Obrigatório: o peso inteiro depende dele (§3.1).
    if row.qtd_cx is None or row.qtd_cx <= 0:
        raise ErroCampoError(campo='qtd_cx', valor_original=row.qtd_cx)
    qtd_cx = int(row.qtd_cx)

    # ── 3. Bloco DESTINO ────────────────────────
    cod_cliente = _exigir(row.cod_cliente, 'cod_cliente')
    cliente_destino = _exigir(row.cliente_destino, 'cliente_destino')
    cnpj_destino = _limpar_cnpj_cpf(row.cnpj_destino, campo='cnpj_destino')
    cidade_destino, uf_destino, cidade_destino_raw = _split_cidade_uf(
        row.cidade_uf_destino, campo='cidade_uf_destino'
    )

    # ── 4. Bloco REMETENTE ──────────────────────
    cod_remetente = _exigir(row.cod_remetente, 'cod_remetente')
    cliente_remetente = _exigir(row.cliente_remetente, 'cliente_remetente')
    cnpj_remetente = _limpar_cnpj_cpf(
        row.cnpj_remetente, campo='cnpj_remetente'
    )
    cidade_remetente, uf_remetente, cidade_remetente_raw = _split_cidade_uf(
        row.cidade_uf_remetente, campo='cidade_uf_remetente'
    )

    # ── 5/6/7. Produto ──────────────────────────
    sku = _exigir(row.cod_produto, 'cod_produto')

    produto = catalogo.get(sku)
    if produto is None:
        raise SemProdutoError(sku=sku)

    if not produto.ativo:
        raise SemProdutoError(sku=sku)

    # ── 8. Peso total derivado (§3.1 / §4.3) ────
    peso_total_kg = Decimal(qtd_cx) * produto.peso_real_kg

    return NotaFiscalCreate(
        embarque_id=embarque_id,
        # identificação
        numero_nf=numero_nf,
        serie_nf=row.serie_nf,
        chave_nfe=row.chave_nfe,
        data_emissao=row.data_emissao,
        # remetente / origem
        cod_remetente=cod_remetente,
        cliente_remetente=cliente_remetente,
        cnpj_remetente=cnpj_remetente,
        cidade_remetente=cidade_remetente,
        uf_remetente=uf_remetente,
        cidade_remetente_raw=cidade_remetente_raw,
        # destinatário / destino
        cod_cliente=cod_cliente,
        cliente_destino=cliente_destino,
        cnpj_destino=cnpj_destino,
        cidade_destino=cidade_destino,
        uf_destino=uf_destino,
        cidade_destino_raw=cidade_destino_raw,
        # produto e carga
        cod_produto=sku,
        qtd_cx=qtd_cx,
        peso_total_kg=peso_total_kg,
        # fiscais e livres
        nf_valor=row.nf_valor,
        observacao=row.observacao,
        centro_custo=row.centro_custo,
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
          - válida   → acumula em `criadas` (NotaFiscalCreate)
          - inválida → acumula em `erros` (NFImportError)
        Nunca interrompe o lote por causa de uma linha ruim.

    📐 REGRA DE NEGÓCIO:
        - StatusNF só existe no relatório (decisão B).
        - Numeração de linha é 1-based (linha 1 = primeira NF).
        - status_calculo NÃO é setado aqui: nasce PENDENTE
          pelo default do model (§6.7).
        - ValidationError do NotaFiscalCreate (ex.: cidade com
          mais de 100 chars) também rejeita apenas a LINHA.
    '''
    criadas: list[NotaFiscalCreate] = []
    erros: list[NFImportError] = []

    for indice, row in enumerate(linhas, start=1):
        try:
            criadas.append(_validar_linha(row, embarque_id, catalogo))

        except NFValidationError as exc:
            # Erro de negócio previsto (SEM_PRODUTO / ERRO_CNPJ / ERRO_CAMPO)
            erros.append(
                NFImportError(
                    linha=indice,
                    numero_nf=row.numero_nf,
                    status=exc.status,
                    campo=exc.campo,
                    mensagem=exc.mensagem,
                )
            )

        except ValidationError as exc:
            # Rede de segurança: violação de constraint do
            # NotaFiscalCreate (max_length, gt=0) não pode
            # derrubar o lote inteiro — rejeita só a linha.
            primeiro = exc.errors()[0]
            campo = str(primeiro['loc'][0]) if primeiro.get('loc') else None
            erros.append(
                NFImportError(
                    linha=indice,
                    numero_nf=row.numero_nf,
                    status=StatusNF.ERRO_CAMPO,
                    campo=campo,
                    mensagem=f"Dado fora do formato aceito: {primeiro['msg']}",
                )
            )

    resultado = NFImportResult(
        total_linhas=len(linhas),
        total_importadas=len(criadas),
        total_erros=len(erros),
        erros=erros,
    )
    return criadas, resultado
