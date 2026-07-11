# 🚚 ApuraFrete

> SaaS de cálculo e auditoria de frete com CT-e — **ADillTech**

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg)](https://fastapi.tiangolo.com/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-316192.svg)](https://www.postgresql.org/)
[![Licença](https://img.shields.io/badge/licença-MIT-green.svg)](LICENSE)
[![Status](https://img.shields.io/badge/status-MVP%20em%20desenvolvimento-yellow.svg)]()

---

## 🎯 Visão Geral

O **ApuraFrete** é um SaaS multi-tenant que automatiza o cálculo de frete por nota fiscal, a exportação de embarques e a auditoria de divergências entre o valor calculado e o valor rateado do CT-e.

### Três fluxos principais:

| # | Fluxo | Descrição |
|---|-------|-----------|
| 1 | **Importar → Calcular → Exportar** | Importe planilhas de NFs, calcule o frete com regras determinísticas e exporte o embarque |
| 2 | **Importar CT-e → Auditar** | Importe XMLs de CT-e, vincule às NFs e audite divergências com tolerância de ±5% |
| 3 | **Governança** | Logs de auditoria append-only, RBAC e multi-tenant completo |

---

## ✨ Funcionalidades

### MVP Atual

- ✅ Importação de NFs via planilha Excel (13 colunas, 11 obrigatórias)
- ✅ Validação tolerante linha a linha com relatório de erros
- ✅ Deduplicação por `(numero_nf, serie_nf)`
- ✅ Cálculo de frete determinístico por peso real (sem cubagem)
- ✅ Engine de cálculo com 13 testes unitários (`pytest`)
- ✅ Cadastro de produtos, transportadoras e tabelas de frete
- ✅ Seeds idempotentes (empresa demo + admin)
- ✅ Autenticação JWT (HS256, 480 min)
- 🔄 Exportação de embarque para Excel
- 🔲 Importação de CT-e (XML)
- 🔲 Auditoria e conciliação (±5%)

---

## 🛠️ Stack Tecnológica

| Componente    | Tecnologia |
|---------------|------------|
| **Framework** | [FastAPI](https://fastapi.tiangolo.com/) |
| **ORM**       | [SQLAlchemy](https://www.sqlalchemy.org/) (async global) |
| **Banco**     | [PostgreSQL](https://www.postgresql.org/) 16 |
| **Migrações** | [Alembic](https://alembic.sqlalchemy.org/) |
| **Validação** | [Pydantic](https://docs.pydantic.dev/) v2 |
| **Autenticação** | JWT (HS256) + bcrypt 4.0.1 (passlib) |
| **Testes**    | [Pytest](https://docs.pytest.org/) + mock |

---

## 📋 Pré-requisitos

- **Python** 3.11+
- **PostgreSQL** 16+
- **Git**

---

## 🚀 Como Rodar Localmente

### 1. Clone o repositório

```bash
git clone https://github.com/seu-usuario/apurafrete-v2.git
cd apurafrete-v2


2. Crie o ambiente virtual
python -m venv .venv
.venv\Scripts\activate  # Windows
# ou
source .venv/bin/activate  # Linux/macOS

3. Instale as dependências
pip install -r requirements.txt
pip install -r requirements-dev.txt  # opcional: ferramentas de desenvolvimento

4. Configure as variáveis de ambiente
Copie o arquivo de exemplo e edite com suas credenciais:
cp .env.example .env

Edite o .env:
# Banco de dados
DATABASE_URL=postgresql+asyncpg://apura:SUA_SENHA@localhost:5432/apurafrete

# JWT
SECRET_KEY=sua_chave_secreta_aqui
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=480

# App
APP_NAME=ApuraFrete
DEBUG=true

5. Execute as migrações
alembic upgrade head

6. Rode as seeds (opcional)
python seeds/seed_inicial.py

Isso criará:

Empresa demo: 12345678000199 (Empresa Demo LTDA)
Admin: allison@apurafrete.com.br / 123456

7. Inicie o servidor
uvicorn app.main:app --reload

Acesse: http://localhost:8000

📖 Documentação interativa da API: http://localhost:8000/docs

📁 Estrutura do Projeto
apurafrete-v2/
├── app/
│   ├── core/                  # Configuração, banco, dependências, segurança
│   │   ├── config.py
│   │   ├── database.py
│   │   ├── deps.py
│   │   └── security.py
│   ├── models/                # Todos os models centralizados (SQLAlchemy)
│   │   ├── base.py
│   │   ├── empresa.py         # Tenant + terceiros (modelo unificado)
│   │   ├── usuario.py
│   │   ├── cliente.py
│   │   ├── transportadora.py
│   │   ├── tabela_frete.py
│   │   ├── nota_fiscal.py
│   │   ├── produto.py
│   │   ├── embarque.py
│   │   ├── cte.py
│   │   └── log_auditoria.py
│   ├── modules/               # Módulos da aplicação
│   │   ├── auditoria/
│   │   ├── auth/
│   │   ├── cadastros/
│   │   └── embarque/
│   ├── schemas/               # Pydantic v2 (entrada e saída)
│   ├── services/              # Regras de negócio
│   │   ├── validacao_service.py
│   │   ├── import_service.py
│   │   └── calculo_frete_service.py
│   ├── repositories/          # Acesso ao banco (SQLAlchemy)
│   ├── validators/
│   ├── exceptions/
│   └── tests/                 # Testes unitários
│       └── test_calculo_frete_service.py
├── alembic/                   # Migrações do banco
│   ├── versions/
│   └── env.py
├── seeds/
│   └── seed_inicial.py
├── .env.example
├── .gitignore
├── requirements.txt
├── requirements-dev.txt
├── alembic.ini
└── README.md

Padrão de 4 Camadas
Request → router → service → repository → PostgreSQL
                                              ↓
Response ← router ← service ← repository ←───┘

| Camada | Arquivo | Responsabilidade | NÃO pode conter |
| --- | --- | --- | --- |
| Rotas | router.py | HTTP, validação de entrada | Regra de negócio, queries |
| Schemas | schemas.py | Pydantic entrada/saída | Lógica, acesso a banco |
| Serviço | service.py | Regras de negócio | Queries SQL (usa repository) |
| Repositório | repository.py | Acesso ao banco | Regras de negócio, commit |

⚖️ Regras de Negócio Principais
Cálculo de Peso
peso_total_kg=QTD_CX×peso_real_kg_produto
Peso sempre derivado do catálogo — não existe coluna de peso na planilha.

Cálculo de Frete (Determinístico)
Se peso_total_kg≤30:
frete=preco_ate_30kg
Se peso_total_kg>30:
frete=preco_ate_30kg+(peso_total_kg−30)×valor_kg_adicional

Rateio CT-e (Igualitário)
rateio_nf=     valor_cte
               qtd_nfs_vinculadas
Resíduo de centavos absorvido pela 1ª NF (ordem por DOCUMENTO).

Auditoria (±5%)
​
 | Condição | Status |
| --- | --- |
| ∥rateio−calculadocalculado∥≤0,05\\left\\\| \\frac{rateio - calculado}{calculado} \\right\\\| \\leq 0{,}05​calculadorateio−calculado​​≤0,05 | ✅ OK |
| ∥rateio−calculadocalculado∥>0,05\\left\\\| \\frac{rateio - calculado}{calculado} \\right\\\| > 0{,}05​calculadorateio−calculado​​>0,05 | 🔴 DIVERGENTE |
| NF sem valor calculado | ⚠️ SEM_BASE |
| CT-e sem vínculo | ⚠️ SEM_VINCULO |

🧪 Testes
pytest app/tests/ -v

Atualmente: 13 testes unitários cobrindo o engine de cálculo de frete:
| Categoria | Cenários |
| --- | --- |
| Cálculo correto | 4 testes |
| Validação de peso | 3 testes |
| Configuração da tabela | 4 testes |
| Metadados | 2 testes |

🔐 Variáveis de Ambiente
| Variável | Descrição | Padrão |
| --- | --- | --- |
| DATABASE_URL | URL de conexão PostgreSQL (asyncpg) | — |
| SECRET_KEY | Chave para assinatura JWT | — |
| ALGORITHM | Algoritmo JWT | HS256 |
| ACCESS_TOKEN_EXPIRE_MINUTES | Expiração do token | 480 |
| APP_NAME | Nome da aplicação | ApuraFrete |
| DEBUG | Modo debug | false |
⚠️ Nunca faça commit do .env — ele já está no .gitignore.

📝 Status do Projeto
| Etapa | Descrição | Status |
| --- | --- | --- |
| 1 | Modelagem do banco | ✅ |
| 2 | Schemas + Validação | ✅ |
| 2a | Importação de NF | ✅ |
| 3 | Cálculo de frete | 🔄 Engine e orquestração concluídos; router pendente |
| 4 | Exportação planilhas | 🔲 |
| 5 | Importação CT-e (XML) | 🔲 |
| 6 | Auditoria e rateio | 🔲 |
| 7 | Trilha de auditoria/logs | 🔄 |
| 8 | RBAC + multi-tenant | 🔲 |

📄 Licença
Este projeto é proprietário da ADillTech. Todos os direitos reservados.

👤 Autor
Allison — ADillTech
Última atualização: 11/07/2026


---

## Resumo do que foi incluído:

| Seção | Conteúdo |
|-------|----------|
| 🎯 Visão Geral | 3 fluxos principais do SaaS |
| ✨ Funcionalidades | Status MVP com ✅/🔄/🔲 claros |
| 🛠️ Stack | Tabela com todas as tecnologias |
| 🚀 Como Rodar | Passo a passo completo (7 passos) |
| 📁 Estrutura | Árvore de pastas + padrão de 4 camadas |
| ⚖️ Regras de Negócio | Fórmulas LaTeX (peso, frete, rateio, auditoria) |
| 🧪 Testes | Comando + breakdown dos 13 cenários |
| 🔐 Variáveis | Todas as env vars documentadas |
| 📝 Status | Etapas 1 a 8 com ✅/🔄/🔲 |

---
