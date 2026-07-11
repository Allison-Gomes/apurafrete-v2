'''
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📁 ARQUIVO : validacao_exceptions.py
📦 MÓDULO  : Embarque / Importação de NF
🎯 OBJETIVO: Definir as exceções customizadas de validação de NF,
             representando cada status possível após a importação
             (PRD Seção 3.4): IMPORTADA (sucesso, sem exceção),
             SEM_PRODUTO, ERRO_CNPJ, ERRO_CAMPO.
             Também define constantes de status para uso padronizado
             em toda a aplicação (evitar strings "soltas" no código).
🔗 DEPENDE  : Nenhuma dependência externa
📅 CRIADO  : 04/07/2026
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

⚠️ OBSERVAÇÃO DE DESIGN:
    Estas exceções são usadas pelo service de validação
    (validacao_service.py) para sinalizar, de forma padronizada,
    por que uma linha de NF não pôde ser importada com sucesso.
    O service captura essas exceções e grava o status
    correspondente na NF (não interrompe o processamento em lote).
'''


class StatusNF:
    '''
    🎯 O QUE FAZ:
        Centraliza as constantes de status possíveis para uma NF
        após o processo de importação/validação.

    📐 REGRA DE NEGÓCIO:
        - Conforme PRD Seção 3.4:
            IMPORTADA   -> linha válida e produto encontrado
            SEM_PRODUTO -> SKU não cadastrado
            ERRO_CNPJ   -> CNPJ inválido (remetente ou destino)
            ERRO_CAMPO  -> campo obrigatório ausente ou inválido

    ⚠️  ATENÇÃO:
        Sempre usar estas constantes (StatusNF.IMPORTADA, etc.)
        em vez de strings soltas, para evitar erros de digitação
        e facilitar manutenção/refatoração futura.
    '''
    IMPORTADA = "IMPORTADA"
    SEM_PRODUTO = "SEM_PRODUTO"
    ERRO_CNPJ = "ERRO_CNPJ"
    ERRO_CAMPO = "ERRO_CAMPO"


class NFValidationError(Exception):
    '''
    🎯 O QUE FAZ:
        Classe base para todas as exceções de validação de NF.
        Permite capturar qualquer erro de validação com um único
        "except NFValidationError" no service, se necessário.

    📐 REGRA DE NEGÓCIO:
        - Toda exceção de validação de NF deve herdar desta classe.

    📥 PARÂMETROS:
        mensagem (str): descrição legível do erro
        status (str): código de status (usar StatusNF.*)
        campo (str | None): nome do campo que originou o erro,
                             quando aplicável (ex.: "cnpj_destino")
    '''

    def __init__(self, mensagem: str, status: str, campo: str | None = None):
        self.mensagem = mensagem
        self.status = status
        self.campo = campo
        super().__init__(mensagem)


class SemProdutoError(NFValidationError):
    '''
    🎯 O QUE FAZ:
        Sinaliza que o SKU informado em "COD PRODUTO" não foi
        encontrado no cadastro de produtos do tenant.

    📐 REGRA DE NEGÓCIO:
        - Conforme PRD Seção 3.4 (status SEM_PRODUTO) e Seção 2.1
          (cadastro obrigatório do produto para cálculo).

    📥 PARÂMETROS:
        sku (str): código do produto não encontrado

    ⚠️  ATENÇÃO:
        Esta exceção NÃO impede a importação da NF (ela é
        importada com status SEM_PRODUTO), apenas impede que a NF
        avance para o cálculo de frete até correção do cadastro.
    '''

    def __init__(self, sku: str):
        mensagem = f"Produto com SKU '{sku}' nao encontrado no cadastro."
        super().__init__(mensagem=mensagem, status=StatusNF.SEM_PRODUTO, campo="cod_produto")
        self.sku = sku


class ErroCnpjError(NFValidationError):
    '''
    🎯 O QUE FAZ:
        Sinaliza que um CNPJ (remetente ou destinatário) é inválido
        apos limpeza de mascara (nao possui 14 digitos numericos).

    📐 REGRA DE NEGÓCIO:
        - Conforme PRD Seção 3.2 e 3.4 (status ERRO_CNPJ).

    📥 PARÂMETROS:
        campo (str): "cnpj_destino" ou "cnpj_remetente"
        valor_original (str): valor bruto recebido da planilha
    '''

    def __init__(self, campo: str, valor_original: str):
        mensagem = f"CNPJ invalido no campo '{campo}': '{valor_original}'."
        super().__init__(mensagem=mensagem, status=StatusNF.ERRO_CNPJ, campo=campo)
        self.valor_original = valor_original


class ErroCampoError(NFValidationError):
    '''
    🎯 O QUE FAZ:
        Sinaliza que um campo obrigatorio esta ausente ou invalido
        (ex.: QTD_CX < 1, formato de "CIDADE - UF" nao reconhecido,
        COD_PRODUTO vazio).

    📐 REGRA DE NEGÓCIO:
        - Conforme PRD Seção 3.4 (status ERRO_CAMPO).

    📥 PARÂMETROS:
        campo (str): nome do campo problematico
        valor_original (str | int | None): valor recebido
    '''

    def __init__(self, campo: str, valor_original):
        mensagem = f"Campo obrigatorio invalido/ausente: '{campo}' (valor: '{valor_original}')."
        super().__init__(mensagem=mensagem, status=StatusNF.ERRO_CAMPO, campo=campo)
        self.valor_original = valor_original
