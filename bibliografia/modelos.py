"""Dados do domínio. Sem I/O e sem dependências: tudo aqui é imutável e fácil de testar."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

BASICA = "basica"
COMPLEMENTAR = "complementar"
TIPOS = (BASICA, COMPLEMENTAR)
ROTULO_TIPO = {BASICA: "básica", COMPLEMENTAR: "complementar"}            # "bibliografia básica"
ROTULO_LIVRO = {BASICA: "básico", COMPLEMENTAR: "complementar"}           # "livro básico"


@dataclass(frozen=True)
class Obra:
    """Um item da bibliografia, como aparece no PPC."""
    titulo: str
    autores: str = ""
    edicao: str = ""
    ano: Optional[int] = None

    def descricao(self) -> str:
        partes = [self.titulo]
        if self.autores:
            partes.append(self.autores)
        if self.edicao:
            partes.append(f"{self.edicao} ed." if self.edicao.isdigit() else self.edicao)
        if self.ano:
            partes.append(str(self.ano))
        return " — ".join(partes)


@dataclass(frozen=True)
class RequisitoDisciplina:
    """O que o PPC pede para uma disciplina (de um tipo de bibliografia)."""
    pasta: str          # nome da pasta local (slug)
    nome: str           # nome da disciplina no PPC
    obras: tuple[Obra, ...] = ()


@dataclass(frozen=True)
class Livro:
    """Um livro do acervo (uma linha do livros.csv)."""
    arquivo: str
    titulo: str
    autor: str
    edicao: str
    vinculos: tuple[tuple[str, str], ...] = ()   # (pasta, tipo)

    def tipo_em(self, pasta: str) -> Optional[str]:
        for p, tipo in self.vinculos:
            if p == pasta:
                return tipo
        return None


@dataclass(frozen=True)
class Equivalencia:
    """Decisão sua: esta obra do PPC é este livro do acervo (outra edição, tradução, título diferente...)."""
    obra: str            # trecho do título como o PPC escreve (sem diferenciar maiúsculas e acentos)
    arquivo: str         # nome do arquivo em livros/ (coluna `arquivo` do livros.csv)
    pasta: str = ""      # opcional: vale só para esta disciplina


class Situacao(Enum):
    OK = "ok"                          # está no acervo e vinculado à disciplina com o tipo certo
    TIPO_DIFERENTE = "tipo_diferente"  # vinculado à disciplina, mas com outro tipo
    SEM_VINCULO = "sem_vinculo"        # está no acervo, mas não vinculado a esta disciplina
    AUSENTE = "ausente"                # não está no acervo


@dataclass(frozen=True)
class Resultado:
    obra: Obra
    situacao: Situacao
    livro: Optional[Livro] = None              # melhor correspondência no acervo
    outra_edicao: bool = False                 # o acervo tem a obra, mas em outra edição
    possiveis: tuple[Livro, ...] = ()          # só quando AUSENTE: candidatos para conferir à mão
    por_autor: bool = False                    # OK por ser dos mesmos autores e já estar vinculado (tradução?)


@dataclass(frozen=True)
class RelatorioDisciplina:
    pasta: str
    nome: str
    tipo: str
    tem_pasta: bool
    no_acervo: int                             # livros do acervo ligados a ela com este tipo
    resultados: tuple[Resultado, ...]

    def _com(self, *situacoes: Situacao) -> tuple[Resultado, ...]:
        return tuple(r for r in self.resultados if r.situacao in situacoes)

    @property
    def ausentes(self):
        return self._com(Situacao.AUSENTE)

    @property
    def ajustes(self):
        return self._com(Situacao.TIPO_DIFERENTE, Situacao.SEM_VINCULO)

    @property
    def prontos(self):
        return self._com(Situacao.OK)
