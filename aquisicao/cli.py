"""python3 -m aquisicao relatorios/faltantes-basica.csv relatorios/faltantes-complementar.csv"""
from __future__ import annotations

import argparse
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional, Sequence

from . import relatorio
from .baixar import BuscarBytes, baixar_livres, buscar_bytes_http
from .entrada import ler_faltantes
from .fontes import BuscarJson, GoogleLivros, OpenLibrary, buscar_json_http
from .links import links_de_busca
from .modelos import Resultado


def montar_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python3 -m aquisicao",
        description="Mostra como obter, de forma legítima, os livros que faltam (relatórios do pacote `bibliografia`).")
    p.add_argument("entradas", nargs="+", help="faltantes-basica.csv/.md e/ou faltantes-complementar.csv/.md")
    p.add_argument("--saida", default="relatorios", help="pasta do relatório (padrão: relatorios)")
    p.add_argument("--sem-rede", action="store_true", help="não consulta as fontes; só gera os links de busca")
    p.add_argument("--baixar", action="store_true",
                   help="baixa os livros de acesso livre (domínio público/acesso aberto) para a pasta de quarentena")
    p.add_argument("--quarentena", default="aquisicao-baixados",
                   help="pasta dos downloads (padrão: aquisicao-baixados; revise e mova você mesmo para livros/)")
    p.add_argument("--pausa", type=float, default=1.0, help="segundos entre consultas (padrão 1)")
    p.add_argument("--limite", type=int, default=0, help="só as N primeiras obras (teste)")
    return p


def main(argv: Optional[Sequence[str]] = None, *, buscar_json: BuscarJson = buscar_json_http,
         buscar_bytes: BuscarBytes = buscar_bytes_http, agora: Optional[datetime] = None,
         dormir: Callable[[float], None] = time.sleep) -> int:
    args = montar_parser().parse_args(argv)
    obras = ler_faltantes([Path(e).expanduser() for e in args.entradas])
    if args.limite:
        obras = obras[:args.limite]
    fontes = [] if args.sem_rede else [OpenLibrary(buscar_json), GoogleLivros(buscar_json)]

    resultados = []
    for n, obra in enumerate(obras, 1):
        r = Resultado(obra=obra, links=links_de_busca(obra))
        for fonte in fontes:
            try:
                r.achados += fonte.buscar(obra)
            except ConnectionError as e:
                print(f"  aviso ({fonte.nome}): {str(e)[:120]}")
            dormir(args.pausa)
        resultados.append(r)
        print(f"[{n}/{len(obras)}] {obra.titulo[:60]}: " + (", ".join(sorted({a.acesso.value for a in r.achados})) or "-"))

    if args.baixar and not args.sem_rede:
        n = baixar_livres(resultados, Path(args.quarentena).expanduser(), buscar_bytes, avisar=print)
        print(f"{n} arquivo(s) baixado(s) em {args.quarentena}/ (só acesso livre). Revise e mova para livros/ se quiser.")

    saida = Path(args.saida).expanduser()
    saida.mkdir(parents=True, exist_ok=True)
    md, planilha = saida / "aquisicao.md", saida / "aquisicao.csv"
    md.write_text(relatorio.renderizar_markdown(resultados, entradas=[Path(e).name for e in args.entradas],
                                                consultou_fontes=not args.sem_rede, gerado_em=agora or datetime.now()),
                  encoding="utf-8")
    relatorio.escrever_csv(planilha, resultados)
    print("\n" + relatorio.resumo_terminal(resultados) + f"\nRelatório: {md}\nPlanilha:  {planilha}")
    return 0
