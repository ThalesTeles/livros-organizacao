import csv
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from bibliografia.cli import main

from .base import requisitos_exemplo


class ExtratorFalso:
    def __init__(self):
        self.tipos = []

    def extrair(self, tipo, texto_ppc, pastas):
        self.tipos.append(tipo)
        return requisitos_exemplo()


def montar_ambiente(raiz: Path):
    for pasta in ("algoritmos", "logica-para-computacao", "compiladores", "redes-de-computadores", "livros"):
        (raiz / pasta).mkdir()
    (raiz / "livros-organizacao").mkdir()
    cabecalho = ["arquivo", "disciplinas", "titulo", "autor", "edicao", "revisar", "ignorar"]
    with open(raiz / "livros-organizacao" / "livros.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(cabecalho)
        w.writerow(["a.pdf", "algoritmos:basica", "Algoritmos: Teoria e Prática", "Cormen et al", "3", "", ""])
        w.writerow(["b.pdf", "logica-para-computacao:complementar", "Lógica para Computação", "Silva et al", "1", "", ""])
        w.writerow(["x.pdf", "algoritmos:basica", "Algoritmos: Teoria e Prática", "Cormen et al", "9", "", "x"])


class TestCli(unittest.TestCase):
    def rodar(self, tipo, *extra):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        raiz = Path(self.tmp.name)
        montar_ambiente(raiz)
        extrator = ExtratorFalso()
        argv = [tipo, "--raiz", str(raiz), "--csv", str(raiz / "livros-organizacao" / "livros.csv"),
                "--ppc", str(raiz / "ementa.pdf"), "--saida", str(raiz / "rel"), *extra]
        codigo = main(argv, extrator=extrator, leitor_ppc=lambda p, pag: "texto " * 1000, agora=datetime(2026, 1, 1))
        return codigo, extrator, raiz

    def test_basica_gera_relatorios_e_chama_so_o_tipo_pedido(self):
        codigo, extrator, raiz = self.rodar("basica")
        self.assertEqual(codigo, 0)
        self.assertEqual(extrator.tipos, ["basica"])
        self.assertTrue((raiz / "rel" / "faltantes-basica.md").is_file())
        self.assertTrue((raiz / "rel" / "faltantes-basica.csv").is_file())
        self.assertFalse((raiz / "rel" / "faltantes-complementar.md").exists())

    def test_complementar_e_separado(self):
        _, extrator, raiz = self.rodar("complementar")
        self.assertEqual(extrator.tipos, ["complementar"])
        self.assertTrue((raiz / "rel" / "faltantes-complementar.md").is_file())

    def test_filtros(self):
        _, _, raiz = self.rodar("basica", "--so-sem-livros", "--disciplina", "redes")
        md = (raiz / "rel" / "faltantes-basica.md").read_text(encoding="utf-8")
        self.assertIn("redes-de-computadores", md)
        self.assertNotIn("(`algoritmos`)", md)

    def test_sem_arquivos(self):
        _, _, raiz = self.rodar("basica", "--sem-arquivos")
        self.assertFalse((raiz / "rel").exists())


if __name__ == "__main__":
    unittest.main()
