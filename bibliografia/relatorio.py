"""Saídas: relatório em Markdown (para ler e marcar), CSV (para planilha) e resumo no terminal."""
from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path
from typing import Sequence

from .casamento import sobrenomes_do_ppc
from .modelos import ROTULO_LIVRO, ROTULO_TIPO, Obra, RelatorioDisciplina, Resultado, Situacao


def termo_de_busca(obra: Obra) -> str:
    """Texto para procurar a obra na biblioteca da universidade, no catálogo ou numa loja."""
    sobrenomes = sorted(sobrenomes_do_ppc(obra.autores))[:2]
    partes = [obra.titulo, " ".join(s.title() for s in sobrenomes)]
    if obra.edicao:
        partes.append(f"{obra.edicao} edição" if obra.edicao.isdigit() else obra.edicao)
    return " ".join(p for p in partes if p)


def sugestao_de_ajuste(r: Resultado, pasta: str, tipo: str) -> str:
    if r.livro is None:
        return ""
    if r.por_autor:
        return "contado pelos autores (título diferente): confira se é a mesma obra"
    if r.situacao is Situacao.TIPO_DIFERENTE:
        atual = r.livro.tipo_em(pasta)
        return f"em `{r.livro.arquivo}`: trocar `{pasta}:{atual}` por `{pasta}:{tipo}` na coluna disciplinas"
    if r.situacao is Situacao.SEM_VINCULO:
        return f"em `{r.livro.arquivo}`: acrescentar `|{pasta}:{tipo}` à coluna disciplinas"
    return ""


def _contagens(relatorios: Sequence[RelatorioDisciplina]) -> dict[str, int]:
    todos = [r for rel in relatorios for r in rel.resultados]
    return {
        "obras": len(todos),
        "ok": sum(r.situacao is Situacao.OK for r in todos),
        "ajustes": sum(r.situacao in (Situacao.TIPO_DIFERENTE, Situacao.SEM_VINCULO) for r in todos),
        "ausentes": sum(r.situacao is Situacao.AUSENTE for r in todos),
    }


def _linha_ausente(r: Resultado) -> list[str]:
    linhas = [f"- [ ] **{r.obra.titulo}**" + (f" — {r.obra.autores}" if r.obra.autores else "")
              + (f", {r.obra.edicao}ª ed." if r.obra.edicao.isdigit() else (f", {r.obra.edicao}" if r.obra.edicao else ""))
              + (f" ({r.obra.ano})" if r.obra.ano else ""),
              f"  - buscar: `{termo_de_busca(r.obra)}`"]
    for livro in r.possiveis:
        linhas.append(f"  - talvez já tenha (mesmos autores, outro título): `{livro.arquivo}`")
    return linhas


def renderizar_markdown(tipo: str, relatorios: Sequence[RelatorioDisciplina], *, ppc: str, total_acervo: int,
                        gerado_em: datetime) -> str:
    rotulo = ROTULO_TIPO[tipo]
    livro_rotulo = ROTULO_LIVRO[tipo]
    c = _contagens(relatorios)
    saida = [f"# Livros faltantes — bibliografia {rotulo}", "",
             f"_Gerado em {gerado_em:%d/%m/%Y %H:%M} a partir de `{ppc}`. Acervo: {total_acervo} livros._", "",
             f"**{c['obras']} obras** no PPC: {c['ok']} já no acervo e vinculadas · {c['ajustes']} no acervo, mas "
             f"com vínculo a ajustar no CSV · **{c['ausentes']} ausentes**.", "",
             "## Resumo por disciplina", "",
             f"| Disciplina | Obras no PPC | OK | Ajustar CSV | Ausentes | Livros {livro_rotulo} no acervo |",
             "|---|---:|---:|---:|---:|---:|"]
    for rel in relatorios:
        marca = "" if rel.tem_pasta else " ⚠ sem pasta local"
        saida.append(f"| {rel.nome} (`{rel.pasta}`){marca} | {len(rel.resultados)} | {len(rel.prontos)} | "
                     f"{len(rel.ajustes)} | {len(rel.ausentes)} | {rel.no_acervo} |")

    vazias = [rel for rel in relatorios if rel.no_acervo == 0 and rel.ausentes]
    outras = [rel for rel in relatorios if rel.no_acervo > 0 and rel.ausentes]
    saida += ["", f"## 1. Disciplinas sem nenhum livro {livro_rotulo} no acervo (prioridade)", ""]
    if not vazias:
        saida += [f"_Nenhuma: todas as disciplinas com obras {rotulo} no PPC têm ao menos um livro vinculado._", ""]
    for rel in vazias:
        saida += [f"### {rel.nome} (`{rel.pasta}`)" + ("" if rel.tem_pasta else "  ⚠ ainda não existe pasta local"), ""]
        for r in rel.ausentes:
            saida += _linha_ausente(r)
        saida.append("")

    saida += [f"## 2. Outras obras {rotulo} ausentes (a disciplina já tem algum livro)", ""]
    if not outras:
        saida += ["_Nenhuma._", ""]
    for rel in outras:
        saida += [f"### {rel.nome} (`{rel.pasta}`) — {rel.no_acervo} no acervo", ""]
        for r in rel.ausentes:
            saida += _linha_ausente(r)
        saida.append("")

    saida += ["## 3. Já estão no acervo, mas o vínculo precisa de ajuste no CSV", ""]
    ajustes = [(rel, r) for rel in relatorios for r in rel.ajustes]
    if not ajustes:
        saida.append("_Nenhum._")
    for rel, r in ajustes:
        saida.append(f"- [ ] **{r.obra.titulo}** ({rel.nome}): {sugestao_de_ajuste(r, rel.pasta, rel.tipo)}")

    por_autor = [(rel, r) for rel in relatorios for r in rel.resultados if r.por_autor]
    if por_autor:
        saida += ["", "## 3b. Contados como presentes pelos autores (título diferente: tradução? confira)", ""]
        for rel, r in por_autor:
            saida.append(f"- [ ] **{r.obra.titulo}** ({rel.nome}): o acervo tem `{r.livro.arquivo}`, dos mesmos "
                         "autores e já vinculado. Se não for a mesma obra, ela está faltando.")

    edicoes = [(rel, r) for rel in relatorios for r in rel.resultados
               if r.outra_edicao and r.situacao is not Situacao.AUSENTE]
    if edicoes:
        saida += ["", "## 4. Edição diferente da citada no PPC (conta como presente; confira se serve)", ""]
        for rel, r in edicoes:
            saida.append(f"- {r.obra.titulo} ({rel.nome}): PPC cita {r.obra.edicao or '?'}, "
                         f"acervo tem `{r.livro.arquivo}`")

    sem_obras = [rel for rel in relatorios if not rel.resultados]
    if sem_obras:
        saida += ["", f"## 5. Disciplinas do PPC sem bibliografia {rotulo} listada", ""]
        saida += [f"- {rel.nome} (`{rel.pasta}`)" for rel in sem_obras]
    return "\n".join(saida) + "\n"


def escrever_csv(caminho: Path, tipo: str, relatorios: Sequence[RelatorioDisciplina]) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with open(caminho, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["disciplina", "pasta", "tipo", "titulo", "autores", "edicao", "situacao",
                    "livro_no_acervo", "termo_de_busca", "sugestao"])
        for rel in relatorios:
            for r in rel.resultados:
                w.writerow([rel.nome, rel.pasta, tipo, r.obra.titulo, r.obra.autores, r.obra.edicao, r.situacao.value,
                            r.livro.arquivo if r.livro else "", termo_de_busca(r.obra),
                            sugestao_de_ajuste(r, rel.pasta, tipo)])


def resumo_terminal(tipo: str, relatorios: Sequence[RelatorioDisciplina]) -> str:
    c = _contagens(relatorios)
    linhas = [f"Bibliografia {ROTULO_TIPO[tipo]}: {c['obras']} obras no PPC | {c['ok']} ok | "
              f"{c['ajustes']} a ajustar no CSV | {c['ausentes']} ausentes", ""]
    for rel in sorted(relatorios, key=lambda r: (r.no_acervo > 0, -len(r.ausentes), r.pasta)):
        if not rel.resultados:
            continue
        linhas.append(f"  {rel.pasta:55} acervo={rel.no_acervo:<2} ok={len(rel.prontos)}/{len(rel.resultados)}"
                      f"  ajustar={len(rel.ajustes)}  ausentes={len(rel.ausentes)}")
    return "\n".join(linhas)
