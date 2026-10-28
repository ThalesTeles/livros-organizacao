"""Tipos de dados do pacote."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Acesso(Enum):
    LIVRE = "livre"              # domínio público / acesso aberto: pode ser baixado
    EMPRESTIMO = "emprestimo"    # empréstimo digital (precisa de conta e devolução)
    A_VENDA = "a_venda"          # e-book à venda
    PREVIA = "previa"            # só trechos


@dataclass(frozen=True)
class ObraFaltante:
    titulo: str
    autores: str = ""
    edicao: str = ""
    consulta: str = ""                       # termo de busca já pronto (coluna `termo_de_busca`, linha `buscar:`)
    disciplinas: tuple[str, ...] = ()
    tipos: tuple[str, ...] = ()              # 'basica' e/ou 'complementar'

    @property
    def prioridade(self) -> int:
        return 0 if "basica" in self.tipos else 1


@dataclass(frozen=True)
class Achado:
    fonte: str                               # 'Open Library' | 'Google Livros'
    acesso: Acesso
    titulo: str
    autores: str
    url: str                                 # página do livro
    url_download: str = ""                   # só quando acesso == LIVRE
    obs: str = ""                            # preço, licença, "empréstimo de 1 hora"...


@dataclass
class Resultado:
    obra: ObraFaltante
    achados: list[Achado] = field(default_factory=list)
    links: dict[str, str] = field(default_factory=dict)
    baixado_em: str = ""                     # caminho do arquivo, se `--baixar` baixou

    def com_acesso(self, acesso: Acesso) -> list[Achado]:
        return [a for a in self.achados if a.acesso is acesso]
