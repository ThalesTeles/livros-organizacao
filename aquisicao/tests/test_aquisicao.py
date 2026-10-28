import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from aquisicao.baixar import baixar_livres, nome_do_arquivo
from aquisicao.cli import main
from aquisicao.entrada import ler_csv, ler_faltantes, ler_md
from aquisicao.fontes import GoogleLivros, OpenLibrary
from aquisicao.links import links_de_busca, termo
from aquisicao.modelos import Acesso, Achado, ObraFaltante, Resultado
from aquisicao.texto import mesma_obra, primeiro_sobrenome

CSV = """\ufeffdisciplina;pasta;tipo;titulo;autores;edicao;situacao;livro_no_acervo;termo_de_busca;sugestao
ÉTICA EM COMPUTAÇÃO;etica-em-computacao;basica;Ética em Computação;MASIERO, Paulo César;;ausente;;Ética em Computação Masiero;
ÁLGEBRA LINEAR;algebra-linear;basica;Álgebra Linear;BOLDRINI, J. L. et al.;;ok;algebra-linear_boldrini.pdf;Álgebra Linear Boldrini;
LAB OAC;lab-oac;basica;Princípios Básicos de Arquitetura;"LOBUR, J.; NULL, L.";2ª ed.;ausente;;Princípios Básicos Lobur;
OAC;oac;basica;Princípios Básicos de Arquitetura;"LOBUR, J.; NULL, L.";2ª ed.;ausente;;Princípios Básicos Lobur;
"""

MD = """# Livros faltantes — bibliografia complementar

## Resumo por disciplina

| x |
|---|

## 1. Disciplinas sem nenhum livro complementar no acervo (prioridade)

### REDES (`redes-de-computadores`)

- [ ] **Computer Networks and Internets** — Comer, Douglas E. (1997)
  - buscar: `Computer Networks and Internets Comer`

## 2. Outras obras complementar ausentes (a disciplina já tem algum livro)

### PROGRAMAÇÃO WEB (`programacao-web`) — 2 no acervo

- [ ] **Patterns of Enterprise Application Architecture** — M. Fowler, 1st ed. (2002)
  - buscar: `Patterns of Enterprise Application Architecture Fowler`

## 3. Já estão no acervo, mas o vínculo precisa de ajuste no CSV

- [ ] **Não é ausente** (X): coisa
"""


def arquivo(d, nome, texto):
    p = Path(d) / nome
    p.write_text(texto, encoding="utf-8")
    return p


class TestEntrada(unittest.TestCase):
    def test_csv_so_ausentes_e_sem_repetir(self):
        with tempfile.TemporaryDirectory() as d:
            obras = ler_faltantes([arquivo(d, "faltantes-basica.csv", CSV)])
        self.assertEqual([o.titulo for o in obras], ["Ética em Computação", "Princípios Básicos de Arquitetura"])
        lobur = obras[1]
        self.assertEqual(lobur.disciplinas, ("LAB OAC", "OAC"))
        self.assertEqual(lobur.consulta, "Princípios Básicos Lobur")

    def test_md_le_so_as_secoes_de_ausentes(self):
        with tempfile.TemporaryDirectory() as d:
            obras = ler_md(arquivo(d, "faltantes-complementar.md", MD))
        self.assertEqual([o.titulo for o in obras], ["Computer Networks and Internets", "Patterns of Enterprise Application Architecture"])
        self.assertEqual(obras[0].disciplinas, ("REDES",))
        self.assertEqual(obras[0].tipos, ("complementar",))
        self.assertEqual(obras[0].consulta, "Computer Networks and Internets Comer")
        self.assertNotIn("Não é ausente", [o.titulo for o in obras])

    def test_junta_csv_e_md_basicas_primeiro(self):
        with tempfile.TemporaryDirectory() as d:
            obras = ler_faltantes([arquivo(d, "c.md", MD), arquivo(d, "b.csv", CSV)])
        self.assertEqual(obras[0].tipos, ("basica",))
        self.assertEqual(obras[-1].tipos, ("complementar",))
        self.assertEqual(len(obras), 4)

    def test_formato_invalido_e_arquivo_ausente(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):
                ler_faltantes([arquivo(d, "x.txt", "oi")])
            with self.assertRaises(FileNotFoundError):
                ler_faltantes([Path(d) / "nao-existe.csv"])


class TestTexto(unittest.TestCase):
    def test_primeiro_sobrenome(self):
        self.assertEqual(primeiro_sobrenome("T. H. CORMEN, C. E. LEISERSON"), "cormen")
        self.assertEqual(primeiro_sobrenome("MASIERO, Paulo César"), "masiero")
        self.assertEqual(primeiro_sobrenome("J. Levesque e G. Wagenbreth"), "levesque")

    def test_mesma_obra_exige_titulo_e_autor(self):
        self.assertTrue(mesma_obra("Ética em Computação", "MASIERO, Paulo", "Ética em computação", "Paulo Cesar Masiero"))
        self.assertFalse(mesma_obra("Ética em Computação", "MASIERO, Paulo", "Ética em Computação", "Fulano Beltrano"))
        self.assertFalse(mesma_obra("Redes de Computadores", "TANENBAUM", "Redes de Computadores e a Internet", "KUROSE"))


OBRA = ObraFaltante("Algoritmos: Teoria e Prática", "CORMEN, Thomas H.", "2", disciplinas=("ALGORITMOS",), tipos=("basica",))


class TestFontes(unittest.TestCase):
    def test_open_library_publico_emprestimo_e_ruido(self):
        docs = [
            {"title": "Algoritmos: Teoria e Prática", "author_name": ["Thomas H. Cormen"], "ia": ["algo-aberto"], "ebook_access": "public"},
            {"title": "Algoritmos: Teoria e Prática", "author_name": ["Thomas H. Cormen"], "ia": ["algo-emp"], "ebook_access": "borrowable"},
            {"title": "Algoritmos: Teoria e Prática", "author_name": ["Thomas H. Cormen"], "ia": ["x"], "ebook_access": "no_ebook"},
            {"title": "Outro livro qualquer", "author_name": ["Fulano"], "ia": ["y"], "ebook_access": "public"},
            {"title": "Algoritmos: Teoria e Prática", "author_name": ["Thomas H. Cormen"], "ebook_access": "public"},   # sem ia
        ]
        urls = []
        achados = OpenLibrary(lambda u: urls.append(u) or {"docs": docs}).buscar(OBRA)
        self.assertEqual([(a.acesso, a.url) for a in achados],
                         [(Acesso.LIVRE, "https://archive.org/details/algo-aberto"),
                          (Acesso.EMPRESTIMO, "https://archive.org/details/algo-emp")])
        self.assertEqual(achados[0].url_download, "https://archive.org/download/algo-aberto/algo-aberto.pdf")
        self.assertEqual(achados[1].url_download, "")                    # empréstimo nunca tem download direto
        self.assertIn("author=cormen", urls[0])

    def test_google_livros_livre_a_venda_e_previa(self):
        def vol(titulo, acesso, venda):
            return {"volumeInfo": {"title": titulo, "authors": ["Thomas H. Cormen"], "infoLink": "https://g/" + titulo},
                    "accessInfo": acesso, "saleInfo": venda}
        itens = [
            vol("Algoritmos: Teoria e Prática", {"publicDomain": True, "pdf": {"downloadLink": "https://g/pdf"}}, {"saleability": "FREE"}),
            vol("Algoritmos: Teoria e Prática", {"viewability": "NO_PAGES"},
                {"saleability": "FOR_SALE", "isEbook": True, "listPrice": {"amount": 99.9, "currencyCode": "BRL"}, "buyLink": "https://g/comprar"}),
            vol("Algoritmos: Teoria e Prática", {"viewability": "PARTIAL"}, {"saleability": "NOT_FOR_SALE"}),
            vol("Algoritmos: Teoria e Prática", {"publicDomain": True}, {"saleability": "FREE"}),     # livre, mas sem link de PDF: não vale
        ]
        achados = GoogleLivros(lambda u: {"items": itens}).buscar(OBRA)
        self.assertEqual([a.acesso for a in achados], [Acesso.LIVRE, Acesso.A_VENDA, Acesso.PREVIA])
        self.assertEqual(achados[0].url_download, "https://g/pdf")
        self.assertIn("BRL 99.9", achados[1].obs)
        self.assertEqual(achados[1].url, "https://g/comprar")

    def test_resposta_sem_resultados(self):
        self.assertEqual(OpenLibrary(lambda u: {}).buscar(OBRA), [])
        self.assertEqual(GoogleLivros(lambda u: {"totalItems": 0}).buscar(OBRA), [])


class TestLinks(unittest.TestCase):
    def test_usa_o_termo_pronto_e_monta_urls(self):
        o = ObraFaltante("Ética em Computação", "MASIERO", consulta="Ética em Computação Masiero")
        self.assertEqual(termo(o), "Ética em Computação Masiero")
        links = links_de_busca(o)
        self.assertIn("estantevirtual", links["Estante Virtual (usado)"])
        self.assertIn("%C3%89tica+em+Computa%C3%A7%C3%A3o+Masiero", links["Amazon Brasil"])
        self.assertEqual(termo(ObraFaltante("Livro X", "SOBRENOME, Fulano")), "Livro X sobrenome")


PDF = b"%PDF-1.4\n...conteudo..."


def resultado_livre(url="https://archive.org/download/x/x.pdf"):
    r = Resultado(OBRA)
    r.achados = [Achado("Open Library", Acesso.EMPRESTIMO, "t", "a", "https://emp"),
                 Achado("Open Library", Acesso.LIVRE, "t", "a", "https://det", url_download=url, obs="acesso aberto")]
    return r


class TestBaixar(unittest.TestCase):
    def test_baixa_so_o_livre_em_quarentena_e_registra(self):
        chamadas = []
        with tempfile.TemporaryDirectory() as d:
            r = resultado_livre()
            n = baixar_livres([r], Path(d) / "q", lambda u: chamadas.append(u) or PDF)
            self.assertEqual(n, 1)
            self.assertEqual(chamadas, ["https://archive.org/download/x/x.pdf"])      # o empréstimo nunca é baixado
            arq = Path(d) / "q" / nome_do_arquivo(OBRA.titulo, OBRA.autores)
            self.assertEqual(arq.read_bytes(), PDF)
            self.assertIn("archive.org/download/x/x.pdf", (Path(d) / "q" / "baixados.csv").read_text(encoding="utf-8"))
            self.assertEqual(r.baixado_em, str(arq))

    def test_nao_sobrescreve(self):
        with tempfile.TemporaryDirectory() as d:
            q = Path(d) / "q"
            q.mkdir()
            existente = q / nome_do_arquivo(OBRA.titulo, OBRA.autores)
            existente.write_bytes(b"%PDF meu arquivo")
            chamadas = []
            n = baixar_livres([resultado_livre()], q, lambda u: chamadas.append(u) or PDF)
            self.assertEqual((n, chamadas), (0, []))
            self.assertEqual(existente.read_bytes(), b"%PDF meu arquivo")

    def test_ignora_o_que_nao_e_pdf(self):
        with tempfile.TemporaryDirectory() as d:
            avisos = []
            n = baixar_livres([resultado_livre()], Path(d) / "q", lambda u: b"<html>login</html>", avisar=avisos.append)
            self.assertEqual(n, 0)
            self.assertFalse(list((Path(d) / "q").glob("*.pdf")))
            self.assertTrue(any("não é PDF" in a for a in avisos))

    def test_nome_do_arquivo(self):
        self.assertEqual(nome_do_arquivo("Algoritmos: Teoria e Prática", "CORMEN, Thomas"), "algoritmos-teoria-e-pratica_cormen.pdf")


class TestCli(unittest.TestCase):
    def rodar(self, *extra, json_falso=None, bytes_falso=None):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        d = Path(self.tmp.name)
        entrada = arquivo(d, "faltantes-basica.csv", CSV)
        argv = [str(entrada), "--saida", str(d / "rel"), "--quarentena", str(d / "q"), "--pausa", "0", *extra]
        main(argv, buscar_json=json_falso or (lambda u: {}), buscar_bytes=bytes_falso or (lambda u: PDF),
             agora=datetime(2026, 1, 1), dormir=lambda s: None)
        return d

    def test_sem_rede_gera_so_links(self):
        chamadas = []
        d = self.rodar("--sem-rede", json_falso=lambda u: chamadas.append(u) or {})
        self.assertEqual(chamadas, [])
        md = (d / "rel" / "aquisicao.md").read_text(encoding="utf-8")
        self.assertIn("Modo offline", md)
        self.assertIn("Estante Virtual", md)

    def test_com_fontes_e_baixar(self):
        def json_falso(url):
            if "openlibrary" in url:
                return {"docs": [{"title": "Ética em Computação", "author_name": ["Paulo Cesar Masiero"],
                                  "ia": ["etica-masiero"], "ebook_access": "public"}]}
            return {}
        d = self.rodar("--baixar", json_falso=json_falso)
        md = (d / "rel" / "aquisicao.md").read_text(encoding="utf-8")
        self.assertIn("## 1. Acesso livre", md)
        self.assertIn("**baixado**", md)
        self.assertTrue(any((d / "q").glob("*masiero.pdf")))
        csv_txt = (d / "rel" / "aquisicao.csv").read_text(encoding="utf-8-sig")
        self.assertIn("livre", csv_txt)
        self.assertIn("sem_versao_digital_legal", csv_txt)                 # a outra obra não tem versão legal

    def test_falha_de_rede_numa_fonte_nao_derruba(self):
        def quebra(url):
            raise ConnectionError("sem internet")
        d = self.rodar(json_falso=quebra)
        self.assertTrue((d / "rel" / "aquisicao.md").is_file())


if __name__ == "__main__":
    unittest.main()
