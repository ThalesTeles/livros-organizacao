"""
Comparação entre uma obra do PPC e os livros do acervo. Funções puras, sem I/O.

A decisão combina três sinais: semelhança de título, sobreposição de autores e conflito de volume.
Edição NÃO impede o casamento (o PPC costuma citar edições antigas); ela só é sinalizada à parte.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Optional, Sequence

from .modelos import Livro, Obra

PALAVRAS_VAZIAS = frozenset(
    "a o as os um uma de da do das dos e em no na nos nas para por com sem ao aos "
    "the of and to for in on an with et y le la les des du el los".split())
PALAVRAS_DE_VOLUME = frozenset("vol volume volumes v tomo".split())
PALAVRAS_DE_AUTOR = frozenset("et al dos das da de do filho junior jr neto and".split())
# "e"/"and" entre autores, mas não a inicial do meio ("Charles E. Leiserson")
SEPARADOR_DE_AUTORES = r",|\be\b(?!\.)|\band\b|&"


def normalizar(texto: str) -> str:
    """minúsculas, sem acento, só letras/números separados por espaço."""
    texto = unicodedata.normalize("NFKD", texto or "")
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", texto.lower()).strip()


def tokens(texto: str) -> frozenset[str]:
    return frozenset(t for t in normalizar(texto).split() if t not in PALAVRAS_VAZIAS)


def _lista_de_tokens(texto: str) -> list[str]:
    """Palavras que identificam a obra: sem artigos/preposições, números e 'vol' (volume é checado à parte)."""
    return [t for t in normalizar(texto).split()
            if t not in PALAVRAS_VAZIAS and t not in PALAVRAS_DE_VOLUME and not t.isdigit()]


def _parecidos(x: str, y: str) -> bool:
    """Mesma palavra com grafia, plural ou idioma próximos: 'projeto'~'projetos', 'algorithms'~'algoritmos'."""
    if x == y:
        return True
    if min(len(x), len(y)) < 4:
        return False
    return x in y or y in x or SequenceMatcher(None, x, y).ratio() >= 0.8     # 'withopengl' ~ 'opengl'


def _palavras_exclusivas(ta: Sequence[str], tb: Sequence[str]) -> tuple[int, int, int]:
    """(pareadas, só em a, só em b), pareando palavras iguais ou parecidas."""
    livres = list(dict.fromkeys(tb))
    pareadas = 0
    so_a = 0
    for x in dict.fromkeys(ta):
        par = next((y for y in livres if _parecidos(x, y)), None)
        if par is None:
            so_a += 1
        else:
            pareadas += 1
            livres.remove(par)
    return pareadas, so_a, len(livres)


def similaridade_titulo(a: str, b: str) -> float:
    na, nb = normalizar(a), normalizar(b)
    la, lb = _lista_de_tokens(a), _lista_de_tokens(b)
    if not na or not nb or not la or not lb:
        return 0.0
    pareadas, so_a, so_b = _palavras_exclusivas(la, lb)
    jaccard = pareadas / (pareadas + so_a + so_b)
    if so_a and so_b:
        # Cada título tem palavras que o outro não tem ('C: Como Programar' x 'Java: Como Programar',
        # 'Redes de Computadores' x 'Organização Estruturada de Computadores'): é outra obra, a não ser
        # que quase tudo coincida. Aqui a semelhança de letras engana; vale só a proporção de palavras.
        return 0.9 * jaccard
    # Um título contém o outro. Só conta como a mesma obra se o curto for o COMEÇO do longo (subtítulo
    # acrescentado: 'Algoritmos' x 'Algoritmos: teoria e prática'). 'Álgebra Linear' no fim de
    # 'Geometria Analítica e Álgebra Linear' é outro livro.
    curto, longo = (la, lb) if len(la) <= len(lb) else (lb, la)
    prefixo = len(curto) >= 2 and all(_parecidos(x, y) for x, y in zip(curto, longo))
    sequencia = SequenceMatcher(None, na, nb).ratio()
    if not prefixo and len(curto) < len(longo) and jaccard < 1:
        return 0.9 * jaccard
    return max(sequencia, jaccard, 0.9 if prefixo else 0.0)


def titulo_principal(titulo: str) -> str:
    """Parte antes do subtítulo: 'Lógica para Ciência da Computação: Uma introdução concisa' -> 'Lógica para ...'."""
    principal = re.split(r"\s*[:(]\s*|\s+[-–]\s+", titulo or "", maxsplit=1)[0]
    return principal if len(_lista_de_tokens(principal)) >= 2 else titulo


def _sem_et_al(texto: str) -> str:
    return re.sub(r"\bet\.?\s*al\.?", " ", texto or "", flags=re.IGNORECASE)


def _sobrenomes_do_trecho(trecho: str) -> set[str]:
    return {t for t in normalizar(trecho).split() if len(t) >= 3 and t not in PALAVRAS_DE_AUTOR}


def _parece_sobrenome_virgula_nome(texto: str) -> bool:
    """'CORMEN, Thomas H.' (sim) x 'Thomas H. Cormen, Charles Leiserson' (não: tem inicial antes da vírgula)."""
    antes = texto.split(",")[0].split()
    return 0 < len(antes) <= 2 and not any(len(normalizar(p)) == 1 for p in antes)


def sobrenomes_do_ppc(autores: str) -> frozenset[str]:
    """Autores como no PPC: 'CORMEN, Thomas H.; LEISERSON, C.' ou 'Thomas Cormen, Charles Leiserson'."""
    texto = _sem_et_al(autores).strip()
    if not texto:
        return frozenset()
    saida: set[str] = set()
    if ";" in texto:
        for parte in texto.split(";"):
            saida |= _sobrenomes_do_trecho(parte.split(",")[0])
    elif texto.count(",") == 1 and _parece_sobrenome_virgula_nome(texto):
        saida |= _sobrenomes_do_trecho(texto.split(",")[0])          # 'SOBRENOME, Nome' (um autor)
    else:
        for parte in re.split(SEPARADOR_DE_AUTORES, texto, flags=re.IGNORECASE):
            palavras = normalizar(parte).split()
            if palavras:
                saida |= _sobrenomes_do_trecho(palavras[-1])           # 'Nome Sobrenome'
    return frozenset(saida)


def sobrenomes_do_livro(autor: str) -> frozenset[str]:
    """Campo `autor` do CSV: 'Cormen et al', 'Marconi e Lakatos'."""
    saida: set[str] = set()
    for parte in re.split(SEPARADOR_DE_AUTORES, _sem_et_al(autor), flags=re.IGNORECASE):
        saida |= _sobrenomes_do_trecho(parte)
    return frozenset(saida)


def _nomes_do_ppc(autores: str) -> frozenset[str]:
    """Todas as palavras de nome dos autores do PPC (sobrenomes e prenomes): o PPC cita autores de jeitos
    variados ('FINGER, MELO E SILVA', 'Pressman. Rogers'), então qualquer palavra pode ser o sobrenome."""
    return frozenset(sobrenomes_do_ppc(autores)) | frozenset(_sobrenomes_do_trecho(_sem_et_al(autores)))


def _siglas_do_ppc(autores: str) -> frozenset[str]:
    """'PMI', 'ABNT' (2 a 6 maiúsculas seguidas)."""
    return frozenset(s.lower() for s in re.findall(r"\b[A-Z]{2,6}\b", autores or ""))


def _mesmo_sobrenome(a: str, b: str) -> bool:
    """Igual, ou com erro de digitação comum no PPC: 'leithould' x 'leithold', 'tanembaum' x 'tanenbaum'."""
    if a == b:
        return True
    return min(len(a), len(b)) >= 6 and SequenceMatcher(None, a, b).ratio() >= 0.85


def sobreposicao_autores(autores_ppc: str, autor_livro: str) -> float:
    """Fração dos sobrenomes do livro que aparecem nos autores do PPC (0 se algum lado não tem autor)."""
    do_livro = sobrenomes_do_livro(autor_livro)
    nomes = _nomes_do_ppc(autores_ppc)
    if not do_livro or not nomes:
        return 0.0
    achados = sum(1 for s in do_livro if any(_mesmo_sobrenome(s, n) for n in nomes))
    if achados == 0:                                   # sigla: 'PMI' = Project Management Institute
        palavras = [p for p in normalizar(_sem_et_al(autor_livro)).split() if p not in PALAVRAS_DE_AUTOR]
        if len(palavras) >= 2 and "".join(p[0] for p in palavras) in _siglas_do_ppc(autores_ppc):
            return 1.0
    return achados / len(do_livro)


def numero_edicao(texto: str) -> Optional[int]:
    m = re.search(r"\d+", normalizar(texto))
    return int(m.group()) if m else None


def numero_volume(texto: str) -> Optional[int]:
    m = re.search(r"\b(?:vol|volume|v|tomo)\s*(\d+)\b", normalizar(texto))
    return int(m.group(1)) if m else None


def edicao_difere(obra: Obra, livro: Livro) -> bool:
    a, b = numero_edicao(obra.edicao), numero_edicao(livro.edicao)
    return a is not None and b is not None and a != b


@dataclass(frozen=True)
class Correspondencia:
    livro: Livro
    titulo: float
    autor: float

    @property
    def pontos(self) -> float:
        return 0.7 * self.titulo + 0.3 * self.autor


class Casador:
    """Encontra, no acervo, os livros que correspondem a uma obra do PPC."""

    def __init__(self, acervo: Sequence[Livro], *, limiar_titulo: float = 0.75, limiar_misto: float = 0.5,
                 limiar_autor: float = 0.5, limiar_possivel: float = 0.75):
        self.acervo = tuple(acervo)
        self.limiar_titulo = limiar_titulo
        self.limiar_misto = limiar_misto
        self.limiar_autor = limiar_autor
        self.limiar_possivel = limiar_possivel

    def _medir(self, obra: Obra, livro: Livro) -> Optional[Correspondencia]:
        v_obra = numero_volume(obra.titulo)
        v_livro = numero_volume(livro.titulo)
        if v_obra is not None and v_livro is not None and v_obra != v_livro:
            return None                                   # volumes diferentes: não é a mesma obra
        autor = sobreposicao_autores(obra.autores, livro.autor)
        titulo = similaridade_titulo(obra.titulo, livro.titulo)
        if autor >= 0.999 and titulo < self.limiar_titulo:
            # mesmos autores: compara também sem os subtítulos ('...: Uma introdução concisa' x '... e Áreas Afins')
            titulo = max(titulo, similaridade_titulo(titulo_principal(obra.titulo), titulo_principal(livro.titulo)))
        return Correspondencia(livro, titulo, autor)

    def _valida(self, obra: Obra, livro: Livro, c: Correspondencia) -> bool:
        sem_autor = not _nomes_do_ppc(obra.autores) or not sobrenomes_do_livro(livro.autor)   # 'COPPIN B.' tem autor
        if c.titulo >= self.limiar_titulo and (c.autor > 0 or sem_autor):
            return True
        return c.titulo >= self.limiar_misto and c.autor >= self.limiar_autor

    def correspondencias(self, obra: Obra) -> list[Correspondencia]:
        achadas = []
        for livro in self.acervo:
            c = self._medir(obra, livro)
            if c is not None and self._valida(obra, livro, c):
                achadas.append(c)
        return sorted(achadas, key=lambda c: -c.pontos)

    def possiveis(self, obra: Obra, limite: int = 3) -> list[Livro]:
        """Candidatos que NÃO casaram, mas têm os mesmos autores (ex.: título em outro idioma)."""
        validos = {c.livro.arquivo for c in self.correspondencias(obra)}
        candidatos = []
        for livro in self.acervo:
            if livro.arquivo in validos:
                continue
            c = self._medir(obra, livro)
            if c is not None and c.autor >= self.limiar_possivel and c.titulo >= 0.1:
                candidatos.append(c)
        return [c.livro for c in sorted(candidatos, key=lambda c: -c.pontos)[:limite]]
