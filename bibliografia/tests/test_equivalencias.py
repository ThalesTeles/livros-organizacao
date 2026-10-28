import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from bibliografia.acervo import carregar_equivalencias
from bibliografia.analise import AnalisadorDeLacunas
from bibliografia.cli import main
from bibliografia.modelos import Equivalencia, Livro, Obra, RequisitoDisciplina, Situacao

from .test_cli import ExtratorFalso, montar_ambiente

FLEX45 = Livro("adobe-flex-4-5-fundamentals_labriola-tapper-e-boles_sem-ed.pdf", "Adobe Flex 4.5 Fundamentals",
               "Labriola, Tapper e Boles", "", (("tdig", "basica"),))
OBRA_FLEX4 = Obra("Adobe Flex 4 Training from the Source V1", "LABRIOLA, M.", ano=2010)
REQ = RequisitoDisciplina("tdig", "Tecnologias de Desenvolvimento de Interface", (OBRA_FLEX4,))
EQ = Equivalencia("Adobe Flex 4 Training from the Source", FLEX45.arquivo)


def resultado(equivalencias, pasta_do_vinculo=("tdig", "basica")):
    livro = Livro(FLEX45.arquivo, FLEX45.titulo, FLEX45.autor, "", (pasta_do_vinculo,))
    analisador = AnalisadorDeLacunas([livro], equivalencias=equivalencias)
    return analisador, analisador.analisar("basica", [REQ], ["tdig"])[0].resultados[0]


class TestEquivalenciasNaAnalise(unittest.TestCase):
    def test_sem_equivalencia_a_versao_nova_nao_e_aceita_sozinha(self):
        _, r = resultado([])
        self.assertIs(r.situacao, Situacao.AUSENTE)

    def test_com_equivalencia_conta_como_presente(self):
        _, r = resultado([EQ])
        self.assertIs(r.situacao, Situacao.OK)
        self.assertEqual(r.livro.arquivo, FLEX45.arquivo)

    def test_equivalencia_nao_ignora_o_vinculo(self):
        _, r = resultado([EQ], pasta_do_vinculo=("outra", "basica"))
        self.assertIs(r.situacao, Situacao.SEM_VINCULO)        # o livro existe, falta ligá-lo a esta disciplina

    def test_equivalencia_restrita_a_uma_disciplina(self):
        _, r = resultado([Equivalencia(EQ.obra, EQ.arquivo, pasta="outra")])
        self.assertIs(r.situacao, Situacao.AUSENTE)
        _, r = resultado([Equivalencia(EQ.obra, EQ.arquivo, pasta="tdig")])
        self.assertIs(r.situacao, Situacao.OK)

    def test_trecho_do_titulo_ignora_acento_e_maiuscula(self):
        _, r = resultado([Equivalencia("ADOBE FLEX 4 training from the SOURCE", FLEX45.arquivo)])
        self.assertIs(r.situacao, Situacao.OK)

    def test_arquivo_inexistente_gera_aviso(self):
        analisador, r = resultado([Equivalencia("Adobe Flex 4", "nao-existe.pdf")])
        self.assertIs(r.situacao, Situacao.AUSENTE)
        self.assertTrue(any("nao-existe.pdf" in a for a in analisador.avisos))


class TestLeituraDoCsv(unittest.TestCase):
    def test_le_ignora_comentarios_e_pasta_vazia(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "equivalencias.csv"
            p.write_text("\ufeffpasta;obra;arquivo\n# edição nova do mesmo livro\n\n"
                         "tecnologias-de-desenvolvimento-de-interface-grafica;Adobe Flex 4 Training;flex45.pdf\n"
                         ";Design Patterns;use-a-cabeca.pdf\n", encoding="utf-8")
            eqs = carregar_equivalencias(p)
        self.assertEqual([(e.pasta, e.obra, e.arquivo) for e in eqs],
                         [("tecnologias-de-desenvolvimento-de-interface-grafica", "Adobe Flex 4 Training", "flex45.pdf"),
                          ("", "Design Patterns", "use-a-cabeca.pdf")])

    def test_arquivo_ausente_nao_e_erro(self):
        self.assertEqual(carregar_equivalencias(Path("/nao/existe/equivalencias.csv")), [])


class TestCliDisciplinasSemBibliografia(unittest.TestCase):
    def rodar(self, *extra):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        raiz = Path(self.tmp.name)
        montar_ambiente(raiz)
        argv = ["basica", "--raiz", str(raiz), "--csv", str(raiz / "livros-organizacao" / "livros.csv"),
                "--ppc", str(raiz / "ementa.pdf"), "--saida", str(raiz / "rel"), *extra]
        main(argv, extrator=ExtratorFalso(), leitor_ppc=lambda p, pag: "texto " * 1000, agora=datetime(2026, 1, 1))
        return (raiz / "rel" / "faltantes-basica.md").read_text(encoding="utf-8")

    def test_por_padrao_fica_de_fora(self):
        md = self.rodar()
        self.assertNotIn("Inglês Instrumental", md)
        self.assertNotIn("sem bibliografia", md)
        self.assertIn("Algoritmos", md)

    def test_flag_traz_de_volta(self):
        md = self.rodar("--incluir-sem-bibliografia")
        self.assertIn("Inglês Instrumental", md)
        self.assertIn("## 5.", md)

    def test_cli_le_o_equivalencias_ao_lado_do_csv(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        raiz = Path(self.tmp.name)
        montar_ambiente(raiz)
        (raiz / "livros-organizacao" / "equivalencias.csv").write_text(
            "pasta;obra;arquivo\nredes-de-computadores;Redes de Computadores;a.pdf\n", encoding="utf-8")
        argv = ["basica", "--raiz", str(raiz), "--csv", str(raiz / "livros-organizacao" / "livros.csv"),
                "--ppc", str(raiz / "ementa.pdf"), "--saida", str(raiz / "rel")]
        main(argv, extrator=ExtratorFalso(), leitor_ppc=lambda p, pag: "texto " * 1000, agora=datetime(2026, 1, 1))
        md = (raiz / "rel" / "faltantes-basica.md").read_text(encoding="utf-8")
        # a.pdf (Cormen) não está vinculado a redes-de-computadores: deixa de estar "ausente" e vira "ajuste de vínculo"
        self.assertIn("acrescentar `|redes-de-computadores:basica`", md)


if __name__ == "__main__":
    unittest.main()
