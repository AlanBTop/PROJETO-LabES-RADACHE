import unittest

from risk import classificar_risco


class ClassificacaoRiscoTests(unittest.TestCase):
    def test_limites_e_classificacao(self):
        casos = {
            0: "estavel", 33: "estavel", 33.5: "moderado", 34: "moderado",
            66: "moderado", 66.99: "moderado", 67: "critico", 100: "critico",
        }
        for indice, esperado in casos.items():
            with self.subTest(indice=indice):
                self.assertEqual(classificar_risco(indice), esperado)

    def test_rejeita_indice_fora_de_zero_a_cem(self):
        for indice in (-0.1, 100.1):
            with self.subTest(indice=indice), self.assertRaises(ValueError):
                classificar_risco(indice)


if __name__ == "__main__":
    unittest.main()
