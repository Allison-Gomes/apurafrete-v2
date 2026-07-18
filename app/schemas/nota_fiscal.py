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
📅 ATUALIZADO: 18/07/2026 — Refatoração: NotaFiscalRead alinhado
              ao model simplificado (frete_peso/frete_cte/frete_total
              removidos; +cod_produto, +transportadora_id, +snapshots
              de auditoria). NotaFiscalCreate +cod_produto (obrigatório).
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
        Representa uma linha crua da planilha de importação,
        com validação básica de formato/presença.

    📐 REGRA DE NEGÓCIO:
        - Peso real é DERIVADO (QTD_CX × peso_catálogo).
          O peso da planilha NÃO é usado (B1) — coluna opcional.
        - Validações de SKU/CNPJ/campos são feitas no
          validacao_service (que lança as exceções StatusNF).
    '''
    model_config = ConfigDict(str_strip_whitespace=True)

    numero_nf: str = Field(..., max_length=50)
    serie_nf: str | None = Field(default=None, max_length=10)
    chave_nfe: str | None = Field(default=None, max_length=44)
    data_emissao: date | None = None

    destinatario_nome: str | None = Field(default=None, max_length=200)
    destinatario_cnpj_cpf: str | None = Field(default=None, max_length=18)
    destinatario_cidade: str | None = Field(default=None, max_length=100)
    destinatario_uf: str | None = Field(default=None, max_length=2)

    cod_produto: str | None = Field(default=None, max_length=50)

    nf_valor: Decimal = Field(..., ge=0)
    peso_real_kg: Decimal | None = Field(default=None, gt=0)
    quantidade_volumes: int | None = Field(default=None, gt=0)

    observacao: str | None = None

    @field_validator("destinatario_uf")
    @classmethod
    def uf_maiuscula(cls, v: str | None) -> str | None:
        return v.upper() if v else v


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
        - cod_produto é obrigatório (model NOT NULL).
        - peso_real_kg aqui é o PESO TOTAL derivado
          (QTD_CX × peso_catálogo) — sempre presente.
        - status_calculo nasce PENDENTE (default do model).
        - Campos frete_* NÃO entram aqui — são preenchidos
          pelo engine de cálculo (services/calculo_frete.py).
    '''
    model_config = ConfigDict(str_strip_whitespace=True)

    embarque_id: UUID

    numero_nf: str = Field(..., max_length=50)
    serie_nf: str | None = Field(default=None, max_length=10)
    chave_nfe: str | None = Field(default=None, max_length=44)
    data_emissao: date | None = None

    destinatario_nome: str | None = Field(default=None, max_length=200)
    destinatario_cnpj_cpf: str | None = Field(default=None, max_length=18)
    destinatario_cidade: str | None = Field(default=None, max_length=100)
    destinatario_uf: str | None = Field(default=None, max_length=2)

    cod_produto: str = Field(..., max_length=50)
    nf_valor: Decimal = Field(..., ge=0)
    peso_real_kg: Decimal = Field(..., gt=0)
    quantidade_volumes: int | None = Field(default=None, gt=0)

    observacao: str | None = None


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
        - Reflete os campos do model NotaFiscal (Opção B).
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

    # Destinatário
    destinatario_nome: str | None = None
    destinatario_cnpj_cpf: str | None = None
    destinatario_cidade: str | None = None
    destinatario_uf: str | None = None

    # Produto e volumes
    cod_produto: str
    quantidade_volumes: int | None = None
    peso_real_kg: Decimal

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
        Resposta individual do cálculo de frete para
        uma NF — usada tanto na rota individual quanto
        como item dentro do lote.

    📐 CAMPOS:
        - nf_id              : UUID da NF
        - numero_nf          : número fiscal da NF
        - status             : "calculado" | "sem_tabela" |
                               "sem_transportadora" | "erro"
        - valor_frete        : valor calculado (None se erro)
        - peso_utilizado_kg  : peso usado no cálculo
        - tabela_nome        : nome da tabela aplicada
        - erro               : mensagem de erro (None se ok)
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
        Resumo consolidado do cálculo em lote:
        quantas NFs foram calculadas com sucesso e
        quantas falharam, com breakdown por motivo.

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
