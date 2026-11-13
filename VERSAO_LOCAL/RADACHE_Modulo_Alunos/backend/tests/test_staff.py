"""Um cenário HTTP de vínculos e transferência, exclusivamente em bancos temporários."""
from contextlib import closing
import json
import sqlite3
import unittest
from uuid import uuid4
import test_local_simulation as acceptance
import gestao_local as gestao
import simulation_store as store
import database


class StaffFlow(unittest.TestCase):
    http=acceptance.LocalSimulation.http
    answer=acceptance.LocalSimulation.answer
    complete=acceptance.LocalSimulation.complete
    def setUp(self):acceptance.LocalSimulation.setUp(self)
    def tearDown(self):
        gestao.SESSOES.clear();acceptance.LocalSimulation.tearDown(self)
    def api(self,path,method='GET',body=None,token=None,expected=200):
        status,result=self.http('/api/local/'+path,method,body,token)
        self.assertEqual(status,expected,result)
        return result.get('dados')
    def login(self,login,password='admin123'):
        return self.api('login','POST',{'login':login,'senha':password})['token']
    def test_multicourse_and_transfer(self):
        admin=self.token;manager=self.login('coord@radache.local')
        catalog=self.api('cursos?campusId=caceres')['itens'];ids={c['id'] for c in catalog}
        self.assertIn('ciencia-da-computacao',ids);self.assertIn('direito',ids)
        def create(name,courses,token=admin):
            return self.api('usuarios','POST',dict(nome=name,login=name,senhaInicial='Inicial#2026',perfil='atendente_academico',campusId='caceres',cursoIds=courses),token)
        ana=create('ana-multi',['ciencia-da-computacao'],manager)
        carlos=create('carlos-multi',['ciencia-da-computacao','direito'])
        a=self.login('ANA-MULTI','Inicial#2026')
        self.api('usuarios','POST',dict(nome='Duplicada',login='ANA-MULTI',senhaInicial='Inicial#2026',perfil='atendente_academico',campusId='caceres',cursoIds=['ciencia-da-computacao']),manager,409)
        self.api('usuarios/'+ana['id'],'PATCH',{'cursoIds':['ciencia-da-computacao','direito']})
        # Gestor de CC remove apenas o seu vínculo, preservando o de Direito.
        self.api('usuarios/'+ana['id'],'PATCH',{'cursoIds':[]},manager)
        self.assertEqual(self.api('usuarios/'+ana['id'])['cursoIds'],['direito'])
        found=self.api('funcionarios?campusId=caceres&busca=ana',token=manager)['itens']
        self.assertEqual(found[0]['id'],ana['id'])
        self.api('usuarios/'+ana['id'],'PATCH',{'cursoIds':['ciencia-da-computacao']},manager)
        self.assertEqual(set(self.api('usuarios/'+ana['id'])['cursoIds']),{'direito','ciencia-da-computacao'})
        self.assertIn(ana['id'],[u['id'] for u in self.api('usuarios',token=manager)['itens']])
        self.api('usuarios/'+ana['id'],'PATCH',{'cursoIds':['direito']},manager,403)
        self.api('usuarios/'+ana['id'],'PATCH',{'campusId':'cuiaba'},admin,409)
        aid=store.save(dict(nome='TESTE Multicurso',matricula='MULTI-001',curso='Ciência da Computação',nota_media=8,frequencia=90))
        academic_before=store.student(aid);self.complete(aid)
        ticket=next(t for t in self.api('atendimentos')['itens'] if t['alunoId']==str(-aid))
        path='atendimentos/'+ticket['id']
        self.api(path+'/responsavel','POST',dict(idAcao=uuid4().hex,uid=ana['id'],texto='Atribuição inicial'),manager)
        a=self.login('ana-multi','Inicial#2026')
        self.api(path,token=a)
        self.api('usuarios/'+ana['id'],'PATCH',{'cursoIds':[]},manager,409)
        self.assertIn('ciencia-da-computacao',self.api('usuarios/'+ana['id'])['cursoIds'])
        origin=self.login('diretor-caceres@radache.local');destination=self.login('diretor-cuiaba@radache.local')
        payload=dict(usuarioId=ana['id'],destino='cuiaba',cursoIds=['ciencia-da-computacao'],motivo='Mudança administrativa',redistribuicoes={ticket['id']:carlos['id']})
        self.api('transferencias','POST',payload,manager,403)
        self.api('transferencias','POST',{**payload,'redistribuicoes':{}},origin,409)
        self.assertEqual(self.api('usuarios/'+ana['id'])['campusId'],'caceres')
        request=self.api('transferencias','POST',payload,origin)
        self.assertEqual(request['status'],'pendente');self.api(path,token=a)
        self.api('transferencias/'+request['id']+'/confirmar','POST',{},manager,403)
        result=self.api('transferencias/'+request['id']+'/confirmar','POST',{},destination)
        self.assertEqual(result['status'],'concluida')
        self.api('sessao',token=a,expected=401)
        a=self.login('ana-multi','Inicial#2026')
        self.api(path,token=a,expected=404)
        self.assertEqual(self.api(path)['responsavel']['uid'],carlos['id'])
        user=self.api('usuarios/'+ana['id']);self.assertEqual(user['campusId'],'cuiaba')
        self.assertEqual(user['cursoIds'],['ciencia-da-computacao'])
        history=self.api('usuarios/'+ana['id']+'/historico')
        self.assertTrue(any(r['campus_id']=='caceres' and r['fim'] for r in history['vinculos']))
        self.assertEqual({r['campus_id'] for r in history['vinculos'] if not r['fim']},{'cuiaba'})
        self.assertEqual(store.student(aid),academic_before)
        self.assertTrue(any((e.get('responsavelAnterior') or {}).get('uid')==ana['id'] for e in self.api(path+'/historico')['itens']))
        with closing(database.get_connection()) as conn:
            with self.assertRaises(sqlite3.IntegrityError),conn:
                conn.execute('INSERT INTO atendentes_vinculos(usuario_id,campus_id,curso_id,inicio,autor_id) VALUES (?,?,?,?,?)',(ana['id'],'caceres','direito','2026-11-09','teste'))
        gestao.iniciar()
        self.assertEqual(self.api('usuarios/'+ana['id'])['campusId'],'cuiaba')
        self.assertEqual(self.api(path)['responsavel']['uid'],carlos['id'])
        print('OK: login/senha, vínculo multicurso, reutilização de funcionário, escopo, transferência com duas direções, redistribuição, histórico e persistência.')


if __name__=='__main__':unittest.main()
