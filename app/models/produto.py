'''
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📁 ARQUIVO : produto.py
📦 MÓDULO  : Cadastros
🎯 OBJETIVO: Define o model Produto (catálogo global),
             com peso real como métrica única para
             cálculo de frete. Sem cubagem no MVP.
🔗 DEPENDE  : app/models/base.py
📅 CRIADO  : 24/06/2026
📅 ATUALIZADO: 06/07/2026 — removida cubagem (Opção B);
              renomeado peso_unitario → peso_real_kg;
              docstrings padronizadas com aspas triplas simples
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
'''

from sqlalchemy import Column, String, Numeric, Boolean

from app.models.base import Base, AuditMixin


class Produto(Base, AuditMixin):
    '''
    🎯 O QUE FAZ:
        Representa um produto no catálogo global do SaaS,
        compartilhado entre todos os tenants. Fornece o
        peso real unitário para a fórmula de cálculo de
        frete de cada NF.

    📐 REGRA DE NEGÓCIO:
        - SKU é único globalmente (catálogo compartilhado
          entre todas as empresas/tenants do SaaS).
        - peso_real_kg deve ser > 0 (obrigatório).
        - A fórmula de peso total da NF é:
          peso_total_kg = QTD_CX × peso_real_kg
        - Não há cubagem (C × L × A) no escopo do MVP.
        - Produto inativo (ativo=False) não pode ser
          selecionado em novas importações.

    🗂️  TABELA: produtos

    ⚠️  ATENÇÃO:
        Não modificar sem autorização de Allison.
        A remoção de cubagem é definitiva para o MVP
        (decisão Opção B, 06/07/2026).
    '''

    __tablename__ = 'produtos'

    sku = Column(
        String(50), nullable=False, unique=True, index=True,
        comment='Código único do produto (SKU) — global entre tenants'
    )
    descricao = Column(
        String(255), nullable=False,
        comment='Descrição/nome do produto'
    )
    ncm = Column(
        String(10), nullable=True,
        comment='Código NCM do produto'
    )
    peso_real_kg = Column(
        Numeric(10, 3), nullable=False,
        comment='Peso real unitário em kg — métrica única para cálculo de frete no MVP'
    )
    ativo = Column(
        Boolean, default=True, nullable=False,
        comment='True = produto disponível para uso em importações'
    )

    def __repr__(self):
        return f'<Produto [{self.sku}] {self.descricao}>'
