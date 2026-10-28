"""
Leitura do PPC e extração da bibliografia por disciplina.

`ExtratorDeBibliografia` é a interface que o resto do programa conhece; `ExtratorClaude` é a única
implementação que fala com a API. Nos testes entra um extrator falso no lugar.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Callable, Optional, Protocol, Sequence

import nucleo

from .modelos import ROTULO_TIPO, TIPOS, Obra, RequisitoDisciplina


class ExtratorDeBibliografia(Protocol):
    def extrair(self, tipo: str, texto_ppc: str, pastas: Sequence[str]) -> list[RequisitoDisciplina]:
        """Bibliografia do `tipo` ('basica'|'complementar') de cada disciplina do PPC."""


def ler_texto_ppc(caminho: Path, paginas: str = "") -> str:
    caminho = Path(caminho)
    if not caminho.is_file():
        sys.exit(f"PPC não encontrado: {caminho}")
    texto = nucleo.texto_ppc(caminho, paginas).strip()
    if len(texto) < 2000:
        sys.exit("Quase nenhum texto extraído do PPC (PDF escaneado?).")
    return texto


SISTEMA = """Você extrai a bibliografia {rotulo} de cada disciplina de um PPC (projeto pedagógico de curso).
Regras:
- {escopo}
- Em "obras", só itens da bibliografia {rotulo}. Ignore a outra (básica/complementar) e as ementas.
- Para cada obra: "titulo" (com subtítulo, se houver), "autores" (como no PPC), "edicao" (como no PPC, ex.: "3", "2ª ed."; "" se não houver), "ano" (número ou null).
- "disciplina" é o nome no PPC. "pasta" é o nome da pasta do aluno que corresponde à disciplina, escolhido SEMPRE da lista fornecida quando houver
  correspondência (ex.: "Cálculo Diferencial e Integral III" -> "calculo-diferencial-e-integral-3"). Sem correspondência, proponha kebab-case sem acentos.
- Não invente obras nem complete dados que não estão no texto.
Responda SOMENTE com um array JSON:
[{{"disciplina": "...", "pasta": "...", "obras": [{{"titulo": "...", "autores": "...", "edicao": "...", "ano": null}}]}}]"""

ESCOPO_LOTE = ('Inclua UMA entrada para cada disciplina da lista "Disciplinas a extrair" (nem mais, nem menos, na mesma ordem), '
               'mesmo que a bibliografia {rotulo} esteja vazia ou ausente (nesse caso "obras": []).')
ESCOPO_TUDO = ('Inclua UMA entrada por disciplina do PPC, mesmo que a bibliografia {rotulo} esteja vazia ou ausente '
               '(nesse caso "obras": []).')

SISTEMA_LISTA = """Você lista as disciplinas de um PPC (projeto pedagógico de curso).
Responda SOMENTE com um array JSON de strings, uma por disciplina, no formato "CÓDIGO - NOME" (ou só o nome, se não houver código),
na ordem em que aparecem no PPC, sem repetir. Não inclua grupos, módulos nem títulos de seção."""

DISCIPLINA_NO_TEXTO = re.compile(r"^[ \t\f]*(?:#+[ \t]*)?([A-Z]{3}\d{5})[ \t]*-[ \t]*(.+?)[ \t]*$", re.MULTILINE)
LOTE = 8                    # disciplinas por chamada: a resposta de cada lote cabe folgada no limite de saída
MAX_TOKENS_LOTE = 12000


def disciplinas_do_ppc(texto: str) -> list[str]:
    """'CPT01003 - ALGORITMOS' ... achadas no texto do PPC (PDF extraído ou o .md gerado), sem repetir, em ordem."""
    vistas, saida = set(), []
    for m in DISCIPLINA_NO_TEXTO.finditer(texto):
        if m.group(1) not in vistas:
            vistas.add(m.group(1))
            saida.append(f"{m.group(1)} - {m.group(2)}")
    return saida


def _extrair_lista_json(texto: str) -> list[Any]:
    inicio = texto.index("[")
    dados, _ = json.JSONDecoder().raw_decode(texto[inicio:])
    if not isinstance(dados, list):
        raise ValueError("a resposta não é uma lista")
    return dados


def requisitos_de_json(dados: Sequence[dict]) -> list[RequisitoDisciplina]:
    """Valida e converte a resposta do modelo; descarta entradas malformadas em vez de falhar."""
    saida = []
    for item in dados:
        if not isinstance(item, dict):
            continue
        nome = str(item.get("disciplina") or "").strip()
        pasta = nucleo.slug(str(item.get("pasta") or nome))
        if not pasta:
            continue
        obras = []
        for o in item.get("obras") or []:
            if isinstance(o, dict) and str(o.get("titulo") or "").strip():
                ano = o.get("ano")
                obras.append(Obra(titulo=str(o["titulo"]).strip(), autores=str(o.get("autores") or "").strip(),
                                  edicao=str(o.get("edicao") or "").strip(),
                                  ano=ano if isinstance(ano, int) else None))
        saida.append(RequisitoDisciplina(pasta=pasta, nome=nome or pasta, obras=tuple(obras)))
    return saida


class ExtratorClaude:
    """Extrai a bibliografia com a API do Claude, em lotes de disciplinas.

    Pedir tudo numa chamada só estourava o limite de saída na bibliografia complementar (muito mais longa que a
    básica) e a resposta vinha cortada no meio do JSON. Agora: lista as disciplinas (no texto do PPC; se não
    houver códigos, pergunta ao modelo), pede LOTE por vez, divide o lote ao meio se a resposta for truncada
    e guarda cada lote no cache, então uma falha no meio não refaz o que já deu certo."""

    def __init__(self, cliente: Any, modelo: str, cache_path: Optional[Path] = None, refazer: bool = False,
                 progresso: Callable[[str], None] = lambda *_: None, lote: int = LOTE):
        self.cliente = cliente
        self.modelo = modelo
        self.cache_path = cache_path
        self.refazer = refazer
        self.progresso = progresso
        self.lote = lote

    # -- chamadas
    def _chamar(self, sistema: str, texto_ppc: str, pergunta: str, max_tokens: int):
        msg = self.cliente.messages.create(
            model=self.modelo, max_tokens=max_tokens, system=sistema,
            messages=[{"role": "user", "content": [
                {"type": "text", "text": "PPC DO CURSO:\n" + texto_ppc, "cache_control": {"type": "ephemeral"}},
                {"type": "text", "text": pergunta}]}])
        texto = next(b.text for b in msg.content if b.type == "text")
        return texto, getattr(msg, "stop_reason", None) == "max_tokens"

    def _listar_com_ia(self, texto_ppc: str) -> list[str]:
        texto, cortada = self._chamar(SISTEMA_LISTA, texto_ppc, "Liste as disciplinas do PPC.", 4000)
        if cortada:
            return []
        try:
            return [str(x).strip() for x in _extrair_lista_json(texto) if str(x).strip()]
        except ValueError:
            return []

    def _extrair_lote(self, tipo: str, texto_ppc: str, pastas: Sequence[str], disciplinas: Sequence[str],
                      cache: dict, chave: str) -> list:
        rotulo = ROTULO_TIPO[tipo]
        chave_lote = f"{chave}|lote|{hashlib.sha256(chr(10).join(disciplinas).encode()).hexdigest()[:12]}"
        if chave_lote in cache:
            return cache[chave_lote]
        sistema = SISTEMA.format(rotulo=rotulo, escopo=ESCOPO_LOTE.format(rotulo=rotulo))
        pergunta = ("Pastas existentes do aluno:\n" + ", ".join(pastas)
                    + f"\n\nExtraia a bibliografia {rotulo} das disciplinas abaixo.\nDisciplinas a extrair:\n"
                    + "\n".join(f"- {d}" for d in disciplinas))
        texto, cortada = self._chamar(sistema, texto_ppc, pergunta, MAX_TOKENS_LOTE)
        if cortada:
            if len(disciplinas) == 1:
                raise RuntimeError(f"A resposta para '{disciplinas[0]}' passou do limite de saída do modelo, mesmo sozinha.")
            meio = len(disciplinas) // 2
            dados = (self._extrair_lote(tipo, texto_ppc, pastas, disciplinas[:meio], cache, chave)
                     + self._extrair_lote(tipo, texto_ppc, pastas, disciplinas[meio:], cache, chave))
        else:
            dados = _extrair_lista_json(texto)
        cache[chave_lote] = dados
        if self.cache_path:
            nucleo.gravar_cache(self.cache_path, cache)
        return dados

    def _extrair_tudo(self, tipo: str, texto_ppc: str, pastas: Sequence[str]) -> list:
        """Último recurso, quando não dá para listar as disciplinas: uma chamada só (com aviso se for cortada)."""
        rotulo = ROTULO_TIPO[tipo]
        sistema = SISTEMA.format(rotulo=rotulo, escopo=ESCOPO_TUDO.format(rotulo=rotulo))
        pergunta = "Pastas existentes do aluno:\n" + ", ".join(pastas) + f"\n\nExtraia a bibliografia {rotulo} de todas as disciplinas."
        texto, cortada = self._chamar(sistema, texto_ppc, pergunta, 32000)
        if cortada:
            raise RuntimeError("A resposta passou do limite de saída e não consegui listar as disciplinas do PPC para dividir "
                               "o pedido. Gere o .md do PPC (python3 -m bibliografia.ppc_markdown) para as disciplinas "
                               "serem reconhecidas pelo código.")
        return _extrair_lista_json(texto)

    # -- interface
    def extrair(self, tipo: str, texto_ppc: str, pastas: Sequence[str]) -> list[RequisitoDisciplina]:
        if tipo not in TIPOS:
            raise ValueError(f"tipo inválido: {tipo}")
        # "auto" mantém a chave antiga: a extração já feita (com qualquer provedor) continua valendo no cache
        rotulo_modelo = "claude-sonnet-5-5" if self.modelo == "auto" else self.modelo
        chave = f"{tipo}|{hashlib.sha256(texto_ppc.encode()).hexdigest()[:16]}|{rotulo_modelo}"
        cache = nucleo.ler_cache(self.cache_path, self.refazer) if self.cache_path else {}
        if chave not in cache:
            disciplinas = disciplinas_do_ppc(texto_ppc)
            if len(disciplinas) < 5:
                self.progresso("Poucos códigos de disciplina no texto; pedindo a lista ao modelo...")
                disciplinas = self._listar_com_ia(texto_ppc)
            if disciplinas:
                dados = []
                lotes = [disciplinas[i:i + self.lote] for i in range(0, len(disciplinas), self.lote)]
                for n, parte in enumerate(lotes, 1):
                    self.progresso(f"  lote {n}/{len(lotes)} ({len(parte)} disciplinas)")
                    dados += self._extrair_lote(tipo, texto_ppc, pastas, parte, cache, chave)
            else:
                dados = self._extrair_tudo(tipo, texto_ppc, pastas)
            cache[chave] = dados
            if self.cache_path:
                nucleo.gravar_cache(self.cache_path, cache)
        return requisitos_de_json(cache[chave])


def criar_cliente_anthropic(estado_path=None):
    """(nome mantido por compatibilidade) Cliente de IA com troca automática: Gemini grátis -> Claude Haiku."""
    import llm
    return llm.criar_cliente_llm(estado_path)
