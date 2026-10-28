"""Fixtures compartilhadas pelos testes."""
from bibliografia.modelos import Livro, Obra, RequisitoDisciplina

CORMEN = Livro("algoritmos-teoria-e-pratica_cormen-et-al_3.pdf", "Algoritmos: Teoria e Prática", "Cormen et al", "3",
               (("algoritmos", "basica"), ("estrutura-de-dados", "basica")))
LOGICA = Livro("logica-para-computacao_silva-et-al_1.pdf", "Lógica para Computação", "Silva et al", "1",
               (("logica-para-computacao", "complementar"),))
AHO = Livro("compiladores-principios-tecnicas-e-ferramentas_aho-et-al_2.pdf",
            "Compiladores: Princípios, Técnicas e Ferramentas", "Aho et al", "2", ())
THOMAS_V1 = Livro("calculo-vol-1_thomas-et-al_12.pdf", "Cálculo Vol. 1", "Thomas et al", "12",
                  (("calculo-1", "basica"),))
THOMAS_V2 = Livro("calculo-vol-2_thomas-et-al_12.pdf", "Cálculo Vol. 2", "Thomas et al", "12",
                  (("calculo-3", "complementar"),))
INTRO_ALG = Livro("introduction-to-algorithms_cormen-et-al_4.pdf", "Introduction to Algorithms", "Cormen et al", "4",
                  (("algoritmos", "basica"),))
ACERVO = [CORMEN, LOGICA, AHO, THOMAS_V1, THOMAS_V2, INTRO_ALG]

OBRA_CORMEN_ED2 = Obra("Algoritmos: teoria e prática", "CORMEN, Thomas H.; LEISERSON, Charles E.", "2", 2002)
OBRA_LOGICA = Obra("Lógica para Computação", "SILVA, Flávio S. C.; FINGER, Marcelo", "1")
OBRA_AHO = Obra("Compiladores: princípios, técnicas e ferramentas", "AHO, Alfred V.; LAM, Monica S.", "2")
OBRA_REDES = Obra("Redes de Computadores", "TANENBAUM, Andrew S.", "5")


def requisitos_exemplo():
    return [
        RequisitoDisciplina("algoritmos", "Algoritmos", (OBRA_CORMEN_ED2,)),
        RequisitoDisciplina("logica-para-computacao", "Lógica para Computação", (OBRA_LOGICA,)),
        RequisitoDisciplina("compiladores", "Compiladores", (OBRA_AHO,)),
        RequisitoDisciplina("redes-de-computadores", "Redes de Computadores", (OBRA_REDES,)),
        RequisitoDisciplina("ingles-instrumental", "Inglês Instrumental", ()),
    ]
