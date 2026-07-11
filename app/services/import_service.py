'''
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📁 ARQUIVO : import_service.py
📦 MÓDULO  : Embarque / Importação de NF
🎯 OBJETIVO: Service que orquestra a importação de NFs:
              1. Valida linhas via validacao_service
              2. Deduplica vs. banco (Decisão #44)
              3. Persiste via repository (Decisão #45)
              4. Commit/rollback centralizado
📐 REGRA    : - Decisão #44: dedup no service
               (consulta repository → filtra → insere só novas)
             - Decisão #45: commit direto no service
               (try/commit/except/rollback, sem UnitOfWork)
             - Decisão #33: duplicatas ignoradas silenciosamente
             - Decisão #41: repository só flush()
             - Decisão #39: peso derivado do catálogo
               (já resolvido no validacao_service)
🔗 DEPENDE  : app/services/validacao_service.py
             app/repositories/nota_fiscal_repository.py
             app/schemas/nf_schema.py
📅 CRIADO   : 11/07/2026
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
'''

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.schemas.nf_schema import (
    NFImportRow,
    NFImportError,
    NotaFiscalCreate,
)
from app.services.validacao_service import (
    ProdutoInfo,
    processar_importacao,
)
from app.repositories.nota_fiscal_repository import NotaFiscalRepository
from app.models.nota_fiscal import NotaFiscal


# ─────────────────────────────────────────────────
# 📊 SCHEMA LOCAL: ImportLoteResult
# Consolidado final: validação + dedup + persistência.
# ─────────────────────────────────────────────────
class ImportLoteResult(BaseModel):
    '''
    🎯 O QUE FAZ:
        Resultado consolidado do lote de importação,
        unificando os dados de validação e deduplicação.

    📐 REGRA DE NEGÓCIO:
        - total_importadas = efetivamente persistidas
          (passaram na validação E não eram duplicatas).
        - total_erros = erros de validação apenas.
        - duplicatas_ignoradas = passaram na validação
          mas já existiam no embarque (não são erro).
        - Σ = total_importadas + total_erros + duplicatas_ignoradas
          = total_linhas da planilha.
    '''
    total_linhas: int = Field(..., ge=0)
    total_importadas: int = Field(..., ge=0)
    total_erros: int = Field(..., ge=0)
    duplicatas_ignoradas: int = Field(default=0, ge=0)
    erros: list[NFImportError] = Field(default_factory=list)


# ─────────────────────────────────────────────────
# 🚀 ENTRYPOINT: importar_nfs
# ─────────────────────────────────────────────────
def importar_nfs(
    session: Session,
    linhas: list[NFImportRow],
    embarque_id: UUID,
    catalogo: dict[str, ProdutoInfo],
) -> tuple[list[NotaFiscal], ImportLoteResult]:
    '''
    🎯 O QUE FAZ:
        Orquestra o fluxo completo de importação de NFs
        em lote, da planilha bruta até a persistência:
          1. Valida e enriquece as linhas (validacao_service)
          2. Consulta chaves já existentes no embarque (repository)
          3. Filtra duplicatas — ignoradas silenciosamente (#33, #44)
          4. Persiste apenas as NFs novas (repository → flush)
          5. Commit da transação (#45)

    📐 REGRA DE NEGÓCIO:
        - Duplicatas NÃO interrompem o lote e NÃO viram erro.
        - Se zero linhas válidas após validação → retorna vazio
          sem tocar no banco (nem chama o repository).
        - Se todas as válidas forem duplicatas → retorna vazio
          sem insert (só fez a consulta de chaves).
        - Em caso de falha no commit → rollback + relança exceção.
        - O chamador (router) é responsável por abrir/fechar a
          session; este service apenas opera dentro dela.

    📥 PARÂMETROS:
        session (Session): sessão SQLAlchemy síncrona (R1).
        linhas (list[NFImportRow]): linhas brutas da planilha.
        embarque_id (UUID): embarque de destino das NFs.
        catalogo (dict[str, ProdutoInfo]): catálogo SKU → peso
          (já carregado pelo router, evita N+1 no service).

    📤 RETORNO:
        tuple[list[NotaFiscal], ImportLoteResult]:
          - models persistidos (com id, flushados).
          - resultado consolidado com validação + dedup.
    '''
    # ── Etapa 1: Validação (pura, sem I/O) ──────
    criadas, resultado_validacao = processar_importacao(
        linhas=linhas,
        embarque_id=embarque_id,
        catalogo=catalogo,
    )

    total_linhas = resultado_validacao.total_linhas
    total_erros = resultado_validacao.total_erros
    erros_validacao = resultado_validacao.erros

    if not criadas:
        # Nenhuma linha passou na validação —
        # nem encosta no banco.
        return [], ImportLoteResult(
            total_linhas=total_linhas,
            total_importadas=0,
            total_erros=total_erros,
            duplicatas_ignoradas=0,
            erros=erros_validacao,
        )

    # ── Etapa 2: Dedup vs. banco (#44) ──────────
    repo = NotaFiscalRepository(session)

    chaves_existentes = repo.buscar_chaves_existentes(embarque_id)

    novas: list[NotaFiscalCreate] = []
    duplicatas = 0

    for nf in criadas:
        chave = (nf.numero_nf, nf.serie_nf)
        if chave in chaves_existentes:
            duplicatas += 1  # ignorada silenciosamente (#33)
        else:
            novas.append(nf)

    if not novas:
        # Todas as válidas já existiam —
        # sem insert, sem commit.
        return [], ImportLoteResult(
            total_linhas=total_linhas,
            total_importadas=0,
            total_erros=total_erros,
            duplicatas_ignoradas=duplicatas,
            erros=erros_validacao,
        )

    # ── Etapa 3: Persistência (#45) ─────────────
    try:
        objetos = repo.criar_em_lote(novas)   # flush apenas
        session.commit()                       # commit aqui (#45)
    except Exception:
        session.rollback()
        raise

    # ── Etapa 4: Resultado consolidado ──────────
    resultado = ImportLoteResult(
        total_linhas=total_linhas,
        total_importadas=len(novas),
        total_erros=total_erros,
        duplicatas_ignoradas=duplicatas,
        erros=erros_validacao,
    )

    return objetos, resultado
