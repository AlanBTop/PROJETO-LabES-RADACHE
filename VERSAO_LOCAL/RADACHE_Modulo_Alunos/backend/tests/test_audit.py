"""Regressões da auditoria: contratos, cache, privacidade e crescimento de consultas."""
from contextlib import closing
import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

import app
import gestao_local
import simulation_store as store
import risk_history
from auth import SessionManager, gerar_hash_senha


class AuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.credential = gerar_hash_senha('senha-auditoria')
        cls.server = app.ThreadingHTTPServer(('127.0.0.1', 0), app.RadacheRequestHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown(); cls.server.server_close(); cls.thread.join(timeout=3)

    def request(self, path, method='GET', headers=None):
        conn = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=4)
        try:
            conn.request(method, path, headers=headers or {})
            response = conn.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            conn.close()

    def test_static_revalidation_avoids_retransmission_and_supports_weak_lists(self):
        status, headers, body = self.request('/assets/radache-theme.css')
        self.assertEqual(status, 200); self.assertTrue(body)
        self.assertIn('no-cache', headers['Cache-Control'])
        for value in (headers['ETag'], '"outro", ' + headers['ETag'], '*'):
            status, repeated, content = self.request('/assets/radache-theme.css', headers={'If-None-Match': value})
            self.assertEqual(status, 304); self.assertEqual(content, b'')
            self.assertEqual(repeated['ETag'], headers['ETag'])

    def test_changed_static_content_invalidates_validator(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); file = root / 'app.css'; file.write_text('body{}')
            with patch.object(app, 'ASSETS_DIR', root):
                etag = self.request('/assets/app.css')[1]['ETag']
                file.write_text('body{color:blue}')
                status, headers, content = self.request('/assets/app.css', headers={'If-None-Match': etag})
                self.assertEqual(status, 200); self.assertNotEqual(headers['ETag'], etag)
                self.assertEqual(content, b'body{color:blue}')

    def test_head_has_same_metadata_without_body(self):
        get = self.request('/assets/radache-theme.css')
        head = self.request('/assets/radache-theme.css', method='HEAD')
        self.assertEqual(head[0], 200); self.assertEqual(head[2], b'')
        for name in ('Content-Length', 'ETag', 'Cache-Control'):
            self.assertEqual(head[1][name], get[1][name])

    def test_security_headers_cover_html_errors_and_redirects(self):
        for path in ('/', '/nao-existe.css', '/painel-demo'):
            with self.subTest(path=path):
                _, headers, _ = self.request(path)
                self.assertEqual(headers['X-Frame-Options'], 'DENY')
                self.assertEqual(headers['Referrer-Policy'], 'same-origin')
                self.assertEqual(headers['X-Content-Type-Options'], 'nosniff')

    def test_internal_exception_details_never_reach_client(self):
        user = dict(id='audit', username='audit', perfil='admin_tecnico', role='coordenacao', scope=None)
        with patch.object(app.RadacheRequestHandler, '_session', return_value=user), patch.object(app.analytics, 'overview', side_effect=RuntimeError('database/path secret=NAO-EXIBIR')):
            status, headers, body = self.request('/api/analytics')
        self.assertEqual(status, 500); self.assertEqual(headers['Cache-Control'], 'no-store')
        self.assertNotIn(b'NAO-EXIBIR', body); self.assertNotIn(b'database/path', body)
        self.assertFalse(json.loads(body)['sucesso'])

    def test_expired_legacy_sessions_are_pruned_on_new_login(self):
        manager = SessionManager({'audit': {**self.credential, 'role': 'coordenacao'}})
        manager._sessoes['expired'] = {'expires_at': 0}
        active = manager.autenticar('audit', 'senha-auditoria')
        self.assertNotIn('expired', manager._sessoes)
        self.assertIsNotNone(manager.obter_sessao(active['token']))

    def test_expired_management_session_is_removed(self):
        with patch.object(gestao_local, 'SESSOES', {'expired': {'expira': 0}}):
            with self.assertRaises(gestao_local.ErroLocal) as error:
                gestao_local.sessao('expired')
            self.assertEqual(error.exception.status, 401)
            self.assertNotIn('expired', gestao_local.SESSOES)

    def test_projection_preserves_order_history_and_latest_assessment_with_constant_queries(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(store, 'ACADEMIC', Path(tmp) / 'academic.db'), patch.object(store, 'OPERATIONAL', Path(tmp) / 'operational.db'):
            store.init()
            for i in range(5):
                store.save(dict(nome=f'TESTE {i}', matricula=f'AUD-{i}', curso='Computação', nota_media=8, frequencia=90))
            for aid in (1, 2):
                session = store.session(aid)
                for n, text in enumerate(('1', '4', '1')):
                    store.session(aid, dict(acao='responder', texto=text, sessao_id=session['sessao_id'], id_cliente=f'{aid}-{n}'))
                store.session(aid, dict(acao='mes', id_cliente=f'mes-{aid}'))
            # Oráculo conserva o contrato anterior, incluindo históricos e a ordem rowid.
            expected = []
            with closing(store.connect(store.OPERATIONAL)) as conn:
                for student in store.students():
                    aid = student['id']
                    evaluations = [json.loads(r[0]) for r in conn.execute('SELECT dados FROM avaliacoes_sim WHERE aluno_id=? ORDER BY rowid DESC', (aid,))]
                    sessions = [dict(id=r['id'], **store.snapshot(json.loads(r['estado']))) for r in conn.execute('SELECT * FROM sessoes WHERE aluno_id=? ORDER BY rowid DESC', (aid,))]
                    history = [dict(r) for r in conn.execute('SELECT * FROM mensagens WHERE aluno_id=? ORDER BY rowid', (aid,))]
                    latest = risk_history.latest(list(reversed(evaluations))) or (evaluations[0] if evaluations else None)
                    expected.append((student['id'], evaluations, sessions, history, latest))
            statements = []; connect = store.connect
            def traced(*args, **kwargs):
                conn = connect(*args, **kwargs); conn.set_trace_callback(statements.append); return conn
            with patch.object(store, 'connect', traced):
                rows = store.projected()
            self.assertEqual(sum(s.startswith('SELECT') for s in statements), 4)
            self.assertEqual(len(rows), len(expected))
            for row, (aid, evaluations, sessions, history, latest) in zip(rows, expected):
                self.assertEqual(row['id'], -aid)
                self.assertEqual(row['historico_avaliacoes'], evaluations)
                self.assertEqual(row['historico_checkins'], sessions)
                self.assertEqual(row['mensagens_simuladas'], history)
                self.assertEqual(row['avaliacao_atual'], latest)
                self.assertEqual(row['ultima_interacao'], history[-1]['timestamp'] if history else None)

    def test_empty_catalog_does_not_require_operational_schema(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(store, 'ACADEMIC', Path(tmp) / 'academic.db'), patch.object(store, 'OPERATIONAL', Path(tmp) / 'operational.db'):
            store.init()
            with patch.object(store, 'OPERATIONAL', Path(tmp) / 'not-initialized.db'):
                self.assertEqual(store.projected(), [])

    def test_projection_ignores_sessions_outside_the_fictional_catalog(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(store, 'ACADEMIC', Path(tmp) / 'academic.db'), patch.object(store, 'OPERATIONAL', Path(tmp) / 'operational.db'):
            store.init()
            aid = store.save(dict(nome='TESTE Escopo', matricula='AUD-SCOPE', curso='Computação'))
            with closing(store.connect(store.OPERATIONAL)) as conn, conn:
                conn.executemany('INSERT INTO sessoes(id,aluno_id,estado) VALUES (?,?,?)', [('original', -1, 'fora do catálogo'), ('orphan', 999, 'fora do catálogo')])
            rows = store.projected()
            self.assertEqual([row['id'] for row in rows], [-aid])
            self.assertEqual(rows[0]['historico_checkins'], [])


if __name__ == '__main__':
    unittest.main()
