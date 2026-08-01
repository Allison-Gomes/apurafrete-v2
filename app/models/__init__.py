'''
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📁 ARQUIVO : app/models/__init__.py
📦 MÓDULO  : Models / Inicialização
🎯 OBJETIVO: Centraliza e expõe todos os models do
             ApuraFrete, garantindo que o SQLAlchemy
             os registre corretamente no metadata
             e que os imports sejam feitos a partir
             de um único ponto de entrada.
🔗 DEPENDE  : app/models/base.py
             app/models/empresa.py
             app/models/usuario.py
             app/models/transportadora.py
             app/models/tabela_frete.py (TabelaFrete, FaixaFrete, ModalidadeFrete)
             app/models/rota_frete.py (RotaFrete)
             app/models/embarque.py
             app/models/nota_fiscal.py
             app/models/cte.py
             app/models/log_auditoria.py
📅 CRIADO  : 24/06/2026
📅 ATUALIZADO: 28/07/2026 — registro do model RotaFrete
               (dimensão geográfica, opção B) e exposição
               dos enums ModalidadeFrete e StatusCalculoNF.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
'''

# ── Base ─────────────────────────────────────────
from app.models.base import Base, AuditMixin

# ── Cadastros ────────────────────────────────────
from app.models.empresa import Empresa
from app.models.usuario import Usuario
from app.models.transportadora import Transportadora

# ── Tabela de Frete ──────────────────────────────
from app.models.tabela_frete import (
    TabelaFrete,
    FaixaFrete,
    ModalidadeFrete,
)

# ── Rotas de Frete (dimensão geográfica) ─────────
# IMPORTANTE: importar APÓS tabela_frete para que o
# relationship 'rotas' seja resolvido corretamente.
from app.models.rota_frete import RotaFrete

# ── Operação ─────────────────────────────────────
from app.models.embarque import Embarque
from app.models.nota_fiscal import NotaFiscal, StatusCalculoNF

# ── CT-e ─────────────────────────────────────────
from app.models.cte import Cte, ItemCte

# ── Auditoria ────────────────────────────────────
from app.models.log_auditoria import AuditoriaLog, AcaoLog, EntidadeLog

# ── Exposição pública do módulo ──────────────────
__all__ = [
    # Base
    "Base",
    "AuditMixin",

    # Cadastros
    "Empresa",
    "Usuario",
    "Transportadora",

    # Tabela de Frete
    "TabelaFrete",
    "FaixaFrete",
    "ModalidadeFrete",

    # Rotas de Frete
    "RotaFrete",

    # Operação
    "Embarque",
    "NotaFiscal",
    "StatusCalculoNF",

    # CT-e
    "Cte",
    "ItemCte",

    # Auditoria
    "AuditoriaLog",
    "AcaoLog",
    "EntidadeLog",
]


'''
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📝 NOTAS DO ARQUIVO
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Por que centralizar no __init__.py?

| Benefício          | Detalhe                                                      |
| ------------------ | ------------------------------------------------------------ |
| Import único       | from app.models import Empresa                               |
| Registro garantido | SQLAlchemy exige todos os models importados antes do Alembic |
| Rastreabilidade    | Um único lugar para verificar todos os models ativos         |
| Alembic            | O env.py importa este __init__.py e detecta todas as tabelas |

Ordem de import importa:
    tabela_frete → rota_frete
O relationship 'rotas' em TabelaFrete usa string ("RotaFrete"),
então funciona em qualquer ordem — mas manter a ordem acima
torna a leitura do grafo de dependências explícita.

Uso esperado no restante do projeto:
    from app.models import Embarque, NotaFiscal, RotaFrete
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
'''
