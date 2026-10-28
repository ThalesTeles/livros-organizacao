import tempfile
import unittest
from pathlib import Path

import nucleo
from bibliografia import ppc_markdown as pm

# Texto no formato do pdftotext: número da página sozinho + avanço de página, linhas quebradas no meio de frases.
BRUTO = """14. EMENTAS
Básico Comum
MAT01142 - ÁLGEBRA LINEAR
Ementa
Matrizes. Sistemas Lineares. Espaços
Vetoriais.
Referências
Básica
BOLDRINI, J. L. et al. Álgebra Linear. Editora Harper & How do Brasil Ltda.: São
Paulo, 1984.
STEINBRUCH, A.; WINTERLE, P. Álgebra Linear. Makron Books do Brasil Ltda.
São Paulo, 2000.
Complementar
COELHO, A.C e LOURENÇO, M.M. Um Curso de Álgebra Linear, São Paulo, 2
Ed, Edusp, 2007
POOLE, D, Álgebra Linear, São Paulo, Cengage Learning, 2012.
61

\fMAT01120 - CÁLCULO I
Ementa
Limites e Continuidade.
Referências
Básica
HINES, W. W.; MONTGOMERY, D. C..
Probabilidade e Estatística na Engenharia. 4ª Edição, LTC, 2006.
APOSTOL, T.M. Calculus Vol.2: Muti-Variable Calculus, John Wiley &
62

\fSons, New York, 2006.
Complementar
Patterns in Java. Mark Grand. John Wiley & Sons. 1999
Applying UML and Patterns. Craig Larman. Prentice Hall. 1997
MACHADO, Anna Rachel. Resumo – Leitura e Produção. São Paulo: Parábola
Editorial, 2004.
__________________________________________________________ Resenha –
leitura e produção. São Paulo: Parábola Editorial, 2004.
PEDRINI,H. Análise de Imagens. Thomson, 2008.Livro texto:
lHEARN, D., BAKER, P. Computer Graphics. Prentice-
Hall, 1997.
Complementar Eletivo
CPT01106 - TÓPICOS ESPECIAIS EM BANCO DE DADOS
Ementa
A ser definida por professores.
Referências
A ser definida por professores na época de sua oferta.
CPT01113 - TÓPICOS ESPECIAIS EM COMPUTAÇÃO
Ementa
A ser definida por professores.
Referências
A ser definida por professores na época de sua oferta.
63
"""


def _entradas(md: str, codigo: str, secao: str):
    bloco = md.split(f"## {codigo}")[1].split("\n## ")[0]
    trecho = bloco.split(f"**{secao}:**")[1].split("**")[0]
    return [l[2:] for l in trecho.splitlines() if l.startswith("- ")]


class TestLimpeza(unittest.TestCase):
    def test_remove_numeros_de_pagina_e_avanco_de_pagina(self):
        linhas = pm.limpar(BRUTO)
        self.assertNotIn("61", linhas)
        self.assertNotIn("62", linhas)
        self.assertFalse(any("\f" in l for l in linhas))

    def test_numero_que_nao_e_pagina_fica(self):
        self.assertIn("41", pm.remover_numeros_de_pagina(["61", "x", "41", "62"]))

    def test_correcoes_explicitas(self):
        linhas = pm.limpar("distribuídosSoftware e Computação.São Paulo")
        self.assertEqual(linhas[0], "distribuídos. Software e Computação. São Paulo")


class TestReferencias(unittest.TestCase):
    def setUp(self):
        self.md = pm.converter(BRUTO)

    def test_junta_linhas_quebradas(self):
        basica = _entradas(self.md, "MAT01142", "Básica")
        self.assertEqual(len(basica), 2)
        self.assertTrue(basica[0].endswith("São Paulo, 1984."))

    def test_edicao_truncada_nao_separa(self):
        comp = _entradas(self.md, "MAT01142", "Complementar")
        self.assertEqual(len(comp), 2)
        self.assertIn("2 Ed, Edusp, 2007", comp[0])

    def test_linha_so_com_autores_continua_no_titulo(self):
        basica = _entradas(self.md, "MAT01120", "Básica")
        self.assertTrue(basica[0].startswith("HINES, W. W.; MONTGOMERY, D. C.. Probabilidade"))

    def test_quebra_de_pagina_no_meio_da_referencia(self):
        basica = _entradas(self.md, "MAT01120", "Básica")
        self.assertEqual(len(basica), 2)
        self.assertIn("John Wiley & Sons, New York, 2006.", basica[1])

    def test_referencia_sem_ponto_final_termina_no_ano(self):
        comp = _entradas(self.md, "MAT01120", "Complementar")
        self.assertTrue(comp[0].endswith("1999"))
        self.assertTrue(comp[1].startswith("Applying UML"))

    def test_mesmos_autores_livro_texto_e_letra_solta(self):
        comp = _entradas(self.md, "MAT01120", "Complementar")
        self.assertIn("[mesmos autores] Resenha – leitura e produção.", comp[3])
        self.assertIn("Livro texto:", comp)
        self.assertTrue(any(c.startswith("HEARN, D., BAKER, P.") and "Prentice-Hall" in c for c in comp))


class TestEstrutura(unittest.TestCase):
    def test_grupos_e_titulos(self):
        md = pm.converter(BRUTO)
        self.assertIn("# 14. EMENTAS", md)
        self.assertIn("# Básico Comum", md)
        self.assertIn("## MAT01142 - ÁLGEBRA LINEAR", md)
        self.assertIn("**Ementa:** Matrizes. Sistemas Lineares. Espaços Vetoriais.", md)

    def test_agrupa_disciplinas_identicas(self):
        md = pm.converter(BRUTO)
        self.assertEqual(md.count("**Ementa:** A ser definida"), 1)
        self.assertIn("## CPT01106 - TÓPICOS ESPECIAIS EM BANCO DE DADOS\n## CPT01113 - TÓPICOS ESPECIAIS EM COMPUTAÇÃO", md)
        self.assertEqual(pm.converter(BRUTO, agrupar=False).count("**Ementa:** A ser definida"), 2)

    def test_so_referencias_omite_ementas(self):
        md = pm.converter(BRUTO, so_referencias=True)
        self.assertNotIn("Ementa", md)
        self.assertIn("BOLDRINI", md)


class TestVerificacao(unittest.TestCase):
    def test_conversao_nao_perde_nada(self):
        self.assertEqual(pm.verificar_preservacao(BRUTO, pm.converter(BRUTO, agrupar=False)), [])

    def test_detecta_texto_perdido(self):
        md = pm.converter(BRUTO, agrupar=False).replace("Makron Books do Brasil Ltda. ", "")
        self.assertTrue(pm.verificar_preservacao(BRUTO, md))

    def test_detecta_texto_acrescentado(self):
        md = pm.converter(BRUTO, agrupar=False) + "\nlinha a mais\n"
        self.assertTrue(pm.verificar_preservacao(BRUTO, md))


class TestIntegracaoComNucleo(unittest.TestCase):
    def test_texto_ppc_le_markdown_direto(self):
        with tempfile.TemporaryDirectory() as d:
            arq = Path(d) / "ementa.md"
            arq.write_text("# 14. EMENTAS\nconteúdo", encoding="utf-8")
            self.assertEqual(nucleo.texto_ppc(arq, ""), "# 14. EMENTAS\nconteúdo")


if __name__ == "__main__":
    unittest.main()
