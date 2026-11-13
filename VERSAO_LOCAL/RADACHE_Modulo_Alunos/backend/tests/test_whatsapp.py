"""Testes do fluxo WhatsApp; não realizam chamadas externas."""
import hashlib
import hmac
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import database
import whatsapp


class FluxoWhatsAppTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp.name) / "teste.db"
        self.patch_db = patch.object(database, "DB_PATH", self.db_path)
        self.patch_db.start()
        conn = sqlite3.connect(self.db_path)
        conn.executescript(database.SCHEMA_PATH.read_text(encoding="utf-8-sig"))
        conn.execute("INSERT INTO alunos (id,nome,matricula,curso,periodo,email,telefone) VALUES (1,'Teste','T1','Curso',1,'','65998123401')")
        conn.execute("INSERT INTO avaliacoes (aluno_id,nota_media,frequencia,situacao_financeira,situacao_psicologica,indice_risco,classificacao_risco) VALUES (1,4.5,60,'moderada','critica',0,'estavel')")
        conn.commit()
        conn.close()
        database.init_db()

    def tearDown(self):
        self.patch_db.stop()
        self.temp.cleanup()

    def test_inicio_pede_consentimento_sem_gravar_consentimento(self):
        with patch.object(whatsapp, "enviar_template") as enviar:
            checkin_id = whatsapp.iniciar_checkin(1)
        self.assertEqual(checkin_id, 1)
        enviar.assert_called_once()
        self.assertEqual(enviar.call_args.args[2], (whatsapp.PERGUNTA_CONSENTIMENTO,))
        conn = sqlite3.connect(self.db_path)
        row = conn.execute("SELECT consentimento_lgpd,resposta_financeira,resposta_psicologica,estado_conversa FROM checkins").fetchone()
        conn.close()
        self.assertEqual(row, (0, None, None, "aguardando_consentimento"))

    def test_sem_aceite_nao_faz_perguntas_nem_processa_respostas(self):
        with patch.object(whatsapp, "enviar_template") as enviar, patch.object(whatsapp, "enviar_texto") as resposta:
            whatsapp.iniciar_checkin(1)
            whatsapp.processar_mensagem("5565998123401", "NAO")
            whatsapp.processar_mensagem("5565998123401", "4")
        enviar.assert_called_once()
        resposta.assert_called_once()
        conn = sqlite3.connect(self.db_path)
        row = conn.execute("SELECT consentimento_lgpd,resposta_financeira FROM checkins").fetchone()
        conn.close()
        self.assertEqual(row, (0, None))

    def test_revogacao_interrompe_fluxo_e_remove_respostas_do_checkin(self):
        with patch.object(whatsapp, "enviar_template") as modelo, patch.object(whatsapp, "enviar_texto") as enviar:
            whatsapp.iniciar_checkin(1)
            whatsapp.processar_mensagem("5565998123401", "SIM")
            whatsapp.processar_mensagem("5565998123401", "3")
            whatsapp.processar_mensagem("5565998123401", "2")
            aceitou_revogacao = whatsapp.processar_mensagem("5565998123401", "REVOGAR")
            mensagem_posterior = whatsapp.processar_mensagem("5565998123401", "4")
        self.assertTrue(aceitou_revogacao)
        self.assertFalse(mensagem_posterior)
        modelo.assert_called_once()
        conn = sqlite3.connect(self.db_path)
        consent, financeira, psicologica, estado = conn.execute(
            "SELECT consentimento_lgpd,resposta_financeira,resposta_psicologica,estado_conversa FROM checkins"
        ).fetchone()
        risco = conn.execute("SELECT indice_risco FROM avaliacoes WHERE aluno_id=1 ORDER BY id DESC LIMIT 1").fetchone()[0]
        conn.close()
        self.assertEqual((consent, financeira, psicologica, estado), (0, None, None, "revogado"))
        # Revogar impede processamento futuro; o índice histórico calculado com consentimento válido permanece.
        self.assertEqual(risco, 59)
        self.assertIn("revogado", enviar.call_args.args[1].casefold())

    def test_recusa_e_palavra_cancelar_nao_registram_resposta_de_pesquisa(self):
        with patch.object(whatsapp, "enviar_template"), patch.object(whatsapp, "enviar_texto") as enviar:
            whatsapp.iniciar_checkin(1)
            whatsapp.processar_mensagem("5565998123401", "CANCELAR")
        conn = sqlite3.connect(self.db_path)
        consent, fin, psi, estado = conn.execute(
            "SELECT consentimento_lgpd,resposta_financeira,resposta_psicologica,estado_conversa FROM checkins"
        ).fetchone()
        conn.close()
        self.assertEqual((consent, fin, psi, estado), (0, None, None, "recusado"))
        self.assertIn("não foi registrado", enviar.call_args.args[1].casefold())

    def test_resposta_invalida_e_repetida_e_checkin_completo_recalcula(self):
        with patch.object(whatsapp, "enviar_template") as modelo, patch.object(whatsapp, "enviar_texto") as enviar:
            whatsapp.iniciar_checkin(1)
            whatsapp.processar_mensagem("5565998123401", "SIM")
            whatsapp.processar_mensagem("5565998123401", "9")
            whatsapp.processar_mensagem("5565998123401", "3")
            whatsapp.processar_mensagem("5565998123401", "2")
        conn = sqlite3.connect(self.db_path)
        consent, fin, psi, state = conn.execute("SELECT consentimento_lgpd,resposta_financeira,resposta_psicologica,estado_conversa FROM checkins").fetchone()
        risk = conn.execute("SELECT indice_risco FROM avaliacoes WHERE aluno_id=1 ORDER BY id DESC LIMIT 1").fetchone()[0]
        conn.close()
        self.assertEqual((consent, fin, psi, state, risk), (1, "Dificuldade significativa", "2", "concluido", 59))
        modelo.assert_called_once()
        self.assertEqual(enviar.call_count, 4)

    def test_assinatura_meta_hmac(self):
        corpo = json.dumps({"entry": []}).encode()
        segredo = "app-secret"
        assinatura = "sha256=" + hmac.new(segredo.encode(), corpo, hashlib.sha256).hexdigest()
        self.assertTrue(whatsapp.validar_assinatura(corpo, assinatura, segredo))
        self.assertFalse(whatsapp.validar_assinatura(corpo, assinatura, "outro"))

    def test_migracao_preserva_checkins_legados(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute("CREATE TABLE checkins (id INTEGER PRIMARY KEY, data_checkin TIMESTAMP)")
        conn.execute("INSERT INTO checkins VALUES (1,'2026-01-02 03:04:05')")
        database.migrate_checkin_conversation(conn.cursor())
        row = conn.execute("SELECT estado_conversa,ultima_interacao,lembrete_enviado FROM checkins WHERE id=1").fetchone()
        conn.close()
        self.assertEqual(tuple(row), ("concluido", "2026-01-02 03:04:05", 0))

    def test_lembrete_so_apos_tres_dias_e_uma_vez(self):
        with patch.object(whatsapp, "enviar_template"), patch.object(whatsapp, "enviar_texto"):
            whatsapp.iniciar_checkin(1)
            whatsapp.processar_mensagem("5565998123401", "SIM")
        conn = sqlite3.connect(self.db_path)
        conn.execute("UPDATE checkins SET ultima_interacao=datetime('now','-4 days') WHERE id=1")
        conn.commit()
        conn.close()
        with patch.object(whatsapp, "enviar_template") as enviar:
            self.assertEqual(whatsapp.enviar_lembretes_pendentes(), 1)
            enviar.assert_called_once()
            self.assertEqual(whatsapp.enviar_lembretes_pendentes(), 0)


if __name__ == "__main__":
    unittest.main()
