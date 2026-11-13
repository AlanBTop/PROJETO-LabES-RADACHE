import hashlib
import hmac
import http.client
import json
import os
import threading
import unittest
from unittest.mock import patch

import app


class WebhookWhatsAppApiTests(unittest.TestCase):
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

    def requisitar(self, method, path, body=b"", headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=3)
        conn.request(method, path, body=body, headers=headers or {})
        response = conn.getresponse()
        raw = response.read()
        status = response.status
        conn.close()
        return status, raw

    def test_verificacao_get_do_provedor_retorna_challenge(self):
        with patch.dict(os.environ, {"WHATSAPP_VERIFY_TOKEN": "verificacao-segura"}):
            status, body = self.requisitar(
                "GET", "/webhooks/whatsapp?hub.mode=subscribe&hub.verify_token=verificacao-segura&hub.challenge=abc123"
            )
        self.assertEqual((status, body), (200, b"abc123"))

    def test_post_exige_hmac_e_encaminha_mensagem(self):
        payload = {"entry": [{"changes": [{"value": {"messages": [
            {"from": "5565998123401", "type": "text", "text": {"body": "SIM"}}
        ]}}]}]}
        corpo = json.dumps(payload).encode()
        segredo = "segredo-app"
        assinatura = "sha256=" + hmac.new(segredo.encode(), corpo, hashlib.sha256).hexdigest()
        with patch.dict(os.environ, {"WHATSAPP_APP_SECRET": segredo}), patch.object(app.whatsapp, "processar_mensagem") as processar:
            status_ruim, _ = self.requisitar("POST", "/webhooks/whatsapp", corpo, {
                "Content-Type": "application/json", "Content-Length": str(len(corpo)),
            })
            self.assertEqual(status_ruim, 401)
            status, resposta = self.requisitar("POST", "/webhooks/whatsapp", corpo, {
                "Content-Type": "application/json", "Content-Length": str(len(corpo)),
                "X-Hub-Signature-256": assinatura,
            })
        self.assertEqual(status, 200)
        self.assertTrue(json.loads(resposta)["sucesso"])
        processar.assert_called_once_with("5565998123401", "SIM")


if __name__ == "__main__":
    unittest.main()
