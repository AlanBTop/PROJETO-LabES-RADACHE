"""Um cenário HTTP integrado, com SQLite temporário e sem tocar dados do projeto."""
import json
from contextlib import closing
from uuid import uuid4
import unittest
import test_local_simulation as acceptance
import gestao_local as gestao
import simulation_store as store
import database


class AttendanceFlow(unittest.TestCase):
    http = acceptance.LocalSimulation.http
    answer = acceptance.LocalSimulation.answer
    complete = acceptance.LocalSimulation.complete

    def setUp(self):
        acceptance.LocalSimulation.setUp(self)

    def tearDown(self):
        gestao.SESSOES.clear()
        acceptance.LocalSimulation.tearDown(self)

    def api(self, path, method='GET', body=None, token=None, expected=200):
        status, result = self.http('/api/local/'+path, method, body, token)
        self.assertEqual(status, expected, result)
        return result.get('dados')

    def login(self, name):
        return self.api('login','POST',{'email':name+'@radache.local','senha':'admin123'})['token']

    def test_complete_flow_and_access_boundaries(self):
        manager=self.login('coord')
        def create(name, **extra):
            body=dict(nome=name,email=name+'@radache.local',senhaInicial='admin123',perfil='atendente_academico',campusId='caceres',cursoIds=['ciencia-da-computacao'])
            return self.api('usuarios','POST',{**body,**extra},manager)
        ana=create('ana');carlos=create('carlos')
        a=self.login('ana');c=self.login('carlos')
        create_body=dict(nome='Indevido',email='indevido@radache.local',perfil='gestor_curso',campusId='caceres',cursoIds=['ciencia-da-computacao'])
        self.api('usuarios','POST',create_body,manager,403)
        self.api('usuarios','POST',{**create_body,'perfil':'atendente_academico','campusId':'cuiaba'},manager,403)
        outsider=self.api('usuarios','POST',dict(nome='Outro curso',email='outro@radache.local',senhaInicial='admin123',perfil='atendente_academico',campusId='cuiaba',cursoIds=['ciencia-da-computacao']))
        aid=store.save(dict(nome='TESTE Atendimento',matricula='ATEND-001',curso='Ciência da Computação',nota_media=8,frequencia=90))
        self.complete(aid)
        cases=self.api('atendimentos',token=manager)['itens']
        ticket=next(t for t in cases if t['alunoId']==str(-aid));path='atendimentos/'+ticket['id']
        self.api('atendimentos',token=manager)
        self.assertEqual(sum(t['alunoId']==str(-aid) for t in self.api('atendimentos',token=manager)['itens']),1)
        academic_before=store.student(aid)
        risk_before=ticket['riscoAcademico']
        self.api(path,token=a,expected=404)
        self.api('alunos/'+str(-aid),token=a,expected=403)
        def action(kind, token=manager, expected=200, **values):
            return self.api(path+'/'+kind,'POST',dict(idAcao=str(uuid4()),texto='Providência de teste',**values),token,expected)
        action('responsavel',uid=outsider['id'],expected=403)
        action('responsavel',uid=ana['id'])
        self.assertEqual(self.api(path,token=a)['responsavel']['uid'],ana['id'])
        self.assertEqual(self.api('indicadores',token=a)['totalAtribuidos'],1)
        self.api(path,token=c,expected=404)
        action('comentarios',token=a)
        action('responsavel',token=a,uid=carlos['id'],expected=403)
        for url in ['/api/alunos','/api/analytics/overview','/api/institucional/resumo','/api/mock-alunos','/simulation-api/alunos','/mock-api/alunos']:
            self.assertEqual(self.http(url,token=a)[0],403,url)
        self.api('usuarios',token=a,expected=403)
        self.api('alunos/'+str(-aid),'PATCH',{'nome':'Indevido'},a,405)
        history=self.api(path+'/historico',token=manager)['itens']
        action('responsavel',uid=carlos['id'])
        self.api(path,token=a,expected=404)
        self.api(path+'/historico',token=a,expected=404)
        self.api('alunos/'+str(-aid),token=a,expected=403)
        self.assertFalse(self.api('atendimentos',token=a)['itens'])
        self.assertEqual(self.api('indicadores',token=a)['totalAtribuidos'],0)
        after=self.api(path+'/historico',token=c)['itens']
        self.assertEqual(after[:-1],history)
        self.assertEqual(after[-1]['responsavelAnterior']['uid'],ana['id'])
        self.assertEqual(after[-1]['novoResponsavel']['uid'],carlos['id'])
        self.assertEqual(after[-1]['autor']['uid'],'coord')
        action('status',token=c,status='aguardando_aluno')
        resolved=action('status',token=c,status='resolvido')
        self.assertEqual(resolved['riscoAcademico'],risk_before)
        self.assertEqual(store.student(aid),academic_before)
        self.api('alunos/'+str(-aid),token=c,expected=403)
        self.api(path+'/historico',token=c)
        action('status',token=c,status='reaberto',expected=403)
        action('status',status='reaberto')
        self.assertEqual(self.api('indicadores',token=manager)['totalReabertos'],1)
        self.api('PATCH-unused',expected=404)
        self.api('usuarios/'+carlos['id'],'PATCH',{'nome':'Carlos atualizado'},manager)
        self.api('sessao',token=c,expected=401)
        c=self.login('carlos')
        # Abrir novamente todas as conexões e invalidar sessões simula reinício.
        gestao.SESSOES.clear();store.init();database.init_db();gestao.iniciar()
        manager=self.login('coord');c=self.login('carlos')
        self.assertEqual(self.api(path,token=c)['status'],'reaberto')
        self.assertEqual(self.api(path,token=c)['responsavel']['uid'],carlos['id'])
        action('responsavel',token=manager,uid=None)
        self.api(path,token=c,expected=404)
        self.api('usuarios/'+carlos['id'],'PATCH',{'ativo':False},manager)
        self.api('sessao',token=c,expected=401)
        print('OK: cadastro, atribuição, isolamento, transferência, histórico, resolução, reabertura, indicadores e persistência.')


if __name__=='__main__':
    unittest.main()
