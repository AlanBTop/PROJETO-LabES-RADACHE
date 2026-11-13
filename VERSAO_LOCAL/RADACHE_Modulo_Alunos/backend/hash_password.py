"""Gera um hash seguro para cadastrar usuário em RADACHE_USERS."""
import json
from getpass import getpass

from auth import gerar_hash_senha


if __name__ == "__main__":
    senha = getpass("Nova senha (mínimo de 8 caracteres): ")
    confirmacao = getpass("Confirme a senha: ")
    if senha != confirmacao:
        raise SystemExit("As senhas não conferem.")
    print(json.dumps(gerar_hash_senha(senha), ensure_ascii=False))
