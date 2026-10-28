"""
Serviço central: compara o que o PPC pede com o que existe no acervo.

Recebe tudo pronto (acervo, requisitos) e devolve dados; não lê arquivos nem fala com a API.
"""
from __future__ import annotations

from typing import Collection, Optional, Sequence

from .casamento import Casador, Correspondencia, edicao_difere, normalizar
from .modelos import Equivalencia, Livro, RelatorioDisciplina, RequisitoDisciplina, Resultado, Situacao


class AnalisadorDeLacunas:
    def __init__(self, acervo: Sequence[Livro], casador: Optional[Casador] = None,
                 equivalencias: Sequence[Equivalencia] = ()):
        self.acervo = tuple(acervo)
        self.casador = casador or Casador(self.acervo)
        por_arquivo = {l.arquivo: l for l in self.acervo}
        self.equivalencias = [(e, por_arquivo[e.arquivo]) for e in equivalencias if e.arquivo in por_arquivo]
        self.avisos = [f"equivalência ignorada: o livro `{e.arquivo}` não está no acervo (livros.csv)"
                       for e in equivalencias if e.arquivo not in por_arquivo]

    def _manuais(self, pasta: str, obra) -> list:
        titulo = normalizar(obra.titulo)
        return [Correspondencia(livro, 1.0, 1.0) for e, livro in self.equivalencias
                if (not e.pasta or e.pasta == pasta) and normalizar(e.obra) in titulo]

    def analisar(self, tipo: str, requisitos: Sequence[RequisitoDisciplina],
                 pastas_existentes: Collection[str] = ()) -> list[RelatorioDisciplina]:
        relatorios = []
        for req in requisitos:
            resultados = self._com_traducoes(tipo, req.pasta, [self._avaliar(tipo, req.pasta, obra) for obra in req.obras])
            no_acervo = sum(1 for livro in self.acervo if livro.tipo_em(req.pasta) == tipo)
            relatorios.append(RelatorioDisciplina(
                pasta=req.pasta, nome=req.nome, tipo=tipo, tem_pasta=req.pasta in set(pastas_existentes),
                no_acervo=no_acervo, resultados=resultados))
        return relatorios

    def _com_traducoes(self, tipo: str, pasta: str, resultados: list) -> tuple:
        """O PPC cita 'Organização Estruturada de Computadores' e o acervo tem 'Structured Computer Organization',
        já vinculado à disciplina com o tipo certo: títulos não batem, mas os autores sim. Um livro vinculado,
        com pelo menos metade dos autores citados, que nenhuma outra obra da disciplina usou, conta como a obra (marcado)."""
        usados = {r.livro.arquivo for r in resultados if r.situacao is Situacao.OK and r.livro}
        for i, r in enumerate(resultados):
            if r.situacao not in (Situacao.SEM_VINCULO, Situacao.AUSENTE):
                continue
            candidatos = []
            for livro in self.acervo:
                if livro.tipo_em(pasta) != tipo or livro.arquivo in usados:
                    continue
                c = self.casador._medir(r.obra, livro)          # None se o volume for outro
                if c is not None and c.autor >= 0.5:        # o PPC às vezes cita só o 1º autor
                    candidatos.append(c)
            if candidatos:
                melhor = max(candidatos, key=lambda c: c.titulo).livro
                usados.add(melhor.arquivo)
                resultados[i] = Resultado(r.obra, Situacao.OK, melhor, edicao_difere(r.obra, melhor), por_autor=True)
        return tuple(resultados)

    def _avaliar(self, tipo: str, pasta: str, obra) -> Resultado:
        manuais = self._manuais(pasta, obra)                  # o que você declarou vale mais que o palpite
        achadas = manuais + [c for c in self.casador.correspondencias(obra)
                             if all(c.livro is not m.livro for m in manuais)]
        if not achadas:
            return Resultado(obra, Situacao.AUSENTE, possiveis=tuple(self.casador.possiveis(obra)))
        for c in achadas:                                    # vinculada à disciplina com o tipo certo
            if c.livro.tipo_em(pasta) == tipo:
                return Resultado(obra, Situacao.OK, c.livro, edicao_difere(obra, c.livro))
        for c in achadas:                                    # vinculada, mas com outro tipo
            if c.livro.tipo_em(pasta) is not None:
                return Resultado(obra, Situacao.TIPO_DIFERENTE, c.livro, edicao_difere(obra, c.livro))
        melhor = achadas[0].livro                            # está no acervo, falta o vínculo
        return Resultado(obra, Situacao.SEM_VINCULO, melhor, edicao_difere(obra, melhor))
