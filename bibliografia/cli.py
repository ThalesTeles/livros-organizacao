"""Linha de comando: monta as peças (injeção de dependências) e executa uma análise de um tipo."""
from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional, Sequence

import nucleo

from . import relatorio
from .acervo import carregar_acervo, carregar_equivalencias
from .analise import AnalisadorDeLacunas
from .modelos import ROTULO_LIVRO, ROTULO_TIPO, TIPOS
from .ppc import ExtratorClaude, ExtratorDeBibliografia, criar_cliente_anthropic, ler_texto_ppc


def montar_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python3 -m bibliografia",
        description="Procura no PPC os livros que ainda faltam no acervo. Um tipo de cada vez.")
    sub = p.add_subparsers(dest="tipo", required=True, metavar="{basica,complementar}")
    for tipo in TIPOS:
        sp = sub.add_parser(tipo, help=f"lacunas da bibliografia {ROTULO_TIPO[tipo]}")
        sp.add_argument("--ppc", default=str(nucleo.PPC_PADRAO),
                        help="PDF ou Markdown do PPC (para analisar só a bibliografia, use o .md gerado com --so-referencias)")
        sp.add_argument("--paginas", default="", help="intervalo do PPC a ler, ex.: 40-160")
        sp.add_argument("--csv", default=str(nucleo.CSV_PADRAO), help="livros.csv (o acervo)")
        sp.add_argument("--raiz", default=str(nucleo.RAIZ_PADRAO), help="pasta com as pastas de disciplina")
        sp.add_argument("--saida", default=str(nucleo.META_PADRAO / "relatorios"), help="pasta dos relatórios")
        sp.add_argument("--modelo", default=nucleo.MODELO_PADRAO)
        sp.add_argument("--refazer", action="store_true", help="ignora o cache da extração do PPC")
        sp.add_argument("--disciplina", nargs="+", metavar="TEXTO",
                        help="só disciplinas cuja pasta contenha algum destes textos")
        sp.add_argument("--so-sem-livros", action="store_true",
                        help=f"só disciplinas sem nenhum livro {ROTULO_LIVRO[tipo]} no acervo")
        sp.add_argument("--equivalencias", default="",
                        help="CSV pasta;obra;arquivo com o que você decidiu que é o mesmo livro "
                             "(padrão: equivalencias.csv ao lado do livros.csv)")
        sp.add_argument("--incluir-sem-bibliografia", action="store_true",
                        help="lista também as disciplinas que o PPC não traz com bibliografia deste tipo "
                             "(estágios, TCC, tópicos especiais...); por padrão ficam de fora")
        sp.add_argument("--sem-arquivos", action="store_true", help="só mostra no terminal; não grava .md/.csv")
    return p


def main(argv: Optional[Sequence[str]] = None, *, extrator: Optional[ExtratorDeBibliografia] = None,
         leitor_ppc: Callable[[Path, str], str] = ler_texto_ppc, agora: Optional[datetime] = None) -> int:
    nucleo.carregar_env()
    args = montar_parser().parse_args(argv)
    tipo = args.tipo
    raiz, csv_path, ppc = Path(args.raiz).expanduser(), Path(args.csv).expanduser(), Path(args.ppc).expanduser()
    if not raiz.is_dir():
        raise SystemExit(f"Pasta raiz não encontrada: {raiz}")
    if not csv_path.is_file():
        raise SystemExit(f"Acervo (livros.csv) não encontrado: {csv_path}")

    cliente = None
    acervo = carregar_acervo(csv_path)
    pastas = nucleo.pastas_disciplina(raiz)
    if extrator is None:
        cliente = criar_cliente_anthropic(nucleo.caminho_cache(csv_path, "llm_estado"))
        extrator = ExtratorClaude(cliente, args.modelo,
                                  cache_path=nucleo.caminho_cache(csv_path, "bibliografia"), refazer=args.refazer,
                                  progresso=print)

    requisitos = extrator.extrair(tipo, leitor_ppc(ppc, args.paginas), pastas)
    if cliente is not None and hasattr(cliente, "resumo"):
        print(cliente.resumo())
    caminho_eq = Path(args.equivalencias).expanduser() if args.equivalencias else csv_path.with_name("equivalencias.csv")
    equivalencias = carregar_equivalencias(caminho_eq)
    analisador = AnalisadorDeLacunas(acervo, equivalencias=equivalencias)
    for aviso in analisador.avisos:
        print(f"Aviso: {aviso}")
    if equivalencias:
        print(f"{len(equivalencias)} equivalência(s) manual(is) lida(s) de {caminho_eq.name}.")
    relatorios = analisador.analisar(tipo, requisitos, pastas)
    if not args.incluir_sem_bibliografia:
        relatorios = [r for r in relatorios if r.resultados]
    if args.disciplina:
        relatorios = [r for r in relatorios if any(t in r.pasta for t in args.disciplina)]
    if args.so_sem_livros:
        relatorios = [r for r in relatorios if r.no_acervo == 0]

    print(relatorio.resumo_terminal(tipo, relatorios))
    if not args.sem_arquivos:
        saida = Path(args.saida).expanduser()
        saida.mkdir(parents=True, exist_ok=True)
        md, planilha = saida / f"faltantes-{tipo}.md", saida / f"faltantes-{tipo}.csv"
        md.write_text(relatorio.renderizar_markdown(tipo, relatorios, ppc=ppc.name, total_acervo=len(acervo),
                                                    gerado_em=agora or datetime.now()), encoding="utf-8")
        relatorio.escrever_csv(planilha, tipo, relatorios)
        print(f"\nRelatório: {md}\nPlanilha:  {planilha}")
    return 0
