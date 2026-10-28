"""
Download do que as fontes marcam como LIVRE (domínio público / acesso aberto) e SÓ disso.

- Vai para uma pasta de quarentena, nunca direto para `livros/` (o `novos` processaria na hora).
- Nunca sobrescreve; confere que o arquivo é mesmo um PDF; registra a origem em `baixados.csv`.
"""
from __future__ import annotations

import csv
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable, Sequence

from .fontes import USER_AGENT
from .modelos import Acesso, Resultado
from .texto import primeiro_sobrenome, slug

BuscarBytes = Callable[[str], bytes]


def buscar_bytes_http(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read()


def nome_do_arquivo(titulo: str, autores: str) -> str:
    return f"{slug(titulo)[:90]}_{primeiro_sobrenome(autores) or 'sem-autor'}.pdf"


def baixar_livres(resultados: Sequence[Resultado], pasta: Path, buscar_bytes: BuscarBytes = buscar_bytes_http,
                  avisar: Callable[[str], None] = lambda *_: None) -> int:
    """Devolve quantos arquivos foram baixados."""
    pasta.mkdir(parents=True, exist_ok=True)
    registro = pasta / "baixados.csv"
    novo = not registro.exists()
    baixados = 0
    with open(registro, "a", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        if novo:
            w.writerow(["arquivo", "titulo", "fonte", "url_origem", "observacao"])
        for r in resultados:
            for a in r.com_acesso(Acesso.LIVRE):
                if not a.url_download:
                    continue
                destino = pasta / nome_do_arquivo(r.obra.titulo, r.obra.autores)
                if destino.exists():
                    avisar(f"  já existe, pulando: {destino.name}")
                    r.baixado_em = str(destino)
                    break
                try:
                    dados = buscar_bytes(a.url_download)
                except (urllib.error.URLError, TimeoutError, OSError) as e:
                    avisar(f"  falhou ({a.fonte}): {r.obra.titulo[:50]}: {e}")
                    continue
                if not dados.lstrip()[:5].startswith(b"%PDF"):
                    avisar(f"  não é PDF ({a.fonte}): {r.obra.titulo[:50]}; ignorado")
                    continue
                destino.write_bytes(dados)
                w.writerow([destino.name, r.obra.titulo, a.fonte, a.url_download, a.obs])
                r.baixado_em = str(destino)
                baixados += 1
                avisar(f"  baixado: {destino.name}")
                break
    return baixados
