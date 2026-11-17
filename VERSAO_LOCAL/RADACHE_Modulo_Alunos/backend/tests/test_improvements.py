"""Regressões de segurança, integridade e privacidade da revisão de 13/11."""
from contextlib import closing
import http.client
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

import app
import analytics
import credential_policy
import database
import gestao_local
import privacy
import security
import simulation_store as store
import whatsapp


class Improvements(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        for obj, name, value in ((database, 'DB_PATH', root/'legacy.db'), (store, 'ACADEMIC', root/'academic.db'),
                                 (store, 'OPERATIONAL', root/'operational.db'), (security, 'LOGIN_LIMITER', security.LoginLimiter())):
            change = patch.object(obj, name, value)
            change.start(); self.addCleanup(change.stop)
        env = patch.dict(os.environ, {'RADACHE_DEMO': '1', 'RADACHE_HTTPS': '0'})
        env.start(); self.addCleanup(env.stop)
        database.init_db(); store.init()
        gestao_local.SESSOES.clear()
        self.addCleanup(gestao_local.SESSOES.clear)
        self.server = app.ThreadingHTTPServer(('127.0.0.1', 0), app.RadacheRequestHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.close)

    def close(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(timeout=3)

    def http(self, path, data=None, headers=None, method=None):
        conn = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        try:
            conn.request(method or ('POST' if data is not None else 'GET'), path,
                         body=json.dumps(data) if data is not None else None,
                         headers={'Content-Type': 'application/json', **(headers or {})})
            response = conn.getresponse()
            raw = response.read()
            body = json.loads(raw) if response.getheader('Content-Type', '').startswith('application/json') else raw
            return response.status, dict(response.getheaders()), body
        finally:
            conn.close()

    def complete(self, emotion='1'):
        with patch.object(whatsapp, 'enviar_template'), patch.object(whatsapp, 'enviar_texto') as sent:
            ident = whatsapp.iniciar_checkin(1)
            for i, text in enumerate(('SIM', '3', emotion)):
                whatsapp.processar_mensagem('5565998123401', text, 'message-' + str(i))
            self.assertIn('acolhimento', sent.call_args.args[1])
        return ident

    def test_secure_accounts_require_change_and_revoke_other_sessions(self):
        with patch.dict(os.environ, {'RADACHE_DEMO': '0'}):
            gestao_local.iniciar()
            path = Path(str(database.DB_PATH) + '.acessos-iniciais.json')
            passwords = json.loads(path.read_text(encoding='utf-8'))
            self.assertEqual(len(passwords), len(set(passwords.values())))
            self.assertNotIn('admin123', passwords.values())
            with closing(database.get_connection()) as conn:
                rows = conn.execute('SELECT salt FROM gestao_usuarios').fetchall()
                self.assertEqual(len(rows), len({r[0] for r in rows}))
            password = passwords['admin@radache.local']
            status, headers, body = self.http('/api/local/login', dict(email='admin@radache.local', senha=password))
            self.assertEqual(status, 200, body)
            self.assertTrue(body['dados']['usuario']['trocaSenhaObrigatoria'])
            token = body['dados']['token']
            bearer = {'Authorization': 'Bearer ' + token}
            self.assertEqual(self.http('/api/alunos', headers=bearer)[0], 403)
            self.assertEqual(self.http('/api/local/usuarios', headers=bearer)[0], 403)
            new = 'Uma-senha-propria-2026'
            self.assertEqual(self.http('/api/local/senha', dict(senhaAtual=password, novaSenha=new), bearer)[0], 200)
            self.assertEqual(self.http('/api/local/sessao', headers=bearer)[0], 401)
            _, _, login = self.http('/api/local/login', dict(email='admin@radache.local', senha=new))
            self.assertFalse(login['dados']['usuario']['trocaSenhaObrigatoria'])
            gestao_local.iniciar()
            self.assertEqual(self.http('/api/local/login', dict(email='admin@radache.local', senha=new))[0], 200)

    def test_login_limit_is_shared_by_aliases(self):
        gestao_local.iniciar()
        for _ in range(6):
            self.assertEqual(self.http('/api/local/login', dict(email='admin@radache.local', senha='admin123'))[0], 200)
        for i in range(5):
            status, _, _ = self.http('/api/local/login' if i % 2 else '/api/v1/login', dict(email='admin@radache.local', senha='errada'))
            self.assertEqual(status, 401)
        self.assertEqual(self.http('/api/login', dict(usuario='admin', senha='admin123'))[0], 429)

    def test_limit_expires_and_separates_ip_and_user(self):
        now = [1000]
        limiter = security.LoginLimiter(clock=lambda: now[0])
        for i in range(5):
            self.assertTrue(limiter.allow('ip1', 'user' + str(i)))
        self.assertFalse(limiter.allow('ip1', 'different'))
        self.assertTrue(limiter.allow('ip2', 'different'))
        now[0] += 59
        self.assertFalse(limiter.allow('ip1', 'user0'))
        now[0] += 1
        self.assertTrue(limiter.allow('ip1', 'user0'))
        ticket = limiter.reserve('ip3', 'ok')
        limiter.release(ticket)
        self.assertEqual(len(limiter.attempts[('ip', 'ip3')]), 0)

    def test_csrf_cors_csp_and_secure_cookie(self):
        gestao_local.iniciar()
        status, headers, body = self.http('/api/local/login', dict(email='admin@radache.local', senha='admin123'))
        self.assertEqual(status, 200)
        self.assertNotIn('Access-Control-Allow-Origin', headers)
        self.assertIn("default-src 'self'", headers['Content-Security-Policy'])
        self.assertIn('HttpOnly', headers['Set-Cookie'])
        cookie = headers['Set-Cookie'].split(';')[0]
        self.assertEqual(self.http('/api/local/logout', {}, {'Cookie': cookie})[0], 403)
        self.assertEqual(self.http('/api/local/logout', {}, {'Cookie': cookie, 'Origin': 'http://evil.example'})[0], 403)
        self.assertEqual(self.http('/api/local/logout', {}, {'Cookie': cookie, 'Origin': 'http://127.0.0.1:' + str(self.server.server_port)})[0], 200)
        with patch.dict(os.environ, {'RADACHE_HTTPS': '1'}):
            _, headers, _ = self.http('/api/local/login', dict(email='admin@radache.local', senha='admin123'))
            self.assertIn('; Secure', headers['Set-Cookie'])
        self.assertIn('Content-Security-Policy', self.http('/assets/change-password.html')[1])

    def test_revocation_removes_events_raw_answers_and_alert(self):
        ident = self.complete()
        with closing(database.get_connection()) as conn:
            rows = conn.execute('SELECT origem,checkin_id FROM whatsapp_eventos').fetchall()
            self.assertEqual(len(rows), 3)
            self.assertTrue(all(row['origem'].startswith('h1:') and row['checkin_id'] == ident for row in rows))
        self.assertTrue(analytics.detail(1, 'nae')['alerta_acolhimento'])
        with patch.object(whatsapp, 'enviar_texto'):
            whatsapp.processar_mensagem('5565998123401', 'REVOGAR', 'revoke-id')
        with closing(database.get_connection()) as conn:
            self.assertEqual(conn.execute("SELECT count(*) FROM whatsapp_eventos WHERE mensagem_id LIKE 'message-%'").fetchone()[0], 0)
            row = conn.execute("SELECT resposta_psicologica,metadados_risco FROM avaliacoes WHERE origem_dados='whatsapp_checkin'").fetchone()
            self.assertIsNone(row[0])
            self.assertNotIn('psicologico', json.loads(row[1])['componentes'])
        self.assertFalse(analytics.detail(1, 'nae')['alerta_acolhimento'])

    def test_phone_lookup_is_indexed_updates_and_rejects_ambiguity(self):
        self.assertEqual(whatsapp._encontrar_aluno_por_telefone('5565998123401'), 1)
        with closing(database.get_connection()) as conn, conn:
            plan = conn.execute('EXPLAIN QUERY PLAN SELECT id FROM alunos WHERE telefone_normalizado=?', ('5565998123401',)).fetchall()
            self.assertIn('INDEX', str([tuple(r) for r in plan]))
            conn.execute("UPDATE alunos SET telefone='(65) 99812-3401' WHERE id=2")
        self.assertIsNone(whatsapp._encontrar_aluno_por_telefone('5565998123401'))

    def test_incomplete_assessment_rolls_back_and_full_assessment_uses_components(self):
        data = dict(nome='Teste',matricula='UNICO',curso='Curso',periodo=1,email='',telefone='',indice_risco=20)
        with self.assertRaisesRegex(ValueError, 'avaliação exige'):
            database.create_aluno(data)
        with closing(database.get_connection()) as conn:
            self.assertEqual(conn.execute("SELECT count(*) FROM alunos WHERE matricula='UNICO'").fetchone()[0], 0)
        data.update(nota_media=10,frequencia=100,resposta_financeira='não sinto dificuldade',resposta_psicologica='5',indice_risco=0)
        ident = database.create_aluno(data)
        row = database.get_aluno_by_id(ident)['avaliacao_atual']
        self.assertEqual(row['indice_risco'], 0)
        self.assertEqual(row['resposta_psicologica'], '5')
        bad = dict(data, nome='Não gravar', indice_risco=30)
        with self.assertRaises(ValueError):
            database.update_aluno(ident, bad)
        self.assertEqual(database.get_aluno_by_id(ident)['nome'], 'Teste')

    def test_initialization_preserves_historical_classifications(self):
        with closing(database.get_connection()) as conn, conn:
            conn.execute("UPDATE avaliacoes SET indice_risco=80,classificacao_risco='estavel' WHERE id=1")
        database.init_db()
        with closing(database.get_connection()) as conn:
            self.assertEqual(conn.execute('SELECT classificacao_risco FROM avaliacoes WHERE id=1').fetchone()[0], 'estavel')

    def test_retention_supports_dry_run_and_preserves_recent_answers(self):
        ident = self.complete('2')
        with closing(database.get_connection()) as conn, conn:
            conn.execute("UPDATE checkins SET data_checkin=datetime('now','-400 days') WHERE id=?", (ident,))
            conn.execute("UPDATE whatsapp_eventos SET recebido_em=datetime('now','-400 days')")
        preview = privacy.purge()
        self.assertFalse(preview['aplicado'])
        with closing(database.get_connection()) as conn:
            self.assertEqual(conn.execute('SELECT resposta_psicologica FROM checkins WHERE id=?', (ident,)).fetchone()[0], '2')
        self.assertEqual(privacy.purge(apply=True)['checkins'], 1)
        self.assertFalse(analytics.detail(1, 'nae')['alerta_acolhimento'])
        with closing(database.get_connection()) as conn:
            self.assertEqual(conn.execute('SELECT count(*) FROM whatsapp_eventos').fetchone()[0], 0)


if __name__ == '__main__':
    unittest.main()
