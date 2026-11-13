"""Aceitação HTTP: WhatsApp → quadro existente → ações de acompanhamento."""
from contextlib import closing
import json
import unittest
from uuid import uuid4
import test_local_simulation as acceptance
import gestao_local as gestao
import simulation_store as store
import simulation_followup as followup
import database
import analytics


class FollowupTests(unittest.TestCase):
    http=acceptance.LocalSimulation.http
    answer=acceptance.LocalSimulation.answer
    complete=acceptance.LocalSimulation.complete

    def setUp(self):
        acceptance.LocalSimulation.setUp(self)
        gestao.iniciar()
        self.gtoken=self.http('/api/local/login','POST',{'email':'admin@radache.local','senha':'admin123'})[1]['dados']['token']
        self.aid=store.save(dict(nome='TESTE Acompanhamento',matricula='ACAD-001',curso='Ciência da Computação',nota_media=8,frequencia=90))

    def tearDown(self):
        gestao.SESSOES.clear()
        acceptance.LocalSimulation.tearDown(self)

    def api(self,path,method='GET',body=None,token=None):
        return self.http('/api/local/'+path,method,body,self.gtoken if token is None else token)

    def tickets(self):
        code,data=self.api('atendimentos');self.assertEqual(code,200,data)
        return [t for t in data['dados']['itens'] if t.get('origem')=='whatsapp_simulado']

    def action(self,ticket,path,**values):
        code,result=self.api('atendimentos/'+ticket['id']+'/'+path,'POST',{'idAcao':str(uuid4()),**values})
        self.assertEqual(code,200,result)
        return result['dados']

    def attendant(self):
        code, result = self.api('usuarios', 'POST', dict(nome='Atendente teste', login='atendente-teste', senhaInicial='Inicial#2026', perfil='atendente_academico', campusId='caceres', cursoIds=['ciencia-da-computacao']))
        self.assertEqual(code, 200, result)
        return result['dados']['id']

    def test_completion_creates_open_ticket_with_correct_identity_and_answers(self):
        before=store.student(self.aid)
        self.answer(self.aid,'1');self.answer(self.aid,'4')
        self.assertEqual(self.tickets(),[])
        self.answer(self.aid,'1')
        ticket=self.tickets()[0]
        self.assertEqual(ticket['status'],'aberto')
        self.assertEqual(ticket['alunoId'],str(-self.aid))
        self.assertEqual(ticket['alunoNome'],'TESTE Acompanhamento')
        self.assertEqual(ticket['questionarios'][0]['indice_risco'],57.5)
        self.assertEqual(store.student(self.aid),before)
        self.assertEqual(self.api('alunos/'+str(-self.aid))[0],200)

    def test_repeated_queries_and_sync_do_not_duplicate_tickets_or_events(self):
        self.complete(self.aid)
        for _ in range(3):followup.sync();self.tickets()
        ticket=self.tickets()[0]
        self.assertEqual(len(self.tickets()),1)
        self.assertEqual(len(self.api('atendimentos/'+ticket['id']+'/historico')[1]['dados']['itens']),1)

    def test_parallel_board_queries_recover_pending_checkin_without_duplicates(self):
        from concurrent.futures import ThreadPoolExecutor
        session=store.session(self.aid)
        for text in ['1','4','1']:
            store.session(self.aid,{'acao':'responder','texto':text,'sessao_id':session['sessao_id'],'id_cliente':str(uuid4())})
        paths=['atendimentos?status=aberto','atendimentos?status=resolvido','indicadores']*4
        with ThreadPoolExecutor(max_workers=6) as pool:
            results=list(pool.map(self.api,paths))
        self.assertTrue(all(code==200 for code,_ in results),results)
        self.assertEqual(len(self.tickets()),1)

    def test_multiple_sessions_append_to_active_ticket_and_return_from_waiting(self):
        self.complete(self.aid);ticket=self.tickets()[0]
        self.action(ticket,'responsavel',uid=self.attendant(),texto='Iniciando acompanhamento.')
        self.action(ticket,'status',status='aguardando_aluno',texto='Aguardando novo check-in.')
        store.session(self.aid,{'acao':'mes','id_cliente':str(uuid4())});self.complete(self.aid,'1','5')
        tickets=self.tickets()
        self.assertEqual(len(tickets),1)
        self.assertEqual(tickets[0]['status'],'em_andamento')
        self.assertEqual(len(tickets[0]['questionarios']),2)
        history=self.api('atendimentos/'+ticket['id']+'/historico')[1]['dados']['itens']
        self.assertEqual(len(history),4)

    def test_resolved_ticket_remains_and_new_session_opens_another(self):
        self.complete(self.aid);ticket=self.tickets()[0]
        self.action(ticket,'responsavel',uid=self.attendant(),texto='Atribuição inicial.')
        for status in ['aguardando_aluno','resolvido']:
            self.action(ticket,'status',status=status,texto='Etapa do acompanhamento.')
        store.session(self.aid,{'acao':'mes','id_cliente':str(uuid4())});self.complete(self.aid,'1','5')
        tickets=self.tickets()
        self.assertEqual({t['status'] for t in tickets},{'aberto','resolvido'})
        self.assertEqual(len(tickets),2)

    def test_responsible_comments_and_retry_use_existing_actions(self):
        self.complete(self.aid);ticket=self.tickets()[0]
        attendant = self.attendant()
        assigned=self.action(ticket,'responsavel',uid=attendant,texto='Atribuição inicial.')
        self.assertEqual(assigned['responsavel']['uid'],attendant)
        body={'idAcao':str(uuid4()),'texto':'Orientação acadêmica registrada.','visivelAoAluno':False}
        url='atendimentos/'+ticket['id']+'/comentarios'
        first=self.api(url,'POST',body)
        self.assertEqual(first,self.api(url,'POST',body))
        self.assertEqual(len(self.api('atendimentos/'+ticket['id']+'/historico')[1]['dados']['itens']),3)
        with closing(store.connect(store.OPERATIONAL,True)) as c:
            for row in c.execute('SELECT resultado FROM gestao_acoes'):
                self.assertNotIn('resposta_financeira',row[0])

    def test_permissions_and_course_filter_are_preserved(self):
        self.complete(self.aid);ticket=self.tickets()[0]
        coord=self.api('login','POST',{'email':'coord@radache.local','senha':'admin123'})[1]['dados']['token']
        self.assertEqual(self.api('atendimentos/'+ticket['id'],token=coord)[0],200)
        other=store.save(dict(nome='TESTE Outro curso',matricula='OUTRO',curso='Pedagogia'))
        self.complete(other)
        other_ticket=next(t for t in self.tickets() if t['alunoId']==str(-other))
        self.assertEqual(self.api('atendimentos/'+other_ticket['id'],token=coord)[0],404)
        items=self.api('atendimentos?cursoId=pedagogia')[1]['dados']['itens']
        self.assertTrue(all(t['cursoId']=='pedagogia' for t in items))

    def test_revocation_removes_answers_in_ticket_and_action_retries(self):
        self.complete(self.aid);ticket=self.tickets()[0]
        body={'idAcao':str(uuid4()),'texto':'Contato inicial registrado.'}
        url='atendimentos/'+ticket['id']+'/comentarios'
        self.assertEqual(self.api(url,'POST',body)[0],200)
        self.answer(self.aid,'REVOGAR')
        data=self.api('atendimentos/'+ticket['id'])[1]['dados']
        self.assertTrue(data['consentimentoRevogado']);self.assertEqual(data['questionarios'],[])
        self.assertEqual(self.api(url,'POST',body)[1]['dados']['questionarios'],[])

    def test_new_process_recovers_already_completed_session(self):
        # Sessão salva antes da integração ou de uma falha de entrega ao quadro.
        session=store.session(self.aid)
        for text in ['1','4','1']:
            session=store.session(self.aid,{'acao':'responder','texto':text,'sessao_id':session['sessao_id'],'id_cliente':str(uuid4())})
        with closing(store.connect(store.OPERATIONAL,True)) as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM gestao_chamados').fetchone()[0],0)
        self.assertEqual(len(self.tickets()),1)
        store.init();self.assertEqual(len(self.tickets()),1)

    def test_board_risk_uses_latest_valid_assessment_and_is_not_cached_in_actions(self):
        store.save({'nota_media':0,'frequencia':0},self.aid)
        self.complete(self.aid);ticket=self.tickets()[0]
        self.assertEqual(ticket['riscoAcademico']['nivel'],'alto')
        self.assertEqual(ticket['riscoAcademico']['indice'],100)
        store.save({'nota_media':10,'frequencia':100},self.aid)
        store.session(self.aid,{'acao':'mes','id_cliente':str(uuid4())});self.complete(self.aid,'1','5')
        ticket=self.tickets()[0]
        self.assertEqual(ticket['riscoAcademico']['nivel'],'baixo')
        self.assertEqual(ticket['riscoAcademico']['indice'],0)
        updated=self.action(ticket,'comentarios',texto='Orientação registrada.')
        self.assertEqual(updated['riscoAcademico'],ticket['riscoAcademico'])
        with closing(store.connect(store.OPERATIONAL,True)) as c:
            self.assertTrue(all('riscoAcademico' not in r[0] for r in c.execute('SELECT resultado FROM gestao_acoes')))

    def test_board_risk_disappears_after_revocation(self):
        self.complete(self.aid);ticket=self.tickets()[0]
        self.assertEqual(ticket['riscoAcademico']['nivel'],'medio')
        self.answer(self.aid,'REVOGAR')
        detail=self.api('atendimentos/'+ticket['id'])[1]['dados']
        self.assertEqual(detail['riscoAcademico'],dict(nivel='sem_avaliacao',indice=None,dataAvaliacao=None))

    def test_status_totals_respect_filters_and_include_unloaded_tickets(self):
        self.complete(self.aid)
        full=self.api('atendimentos?status=aberto')[1]['dados']
        first=self.api('atendimentos?status=aberto&limite=1')[1]['dados']
        self.assertEqual(first['total'],len(full['itens']))
        self.assertEqual(len(first['itens']),1)
        if first['total']>1:self.assertIsNotNone(first['proximaPagina'])
        course=self.api('atendimentos?status=aberto&cursoId=ciencia-da-computacao')[1]['dados']
        self.assertEqual(course['total'],len(course['itens']))
        self.assertTrue(all(t['status']=='aberto' and t['cursoId']=='ciencia-da-computacao' for t in course['itens']))

    def test_risk_priority_precedes_recency_and_pagination_in_every_status(self):
        cases=[(0,0,'4','1'),(10,100,'1','5'),(8,90,'4','1'),(None,None,'1','5'),(0,0,'4','1')]
        for n,(grade,attendance,finance,emotion) in enumerate(cases):
            aid=store.save(dict(nome='TESTE Prioridade '+str(n),matricula='PRIO-'+str(n),curso='Curso Prioridade',nota_media=grade,frequencia=attendance))
            self.complete(aid,finance,emotion)
        with closing(store.connect(store.OPERATIONAL)) as c,c:
            rows=c.execute('SELECT id,dados FROM gestao_chamados ORDER BY rowid').fetchall()
            for n,row in enumerate(rows):
                item=json.loads(row['dados']);item['ultimaAtividadeEm']=f'2026-01-0{n+1}T12:00:00+00:00'
                c.execute('UPDATE gestao_chamados SET dados=? WHERE id=?',(json.dumps(item),row['id']))
        expected=[rows[i]['id'] for i in [4,0,2,1,3]]
        for status in gestao.TRANSICOES:
            with closing(store.connect(store.OPERATIONAL)) as c,c:
                for row in c.execute('SELECT id,dados FROM gestao_chamados').fetchall():
                    item=json.loads(row['dados']);item['status']=status
                    c.execute('UPDATE gestao_chamados SET dados=? WHERE id=?',(json.dumps(item),row['id']))
            query='atendimentos?cursoId=curso-prioridade&status='+status
            full=self.api(query)[1]['dados']
            self.assertEqual([t['id'] for t in full['itens']],expected,status)
            pages=[self.api(query+'&limite=1&depois='+str(i))[1]['dados']['itens'][0]['id'] for i in range(5)]
            self.assertEqual(pages,expected,status)

    def test_contact_links_distinguish_original_and_simulated_students(self):
        example=self.api('atendimentos/exemplo-1')[1]['dados']
        self.assertEqual(example['whatsappSimuladoUrl'],'/mensagens/?aluno=-1')
        academic=self.http('/simulation-api/academicos/1')[1]['dados']
        self.assertEqual(academic['id'],-1)
        self.assertEqual(academic['nome'],example['alunoNome'])
        self.complete(self.aid);ticket=self.tickets()[0]
        self.assertEqual(ticket['whatsappSimuladoUrl'],'/mensagens/?aluno='+str(self.aid))
        self.assertNotEqual(store.session(-1)['sessao_id'],store.session(self.aid)['sessao_id'])
        store.deactivate(self.aid)
        self.assertIsNone(self.api('atendimentos/'+ticket['id'])[1]['dados']['whatsappSimuladoUrl'])

    def test_original_contact_questionnaire_preserves_identity_and_academic_database(self):
        before=database.DB_PATH.read_bytes();source=analytics.source();count=len(source);mock_count=len(store.students())
        responses_before=len(next(s for s in source if s['id']==1)['respondidos'])
        self.complete(-1,'1','5')
        self.assertEqual(database.DB_PATH.read_bytes(),before)
        self.assertEqual(len(store.students()),mock_count)
        self.assertEqual(len(analytics.source()),count)
        student=next(s for s in analytics.source() if s['id']==1)
        self.assertEqual(len(student['respondidos']),responses_before+1)
        ticket=next(t for t in self.tickets() if t['alunoId']=='1')
        self.assertEqual(ticket['whatsappSimuladoUrl'],'/mensagens/?aluno=-1')
        self.assertEqual(ticket['alunoNome'],store.conversation_student(-1)['nome'])


if __name__=='__main__':unittest.main(verbosity=2)
