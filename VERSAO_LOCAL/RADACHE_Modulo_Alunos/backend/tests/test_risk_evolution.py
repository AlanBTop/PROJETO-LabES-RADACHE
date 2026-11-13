"""Evolução por novas evidências, independente do atendimento, com histórico durável."""
from contextlib import closing
import json
import os
import subprocess
import sys
import unittest
from unittest.mock import patch
from uuid import uuid4
import test_local_simulation as acceptance
import analytics
import database
import gestao_local as gestao
import simulation_store as store


class RiskEvolutionTests(unittest.TestCase):
    http=acceptance.LocalSimulation.http
    answer=acceptance.LocalSimulation.answer
    complete=acceptance.LocalSimulation.complete

    def setUp(self):
        acceptance.LocalSimulation.setUp(self);gestao.iniciar()
        self.gtoken=self.http('/api/local/login','POST',{'email':'admin@radache.local','senha':'admin123'})[1]['dados']['token']
        self.aid=store.save(dict(nome='TESTE Evolução',matricula='EV-01',curso='Ciência da Computação',nota_media=0,frequencia=0))

    def tearDown(self):
        gestao.SESSOES.clear();acceptance.LocalSimulation.tearDown(self)

    def detail(self):return analytics.detail(-self.aid)

    def ticket(self):
        result=self.http('/api/local/atendimentos','GET',token=self.gtoken)[1]['dados']['itens']
        return next(t for t in result if t['alunoId']==str(-self.aid))

    def action(self,ticket,path,**values):
        code,result=self.http('/api/local/atendimentos/'+ticket['id']+'/'+path,'POST',{'idAcao':str(uuid4()),**values},token=self.gtoken)
        self.assertEqual(code,200,result);return result['dados']

    def next(self,grade,attendance,finance='4',emotion='1'):
        before=self.detail()['indice']
        store.save({'nota_media':grade,'frequencia':attendance},self.aid)
        store.session(self.aid,{'acao':'mes','id_cliente':str(uuid4())})
        self.assertEqual(self.detail()['indice'],before)
        self.complete(self.aid,finance,emotion)
        return self.detail()

    def raw(self):
        with closing(store.connect(store.OPERATIONAL,True)) as c:
            return [r[0] for r in c.execute('SELECT dados FROM avaliacoes_sim WHERE aluno_id=? ORDER BY rowid',(self.aid,))]

    def test_all_ticket_actions_and_resolution_preserve_high_risk_and_history(self):
        self.complete(self.aid);before=self.raw();ticket=self.ticket()
        self.assertEqual(ticket['riscoAcademico']['indice'],100)
        attendant = gestao.tratar('POST', 'usuarios', {}, dict(nome='Atendente risco', login='atendente-risco', senhaInicial='Inicial#2026', perfil='atendente_academico', campusId='caceres', cursoIds=['ciencia-da-computacao']), self.gtoken)
        assigned = self.action(ticket,'responsavel',uid=attendant['id'],texto='Atribuição inicial.')
        self.assertEqual(assigned['status'], 'em_andamento')
        self.assertEqual(assigned['riscoAcademico']['indice'], 100)
        self.action(ticket,'comentarios',texto='Orientação sem nova evidência de melhora.')
        self.action(ticket,'classificacao',categoria='financeiro',texto='Ajuste de categoria.')
        for status in ('aguardando_aluno','resolvido'):
            item=self.action(ticket,'status',status=status,texto='Ação de acompanhamento.')
            self.assertEqual(item['riscoAcademico']['indice'],100)
            self.assertEqual(item['evolucaoRisco']['direcao'],'inicial')
            self.assertEqual(self.raw(),before)
        self.assertEqual(self.detail()['risco'],'alto')
        self.assertEqual(self.ticket()['status'],'resolvido')

    def test_progressive_improvement_records_snapshots_contributions_and_dashboards(self):
        self.complete(self.aid);first=self.raw()[0]
        self.assertEqual(self.detail()['indice'],100)
        self.assertEqual(self.next(0,80)['indice'],80)
        data=self.next(6,90,'2','4')
        self.assertEqual(data['indice'],27)
        metadata=json.loads(self.raw()[-1])['metadados_risco']
        self.assertEqual(metadata['variacao_pontos'],-53)
        self.assertEqual(metadata['origem'],'whatsapp_simulado')
        self.assertAlmostEqual(sum(f['variacao_contribuicao'] for f in metadata['fatores']),-53)
        self.assertEqual(self.next(9,100,'1','5')['indice'],2.5)
        self.assertEqual(self.raw()[0],first)
        self.assertEqual(len(self.raw()),4)
        evolution=self.detail()['evolucao_risco']
        self.assertEqual([p['indice'] for p in evolution['pontos']],[100,80,27,2.5])
        self.assertEqual(evolution['direcao'],'diminuiu')
        self.assertEqual(evolution['variacao_total'],-97.5)
        summary=analytics.overview({'curso':'Ciência da Computação'})
        self.assertEqual(summary['mudancas_risco']['diminuiu'],1)
        row=next(s for s in summary['estudantes']['itens'] if s['id']==-self.aid)
        self.assertEqual(row['evolucao_risco']['direcao'],'diminuiu')

    def test_worsening_and_stability_follow_new_answers_even_with_followup_open(self):
        store.save({'nota_media':9,'frequencia':95},self.aid);self.complete(self.aid,'1','5')
        self.assertEqual(self.detail()['indice'],3.75)
        data=self.next(0,30)
        self.assertEqual(data['indice'],92.5)
        self.assertEqual(data['evolucao_risco']['direcao'],'aumentou')
        data=self.next(0,30)
        self.assertEqual(data['evolucao_risco']['direcao'],'estavel')
        self.assertEqual(data['evolucao_risco']['variacao'],0)
        self.assertEqual(self.ticket()['status'],'aberto')

    def test_incomplete_new_evidence_does_not_replace_last_valid_risk_with_zero(self):
        self.complete(self.aid)
        data=self.next(None,None,'1','5')
        self.assertEqual(data['indice'],100)
        self.assertEqual(store.projected()[0]['indice_risco'],100)
        self.assertEqual(len(data['evolucao_risco']['avaliacoes']),2)
        self.assertIsNone(data['evolucao_risco']['avaliacoes'][-1]['indice'])
        self.assertEqual(len(data['evolucao_risco']['pontos']),1)

    def test_weight_changes_are_stored_and_not_misrepresented_as_new_answers(self):
        store.save({'frequencia':50},self.aid);self.complete(self.aid)
        weights=dict(notas=.4,frequencia=.4,financeiro=.1,psicologico=.1)
        with patch.dict(os.environ,{'RADACHE_RISK_WEIGHTS':json.dumps(weights)}):
            self.next(0,50)
        last=self.detail()['evolucao_risco']['avaliacoes'][-1]
        self.assertTrue(last['pesos_alterados'])
        self.assertEqual(last['variacao_pontos'],-7.5)
        self.assertTrue(all(f['variacao_componente']==0 for f in last['fatores']))

    def test_restricted_profile_does_not_receive_other_factor_details(self):
        self.complete(self.aid);self.next(9,100,'1','5')
        data=analytics.detail(-self.aid,'nae')
        factors=data['evolucao_risco']['avaliacoes'][-1]['fatores']
        self.assertEqual([f['chave'] for f in factors],['psicologico'])
        for e in data['historico_avaliacoes']:
            self.assertNotIn('metadados_risco',e)
            self.assertNotIn('nota_media',e)

    def test_evolution_survives_restart_and_separate_process(self):
        self.complete(self.aid);self.next(8,90,'1','5');before=self.raw();store.init()
        self.assertEqual(self.raw(),before)
        env={**os.environ,'RADACHE_DB':str(database.DB_PATH),'RADACHE_MOCK_DB':str(store.ACADEMIC),'RADACHE_SIM_DB':str(store.OPERATIONAL)}
        script=f"import analytics,json;print(json.dumps(analytics.detail({-self.aid})['evolucao_risco']))"
        result=subprocess.run([sys.executable,'-c',script],cwd=database.BASE_DIR/'backend',env=env,capture_output=True,text=True,check=True)
        data=json.loads(result.stdout)
        self.assertEqual(data,self.detail()['evolucao_risco'])


if __name__=='__main__':unittest.main(verbosity=2)
