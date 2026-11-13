"""RBAC, isolamento por câmpus e proteção contra consultas por diferenças."""
from contextlib import closing
from collections import Counter
import json
import unittest
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from uuid import uuid4
import test_local_simulation as acceptance
import database,gestao_local as gestao,simulation_store as store,institutional,rbac


class InstitutionalTests(unittest.TestCase):
    http=acceptance.LocalSimulation.http
    answer=acceptance.LocalSimulation.answer
    complete=acceptance.LocalSimulation.complete

    def setUp(self):
        acceptance.LocalSimulation.setUp(self)
        with closing(database.get_connection()) as c,c:c.execute('DELETE FROM alunos')
        self.analyst=self.login('analista');self.admin=self.login('admin')
        self.ids={}

    def tearDown(self):
        gestao.SESSOES.clear();acceptance.LocalSimulation.tearDown(self)

    def login(self,user):
        code,result=self.http('/api/local/login','POST',dict(email=user+'@radache.local',senha='admin123'),token='')
        self.assertEqual(code,200,result);return result['dados']['token']

    def seed(self,campus='caceres',high=20,low=20,course='Ciência da Computação',semester=1):
        ids=[]
        for n in range(high+low):
            aid=store.save(dict(nome=f'PRIVADO {campus} {uuid4().hex[:8]}',matricula=uuid4().hex[:18],curso=course,campus=rbac.CAMPI[campus],periodo=semester,nota_media=0 if n<high else 10,frequencia=0 if n<high else 100))
            session=store.session(aid)
            for text in ['1','4' if n<high else '1','1' if n<high else '5']:
                store.session(aid,dict(acao='responder',texto=text,sessao_id=session['sessao_id'],id_cliente=str(uuid4())))
            with closing(store.connect(store.ACADEMIC)) as c,c:c.execute("UPDATE alunos SET data_cadastro='2026-01-01' WHERE id=?",(aid,))
            with closing(store.connect(store.OPERATIONAL)) as c,c:
                row=c.execute('SELECT dados FROM avaliacoes_sim WHERE aluno_id=?',(aid,)).fetchone();e=json.loads(row[0]);e['data_avaliacao']='2026-10-01T12:00:00+00:00'
                c.execute('UPDATE avaliacoes_sim SET dados=? WHERE aluno_id=?',(json.dumps(e),aid))
                row=c.execute('SELECT estado FROM sessoes WHERE aluno_id=?',(aid,)).fetchone();s=json.loads(row[0]);s['timestamp']='2026-10-01T12:00:00+00:00'
                c.execute('UPDATE sessoes SET estado=? WHERE aluno_id=?',(json.dumps(s),aid))
            ids.append(aid)
        self.ids[campus]=ids
        return ids

    def report(self,query=''):
        code,result=self.http('/api/institucional/resumo'+('?' + query if query else ''),token=self.analyst)
        self.assertEqual(code,200,result);return result['dados']

    def test_twenty_active_demo_accounts_and_secure_hashes(self):
        with closing(database.get_connection()) as c:
            rows=[dict(r) for r in c.execute('SELECT * FROM gestao_usuarios')]
        active=[r for r in rows if json.loads(r['dados'])['ativo']]
        self.assertEqual(Counter(json.loads(r['dados'])['perfil'] for r in active),dict(admin_tecnico=1,analista_institucional=1,diretor_campus=3,gestor_curso=15))
        for r in active:
            self.assertEqual(len(r['password_hash']),64);self.assertGreaterEqual(len(r['salt']),32)
            self.assertNotIn('admin123',r['dados'])
        self.assertEqual(len({r['salt'] for r in active}),20)
        gestao.iniciar()
        with closing(database.get_connection()) as c:self.assertEqual(c.execute('SELECT COUNT(*) FROM gestao_usuarios').fetchone()[0],len(rows))

    def test_institutional_endpoints_never_return_student_records(self):
        for campus in rbac.CAMPI:self.seed(campus)
        for path in ('resumo','campus','cursos/riscos','evolucao'):
            code,result=self.http('/api/institucional/'+path,token=self.analyst)
            self.assertEqual(code,200,result)
            serialized=json.dumps(result,ensure_ascii=False)
            for forbidden in ('PRIVADO','matricula','alunoId','resposta_financeira','responsavel','comentarios','historico_avaliacoes'):
                self.assertNotIn(forbidden,serialized)
        result=self.report()
        self.assertFalse(result['resumo']['protegido'])
        self.assertEqual(result['resumo']['valores']['cadastrados'],120)
        self.assertEqual(result['resumo']['valores']['alto_pct'],50)
        self.assertEqual([c['valores']['cadastrados'] for c in result['campus']],[40,40,40])

    def test_analyst_cannot_read_or_modify_operational_data(self):
        paths=['/api/alunos','/api/alunos/1','/api/analytics','/api/analytics/students/1','/api/mock-alunos',
               '/simulation-api/alunos','/simulation-api/academicos/1','/simulation-api/alunos/1/conversa',
               '/api/local/usuarios','/api/local/alunos','/api/local/atendimentos/exemplo-1','/api/local/responsaveis','/api/local/cursos']
        for path in paths:
            self.assertEqual(self.http(path,token=self.analyst)[0],403,path)
            self.assertEqual(self.http(path,token='')[0],401,path)
        for method in ('POST','PATCH','PUT','DELETE'):
            self.assertEqual(self.http('/api/mock-alunos/1',method,{},self.analyst)[0],403)
            self.assertEqual(self.http('/api/institucional/resumo',method,{},self.analyst)[0],405)

    def test_cookie_and_alternate_login_do_not_bypass_analyst_role(self):
        request=Request(self.base+'/api/alunos',headers={'Cookie':'radache_session='+self.analyst,'Authorization':'Bearer '+self.admin})
        with self.assertRaises(HTTPError) as e:urlopen(request)
        self.assertEqual(e.exception.code,403)
        code,result=self.http('/api/login','POST',dict(usuario='analista',senha='admin123',perfil='admin_tecnico'),token='')
        self.assertEqual(code,200,result)
        self.assertEqual(result['usuario']['role'],rbac.ANALYST)
        self.assertEqual(self.http('/api/alunos',token=result['token'])[0],403)
        code,result=self.http('/api/login','POST',dict(usuario='coord',senha='admin123'),token='')
        self.assertEqual(code,200,result)
        self.assertEqual(self.http('/api/mock-alunos',token=result['token'])[0],403)

    def test_director_and_course_manager_are_scoped_on_every_interface(self):
        for campus in rbac.CAMPI:self.seed(campus,high=5,low=5)
        director=self.login('diretor-caceres');manager=self.login('coord')
        for token in (director,manager):
            code,result=self.http('/api/local/alunos',token=token)
            self.assertEqual(code,200,result)
            self.assertTrue(all(s['campus']==rbac.CAMPI['caceres'] for s in result['dados']['itens']))
            foreign=-self.ids['cuiaba'][0]
            self.assertIn(self.http('/api/local/alunos/'+str(foreign),token=token)[0],(403,404))
            self.assertEqual(self.http('/api/analytics/students/'+str(foreign),token=token)[0],404)
            self.assertEqual(self.http('/api/alunos/'+str(foreign),token=token)[0],404)
            self.assertEqual(self.http('/api/dashboard',token=token)[1]['dados']['total_alunos'],10)
            self.assertEqual(self.http('/simulation-api/alunos/'+str(-foreign)+'/conversa',token=token)[0],404)
            code, users = self.http('/api/local/usuarios', token=token)
            self.assertEqual(code, 200, users)
            self.assertTrue(all(u['perfil']=='atendente_academico' and u['campusId']=='caceres' for u in users['dados']['itens']))
            self.assertEqual(self.http('/api/institucional/resumo',token=token)[0],403)
        self.assertEqual(self.http('/api/local/usuarios','POST',dict(nome='X',email='x@radache.local',perfil='analista_institucional'),manager)[0],403)

    def test_small_groups_and_complementary_totals_are_suppressed_before_filters(self):
        for campus in rbac.CAMPI:self.seed(campus)
        self.seed('caceres',high=1,low=0,course='Pedagogia')
        data=self.report()
        self.assertTrue(data['resumo']['protegido']);self.assertIsNone(data['resumo']['valores'])
        self.assertTrue(data['campus'][0]['protegido'])
        self.assertFalse(data['campus'][1]['protegido'])
        for risk in ('alto','baixo','sem_avaliacao'):
            small=self.report('campus=caceres&curso=pedagogia&risco='+risk)
            self.assertIsNone(small['resumo']['valores'])
        safe=self.report('curso=ciencia-da-computacao')
        self.assertEqual(safe['resumo']['valores']['cadastrados'],120)
        self.assertIsNone(data['resumo']['valores'])  # Sem total exato, não existe a subtração 121 - 120.

    def test_rounding_and_percentages_use_the_same_fixed_cells(self):
        self.seed(high=22,low=21)
        all_values=self.report()['resumo']['valores']
        high=self.report('risco=alto')['resumo']['valores'];low=self.report('risco=baixo')['resumo']['valores']
        self.assertEqual(all_values['cadastrados'],40)
        self.assertEqual(high['cadastrados']+low['cadastrados'],all_values['cadastrados'])
        self.assertEqual(all_values['alto_pct'],50)
        self.assertEqual(high['alto'],20)
        self.assertEqual(self.report()['resumo']['valores'],all_values)

    def test_restricts_differencing_filters_and_audits_reads_and_denials(self):
        for query in ('busca=PRIVADO','aluno_id=1','inicio=2026-10-02','periodo=2026-2&inicio=2026-10','campus=caceres&campus=cuiaba','curso=PRIVADO'):
            self.assertEqual(self.http('/api/institucional/resumo?'+query,token=self.analyst)[0],400,query)
        self.report();self.http('/api/alunos',token=self.analyst)
        with closing(database.get_connection()) as c:
            entries=c.execute('SELECT usuario_id,resultado FROM institucional_auditoria').fetchall()
        self.assertTrue(any(r[0]=='analista' and r[1]==200 for r in entries))
        self.assertTrue(any(r[0]=='analista' and r[1]==403 for r in entries))

    def test_updates_from_local_questionnaires_without_duplicating_students(self):
        ids=self.seed()
        self.assertEqual(self.report()['resumo']['valores']['alto_pct'],50)
        for aid in ids[:5]:
            store.save({'nota_media':10,'frequencia':100},aid)
            store.session(aid,dict(acao='mes',id_cliente=str(uuid4())))
            self.complete(aid,'1','5')
        data=self.report()
        self.assertEqual(data['resumo']['valores']['alto_pct'],37.5)
        self.assertEqual(data['resumo']['valores']['diminuiu'],5)
        self.assertEqual(data['resumo']['valores']['cadastrados'],40)
        with closing(store.connect(store.ACADEMIC,True)) as c:self.assertEqual(c.execute('SELECT COUNT(*) FROM alunos').fetchone()[0],40)


if __name__=='__main__':unittest.main(verbosity=2)
