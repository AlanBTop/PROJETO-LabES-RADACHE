import unittest
from unittest.mock import patch

from auth import SessionManager, gerar_hash_senha, projetar_aluno


class AutenticacaoTests(unittest.TestCase):
    def setUp(self):
        credenciais = gerar_hash_senha("senha-correta", salt="00112233445566778899aabbccddeeff")
        self.auth = SessionManager({"coord": {**credenciais, "role": "coordenacao"}}, ttl_seconds=60)

    def test_senha_e_verificada_sem_armazenar_texto_puro(self):
        self.assertIsNone(self.auth.autenticar("coord", "errada"))
        sessao = self.auth.autenticar("coord", "senha-correta")
        self.assertEqual(sessao["role"], "coordenacao")
        self.assertNotIn("password", sessao)

    def test_token_autentica_e_logout_revoga(self):
        sessao = self.auth.autenticar("coord", "senha-correta")
        self.assertEqual(self.auth.obter_sessao(sessao["token"])["username"], "coord")
        self.assertTrue(self.auth.encerrar(sessao["token"]))
        self.assertIsNone(self.auth.obter_sessao(sessao["token"]))

    def test_sessao_expira(self):
        sessao = self.auth.autenticar("coord", "senha-correta")
        with patch("auth.time.time", return_value=sessao["expires_at"] + 1):
            self.assertIsNone(self.auth.obter_sessao(sessao["token"]))

    def test_arquivo_de_usuarios_exige_hash(self):
        with self.assertRaises(ValueError):
            SessionManager({"coord": {"password": "senha-pura", "role": "coordenacao"}})

    def test_perfil_setorial_recebe_apenas_seus_campos(self):
        aluno = {
            "id": 4, "nome": "Teste", "matricula": "A1", "curso": "Curso", "email": "oculto",
            "telefone": "oculto", "indice_risco": 60, "situacao_financeira": "critica",
            "avaliacao_atual": {"nota_media": 4, "frequencia": 60, "situacao_psicologica": "critica",
                                "situacao_financeira": "critica", "indice_risco": 60},
            "historico_checkins": [{"resposta_psicologica": "1"}],
        }
        prae = projetar_aluno(aluno, "prae")
        self.assertEqual(prae["situacao_financeira"], "critica")
        self.assertNotIn("email", prae)
        self.assertNotIn("indice_risco", prae)
        self.assertNotIn("historico_checkins", prae)
        self.assertEqual(set(prae["avaliacao_atual"]), {"situacao_financeira"})


if __name__ == "__main__":
    unittest.main()
