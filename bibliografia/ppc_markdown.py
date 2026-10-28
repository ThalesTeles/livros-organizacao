"""
Converte o PDF de ementas do PPC em Markdown compacto, sem perder conteúdo.

Por que: o PPC em PDF vai inteiro para a API a cada análise. Em Markdown ele fica sem números de
página, sem quebras de linha no meio de frases e com a mesma estrutura sempre (disciplina, ementa,
referências básicas e complementares), o que gasta menos tokens e é mais fácil para o modelo ler.

    python3 -m bibliografia.ppc_markdown ementa.pdf -o ementa.md --verificar

O que NÃO muda: nenhuma palavra do PPC é removida ou reordenada. O que muda:
  - somem os números de página e as quebras de linha dentro de frases e de referências;
  - o cabeçalho da bibliografia vira sempre **Básica** / **Complementar**;
  - disciplinas com ementa e referências idênticas (estágios, TCC, tópicos especiais) aparecem
    com todos os seus títulos e o conteúdo uma vez só (desligue com --sem-agrupar);
  - remendos explícitos de defeitos de extração do PDF (lista em CORRECOES_DE_TEXTO).
`--verificar` compara letra a letra o texto do PDF com o Markdown e acusa qualquer diferença.
"""
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Sequence

COD_DISCIPLINA = re.compile(r"^([A-Z]{3}\d{5}) - (.+)$")
GRUPO = re.compile(r"^(?:Básico|Complementar) (?:Comum|Específico.*|Eletivo)$")
CABECALHO_BASICA = {"Básica", "Básicas", "Basica"}
CABECALHO_COMPLEMENTAR = {"Complementar", "Complementares"}
CABECALHO_REFERENCIAS = {"Referências", "Bibliografia"}
MESMOS_AUTORES = re.compile(r"^_{3,}\s*")

# Defeitos de extração do PDF corrigidos de forma explícita (texto original -> texto corrigido).
CORRECOES_DE_TEXTO = (
    ("Thomson, 2008.Livro texto:", "Thomson, 2008.\nLivro texto:"),
    ("2009.IEEE Computer Society", "2009.\nIEEE Computer Society"),
    ("distribuídosSoftware", "distribuídos. Software"),
    ("computacionaisComputação", "computacionais. Computação"),
    ("mensagensArquiteturas", "mensagens. Arquiteturas"),
    ("Interface)Amazon Web Services", "Interface). Amazon Web Services"),
)
LETRA_SOLTA_NO_INICIO = re.compile(r"^l(?=[A-ZÀ-Ý]{3,},)")            # 'lHEARN, D.' -> 'HEARN, D.'
PONTO_COLADO = re.compile(r"(?<=[A-Za-zÀ-ÿ0-9])\.(?=[A-ZÀ-Ý][a-zà-ÿ]{2,})")  # 'Computação.São Paulo'


# ----------------------------------------------------------------------------- limpeza do texto bruto

def remover_numeros_de_pagina(linhas: Sequence[str]) -> list[str]:
    """Tira as linhas que são só o número da página (sequência crescente) e os avanços de página."""
    saida, proximo = [], None
    for linha in linhas:
        s = linha.replace("\f", "").strip()
        if re.fullmatch(r"\d{2,3}", s):
            n = int(s)
            if (proximo is None and 40 <= n <= 400) or n == proximo:
                proximo = n + 1
                continue
        saida.append(s)
    return saida


def limpar(texto: str) -> list[str]:
    for antigo, novo in CORRECOES_DE_TEXTO:
        texto = texto.replace(antigo, novo)
    linhas = remover_numeros_de_pagina(texto.splitlines())
    linhas = [LETRA_SOLTA_NO_INICIO.sub("", l) for l in linhas]
    linhas = [PONTO_COLADO.sub(". ", l) for l in linhas]
    return [l for l in linhas if l]


# ----------------------------------------------------------------------------- referências

def _termina_completa(anterior: str) -> bool:
    """Referência terminada: pontuação final, ou um ano no fim (muitas referências do PPC não têm ponto)."""
    a = anterior.rstrip()
    return a.endswith((".", ">", ")", "?", "!", "]")) or bool(re.search(r"(?<!\d)(?:19|20)\d{2}$", a))


def _so_autores(anterior: str) -> bool:
    """'HINES, W. W.; MONTGOMERY, D. C..' — linha com só autores: o título vem na linha seguinte."""
    palavras = re.findall(r"[^\W\d_]+", anterior)
    if not palavras:
        return False
    permitidas = {"et", "al", "e", "and", "org"}
    return (any(len(p) >= 2 and p.isupper() for p in palavras)
            and all(len(p) == 1 or p.isupper() or p.lower() in permitidas for p in palavras))


INICIO_FORTE = re.compile(
    r"^(?:[A-ZÀ-Ý]{2,}(?:[ \-][A-ZÀ-Ý]{2,})*|[A-ZÀ-Ý][a-zà-ÿ]{2,}(?:[ \-][A-ZÀ-Ý][a-zà-ÿ]+)?),\s+"
    r"(?:[A-ZÀ-Ý]\.|[A-ZÀ-Ý](?=[,;])|[A-ZÀ-Ý][a-zà-ÿ]{2,})")                  # 'MATTAR, João'  'POOLE, D,'
INICIO_INICIAIS = re.compile(r"^(?:[A-ZÀ-Ý]\.\s*){1,3}[A-ZÀ-Ý][A-Za-zÀ-ÿ'’\-]+")    # 'M. T. GOODRICH'  'J. Levesque'
INICIO_NOME_EM_CAIXA_ALTA = re.compile(r"^[A-ZÀ-Ý]{2,}(?:\s+(?:&|E|[A-ZÀ-Ý]{2,})){1,5}\.\s")  # 'KIM HELDMAN. Gerência'

# Linhas que continuam a referência anterior: cidade, editora ou edição ('São Paulo, 2000.', 'Pearson, 2010.').
_CIDADES = ("São Paulo|Rio de Janeiro|Porto Alegre|Belo Horizonte|Campina Grande|Brasília|Petrópolis|Lisboa|"
            "Florianópolis|New York|Upper Saddle River|Natal|Teresina|Belém|Curitiba|Campinas|Santa Barbara|"
            "Palmas|Montivideo|London|Londres|Cambridge|Boston|Los Alamitos|Paulo|Janeiro|Alegre")
_EDITORAS = ("Editora|Pearson|Campus|McGraw|Prentice|Addison|Thomson|Bookman|LTC|Atlas|Elsevier|Makron|Saraiva|"
             "Érica|Erica|Novatec|John Wiley|Wiley|Springer|Vozes|Livros Técnicos|Harper|Harbra|IMPA|SBM|Edusp|EDUSP|"
             "Sagra|Brasport|Cengage|Penso|Autores Associados|Summus|Senac|Alta [Bb]ooks|Academic Press|Morgan|"
             "Peachpit|Apress|Packt|Manning|Sams|Wrox|O'Reilly|Chapman|Pioneira|Blücher|Parábola|Autêntica|"
             "Martins Fontes|Ática|Brasiliense|Loyola|Cortez|Gradiva|Lucerne|Global|FGV|Visual Books|Reichmann|"
             "Cambridge University Press|Hall")
_EDICAO = (r"\d+\s?[ªa°]?\s?(?:ed|Ed|edição|Edição)\b|(?:Primeira|Segunda|Terceira|Quarta|Quinta|Sexta|Sétima|"
           r"Oitava|Nona|Décima)\s+[Ee]di[cç][aã]o|Ed\.|Ed,|ed\.")
CONTINUACAO = re.compile(rf"^(?:{_CIDADES}|{_EDITORAS}|{_EDICAO})(?![A-Za-zÀ-ÿ])")


def _inicio_forte(linha: str) -> bool:
    return bool(INICIO_FORTE.match(linha) or INICIO_INICIAIS.match(linha) or INICIO_NOME_EM_CAIXA_ALTA.match(linha))


def _inicia_nova_referencia(anterior: str, linha: str) -> bool:
    if MESMOS_AUTORES.match(linha) or linha.startswith("Livro texto") or anterior == "Livro texto:":
        return True
    if _termina_completa(anterior):
        if _so_autores(anterior) or CONTINUACAO.match(linha):
            return False
        return linha[:1].isupper() or linha[:1] in "“\"«"
    # Linha anterior não terminou: em geral é continuação. Exceção: terminou em dígito (ano ou edição
    # sem ponto final) e a próxima linha começa como uma referência nova.
    return anterior[-1:].isdigit() and not CONTINUACAO.match(linha) and _inicio_forte(linha)


def _unir(anterior: str, linha: str) -> str:
    return anterior + linha if anterior.endswith("-") and anterior[-2:-1].isalpha() else anterior + " " + linha


def segmentar_referencias(linhas: Sequence[str]) -> list[str]:
    """Junta as linhas quebradas do PDF em uma referência por item."""
    itens: list[str] = []
    for linha in linhas:
        if itens and not _inicia_nova_referencia(itens[-1], linha):
            itens[-1] = _unir(itens[-1], linha)
        else:
            itens.append(linha)
    return [MESMOS_AUTORES.sub("[mesmos autores] ", i) for i in itens]


# ----------------------------------------------------------------------------- estrutura

@dataclass
class Disciplina:
    codigo: str
    nome: str
    ementa: str = ""
    referencias: dict[str, list[str]] = field(default_factory=dict)   # '' | 'Básica' | 'Complementar'

    def conteudo(self):
        return (self.ementa, tuple((k, tuple(v)) for k, v in self.referencias.items()))


@dataclass
class Grupo:
    nome: str
    disciplinas: list[Disciplina] = field(default_factory=list)


@dataclass
class Documento:
    titulo: str
    grupos: list[Grupo] = field(default_factory=list)


def _juntar_linhas(linhas: Sequence[str]) -> str:
    texto = ""
    for l in linhas:
        texto = _unir(texto, l) if texto else l
    return texto


def interpretar(linhas: Sequence[str]) -> Documento:
    doc = Documento(titulo=linhas[0] if linhas else "")
    grupo: Optional[Grupo] = None
    disc: Optional[Disciplina] = None
    estado, secao = "", ""
    buffers: dict[str, list[str]] = {}

    def fechar():
        nonlocal disc, estado, secao, buffers
        if disc is not None:
            disc.referencias = {k: segmentar_referencias(v) for k, v in buffers.items() if v}
        disc, estado, secao, buffers = None, "", "", {}

    for linha in linhas[1:]:
        if GRUPO.match(linha):
            fechar()
            grupo = Grupo(linha)
            doc.grupos.append(grupo)
            continue
        m = COD_DISCIPLINA.match(linha)
        if m:
            fechar()
            if grupo is None:
                grupo = Grupo("")
                doc.grupos.append(grupo)
            disc = Disciplina(m.group(1), m.group(2))
            grupo.disciplinas.append(disc)
            continue
        if disc is None:
            continue
        if linha == "Ementa" and estado == "":
            estado, buffers = "ementa", {}
            disc._ementa_linhas = []                       # type: ignore[attr-defined]
        elif linha in CABECALHO_REFERENCIAS and estado in ("ementa", "refs"):
            if estado == "ementa":
                disc.ementa = _juntar_linhas(disc._ementa_linhas)  # type: ignore[attr-defined]
            estado, secao = "refs", ""
        elif estado == "ementa":
            disc._ementa_linhas.append(linha)              # type: ignore[attr-defined]
        elif estado == "refs":
            if linha in CABECALHO_BASICA:
                secao = "Básica"
            elif linha in CABECALHO_COMPLEMENTAR:
                secao = "Complementar"
            else:
                buffers.setdefault(secao, []).append(linha)
    fechar()
    return doc


# ----------------------------------------------------------------------------- saída

def _blocos(grupo: Grupo, agrupar: bool) -> list[list[Disciplina]]:
    blocos: list[list[Disciplina]] = []
    for d in grupo.disciplinas:
        if agrupar and blocos and blocos[-1][0].conteudo() == d.conteudo():
            blocos[-1].append(d)
        else:
            blocos.append([d])
    return blocos


def renderizar(doc: Documento, *, agrupar: bool = True, so_referencias: bool = False) -> str:
    saida = [f"# {doc.titulo}"]
    for grupo in doc.grupos:
        if grupo.nome:
            saida += ["", f"# {grupo.nome}"]
        for bloco in _blocos(grupo, agrupar):
            saida.append("")
            saida += [f"## {d.codigo} - {d.nome}" for d in bloco]
            d = bloco[0]
            if d.ementa and not so_referencias:
                saida.append(f"**Ementa:** {d.ementa}")
            for secao, itens in d.referencias.items():
                saida += ["", f"**{secao or 'Referências'}:**" if secao else "**Referências:**"]
                if len(itens) == 1 and itens[0].startswith("A ser definid"):
                    saida[-1] = f"**Referências:** {itens[0]}"
                else:
                    saida += [f"- {i}" for i in itens]
    return "\n".join(saida) + "\n"


def converter(texto_bruto: str, *, agrupar: bool = True, so_referencias: bool = False) -> str:
    return renderizar(interpretar(limpar(texto_bruto)), agrupar=agrupar, so_referencias=so_referencias)


# ----------------------------------------------------------------------------- verificação

PALAVRAS_DE_ROTULO = ("ementa", "referencias", "bibliografia", "basica", "basicas", "complementar", "complementares")


def _letras(texto: str) -> str:
    """Só letras e números, minúsculos e sem acento, na ordem original."""
    import unicodedata
    t = unicodedata.normalize("NFKD", texto)
    return re.sub(r"[^a-z0-9]+", "", "".join(c for c in t if not unicodedata.combining(c)).lower())


def verificar_preservacao(texto_bruto: str, markdown: str) -> list[str]:
    """Compara o texto do PDF (já sem números de página) com o Markdown gerado SEM agrupar.
    Só letras e números entram na comparação, na ordem; os rótulos Ementa/Referências/Básica/Complementar
    e o '[mesmos autores]' são ignorados nos dois lados. Devolve as diferenças (vazia = nada se perdeu)."""
    rotulos = ("Ementa", "Referências", "Bibliografia", "Básica", "Básicas", "Basica", "Complementar", "Complementares")
    origem = "\n".join(limpar(texto_bruto))
    origem = re.sub(r"_{3,}", "", origem)
    origem = re.sub(r"(?m)^(?:" + "|".join(rotulos) + r")$", "", origem)
    destino = markdown.replace("[mesmos autores]", "")
    destino = re.sub(r"\*\*(?:Ementa|Referências|Básica|Complementar):\*\*", "", destino)
    a, b = _letras(origem), _letras(destino)
    if a == b:
        return []
    i = next((k for k in range(min(len(a), len(b))) if a[k] != b[k]), min(len(a), len(b)))
    return [f"primeira diferença na posição {i}: PDF ...{a[max(0, i - 30):i + 30]}... | MD ...{b[max(0, i - 30):i + 30]}..."]


# ----------------------------------------------------------------------------- linha de comando

def main(argv: Optional[Sequence[str]] = None) -> int:
    p = argparse.ArgumentParser(prog="python3 -m bibliografia.ppc_markdown",
                                description="Converte o PDF de ementas do PPC em Markdown compacto.")
    p.add_argument("entrada", help="PDF do PPC (ou .txt já extraído)")
    p.add_argument("-o", "--saida", help="arquivo .md de saída (padrão: mesmo nome, extensão .md)")
    p.add_argument("--so-referencias", action="store_true",
                   help="omite as ementas e mantém só as referências (para a análise de livros faltantes)")
    p.add_argument("--sem-agrupar", action="store_true", help="repete o conteúdo de disciplinas idênticas")
    p.add_argument("--verificar", action="store_true", help="confere letra a letra que nada se perdeu")
    args = p.parse_args(argv)

    entrada = Path(args.entrada).expanduser()
    if entrada.suffix.lower() == ".pdf":
        import nucleo
        bruto = nucleo.texto_ppc(entrada, "")
    else:
        bruto = entrada.read_text(encoding="utf-8")
    md = converter(bruto, agrupar=not args.sem_agrupar, so_referencias=args.so_referencias)
    saida = Path(args.saida).expanduser() if args.saida else entrada.with_suffix(".md")
    saida.write_text(md, encoding="utf-8")
    print(f"{saida}: {len(md):,} caracteres (PDF extraído: {len(bruto):,}; "
          f"{100 * (1 - len(md) / len(bruto)):.0f}% menor)")
    if args.verificar:
        completo = converter(bruto, agrupar=False)
        problemas = verificar_preservacao(bruto, completo)
        print("Verificação: " + ("OK, nenhuma letra perdida." if not problemas else "DIFERENÇAS:"))
        for pr in problemas:
            print("  ", pr)
        return 1 if problemas else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
