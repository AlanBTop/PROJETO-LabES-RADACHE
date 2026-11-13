"""Regressões de CRUD, integridade, validação HTTP e reentregas WhatsApp."""
from contextlib import closing
import http.client
import json
import os
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

import app
import database
import whatsapp
from aluno_service import AlunoService
from auth import SessionManager, gerar_hash_senha
from risk import carregar_pesos


class ManutencaoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cred = gerar_hash_senha("senha-de-teste")
        cls.manager = SessionManager({"coord": {**cred, "role": "coordenacao"}})
        cls.token = cls.manager.autenticar("coord", "senha-de-teste")["token"]
        cls.server = app.ThreadingHTTPServer(("127.0.0.1", 0), app.RadacheRequestHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = patch.object(database, "DB_PATH", Path(self.temp.name) / "test.db")
        self.db.start()
        self.auth = patch.object(app, "auth", self.manager)
        self.auth.start()
        # Estes testes exercitam o banco legado, sem consultar o catálogo da instalação.
        self.catalog = patch.object(app.mock_alunos, 'projetados', return_value=[])
        self.catalog.start()
        self.addCleanup(self.catalog.stop)
        database.init_db()
        self.service = AlunoService()
        self.data = {"nome": "Aluno Teste", "matricula": "TEST1", "curso": "Curso",
                     "periodo": 1, "email": "aluno@example.com", "telefone": "(65) 99999-1234",
                     "nota_media": 0, "frequencia": 0, "indice_risco": 0,
                     "situacao_financeira": "critica", "situacao_psicologica": "moderada"}
        self.addCleanup(self.temp.cleanup)
        self.addCleanup(self.db.stop)
        self.addCleanup(self.auth.stop)

    def request(self, method, path, data=None, raw=None, headers=None):
        body = json.dumps(data).encode() if data is not None else raw
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=4)
        conn.request(method, path, body=body, headers={"Authorization": "Bearer " + self.token, **(headers or {})})
        response = conn.getresponse()
        status, content, response_headers = response.status, response.read(), dict(response.getheaders())
        conn.close()
        return status, content, response_headers

    def test_edicao_preserva_avaliacao_e_zero_sem_criar_historico_inutil(self):
        aluno_id = self.service.cadastrar(self.data)
        self.service.atualizar(aluno_id, {"nome": "Nome Alterado", "indice_risco": 0})
        aluno = self.service.obter(aluno_id)
        self.assertEqual(len(aluno["historico_avaliacoes"]), 1)
        self.assertEqual(aluno["avaliacao_atual"]["nota_media"], 0)
        self.assertEqual(aluno["avaliacao_atual"]["frequencia"], 0)
        self.assertEqual(aluno["avaliacao_atual"]["situacao_financeira"], "critica")

    def test_edicao_de_risco_preserva_demais_fatores(self):
        aluno_id = self.service.cadastrar(self.data)
        self.service.atualizar(aluno_id, {"indice_risco": 33.5})
        aluno = self.service.obter(aluno_id)
        self.assertEqual(aluno["avaliacao_atual"]["indice_risco"], 33.5)
        self.assertEqual(aluno["avaliacao_atual"]["classificacao_risco"], "moderado")
        self.assertEqual(aluno["avaliacao_atual"]["nota_media"], 0)
        self.assertEqual(aluno["avaliacao_atual"]["situacao_psicologica"], "moderada")
        self.assertEqual(len(aluno["historico_avaliacoes"]), 2)

    def test_avaliacoes_com_mesmo_timestamp_usam_a_ultima_insercao(self):
        aluno_id = self.service.cadastrar(self.data)
        self.service.atualizar(aluno_id, {"indice_risco": 70})
        with closing(database.get_connection()) as conn, conn:
            conn.execute("UPDATE avaliacoes SET data_avaliacao='2026-01-01' WHERE aluno_id=?", (aluno_id,))
        self.assertEqual(self.service.obter(aluno_id)["avaliacao_atual"]["indice_risco"], 70)

    def test_exclusao_logica_atualiza_vinculo_e_preserva_historico(self):
        aluno_id = self.service.cadastrar(self.data)
        self.assertTrue(self.service.excluir(aluno_id))
        self.assertIsNone(self.service.obter(aluno_id))
        self.assertNotIn(aluno_id, [row["id"] for row in self.service.listar()])
        aluno = database.get_aluno_by_id(aluno_id)
        self.assertEqual((aluno["status"], aluno["status_exclusao"]), ("inativo", 1))
        self.assertTrue(aluno["historico_avaliacoes"])

    def test_exclusao_fisica_cascateia_relacionamentos(self):
        aluno_id = self.service.cadastrar(self.data)
        self.service.excluir(aluno_id, "fisica")
        with closing(database.get_connection()) as conn, conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM avaliacoes WHERE aluno_id=?", (aluno_id,)).fetchone()[0], 0)

    def test_validacao_rejeita_nulos_tipos_e_limites_sem_escrever(self):
        casos = [{"nome": None}, {"matricula": 123}, {"curso": {}}, {"periodo": 1.5},
                 {"periodo": True}, {"periodo": 17}, {"indice_risco": float("nan")},
                 {"indice_risco": float("inf")}, {"nota_media": -1}, {"frequencia": 101},
                 {"status": "outro"}, {"email": "invalido"}, {"telefone": "123"},
                 {"situacao_financeira": "<script>"}, {"nome": "a" * 151}]
        before = len(self.service.listar())
        for change in casos:
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.service.cadastrar({**self.data, **change})
        self.assertEqual(len(self.service.listar()), before)

    def test_cadastro_operacional_bloqueia_escrita_mesmo_com_matricula_duplicada(self):
        self.service.cadastrar(self.data)
        status, _, _ = self.request("POST", "/api/alunos", self.data)
        self.assertEqual(status, 405)

    def test_falha_na_avaliacao_desfaz_cadastro_e_libera_escritas(self):
        with self.assertRaises(sqlite3.IntegrityError):
            database.create_aluno({**self.data, "nota_media": 999})
        self.assertFalse(any(row["matricula"] == "TEST1" for row in self.service.listar()))
        self.assertIsInstance(self.service.cadastrar(self.data), int)

    def test_falha_na_avaliacao_desfaz_edicao(self):
        aluno_id = self.service.cadastrar(self.data)
        with self.assertRaises(sqlite3.IntegrityError):
            database.update_aluno(aluno_id, {**self.data, "nome": "Não salvar", "nota_media": 999})
        self.assertEqual(self.service.obter(aluno_id)["nome"], "Aluno Teste")

    def test_banco_esvaziado_nao_recebe_amostras_ao_reiniciar(self):
        with closing(database.get_connection()) as conn, conn:
            conn.execute("DELETE FROM alunos")
        database.init_db()
        self.assertEqual(self.service.listar(), [])

    def test_periodo_invalido_na_consulta_retorna_400(self):
        self.assertEqual(self.request("GET", "/api/alunos?periodo=abc")[0], 400)

    def test_rotas_api_e_arquivos_inexistentes_retornam_404(self):
        for path in ("/api/inexistente", "/nao-existe.js", "/painel-demo/nao-existe.css", "/assets/nao-existe.css"):
            with self.subTest(path=path):
                self.assertEqual(self.request("GET", path)[0], 404)

    def test_rotas_de_mutacao_nao_aceitam_segmentos_extras(self):
        for method in ("PUT", "DELETE"):
            self.assertEqual(self.request(method, "/api/alunos/extra/1", {})[0], 404)

    def test_corpos_invalidos_retornam_400(self):
        for raw in (b'[]', b'{"nome": NaN}', b'{"nome":', b'\xff'):
            self.assertEqual(self.request("POST", "/api/mock-alunos", raw=raw)[0], 400)
        self.assertEqual(self.request("POST", "/api/mock-alunos", raw=b"{}", headers={"Content-Length": "1000001"})[0], 400)

    def test_respostas_privadas_nao_sao_armazenadas_em_cache(self):
        self.assertEqual(self.request("GET", "/api/session")[2]["Cache-Control"], "no-store")

    def test_painel_sem_barra_redireciona_para_assets_corretos(self):
        status, _, headers = self.request("GET", "/painel-demo")
        self.assertEqual((status, headers["Location"]), (302, "/painel-demo/"))

    def test_pesos_nan_e_infinito_sao_rejeitados(self):
        for value in (float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                carregar_pesos({"notas": value, "frequencia": 0, "financeiro": 0, "psicologico": 0})

    def test_webhook_repetido_nao_avanca_duas_perguntas(self):
        with patch.object(whatsapp, "enviar_template"), patch.object(whatsapp, "enviar_texto") as send:
            checkin_id = whatsapp.iniciar_checkin(1)
            whatsapp.processar_mensagem("5565998123401", "SIM", "m1")
            whatsapp.processar_mensagem("5565998123401", "3", "m2")
            whatsapp.processar_mensagem("5565998123401", "3", "m2")
            with closing(database.get_connection()) as conn, conn:
                row = conn.execute("SELECT estado_conversa,resposta_psicologica FROM checkins WHERE id=?", (checkin_id,)).fetchone()
            self.assertEqual(tuple(row), ("pergunta_psicologica", None))
            self.assertEqual(send.call_count, 2)

    def test_falha_de_envio_repete_resposta_sem_avancar_estado(self):
        with patch.object(whatsapp, "enviar_template"), patch.object(whatsapp, "enviar_texto") as send:
            whatsapp.iniciar_checkin(1)
            send.side_effect = RuntimeError("Sem rede")
            with self.assertRaises(RuntimeError):
                whatsapp.processar_mensagem("5565998123401", "SIM", "m3")
            send.side_effect = None
            whatsapp.processar_mensagem("5565998123401", "SIM", "m3")
            self.assertEqual(send.call_args.args[1], whatsapp.PERGUNTA_FINANCEIRA)

    def test_conclusao_sem_avaliacao_faz_rollback_do_checkin(self):
        aluno_id = self.service.cadastrar(self.data)
        with closing(database.get_connection()) as conn, conn:
            conn.execute("DELETE FROM avaliacoes WHERE aluno_id=?", (aluno_id,))
        with patch.object(whatsapp, "enviar_template"), patch.object(whatsapp, "enviar_texto"):
            checkin_id = whatsapp.iniciar_checkin(aluno_id)
            whatsapp.processar_mensagem("5565999991234", "SIM")
            whatsapp.processar_mensagem("5565999991234", "3")
            with self.assertRaises(ValueError):
                whatsapp.processar_mensagem("5565999991234", "2")
        with closing(database.get_connection()) as conn, conn:
            row = conn.execute("SELECT estado_conversa,resposta_psicologica FROM checkins WHERE id=?", (checkin_id,)).fetchone()
        self.assertEqual(tuple(row), ("pergunta_psicologica", None))

    def test_numero_com_ddd_55_nao_perde_ddd_na_comparacao(self):
        with closing(database.get_connection()) as conn, conn:
            conn.execute("UPDATE alunos SET telefone='(55) 99999-7777' WHERE id=1")
        self.assertEqual(whatsapp._encontrar_aluno_por_telefone("5555999997777"), 1)

    def test_convite_usa_codigo_do_pais(self):
        with patch.object(whatsapp, "enviar_template") as send:
            whatsapp.iniciar_checkin(1)
        self.assertEqual(send.call_args.args[0], "5565998123401")

    def test_webhook_rejeita_estrutura_invalida(self):
        for payload in ([], {"entry": [None]}, {"entry": [{"changes": [1]}]}):
            with self.assertRaises(ValueError):
                whatsapp.extrair_mensagens(payload)

    def test_envio_sem_configuracao_retorna_503_sem_disparar(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(whatsapp, "enviar_template") as send:
            self.assertEqual(self.request("POST", "/api/checkins/enviar")[0], 503)
            send.assert_not_called()

    def test_convites_concorrentes_criam_uma_unica_pendencia(self):
        results = []
        def iniciar():
            try:
                results.append(whatsapp.iniciar_checkin(1))
            except ValueError:
                results.append(None)
        with patch.object(whatsapp, "enviar_template") as send:
            threads = [threading.Thread(target=iniciar) for _ in range(2)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=3)
            self.assertEqual(results.count(None), 1)
            self.assertEqual(send.call_count, 1)

    def test_checkin_atualiza_situacoes_exibidas_na_ficha(self):
        with patch.object(whatsapp, "enviar_template"), patch.object(whatsapp, "enviar_texto"):
            whatsapp.iniciar_checkin(1)
            for text in ("SIM", "1", "5"):
                whatsapp.processar_mensagem("5565998123401", text)
        aluno = self.service.obter(1)
        self.assertEqual(aluno["avaliacao_atual"]["situacao_financeira"], "estavel")
        self.assertEqual(aluno["avaliacao_atual"]["situacao_psicologica"], "estavel")

if __name__ == "__main__":
    unittest.main()


