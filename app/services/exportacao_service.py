# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 📁 ARQUIVO : exportacao_service.py
# 📦 MÓDULO  : Embarque / Serviço de Exportação
# 🎯 OBJETIVO: Orquestrar a geração da planilha Excel (.xlsx)
#              do embarque. Retorna (bytes, filename) —
#              o router monta a StreamingResponse.
# 📐 REGRA   :
#     - NUNCA acessa o banco diretamente → usa repository
#     - NUNCA levanta HTTPException → quem levanta é o router
# 🔗 DEPENDE  : app.repositories.embarque_repository
#              app.exceptions.embarque_exceptions
# 📅 CRIADO   : 18/07/2026
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

from datetime import date
from io import BytesIO
from uuid import UUID

from openpyxl import Workbook
from sqlalchemy.orm import Session

from app.exceptions.embarque_exceptions import EmbarqueNaoEncontradoError
from app.repositories.embarque_repository import buscar_embarque_com_nfs


# ── Colunas da planilha (Seção 11 do Documento Master) ─────────
COLUNAS = [
    "DOCUMENTO",
    "SÉRIE",
    "CLIENTE",
    "CNPJ",
    "ORIGEM",
    "DESTINO",
    "SKU",
    "QTD CX",
    "PESO TOTAL (KG)",
    "TRANSPORTADORA",
    "VALOR CALCULADO",
    "PRAZO (DIAS)",
]


def _montar_linhas(embarque) -> list[list]:
    '''
    Converte NFs do embarque em lista de linhas para o Excel.

    Parâmetros:
        embarque: instância de Embarque com notas_fiscais já carregadas.

    Retorna:
        Lista de listas, onde cada sublista representa uma linha da planilha.
        Ordem das colunas segue COLUNAS.
    '''
    linhas = []
    for nf in embarque.notas_fiscais:
        linhas.append([
            nf.numero_nf or "",
            nf.serie_nf or "",
            nf.remetente.nome_razao_social if nf.remetente else "",
            nf.remetente.cnpj if nf.remetente else "",
            f"{nf.cidade_origem}/{nf.uf_origem}" if nf.cidade_origem else "",
            f"{nf.cidade_destino}/{nf.uf_destino}" if nf.cidade_destino else "",
            nf.sku or "",
            nf.quantidade_caixas or 0,
            float(nf.peso_total_kg) if nf.peso_total_kg is not None else 0.0,
            nf.transportadora.nome if nf.transportadora else "",
            float(nf.valor_calculado) if nf.valor_calculado is not None else 0.0,
            nf.prazo_dias or 0,
        ])
    return linhas


def _gerar_xlsx(linhas: list[list]) -> bytes:
    '''
    Gera arquivo .xlsx em memória e retorna bytes.

    Parâmetros:
        linhas: lista de linhas (cada linha é uma lista de valores).

    Retorna:
        bytes do arquivo Excel pronto para download.
    '''
    wb = Workbook()
    ws = wb.active
    ws.title = "Embarque"

    # Cabeçalho
    ws.append(COLUNAS)

    # Dados
    for linha in linhas:
        ws.append(linha)

    # Ajuste automático de largura das colunas
    for col in ws.columns:
        max_len = max(len(str(cell.value or "")) for cell in col)
        ws.column_dimensions[col[0].column_letter].width = min(max_len + 2, 40)

    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer.getvalue()


def exportar_embarque(db: Session, embarque_id: UUID) -> tuple[bytes, str]:
    '''
    Exporta embarque para planilha Excel.

    Parâmetros:
        db: Sessão SQLAlchemy (injetada via Depends).
        embarque_id: UUID do embarque a exportar.

    Retorna:
        Tuple com (bytes_do_arquivo_xlsx, nome_do_arquivo).

    Lança:
        EmbarqueNaoEncontradoError: se o embarque não for encontrado.
    '''
    embarque = buscar_embarque_com_nfs(db, embarque_id)

    if embarque is None:
        raise EmbarqueNaoEncontradoError(embarque_id)

    linhas = _montar_linhas(embarque)
    bytes_xlsx = _gerar_xlsx(linhas)
    filename = f"embarque_{embarque_id}_{date.today().strftime("%Y%m%d")}.xlsx"

    return bytes_xlsx, filename
