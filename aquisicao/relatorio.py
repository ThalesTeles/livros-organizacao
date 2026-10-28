"""Relatório em Markdown e CSV do que foi encontrado."""
from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path
from typing import Sequence

from .modelos import Acesso, Resultado

ROTULO = {"basica": "básica", "complementar": "complementar"}


def _quem(r: Resultado) -> str:
    tipos = " + ".join(ROTULO.get(t, t) for t in r.obra.tipos)
    discs = ", ".join(r.obra.disciplinas)
    return f"{tipos}: {discs}" if discs else tipos


def _bloco(r: Resultado, mostrar_links: bool) -> list[str]:
    o = r.obra
    linhas = [f"- [ ] **{o.titulo}**" + (f" — {o.autores}" if o.autores else ""), f"  - para: {_quem(r)}"]
    if r.baixado_em:
        linhas.append(f"  - **baixado** em `{r.baixado_em}`")
    for a in r.achados:
        extra = f" — {a.obs}" if a.obs else ""
        linhas.append(f"  - {a.fonte}: [{a.titulo}]({a.url}){extra}")
    if mostrar_links:
        linhas.append("  - procurar/comprar: " + " · ".join(f"[{n}]({u})" for n, u in r.links.items()))
    return linhas


def renderizar_markdown(resultados: Sequence[Resultado], *, entradas: Sequence[str], consultou_fontes: bool,
                        gerado_em: datetime) -> str:
    def tem(r, ac): return bool(r.com_acesso(ac))
    livres = [r for r in resultados if tem(r, Acesso.LIVRE)]
    emprestimo = [r for r in resultados if not tem(r, Acesso.LIVRE) and tem(r, Acesso.EMPRESTIMO)]
    venda = [r for r in resultados if not tem(r, Acesso.LIVRE) and not tem(r, Acesso.EMPRESTIMO) and tem(r, Acesso.A_VENDA)]
    resto = [r for r in resultados if r not in livres and r not in emprestimo and r not in venda]
    saida = ["# Como obter os livros que faltam", "",
             f"_Gerado em {gerado_em:%d/%m/%Y %H:%M} a partir de: {', '.join(f'`{e}`' for e in entradas)}._", "",
             (f"**{len(resultados)} obras** ausentes: {len(livres)} com acesso livre · {len(emprestimo)} para emprestar · "
              f"{len(venda)} e-book à venda · {len(resto)} sem versão digital legal encontrada." if consultou_fontes else
              f"**{len(resultados)} obras** ausentes (fontes não consultadas)."), ""]
    if not consultou_fontes:
        saida += ["> Modo offline (`--sem-rede`): as fontes não foram consultadas; só os links de busca estão abaixo.", ""]
    secoes = [
        ("1. Acesso livre (domínio público / acesso aberto)", livres, False),
        ("2. Empréstimo digital (Internet Archive / Open Library)", emprestimo, True),
        ("3. E-book à venda", venda, True),
        ("4. Sem versão digital legal encontrada: comprar (inclusive usado) ou pedir em biblioteca", resto, True)]
    for titulo, grupo, links in secoes:
        saida += [f"## {titulo}", ""]
        if not grupo:
            saida += ["_Nenhum._", ""]
        for r in grupo:
            saida += _bloco(r, links)
        saida.append("")
    saida += ["---", "Dica: pergunte à biblioteca da UEPB se há acesso a uma biblioteca virtual de e-books "
              "(muitas universidades assinam) e se ela aceita sugestões de compra; vale para os livros da seção 4."]
    return "\n".join(saida) + "\n"


def escrever_csv(caminho: Path, resultados: Sequence[Resultado]) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with open(caminho, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["titulo", "autores", "tipos", "disciplinas", "situacao", "fonte", "url", "observacao", "baixado_em"])
        for r in resultados:
            if not r.achados:
                w.writerow([r.obra.titulo, r.obra.autores, "+".join(r.obra.tipos), " | ".join(r.obra.disciplinas),
                            "sem_versao_digital_legal", "", "", "", r.baixado_em])
            for a in r.achados:
                w.writerow([r.obra.titulo, r.obra.autores, "+".join(r.obra.tipos), " | ".join(r.obra.disciplinas),
                            a.acesso.value, a.fonte, a.url_download or a.url, a.obs, r.baixado_em])


def resumo_terminal(resultados: Sequence[Resultado]) -> str:
    cont = {ac: sum(1 for r in resultados if r.com_acesso(ac)) for ac in Acesso}
    return (f"{len(resultados)} obras ausentes | livres: {cont[Acesso.LIVRE]} | empréstimo: {cont[Acesso.EMPRESTIMO]} | "
            f"e-book à venda: {cont[Acesso.A_VENDA]} | só prévia: {cont[Acesso.PREVIA]}")
