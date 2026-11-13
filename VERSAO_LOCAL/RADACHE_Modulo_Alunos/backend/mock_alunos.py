"""Catálogo acadêmico fictício local; escrita exclusiva no módulo administrativo."""
import simulation_store as store
from simulation_api import respond as responder, store_enabled as habilitado

def listar(): return store.students()
def incluir(dados): return store.save(dados)
def excluir(ident): return store.deactivate(ident)
def projetados(): return store.projected() if habilitado() else []
