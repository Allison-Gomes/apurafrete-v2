'''
╔══════════════════════════════════════════════════════════╗
║ ARQUIVO : seeds/seed_inicial.py                          ║
║ MÓDULO  : Seeds / População inicial                      ║
║ OBJETIVO: Cria empresa + usuário admin para              ║
║           desenvolvimento e testes.                      ║
║ DEPENDE : app/core/database.py (AsyncSessionLocal)       ║
║           app/core/security.py (hash_senha)              ║
║           app/models/empresa.py                          ║
║           app/models/usuario.py                          ║
║ DATA    : 11/07/2026                                     ║
╚══════════════════════════════════════════════════════════╝
'''

import asyncio
import uuid

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.core.security import hash_senha
from app.models.empresa import Empresa
from app.models.usuario import PerfilAcesso, Usuario


# ──────────────────────────────────────────────────────────
# 🔧 DADOS DO SEED
# ──────────────────────────────────────────────────────────
EMPRESA_RAZAO = 'Empresa Demo LTDA'
EMPRESA_CNPJ = '12345678000199'

ADMIN_NOME = 'Allison'
ADMIN_EMAIL = 'allison@apurafrete.com.br'
ADMIN_SENHA = '123456'


async def executar_seed():
    '''
    Executa o seed: cria empresa e usuário admin
    se ainda não existirem.
    '''
    async with AsyncSessionLocal() as session:
        # ── Verifica se empresa já existe ──
        resultado = await session.execute(
            select(Empresa).where(Empresa.cnpj == EMPRESA_CNPJ)
        )
        empresa = resultado.scalar_one_or_none()

        if empresa is None:
            empresa = Empresa(
                id=uuid.uuid4(),
                razao_social=EMPRESA_RAZAO,
                cnpj=EMPRESA_CNPJ,
                tipo='tenant',
                plano='basico',
                trial=False,
                ativo=True,
            )
            session.add(empresa)
            await session.flush()
            print(f'✅ Empresa criada: {empresa.razao_social} ({empresa.cnpj})')
        else:
            print(f'⏭️  Empresa já existe: {empresa.razao_social}')

        # ── Verifica se admin já existe ──
        resultado = await session.execute(
            select(Usuario).where(Usuario.email == ADMIN_EMAIL)
        )
        usuario = resultado.scalar_one_or_none()

        if usuario is None:
            usuario = Usuario(
                id=uuid.uuid4(),
                empresa_id=empresa.id,
                nome=ADMIN_NOME,
                email=ADMIN_EMAIL,
                senha_hash=hash_senha(ADMIN_SENHA),
                perfil=PerfilAcesso.ADMIN,
                primeiro_acesso=False,
                ativo=True,
            )
            session.add(usuario)
            await session.commit()
            print(f'✅ Admin criado: {usuario.email}')
        else:
            print(f'⏭️  Admin já existe: {usuario.email}')

        print('\n🎉 Seed finalizado com sucesso!')
        print(f'📧 Login: {ADMIN_EMAIL}')
        print(f'🔑 Senha: {ADMIN_SENHA}')


if __name__ == '__main__':
    asyncio.run(executar_seed())
