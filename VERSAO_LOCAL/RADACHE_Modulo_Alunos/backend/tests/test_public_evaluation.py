"""Avaliação pública: configuração fechada, perfis, CSRF e serviços externos bloqueados."""
from contextlib import redirect_stdout
import http.client
import io
import json
import os
from pathlib import Path
import secrets
import tempfile
import threading
import unittest
from unittest.mock import patch

import app
import credential_policy
import database
import gestao_local
import run_web
import security
import simulation_store as store
import whatsapp


class PublicConfiguration(unittest.TestCase):
    def test_public_boot_requires_hosts_and_four_private_distinct_passwords(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {}, clear=True):
            os.environ['RADACHE_DATA_DIR'] = directory
            with self.assertRaises(ValueError):run_web.configure()
            os.environ['RENDER_EXTERNAL_HOSTNAME'] = 'radache02-26labes.onrender.com'
            with self.assertRaises(ValueError):run_web.configure()
            for key in credential_policy.EVALUATION_ACCOUNTS.values():
                os.environ[key] = secrets.token_urlsafe(24)
            os.environ.update(WHATSAPP_ACCESS_TOKEN='TESTE-nao-enviar', RADACHE_DEMO='1')
            self.assertEqual(run_web.configure(), 10000)
            self.assertEqual(os.environ['RADACHE_DEMO'], '0')
            self.assertEqual(os.environ['RADACHE_ENV'], 'evaluation')
            self.assertEqual(os.environ['RADACHE_HOST'], '0.0.0.0')
            self.assertNotIn('WHATSAPP_ACCESS_TOKEN', os.environ)
            values = tuple(credential_policy.EVALUATION_ACCOUNTS.values())
            os.environ[values[1]] = os.environ[values[0]]
            with self.assertRaises(ValueError):run_web.configure()

    def test_host_parser_rejects_suffix_userinfo_bad_ports_and_paths(self):
        with patch.dict(os.environ, {'RADACHE_ALLOWED_HOSTS': 'radache02-26labes.onrender.com'}):
            self.assertTrue(security.allowed_public_host('radache02-26labes.onrender.com:443'))
            for bad in ('', 'localhost', 'radache02-26labes.onrender.com.evil.test',
                        'evil@radache02-26labes.onrender.com', 'radache02-26labes.onrender.com/path',
                        'radache02-26labes.onrender.com:abc', 'radache02-26labes.onrender.com '):
                self.assertFalse(security.allowed_public_host(bad), bad)


class PublicHTTP(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.passwords = {email:secrets.token_urlsafe(24) for email in credential_policy.EVALUATION_ACCOUNTS}
        env = {'RADACHE_PUBLIC_EVALUATION':'1', 'RADACHE_DEMO':'0', 'RADACHE_HTTPS':'1',
               'RADACHE_ENV':'evaluation', 'RADACHE_ALLOWED_HOSTS':'radache02-26labes.onrender.com'}
        env.update({key:self.passwords[email] for email,key in credential_policy.EVALUATION_ACCOUNTS.items()})
        self.enterContext(patch.dict(os.environ, env))
        self.enterContext(patch.object(database, 'DB_PATH', root/'legacy.db'))
        self.enterContext(patch.object(store, 'ACADEMIC', root/'academic.db'))
        self.enterContext(patch.object(store, 'OPERATIONAL', root/'operational.db'))
        self.enterContext(patch.object(security, 'LOGIN_LIMITER', security.LoginLimiter()))
        gestao_local.SESSOES.clear(); self.addCleanup(gestao_local.SESSOES.clear)
        with redirect_stdout(io.StringIO()):
            database.init_db();store.init();gestao_local.iniciar()
        self.server = run_web.EvaluationServer(('127.0.0.1', 0), app.RadacheRequestHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True);self.thread.start()
        self.addCleanup(self.close)

    def close(self):
        self.server.shutdown();self.server.server_close();self.thread.join(timeout=3)

    def http(self, path, data=None, headers=None, method=None):
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        try:
            connection.request(method or ('POST' if data is not None else 'GET'), path,
                               json.dumps(data) if data is not None else None,
                               {'Host':'radache02-26labes.onrender.com', 'Content-Type':'application/json', **(headers or {})})
            response=connection.getresponse();raw=response.read()
            body=json.loads(raw) if response.getheader('Content-Type','').startswith('application/json') else raw
            return response.status,dict(response.getheaders()),body
        finally:connection.close()

    def login(self, email='admin@radache.local', change=True):
        status,headers,body=self.http('/api/local/login', {'email':email,'senha':self.passwords[email]})
        self.assertEqual(status,200)
        self.assertIn('Secure',headers['Set-Cookie'])
        self.assertTrue(body['dados']['usuario']['trocaSenhaObrigatoria'])
        token=body['dados']['token']
        if not change:return token
        password=secrets.token_urlsafe(24)
        status,_,_=self.http('/api/local/senha', {'senhaAtual':self.passwords[email],'novaSenha':password},
                             {'Authorization':'Bearer '+token})
        self.assertEqual(status,200)
        self.assertEqual(self.http('/api/local/sessao',headers={'Authorization':'Bearer '+token})[0],401)
        status,_,body=self.http('/api/local/login',{'email':email,'senha':password})
        self.assertEqual(status,200)
        self.assertFalse(body['dados']['usuario']['trocaSenhaObrigatoria'])
        return body['dados']['token']

    def test_no_anonymous_operational_access_including_message_mock(self):
        for path in ('/api/alunos','/api/mock-alunos','/simulation-api/alunos'):
            self.assertEqual(self.http(path)[0],401,path)
        self.assertEqual(self.http('/mock-api/mensagens',{})[0],401)
        self.assertEqual(self.http('/api/login',{'usuario':'admin@radache.local','senha':'admin123'})[0],401)

    def test_demo_session_can_visit_pages_but_cannot_modify_private_accounts(self):
        status, headers, body = self.http('/api/demo/login', {})
        self.assertEqual(status, 200, body)
        self.assertIn('HttpOnly', headers['Set-Cookie'])
        self.assertTrue(body['dados']['usuario']['demonstracaoPublica'])
        token = body['dados']['token']
        auth = {'Authorization': 'Bearer ' + token}
        for path in ('/api/session', '/api/local/sessao', '/api/local/usuarios',
                     '/api/analytics', '/api/institucional/resumo', '/api/mock-alunos',
                     '/simulation-api/alunos'):
            self.assertEqual(self.http(path, headers=auth)[0], 200, path)
        for path, method in (('/api/local/usuarios', 'POST'),
                             ('/api/v1/usuarios/admin', 'PATCH'),
                             ('/api/local/transferencias', 'POST'),
                             ('/api/local/senha', 'POST')):
            self.assertEqual(self.http(path, {}, auth, method)[0], 403, path)
        with patch.dict(os.environ, {'RADACHE_PUBLIC_EVALUATION':'0'}):
            self.assertNotEqual(self.http('/api/demo/login', {})[0], 200)

    def test_initial_password_does_not_unlock_data_before_change(self):
        token=self.login(change=False)
        for path in ('/api/alunos','/api/local/usuarios'):
            self.assertEqual(self.http(path,headers={'Authorization':'Bearer '+token})[0],403)
        self.assertEqual(self.http('/mock-api/mensagens',{}, {'Authorization':'Bearer '+token})[0],403)

    def test_cookie_csrf_scope_and_private_initial_password_preserved(self):
        token=self.login()
        cookie={'Cookie':'radache_session='+token}
        self.assertEqual(self.http('/api/local/logout',{},cookie)[0],403)
        self.assertEqual(self.http('/api/local/logout',{}, {**cookie,'Origin':'https://evil.test'})[0],403)
        self.assertEqual(self.http('/api/local/alunos',headers=cookie)[0],200)
        with redirect_stdout(io.StringIO()):gestao_local.iniciar()
        self.assertEqual(self.http('/api/local/alunos',headers=cookie)[0],200)
        self.assertEqual(self.http('/api/local/logout',{}, {**cookie,'Origin':'https://radache02-26labes.onrender.com'})[0],200)

    def test_analyst_and_director_keep_their_scope(self):
        analyst={'Authorization':'Bearer '+self.login('analista@radache.local')}
        self.assertEqual(self.http('/api/institucional/resumo',headers=analyst)[0],200)
        self.assertEqual(self.http('/api/alunos',headers=analyst)[0],403)
        self.assertEqual(self.http('/mock-api/mensagens',{},analyst)[0],403)
        director={'Authorization':'Bearer '+self.login('diretor-caceres@radache.local')}
        self.assertEqual(self.http('/api/mock-alunos',{'nome':'TESTE Negado'},director)[0],403)
        self.assertEqual(self.http('/mock-api/mensagens',{},director)[0],403)
        self.assertEqual(self.http('/simulation-api/alunos',headers=director)[0],200)

    def test_health_and_config_do_not_expose_private_files(self):
        status,_,body=self.http('/healthz')
        self.assertEqual(status,200);self.assertEqual(set(body),{'servico','status'})
        config=self.http('/public-config.json')[2]
        self.assertTrue(config['publicEvaluation']);self.assertNotIn('password',json.dumps(config).lower())
        self.assertEqual(self.http('/',headers={'Host':'evil.test'})[0],403)
        self.assertEqual(self.http('/assets/../RADACHE_Modulo_Alunos/database/legacy.db')[0],403)
        self.assertEqual(self.http('/legacy.db.acessos-iniciais.json')[0],404)

    def test_real_whatsapp_is_disabled_even_with_environment_credentials(self):
        self.assertEqual(self.http('/webhooks/whatsapp')[0],404)
        self.assertEqual(self.http('/webhooks/whatsapp',{})[0],404)
        with patch.dict(os.environ,{'WHATSAPP_ACCESS_TOKEN':'TESTE','WHATSAPP_PHONE_NUMBER_ID':'TESTE','WHATSAPP_API_VERSION':'TESTE'}), patch('whatsapp.urllib.request.urlopen') as send:
            with self.assertRaises(RuntimeError):whatsapp.enviar_texto('0000000000','TESTE')
            send.assert_not_called()

