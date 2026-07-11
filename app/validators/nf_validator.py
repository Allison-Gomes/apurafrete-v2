'''
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📁 ARQUIVO : nf_validator.py
📦 MÓDULO  : Embarque / Importação de NF
🎯 OBJETIVO: Concentrar as regras de validação de NEGÓCIO aplicadas
             a cada linha de NF já validada estruturalmente pelo
             NFSchema (nf_schema.py). Aqui ficam: limpeza/validação
             de CNPJ, derivação de cidade/UF, validação de QTD_CX
             e normalização do COD_PRODUTO (SKU).
🔗 DEPENDE  : re (biblioteca padrão)
📅 CRIADO  : 04/07/2026
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

⚠️ OBSERVAÇÃO DE DESIGN:
    Este arquivo NÃO lança exceções customizadas diretamente.
    Cada função de validação retorna uma tupla:
        (valor_normalizado_ou_none, codigo_erro_ou_none)
    O motivo é evitar dependência circular com o arquivo de
    exceções (validacao_exceptions.py), que ainda será criado
    (arquivo 4/4). Quem decide o status final da NF (IMPORTADA,
    ERRO_CNPJ, ERRO_CAMPO, SEM_PRODUTO) é o service
    (validacao_service.py), que orquestra estas funções.
'''

import re


def limpar_e_validar_cnpj(cnpj_raw: str) -> tuple[str | None, str | None]:
    '''
    🎯 O QUE FAZ:
        Remove a máscara do CNPJ (pontos, barra, hífen, espaços) e
        valida se o resultado possui exatamente 14 dígitos numéricos.

    📐 REGRA DE NEGÓCIO:
        - Conforme PRD Seção 3.2: remover "." "/" "-" e espaços.
        - Validar que restaram exatamente 14 dígitos.
        - Este método NÃO valida o dígito verificador do CNPJ
          (validação de "CNPJ real"), apenas o formato/tamanho.
          Essa decisão segue o MVP (não foi solicitado DV no PRD).

    📥 PARÂMETROS:
        cnpj_raw (str): CNPJ como veio da planilha (com ou sem máscara)

    📤 RETORNO:
        tuple[str | None, str | None]:
            - Se válido: (cnpj_limpo_14_digitos, None)
            - Se inválido: (None, "ERRO_CNPJ")

    ⚠️  ATENÇÃO:
        Não adicionar validação de dígito verificador sem
        autorização de Allison (fora do escopo do MVP).
    '''
    if not cnpj_raw:
        return None, "ERRO_CNPJ"

    cnpj_limpo = re.sub(r"[.\-/\s]", "", cnpj_raw)

    if not cnpj_limpo.isdigit() or len(cnpj_limpo) != 14:
        return None, "ERRO_CNPJ"

    return cnpj_limpo, None


def derivar_cidade_uf(cidade_uf_raw: str) -> tuple[dict | None, str | None]:
    '''
    🎯 O QUE FAZ:
        A partir do texto bruto "CIDADE - UF" (ex.: "CAMPINAS - SP"),
        separa e retorna a cidade e a UF (2 letras) individualmente,
        mantendo também o valor original (raw) para auditoria.

    📐 REGRA DE NEGÓCIO:
        - Conforme PRD Seção 3.2: guardar valor original em campo
          "*_raw" e derivar "cidade" e "uf" (UF com 2 letras).
        - Formato esperado: "CIDADE - UF" (separador " - ").
        - UF deve conter exatamente 2 letras (validado após strip
          e upper).

    📥 PARÂMETROS:
        cidade_uf_raw (str): valor bruto da coluna, ex.: "CAMPINAS - SP"

    📤 RETORNO:
        tuple[dict | None, str | None]:
            - Se válido: ({"raw": str, "cidade": str, "uf": str}, None)
            - Se inválido (formato não reconhecido ou UF != 2 letras):
              (None, "ERRO_CAMPO")

    ⚠️  ATENÇÃO:
        Não alterar o separador esperado (" - ") sem confirmar com
        Allison o padrão real usado nas planilhas de produção.
    '''
    if not cidade_uf_raw or " - " not in cidade_uf_raw:
        return None, "ERRO_CAMPO"

    partes = cidade_uf_raw.rsplit(" - ", 1)
    if len(partes) != 2:
        return None, "ERRO_CAMPO"

    cidade = partes[0].strip()
    uf = partes[1].strip().upper()

    if not cidade or len(uf) != 2 or not uf.isalpha():
        return None, "ERRO_CAMPO"

    return {"raw": cidade_uf_raw, "cidade": cidade, "uf": uf}, None


def validar_qtd_cx(qtd_cx: int) -> tuple[int | None, str | None]:
    '''
    🎯 O QUE FAZ:
        Valida se a quantidade de caixas (QTD CX) é um inteiro
        maior ou igual a 1.

    📐 REGRA DE NEGÓCIO:
        - Conforme PRD Seção 3.2: QTD_CX >= 1 (obrigatório).

    📥 PARÂMETROS:
        qtd_cx (int): valor já convertido para inteiro pelo NFSchema

    📤 RETORNO:
        tuple[int | None, str | None]:
            - Se válido: (qtd_cx, None)
            - Se inválido (< 1): (None, "ERRO_CAMPO")
    '''
    if qtd_cx is None or qtd_cx < 1:
        return None, "ERRO_CAMPO"

    return qtd_cx, None


def normalizar_cod_produto(cod_produto: str) -> tuple[str | None, str | None]:
    '''
    🎯 O QUE FAZ:
        Normaliza o COD_PRODUTO (SKU) removendo espaços extras,
        garantindo que seja tratado como string para busca no
        cadastro de produtos.

    📐 REGRA DE NEGÓCIO:
        - Conforme PRD Seção 3.2: COD PRODUTO deve ser tratado
          como string (evitar problemas de SKU numérico perdendo
          zeros à esquerda, por exemplo).

    📥 PARÂMETROS:
        cod_produto (str): valor bruto da coluna "COD PRODUTO"

    📤 RETORNO:
        tuple[str | None, str | None]:
            - Se válido (não vazio): (sku_normalizado, None)
            - Se inválido (vazio): (None, "ERRO_CAMPO")

    ⚠️  ATENÇÃO:
        A busca do SKU no cadastro de produtos (para determinar
        status "SEM_PRODUTO") é responsabilidade do service
        (validacao_service.py), não deste validator.
    '''
    if not cod_produto or not cod_produto.strip():
        return None, "ERRO_CAMPO"

    return cod_produto.strip(), None
