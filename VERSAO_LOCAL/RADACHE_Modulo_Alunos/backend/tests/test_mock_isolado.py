import json
import os
from contextlib import closing
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from http.server import ThreadingHTTPServer

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app,auth,database,gestao_local,mock_alunos
import simulation_store as store


class MockIsoladoTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory()
        cls.old_db=database.DB_PATH; cls.old_mock=(store.ACADEMIC,store.OPERATIONAL); cls.old_auth=app.auth; cls.env=os.environ.get('RADACHE_ENV')
        os.environ['RADACHE_ENV']='development'
        database.DB_PATH=Path(cls.temp.name)/'original.db'; store.ACADEMIC=Path(cls.temp.name)/'mock.db'; store.OPERATIONAL=Path(cls.temp.name)/'operacional.db'; store.init()
        database.init_db(); gestao_local.iniciar()
        app.auth=auth.SessionManager({'coord':{'role':'coordenacao',**auth.gerar_hash_senha('teste12345')}})
        cls.server=ThreadingHTTPServer(('127.0.0.1',0),app.RadacheRequestHandler)
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True); cls.thread.start()
        cls.base=f'http://127.0.0.1:{cls.server.server_port}'
        cls.token=cls.call('/api/local/login','POST',{'email':'admin@radache.local','senha':'admin123'},token='')[1]['dados']['token']

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown(); cls.server.server_close(); cls.thread.join()
        database.DB_PATH=cls.old_db; store.ACADEMIC,store.OPERATIONAL=cls.old_mock; app.auth=cls.old_auth
        if cls.env is None: os.environ.pop('RADACHE_ENV',None)
        else: os.environ['RADACHE_ENV']=cls.env
        cls.temp.cleanup()

    @classmethod
    def call(cls,path,method='GET',body=None,token=None):
        req=Request(cls.base+path,method=method,headers={'Authorization':'Bearer '+(getattr(cls,'token','') if token is None else token),
                    'Content-Type':'application/json'},data=json.dumps(body).encode() if body is not None else None)
        try:
            with urlopen(req) as r: return r.status,json.load(r)
        except HTTPError as e:
            with e: return e.code,json.load(e)

    def test_01_create_deactivate_isolated_and_admin_update_allowed(self):
        before=database.DB_PATH.read_bytes()
        body={'nome':'TESTE ALFA','matricula':'TESTE-001','curso':'Curso fictício'}
        status,result=self.call('/api/mock-alunos','POST',body); self.assertEqual(status,201)
        ident=result['id']
        for method in ['PUT','PATCH']:
            self.assertEqual(self.call('/api/mock-alunos/'+str(ident),method,body)[0],200)
        with closing(store.connect(store.ACADEMIC,True)) as conn:
            import sqlite3
            with self.assertRaises(sqlite3.OperationalError): conn.execute("UPDATE alunos SET nome='TESTE OUTRO'")
        self.assertEqual(self.call('/api/mock-alunos/'+str(ident),'DELETE')[0],200)
        self.assertEqual(database.DB_PATH.read_bytes(),before)

    def test_02_legacy_and_alias_writes_denied(self):
        for path,method in [('/api/alunos','POST'),('/api/alunos/1','PUT'),('/api/alunos/1','PATCH'),('/api/alunos/1','DELETE')]:
            self.assertEqual(self.call(path,method,{})[0],405)
        token=self.call('/api/local/login','POST',{'email':'admin@radache.local','senha':'admin123'},token='')[1]['dados']['token']
        for prefix in ['/api/local/','/api/v1/']:
            self.assertEqual(self.call(prefix+'alunos/1','PATCH',{},token)[0],405)
            self.assertEqual(self.call(prefix+'alunos','POST',{},token)[0],405)

    def test_03_auth_production_and_fictitious_validation(self):
        self.assertEqual(self.call('/api/mock-alunos',token='')[0],401)
        self.assertEqual(self.call('/api/mock-alunos','POST',{'nome':'TESTE','matricula':'123','curso':'Curso','email':'real@example.com'})[0],400)
        os.environ['RADACHE_ENV']='production'
        try:
            for method in ['GET','POST','DELETE']:
                self.assertEqual(self.call('/api/mock-alunos',method,{} if method=='POST' else None)[0],403)
        finally: os.environ['RADACHE_ENV']='development'

    def test_04_simulation_rejects_deactivated_student_and_preserves_session(self):
        status,result=self.call('/api/mock-alunos','POST',{'nome':'TESTE Sessão','matricula':'TESTE-SESSAO','curso':'Teste'})
        self.assertEqual(status,201)
        ident=result['id']
        self.assertEqual(self.call(f'/simulation-api/alunos/{ident}/conversa')[0],200)
        self.assertEqual(self.call('/api/mock-alunos/'+str(ident),'DELETE')[0],200)
        self.assertEqual(self.call(f'/simulation-api/alunos/{ident}/conversa')[0],400)
        self.assertEqual(len(next(a for a in store.projected() if a['id']==-ident)['historico_checkins']),1)


if __name__=='__main__': unittest.main(verbosity=2)

