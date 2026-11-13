import http.client
import json
import threading
import unittest
from unittest.mock import patch

import app
from auth import SessionManager, gerar_hash_senha


class RotasAutenticacaoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = app.ThreadingHTTPServer(("127.0.0.1", 0), app.RadacheRequestHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.port = cls.server.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def setUp(self):
        credenciais = gerar_hash_senha("senha-de-teste", "00112233445566778899aabbccddeeff")
        self.patch_auth = patch.object(app, "auth", SessionManager({"operador": {**credenciais, "role": "coordenacao"}}))
        self.patch_auth.start()

    def tearDown(self):
        self.patch_auth.stop()

    def requisitar(self, method, path, dados=None, token=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=3)
        headers = {}
        body = None
        if dados is not None:
            headers["Content-Type"] = "application/json"
            body = json.dumps(dados)
        if token:
            headers["Authorization"] = "Bearer " + token
        conn.request(method, path, body=body, headers=headers)
        response = conn.getresponse()
        payload = json.loads(response.read().decode("utf-8"))
        conn.close()
        return response.status, payload

    def test_rotas_de_dados_negam_acesso_sem_login(self):
        for method, path in (("GET", "/api/dashboard"), ("GET", "/api/alunos"),
                             ("POST", "/api/alunos"), ("PUT", "/api/alunos/1"),
                             ("DELETE", "/api/alunos/1")):
            with self.subTest(method=method, path=path):
                status, _ = self.requisitar(method, path, dados={} if method in ("POST", "PUT") else None)
                self.assertEqual(status, 401)

    def test_login_emite_token_que_libera_endpoint_de_sessao(self):
        status, payload = self.requisitar("POST", "/api/login", {"usuario": "operador", "senha": "senha-de-teste"})
        self.assertEqual(status, 200)
        status, sessao = self.requisitar("GET", "/api/session", token=payload["token"])
        self.assertEqual(status, 200)
        self.assertEqual(sessao["usuario"]["role"], "coordenacao")

    def test_logout_revoga_token(self):
        _, payload = self.requisitar("POST", "/api/login", {"usuario": "operador", "senha": "senha-de-teste"})
        self.assertEqual(self.requisitar("POST", "/api/logout", token=payload["token"])[0], 200)
        self.assertEqual(self.requisitar("GET", "/api/session", token=payload["token"])[0], 401)

    def test_perfil_setorial_e_somente_leitura(self):
        credenciais = gerar_hash_senha("senha-de-teste", "ffeeddccbbaa99887766554433221100")
        manager = SessionManager({"academico": {**credenciais, "role": "caest"}})
        with patch.object(app, "auth", manager):
            _, sessao = self.requisitar("POST", "/api/login", {"usuario": "academico", "senha": "senha-de-teste"})
            status, _ = self.requisitar("POST", "/api/alunos", {}, sessao["token"])
            self.assertEqual(status, 403)
            aluno = {"id": 1, "nome": "Teste", "matricula": "M1", "curso": "Curso", "periodo": 1,
                     "status": "ativo", "nota_media": 8, "frequencia": 90, "email": "privado",
                     "situacao_financeira": "critica", "indice_risco": 90}
            with patch.object(app.alunos, "listar", return_value=[aluno]):
                status, payload = self.requisitar("GET", "/api/alunos", token=sessao["token"])
            self.assertEqual(status, 200)
            self.assertIn("nota_media", payload["dados"][0])
            self.assertNotIn("email", payload["dados"][0])
            self.assertNotIn("situacao_financeira", payload["dados"][0])
            self.assertNotIn("indice_risco", payload["dados"][0])


if __name__ == "__main__":
    unittest.main()
