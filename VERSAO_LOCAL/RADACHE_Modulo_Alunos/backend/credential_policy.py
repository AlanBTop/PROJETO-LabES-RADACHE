"""Credenciais de exemplo somente no modo explícito de demonstração."""
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import threading

from auth import gerar_hash_senha, ITERACOES_PBKDF2

LOCK = threading.RLock()


def demo():
    return os.environ.get('RADACHE_DEMO') == '1'


def provision(email):
    if demo():
        return gerar_hash_senha('admin123')
    import database
    path = Path(str(database.DB_PATH) + '.acessos-iniciais.json')
    with LOCK:
        if path.exists():
            entries = json.loads(path.read_text(encoding='utf-8'))
        else:
            entries = {}
        password = entries.setdefault(email, secrets.token_urlsafe(24))
        # Arquivo externo ao conteúdo servido pelo HTTP; permissões restritas onde suportadas.
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8') as target:
            json.dump(entries, target, ensure_ascii=False, indent=2)
        return gerar_hash_senha(password)


def protect_existing(conn):
    if demo():
        return
    marker = 'credenciais-proprias-v1'
    if conn.execute('SELECT 1 FROM gestao_meta WHERE chave=?', (marker,)).fetchone():
        return
    for row in conn.execute('SELECT * FROM gestao_usuarios').fetchall():
        known = hashlib.pbkdf2_hmac('sha256', b'admin123', bytes.fromhex(row['salt']), ITERACOES_PBKDF2).hex()
        if hmac.compare_digest(known, row['password_hash']):
            data = json.loads(row['dados'])
            data.update(trocaSenhaObrigatoria=True, versaoAcesso=data.get('versaoAcesso', 1) + 1)
            cred = provision(row['email'])
            conn.execute('UPDATE gestao_usuarios SET dados=?,salt=?,password_hash=? WHERE id=?',
                         (json.dumps(data), cred['salt'], cred['password_hash'], row['id']))
    conn.execute('INSERT INTO gestao_meta VALUES (?)', (marker,))
