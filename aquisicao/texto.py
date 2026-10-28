"""Normalização e comparação de títulos/autores. Funções puras."""
from __future__ import annotations

import re
import unicodedata

PALAVRAS_VAZIAS = frozenset("a o as os um uma de da do das dos e em no na nos nas para por com sem ao aos "
                            "the of and to for in on an with et y le la".split())
NAO_E_NOME = frozenset("edicao edition ed ed. et al org vol volume oitava quinta quarta terceira segunda primeira "
                       "sexta setima nona decima".split())


def normalizar(texto: str) -> str:
    t = unicodedata.normalize("NFKD", texto or "")
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", t.lower()).strip()


def slug(texto: str) -> str:
    return normalizar(texto).replace(" ", "-")


def tokens_titulo(texto: str) -> frozenset[str]:
    return frozenset(t for t in normalizar(texto).split() if t not in PALAVRAS_VAZIAS and not t.isdigit())


def similaridade_titulo(a: str, b: str) -> float:
    ta, tb = tokens_titulo(a), tokens_titulo(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def nomes_de_autores(autores: str) -> frozenset[str]:
    """Palavras que podem ser sobrenome (≥3 letras). O PPC escreve autores de muitos jeitos; qualquer palavra serve."""
    return frozenset(t for t in normalizar(autores).split() if len(t) >= 3 and t not in NAO_E_NOME and not t.isdigit())


def primeiro_sobrenome(autores: str) -> str:
    """Primeira palavra de ≥4 letras: 'T. H. CORMEN, C. E. LEISERSON' -> 'cormen'; 'MASIERO, Paulo' -> 'masiero'."""
    for t in normalizar(autores).split():
        if len(t) >= 4 and t not in NAO_E_NOME and not t.isdigit():
            return t
    return ""


def mesma_obra(titulo_a: str, autores_a: str, titulo_b: str, autores_b: str, limiar: float = 0.6) -> bool:
    """Título parecido E (se os dois lados têm autores) pelo menos um nome em comum."""
    if similaridade_titulo(titulo_a, titulo_b) < limiar:
        return False
    na, nb = nomes_de_autores(autores_a), nomes_de_autores(autores_b)
    return not na or not nb or bool(na & nb)
