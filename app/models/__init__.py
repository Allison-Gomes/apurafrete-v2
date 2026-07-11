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
             app/models/tabela_frete.py (TabelaFrete, FaixaFrete)
             app/models/embarque.py
             app/models/nota_fiscal.py
             app/models/cte.py
             app/models/log_auditoria.py
📅 CRIADO  : 24/06/2026
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
'''

# ── Base ─────────────────────────────────────────
from app.models.base import Base, AuditMixin

# ── Cadastros ────────────────────────────────────
from app.models.empresa import Empresa
from app.models.usuario import Usuario
from app.models.transportadora import Transportadora

# ── Tabela de Frete ──────────────────────────────
from app.models.tabela_frete import TabelaFrete, FaixaFrete

# ── Operação ─────────────────────────────────────
from app.models.embarque import Embarque
from app.models.nota_fiscal import NotaFiscal

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

    # Operação
    "Embarque",
    "NotaFiscal",

    # CT-e
    "Cte",
    "ItemCte",

    # Auditoria
    "AuditoriaLog",
    "AcaoLog",
    "EntidadeLog",
]



'''
Notas do arquivo
Por que centralizar no __init__.py?
| Benefício | Detalhe |
| --- | --- |
| Import único | from app.models import Empresa em vez de from app.models.empresa import Empresa |
| Registro garantido | O SQLAlchemy precisa que todos os models sejam importados antes do create_all() ou das migrações Alembic |
| Rastreabilidade | Um único lugar para verificar todos os models ativos do sistema |
| Alembic | O env.py do Alembic importa este __init__.py para detectar automaticamente todas as tabelas |

Uso esperado no restante do projeto
# Em qualquer service, rota ou script:
from app.models import Embarque, NotaFiscal, AuditoriaLog, AcaoLog


'''