#!/usr/bin/env python3
"""
Organiza a biblioteca de livros da faculdade.

Nome padrão dos arquivos:  titulo_autor_edicao.ext
(minúsculo, sem acento, hífen dentro de cada campo e underline só entre os campos;
 sem edição o campo vira "sem-ed"). Ex.: algoritmos-teoria-e-pratica_cormen-et-al_3.pdf

Estrutura no computador
-----------------------
    ~/documents/estudos/faculdade/
    ├── livros/                       <- TODOS os livros (é aqui que você joga um livro novo)
    ├── livros-organizacao/           <- tudo que é do script (nada disso fica solto em livros/)
    │   ├── organizar_livros.py
    │   ├── livros.csv                <- planilha mestra (arquivo;disciplinas;titulo;autor;edicao;...)
    │   ├── cache/                    <- livros.ia_cache.json, livros.ppc_cache.json
    │   └── backups/                  <- cópias automáticas do CSV (as 10 últimas)
    └── <disciplina>/
        └── livros/
            ├── basica/               <- links simbólicos: bibliografia BÁSICA do PPC
            └── complementar/         <- links simbólicos: bibliografia complementar (e o que não consta no PPC)

Estrutura no Drive (comando `drive`, sem pasta intermediária no computador)
--------------------------------------------------------------------------
    faculdade/                        <- o destino que você passa em --rclone (ex.: gdrive:faculdade)
    ├── livros/                       <- arquivos reais, enviados direto de faculdade/livros
    └── <disciplina>/{basica,complementar}/<livro>     <- ATALHOS do Drive para livros/<livro>
Os atalhos são criados com `rclone backend shortcut`: não ocupam espaço extra e acompanham o arquivo
se ele for renomeado ou movido no Drive.

Coluna `disciplinas` do CSV: nomes separados por |, cada um com tipo opcional:
    algoritmos:basica|estrutura-de-dados:complementar|logica-para-computacao
Sem tipo = ainda não classificado; é tratado como complementar até o comando `ppc` classificar.

Valores padrão (todos podem ser trocados por opções de linha de comando):
    raiz    = $LIVROS_RAIZ ou ~/documents/estudos/faculdade
    livros  = <raiz>/livros
    csv     = <raiz>/livros-organizacao/livros.csv        (caches e backups ficam ao lado dele)
    ppc     = <raiz>/informacoes-do-curso/ementa.pdf
    rclone  = $LIVROS_RCLONE (ex.: gdrive:faculdade; sem isso nada é enviado ao Drive)

Comandos (sempre teste com --simular antes)
-------------------------------------------
  manifesto  gera o CSV a partir dos links simbólicos que já existem (não sobrescreve sem --forcar):
               python3 organizar_livros.py manifesto
  ia         preenche titulo/autor/edicao lendo as primeiras páginas com a API do Claude:
               python3 organizar_livros.py ia --limite 3        # teste
  ppc        usa o PPC para (1) classificar cada livro como basica/complementar em cada disciplina
             em que ele já está e (2) propor disciplinas para livros que ainda não têm nenhuma.
             O que o PPC não lista é complementar. --mesclar deixa o modelo acrescentar disciplinas a
             livros que já têm; --refazer reclassifica tudo, inclusive tipos já preenchidos:
               python3 organizar_livros.py ppc
  pastas     renomeia pastas de disciplina de underline para hífen (--todas, --incluir PASTA...).
  liberar    recalcula revisar=sim com as respostas já guardadas (sem gastar API): libera os livros que a IA e o
             PPC identificaram com confiança alta e cujas pastas existem, e diz por que os outros continuam.
               python3 organizar_livros.py liberar --simular
  reconciliar  acerta a coluna `arquivo` do CSV se você moveu livros à mão (tirou de subpastas, etc.).
               Rode antes de `local` ou `novos` sempre que mexer nos arquivos de livros/ sem o script.
  local      renomeia os livros em livros/, cria <disciplina>/livros/{basica,complementar}/ (reaproveita
             as pastas que já existem), põe os links e remove só os links velhos/quebrados dessas pastas:
               python3 organizar_livros.py local --simular
  drive      envia os livros prontos (sem revisar=sim e já renomeados) de livros/ para <remoto>/livros e cria,
             nas pastas de disciplina do Drive, um atalho por livro (cria as pastas que faltarem; nunca apaga
             livros; atalhos que já existem não são recriados). O destino vem de --rclone ou de LIVROS_RCLONE:
               python3 organizar_livros.py drive --rclone gdrive:faculdade --simular
               python3 organizar_livros.py drive --limpar-copias   # remove cópias reais de um envio antigo
             Atalhos obsoletos (livro que mudou de tipo ou disciplina, foi renomeado ou saiu do CSV) são
             removidos sozinhos; --sem-podar desliga isso. Arquivos reais em livros/ nunca são apagados.
  recolher   move para livros/ os livros REAIS (não links) que estão dentro das pastas de disciplina, em
             pastas livros/, livro/ ou livros_*/, e organiza (ia -> ppc -> local). A disciplina de onde o
             arquivo veio vira a disciplina do livro; o tipo (basica/complementar) vem do PPC. Duplicatas
             idênticas (mesmo conteúdo) de algo que já está em livros/ não são movidas.
               python3 organizar_livros.py recolher --varrer          # lista candidatos (e PDFs longos suspeitos)
               python3 organizar_livros.py recolher --simular
               python3 organizar_livros.py recolher --tudo --excluir estagio/ prova_2_ia   # tudo do --varrer, menos o excluído
               python3 organizar_livros.py recolher "paradigmas-de-programacao/x.pdf"   # arquivos escolhidos
  novos      "caixa de entrada": acha os livros jogados em livros/ que ainda não estão no CSV, identifica
             (ia), classifica pelo PPC (ppc), renomeia e linka (local) e, se pedido, atualiza o Drive:
               python3 organizar_livros.py novos --rclone gdrive:faculdade
             Livros que o modelo não identificou com segurança ficam onde estão, marcados revisar=sim
             no CSV, e você é avisado (notify-send). Corrija o CSV e rode `local`.
             Para rodar sozinho ao soltar um livro na pasta, veja livros-organizar.path/.service (systemd).

Variáveis: GEMINI_API_KEY (grátis) e/ou ANTHROPIC_API_KEY (ia, ppc, novos; veja llm.py), lidas do ambiente ou de um arquivo .env (veja carregar_env). Dependências: pdftotext (poppler) para ler PDFs; pypdf opcional.
"""
import argparse
import csv
import fcntl
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
import unicodedata
from datetime import datetime
from pathlib import Path

import llm
from nucleo import (  # código compartilhado com o pacote `bibliografia` (veja nucleo.py)
    CAMPOS, CSV_PADRAO, EXTENSOES, LIVROS_PADRAO, META_PADRAO, MODELO_PADRAO, NAO_SAO_DISCIPLINA, PPC_PADRAO,
    RAIZ_PADRAO, TIPOS, backup_csv, caminho_cache, carregar_env, disciplinas_do_csv, formatar_disciplinas,
    gravar_cache, gravar_csv, ler_cache, ler_csv, parse_disciplinas, pastas_disciplina, slug, texto_ppc, unir_pares,
)
from nucleo import rodar as _rodar


def listar_livros(livros: Path):
    return sorted(
        p for p in livros.rglob("*")
        if p.is_file() and p.suffix.lower() in EXTENSOES
        and not any(parte.startswith(".") for parte in p.relative_to(livros).parts)
    )


# ----------------------------------------------------------------------------- CSV, cache, backup

# ----------------------------------------------------------------------------- disciplinas e tipos

def descobrir_disciplinas(raiz: Path, livros: Path) -> dict:
    """Varre os links simbólicos de `raiz` e devolve {livro: [(disciplina, tipo), ...]}.
    O tipo vem da pasta (<disc>/livros/basica/...); links soltos (estrutura antiga) ficam sem tipo."""
    mapa = {}
    livros = livros.resolve()
    for atual, dirs, arquivos in os.walk(raiz, followlinks=False):
        for nome in dirs + arquivos:
            caminho = Path(atual) / nome
            if not caminho.is_symlink():
                continue
            alvo = caminho.resolve()
            if livros in alvo.parents or alvo == livros:
                partes = caminho.relative_to(raiz).parts
                tipo = slug(partes[2]) if len(partes) >= 4 and partes[1] == "livros" else ""
                mapa.setdefault(alvo, []).append((partes[0], tipo if tipo in TIPOS else ""))
    return mapa


PADROES_ED = [
    r"(\d+)\s*(?:st|nd|rd|th)\s*ed",
    r"(\d+)\s*[ºª°oa]?\s*ed(?:i[cç][aã]o|ition)?\b",
    r"\b(\d+)(?:st|nd|rd|th)\b",
]


def extrair_edicao(texto):
    """Acha '3ed', '12º ED', '4th', '3rd Edition', '2ª Edição'. Devolve (numero, texto_sem_a_edicao)."""
    for padrao in PADROES_ED:
        m = re.search(padrao, texto, flags=re.I)
        if m:
            fim = m.end()
            while fim < len(texto) and texto[fim].isalpha():
                fim += 1
            limpo = (texto[:m.start()] + " " + texto[fim:]).strip(" -,;")
            return m.group(1), re.sub(r"\s+", " ", limpo)
    return "", texto


def metadado_autor(livro: Path) -> str:
    """Tenta ler o autor dos metadados do PDF/EPUB (precisa de: pip install pypdf para PDFs)."""
    ruins = ("microsoft", "unknown", "anonymous", "admin", "user", "z-lib", "anna", "toaz")
    try:
        if livro.suffix.lower() == ".pdf":
            from pypdf import PdfReader
            m = PdfReader(str(livro)).metadata
            autor = (m.author or "") if m else ""
        elif livro.suffix.lower() == ".epub":
            import zipfile
            with zipfile.ZipFile(livro) as z:
                opf = next(n for n in z.namelist() if n.endswith(".opf"))
                xml = z.read(opf).decode("utf-8", "ignore")
            a = re.search(r"<dc:creator[^>]*>(.*?)</dc:creator>", xml, re.S)
            autor = a.group(1) if a else ""
        else:
            return ""
    except Exception:
        return ""
    autor = autor.strip()
    if len(autor) < 4 or any(r in autor.lower() for r in ruins):
        return ""
    return autor


def adivinhar(livro: Path):
    """Palpite de (titulo, autor, edicao) a partir do nome do arquivo (e metadados, se faltar autor)."""
    s = re.sub(r"(\.(pdf|epub|djvu|mobi|html))+$", "", livro.name, flags=re.I)
    s = s.replace("_", " ")
    s = re.sub(r"\(z-lib\.org\)|Anna.s Archive", "", s).strip()
    titulo = autor = edicao = ""

    # "Titulo (Autor 1, Autor 2)" no final
    m = re.search(r"\(([^()]*)\)\s*$", s)
    if m and not re.search(r"\d{4}", m.group(1)):
        autor, s = m.group(1).strip(), s[:m.start()].strip()

    if " -- " in s:  # padrão Anna's Archive: Titulo -- Autor -- 2, 2002 -- Editora -- ...
        partes = [p.strip() for p in s.split(" -- ")]
        titulo = partes[0]
        if not autor and len(partes) > 1 and not re.search(r"\d{4}", partes[1]):
            autor = partes[1]
        for p in partes[2:]:
            mm = re.match(r"(\d+)\s*,", p)
            if mm:
                edicao = mm.group(1)
                break
    elif " - " in s:  # "Titulo - Autor" ou "Titulo - 12º ED - Autor"
        resto = []
        for p in (x.strip() for x in s.split(" - ")):
            num, _ = extrair_edicao(p)
            if num and len(p) < 20:
                edicao = edicao or num
            else:
                resto.append(p)
        if autor:
            titulo = " ".join(resto)
        else:
            titulo = resto[0]
            if len(resto) > 1:
                autor = resto[-1]
                titulo = " ".join(resto[:-1])
    else:
        titulo = s

    num, titulo = extrair_edicao(titulo)
    edicao = edicao or num
    if not autor:
        autor = metadado_autor(livro)
    autor = re.sub(r"\s*\d+$", "", autor).strip()
    return re.sub(r"\s+", " ", titulo).strip(), autor, edicao


def cmd_manifesto(args):
    livros = Path(args.livros).expanduser()
    raiz = Path(args.raiz).expanduser()
    saida = Path(args.saida).expanduser()
    if not livros.is_dir():
        sys.exit(f"Pasta de livros não encontrada: {livros}")
    if not raiz.is_dir():
        sys.exit(f"Pasta raiz não encontrada: {raiz}  (esqueceu o ~ no começo do caminho?)")
    if saida.exists() and not args.forcar:
        sys.exit(f"{saida} já existe e seria sobrescrito (perderia suas correções). Use --forcar se for isso mesmo.")
    lista = listar_livros(livros)
    if not lista:
        sys.exit(f"Nenhum livro ({', '.join(sorted(EXTENSOES))}) encontrado em {livros}")

    mapa = descobrir_disciplinas(raiz, livros)
    sem_disc = sem_autor = 0
    linhas = []
    for livro in lista:
        pares = sorted(unir_pares(mapa.get(livro.resolve(), [])), key=lambda p: slug(p[0]))
        titulo, autor, edicao = adivinhar(livro)
        sem_disc += not pares
        sem_autor += not autor
        linhas.append({
            "arquivo": str(livro.relative_to(livros)),
            "disciplinas": formatar_disciplinas(pares),
            "titulo": titulo, "autor": autor, "edicao": edicao,
            "revisar": "sim" if not autor or not pares else "",
            "ignorar": "",
        })
    gravar_csv(saida, linhas)
    print(f"{len(lista)} livros em {saida}")
    print(f"  {sem_disc} sem disciplina (nenhum link simbólico aponta para eles)")
    print(f"  {sem_autor} sem autor detectado")
    print("Revise principalmente as linhas com revisar=sim; os demais campos são palpites.")


def criar_link(origem: Path, link: Path):
    if link.exists() or link.is_symlink():
        link.unlink()
    link.symlink_to(os.path.relpath(origem, link.parent))


def nome_padrao(l: dict, aceitar_sem_autor=False):
    """Devolve (nome_final, [(disciplina, tipo), ...]) para uma linha do CSV, ou (None, motivo)."""
    pares = unir_pares(parse_disciplinas(l["disciplinas"]))
    titulo = l["titulo"].strip()
    autor = l["autor"].strip() or ("desconhecido" if aceitar_sem_autor else "")
    edicao = l["edicao"].strip() or "sem-ed"
    if not (pares and titulo and autor):
        return None, "faltando disciplina/titulo/autor"
    nome = "_".join([slug(titulo), slug(autor), slug(edicao)]) + Path(l["arquivo"]).suffix.lower()
    return nome, pares


def cmd_pastas(args):
    """Renomeia as pastas de disciplina de underline para hífen (algebra_linear -> algebra-linear)."""
    raiz = Path(args.raiz).expanduser().resolve()
    nomes = disciplinas_do_csv(ler_csv(Path(args.csv).expanduser()))
    nomes |= set(args.incluir or [])
    if args.todas:
        nomes |= {p.name for p in raiz.iterdir()
                  if p.is_dir() and not p.is_symlink() and not p.name.startswith(".")
                  and p.name not in NAO_SAO_DISCIPLINA}
    erros = n = 0
    for nome in sorted(nomes):
        origem, novo = raiz / nome, raiz / slug(nome)
        if nome == slug(nome) or not origem.is_dir() or origem.is_symlink():
            continue
        if novo.exists():
            print(f"CONFLITO: {nome}/ e {slug(nome)}/ já existem (não mexi; junte à mão)")
            erros += 1
            continue
        print(f"{nome}/  ->  {slug(nome)}/")
        n += 1
        if not args.simular:
            origem.rename(novo)
    print(f"\n{n} pastas renomeadas, {erros} conflitos." + (" (simulação)" if args.simular else ""))
    if erros:
        sys.exit(1)


def coletar_links(raiz: Path, livros: Path):
    """Lista (link, alvo) de todos os links simbólicos em `raiz` que apontam para dentro de `livros`."""
    achados = []
    for atual, dirs, arquivos in os.walk(raiz, followlinks=False):
        for nome in dirs + arquivos:
            c = Path(atual) / nome
            if c.is_symlink():
                alvo = c.resolve()
                if livros in alvo.parents:
                    achados.append((c, alvo))
    return achados


def na_zona_gerenciada(link: Path, raiz: Path) -> bool:
    """True para links dentro de <raiz>/<disciplina>/livros/ (a pasta que o script administra)."""
    partes = link.relative_to(raiz).parts
    return len(partes) >= 3 and partes[1] == "livros"


def _fundir_substituicoes(linhas: list, livros: Path, somente, aceitar_sem_autor: bool = False) -> list:
    """Você apagou um PDF ruim e colocou outro do mesmo livro em livros/? A linha antiga (arquivo que não existe
    mais) e a linha nova geram o MESMO nome. Aqui elas viram uma só: fica a linha nova, com as disciplinas e os
    tipos das duas. Devolve [(arquivo_antigo, arquivo_novo)]."""
    fundidas = []
    for antiga in list(linhas):
        if antiga["ignorar"].strip() or (livros / antiga["arquivo"]).exists():
            continue
        nome_antigo, pares_antigos = nome_padrao(antiga, aceitar_sem_autor)
        if nome_antigo is None:
            continue
        for nova in linhas:
            if (nova is antiga or nova["ignorar"].strip() or not (livros / nova["arquivo"]).exists()
                    or (somente is not None and nova["arquivo"] not in somente)):
                continue
            nome_novo, pares_novos = nome_padrao(nova, aceitar_sem_autor)
            if nome_novo == nome_antigo:
                nova["disciplinas"] = formatar_disciplinas(unir_pares(pares_antigos + pares_novos))
                linhas[:] = [x for x in linhas if x is not antiga]
                fundidas.append((antiga["arquivo"], nova["arquivo"]))
                break
    return fundidas


def _local(args):
    """Renomeia os livros em place e recria os links por disciplina e tipo. Devolve (processados, erros)."""
    livros = Path(args.livros).expanduser().resolve()
    raiz = Path(args.raiz).expanduser().resolve()
    csv_path = Path(args.csv).expanduser()
    somente = getattr(args, "somente", None)  # conjunto de 'arquivo' (modo caixa de entrada) ou None
    if not livros.is_dir() or not raiz.is_dir():
        sys.exit("Pasta de livros ou raiz não encontrada.")
    linhas = ler_csv(csv_path)
    for antigo, novo_arq in _fundir_substituicoes(linhas, livros, somente, args.aceitar_sem_autor):
        print(f"substituição: {antigo} (arquivo apagado) <- {novo_arq} (arquivo novo): "
              "uma linha só, com as disciplinas e tipos das duas")

    pendentes = sorted(d for d in disciplinas_do_csv(linhas)
                       if d != slug(d) and (raiz / d).is_dir() and not (raiz / slug(d)).exists())
    if pendentes:
        sys.exit("As pastas abaixo ainda usam underline; rode antes o comando 'pastas' para não duplicar:\n  "
                 + "\n  ".join(pendentes))

    links_antigos = coletar_links(raiz, livros)
    protegidos = {a for l in linhas if l["ignorar"].strip()
                  for a in [(livros / l["arquivo"]).resolve()] if a.exists()}
    plano, usados, erros = [], {}, 0
    falhos = set()
    if somente is not None:  # nomes dos livros que não estão sendo processados contam para detectar duplicatas
        for l in linhas:
            if l["arquivo"] not in somente and not l["ignorar"].strip():
                usados[Path(l["arquivo"]).name] = l["arquivo"]
    avisadas = set()

    for i, l in enumerate(linhas, start=2):
        if l["ignorar"].strip() or (somente is not None and l["arquivo"] not in somente):
            continue
        nome, pares = nome_padrao(l, args.aceitar_sem_autor)
        if nome is None:
            print(f"[linha {i}] {pares}: {l['arquivo']} (pulado)")
            erros += 1
            falhos.add((livros / l["arquivo"]).resolve())
            continue
        if nome in usados:
            print(f"[linha {i}] nome duplicado: {nome} (já usado por {usados[nome]})")
            erros += 1
            falhos.add((livros / l["arquivo"]).resolve())
            continue
        usados[nome] = l["arquivo"]
        origem = livros / l["arquivo"]
        novo = (livros / nome) if args.achatar else origem.with_name(nome)
        if not origem.exists() and not novo.exists():
            print(f"[linha {i}] arquivo não existe: {origem}")
            erros += 1
            falhos.add((livros / l["arquivo"]).resolve())
            continue
        if origem.exists() and origem != novo and novo.exists():
            print(f"[linha {i}] já existe um arquivo com o nome novo: {novo.name} (pulado)")
            erros += 1
            falhos.add((livros / l["arquivo"]).resolve())
            continue
        plano.append((l, origem, novo, pares))

    renomeados = {o.resolve() for _, o, n, _ in plano if o.exists() and o != n}
    desejados = {}
    for l, origem, novo, pares in plano:
        if origem.exists() and origem != novo:
            print(f"renomear: {origem.relative_to(livros)}\n      ->  {novo.relative_to(livros)}")
            if not args.simular:
                novo.parent.mkdir(parents=True, exist_ok=True)
                origem.rename(novo)
        for d, tipo in pares:
            tipo_pasta = tipo or "complementar"
            pasta_livros = raiz / slug(d) / "livros"
            if not pasta_livros.is_dir() and pasta_livros not in avisadas:
                avisadas.add(pasta_livros)
                outras = [x.name for x in (pasta_livros.parent.iterdir() if pasta_livros.parent.is_dir() else [])
                          if x.is_dir() and x.name in ("livro", "livros_texto", "Livros")]
                print(f"   (pasta nova: {slug(d)}/livros/)"
                      + (f"  ATENÇÃO: já existe {outras}; talvez renomeie para 'livros'" if outras else ""))
            link = pasta_livros / tipo_pasta / novo.name
            desejados[link] = novo
            print(f"   link em {slug(d)}/livros/{tipo_pasta}/")
            if not args.simular:
                link.parent.mkdir(parents=True, exist_ok=True)
                criar_link(novo, link)

    # Limpeza: só links simbólicos, nunca livros. Remove os que ficaram quebrados pelo renome e, numa rodada
    # completa, os que estão nas pastas <disciplina>/livros/ mas não fazem mais parte do plano (ex.: livro
    # que mudou de basica para complementar, links soltos da estrutura antiga, links quebrados).
    for link, alvo in links_antigos:
        if link in desejados or alvo in protegidos or alvo in falhos:
            continue
        completo = somente is None
        if alvo in renomeados or (completo and (not alvo.exists() or na_zona_gerenciada(link, raiz))):
            print(f"remover link antigo: {link.relative_to(raiz)}")
            if not args.simular:
                link.unlink()

    if not args.simular:
        backup_csv(csv_path)
        for l, _, novo, pares in plano:
            l["arquivo"] = str(novo.relative_to(livros))
            l["disciplinas"] = formatar_disciplinas([(slug(n), t) for n, t in pares])  # mesmo nome das pastas
        gravar_csv(csv_path, linhas)
    print(f"\n{len(plano)} livros processados, {erros} com problema."
          + (" (simulação, nada foi alterado)" if args.simular
             else " CSV atualizado com os novos nomes (backup em backups/)."))
    return len(plano), erros


def cmd_local(args):
    _, erros = _local(args)
    if erros:
        sys.exit(1)


SISTEMA_IA = """Você identifica dados bibliográficos de livros a partir do texto (ou imagens) das primeiras páginas.
Responda SOMENTE com um objeto JSON, sem markdown, com as chaves:
- "titulo": título principal curto, no idioma original do livro; inclua o volume se houver (ex.: "Cálculo Vol. 1"); omita subtítulos longos.
- "autor": apenas SOBRENOMES, no máximo 2 autores unidos por " e " (ex.: "Cormen e Leiserson"); se houver 3 ou mais autores, use o primeiro seguido de " et al" (ex.: "Cormen et al").
- "edicao": somente o número da edição (ex.: "3"); "" se não aparecer.
- "confianca": "alta", "media" ou "baixa".
Use o nome do arquivo e o palpite atual apenas como dicas; confie no conteúdo das páginas.
Se algo não estiver visível, deixe "" em vez de inventar."""


def extrair_texto(livro: Path, paginas: int) -> str:
    sufixo = livro.suffix.lower()
    if sufixo == ".pdf":
        if shutil.which("pdftotext"):
            r = _rodar(["pdftotext", "-f", "1", "-l", str(paginas), "-layout", str(livro), "-"])
            return r.stdout.decode("utf-8", "ignore")
        try:
            from pypdf import PdfReader
            rd = PdfReader(str(livro))
            return "\n".join((rd.pages[i].extract_text() or "") for i in range(min(paginas, len(rd.pages))))
        except Exception:
            return ""
    if sufixo == ".html":
        bruto = livro.read_bytes()[:60000].decode("utf-8", "ignore")
        bruto = re.sub(r"(?is)<(script|style).*?</\1>", " ", bruto)
        return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", bruto))
    if sufixo == ".epub":
        import zipfile
        try:
            with zipfile.ZipFile(livro) as z:
                opf = next(n for n in z.namelist() if n.endswith(".opf"))
                return re.sub(r"<[^>]+>", " ", z.read(opf).decode("utf-8", "ignore"))[:3000]
        except Exception:
            return ""
    return ""


def renderizar_paginas(livro: Path, paginas: int) -> list:
    """Para PDFs escaneados (sem texto): devolve as primeiras páginas como JPEG (bytes)."""
    if livro.suffix.lower() != ".pdf" or not shutil.which("pdftoppm"):
        return []
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        _rodar(["pdftoppm", "-f", "1", "-l", str(paginas), "-r", "60", "-jpeg", str(livro), f"{tmp}/p"])
        return [p.read_bytes() for p in sorted(Path(tmp).glob("p*.jpg"))]


def perguntar_ia(client, modelo, livro: Path, linha: dict, args):
    import base64
    texto = extrair_texto(livro, args.paginas).strip()
    dica = (f"Arquivo: {livro.name}\nPalpite atual: titulo={linha['titulo']!r}, "
            f"autor={linha['autor']!r}, edicao={linha['edicao']!r}\n\n")
    if len(texto) >= 200:
        conteudo = [{"type": "text", "text": dica + "Texto das primeiras páginas:\n" + texto[:6000]}]
        origem = "texto"
    else:
        imagens = renderizar_paginas(livro, min(args.paginas, 4))
        conteudo = [{"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                                  "data": base64.b64encode(i).decode()}} for i in imagens]
        conteudo.append({"type": "text", "text": dica + ("Texto extraído (pouco):\n" + texto[:1500] if texto else "")})
        origem = "imagem" if imagens else "so-nome"
    msg = client.messages.create(model=modelo, max_tokens=300, system=SISTEMA_IA,
                                 messages=[{"role": "user", "content": conteudo}])
    resposta = next(b.text for b in msg.content if b.type == "text")
    dados, fim = json.JSONDecoder().raw_decode(resposta[resposta.index("{"):])
    if "{" in resposta[resposta.index("{") + fim:]:  # modelo devolveu mais de um objeto
        dados["confianca"] = "baixa"
    dados["_origem"] = origem
    dados["_tokens"] = [msg.usage.input_tokens, msg.usage.output_tokens]
    return dados


def _exigir_api():
    """Precisa de GEMINI_API_KEY (grátis) e/ou ANTHROPIC_API_KEY; o `llm.py` escolhe o provedor a cada chamada."""
    if not llm.ha_chave():
        sys.exit("Defina GEMINI_API_KEY (grátis: https://aistudio.google.com/app/apikey) e/ou ANTHROPIC_API_KEY "
                 "(ambiente ou .env).")


def _cliente_llm(csv_path):
    """Gemini grátis primeiro; quando a cota acaba, Claude Haiku. O estado da cota fica em cache/."""
    return llm.criar_cliente_llm(caminho_cache(csv_path, "llm_estado"))


def impressao_digital(caminho: Path) -> str:
    """Identifica um livro pelo conteúdo (tamanho + SHA-1 do primeiro MiB) e não pelo nome:
    renomear o arquivo não invalida mais o cache da `ia`."""
    import hashlib
    h = hashlib.sha1()
    with open(caminho, "rb") as f:
        h.update(f.read(1 << 20))
    return f"{caminho.stat().st_size}:{h.hexdigest()[:16]}"


def cmd_ia(args):
    _exigir_api()
    livros = Path(args.livros).expanduser()
    csv_path = Path(args.csv).expanduser()
    somente = getattr(args, "somente", None)
    todos = getattr(args, "todos", False)
    cache_path = caminho_cache(csv_path, "ia")
    cache = ler_cache(cache_path, args.refazer)

    linhas = ler_csv(csv_path)
    backup_csv(csv_path)

    def precisa(l):
        # Por padrão só os livros que ainda não foram conferidos: com revisar=sim ou sem título/autor.
        return todos or bool(l["revisar"].strip()) or not l["titulo"].strip() or not l["autor"].strip()

    elegiveis = [l for l in linhas if not l["ignorar"].strip() and (somente is None or l["arquivo"] in somente)]
    alvo = [l for l in elegiveis if precisa(l)]
    if len(elegiveis) - len(alvo):
        print(f"{len(elegiveis) - len(alvo)} livro(s) já conferidos foram pulados (--todos reprocessa tudo).")
    if args.limite:
        alvo = alvo[:args.limite]

    client = _cliente_llm(csv_path)
    tin = tout = alterados = 0
    for n, l in enumerate(alvo, 1):
        origem = livros / l["arquivo"]
        chave = impressao_digital(origem) if origem.is_file() else l["arquivo"]
        if chave not in cache and l["arquivo"] in cache:      # entrada antiga, indexada pelo nome do arquivo
            cache[chave] = cache[l["arquivo"]]
        if chave not in cache:
            try:
                cache[chave] = perguntar_ia(client, args.modelo, origem, l, args)
                tin += cache[chave]["_tokens"][0]
                tout += cache[chave]["_tokens"][1]
            except Exception as e:
                print(f"[{n}/{len(alvo)}] ERRO em {l['arquivo']}: {e}")
                continue
            gravar_cache(cache_path, cache)
        d = cache[chave]
        ja_conferido = not l["revisar"].strip() and l["titulo"].strip() and l["autor"].strip()
        antes = {"titulo": l["titulo"], "autor": l["autor"], "edicao": l["edicao"]}
        l["titulo"] = d.get("titulo", "").strip() or l["titulo"]
        l["autor"] = d.get("autor", "").strip() or l["autor"]
        l["edicao"] = str(d.get("edicao", "")).strip() or l["edicao"]
        baixa = d.get("confianca") != "alta" or not l["autor"] or not l["disciplinas"].strip()
        l["revisar"] = "sim" if baixa else ""
        print(f"[{n}/{len(alvo)}] ({d.get('_origem')}, {d.get('confianca')}) {l['arquivo'][:45]} -> "
              f"{l['titulo']} | {l['autor']} | {l['edicao'] or 'sem-ed'}")
        if ja_conferido:
            for campo, antigo in antes.items():
                if antigo.strip() and antigo.strip() != l[campo]:
                    alterados += 1
                    print(f"      MUDOU {campo}: {antigo!r} -> {l[campo]!r}")

    gravar_csv(csv_path, linhas)
    print(f"\nCSV atualizado (backups em {csv_path.parent / 'backups'}).")
    print(client.resumo())
    if alterados:
        print(f"ATENÇÃO: {alterados} campo(s) de livros já conferidos foram alterados (linhas MUDOU acima). "
              "O `local` renomeia os arquivos conforme o CSV: compare com o backup mais recente antes de rodá-lo.")


SISTEMA_PPC = """Você relaciona livros às disciplinas de um curso usando o PPC (projeto pedagógico) fornecido, que traz ementas e as bibliografias básica e complementar de cada disciplina.
Para cada livro você recebe: id, titulo, autor, edicao e "atuais" (as disciplinas em que o aluno já usa o livro; pode estar vazio).
Regras:
- A bibliografia básica e a complementar de cada disciplina no PPC são a evidência mais forte; depois a ementa.
- Compare os livros pela obra, não pela edição: o PPC pode citar outra edição, ou a versão em outro idioma, do mesmo livro.
- Para cada disciplina, "tipo" é "basica" somente se o livro consta na bibliografia BÁSICA daquela disciplina no PPC. Se consta na complementar, OU não consta em nenhuma das duas, o tipo é "complementar". O mesmo livro pode ser básico numa disciplina e complementar em outra.
- Prefira SEMPRE um nome da lista de pastas existentes do aluno (ex.: "Cálculo Diferencial e Integral III" -> "calculo-diferencial-e-integral-3"). Se a disciplina do PPC não tiver pasta correspondente, proponha um nome em kebab-case, sem acentos, no mesmo estilo.
- Se "atuais" não estiver vazio, devolva uma entrada para CADA disciplina atual, com exatamente o nome dela. Só acrescente outras disciplinas se a instrução da rodada permitir.
- Se "atuais" estiver vazio, proponha as disciplinas em que o PPC lista o livro (no máximo 4). Se nenhuma se aplicar com segurança, devolva lista vazia. Não force.
- "confianca" refere-se à evidência encontrada no PPC.
Responda SOMENTE com um array JSON, um item por livro:
[{"id": <int>, "disciplinas": [{"pasta": "nome-da-pasta", "tipo": "basica|complementar"}], "confianca": "alta|media|baixa", "motivo": "<até 15 palavras>"}]"""


def _sugestoes(r):
    """Normaliza a resposta do modelo para [(pasta, tipo)] (aceita o formato antigo: lista de strings)."""
    saida = []
    for d in r.get("disciplinas", []):
        if isinstance(d, dict) and d.get("pasta"):
            t = slug(str(d.get("tipo", "")))
            saida.append((d["pasta"], t if t in TIPOS else ""))
        elif isinstance(d, str) and d.strip():
            saida.append((d.strip(), ""))
    return saida


def resposta_da_ia(ia_cache: dict, livros: Path, arquivo: str) -> dict:
    """Resposta guardada da `ia` para um livro: pelo conteúdo do arquivo (atual) ou pelo nome (entradas antigas)."""
    origem = livros / arquivo
    if origem.is_file():
        r = ia_cache.get(impressao_digital(origem))
        if r:
            return r
    return ia_cache.get(arquivo) or {}


def motivos_de_revisao(l: dict, livros: Path, ia_cache: dict, ppc_cache: dict) -> list:
    """Por que este livro ainda precisa de conferência? Lista vazia = pode ser organizado sozinho.
    Pasta de disciplina que ainda não existe NÃO é motivo: o `local` cria a pasta."""
    motivos = []
    r_ia = resposta_da_ia(ia_cache, livros, l["arquivo"])
    if not r_ia:
        motivos.append("a IA ainda não leu o livro")
    elif r_ia.get("confianca") != "alta":
        motivos.append(f"IA com confiança {r_ia.get('confianca')}")
    if not l["autor"].strip():
        motivos.append("sem autor")
    pares = parse_disciplinas(l["disciplinas"])
    if not pares:
        motivos.append("sem disciplina")
        return motivos
    r_ppc = ppc_cache.get(l["arquivo"]) or {}
    if r_ppc and r_ppc.get("confianca") != "alta":
        motivos.append(f"PPC com confiança {r_ppc.get('confianca')}")
    return motivos


def _contexto_de_confianca(args):
    livros = Path(getattr(args, "livros", None) or LIVROS_PADRAO).expanduser()
    csv_path = Path(args.csv).expanduser()
    ia_cache = ler_cache(caminho_cache(csv_path, "ia"))
    ppc_cache = ler_cache(caminho_cache(csv_path, "ppc"))
    return livros, csv_path, ia_cache, ppc_cache


def cmd_liberar(args):
    """Recalcula `revisar` com as respostas já guardadas (sem API): libera quem a IA e o PPC identificaram
    com confiança alta e cujas pastas existem; para os demais, mostra o motivo."""
    livros, csv_path, ia_cache, ppc_cache = _contexto_de_confianca(args)
    linhas = ler_csv(csv_path)
    liberados = mantidos = 0
    for l in linhas:
        if l["ignorar"].strip() or not l["revisar"].strip():
            continue
        motivos = motivos_de_revisao(l, livros, ia_cache, ppc_cache)
        if motivos:
            mantidos += 1
            print(f"  fica com revisar=sim: {l['arquivo'][:70]}\n      -> {'; '.join(motivos)}")
        else:
            liberados += 1
            print(f"  liberado: {l['arquivo'][:70]}  ({l['titulo']} | {l['autor']} | {l['edicao'] or 'sem-ed'})")
            l["revisar"] = ""
    if liberados and not args.simular:
        backup_csv(csv_path)
        gravar_csv(csv_path, linhas)
    print(f"\n{liberados} liberado(s), {mantidos} continuam para revisar." + (" (simulação)" if args.simular else ""))
    if liberados and not args.simular:
        print("Próximos passos: python3 organizar_livros.py local   e depois   python3 organizar_livros.py drive")


def cmd_ppc(args):
    _exigir_api()
    raiz = Path(args.raiz).expanduser()
    csv_path = Path(args.csv).expanduser()
    if not raiz.is_dir():
        sys.exit(f"Pasta raiz não encontrada: {raiz}")
    ppc = texto_ppc(Path(args.ppc).expanduser(), args.paginas).strip()
    if len(ppc) < 2000:
        sys.exit("Quase nenhum texto extraído do PPC (PDF escaneado?).")
    print(f"PPC: {len(ppc):,} caracteres (≈ {len(ppc)//3:,} tokens por chamada; só a 1ª paga preço cheio, as outras usam cache).")

    somente = getattr(args, "somente", None)
    mesclar = getattr(args, "mesclar", False)
    cache_path = caminho_cache(csv_path, "ppc")
    cache = ler_cache(cache_path, args.refazer)
    ia = ler_cache(caminho_cache(csv_path, "ia"))
    livros_dir = Path(getattr(args, "livros", None) or LIVROS_PADRAO).expanduser()

    linhas = ler_csv(csv_path)
    backup_csv(csv_path)

    def elegivel(l):
        return not l["ignorar"].strip() and (somente is None or l["arquivo"] in somente)

    def precisa(l):
        pares = parse_disciplinas(l["disciplinas"])
        return (not pares) or any(not t for _, t in pares) or mesclar or args.refazer

    import hashlib
    vocab = pastas_disciplina(raiz)
    vocab_hash = hashlib.sha1(",".join(vocab).encode()).hexdigest()[:12]

    def cacheado(l):
        r = cache.get(l["arquivo"])
        if r is None:
            return False
        atuais = parse_disciplinas(l["disciplinas"])
        if not atuais and not _sugestoes(r) and r.get("_vocab") != vocab_hash:
            return False      # "nenhuma disciplina" foi respondido com outra lista de pastas: pergunta de novo
        cobertas = {slug(p) for p, _ in _sugestoes(r)}
        return all(slug(n) in cobertas for n, _ in atuais)

    alvo = [i for i, l in enumerate(linhas) if elegivel(l) and precisa(l) and not cacheado(l)]
    if args.limite:
        alvo = alvo[:args.limite]

    regra = ("Instrução da rodada: classifique as disciplinas atuais e, se o PPC listar claramente o livro em OUTRA "
             "disciplina da lista de pastas, acrescente-a também." if mesclar else
             "Instrução da rodada: para livros com atuais não vazio, devolva SOMENTE essas disciplinas, classificadas "
             "(não acrescente outras); para atuais vazio, proponha as disciplinas.")
    client = _cliente_llm(csv_path)
    uso = dict(inp=0, out=0, cw=0, cr=0)
    for ini in range(0, len(alvo), args.lote):
        ids = alvo[ini:ini + args.lote]
        lista = "\n".join(
            f"{i}: titulo={linhas[i]['titulo']!r} autor={linhas[i]['autor']!r} edicao={linhas[i]['edicao']!r} "
            f"atuais={[n for n, _ in parse_disciplinas(linhas[i]['disciplinas'])]!r} arquivo={linhas[i]['arquivo']!r}"
            for i in ids)
        msg = client.messages.create(
            model=args.modelo, max_tokens=8000, system=SISTEMA_PPC,
            messages=[{"role": "user", "content": [
                {"type": "text", "text": "PPC DO CURSO:\n" + ppc, "cache_control": {"type": "ephemeral"}},
                {"type": "text", "text": "Pastas existentes do aluno:\n" + ", ".join(vocab) + "\n\n" + regra
                                         + "\n\nLivros:\n" + lista},
            ]}])
        u = msg.usage
        uso["inp"] += u.input_tokens
        uso["out"] += u.output_tokens
        uso["cw"] += getattr(u, "cache_creation_input_tokens", 0) or 0
        uso["cr"] += getattr(u, "cache_read_input_tokens", 0) or 0
        resp = next(b.text for b in msg.content if b.type == "text")
        for item in json.JSONDecoder().raw_decode(resp[resp.index("["):])[0]:
            i = int(item["id"])
            if i in ids:
                item["_vocab"] = vocab_hash
                cache[linhas[i]["arquivo"]] = item
        gravar_cache(cache_path, cache)
        print(f"  lote {ini // args.lote + 1}: {len(ids)} livros")

    vocab_slugs = {slug(v) for v in vocab}
    for l in linhas:
        r = cache.get(l["arquivo"])
        if not r or not elegivel(l) or not precisa(l):
            continue
        atuais = parse_disciplinas(l["disciplinas"])
        sugeridas = _sugestoes(r)
        tipo_sugerido = {slug(p): t for p, t in sugeridas}
        novas = []
        for nome, tipo in atuais:
            t = tipo_sugerido.get(slug(nome), "")
            novas.append((nome, t if t and (args.refazer or not tipo) else tipo))
        pastas_novas = []
        if not atuais or mesclar:
            conhecidas = {slug(n) for n, _ in atuais}
            for pasta, t in sugeridas:
                if slug(pasta) not in conhecidas:
                    novas.append((pasta, t or "complementar"))
                    if slug(pasta) not in vocab_slugs:
                        pastas_novas.append(slug(pasta))
        l["disciplinas"] = formatar_disciplinas(unir_pares(novas))
        if not atuais:
            l["revisar"] = "sim" if (not novas or r.get("confianca") != "alta" or motivos_de_revisao(
                l, livros_dir, ia, cache)) else ""
        print(f"{l['titulo'][:40]:40} -> {l['disciplinas'] or '(nenhuma)'} "
              f"[{r.get('confianca')}] {r.get('motivo', '')}"
              + (f"  (pasta nova, será criada: {', '.join(pastas_novas)})" if pastas_novas else ""))

    gravar_csv(csv_path, linhas)
    print(f"\nCSV atualizado (backups em {csv_path.parent / 'backups'}).")
    print(client.resumo())


def cmd_reconciliar(args):
    """Acerta a coluna 'arquivo' do CSV quando você moveu livros à mão (ex.: tirou das subpastas)."""
    livros = Path(args.livros).expanduser().resolve()
    csv_path = Path(args.csv).expanduser()
    linhas = ler_csv(csv_path)
    por_nome = {}
    for p in listar_livros(livros):
        por_nome.setdefault(p.name, []).append(str(p.relative_to(livros)))
    ajustados = sumidos = ambiguos = 0
    for l in linhas:
        if l["ignorar"].strip() or (livros / l["arquivo"]).exists():
            continue
        achados = por_nome.get(Path(l["arquivo"]).name, [])
        if len(achados) == 1:
            print(f"{l['arquivo']}  ->  {achados[0]}")
            l["arquivo"] = achados[0]
            ajustados += 1
        elif not achados:
            print(f"NÃO ENCONTRADO em livros/: {l['arquivo']}")
            sumidos += 1
        else:
            print(f"AMBÍGUO ({len(achados)} arquivos com esse nome): {l['arquivo']}  {achados}")
            ambiguos += 1
    no_csv = {l["arquivo"] for l in linhas}
    fora = [p for ps in por_nome.values() for p in ps if p not in no_csv]
    if ajustados and not args.simular:
        backup_csv(csv_path)
        gravar_csv(csv_path, linhas)
    print(f"\n{ajustados} caminhos acertados, {sumidos} não encontrados, {ambiguos} ambíguos."
          + (" (simulação)" if args.simular else ""))
    if fora:
        print(f"{len(fora)} arquivo(s) em livros/ ainda não estão no CSV (o comando `novos` os trataria como novos):")
        print(*fora, sep="\n  ")


def _pronto_para_drive(l, livros: Path):
    """Devolve ((arquivo, nome, pares), None) se a linha pode ir ao Drive; senão (None, motivo)."""
    if l["ignorar"].strip():
        return None, None
    if l["revisar"].strip():
        return None, "pendente de revisão"
    nome, pares = nome_padrao(l)
    if nome is None:
        return None, pares
    if not (livros / l["arquivo"]).exists():
        return None, "arquivo não existe"
    if Path(l["arquivo"]).name != nome:
        return None, "ainda não renomeado (rode `local`)"
    return (l["arquivo"], nome, pares), None


def _rclone(argumentos):
    return subprocess.run(["rclone", *argumentos], capture_output=True, text=True)


def _drive(args):
    """Envia livros/ direto do seu computador para <remoto>/livros e cria, nas pastas de disciplina do Drive,
    atalhos do Drive (rclone backend shortcut) apontando para esses arquivos. Não usa pasta intermediária.
    Nunca apaga livros no Drive; só cria/atualiza. Atalhos que já existem não são recriados."""
    if not shutil.which("rclone"):
        print("rclone não encontrado no PATH.")
        return
    if not args.rclone:
        print("Defina o destino do Drive: --rclone gdrive:faculdade (ou LIVROS_RCLONE no .env).")
        return
    remoto, _, base = args.rclone.partition(":")
    base = base.strip("/")
    caminho = lambda *partes: "/".join(x for x in (base, *partes) if x)  # relativo à raiz do remoto
    livros = Path(args.livros).expanduser().resolve()
    extra = shlex.split(args.rclone_args or "")
    simular = args.simular or "--dry-run" in extra or "-n" in extra

    prontos = []
    for i, l in enumerate(ler_csv(Path(args.csv).expanduser()), start=2):
        info, motivo = _pronto_para_drive(l, livros)
        if info:
            prontos.append(info)
        elif motivo:
            print(f"[linha {i}] {motivo}: {l['arquivo']} (fica fora do Drive por enquanto)")
    if not prontos:
        print("Nada pronto para enviar.")
        return

    # 1) os arquivos: um envio só, de livros/ para <base>/livros (rclone pula o que já está igual)
    import tempfile
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as f:
        f.write("\n".join(a for a, _, _ in prontos) + "\n")
        lista = f.name
    cmd = ["rclone", "copy", str(livros), f"{remoto}:{caminho('livros')}", "--files-from", lista, "-v"]
    if simular and "--dry-run" not in extra and "-n" not in extra:
        cmd.append("--dry-run")                       # simulação: o rclone só diz o que enviaria
    cmd += extra
    print("Executando:", " ".join(shlex.quote(c) for c in cmd))
    r = subprocess.run(cmd)
    os.unlink(lista)
    if r.returncode:
        print(f"rclone copy terminou com código {r.returncode}: não vou criar atalhos.")
        return

    # 2) o que já existe nas pastas de disciplina do Drive (atalho de arquivo aparece como arquivo)
    r = _rclone(["lsf", "-R", "--files-only", "--format", "ip", "--separator", "|", f"{remoto}:{base}"] + extra)
    if r.returncode:
        print("Não consegui listar o Drive:", r.stderr.strip()[-300:])
        return
    existentes, copias_reais, atalhos_no_drive, no_drive_livros = set(), [], [], set()
    ids_dos_livros, ids_dos_atalhos = {}, {}
    for linha in r.stdout.splitlines():
        if "|" not in linha:
            continue
        id_, rel = linha.split("|", 1)
        partes = rel.split("/")
        if partes[0] == "livros":
            no_drive_livros.add("/".join(partes[1:]))
            ids_dos_livros["/".join(partes[1:])] = id_
            continue
        existentes.add(rel)
        if len(partes) == 3 and partes[1] in TIPOS:
            # o ID de um atalho vem com uma tabulação (alvo + atalho); sem ela é uma cópia real
            if "\t" in id_:
                atalhos_no_drive.append(rel)
                ids_dos_atalhos[rel] = id_
            elif Path(rel).suffix.lower() in EXTENSOES:
                copias_reais.append(rel)
    if copias_reais:
        if getattr(args, "limpar_copias", False):
            print(f"Removendo {len(copias_reais)} cópia(s) real(is) de um envio antigo das pastas de disciplina"
                  f"{' (simulação)' if simular else ' (vão para a lixeira do Drive)'}:")
            for rel in copias_reais:
                print("  ", rel)
                if not simular:
                    r = _rclone(["deletefile", f"{remoto}:{caminho(rel)}"] + extra)
                    if r.returncode:
                        print("     FALHOU:", (r.stderr or r.stdout).strip()[-150:])
                        continue
                existentes.discard(rel)
        else:
            print(f"AVISO: {len(copias_reais)} arquivo(s) real(is) (de um envio antigo) em pastas de disciplina do Drive; "
                  "eles contam como já existentes e não viram atalho. Rode `drive --limpar-copias` para removê-los.")

    # 3) atalhos obsoletos (livro que mudou de tipo/disciplina, foi renomeado ou removido do CSV): só atalhos,
    #    nunca o arquivo real em livros/. Conta como "esperado" todo destino de qualquer linha não ignorada,
    #    inclusive as pendentes de revisão, para não podar o que só está esperando você corrigir o CSV.
    esperados = set()
    for l in ler_csv(Path(args.csv).expanduser()):
        if not l["ignorar"].strip():
            nome_l, pares_l = nome_padrao(l)
            if nome_l:
                esperados.update(f"{slug(d)}/{t or 'complementar'}/{nome_l}" for d, t in pares_l)
    obsoletos = [rel for rel in atalhos_no_drive if rel not in esperados]
    if obsoletos and not getattr(args, "sem_podar", False):
        print(f"Removendo {len(obsoletos)} atalho(s) obsoleto(s){' (simulação)' if simular else ''}:")
        for rel in obsoletos:
            print("  ", rel)
            if not simular:
                r = _rclone(["deletefile", f"{remoto}:{caminho(rel)}"] + extra)
                if r.returncode:
                    print("     FALHOU:", (r.stderr or r.stdout).strip()[-150:])
                    continue
            existentes.discard(rel)
    elif obsoletos:
        print(f"{len(obsoletos)} atalho(s) obsoleto(s) mantido(s) (--sem-podar).")
    nomes_esperados = {Path(a).as_posix() for a, _, _ in prontos}
    orfaos = sorted(x for x in no_drive_livros if x not in nomes_esperados)
    if orfaos:
        print(f"Informação: {len(orfaos)} arquivo(s) em {caminho('livros')} no Drive não correspondem a nenhum livro "
              "pronto (renomeados ou removidos?). Não apago arquivos reais; revise pelo navegador:")
        print(*orfaos[:15], sep="\n   ")
        if len(orfaos) > 15:
            print(f"   ... e mais {len(orfaos) - 15}")

    # 3b) atalhos que existem com o nome certo, mas apontam para OUTRO arquivo: acontece quando você troca um PDF
    #     (o antigo saiu do Drive e o novo entrou com outro ID). O ID de um atalho traz o ID do alvo.
    desatualizados = []
    for arquivo, nome, pares in prontos:
        id_arquivo = ids_dos_livros.get(Path(arquivo).as_posix())
        if not id_arquivo:
            continue
        for d, tipo in pares:
            destino = f"{slug(d)}/{tipo or 'complementar'}/{nome}"
            if destino in ids_dos_atalhos and id_arquivo not in ids_dos_atalhos[destino].split("\t"):
                desatualizados.append(destino)
    if desatualizados:
        print(f"{len(desatualizados)} atalho(s) apontam para outro arquivo (PDF substituído?); "
              f"{'seriam recriados' if simular else 'recriando'}:")
        for destino in desatualizados:
            print("  ", destino)
            if not simular:
                r = _rclone(["deletefile", f"{remoto}:{caminho(destino)}"] + extra)
                if r.returncode:
                    print("     FALHOU:", (r.stderr or r.stdout).strip()[-150:])
                    continue
            existentes.discard(destino)

    # 4) os atalhos que faltam
    faltam = []
    for arquivo, nome, pares in prontos:
        for d, tipo in pares:
            destino = f"{slug(d)}/{tipo or 'complementar'}/{nome}"
            if destino not in existentes:
                faltam.append((arquivo, destino))
    print(f"{len(faltam)} atalho(s) a criar ({sum(len(p) for _, _, p in prontos)} previstos no total).")
    if simular or not faltam:
        return
    for pasta in sorted({d.rsplit("/", 1)[0] for _, d in faltam}):
        _rclone(["mkdir", f"{remoto}:{caminho(pasta)}"] + extra)

    from concurrent.futures import ThreadPoolExecutor

    def criar(par):
        arquivo, destino = par
        res = _rclone(["backend", "shortcut", f"{remoto}:", caminho("livros", arquivo), caminho(destino)] + extra)
        return par, res.returncode, (res.stderr or res.stdout).strip()[-200:]

    criados = falhas = 0
    with ThreadPoolExecutor(max_workers=4) as pool:
        for (arquivo, destino), codigo, saida in pool.map(criar, faltam):
            if codigo == 0:
                criados += 1
                print(f"  atalho: {destino}")
            else:
                falhas += 1
                print(f"  FALHOU: {destino}  ({saida})")
    print(f"{criados} atalho(s) criado(s), {falhas} falha(s).")


def cmd_drive(args):
    _drive(args)


def notificar(titulo, texto):
    """Aviso na área de trabalho, se houver notify-send (falha em silêncio)."""
    if shutil.which("notify-send"):
        try:
            subprocess.run(["notify-send", "-a", "Livros", titulo, texto], check=False, timeout=5)
        except Exception:
            pass


def _organizar(args, livros, raiz, csv_path, novos_rel):
    """ia -> ppc -> local para as linhas de `novos_rel`. Devolve (organizados, para_revisar)."""
    novos_rel = set(novos_rel)
    if llm.ha_chave():
        base = dict(livros=str(livros), csv=str(csv_path), modelo=args.modelo, somente=novos_rel)
        try:
            cmd_ia(argparse.Namespace(**base, paginas=8, limite=0, apenas_revisar=False, refazer=False,
                                      preco_in=2.0, preco_out=10.0))
            if Path(args.ppc).expanduser().exists():
                cmd_ppc(argparse.Namespace(**base, raiz=str(raiz), ppc=args.ppc, paginas=args.paginas_ppc,
                                           lote=45, limite=0, mesclar=False, refazer=False))
            else:
                print(f"PPC não encontrado em {args.ppc}: tipos e disciplinas não propostos.")
        except (Exception, SystemExit) as e:
            print(f"Falha na identificação/classificação: {e}")
    else:
        print("Nenhuma chave de IA (GEMINI_API_KEY / ANTHROPIC_API_KEY): os livros ficam no CSV para você preencher à mão.")

    linhas = ler_csv(csv_path)
    prontos = {l["arquivo"] for l in linhas if l["arquivo"] in novos_rel and not l["ignorar"].strip()
               and (args.aplicar_tudo or not l["revisar"].strip())}
    revisar = sorted(novos_rel - prontos)
    _, _, ia_cache, ppc_cache = _contexto_de_confianca(
        argparse.Namespace(livros=str(livros), csv=str(csv_path), raiz=str(raiz)))
    por_arquivo = {l["arquivo"]: l for l in linhas}
    revisar = [f"{rel}   [{'; '.join(motivos_de_revisao(por_arquivo[rel], livros, ia_cache, ppc_cache)) or 'marcado para revisão'}]"
               if rel in por_arquivo else rel for rel in revisar]
    organizados = 0
    if prontos:
        pastas_antes = set(pastas_disciplina(raiz))
        organizados, erros = _local(argparse.Namespace(livros=str(livros), raiz=str(raiz), csv=str(csv_path),
                                                       simular=False, achatar=False, aceitar_sem_autor=False,
                                                       somente=prontos))
        criadas = sorted(set(pastas_disciplina(raiz)) - pastas_antes)
        if criadas:
            print("Pastas de disciplina criadas automaticamente:", ", ".join(criadas))
        if erros:
            revisar.append(f"{erros} com erro no passo local (veja o log)")
    return organizados, revisar


def _fechar(args, livros, csv_path, organizados, revisar):
    """Atualiza o Drive (se pedido), imprime o resumo e avisa na área de trabalho."""
    if args.drive or args.rclone:
        _drive(argparse.Namespace(livros=str(livros), csv=str(csv_path), rclone=args.rclone,
                                  rclone_args=args.rclone_args, simular=False, limpar_copias=False))
    resumo = f"{organizados} livro(s) organizado(s)."
    if revisar:
        resumo += f" Para revisar no CSV ({Path(csv_path).name}): {len(revisar)}."
        print("Precisam de revisão (revisar=sim):", *revisar, sep="\n  ")
    print(resumo)
    notificar("Livros", resumo)


def _trava(csv_path):
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    trava = open(csv_path.parent / ".lock", "w")
    try:
        fcntl.flock(trava, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return None
    return trava


def cmd_novos(args):
    """Caixa de entrada: organiza os livros jogados em livros/ que ainda não estão no CSV."""
    livros = Path(args.livros).expanduser().resolve()
    raiz = Path(args.raiz).expanduser().resolve()
    csv_path = Path(args.csv).expanduser()
    if not livros.is_dir():
        sys.exit(f"Pasta de livros não encontrada: {livros}")
    trava = _trava(csv_path)
    if trava is None:
        print("Outra execução já está em andamento; saindo.")
        return

    linhas = ler_csv(csv_path) if csv_path.exists() else []
    conhecidos = {l["arquivo"] for l in linhas}

    def livros_novos():
        return [p for p in listar_livros(livros) if str(p.relative_to(livros)) not in conhecidos]

    novos = livros_novos()
    for _ in range(10):  # espera terminar a cópia/download: ninguém mexeu no arquivo nos últimos N segundos
        if not novos or not args.estavel or args.simular:
            break
        agora = time.time()
        if all(agora - p.stat().st_mtime >= args.estavel for p in novos):
            break
        print(f"Aguardando {args.estavel}s para os arquivos terminarem de ser gravados...")
        time.sleep(args.estavel)
        novos = livros_novos()
    if not novos:
        print("Nenhum livro novo.")
        return

    print(f"{len(novos)} livro(s) novo(s):")
    for p in novos:
        print("  ", p.relative_to(livros))
    if args.simular:
        print("(simulação: nada foi alterado)")
        return

    for p in novos:
        titulo, autor, edicao = adivinhar(p)
        linhas.append({"arquivo": str(p.relative_to(livros)), "disciplinas": "", "titulo": titulo,
                       "autor": autor, "edicao": edicao, "revisar": "sim", "ignorar": ""})
    backup_csv(csv_path)
    gravar_csv(csv_path, linhas)
    organizados, revisar = _organizar(args, livros, raiz, csv_path, {str(p.relative_to(livros)) for p in novos})
    _fechar(args, livros, csv_path, organizados, revisar)


# ----------------------------------------------------------------------------- recolher livros espalhados

PASTAS_IGNORADAS = {"node_modules", "__pycache__", "target", "out", "bin", "lib", "src", "aulas", "provas", "slides"}


def _pasta_de_livros(nome: str) -> bool:
    n = nome.lower()
    return n in ("livros", "livro") or n.startswith(("livros_", "livros-"))


def _disciplinas_da_raiz(raiz: Path):
    return [d for d in sorted(raiz.iterdir())
            if d.is_dir() and not d.is_symlink() and not d.name.startswith(".") and d.name not in NAO_SAO_DISCIPLINA]


def _arquivos_de_livro(pasta: Path):
    """Arquivos reais (não links) com extensão de livro dentro de `pasta`, sem entrar em pastas de código/aulas."""
    for atual, dirs, arquivos in os.walk(pasta, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d not in PASTAS_IGNORADAS and not d.startswith("."))
        for nome in sorted(arquivos):
            p = Path(atual) / nome
            if p.suffix.lower() in EXTENSOES and not p.is_symlink():
                yield p


def candidatos_obvios(raiz: Path):
    """Livros reais dentro de pastas chamadas livros/, livro/ ou livros_*/ de cada disciplina."""
    achados = []
    for d in _disciplinas_da_raiz(raiz):
        for p in _arquivos_de_livro(d):
            if any(_pasta_de_livros(parte) for parte in p.relative_to(d).parts[:-1]):
                achados.append(p)
    return achados


def paginas_pdf(p: Path) -> int:
    if p.suffix.lower() != ".pdf" or not shutil.which("pdfinfo"):
        return 0
    m = re.search(rb"Pages:\s+(\d+)", _rodar(["pdfinfo", str(p)]).stdout)
    return int(m.group(1)) if m else 0


def candidatos_talvez(raiz: Path, obvios, paginas_min: int):
    """PDFs longos fora das pastas de livros (só listados; você escolhe quais recolher)."""
    vistos = set(obvios)
    achados = []
    for d in _disciplinas_da_raiz(raiz):
        for p in _arquivos_de_livro(d):
            if p not in vistos:
                n = paginas_pdf(p)
                if n >= paginas_min:
                    achados.append((n, p))
    return sorted(achados, key=lambda t: -t[0])


def _sha256(p: Path) -> str:
    import hashlib
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def cmd_recolher(args):
    """Move livros que estão soltos dentro das pastas de disciplina para livros/ e organiza (ia -> ppc -> local)."""
    livros = Path(args.livros).expanduser().resolve()
    raiz = Path(args.raiz).expanduser().resolve()
    csv_path = Path(args.csv).expanduser()
    if not livros.is_dir() or not raiz.is_dir():
        sys.exit("Pasta de livros ou raiz não encontrada.")

    obvios = candidatos_obvios(raiz)
    if args.varrer:
        print("Dentro de pastas livros/, livro/ ou livros_*/ (seriam recolhidos):")
        print(*[f"  {p.relative_to(raiz)}" for p in obvios] or ["  (nenhum)"], sep="\n")
        print(f"\nPDFs com {args.paginas_min}+ páginas em outros lugares (só listados; passe os que quiser como argumento):")
        talvez = candidatos_talvez(raiz, obvios, args.paginas_min)
        print(*[f"  {n:5d} págs  {p.relative_to(raiz)}" for n, p in talvez] or ["  (nenhum, ou o pdfinfo não está instalado)"],
              sep="\n")
        return

    if args.tudo:
        candidatos = obvios + [p for _, p in candidatos_talvez(raiz, obvios, args.paginas_min)]
    elif args.arquivos:
        candidatos = []
        for a in args.arquivos:
            p = Path(a).expanduser().resolve()
            if not p.is_file() or raiz not in p.parents:
                sys.exit(f"Arquivo não encontrado dentro de {raiz}: {a}")
            candidatos.append(p)
    else:
        candidatos = obvios
    candidatos = [p for p in candidatos if not any(t in str(p.relative_to(raiz)) for t in (args.excluir or []))]
    if not candidatos:
        print("Nenhum livro solto para recolher.")
        return

    existentes = {}
    for q in listar_livros(livros):
        existentes.setdefault(q.stat().st_size, []).append(q)

    plano, duplicados = [], []
    for p in candidatos:
        igual = next((q for q in existentes.get(p.stat().st_size, []) if _sha256(q) == _sha256(p)), None)
        (duplicados if igual else plano).append((p, igual))
    disciplina_de = lambda p: slug(p.relative_to(raiz).parts[0])

    print(f"{len(plano)} livro(s) para recolher:")
    for p, _ in plano:
        print(f"  {p.relative_to(raiz)}   (disciplina: {disciplina_de(p)})")
    for p, igual in duplicados:
        print(f"DUPLICADO (já existe em livros/ como {igual.name}); não movido, apague se quiser: {p.relative_to(raiz)}")
    if args.simular or not plano:
        print("(simulação: nada foi alterado)" if args.simular else "")
        return

    trava = _trava(csv_path)
    if trava is None:
        print("Outra execução já está em andamento; saindo.")
        return
    linhas = ler_csv(csv_path) if csv_path.exists() else []
    novos_rel = set()
    for p, _ in plano:
        destino, n = livros / p.name, 1
        while destino.exists():
            n += 1
            destino = livros / f"{p.stem} ({n}){p.suffix}"
        shutil.move(str(p), str(destino))
        titulo, autor, edicao = adivinhar(destino)
        rel = str(destino.relative_to(livros))
        linhas.append({"arquivo": rel, "disciplinas": disciplina_de(p), "titulo": titulo, "autor": autor,
                       "edicao": edicao, "revisar": "sim", "ignorar": ""})
        novos_rel.add(rel)
        print(f"movido: {p.relative_to(raiz)}  ->  livros/{rel}")
    backup_csv(csv_path)
    gravar_csv(csv_path, linhas)
    organizados, revisar = _organizar(args, livros, raiz, csv_path, novos_rel)
    _fechar(args, livros, csv_path, organizados, revisar)


def main():
    carregar_env()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(line_buffering=True)
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    rclone_padrao = os.environ.get("LIVROS_RCLONE")
    rclone_args_padrao = os.environ.get("LIVROS_RCLONE_ARGS", "")

    def comuns(sp, livros=False, raiz=False, csv_=False):
        if livros:
            sp.add_argument("--livros", default=str(LIVROS_PADRAO), help="pasta com todos os livros")
        if raiz:
            sp.add_argument("--raiz", default=str(RAIZ_PADRAO), help="pasta que contém as pastas de disciplina")
        if csv_:
            sp.add_argument("--csv", default=str(CSV_PADRAO), help="planilha mestra (caches e backups ficam ao lado)")

    m = sub.add_parser("manifesto", help="gera a planilha CSV a partir dos links simbólicos existentes")
    comuns(m, livros=True, raiz=True)
    m.add_argument("--saida", default=str(CSV_PADRAO))
    m.add_argument("--forcar", action="store_true", help="sobrescreve o CSV se ele já existir")
    m.set_defaults(func=cmd_manifesto)

    pa = sub.add_parser("pastas", help="renomeia pastas de disciplina de underline para hífen")
    comuns(pa, raiz=True, csv_=True)
    pa.add_argument("--simular", action="store_true")
    pa.add_argument("--todas", action="store_true", help="renomeia TODAS as pastas do primeiro nível, não só as do CSV")
    pa.add_argument("--incluir", nargs="+", metavar="PASTA",
                    help="pastas extras para renomear (disciplinas que não aparecem no CSV)")
    pa.set_defaults(func=cmd_pastas)

    lo = sub.add_parser("local", help="renomeia os livros e cria <disciplina>/livros/{basica,complementar}/ com links")
    comuns(lo, livros=True, raiz=True, csv_=True)
    lo.add_argument("--simular", action="store_true")
    lo.add_argument("--achatar", action="store_true", help="move todos os livros para a raiz de livros/ (tira das subpastas)")
    lo.add_argument("--aceitar-sem-autor", action="store_true")
    lo.set_defaults(func=cmd_local)

    i = sub.add_parser("ia", help="preenche titulo/autor/edicao lendo as primeiras páginas com a API do Claude")
    comuns(i, livros=True, csv_=True)
    i.add_argument("--modelo", default=MODELO_PADRAO)
    i.add_argument("--paginas", type=int, default=8, help="quantas páginas iniciais ler (padrão 8)")
    i.add_argument("--limite", type=int, default=0, help="processa só os N primeiros (para testar)")
    i.add_argument("--apenas-revisar", action="store_true", help="(já é o padrão) só livros com revisar=sim ou sem título/autor")
    i.add_argument("--todos", action="store_true", help="reprocessa TODOS os livros, inclusive os já conferidos: pode alterar título/autor/edição deles e, depois, os nomes dos arquivos")
    i.add_argument("--refazer", action="store_true", help="ignora o cache de respostas anteriores")
    i.add_argument("--preco-in", type=float, default=2.0, help="(sem efeito: o custo vem do provedor, veja llm.py)")
    i.add_argument("--preco-out", type=float, default=10.0, help="(sem efeito)")
    i.set_defaults(func=cmd_ia)

    q = sub.add_parser("ppc", help="classifica livros em basica/complementar e atribui disciplinas usando o PPC")
    comuns(q, livros=True, raiz=True, csv_=True)
    q.add_argument("--ppc", default=str(PPC_PADRAO), help="PDF ou Markdown do PPC (gere o .md com: python3 -m bibliografia.ppc_markdown ementa.pdf)")
    q.add_argument("--paginas", default="", help="intervalo do PPC a ler, ex.: 40-160 (só a parte das ementas)")
    q.add_argument("--modelo", default=MODELO_PADRAO)
    q.add_argument("--lote", type=int, default=45, help="livros por chamada")
    q.add_argument("--limite", type=int, default=0)
    q.add_argument("--mesclar", action="store_true", help="também acrescenta disciplinas do PPC a livros que já têm")
    q.add_argument("--refazer", action="store_true", help="ignora o cache e reclassifica tudo, inclusive tipos já preenchidos")
    q.set_defaults(func=cmd_ppc)

    li = sub.add_parser("liberar", help="recalcula revisar=sim com as respostas já guardadas (sem API) e explica os que continuam")
    comuns(li, livros=True, raiz=True, csv_=True)
    li.add_argument("--simular", action="store_true", help="só mostra quem seria liberado")
    li.set_defaults(func=cmd_liberar)

    rc = sub.add_parser("reconciliar", help="acerta o caminho 'arquivo' do CSV depois de mover livros à mão")
    comuns(rc, livros=True, csv_=True)
    rc.add_argument("--simular", action="store_true")
    rc.set_defaults(func=cmd_reconciliar)

    dr = sub.add_parser("drive", help="envia livros/ ao Drive e cria os atalhos nas pastas de disciplina (rclone)")
    comuns(dr, livros=True, csv_=True)
    dr.add_argument("--rclone", metavar="REMOTO:CAMINHO", default=rclone_padrao, help="ex.: gdrive:faculdade. Padrão: variável LIVROS_RCLONE")
    dr.add_argument("--rclone-args", default=rclone_args_padrao, help="opções extras do rclone: --rclone-args='--dry-run'")
    dr.add_argument("--sem-podar", action="store_true", help="não remove atalhos obsoletos do Drive (por padrão remove só atalhos, nunca arquivos reais)")
    dr.add_argument("--limpar-copias", action="store_true", help="apaga (para a lixeira) cópias reais de um envio antigo nas pastas de disciplina do Drive")
    dr.add_argument("--simular", action="store_true", help="envia nada e cria nenhum atalho; só mostra")
    dr.set_defaults(func=cmd_drive)

    def opcoes_pipeline(sp):
        comuns(sp, livros=True, raiz=True, csv_=True)
        sp.add_argument("--ppc", default=str(PPC_PADRAO))
        sp.add_argument("--paginas-ppc", default="", help="intervalo do PPC a ler, ex.: 40-160")
        sp.add_argument("--modelo", default=MODELO_PADRAO)
        sp.add_argument("--aplicar-tudo", action="store_true", help="renomeia também os livros com revisar=sim (se tiverem disciplina/título/autor)")
        sp.add_argument("--drive", action="store_true", help="atualiza o Drive depois de organizar (usa --rclone ou LIVROS_RCLONE)")
        sp.add_argument("--rclone", metavar="REMOTO:CAMINHO", default=rclone_padrao, help="envia livros/ ao Drive e cria atalhos nas pastas de disciplina (ex.: gdrive:faculdade). Padrão: variável LIVROS_RCLONE")
        sp.add_argument("--rclone-args", default=rclone_args_padrao, help="opções extras para o rclone; use o sinal de igual: --rclone-args='--copy-links'")
        sp.add_argument("--simular", action="store_true", help="só lista o que seria feito")

    n = sub.add_parser("novos", help="organiza os livros novos jogados em livros/ (ia + ppc + local + Drive)")
    opcoes_pipeline(n)
    n.add_argument("--estavel", type=int, default=20, help="segundos sem alteração para considerar o arquivo pronto (0 desliga)")
    n.set_defaults(func=cmd_novos)

    rec = sub.add_parser("recolher", help="move livros soltos dentro das pastas de disciplina para livros/ e organiza")
    opcoes_pipeline(rec)
    rec.add_argument("arquivos", nargs="*", help="arquivos específicos a recolher (sem isso, recolhe os de pastas livros/, livro/, livros_*/)")
    rec.add_argument("--tudo", action="store_true", help="recolhe tudo que o --varrer lista (as duas listas), menos o que casar com --excluir")
    rec.add_argument("--varrer", action="store_true", help="só lista: os recolhíveis e os PDFs longos de outros lugares")
    rec.add_argument("--paginas-min", type=int, default=120, help="mínimo de páginas para listar no --varrer (precisa do pdfinfo)")
    rec.add_argument("--excluir", nargs="+", metavar="TEXTO", help="ignora arquivos cujo caminho (a partir da raiz) contenha algum destes textos")
    rec.set_defaults(func=cmd_recolher)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
