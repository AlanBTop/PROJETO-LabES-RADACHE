"""Perguntas simples e ciclo simulado: HTTP real, SQLite temporário e serviços externos bloqueados."""
from contextlib import closing
import json
import re
import socket
import unittest
from unittest.mock import patch
from uuid import uuid4

import test_local_simulation as fixture
import simulation_store as store
import whatsapp

class CheckinClaro(unittest.TestCase):
    http = fixture.LocalSimulation.http
    create = fixture.LocalSimulation.create
    answer = fixture.LocalSimulation.answer
    complete = fixture.LocalSimulation.complete

    def setUp(self):
        fixture.LocalSimulation.setUp(self)
        self.addCleanup(fixture.LocalSimulation.tearDown, self)
        self.enterContext(patch.object(whatsapp, 'enviar_texto', side_effect=AssertionError('WhatsApp externo proibido')))
        self.enterContext(patch.object(whatsapp, 'enviar_template', side_effect=AssertionError('WhatsApp externo proibido')))
        connect = socket.create_connection
        def local_only(address, *args, **kwargs):
            if address[0] not in ('localhost', '127.0.0.1', '::1'):
                raise AssertionError('Rede externa proibida')
            return connect(address, *args, **kwargs)
        self.enterContext(patch('socket.create_connection', side_effect=local_only))

    def cycle(self, stage):
        aid = self.create('TESTE Clareza', 'CLARO-' + str(uuid4())[:8])
        store.session(aid)
        if stage == 'aguardando_inicio':
            self.complete(aid)
            store.session(aid, dict(acao='mes', id_cliente=str(uuid4())))
        elif stage in ('financeira', 'emocional', 'concluido'):
            self.answer(aid, '1')
            if stage in ('emocional', 'concluido'):
                self.answer(aid, '3')
            if stage == 'concluido':
                self.answer(aid, '1')
        return aid

    def test_perguntas_duas_frases_uma_ideia_e_opcoes_estaveis(self):
        prompts = dict(consentimento='Você aceita participar desta simulação?',
                       mensal='Você quer responder ao check-in simulado deste mês?',
                       financeira='Hoje, como estão suas condições financeiras para continuar estudando?',
                       emocional='Nas últimas semanas, como você tem se sentido?')
        for key, prompt in prompts.items():
            with self.subTest(pergunta=key):
                text = store.TEXTS[key]
                self.assertEqual(text.count('?'), 1)
                self.assertIn(prompt, text)
                self.assertLessEqual(len(re.findall(r'[.!?]+', text)), 2)
                self.assertIn('Responda apenas com o número da opção.', text)
                self.assertIn('Para sair: SAIR', text)
                numbers = re.findall(r'^(\d+) - ', text, re.MULTILINE)
                count = {'consentimento':2,'mensal':2,'financeira':4,'emocional':5}[key]
                self.assertEqual(numbers, [str(n) for n in range(1, count+1)])
                self.assertNotRegex(prompt, r'diagnóstico|transtorno|ansiedade|e trabalha|moradia e')
        self.assertEqual(re.findall(r'^\d - (.+)$', store.TEXTS['consentimento'], re.MULTILINE), ['Aceito', 'Recuso'])
        self.assertEqual(re.findall(r'^\d - (.+)$', store.TEXTS['emocional'], re.MULTILINE), ['Muito ruim','Ruim','Regular','Bom','Muito bom'])
        self.assertEqual(len(re.findall(r'[.!?]+', store.TEXTS['boasVindas'])), 1)
        self.assertIn('simulação', store.TEXTS['boasVindas'])

    def test_CT07_aceite_respostas_validas_e_risco_inalterado(self):
        with patch.object(store, 'calcular_indice_risco', wraps=store.calcular_indice_risco) as calculate:
            aid = self.cycle('consentimento')
            initial = store.session(aid)
            self.assertEqual([m['conteudo'] for m in initial['mensagens']], [store.TEXTS[k] for k in ('boasVindas','privacidade','sair','consentimento')])
            self.assertEqual(self.answer(aid, '1')[1]['dados']['estado']['etapa'], 'financeira')
            self.assertEqual(self.answer(aid, '4')[1]['dados']['estado']['etapa'], 'emocional')
            self.assertEqual(self.answer(aid, '1')[1]['dados']['estado']['etapa'], 'concluido')
            self.assertEqual(calculate.call_count, 1)
            self.assertEqual(calculate.call_args.args, (8.0,90.0,store.FIN[3],1))
        current = store.projected()[0]['avaliacao_atual']
        self.assertEqual((current['indice_risco'],current['classificacao_risco']), (57.5, 'moderado'))
        self.assertIn('não substitui a orientação de profissionais', store.session(aid)['mensagens'][-1]['conteudo'])

    def test_todas_as_opcoes_mantem_componentes_originais(self):
        for financial in range(1, 5):
            for emotion in range(1, 6):
                with self.subTest(financeira=financial, emocional=emotion):
                    aid = self.cycle('consentimento')
                    state = self.complete(aid, str(financial), str(emotion))['estado']
                    self.assertEqual((state['F'],state['P']), ([0,33,66,100][financial-1], [100,75,50,25,0][emotion-1]))

    def test_duas_invalidas_repetem_pergunta_e_encerram_em_todas_as_etapas(self):
        for stage in ('consentimento','aguardando_inicio','financeira','emocional'):
            with self.subTest(etapa=stage):
                aid = self.cycle(stage)
                with patch.object(store, 'calcular_indice_risco', side_effect=AssertionError('Não calcular incompletos')):
                    first = self.answer(aid, 'VALOR_INVALIDO')[1]['dados']
                    self.assertEqual(first['estado']['etapa'], stage)
                    self.assertEqual(first['estado']['tentativasInvalidas'], 1)
                    self.assertEqual([m['conteudo'] for m in first['mensagens'][-2:]], [store.TEXTS['invalida'], store.TEXTS[store.question_key(stage)]])
                    second = self.answer(aid, 'OUTRO_INVALIDO')[1]['dados']
                    self.assertEqual(second['estado']['etapa'], 'encerrado')
                    self.assertIsNone(second['estado']['financeira'])
                    self.assertIsNone(second['estado']['emocional'])
                    self.assertEqual(second['mensagens'][-1]['conteudo'], store.TEXTS['encerradoInvalido'])
                with closing(store.connect(store.OPERATIONAL)) as conn:
                    self.assertEqual(conn.execute('SELECT count(*) FROM avaliacoes_sim WHERE sessao_id=?', (second['sessao_id'],)).fetchone()[0], 0)
                    self.assertNotIn('VALOR_INVALIDO', '\n'.join(conn.iterdump()))
                self.assertEqual(self.answer(aid, '1')[1]['dados']['estado']['etapa'], 'encerrado')
                restarted = self.answer(aid, 'INICIAR')[1]['dados']['estado']
                self.assertEqual(restarted['tentativasInvalidas'], 0)

    def test_retry_e_recarga_nao_contam_como_nova_tentativa(self):
        aid = self.cycle('emocional')
        sid = store.session(aid)['sessao_id']
        ident = str(uuid4())
        first = self.answer(aid, '9', sid, ident)
        self.assertEqual(self.answer(aid, '9', sid, ident), first)
        self.assertEqual(store.session(aid)['estado']['tentativasInvalidas'], 1)
        self.assertEqual(self.answer(aid, '9')[1]['dados']['estado']['etapa'], 'encerrado')
        # Retry do comando financeiro anterior não recupera um cache de resposta incompleta.
        with closing(store.connect(store.OPERATIONAL)) as conn:
            self.assertTrue(all(json.loads(r[0])['estado']['financeira'] is None for r in conn.execute('SELECT resultado FROM comandos WHERE aluno_id=?', (aid,))))

    def test_resposta_valida_reinicia_contador_por_pergunta(self):
        aid = self.cycle('financeira')
        self.answer(aid, '9')
        state = self.answer(aid, '2')[1]['dados']['estado']
        self.assertEqual((state['etapa'],state['financeira'],state['tentativasInvalidas']), ('emocional',2,0))
        self.assertEqual(self.answer(aid, '9')[1]['dados']['estado']['etapa'], 'emocional')
        self.assertEqual(self.answer(aid, '2')[1]['dados']['estado']['etapa'], 'concluido')

    def test_recusa_nos_convites_e_sair_em_qualquer_etapa(self):
        for stage in ('consentimento','aguardando_inicio'):
            aid = self.cycle(stage)
            result = self.answer(aid, '2')[1]['dados']
            self.assertEqual((result['estado']['etapa'],result['estado']['consentimento']), ('recusado',False))
        for stage in ('consentimento','aguardando_inicio','financeira','emocional','concluido'):
            with self.subTest(etapa=stage):
                aid = self.cycle(stage)
                result = self.answer(aid, 'SAIR')[1]['dados']
                state = result['estado']
                self.assertFalse(state['consentimento'])
                self.assertIsNone(state['financeira']); self.assertIsNone(state['emocional'])
                self.assertIn(state['etapa'], ('recusado','revogado'))
                self.assertFalse(any(m['sensivel'] for m in result['mensagens']))
                with closing(store.connect(store.OPERATIONAL)) as conn:
                    self.assertEqual(conn.execute('SELECT count(*) FROM avaliacoes_sim WHERE aluno_id=?', (aid,)).fetchone()[0], 0)

    def test_aliases_de_revogacao_e_consentimento_expirado(self):
        for command in ('REVOGAR', 'CANCELAR', ' sair '):
            aid = self.cycle('emocional')
            self.assertEqual(self.answer(aid, command)[1]['dados']['estado']['etapa'], 'revogado')
        aid = self.cycle('emocional')
        with closing(store.connect(store.OPERATIONAL)) as conn, conn:
            row = conn.execute('SELECT id,estado FROM sessoes WHERE aluno_id=? ORDER BY rowid DESC LIMIT 1', (aid,)).fetchone()
            state = json.loads(row['estado']); state['timestamp'] = store.months(state['dataConsentimento'], 12)
            conn.execute('UPDATE sessoes SET estado=? WHERE id=?', (json.dumps(state),row['id']))
        with patch.object(store, 'calcular_indice_risco', side_effect=AssertionError('Consentimento expirado')):
            state = self.answer(aid, '1')[1]['dados']['estado']
            self.assertEqual((state['etapa'],state['consentimento'],state['emocional']), ('consentimento',False,None))

    def test_sem_aceite_nao_persiste_resposta_sensivel(self):
        aid = self.cycle('consentimento')
        marker = 'CONTEUDO_SENSIVEL_SEM_ACEITE'
        with patch.object(store, 'calcular_indice_risco', side_effect=AssertionError('Sem aceite')):
            self.answer(aid, marker)
            self.answer(aid, marker)
            self.assertFalse(store.session(aid)['estado']['consentimento'])
        with closing(store.connect(store.OPERATIONAL)) as conn:
            self.assertNotIn(marker, '\n'.join(conn.iterdump()))
            self.assertEqual(conn.execute('SELECT count(*) FROM mensagens WHERE aluno_id=? AND sensivel=1', (aid,)).fetchone()[0], 0)

    def test_audio_conta_como_invalida_sem_aceitar_ou_registrar_numero(self):
        aid = self.cycle('consentimento')
        for expected in ('consentimento','encerrado'):
            result = store.session(aid, dict(acao='responder',texto='1',tipo='audio',sessao_id=store.session(aid)['sessao_id'],id_cliente=str(uuid4())))
            self.assertEqual(result['estado']['etapa'], expected)
            self.assertFalse(result['estado']['consentimento'])

    def test_encerramento_incompleto_preserva_avaliacoes_anteriores(self):
        aid = self.cycle('concluido')
        with closing(store.connect(store.OPERATIONAL)) as conn:
            before = conn.execute('SELECT dados FROM avaliacoes_sim WHERE aluno_id=?', (aid,)).fetchone()[0]
        store.session(aid, dict(acao='mes',id_cliente=str(uuid4())))
        self.answer(aid,'1'); self.answer(aid,'2'); self.answer(aid,'9'); self.answer(aid,'9')
        with closing(store.connect(store.OPERATIONAL)) as conn:
            rows = conn.execute('SELECT dados FROM avaliacoes_sim WHERE aluno_id=?', (aid,)).fetchall()
            self.assertEqual([r[0] for r in rows], [before])
            result = store.session(aid)
            self.assertFalse(any(m['sensivel'] for m in result['mensagens'] if m['sessao_id']==result['sessao_id']))
