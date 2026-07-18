'''
Service de Exportacao — Etapa 4
Responsabilidade: orquestrar a geracao da planilha Excel (.xlsx).
Retorna (bytes, filename) — o router monta a StreamingResponse.

Regras de Ouro:
    - NUNCA acessa o banco diretamente → usa repository
    - Multi-tenant: o embarque pertence a empresa; busca por ID
    - Docstrings com \'\'\'
'''

from datetime import date
from io import BytesIO
from uuid import UUID

from fastapi import HTTPException
from openpyxl import Workbook
from sqlalchemy.orm import Session

from app.repositories.embarque_repository import buscar_embarque_com_nfs


# ── Definicao das colunas do Excel ─────────────────────────────
COLUNAS = [
    'DOCUMENTO',
    'Cliente',
    'CNPJ',
    'Origem',
    'Destino',
    'SKU',
    'QTD CX',
    'Peso Total (kg)',
    'Transportadora',
    'Valor Calculado (R$)',
    'Prazo (dias)',
]


def _montar_linhas(embarque) -> list[list]:
    '''
    Converte NFs do embarque em lista de linhas para o Excel.

    Parametros:
        embarque: instancia de Embarque com notas_fiscais ja carregadas

    Retorna:
        Lista de listas, onde cada sublista representa uma linha da planilha.
        Ordem das colunas segue COLUNAS.
    '''
    linhas = []
    for nf in embarque.notas_fiscais:
        transportadora_nome = (
            nf.transportadora.nome if nf.transportadora else ''
        )
        linhas.append([
            f'NF-{nf.numero_nf}-{nf.serie_nf}',
            nf.nome_destinatario or '',
            nf.cnpj_destinatario or '',
            nf.cidade_origem or '',
            nf.cidade_destino or '',
            nf.sku_produto or '',
            nf.quantidade_caixas or 0,
            float(nf.peso_total_kg) if nf.peso_total_kg is not None else 0.0,
            transportadora_nome,
            float(nf.valor_calculado) if nf.valor_calculado is not None else 0.0,
            nf.prazo_dias or 0,
        ])
    return linhas


def _gerar_xlsx(linhas: list[list]) -> bytes:
    '''
    Gera arquivo .xlsx em memoria e retorna bytes.

    Parametros:
        linhas: lista de linhas (cada linha e uma lista de valores)

    Retorna:
        bytes do arquivo Excel pronto para download.
    '''
    wb = Workbook()
    ws = wb.active
    ws.title = 'Embarque'

    # Cabecalho
    ws.append(COLUNAS)

    # Dados
    for linha in linhas:
        ws.append(linha)

    # Ajuste automatico de largura das colunas
    for col in ws.columns:
        max_len = max(len(str(cell.value or '')) for cell in col)
        ws.column_dimensions[col[0].column_letter].width = min(max_len + 2, 40)

    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer.getvalue()


def exportar_embarque(db: Session, embarque_id: UUID) -> tuple[bytes, str]:
    '''
    Exporta embarque para planilha Excel.

    Parametros:
        db: Sessao SQLAlchemy (injetada via Depends)
        embarque_id: UUID do embarque a exportar

    Retorna:
        Tuple com (bytes_do_arquivo_xlsx, nome_do_arquivo)

    Lanca:
        HTTPException 404 se o embarque nao for encontrado.
    '''
    embarque = buscar_embarque_com_nfs(db, embarque_id)

    if embarque is None:
        raise HTTPException(status_code=404, detail='Embarque nao encontrado')

    linhas = _montar_linhas(embarque)
    bytes_xlsx = _gerar_xlsx(linhas)
    filename = f'embarque_{embarque_id}_{date.today().strftime("%Y%m%d")}.xlsx'

    return bytes_xlsx, filename
