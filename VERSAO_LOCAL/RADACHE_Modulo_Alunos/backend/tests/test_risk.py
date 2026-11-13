import os
import unittest
from unittest.mock import patch

from risk import calcular_indice_risco, calcular_nota, calcular_frequencia, calcular_financeiro, calcular_psicologico, carregar_pesos


class CalculoRiscoTests(unittest.TestCase):
    def test_componentes_do_criterio_de_aceitacao(self):
        self.assertEqual(calcular_nota(4.5), 55)
        self.assertEqual(calcular_frequencia(60), 40)
        self.assertEqual(calcular_financeiro("Dificuldade significativa"), 66)
        self.assertEqual(calcular_psicologico(2), 75)

    def test_indice_padrao_e_59_porcento(self):
        self.assertEqual(calcular_indice_risco(4.5, 60, "Dificuldade significativa", 2), 59)

    def test_pesos_configuraveis_sem_alterar_codigo(self):
        pesos = {"notas": 0.4, "frequencia": 0.2, "financeiro": 0.2, "psicologico": 0.2}
        self.assertEqual(calcular_indice_risco(4.5, 60, "Dificuldade significativa", 2, pesos), 58.2)

    def test_pesos_lidos_da_variavel_de_ambiente(self):
        config = '{"notas":0.4,"frequencia":0.2,"financeiro":0.2,"psicologico":0.2}'
        with patch.dict(os.environ, {"RADACHE_RISK_WEIGHTS": config}):
            self.assertEqual(carregar_pesos()["notas"], 0.4)

    def test_converte_financeiro_legado(self):
        self.assertEqual(calcular_financeiro("critica"), 100)
        self.assertEqual(calcular_financeiro("moderada"), 66)
        self.assertEqual(calcular_financeiro("estavel"), 0)

    def test_rejeita_valores_fora_da_escala(self):
        for func, value in ((calcular_nota, 10.1), (calcular_frequencia, -1), (calcular_psicologico, 6)):
            with self.subTest(func=func.__name__, value=value):
                with self.assertRaises(ValueError):
                    func(value)

    def test_pesos_devem_somar_um(self):
        with self.assertRaises(ValueError):
            calcular_indice_risco(4.5, 60, "Dificuldade significativa", 2,
                                  {"notas": .25, "frequencia": .25, "financeiro": .25, "psicologico": .1})


if __name__ == "__main__":
    unittest.main()
