"""
Fontes que informam, nos próprios metadados, se um livro pode ser lido/baixado legalmente.

- Open Library (API pública): `ebook_access` = public | borrowable | printdisabled | no_ebook.
- Google Livros (API pública): `accessInfo.publicDomain`, `saleInfo.saleability` (FREE | FOR_SALE ...).

O acesso HTTP é injetado (`buscar_json(url) -> dict`), então tudo aqui é testável sem rede.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Callable, Optional

from .modelos import Achado, Acesso, ObraFaltante
from .texto import mesma_obra, primeiro_sobrenome

BuscarJson = Callable[[str], dict]
USER_AGENT = "livros-aquisicao/1.0 (uso pessoal; busca de livros em acesso aberto)"


def buscar_json_http(url: str, *, tentativas: int = 2, espera: float = 2.0) -> dict:
    """GET de JSON com User-Agent identificado e uma nova tentativa em erro temporário."""
    ultimo: Optional[Exception] = None
    for n in range(tentativas):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=25) as r:
                return json.loads(r.read().decode("utf-8", "replace"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            ultimo = e
            if n + 1 < tentativas:
                time.sleep(espera)
    raise ConnectionError(f"{url}: {ultimo}")


def _titulo_busca(obra: ObraFaltante) -> str:
    return obra.titulo.split(":")[0].strip() if len(obra.titulo.split()) > 8 else obra.titulo


class OpenLibrary:
    nome = "Open Library"

    def __init__(self, buscar_json: BuscarJson = buscar_json_http):
        self.buscar_json = buscar_json

    def buscar(self, obra: ObraFaltante) -> list[Achado]:
        params = {"title": _titulo_busca(obra), "limit": "6",
                  "fields": "key,title,author_name,first_publish_year,ia,ebook_access"}
        autor = primeiro_sobrenome(obra.autores)
        if autor:
            params["author"] = autor
        dados = self.buscar_json("https://openlibrary.org/search.json?" + urllib.parse.urlencode(params))
        achados = []
        for doc in dados.get("docs", []):
            acesso_ol = doc.get("ebook_access")
            ia = (doc.get("ia") or [None])[0]
            if acesso_ol not in ("public", "borrowable") or not ia:
                continue
            autores = ", ".join(doc.get("author_name") or [])
            if not mesma_obra(obra.titulo, obra.autores, doc.get("title", ""), autores):
                continue
            pagina = f"https://archive.org/details/{ia}"
            if acesso_ol == "public":
                achados.append(Achado(self.nome, Acesso.LIVRE, doc["title"], autores, pagina,
                                      url_download=f"https://archive.org/download/{ia}/{ia}.pdf",
                                      obs="acesso aberto no Internet Archive"))
            else:
                achados.append(Achado(self.nome, Acesso.EMPRESTIMO, doc["title"], autores, pagina,
                                      obs="empréstimo digital gratuito (precisa de conta no Internet Archive)"))
        return achados


class GoogleLivros:
    nome = "Google Livros"

    def __init__(self, buscar_json: BuscarJson = buscar_json_http):
        self.buscar_json = buscar_json

    def buscar(self, obra: ObraFaltante) -> list[Achado]:
        q = f'intitle:"{_titulo_busca(obra)}"'
        autor = primeiro_sobrenome(obra.autores)
        if autor:
            q += f"+inauthor:{autor}"
        url = ("https://www.googleapis.com/books/v1/volumes?" + "q=" + urllib.parse.quote(q, safe=":+\"")
               + "&maxResults=6&printType=books&country=BR")
        achados = []
        for item in self.buscar_json(url).get("items", []):
            info, acesso, venda = item.get("volumeInfo", {}), item.get("accessInfo", {}), item.get("saleInfo", {})
            titulo = " ".join(x for x in (info.get("title"), info.get("subtitle")) if x)
            autores = ", ".join(info.get("authors") or [])
            if not mesma_obra(obra.titulo, obra.autores, titulo, autores):
                continue
            pagina = info.get("infoLink") or item.get("selfLink", "")
            baixavel = (acesso.get("pdf") or {}).get("downloadLink", "")
            if (acesso.get("publicDomain") or venda.get("saleability") == "FREE") and baixavel:
                achados.append(Achado(self.nome, Acesso.LIVRE, titulo, autores, pagina, url_download=baixavel,
                                      obs="domínio público / gratuito no Google Livros"))
            elif venda.get("saleability") == "FOR_SALE" and venda.get("isEbook"):
                preco = venda.get("listPrice") or {}
                texto = f"{preco.get('currencyCode', '')} {preco.get('amount', '')}".strip()
                achados.append(Achado(self.nome, Acesso.A_VENDA, titulo, autores, venda.get("buyLink") or pagina,
                                      obs=f"e-book à venda{': ' + texto if texto else ''}"))
            elif acesso.get("viewability") in ("PARTIAL", "ALL_PAGES"):
                achados.append(Achado(self.nome, Acesso.PREVIA, titulo, autores, pagina, obs="prévia (trechos)"))
        return achados
