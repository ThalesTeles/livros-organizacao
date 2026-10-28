"""Leitura do acervo: transforma o livros.csv em objetos `Livro`."""
from __future__ import annotations

import csv
from pathlib import Path

import nucleo

from .modelos import COMPLEMENTAR, Equivalencia, Livro


def carregar_equivalencias(caminho: Path) -> list[Equivalencia]:
    """Lê o equivalencias.csv (colunas `pasta;obra;arquivo`; `pasta` pode ficar vazia). Arquivo ausente = nenhuma.
    Linhas em branco e as que começam com # são ignoradas."""
    caminho = Path(caminho)
    if not caminho.is_file():
        return []
    texto = caminho.read_text(encoding="utf-8-sig")
    linhas = [l for l in texto.splitlines() if l.strip() and not l.lstrip().startswith("#")]
    saida = []
    for linha in csv.DictReader(linhas, delimiter=";"):
        obra, arquivo = (linha.get("obra") or "").strip(), (linha.get("arquivo") or "").strip()
        if obra and arquivo:
            saida.append(Equivalencia(obra=obra, arquivo=arquivo, pasta=nucleo.slug((linha.get("pasta") or "").strip())))
    return saida


def carregar_acervo(csv_path: Path) -> list[Livro]:
    """Livros não ignorados. Vínculo sem tipo conta como complementar (mesma regra do `local`)."""
    livros = []
    for linha in nucleo.ler_csv(Path(csv_path)):
        if linha["ignorar"].strip():
            continue
        vinculos = tuple((nucleo.slug(d), t or COMPLEMENTAR) for d, t in nucleo.parse_disciplinas(linha["disciplinas"]))
        livros.append(Livro(arquivo=linha["arquivo"], titulo=linha["titulo"].strip(), autor=linha["autor"].strip(),
                            edicao=linha["edicao"].strip(), vinculos=vinculos))
    return livros
