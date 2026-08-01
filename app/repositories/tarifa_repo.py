'''
Acesso a dados da resolucao de tarifa.

Retorna a faixa vigente para (transportadora, modalidade, UF, cidade, peso).
Regras aplicadas no SQL para garantir determinismo:
  - cidade especifica tem prioridade sobre curinga da UF;
  - faixa de peso semiaberta [peso_de_kg, peso_ate_kg);
  - peso_ate_kg NULL = faixa aberta superior.
'''

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

_SQL_TARIFA = text(
    '''
    WITH rota AS (
        SELECT r.tabela_id,
               r.prazo_dias,
               r.valor_minimo_rota,
               ROW_NUMBER() OVER (
                   ORDER BY (r.cidade_normalizada IS NOT NULL) DESC,
                            r.criado_em DESC
               ) AS prioridade
        FROM rotas_frete r
        JOIN tabelas_frete t ON t.id = r.tabela_id
        WHERE r.ativo
          AND t.ativo
          AND t.transportadora_id = :transportadora_id
          AND t.modalidade = :modalidade
          AND r.uf = :uf_destino
          AND (r.cidade_normalizada = :cidade_normalizada
               OR r.cidade_normalizada IS NULL)
    )
    SELECT f.id                 AS faixa_id,
           rota.tabela_id       AS tabela_id,
           f.valor_kg           AS valor_kg,
           f.valor_minimo_faixa AS valor_minimo_faixa,
           rota.valor_minimo_rota AS valor_minimo_rota,
           rota.prazo_dias      AS prazo_dias
    FROM rota
    JOIN faixas_frete f ON f.tabela_id = rota.tabela_id
    WHERE rota.prioridade = 1
      AND f.ativo
      AND :peso_kg >= f.peso_de_kg
      AND (f.peso_ate_kg IS NULL OR :peso_kg < f.peso_ate_kg)
    LIMIT 1
    '''
)


@dataclass(frozen=True)
class Tarifa:
    '''Snapshot imutavel da tarifa resolvida, para auditoria.'''

    tabela_id: UUID
    faixa_id: UUID
    valor_kg: Decimal
    valor_minimo_faixa: Decimal | None
    valor_minimo_rota: Decimal | None
    prazo_dias: int | None


def buscar_tarifa(
    db: Session,
    *,
    transportadora_id: UUID,
    modalidade: str,
    uf_destino: str,
    cidade_normalizada: str | None,
    peso_kg: Decimal,
) -> Tarifa | None:
    '''Resolve a tarifa vigente ou retorna None se nao houver cobertura.'''
    linha = db.execute(
        _SQL_TARIFA,
        {
            "transportadora_id": str(transportadora_id),
            "modalidade": modalidade,
            "uf_destino": uf_destino,
            "cidade_normalizada": cidade_normalizada,
            "peso_kg": peso_kg,
        },
    ).mappings().first()

    if linha is None:
        return None

    return Tarifa(
        tabela_id=linha["tabela_id"],
        faixa_id=linha["faixa_id"],
        valor_kg=linha["valor_kg"],
        valor_minimo_faixa=linha["valor_minimo_faixa"],
        valor_minimo_rota=linha["valor_minimo_rota"],
        prazo_dias=linha["prazo_dias"],
    )
