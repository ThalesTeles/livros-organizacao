import unittest

from bibliografia.analise import AnalisadorDeLacunas
from bibliografia.modelos import BASICA, Situacao

from .base import ACERVO, requisitos_exemplo


class TestAnalise(unittest.TestCase):
    def setUp(self):
        pastas = ["algoritmos", "logica-para-computacao", "compiladores", "redes-de-computadores"]
        rels = AnalisadorDeLacunas(ACERVO).analisar(BASICA, requisitos_exemplo(), pastas)
        self.por_pasta = {r.pasta: r for r in rels}

    def test_ok_com_outra_edicao(self):
        r = self.por_pasta["algoritmos"].resultados[0]
        self.assertIs(r.situacao, Situacao.OK)
        self.assertTrue(r.outra_edicao)          # PPC cita a 2ª, o acervo tem a 3ª

    def test_tipo_diferente(self):
        r = self.por_pasta["logica-para-computacao"].resultados[0]
        self.assertIs(r.situacao, Situacao.TIPO_DIFERENTE)

    def test_sem_vinculo(self):
        r = self.por_pasta["compiladores"].resultados[0]
        self.assertIs(r.situacao, Situacao.SEM_VINCULO)

    def test_ausente(self):
        r = self.por_pasta["redes-de-computadores"].resultados[0]
        self.assertIs(r.situacao, Situacao.AUSENTE)
        self.assertEqual(self.por_pasta["redes-de-computadores"].no_acervo, 0)

    def test_contagem_do_acervo_e_pasta_inexistente(self):
        self.assertEqual(self.por_pasta["algoritmos"].no_acervo, 2)       # Cormen e Introduction to Algorithms
        self.assertFalse(self.por_pasta["ingles-instrumental"].tem_pasta)
        self.assertEqual(self.por_pasta["ingles-instrumental"].resultados, ())

    def test_cada_tipo_e_analisado_separadamente(self):
        rels = AnalisadorDeLacunas(ACERVO).analisar("complementar", requisitos_exemplo(), [])
        logica = next(r for r in rels if r.pasta == "logica-para-computacao")
        self.assertIs(logica.resultados[0].situacao, Situacao.OK)         # Lógica é complementar no acervo


if __name__ == "__main__":
    unittest.main()
