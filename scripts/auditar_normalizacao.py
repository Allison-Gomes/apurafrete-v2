'''
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📁 ARQUIVO : scripts/auditar_normalizacao.py
📦 MÓDULO  : Scripts (manutencao)
🎯 OBJETIVO: Auditar rotas_frete.cidade_normalizada apos
             a Decisao #73 Acao 2, listando as chaves que
             deixariam de casar com a normalizacao nova.
📅 CRIADO  : 01/08/2026
📌 REGRAS  : Decisao #73 Acao 2 | RN v2.9 secao 1.9
⚠️ CRITICO : SOMENTE LEITURA. Nao executa UPDATE, INSERT
             nem DELETE. Nenhum commit e emitido.
⚠️ LIMITE  : Detecta apenas chaves que a funcao NOVA ainda
             alteraria. Chaves ja fundidas pela regra antiga
             (ex.: "EMBUSP") sao estaveis nas duas versoes e
             NAO aparecem aqui — para essas e preciso comparar
             com o texto de origem do cadastro.
🚫 PROIBIDO: Rodar em producao sem backup previo do banco.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

USO (CMD do VS Code):
    cd /d C:\\ADILLTECH\\apurafrete-v2 && python scripts\\auditar_normalizacao.py
'''

import asyncio

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.rota_frete import RotaFrete
from app.utils.normalizacao import normalizar_cidade


async def auditar() -> None:
    '''
    Percorre todas as rotas e compara a chave gravada com o
    retorno da normalizacao vigente.

    Imprime:
        - total de rotas na tabela;
        - total de rotas com cidade preenchida (nao curinga);
        - lista das divergencias no formato
          tabela_id | UF | chave_atual -> chave_nova
    '''
    async with AsyncSessionLocal() as session:
        resultado = await session.execute(select(RotaFrete))
        rotas = resultado.scalars().all()

    com_cidade = [r for r in rotas if r.cidade_normalizada]

    divergentes = [
        (r, normalizar_cidade(r.cidade_normalizada))
        for r in com_cidade
        if normalizar_cidade(r.cidade_normalizada) != r.cidade_normalizada
    ]

    print('=' * 60)
    print('AUDITORIA DE NORMALIZACAO — rotas_frete')
    print('=' * 60)
    print(f'Total de rotas .............: {len(rotas)}')
    print(f'Rotas com cidade (nao curinga): {len(com_cidade)}')
    print(f'Rotas curinga (cidade NULL) .: {len(rotas) - len(com_cidade)}')
    print(f'Chaves divergentes .........: {len(divergentes)}')
    print('-' * 60)

    if not divergentes:
        print('OK — nenhuma chave gravada muda com a regra nova.')
        return

    for rota, chave_nova in divergentes:
        print(
            f'tabela_id={rota.tabela_id} | {rota.uf} | '
            f'{rota.cidade_normalizada!r} -> {chave_nova!r}'
        )

    print('-' * 60)
    print('ACAO: nenhuma alteracao feita. Aguardando decisao.')


if __name__ == '__main__':
    asyncio.run(auditar())
