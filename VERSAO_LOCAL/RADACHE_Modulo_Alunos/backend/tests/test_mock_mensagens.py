"""Contrato HTTP do protótipo, inclusive isolamento do banco e APIs privadas."""
import http.client
import json
from pathlib import Path
import sys
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app
import mock_mensagens


def payload_valido(**alteracoes):
    return {
        "id_cliente": "da16077f-0230-48cc-966b-a3ce23635312",
        "conteudo_texto": "Olá! Acolhimento e atenção. 💚",
        "id_remetente": 1,
        "id_destinatario": 101,
        "timestamp": "2026-10-26T14:30:00.000Z",
        **alteracoes,
    }


class MockMensagensTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = app.ThreadingHTTPServer(("127.0.0.1", 0), app.RadacheRequestHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def request(self, method, path, payload=None, raw=None, content_type="application/json"):
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=3)
        body = raw if raw is not None else json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else b""
        conn.request(method, path, body, {"Content-Type": content_type})
        response = conn.getresponse()
        status, headers, data = response.status, dict(response.getheaders()), response.read()
        conn.close()
        return status, headers, data

    def test_post_real_preserva_unicode_e_declara_ausencia_de_persistencia(self):
        payload = payload_valido()
        with patch.object(app.database, "get_connection", side_effect=AssertionError("Não acessar banco")):
            status, headers, raw = self.request("POST", mock_mensagens.ENDPOINT, payload)
        resposta = json.loads(raw)
        self.assertEqual(status, 201)
        self.assertEqual(headers["Content-Type"], "application/json; charset=utf-8")
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertTrue(resposta["sucesso"])
        self.assertEqual(resposta["modo"], "mock")
        self.assertFalse(resposta["persistido"])
        self.assertEqual({k: resposta["dados"][k] for k in payload}, payload)
        self.assertTrue(resposta["dados"]["id_mensagem"])

    def test_rejeita_payloads_invalidos_sem_sucesso_ficticio(self):
        invalidos = [None, [], {}, payload_valido(conteudo_texto="   "), payload_valido(conteudo_texto="x" * 4001),
                     payload_valido(id_remetente=True), payload_valido(id_destinatario=0),
                     payload_valido(id_destinatario=1.5), payload_valido(id_cliente="invalido"),
                     payload_valido(timestamp="2026-10-26T10:00:00"), payload_valido(timestamp="ontem"),
                     payload_valido(timestamp="2026-10-26T10:00:00-04:00"), payload_valido(extra="nao previsto")]
        for payload in invalidos:
            with self.subTest(payload=payload):
                status, _, raw = self.request("POST", mock_mensagens.ENDPOINT, raw=json.dumps(payload).encode())
                self.assertEqual(status, 400)
                self.assertFalse(json.loads(raw)["sucesso"])

    def test_corpo_invalido_grande_e_content_type(self):
        for raw in (b"{", b"\xff", b""):
            self.assertEqual(self.request("POST", mock_mensagens.ENDPOINT, raw=raw)[0], 400)
        self.assertEqual(self.request("POST", mock_mensagens.ENDPOINT, raw=b"x" * 32769)[0], 413)
        self.assertEqual(self.request("POST", mock_mensagens.ENDPOINT, payload_valido(), content_type="text/plain")[0], 415)

    def test_rotas_estaticas_e_modulos_es(self):
        for path in ("/mensagens/", "/mensagens/js/app.js", "/mensagens/js/services/api-service.js", "/mensagens/styles.css", "/mensagens/README.md"):
            with self.subTest(path=path):
                status, headers, raw = self.request("GET", path)
                self.assertEqual(status, 200)
                self.assertGreater(len(raw), 0)
                if path.endswith(".js"):
                    self.assertIn("javascript", headers["Content-Type"])
        self.assertEqual(self.request("GET", "/mensagens")[0], 302)

    def test_rejeicao_de_content_type_entrega_resposta_http_em_sequencia(self):
        for _ in range(20):
            status, _, raw = self.request('POST', mock_mensagens.ENDPOINT, payload_valido(), content_type='text/plain')
            self.assertEqual(status, 415)
            self.assertFalse(json.loads(raw)['sucesso'])

    def test_mock_nao_abre_endpoints_privados(self):
        for method in ("GET", "POST"):
            status, _, _ = self.request(method, "/api/mensagens", payload_valido() if method == "POST" else None)
            self.assertEqual(status, 401)


if __name__ == "__main__":
    unittest.main()
