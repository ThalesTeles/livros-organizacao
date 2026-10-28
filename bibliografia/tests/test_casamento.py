import unittest

from bibliografia.casamento import (Casador, normalizar, numero_edicao, numero_volume, similaridade_titulo,
                                    sobrenomes_do_livro, sobrenomes_do_ppc)
from bibliografia.modelos import Livro, Obra

from .base import ACERVO, CORMEN, INTRO_ALG, OBRA_CORMEN_ED2, THOMAS_V1, THOMAS_V2


class TestNormalizacao(unittest.TestCase):
    def test_normalizar(self):
        self.assertEqual(normalizar("Álgebra Linear: do Jeito Certo!"), "algebra linear do jeito certo")

    def test_edicao_e_volume(self):
        self.assertEqual(numero_edicao("3ª ed."), 3)
        self.assertIsNone(numero_edicao("sem-ed"))
        self.assertEqual(numero_volume("Cálculo, v. 2"), 2)
        self.assertEqual(numero_volume("Cálculo Vol. 1"), 1)
        self.assertIsNone(numero_volume("Cálculo"))

    def test_titulo_igual_vale_um(self):
        self.assertEqual(similaridade_titulo("Lógica para Computação", "logica para computacao"), 1.0)


class TestAutores(unittest.TestCase):
    def test_formato_abnt(self):
        self.assertEqual(sobrenomes_do_ppc("CORMEN, Thomas H.; LEISERSON, Charles E."), {"cormen", "leiserson"})
        self.assertEqual(sobrenomes_do_ppc("STEWART, James"), {"stewart"})

    def test_nome_sobrenome(self):
        self.assertEqual(sobrenomes_do_ppc("Thomas H. Cormen, Charles E. Leiserson"), {"cormen", "leiserson"})

    def test_autores_do_acervo(self):
        self.assertEqual(sobrenomes_do_livro("Cormen et al"), {"cormen"})
        self.assertEqual(sobrenomes_do_livro("Marconi e Lakatos"), {"marconi", "lakatos"})


class TestCasador(unittest.TestCase):
    def setUp(self):
        self.casador = Casador(ACERVO)

    def test_mesma_obra_em_outra_edicao_casa(self):
        achadas = self.casador.correspondencias(OBRA_CORMEN_ED2)
        self.assertEqual(achadas[0].livro, CORMEN)

    def test_primeiro_nome_igual_a_sobrenome_nao_confunde(self):
        obra = Obra("Algoritmos: teoria e prática", "CORMEN, Thomas H.")
        livros = {c.livro for c in self.casador.correspondencias(obra)}
        self.assertNotIn(THOMAS_V1, livros)
        self.assertNotIn(THOMAS_V2, livros)
        self.assertNotIn(THOMAS_V1, self.casador.possiveis(obra))

    def test_volume_diferente_nao_casa(self):
        obra = Obra("Cálculo, v. 2", "THOMAS, George B.")
        livros = [c.livro for c in self.casador.correspondencias(obra)]
        self.assertIn(THOMAS_V2, livros)
        self.assertNotIn(THOMAS_V1, livros)

    def test_mesmo_titulo_com_autores_diferentes_nao_casa(self):
        casador = Casador([Livro("l.pdf", "Lógica", "Silva", "1")])
        self.assertEqual(casador.correspondencias(Obra("Lógica", "SOUZA, João")), [])

    def test_titulo_em_outro_idioma_vira_possivel_nao_casamento(self):
        obra = Obra("Algoritmos: teoria e prática", "CORMEN, Thomas H.")
        casador = Casador([INTRO_ALG])
        self.assertEqual(casador.correspondencias(obra), [])
        self.assertEqual(casador.possiveis(obra), [INTRO_ALG])

    def test_sem_autor_no_ppc_aceita_so_pelo_titulo(self):
        obra = Obra("Algoritmos: Teoria e Prática", "")
        self.assertTrue(self.casador.correspondencias(obra))


if __name__ == "__main__":
    unittest.main()
