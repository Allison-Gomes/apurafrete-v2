'''
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📁 ARQUIVO : nota_fiscal.py
📦 MÓDULO  : Embarque / Importação de NF / Cálculo de Frete
🎯 OBJETIVO: Schemas Pydantic (v2) para importação, validação,
             serialização de Notas Fiscais e cálculo de frete.
             Arquitetura de status (decisão B):
               - StatusNF NÃO persiste na NotaFiscal.
               - Somente linhas IMPORTADA viram NF no banco.
               - SEM_PRODUTO / ERRO_CNPJ / ERRO_CAMPO viram
                 linhas de erro no relatório de importação.
               - Na NF, o único status persistido é status_calculo.
🔗 DEPENDE  : app/models/nota_fiscal.py (StatusCalculoNF)
              app/exceptions/validacao_exceptions.py (StatusNF)
📅 CRIADO   : 07/07/2026
📅 ATUALIZADO: 28/07/2026 — Alinhamento ao schema REAL do banco.
               Renomes: quantidade_volumes → qtd_cx,
               peso_real_kg → peso_total_kg.
               Bloco destinatario_* substituído pelos campos
               desnormalizados reais + bloco remetente completo.
               NFImportRow tornado PERMISSIVO (todos opcionais,
               sem max_length): obrigatoriedade e formato são
               julgados no validacao_service, para que uma célula
               ruim rejeite a LINHA e não aborte o LOTE.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
'''

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.nota_fiscal import StatusCalculoNF


# ═════════════════════════════════════════════════
# 📥 IMPORTACAO — Schemas de entrada da planilha
# ═════════════════════════════════════════════════

# ─────────────────────────────────────────────────
# 📥 SCHEMA: NFImportRow
# Linha crua vinda da planilha, antes de normalizar.
# ─────────────────────────────────────────────────
class NFImportRow(BaseModel):
    '''
    🎯 O QUE FAZ:
        Representa uma linha crua da planilha de importação.
        É um schema de TRANSPORTE TOLERANTE.

    📐 REGRA DE NEGÓCIO:
        - Espelha os cabeçalhos da planilha (Seção 4.1), não o model.
        - Cidade e UF vêm JUNTAS em `cidade_uf_*` ("CIDADE - UF");
          o split é feito no validacao_service (Seção 4.2).
        - TODOS os campos são opcionais e SEM max_length de propósito:
          obrigatoriedade/tamanho são julgados no validacao_service,
          que rejeita a LINHA e segue o lote. Um Field(...) estrito
          aqui abortaria a importação inteira por uma célula ruim.
        - Peso é DERIVADO (qtd_cx × produto.peso_real_kg).
          O peso da planilha NÃO é usado (B1) — não há coluna.
    '''
    model_config = ConfigDict(str_strip_whitespace=True)

    # Identificação
    numero_nf: str | None = Field(default=None, description="Coluna DOCUMENTO")
    serie_nf: str | None = None
    chave_nfe: str | None = None
    data_emissao: date | None = None

    # Destino (colunas 2-5)
    cod_cliente: str | None = None
    cliente_destino: str | None = None
    cnpj_destino: str | None = None
    cidade_uf_destino: str | None = Field(
        default=None,
        description="Coluna 'CIDADE - UF DESTINO' (bruta)",
    )

    # Origem (colunas 6-9)
    cod_remetente: str | None = None
    cliente_remetente: str | None = None
    cnpj_remetente: str | None = None
    cidade_uf_remetente: str | None = Field(
        default=None,
        description="Coluna 'CIDADE - UF REMETENTE' (bruta)",
    )

    # Produto / carga
    cod_produto: str | None = None
    # ⚠️ sem ge=1: qtd_cx ≤ 0 deve virar ERRO_CAMPO no relatório.
    qtd_cx: int | None = Field(default=None, description="Coluna QTD CX")

    # Fiscais e livres
    nf_valor: Decimal | None = None
    observacao: str | None = None
    centro_custo: str | None = None


# ═════════════════════════════════════════════════
# ❌ IMPORTACAO — Schemas de erro e resultado
# ═════════════════════════════════════════════════

# ─────────────────────────────────────────────────
# ❌ SCHEMA: NFImportError
# Linha rejeitada — vai para o relatório, não vira NF.
# ─────────────────────────────────────────────────
class NFImportError(BaseModel):
    '''
    🎯 O QUE FAZ:
        Representa uma linha que NÃO pôde ser importada.
        Carrega o status (StatusNF), o campo problemático
        e o motivo legível, para exibição no relatório.

    📐 REGRA DE NEGÓCIO:
        - status usa as constantes de StatusNF
          (SEM_PRODUTO / ERRO_CNPJ / ERRO_CAMPO).
        - Estas linhas NÃO geram registro em notas_fiscais.
    '''
    linha: int = Field(..., description="Índice da linha na planilha (1-based)")
    numero_nf: str | None = None
    status: str = Field(..., description="Código StatusNF do erro")
    campo: str | None = Field(default=None, description="Campo que originou o erro")
    mensagem: str = Field(..., description="Descrição legível do erro")


# ─────────────────────────────────────────────────
# 📊 SCHEMA: NFImportResult
# Resumo do lote de importação.
# ─────────────────────────────────────────────────
class NFImportResult(BaseModel):
    '''
    🎯 O QUE FAZ:
        Resumo consolidado do processamento em lote:
        quantas linhas foram importadas com sucesso e
        a lista de erros para revisão operacional.
    '''
    total_linhas: int = Field(..., ge=0)
    total_importadas: int = Field(..., ge=0)
    total_erros: int = Field(..., ge=0)
    erros: list[NFImportError] = Field(default_factory=list)


# ═════════════════════════════════════════════════
# 💾 PERSISTÊNCIA — Schemas de escrita e leitura
# ═════════════════════════════════════════════════

# ─────────────────────────────────────────────────
# 💾 SCHEMA: NotaFiscalCreate
# Payload normalizado para persistir (só IMPORTADA).
# ─────────────────────────────────────────────────
class NotaFiscalCreate(BaseModel):
    '''
    🎯 O QUE FAZ:
        Dados já validados/normalizados de uma NF pronta
        para ser gravada em notas_fiscais.

    📐 REGRA DE NEGÓCIO:
        - Só linhas IMPORTADA chegam aqui (decisão B).
        - Este schema é ESTRITO: é o contrato com o banco.
          Toda constraint (max_length, gt=0) espelha a coluna.
        - CNPJs já chegam limpos (14 dígitos, sem máscara).
        - cidade_*_raw guarda o texto original da planilha.
        - peso_total_kg é DERIVADO (qtd_cx × peso_real_kg).
        - status_calculo nasce PENDENTE (default do model).
        - Campos de cálculo/snapshot NÃO entram aqui — são
          preenchidos pelo engine (calculo_frete_service.py).
    '''
    model_config = ConfigDict(str_strip_whitespace=True)

    embarque_id: UUID

    # Identificação da NF
    numero_nf: str = Field(..., max_length=50)
    serie_nf: str | None = Field(default=None, max_length=10)
    chave_nfe: str | None = Field(default=None, max_length=44)
    data_emissao: date | None = None

    # Remetente / ORIGEM
    cod_remetente: str = Field(..., max_length=50)
    cliente_remetente: str = Field(..., max_length=200)
    cnpj_remetente: str = Field(..., min_length=14, max_length=14)
    cidade_remetente: str = Field(..., max_length=100)
    uf_remetente: str = Field(..., min_length=2, max_length=2)
    cidade_remetente_raw: str | None = Field(default=None, max_length=200)

    # Destinatário / DESTINO
    cod_cliente: str = Field(..., max_length=50)
    cliente_destino: str = Field(..., max_length=200)
    cnpj_destino: str = Field(..., min_length=14, max_length=14)
    cidade_destino: str = Field(..., max_length=100)
    uf_destino: str = Field(..., min_length=2, max_length=2)
    cidade_destino_raw: str | None = Field(default=None, max_length=200)

    # Produto e carga
    cod_produto: str = Field(..., max_length=100)
    qtd_cx: int = Field(..., ge=1)
    peso_total_kg: Decimal = Field(..., gt=0)

    # Dados fiscais
    nf_valor: Decimal | None = Field(default=None, ge=0)

    # Campos livres
    observacao: str | None = None
    centro_custo: str | None = None

    @field_validator("uf_remetente", "uf_destino")
    @classmethod
    def uf_maiuscula(cls, v: str) -> str:
        '''📐 UF sempre em caixa alta (chave de rota).'''
        return v.upper()

    @field_validator("cnpj_remetente", "cnpj_destino")
    @classmethod
    def cnpj_somente_digitos(cls, v: str) -> str:
        '''📐 Última barreira: garante 14 dígitos sem máscara.'''
        limpo = "".join(c for c in v if c.isdigit())
        if len(limpo) != 14:
            raise ValueError("CNPJ deve ter 14 dígitos")
        return limpo


# ─────────────────────────────────────────────────
# 📤 SCHEMA: NotaFiscalRead
# Resposta da API (inclui id + resultado do cálculo).
# ─────────────────────────────────────────────────
class NotaFiscalRead(BaseModel):
    '''
    🎯 O QUE FAZ:
        Serializa uma NotaFiscal para resposta da API,
        incluindo id, dados fiscais, resultado do cálculo
        de frete, snapshots de auditoria e status_calculo.

    📐 REGRA DE NEGÓCIO:
        - Reflete 1:1 os campos do model NotaFiscal.
        - from_attributes=True permite carregar direto do ORM.
        - Snapshots preco_ate_30kg_usado, valor_kg_adicional_usado
          e peso_kg_usado são para auditoria (Seção 6.6).
    '''
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    embarque_id: UUID

    # Identificação da NF
    numero_nf: str
    serie_nf: str | None = None
    chave_nfe: str | None = None
    data_emissao: date | None = None

    # Remetente / ORIGEM
    cod_remetente: str
    cliente_remetente: str
    cnpj_remetente: str
    cidade_remetente: str
    uf_remetente: str
    cidade_remetente_raw: str | None = None

    # Destinatário / DESTINO
    cod_cliente: str
    cliente_destino: str
    cnpj_destino: str
    cidade_destino: str
    uf_destino: str
    cidade_destino_raw: str | None = None

    # Produto e carga
    cod_produto: str
    qtd_cx: int
    peso_total_kg: Decimal

    # Dados fiscais
    nf_valor: Decimal | None = None

    # Transportadora
    transportadora_id: UUID | None = None

    # Resultado do cálculo de frete
    valor_calculado: Decimal | None = None
    prazo_dias: int | None = None

    # Snapshots para auditoria (Seção 6.6)
    preco_ate_30kg_usado: Decimal | None = None
    valor_kg_adicional_usado: Decimal | None = None
    peso_kg_usado: Decimal | None = None

    # Status e rastreabilidade
    status_calculo: StatusCalculoNF
    erro_calculo: str | None = None
    observacao: str | None = None
    centro_custo: str | None = None


# ═════════════════════════════════════════════════
# 🧮 CÁLCULO DE FRETE — Schemas de resposta
# ═════════════════════════════════════════════════

# ─────────────────────────────────────────────────
# 📊 SCHEMA: CalcularFreteItemResponse
# Resultado do cálculo de uma NF individual.
# ─────────────────────────────────────────────────
class CalcularFreteItemResponse(BaseModel):
    '''
    🎯 O QUE FAZ:
        Resposta individual do cálculo de frete para uma NF —
        usada na rota individual e como item dentro do lote.

    📐 CAMPOS:
        - nf_id             : UUID da NF
        - numero_nf         : número fiscal da NF
        - status            : "calculado" | "sem_tabela" |
                              "sem_transportadora" | "erro"
        - valor_frete       : valor calculado (None se erro)
        - peso_utilizado_kg : peso usado no cálculo
        - tabela_nome       : nome da tabela aplicada
        - erro              : mensagem de erro (None se ok)
    '''
    nf_id: UUID
    numero_nf: str
    status: str = Field(
        ...,
        description="Status final do cálculo",
        examples=["calculado", "sem_tabela", "sem_transportadora", "erro"],
    )
    valor_frete: Decimal | None = Field(
        default=None,
        description="Valor calculado (None se falha)",
    )
    peso_utilizado_kg: Decimal | None = Field(default=None)
    tabela_nome: str | None = Field(default=None)
    erro: str | None = Field(
        default=None,
        description="Mensagem de erro (None se sucesso)",
    )


# ─────────────────────────────────────────────────
# 📊 SCHEMA: CalcularFreteLoteResponse
# Resumo do cálculo em lote de um embarque.
# ─────────────────────────────────────────────────
class CalcularFreteLoteResponse(BaseModel):
    '''
    🎯 O QUE FAZ:
        Resumo consolidado do cálculo em lote: quantas NFs
        foram calculadas com sucesso e quantas falharam,
        com breakdown por motivo.

    📐 CAMPOS:
        - embarque_id        : UUID do embarque processado
        - total_nfs          : total de NFs no embarque
        - calculadas         : NFs com frete calculado
        - sem_tabela         : NFs cuja transportadora não tem tabela
        - sem_transportadora : NFs sem transportadora definida
        - erro               : NFs com erro (peso inválido, etc.)
        - resultados         : lista detalhada por NF
    '''
    embarque_id: UUID
    total_nfs: int = Field(..., ge=0)
    calculadas: int = Field(default=0, ge=0)
    sem_tabela: int = Field(default=0, ge=0)
    sem_transportadora: int = Field(default=0, ge=0)
    erro: int = Field(default=0, ge=0)
    resultados: list[CalcularFreteItemResponse] = Field(default_factory=list)
