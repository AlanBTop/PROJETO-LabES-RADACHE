import sqlite3
import tempfile
from contextlib import closing
import unittest
from pathlib import Path
from unittest.mock import patch

import database


class RecalculoPorCheckinTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp.name) / "teste.db"
        self.patch_db = patch.object(database, "DB_PATH", self.db_path)
        self.patch_db.start()
        conn = sqlite3.connect(self.db_path)
        conn.executescript(database.SCHEMA_PATH.read_text(encoding="utf-8-sig"))
        conn.execute("INSERT INTO alunos (nome,matricula,curso,periodo,email,telefone) VALUES ('Teste','T1','Curso',1,'','')")
        conn.execute("INSERT INTO avaliacoes (aluno_id,nota_media,frequencia,situacao_financeira,situacao_psicologica,indice_risco,classificacao_risco) VALUES (1,4.5,60,'moderada','critica',0,'estavel')")
        conn.execute("INSERT INTO checkins (aluno_id,consentimento_lgpd,resposta_financeira,resposta_psicologica) VALUES (1,1,'Dificuldade significativa','2')")
        conn.commit()
        conn.close()

    def tearDown(self):
        self.patch_db.stop()
        self.temp.cleanup()

    def test_checkin_completo_consentido_atualiza_indice(self):
        self.assertEqual(database.recalcular_avaliacao_por_checkin(1), 59)
        conn = sqlite3.connect(self.db_path)
        indice, classificacao = conn.execute(
            "SELECT indice_risco, classificacao_risco FROM avaliacoes WHERE aluno_id=1 ORDER BY id DESC LIMIT 1"
        ).fetchone()
        conn.close()
        self.assertEqual(indice, 59)
        self.assertEqual(classificacao, "moderado")

    def test_new_assessment_preserves_previous_and_checkin_retry_is_idempotent(self):
        self.assertEqual(database.recalcular_avaliacao_por_checkin(1),59)
        self.assertEqual(database.recalcular_avaliacao_por_checkin(1),59)
        with closing(sqlite3.connect(self.db_path)) as conn:
            rows=conn.execute('SELECT indice_risco FROM avaliacoes ORDER BY id').fetchall()
        self.assertEqual(rows,[(0.0,),(59.0,)])

    def test_checkin_sem_consentimento_nao_e_processado(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("UPDATE checkins SET consentimento_lgpd=0 WHERE id=1")
        conn.commit()
        conn.close()
        with self.assertRaisesRegex(ValueError, "sem consentimento"):
            database.recalcular_avaliacao_por_checkin(1)

    def test_novo_aluno_grava_classe_derivada_do_indice(self):
        aluno_id = database.create_aluno({
            "nome": "Outro Teste", "matricula": "T2", "curso": "Curso", "periodo": 1,
            "email": "", "telefone": "", "indice_risco": 67,
            "classificacao_risco": "estavel",
        })
        conn = sqlite3.connect(self.db_path)
        classe = conn.execute(
            "SELECT classificacao_risco FROM avaliacoes WHERE aluno_id=?", (aluno_id,)
        ).fetchone()[0]
        conn.close()
        self.assertEqual(classe, "critico")

    def test_sincroniza_classificacao_legada_com_indice(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("UPDATE avaliacoes SET indice_risco=67, classificacao_risco='moderado' WHERE id=1")
        conn.commit()
        conn.close()
        self.assertEqual(database.reclassificar_avaliacoes(), 1)
        conn = sqlite3.connect(self.db_path)
        classe = conn.execute("SELECT classificacao_risco FROM avaliacoes WHERE id=1").fetchone()[0]
        conn.close()
        self.assertEqual(classe, "critico")


if __name__ == "__main__":
    unittest.main()
