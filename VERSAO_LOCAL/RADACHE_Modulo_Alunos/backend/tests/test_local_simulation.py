"""Aceitação do fluxo integrado com arquivos SQLite temporários e HTTP real."""
from contextlib import closing
from http.server import ThreadingHTTPServer
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
import unittest
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from uuid import uuid4

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import simulation_store as store
import database
import app
from auth import SessionManager,gerar_hash_senha


class LocalSimulation(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.old=(store.ACADEMIC,store.OPERATIONAL,database.DB_PATH,app.auth)
        store.ACADEMIC=Path(self.temp.name)/'mock_sigaa.db'
        store.OPERATIONAL=Path(self.temp.name)/'radache.db'
        database.DB_PATH=Path(self.temp.name)/'legacy.db'
        store.init();database.init_db()
        import gestao_local
        gestao_local.iniciar()
        app.auth=SessionManager({'coord':{'role':'coordenacao',**gerar_hash_senha('admin123')},'nae':{'role':'nae',**gerar_hash_senha('admin123')}})
        self.server=ThreadingHTTPServer(('127.0.0.1',0),app.RadacheRequestHandler)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.base='http://127.0.0.1:'+str(self.server.server_port)
        self.token=self.http('/api/login','POST',{'usuario':'admin@radache.local','senha':'admin123'})[1]['token']

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join()
        store.ACADEMIC,store.OPERATIONAL,database.DB_PATH,app.auth=self.old
        self.temp.cleanup()

    def http(self,path,method='GET',body=None,token=None):
        headers={'Content-Type':'application/json','Authorization':'Bearer '+(token if token is not None else getattr(self,'token',''))}
        req=Request(self.base+path,data=json.dumps(body).encode() if body is not None else None,headers=headers,method=method)
        try:
            with urlopen(req,timeout=4) as r:return r.status,json.load(r)
        except HTTPError as e:return e.code,json.load(e)

    def create(self,name='TESTE Alfa',matricula='20260001',**extra):
        code,data=self.http('/api/mock-alunos','POST',dict(nome=name,matricula=matricula,curso='Computação',periodo=4,nota_media=8,frequencia=90,**extra))
        self.assertEqual(code,201,data);return data['id']

    def answer(self,aid,text,sid=None,ident=None):
        sid=sid or store.session(aid)['sessao_id']
        return self.http(f'/simulation-api/alunos/{aid}/conversa','POST',dict(acao='responder',texto=text,sessao_id=sid,id_cliente=ident or str(uuid4())))

    def complete(self,aid,f='4',p='1'):
        for text in ('1',f,p):
            code,data=self.answer(aid,text);self.assertEqual(code,200,data)
        return data['dados']

    def test_create_duplicate_edit_and_shared_identity(self):
        aid=self.create()
        self.assertEqual(self.http('/api/mock-alunos','POST',dict(nome='Outro',matricula='20260001',curso='Outro'))[0],409)
        self.assertEqual(self.http('/api/mock-alunos/'+str(aid),'PUT',{'nome':'TESTE Editado','periodo':5})[0],200)
        self.assertEqual(self.http('/simulation-api/alunos')[1]['dados'][0]['nome'],'TESTE Editado')
        self.assertEqual(self.http('/api/alunos/'+str(-aid))[1]['dados']['periodo'],5)

    def test_migration_preserves_previous_local_sandbox_once(self):
        source=Path(self.temp.name)/'old.db'
        with closing(sqlite3.connect(source)) as c,c:
            c.execute('CREATE TABLE alunos_mock(id,nome,matricula,curso,criado_em)')
            c.execute("INSERT INTO alunos_mock VALUES (7,'TESTE Anterior','ANTERIOR','Teste','2026-01-01')")
        before=source.read_bytes()
        store.import_legacy(source);store.import_legacy(source)
        self.assertEqual(len(store.students()),1)
        self.assertEqual(store.student(7)['matricula'],'ANTERIOR')
        self.assertEqual(source.read_bytes(),before)

    def test_responses_panel_metrics_and_academic_unchanged(self):
        aid=self.create();before=store.student(aid)
        result=self.complete(aid)
        self.assertEqual(result['estado']['etapa'],'concluido')
        detail=self.http('/api/alunos/'+str(-aid))[1]['dados']
        self.assertEqual(detail['avaliacao_atual']['indice_risco'],57.5)
        self.assertEqual(detail['avaliacao_atual']['classificacao_risco'],'moderado')
        self.assertEqual(len(detail['historico_checkins']),1)
        self.assertEqual(len(detail['mensagens_simuladas']),7)
        self.assertEqual(store.student(aid),before)
        self.assertGreaterEqual(self.http('/api/dashboard')[1]['dados']['alunos_moderados'],1)

    def test_two_students_separate_histories(self):
        a=self.create();b=self.create('TESTE Beta','20260002')
        self.complete(a);self.complete(b,'1','5')
        data={r['id']:r for r in store.projected()}
        self.assertEqual(data[-a]['indice_risco'],57.5)
        self.assertEqual(data[-b]['indice_risco'],7.5)
        self.assertTrue(all(m['aluno_id']==a for m in data[-a]['mensagens_simuladas']))

    def test_multiple_sessions_preserve_history(self):
        aid=self.create();first=self.complete(aid)
        second=store.session(aid,{'acao':'mes','id_cliente':str(uuid4())})
        self.assertNotEqual(first['sessao_id'],second['sessao_id'])
        self.complete(aid,'1','5')
        self.assertEqual(len(store.projected()[0]['historico_avaliacoes']),2)

    def test_restart_preserves_files(self):
        aid=self.create();first=self.complete(aid)
        # Um processo novo abre os arquivos, sem memória das sessões anteriores.
        import subprocess
        env={**os.environ,'RADACHE_MOCK_DB':str(store.ACADEMIC),'RADACHE_SIM_DB':str(store.OPERATIONAL)}
        script='import simulation_store as s,json;s.init();print(json.dumps(s.session('+str(aid)+')))'
        proc=subprocess.run([sys.executable,'-c',script],cwd=Path(store.__file__).parent,env=env,capture_output=True,text=True,check=True)
        self.assertEqual(json.loads(proc.stdout),first)

    def test_deactivation_missing_and_invalid_session(self):
        aid=self.create();self.complete(aid)
        self.assertEqual(self.answer(aid,'1','invalid')[0],400)
        self.assertEqual(self.http('/api/mock-alunos/'+str(aid),'DELETE')[0],200)
        self.assertEqual(self.http(f'/simulation-api/alunos/{aid}/conversa')[0],400)
        self.assertEqual(self.http('/simulation-api/alunos/99999/conversa')[0],404)
        self.assertEqual(len(store.projected()[0]['historico_avaliacoes']),1)

    def test_admin_auth_and_operational_write_protection(self):
        aid=self.create()
        token=self.http('/api/login','POST',{'usuario':'nae','senha':'admin123'})[1]['token']
        self.assertEqual(self.http('/api/mock-alunos/'+str(aid),'PUT',{'nome':'Mudado'},token)[0],403)
        self.assertEqual(self.http('/api/mock-alunos','GET',token='')[0],401)
        self.assertEqual(self.http('/api/alunos/'+str(-aid),'PUT',{'nome':'Mudado'})[0],405)
        with closing(store.connect(store.ACADEMIC,True)) as conn:
            with self.assertRaises(sqlite3.OperationalError):conn.execute("UPDATE alunos SET nome='Mudado'")

    def test_retry_is_idempotent(self):
        aid=self.create();sid=store.session(aid)['sessao_id'];ident=str(uuid4())
        first=self.answer(aid,'1',sid,ident)
        self.assertEqual(self.answer(aid,'1',sid,ident),first)
        self.assertEqual(len(store.session(aid)['mensagens']),3)
        self.assertEqual(self.answer(aid,'2',sid,ident)[0],400)

    def test_revocation_erases_sensitive_persistence(self):
        aid=self.create();self.complete(aid);self.answer(aid,'REVOGAR')
        data=store.projected()[0]
        self.assertEqual(data['historico_avaliacoes'],[])
        self.assertIsNone(data['historico_checkins'][0]['financeira'])
        self.assertTrue(any(m['conteudo']=='Resposta removida após revogação.' for m in data['mensagens_simuladas']))

    def test_missing_academic_values_no_invented_risk(self):
        aid=store.save({'nome':'TESTE Sem nota','matricula':'SEM-NOTA','curso':'Teste'})
        self.complete(aid)
        data=store.projected()[0]['avaliacao_atual']
        self.assertIsNone(data['indice_risco']);self.assertIn('limitacao',data)

    def test_invalid_response_reminder_refusal_and_expiry(self):
        aid=self.create();self.answer(aid,'9')
        self.assertEqual(store.session(aid)['estado']['etapa'],'consentimento')
        self.answer(aid,'2');self.assertEqual(store.session(aid)['estado']['etapa'],'recusado')
        self.answer(aid,'INICIAR');self.answer(aid,'1')
        r=store.session(aid,{'acao':'dias','id_cliente':str(uuid4())})
        self.assertTrue(r['estado']['lembreteEnviado'])
        r=store.session(aid,{'acao':'ano','id_cliente':str(uuid4())})
        self.assertEqual(r['estado']['etapa'],'consentimento')

    def test_offline_no_network_services(self):
        # Bloqueia toda tentativa de saída; HTTP do teste roda no próprio processo.
        from unittest.mock import patch
        with patch('socket.create_connection',side_effect=AssertionError('Rede externa proibida')):
            aid=store.save({'nome':'TESTE Offline','matricula':'OFFLINE','curso':'Teste'})
            result=store.session(aid)
            for text in ('1','1','5'):
                result=store.session(aid,dict(acao='responder',texto=text,sessao_id=result['sessao_id'],id_cliente=str(uuid4())))
            self.assertEqual(result['estado']['etapa'],'concluido')


if __name__=='__main__':unittest.main(verbosity=2)
