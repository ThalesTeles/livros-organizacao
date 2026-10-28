"""
Núcleo compartilhado: configuração de caminhos, nomes (slug), planilha CSV, caches, backups,
disciplinas/tipos (`algoritmos:basica|...`), leitura de texto do PPC e carga do .env.

É usado por `organizar_livros.py` (a ferramenta que organiza e envia os livros) e pelo pacote
`bibliografia` (que procura livros faltantes). Não depende de nenhum dos dois.
"""
import csv
import json
import os
import re
import shutil
import subprocess
import sys
import unicodedata
from datetime import datetime
from pathlib import Path

RAIZ_PADRAO = Path(os.environ.get("LIVROS_RAIZ", "~/documents/estudos/faculdade")).expanduser()
LIVROS_PADRAO = RAIZ_PADRAO / "livros"
META_PADRAO = RAIZ_PADRAO / "livros-organizacao"
CSV_PADRAO = META_PADRAO / "livros.csv"
_PPC_PDF = RAIZ_PADRAO / "informacoes-do-curso" / "ementa.pdf"
# Se existir a versão em Markdown (python3 -m bibliografia.ppc_markdown), ela passa a ser o padrão:
# é mais curta e gasta menos tokens a cada chamada.
PPC_PADRAO = _PPC_PDF.with_suffix(".md") if _PPC_PDF.with_suffix(".md").exists() else _PPC_PDF
# "auto": cada provedor usa o seu padrão (Gemini: gemini-2.5-flash; Claude: Haiku 4.5). Veja llm.py.
MODELO_PADRAO = "auto"

EXTENSOES = {".pdf", ".epub", ".djvu", ".mobi", ".html"}
CAMPOS = ["arquivo", "disciplinas", "titulo", "autor", "edicao", "revisar", "ignorar"]
TIPOS = ("basica", "complementar")
NAO_SAO_DISCIPLINA = {"livros", META_PADRAO.name, "informacoes-do-curso", "modelos", "atividades-academicas", "artigos"}


def slug(texto: str) -> str:
    """minúsculo, sem acento, palavras separadas por hífen (underline fica só como separador de campos)."""
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = re.sub(r"[^a-zA-Z0-9]+", "-", texto.lower())
    return texto.strip("-")


def ler_csv(caminho):
    with open(caminho, newline="", encoding="utf-8-sig") as f:
        linhas = list(csv.DictReader(f, delimiter=";"))
    for l in linhas:
        for c in CAMPOS:
            l[c] = l.get(c) or ""
    return linhas


def gravar_csv(caminho, linhas):
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with open(caminho, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=CAMPOS, delimiter=";", extrasaction="ignore")
        w.writeheader()
        w.writerows(linhas)


def caminho_cache(csv_path, nome):
    """Os caches ficam em <pasta do csv>/cache/<nome do csv>.<ia|ppc>_cache.json"""
    csv_path = Path(csv_path)
    return csv_path.parent / "cache" / f"{csv_path.stem}.{nome}_cache.json"


def ler_cache(caminho, ignorar=False):
    if ignorar or not caminho.exists():
        return {}
    return json.loads(caminho.read_text(encoding="utf-8"))


def gravar_cache(caminho, cache):
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")


def backup_csv(csv_path, manter=10):
    """Copia o CSV para <pasta do csv>/backups/ com data e hora e mantém só as `manter` últimas."""
    csv_path = Path(csv_path)
    if not csv_path.exists():
        return None
    pasta = csv_path.parent / "backups"
    pasta.mkdir(parents=True, exist_ok=True)
    base = f"{csv_path.stem}.{datetime.now():%Y%m%d-%H%M%S}"
    destino, n = pasta / f"{base}.csv.bak", 1
    while destino.exists():
        n += 1
        destino = pasta / f"{base}-{n}.csv.bak"
    shutil.copy2(csv_path, destino)
    for velho in sorted(pasta.glob(f"{csv_path.stem}.*.csv.bak"))[:-manter]:
        velho.unlink()
    return destino


def parse_disciplinas(texto):
    """'a:basica|b' -> [('a','basica'), ('b','')]   (tipo vazio = ainda não classificado)"""
    pares = []
    for parte in (texto or "").split("|"):
        nome, _, tipo = parte.strip().partition(":")
        nome = nome.strip()
        if nome:
            tipo = slug(tipo)
            pares.append((nome, tipo if tipo in TIPOS else ""))
    return pares


def formatar_disciplinas(pares):
    return "|".join(f"{n}:{t}" if t else n for n, t in pares)


def unir_pares(pares):
    """Junta repetidas (mesma disciplina, comparando por slug). Entre tipos diferentes: basica > complementar > vazio."""
    peso = {"": 0, "complementar": 1, "basica": 2}
    achados = {}
    for nome, tipo in pares:
        k = slug(nome)
        if k not in achados:
            achados[k] = (nome, tipo)
        elif peso[tipo] > peso[achados[k][1]]:
            achados[k] = (achados[k][0], tipo)
    return list(achados.values())


def disciplinas_do_csv(linhas):
    nomes = set()
    for l in linhas:
        if not l["ignorar"].strip():
            nomes.update(n for n, _ in parse_disciplinas(l["disciplinas"]))
    return nomes


def rodar(cmd):
    return subprocess.run(cmd, capture_output=True, check=False)


def texto_ppc(caminho: Path, paginas: str) -> str:
    """Texto do PPC: lê direto um .md/.txt; para PDF usa o pdftotext (com intervalo de páginas opcional)."""
    caminho = Path(caminho)
    if caminho.suffix.lower() in (".md", ".txt"):
        if paginas:
            print("Aviso: --paginas só vale para PDF; usando o arquivo inteiro.", file=sys.stderr)
        return caminho.read_text(encoding="utf-8")
    if not shutil.which("pdftotext"):
        sys.exit("Precisa do pdftotext (pacote poppler):  sudo pacman -S poppler")
    cmd = ["pdftotext"]
    if paginas:
        a, b = paginas.split("-")
        cmd += ["-f", a, "-l", b]
    cmd += [str(caminho), "-"]
    return rodar(cmd).stdout.decode("utf-8", "ignore")


def pastas_disciplina(raiz: Path):
    return sorted(d.name for d in raiz.iterdir()
                  if d.is_dir() and not d.is_symlink() and not d.name.startswith(".")
                  and d.name not in NAO_SAO_DISCIPLINA)


def carregar_env():
    """Carrega GEMINI_API_KEY, ANTHROPIC_API_KEY (e outras) de arquivos .env, sem sobrescrever o que já está no ambiente.
    Procura, nesta ordem: ./.env, <livros-organizacao>/.env, <raiz>/.env, ~/.config/livros-organizar.env"""
    candidatos = [Path.cwd() / ".env", META_PADRAO / ".env", RAIZ_PADRAO / ".env",
                  Path("~/.config/livros-organizar.env").expanduser()]
    for arq in candidatos:
        if not arq.is_file():
            continue
        for linha in arq.read_text(encoding="utf-8").splitlines():
            linha = linha.strip()
            if not linha or linha.startswith("#") or "=" not in linha:
                continue
            chave, _, valor = linha.removeprefix("export ").partition("=")
            valor = valor.strip().strip("'\"")
            if chave.strip() and valor:
                os.environ.setdefault(chave.strip(), valor)
