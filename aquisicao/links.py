"""Links de busca para comprar (inclusive usado) e procurar em bibliotecas. Só monta URLs: nada é raspado."""
from __future__ import annotations

import urllib.parse

from .modelos import ObraFaltante
from .texto import primeiro_sobrenome


def termo(obra: ObraFaltante) -> str:
    if obra.consulta:
        return obra.consulta
    return " ".join(p for p in (obra.titulo, primeiro_sobrenome(obra.autores)) if p)


def links_de_busca(obra: ObraFaltante) -> dict[str, str]:
    q = urllib.parse.quote_plus(termo(obra))
    return {
        "Estante Virtual (usado)": f"https://www.estantevirtual.com.br/busca?q={q}",
        "Amazon Brasil": f"https://www.amazon.com.br/s?k={q}",
        "Google Livros": f"https://www.google.com/search?tbm=bks&q={q}",
        "Open Library": f"https://openlibrary.org/search?q={q}",
        "Internet Archive": f"https://archive.org/search?query={q}",
        "WorldCat (bibliotecas)": f"https://search.worldcat.org/search?q={q}",
    }
