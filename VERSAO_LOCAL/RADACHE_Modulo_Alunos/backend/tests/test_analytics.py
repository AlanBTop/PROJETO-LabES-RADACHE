"""Indicadores confrontados com dados SQLite controlados, sem números de interface."""
from contextlib import closing
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from uuid import uuid4
import test_local_simulation as acceptance
import analytics
import course_catalog
import database
import simulation_store as store
import gestao_local


class AnalyticsTests(unittest.TestCase):
    http=acceptance.LocalSimulation.http
    answer=acceptance.LocalSimulation.answer
    complete=acceptance.LocalSimulation.complete

    def setUp(self):
        acceptance.LocalSimulation.setUp(self)
        with closing(database.get_connection()) as c,c:c.execute('DELETE FROM alunos')

    def tearDown(self):
        gestao_local.SESSOES.clear()
        acceptance.LocalSimulation.tearDown(self)

    def add(self,n=1,course='Computação',period=4,average=8,attendance=90,status='ativo'):
        return store.save(dict(nome='TESTE Analítico '+str(n),matricula='BI-'+str(n),curso=course,periodo=period,nota_media=average,frequencia=attendance,status=status))

    def query(self,**filters):
        from urllib.parse import urlencode
        code,result=self.http('/api/analytics?'+urlencode(filters))
        self.assertEqual(code,200,result)
        return result['dados']

    def test_multiple_courses_with_unanswered_students_and_other_statuses(self):
        self.add(1);self.add(2,'Pedagogia');self.add(3,'Direito');self.add(4,'Direito',status='inativo')
        data=self.query();k=data['kpis']
        self.assertEqual((k['cadastrados'],k['elegiveis'],k['cursos']),(4,3,31))
        self.assertEqual((k['sem_avaliacao'],k['baixo'],k['sem_resposta']),(3,0,3))
        self.assertEqual(data['estudantes']['itens'],[])
        self.assertEqual(sum(c['elegiveis'] for c in data['cursos']),3)

    def test_shared_catalog_has_thirty_courses_and_no_alias_duplicates(self):
        self.assertEqual(len(course_catalog.COURSES),30)
        rows=course_catalog.catalog(['agronomia','Engenharia Agronômica','ADMINISTRACAO','  Administração  ','Economia'])
        self.assertEqual(len(rows),30)
        self.assertEqual(len({r['id'] for r in rows}),30)
        self.assertEqual(course_catalog.course_id('Engenharia Agronômica'),'agronomia')

    def test_empty_catalog_available_in_all_dashboard_and_management_options(self):
        code,result=self.http('/api/cursos')
        self.assertEqual(code,200)
        self.assertEqual(len(result['dados']),30)
        self.assertEqual(result['dados'],gestao_local.cursos())
        data=self.query()
        self.assertEqual(data['kpis']['cursos'],30)
        self.assertEqual(data['kpis']['cadastrados'],0)
        self.assertEqual(len(data['cursos']),30)
        self.assertTrue(all(c['cadastrados']==0 and c['alto_pct_total'] is None for c in data['cursos']))
        self.assertEqual({c['nome'] for c in data['opcoes']['cursos']},set(course_catalog.COURSES))

    def test_existing_aliases_are_grouped_without_rewriting_academic_database(self):
        self.add(1,'Agronomia');self.add(2,'Engenharia Agronômica')
        with closing(store.connect(store.ACADEMIC)) as c,c:
            c.execute("UPDATE alunos SET curso='Agronomia' WHERE id=1")
        before=store.ACADEMIC.read_bytes()
        data=self.query(curso='Engenharia Agronômica')
        self.assertEqual(len(data['cursos']),1)
        self.assertEqual(data['kpis']['cadastrados'],2)
        self.assertEqual({s['curso'] for s in data['estudantes']['itens']},{'Agronomia / Engenharia Agronômica'})
        self.assertEqual(before,store.ACADEMIC.read_bytes())
        self.assertEqual(len(self.http('/api/cursos')[1]['dados']),30)

    def test_administrative_save_normalizes_alias_and_whatsapp_reads_same_course(self):
        code,result=self.http('/api/mock-alunos','POST',dict(nome='TESTE Catálogo',matricula='CAT-1',curso='  engenharia agronomica  '))
        self.assertEqual(code,201,result)
        student=store.student(result['id'])
        self.assertEqual(student['curso'],'Agronomia / Engenharia Agronômica')
        students=self.http('/simulation-api/alunos')[1]['dados']
        self.assertEqual(students[0]['curso'],student['curso'])

    def test_course_without_students_has_no_invented_percentages(self):
        self.add()
        data=self.query(curso='Curso sem alunos')
        self.assertEqual(data['kpis']['cadastrados'],0)
        self.assertIsNone(data['kpis']['cobertura_avaliacao'])
        self.assertIsNone(data['cursos'][0]['alto_pct_total'])
        self.assertFalse(data['evolucao']['suficiente'])

    def test_course_with_students_but_without_answers_is_not_low_risk(self):
        self.add();self.add(2)
        k=self.query(curso='Computação')['kpis']
        self.assertEqual(k['sem_avaliacao'],2)
        self.assertEqual(k['baixo'],0)
        self.assertEqual(k['checkins'],0)

    def test_real_questionnaire_changes_kpis_and_distinct_denominators(self):
        high=self.add(1,average=0,attendance=0);medium=self.add(2);low=self.add(3,average=10,attendance=100);self.add(4)
        self.complete(high,'4','1');self.complete(medium,'4','1');self.complete(low,'1','5')
        k=self.query()['kpis']
        self.assertEqual((k['alto'],k['medio'],k['baixo'],k['sem_avaliacao']),(1,1,1,1))
        self.assertEqual(k['alto_pct_total'],25)
        self.assertEqual(k['alto_pct_avaliados'],33.3)
        self.assertEqual(k['cobertura_avaliacao'],75)
        self.assertEqual(k['checkins'],3)
        with closing(store.connect(store.OPERATIONAL,True)) as c:
            self.assertEqual(c.execute('SELECT COUNT(DISTINCT aluno_id) FROM avaliacoes_sim').fetchone()[0],k['avaliados'])

    def test_latest_valid_evaluation_not_multiple_people(self):
        aid=self.add();self.complete(aid,'4','1')
        store.session(aid,{'acao':'mes','id_cliente':str(uuid4())});self.complete(aid,'1','5')
        data=self.query(curso='Computação');k=data['kpis']
        self.assertEqual(k['cadastrados'],1);self.assertEqual(k['baixo'],1);self.assertEqual(k['medio'],0)
        self.assertEqual(k['checkins'],2)
        self.assertEqual(data['estudantes']['itens'][0]['indice'],7.5)
        self.assertTrue(data['evolucao']['suficiente'])

    def test_filters_by_course_semester_risk_dates_and_followup(self):
        aid=self.add();self.complete(aid)
        first=store.session(aid)['estado']['timestamp'][:10]
        store.session(aid,{'acao':'mes','id_cliente':str(uuid4())});self.complete(aid,'1','5')
        self.add(2,'Pedagogia',2)
        self.assertEqual(self.query(curso='Pedagogia',periodo=2)['kpis']['cadastrados'],1)
        self.assertEqual(self.query(curso='Pedagogia',periodo=4)['kpis']['cadastrados'],0)
        k=self.query(inicio=first,fim=first)['kpis']
        self.assertEqual((k['medio'],k['baixo'],k['checkins']),(1,0,1))
        self.assertEqual(self.query(risco='baixo')['kpis']['cadastrados'],1)
        self.assertEqual(self.query(acompanhamento='sem_resposta')['kpis']['cadastrados'],1)
        self.assertEqual(self.query(acompanhamento='aberto')['kpis']['cadastrados'],1)

    def test_comparison_between_different_size_courses(self):
        for i in range(1,5):self.add(i,'Curso A',average=0,attendance=0)
        self.add(5,'Curso B',average=0,attendance=0)
        self.complete(1);self.complete(5)
        courses={c['nome']:c for c in self.query()['cursos']}
        self.assertEqual(courses['Curso A']['alto_pct_total'],25)
        self.assertEqual(courses['Curso B']['alto_pct_total'],100)
        self.assertEqual(courses['Curso A']['sem_avaliacao_pct'],75)

    def test_no_temporal_trend_with_single_observed_month(self):
        aid=self.add();self.complete(aid)
        data=self.query()
        self.assertFalse(data['evolucao']['suficiente'])
        self.assertEqual(len(data['evolucao']['pontos']),1)
        self.assertEqual(data['evolucao']['pontos'][0]['checkins'],1)

    def test_student_pagination_order_and_individual_history(self):
        for i in range(1,12):self.add(i)
        data=self.query(curso='Computação',limite=3,pagina=2,ordenar_alunos='nome')
        self.assertEqual(data['estudantes']['total'],11)
        self.assertEqual(data['estudantes']['paginas'],4)
        self.assertEqual(len(data['estudantes']['itens']),3)
        self.assertEqual([s['id'] for s in data['estudantes']['itens']],[-2,-3,-4])
        self.assertEqual(self.query(curso='Computação',busca='BI-11')['estudantes']['total'],1)
        self.complete(1)
        result=self.http('/api/analytics/students/-1')[1]['dados']
        self.assertEqual(len(result['questionarios']),1)
        self.assertEqual(len(result['atendimentos']),1)
        self.assertIsNone(result['variacao'])

    def test_readonly_analytics_does_not_change_any_database(self):
        aid=self.add();self.complete(aid)
        paths=[store.ACADEMIC,store.OPERATIONAL,database.DB_PATH]
        before=[p.read_bytes() for p in paths]
        self.query();self.query(curso='Computação');self.http('/api/analytics/students/-1')
        self.assertEqual(before,[p.read_bytes() for p in paths])

    def test_authentication_profile_and_aggregate_privacy(self):
        aid=self.add();self.complete(aid)
        self.assertEqual(self.http('/api/analytics',token='')[0],401)
        general=self.query()
        self.assertNotIn('TESTE Analítico',json.dumps(general,ensure_ascii=False))
        nae=self.http('/api/login','POST',{'usuario':'nae','senha':'admin123'})[1]['token']
        data=self.http('/api/analytics',token=nae)[1]['dados']
        self.assertEqual([f['chave'] for f in data['fatores']],['emocional'])
        detail=self.http('/api/analytics/students/-1',token=nae)[1]['dados']
        self.assertNotIn('financeira',detail['questionarios'][0])
        self.assertNotIn('nota_media',detail['atual'])
        self.assertNotIn('eventos',detail['atendimentos'][0])

    def test_invalid_filters_and_missing_student(self):
        for query in ['periodo=0','inicio=ruim','inicio=2027-01-01&fim=2026-01-01','risco=inventado','pagina=0','ordenacao=SQL']:
            self.assertEqual(self.http('/api/analytics?'+query)[0],400,query)
        self.assertEqual(self.http('/api/analytics/students/-99999')[0],404)

    def test_risk_transition_and_attention_alert_are_based_on_history(self):
        aid=self.add();self.complete(aid)
        store.save({'nota_media':0,'frequencia':0},aid)
        store.session(aid,{'acao':'mes','id_cliente':str(uuid4())});self.complete(aid)
        data=self.query(curso='Computação')
        self.assertEqual(data['alertas']['subiu_para_alto'],1)
        self.assertEqual(data['alertas']['sem_primeiro_atendimento'],1)
        self.assertEqual(self.query(alerta='subiu_para_alto')['kpis']['alto'],1)

    def test_persistence_and_offline_read_in_separate_process(self):
        aid=self.add();self.complete(aid)
        env={**os.environ,'RADACHE_DB':str(database.DB_PATH),'RADACHE_MOCK_DB':str(store.ACADEMIC),'RADACHE_SIM_DB':str(store.OPERATIONAL)}
        script="from unittest.mock import patch;import analytics,json;\nwith patch('socket.create_connection',side_effect=AssertionError('Rede bloqueada')): print(json.dumps(analytics.overview({})['kpis']))"
        result=subprocess.run([sys.executable,'-c',script],cwd=Path(store.__file__).parent,env=env,capture_output=True,text=True,check=True)
        self.assertEqual(json.loads(result.stdout),self.query()['kpis'])


if __name__=='__main__':unittest.main(verbosity=2)
