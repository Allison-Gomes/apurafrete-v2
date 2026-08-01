'''
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📁 ARQUIVO : app/utils/__init__.py
📦 MÓDULO  : Utils
🎯 OBJETIVO: Marca app/utils como pacote Python e
             reexporta os helpers de normalização.
📅 CRIADO  : 01/08/2026
📌 REGRA   : Decisão #73 — normalizacao.py e a UNICA
             fonte de verdade da normalizacao geografica.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
'''

from app.utils.normalizacao import normalizar_cidade, normalizar_uf

__all__ = ['normalizar_cidade', 'normalizar_uf']
