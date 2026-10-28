"""Casos tirados do relatório real do PPC (UEPB): falsos positivos que o casamento antigo aceitava e
casamentos legítimos que o endurecimento não pode perder."""
import unittest

from bibliografia.analise import AnalisadorDeLacunas
from bibliografia.casamento import Casador
from bibliografia.modelos import Livro, Obra, RequisitoDisciplina, Situacao


def L(arquivo, titulo, autor, edicao="", vinculos=()):
    return Livro(arquivo, titulo, autor, edicao, tuple(vinculos))


JAVA_DEITEL = L("java-como-programar_deitel-e-deitel_8.pdf", "Java: como programar", "Deitel e Deitel", "8")
REDES_TAN = L("redes-de-computadores_tanenbaum-et-al_6.pdf", "Redes de Computadores", "Tanenbaum et al", "6")
SCO = L("structured-computer-organization_tanenbaum-e-austin_6.pdf", "Structured Computer Organization",
        "Tanenbaum e Austin", "6", [("oac", "basica")])
AL_LIMA = L("algebra-linear_lima_1.pdf", "Álgebra Linear", "Lima", "1", [("algebra-linear", "basica")])
MUNEM_V1 = L("calculo-vol-1_munem-e-foulis_sem-ed.pdf", "Cálculo Vol. 1", "Munem e Foulis")
HEARN = L("computer-graphics-with-opengl_hearn-et-al_4.pdf", "Computer Graphics with OpenGL", "Hearn et al", "4")
SOUZA = L("logica-para-ciencia-da-computacao-e-areas-afins_souza_sem-ed.pdf",
          "Lógica para Ciência da Computação e Áreas Afins", "Souza")
GONCALVES = L("java-ee-6-et-glassfish-3_goncalves_sem-ed.pdf", "Java EE 6 et GlassFish 3", "Goncalves")
SOM = L("sistemas-operacionais-modernos_tanenbaum-e-bos_4.pdf", "Sistemas Operacionais Modernos", "Tanenbaum e Bos", "4")


def casa(obra, livro):
    return any(c.livro is livro for c in Casador([livro]).correspondencias(obra))


class TestFalsosPositivosDoRelatorio(unittest.TestCase):
    def test_c_como_programar_nao_e_java_como_programar(self):
        self.assertFalse(casa(Obra("C: Como Programar", "DEITEL, Paul. DEITEL, Harvey.", "6ª edição"), JAVA_DEITEL))

    def test_organizacao_estruturada_nao_e_redes(self):
        self.assertFalse(casa(Obra("Organização Estruturada de Computadores", "TANENBAUM, A. S.; AUSTIN, T.", "6"),
                              REDES_TAN))

    def test_geometria_analitica_e_algebra_linear_nao_e_algebra_linear(self):
        self.assertFalse(casa(Obra("Geometria analítica e Álgebra Linear", "LIMA, E. L."), AL_LIMA))

    def test_outro_livro_do_mesmo_autor_com_subtitulo_parecido(self):
        self.assertFalse(casa(Obra("Sistemas Operacionais: Projeto e Implementação", "TANENBAUM, A. S.; WOODHULL, A. S."),
                              SOM))


class TestCasamentosQueContinuam(unittest.TestCase):
    def test_volume_por_extenso(self):
        self.assertTrue(casa(Obra("Cálculo. Volume 1 e 2", "MUNEM, M. A. e FOULIS, D. J."), MUNEM_V1))

    def test_autor_citado_pela_metade(self):
        self.assertTrue(casa(Obra("Cálculo. Vol. 1", "FOULIS, M."), MUNEM_V1))

    def test_palavras_coladas_no_ppc(self):
        self.assertTrue(casa(Obra("Computer Graphics WithOpenGl", "HEARN, D., BAKER, M. P."), HEARN))

    def test_subtitulos_diferentes_com_os_mesmos_autores(self):
        self.assertTrue(casa(Obra("Lógica para Ciência da Computação: Uma introdução concisa", "SOUZA, JOÃO NUNUS DE"),
                             SOUZA))

    def test_edicao_em_outro_idioma(self):
        self.assertTrue(casa(Obra("Beginning Java EE 6 Platform with GlassFish 3: From Novice to Professional",
                                  "A. Goncalves"), GONCALVES))


class TestTraducaoJaVinculada(unittest.TestCase):
    OBRA = Obra("Organização Estruturada de Computadores", "TANENBAUM, A. S.; AUSTIN, T.", "6")

    def _resultado(self, acervo, obras, tipo="basica"):
        rel = AnalisadorDeLacunas(acervo).analisar(tipo, [RequisitoDisciplina("oac", "OAC", tuple(obras))])[0]
        return rel.resultados

    def test_original_em_ingles_vinculado_conta_como_presente(self):
        r = self._resultado([SCO, REDES_TAN], [self.OBRA])[0]
        self.assertIs(r.situacao, Situacao.OK)
        self.assertIs(r.livro, SCO)
        self.assertTrue(r.por_autor)

    def test_nao_vale_para_outro_tipo(self):
        r = self._resultado([SCO], [self.OBRA], tipo="complementar")[0]
        self.assertIs(r.situacao, Situacao.AUSENTE)

    def test_livro_ja_usado_por_outra_obra_nao_e_reaproveitado(self):
        obra_sco = Obra("Structured Computer Organization", "TANENBAUM, A. S.; AUSTIN, T.", "6")
        resultados = self._resultado([SCO], [obra_sco, self.OBRA])
        self.assertIs(resultados[0].situacao, Situacao.OK)
        self.assertFalse(resultados[0].por_autor)
        self.assertIs(resultados[1].situacao, Situacao.AUSENTE)

    def test_exige_pelo_menos_metade_dos_autores_do_livro(self):
        # caso real: o PPC cita 'Adobe Flex 4 Training' (Labriola); o acervo tem 'Adobe Flex 4.5 Fundamentals'
        # (Labriola, Tapper e Boles), outro livro, vinculado como básica: 1 de 3 autores não basta
        flex45 = L("adobe-flex-4-5-fundamentals_labriola-tapper-e-boles_sem-ed.pdf", "Adobe Flex 4.5 Fundamentals",
                   "Labriola, Tapper e Boles", "", [("oac", "basica")])
        r = self._resultado([flex45], [Obra("Adobe Flex 4 Training from the Source V1", "LABRIOLA, M.")])[0]
        self.assertIs(r.situacao, Situacao.AUSENTE)


LEITHOLD_V1 = L("o-calculo-com-geometria-analitica-vol-1_leithold_3.pdf", "O Cálculo com Geometria Analítica Vol. 1",
                "Leithold", "3")
SWOKOWSKI_V1 = L("calculo-com-geometria-analitica-vol-1_swokowski_2.pdf", "Cálculo com Geometria Analítica Vol. 1",
                 "Swokowski", "2")
LOGICA_SILVA = L("logica-para-computacao_silva-et-al_1.pdf", "Lógica para Computação", "Silva et al", "1")
PRESSMAN = L("engenharia-de-software_pressman_7.pdf", "Engenharia de Software", "Pressman", "7")
PMBOK = L("um-guia-do-conhecimento-em-gerenciamento-de-projetos-guia-pmbok_project-management-institute_4.pdf",
          "Um Guia do Conhecimento em Gerenciamento de Projetos (Guia PMBOK)", "Project Management Institute", "4")
RUSSELL_PT = L("inteligencia-artificial_russell-e-norvig_3.pdf", "Inteligência Artificial", "Russell e Norvig", "3",
               [("ia", "basica")])


class TestAutoresComoOPPCEscreve(unittest.TestCase):
    def test_sobrenome_com_erro_de_digitacao(self):
        self.assertTrue(casa(Obra("Cálculo com Geometria Analítica. Vol. 1", "LEITHOULD, L."), LEITHOLD_V1))
        self.assertTrue(casa(Obra("Redes de Computadores", "TANEMBAUM, A."), REDES_TAN))

    def test_mesmo_titulo_de_outro_autor_continua_fora(self):
        self.assertFalse(casa(Obra("Cálculo com Geometria Analítica. Vol. 1", "LEITHOULD, L."), SWOKOWSKI_V1))

    def test_varios_autores_numa_virgula_so(self):
        self.assertTrue(casa(Obra("Lógica para computação", "FINGER, MELO E SILVA"), LOGICA_SILVA))

    def test_sobrenome_antes_do_ponto(self):
        self.assertTrue(casa(Obra("Engenharia de Software", "Pressman. Rogers"), PRESSMAN))

    def test_sigla_da_instituicao(self):
        self.assertTrue(casa(Obra("Um guia do conhecimento em gerenciamento de projetos. Guia PMBOK", "PMI"), PMBOK))

    def test_autor_sem_virgula_ainda_conta_como_autor(self):
        # 'COPPIN B.' não pode casar com o Russell só porque os títulos são iguais
        self.assertFalse(casa(Obra("Inteligência Artificial", "COPPIN B."), RUSSELL_PT))

    def test_ppc_cita_so_o_primeiro_autor_da_traducao(self):
        obras = (Obra("Artificial Intelligence: a modern approach", "RUSSELL, S."), Obra("Inteligência Artificial", "COPPIN B."))
        rel = AnalisadorDeLacunas([RUSSELL_PT]).analisar("basica", [RequisitoDisciplina("ia", "IA", obras)])[0]
        self.assertIs(rel.resultados[0].situacao, Situacao.OK)
        self.assertTrue(rel.resultados[0].por_autor)
        self.assertIs(rel.resultados[1].situacao, Situacao.AUSENTE)


if __name__ == "__main__":
    unittest.main()
