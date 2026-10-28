import csv
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from bibliografia import relatorio
from bibliografia.analise import AnalisadorDeLacunas
from bibliografia.modelos import BASICA

from .base import ACERVO, OBRA_REDES, requisitos_exemplo


class TestRelatorio(unittest.TestCase):
    def setUp(self):
        self.rels = AnalisadorDeLacunas(ACERVO).analisar(BASICA, requisitos_exemplo(), ["algoritmos"])

    def test_markdown(self):
        md = relatorio.renderizar_markdown(BASICA, self.rels, ppc="ementa.pdf", total_acervo=len(ACERVO),
                                           gerado_em=datetime(2026, 10, 4, 12, 0))
        self.assertIn("# Livros faltantes — bibliografia básica", md)
        self.assertIn("Disciplinas sem nenhum livro básico no acervo (prioridade)", md)
        self.assertIn("- [ ] **Redes de Computadores**", md)
        self.assertIn("buscar: `Redes de Computadores Tanenbaum 5 edição`", md)
        self.assertIn("acrescentar `|compiladores:basica`", md)                 # vínculo a ajustar
        self.assertIn("trocar `logica-para-computacao:complementar` por `logica-para-computacao:basica`", md)
        self.assertIn("Inglês Instrumental", md)                               # PPC sem bibliografia listada

    def test_csv(self):
        with tempfile.TemporaryDirectory() as d:
            caminho = Path(d) / "x.csv"
            relatorio.escrever_csv(caminho, BASICA, self.rels)
            with open(caminho, encoding="utf-8-sig") as f:
                linhas = list(csv.DictReader(f, delimiter=";"))
        self.assertEqual({l["situacao"] for l in linhas}, {"ok", "tipo_diferente", "sem_vinculo", "ausente"})
        ausente = next(l for l in linhas if l["situacao"] == "ausente")
        self.assertEqual(ausente["titulo"], OBRA_REDES.titulo)

    def test_resumo_lista_primeiro_as_disciplinas_sem_livros(self):
        linhas = relatorio.resumo_terminal(BASICA, self.rels).splitlines()
        primeira = next(l for l in linhas[2:] if l.strip())
        self.assertIn("acervo=0", primeira)


if __name__ == "__main__":
    unittest.main()
