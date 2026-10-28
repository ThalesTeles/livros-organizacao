"""Lê os relatórios `faltantes-*.csv` / `faltantes-*.md` e devolve as obras AUSENTES, sem repetição."""
from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Sequence

from .modelos import ObraFaltante
from .texto import normalizar


def _tipo_do_md(primeira_linha: str) -> str:
    return "basica" if "básica" in primeira_linha.lower() or "basica" in normalizar(primeira_linha).split() else "complementar"


def ler_csv(caminho: Path) -> list[ObraFaltante]:
    obras = []
    with open(caminho, newline="", encoding="utf-8-sig") as f:
        for linha in csv.DictReader(f, delimiter=";"):
            if (linha.get("situacao") or "").strip() != "ausente":
                continue
            titulo = (linha.get("titulo") or "").strip()
            if not titulo:
                continue
            obras.append(ObraFaltante(
                titulo=titulo, autores=(linha.get("autores") or "").strip(), edicao=(linha.get("edicao") or "").strip(),
                consulta=(linha.get("termo_de_busca") or "").strip(),
                disciplinas=((linha.get("disciplina") or "").strip(),), tipos=((linha.get("tipo") or "").strip(),)))
    return obras


ITEM_MD = re.compile(r"^- \[[ xX]\] \*\*(?P<titulo>.+?)\*\*(?: — (?P<resto>.*))?$")
DISCIPLINA_MD = re.compile(r"^### (?P<nome>.+?)(?: \(`[^`]*`\))?(?: — .*)?(?:\s+⚠.*)?$")
BUSCAR_MD = re.compile(r"^\s*- buscar: `(?P<termo>.+)`\s*$")


def ler_md(caminho: Path) -> list[ObraFaltante]:
    """Só as seções 1 e 2 (obras ausentes). As demais (3, 3b, 4, 5) falam de livros que já estão no acervo."""
    linhas = Path(caminho).read_text(encoding="utf-8").splitlines()
    tipo = _tipo_do_md(linhas[0]) if linhas else "basica"
    secao, disciplina, obras, pendente = "", "", [], None

    def fechar():
        nonlocal pendente
        if pendente:
            obras.append(ObraFaltante(**pendente))
            pendente = None

    for linha in linhas[1:]:
        m = re.match(r"^## (\d+)b?\.", linha)
        if m or linha.startswith("## "):
            fechar()
            secao = m.group(1) if m else ""
            continue
        if secao not in ("1", "2"):
            continue
        if linha.startswith("### "):
            fechar()
            disciplina = (DISCIPLINA_MD.match(linha).group("nome") if DISCIPLINA_MD.match(linha) else linha[4:]).strip()
            continue
        item = ITEM_MD.match(linha)
        if item:
            fechar()
            resto = re.sub(r"\s*\(\d{4}\)\s*$", "", item.group("resto") or "").strip()
            pendente = dict(titulo=item.group("titulo").strip(), autores=resto, consulta="",
                            disciplinas=(disciplina,), tipos=(tipo,))
            continue
        b = BUSCAR_MD.match(linha)
        if b and pendente:
            pendente["consulta"] = b.group("termo")
    fechar()
    return obras


def ler_faltantes(caminhos: Sequence[Path]) -> list[ObraFaltante]:
    """Junta vários relatórios; a mesma obra em várias disciplinas/tipos vira uma só. Básicas primeiro."""
    todas: list[ObraFaltante] = []
    for c in map(Path, caminhos):
        if not c.is_file():
            raise FileNotFoundError(f"Relatório não encontrado: {c}")
        sufixo = c.suffix.lower()
        if sufixo == ".csv":
            todas += ler_csv(c)
        elif sufixo in (".md", ".markdown"):
            todas += ler_md(c)
        else:
            raise ValueError(f"Formato não suportado (use .csv ou .md): {c}")
    por_chave: dict[str, ObraFaltante] = {}
    for o in todas:
        chave = normalizar(o.titulo)
        antiga = por_chave.get(chave)
        if antiga is None:
            por_chave[chave] = o
        else:
            por_chave[chave] = ObraFaltante(
                titulo=antiga.titulo, autores=antiga.autores or o.autores, edicao=antiga.edicao or o.edicao,
                consulta=antiga.consulta or o.consulta,
                disciplinas=tuple(dict.fromkeys(antiga.disciplinas + o.disciplinas)),
                tipos=tuple(dict.fromkeys(antiga.tipos + o.tipos)))
    return sorted(por_chave.values(), key=lambda o: (o.prioridade, normalizar(o.titulo)))
