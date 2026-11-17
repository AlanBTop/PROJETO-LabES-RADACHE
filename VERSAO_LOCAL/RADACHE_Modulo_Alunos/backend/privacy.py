"""Minimização dos registros de entrega e expurgo explícito de respostas antigas."""
from contextlib import closing
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import threading

import database

KEY_LOCK = threading.RLock()


def phone_hash(number):
    import whatsapp
    path = Path(str(database.DB_PATH) + '.telefone.key')
    with KEY_LOCK:
        try:
            key = path.read_bytes()
        except FileNotFoundError:
            key = secrets.token_bytes(32)
            path.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, 'wb') as target:
                target.write(key)
    return 'h1:' + hmac.new(key, whatsapp._telefone_internacional(number).encode(), hashlib.sha256).hexdigest()


def initialize(cursor):
    columns = {r['name'] for r in cursor.execute('PRAGMA table_info(whatsapp_eventos)')}
    for column, definition in (('aluno_id', 'INTEGER REFERENCES alunos(id) ON DELETE CASCADE'),
                               ('checkin_id', 'INTEGER REFERENCES checkins(id) ON DELETE CASCADE')):
        if column not in columns:
            cursor.execute('ALTER TABLE whatsapp_eventos ADD COLUMN ' + column + ' ' + definition)
    cursor.execute('CREATE INDEX IF NOT EXISTS evento_checkin ON whatsapp_eventos(checkin_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS evento_origem ON whatsapp_eventos(origem)')
    # A migração não tenta inferir a qual check-in pertence uma entrega antiga.
    for row in cursor.execute("SELECT mensagem_id,origem FROM whatsapp_eventos WHERE origem NOT LIKE 'h1:%'").fetchall():
        cursor.execute('UPDATE whatsapp_eventos SET origem=? WHERE mensagem_id=?', (phone_hash(row['origem']), row['mensagem_id']))


def scrub_assessments(conn, checkin_id):
    rows = conn.execute("SELECT id,metadados_risco FROM avaliacoes WHERE origem_dados='whatsapp_checkin' AND referencia_origem=?", (str(checkin_id),)).fetchall()
    for row in rows:
        meta = json.loads(row['metadados_risco'] or '{}')
        meta['componentes'] = {k: v for k, v in meta.get('componentes', {}).items() if k not in {'financeiro', 'psicologico'}}
        meta['fatores'] = [v for v in meta.get('fatores', []) if v.get('chave') not in {'financeiro', 'psicologico'}]
        meta['respostas_removidas'] = True
        conn.execute('UPDATE avaliacoes SET resposta_financeira=NULL,resposta_psicologica=NULL,metadados_risco=? WHERE id=?', (json.dumps(meta), row['id']))
        # Comparações posteriores podem conter a resposta anterior em seus fatores.
        later = conn.execute('SELECT id,metadados_risco FROM avaliacoes WHERE aluno_id=(SELECT aluno_id FROM avaliacoes WHERE id=?) AND id>?', (row['id'], row['id'])).fetchall()
        for assessment in later:
            meta = json.loads(assessment['metadados_risco'] or '{}')
            meta['fatores'] = [v for v in meta.get('fatores', []) if v.get('chave') not in {'financeiro', 'psicologico'}]
            conn.execute('UPDATE avaliacoes SET metadados_risco=? WHERE id=?', (json.dumps(meta), assessment['id']))


def revoke(conn, checkin_id, aluno_id):
    row = conn.execute('SELECT telefone FROM alunos WHERE id=?', (aluno_id,)).fetchone()
    hashed = phone_hash(row['telefone']) if row else ''
    conn.execute('DELETE FROM whatsapp_eventos WHERE checkin_id=? OR (checkin_id IS NULL AND origem=?)', (checkin_id, hashed))
    columns = {r['name'] for r in conn.execute('PRAGMA table_info(checkins)')}
    if 'resposta_academica' in columns:
        conn.execute('UPDATE checkins SET resposta_academica=NULL WHERE id=?', (checkin_id,))
    scrub_assessments(conn, checkin_id)


def purge(days=365, apply=False):
    if not isinstance(days, int) or days < 1:
        raise ValueError('Retenção deve ser um número positivo de dias.')
    with closing(database.get_connection()) as conn, conn:
        cutoff = '-' + str(days) + ' days'
        rows = conn.execute("SELECT id,aluno_id FROM checkins WHERE datetime(data_checkin)<datetime('now',?) AND (resposta_financeira IS NOT NULL OR resposta_psicologica IS NOT NULL)", (cutoff,)).fetchall()
        events = conn.execute("SELECT count(*) FROM whatsapp_eventos WHERE datetime(recebido_em)<datetime('now',?)", (cutoff,)).fetchone()[0]
        if apply:
            for row in rows:
                revoke(conn, row['id'], row['aluno_id'])
                conn.execute("UPDATE checkins SET resposta_financeira=NULL,resposta_psicologica=NULL,consentimento_lgpd=0,estado_conversa='expurgado' WHERE id=?", (row['id'],))
            conn.execute("DELETE FROM whatsapp_eventos WHERE datetime(recebido_em)<datetime('now',?)", (cutoff,))
        return dict(checkins=len(rows), eventos=events, aplicado=apply, dias=days)
