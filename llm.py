"""
Cliente de LLM com troca automática de provedor.

Ordem: Gemini (plano gratuito do Google AI Studio) primeiro; quando a cota gratuita acaba, ou o Gemini falha,
usa o Claude (Haiku 4.5, o mais barato). Quem chama usa a mesma interface do SDK da Anthropic
(`cliente.messages.create(model=..., max_tokens=..., system=..., messages=[...])`), então `ia`, `ppc` e a extração do
pacote `bibliografia` não sabem qual provedor respondeu.

Configuração (ambiente ou .env):
    GEMINI_API_KEY      chave do AI Studio (https://aistudio.google.com/app/apikey), grátis
    ANTHROPIC_API_KEY   chave da Anthropic (paga, usada só quando o Gemini não puder)
    LIVROS_LLM          auto (padrão: Gemini -> Claude) | gemini | claude
    LIVROS_MODELO_GEMINI  padrão gemini-2.5-flash
    LIVROS_MODELO_CLAUDE  padrão claude-haiku-4-5-20251001
    LIVROS_GEMINI_ESPERA_MAX  segundos que vale esperar um limite "por minuto" antes de trocar (padrão 45)

O argumento `model` de cada chamada é interpretado assim: "auto" (ou vazio) = padrão de cada provedor; "gemini-..." vale
só para o Gemini; "claude-..." vale só para o Claude. Quando o Gemini esgota a cota DIÁRIA, o aviso fica gravado num
arquivo de estado e as próximas execuções nem tentam o Gemini até a cota voltar (meia-noite do Pacífico).
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Optional, Sequence

GEMINI_MODELO_PADRAO = "gemini-2.5-flash"
CLAUDE_MODELO_PADRAO = "claude-haiku-4-5-20251001"
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent"

# US$ por milhão de tokens (preço de lista): entrada, saída, escrita de cache, leitura de cache
PRECOS_CLAUDE = {"haiku": (1.0, 5.0, 1.25, 0.10)}


class CotaEsgotada(Exception):
    def __init__(self, diaria: bool, atraso: Optional[float] = None, detalhe: str = ""):
        super().__init__(detalhe or ("cota diária esgotada" if diaria else "limite por minuto"))
        self.diaria, self.atraso = diaria, atraso


class ProvedorIndisponivel(Exception):
    def __init__(self, motivo: str, permanente: bool = False):
        super().__init__(motivo)
        self.permanente = permanente


class LLMIndisponivel(RuntimeError):
    """Nenhum provedor conseguiu responder."""


# ----------------------------------------------------------------------------------------------- Gemini

def _post_json(url: str, corpo: dict, chave: str, timeout: int = 180) -> tuple[int, dict]:
    req = urllib.request.Request(url, data=json.dumps(corpo).encode("utf-8"), method="POST",
                                 headers={"Content-Type": "application/json", "x-goog-api-key": chave})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode("utf-8", "replace"))
        except (ValueError, OSError):
            return e.code, {}
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise ProvedorIndisponivel(f"sem conexão com o Gemini: {e}") from e


def _partes(conteudo: Any) -> list[dict]:
    if isinstance(conteudo, str):
        return [{"text": conteudo}]
    partes = []
    for bloco in conteudo:
        tipo = bloco.get("type")
        if tipo == "text":
            partes.append({"text": bloco["text"]})                       # cache_control é do Claude: ignorado aqui
        elif tipo in ("image", "document"):
            origem = bloco["source"]
            partes.append({"inlineData": {"mimeType": origem["media_type"], "data": origem["data"]}})
    return partes


def corpo_gemini(modelo: str, max_tokens: int, system: str, messages: Sequence[dict]) -> dict:
    corpo: dict = {
        "contents": [{"role": "model" if m["role"] == "assistant" else "user", "parts": _partes(m["content"])}
                     for m in messages],
        "generationConfig": {"maxOutputTokens": max_tokens, "temperature": 0}}
    if system:
        corpo["systemInstruction"] = {"parts": [{"text": system}]}
        if "json" in system.lower():
            corpo["generationConfig"]["responseMimeType"] = "application/json"
    if "flash" in modelo:                                                # sem "pensar": o orçamento de saída é do JSON
        corpo["generationConfig"]["thinkingConfig"] = {"thinkingBudget": 0}
    return corpo


def _atraso_em_segundos(texto: str) -> Optional[float]:
    try:
        return float(str(texto).rstrip("s"))
    except ValueError:
        return None


def analisar_429(dados: dict) -> tuple[bool, Optional[float], bool, str]:
    """(cota_diaria, atraso_sugerido, sem_acesso_gratuito, mensagem) a partir do erro 429 do Gemini."""
    erro = dados.get("error", {}) if isinstance(dados, dict) else {}
    mensagem = str(erro.get("message", ""))
    diaria, atraso = False, None
    for d in erro.get("details", []) or []:
        for v in d.get("violations", []) or []:
            if "perday" in str(v.get("quotaId", "")).lower().replace("_", ""):
                diaria = True
        if d.get("retryDelay"):
            atraso = _atraso_em_segundos(d["retryDelay"])
    texto = mensagem.lower()
    diaria = diaria or "per day" in texto or "daily" in texto
    return diaria, atraso, "limit: 0" in texto, mensagem


class ProvedorGemini:
    nome = "gemini"

    def __init__(self, chave: str, modelo: str = GEMINI_MODELO_PADRAO, *,
                 http: Optional[Callable[[str, dict, str], tuple[int, dict]]] = None,
                 dormir: Callable[[float], None] = time.sleep, espera_max: float = 45.0, tentativas: int = 3):
        self.chave, self.modelo, self.http = chave, modelo, http
        self.dormir, self.espera_max, self.tentativas = dormir, espera_max, tentativas

    def modelo_para(self, pedido: Optional[str]) -> str:
        return pedido if pedido and pedido.startswith("gemini") else self.modelo

    def chamar(self, model, max_tokens, system, messages):
        modelo = self.modelo_para(model)
        corpo = corpo_gemini(modelo, max_tokens, system, messages)
        url = GEMINI_URL.format(modelo=modelo)
        for tentativa in range(1, self.tentativas + 1):
            status, dados = (self.http or _post_json)(url, corpo, self.chave)
            if status == 200:
                return self._resposta(dados)
            erro = dados.get("error", {}) if isinstance(dados, dict) else {}
            if status == 429:
                diaria, atraso, sem_acesso, msg = analisar_429(dados)
                if sem_acesso:
                    raise ProvedorIndisponivel(f"o modelo {modelo} não está no plano gratuito: {msg[:120]}", permanente=True)
                if diaria:
                    raise CotaEsgotada(True, atraso, msg[:160])
                if atraso is not None and atraso <= self.espera_max and tentativa < self.tentativas:
                    self.dormir(atraso + 1)
                    continue
                raise CotaEsgotada(False, atraso, msg[:160])
            if status == 400 and "thinking" in str(erro.get("message", "")).lower() \
                    and "thinkingConfig" in corpo["generationConfig"]:
                del corpo["generationConfig"]["thinkingConfig"]            # modelo sem essa opção: tenta de novo sem ela
                continue
            if status in (401, 403):
                raise ProvedorIndisponivel(f"chave do Gemini recusada (HTTP {status}): {str(erro.get('message', ''))[:100]}",
                                           permanente=True)
            if status >= 500 or status == 408:
                if tentativa < self.tentativas:
                    self.dormir(2.0 * tentativa)
                    continue
            raise ProvedorIndisponivel(f"Gemini HTTP {status}: {str(erro.get('message', ''))[:120]}")
        raise ProvedorIndisponivel("Gemini não respondeu após várias tentativas")

    @staticmethod
    def _resposta(dados: dict):
        candidatos = dados.get("candidates") or []
        partes = ((candidatos[0].get("content") or {}).get("parts") or []) if candidatos else []
        texto = "".join(p.get("text", "") for p in partes if not p.get("thought"))
        fim = candidatos[0].get("finishReason") if candidatos else (dados.get("promptFeedback") or {}).get("blockReason")
        if not texto.strip():
            raise ProvedorIndisponivel(f"resposta vazia do Gemini ({fim or 'sem motivo'})")
        uso = dados.get("usageMetadata") or {}
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text=texto)],
            stop_reason="max_tokens" if fim == "MAX_TOKENS" else "end_turn",
            usage=SimpleNamespace(input_tokens=int(uso.get("promptTokenCount") or 0),
                                  output_tokens=int((uso.get("candidatesTokenCount") or 0) + (uso.get("thoughtsTokenCount") or 0)),
                                  cache_creation_input_tokens=0,
                                  cache_read_input_tokens=int(uso.get("cachedContentTokenCount") or 0)))


# ----------------------------------------------------------------------------------------------- Claude

class ProvedorClaude:
    nome = "claude"

    def __init__(self, modelo: str = CLAUDE_MODELO_PADRAO, cliente: Any = None):
        self.modelo, self._cliente = modelo, cliente

    def modelo_para(self, pedido: Optional[str]) -> str:
        return pedido if pedido and pedido.startswith("claude") else self.modelo

    def _sdk(self):
        if self._cliente is None:
            try:
                import anthropic
            except ImportError as e:
                raise ProvedorIndisponivel("SDK da Anthropic não instalado (pip install anthropic)", permanente=True) from e
            self._cliente = anthropic.Anthropic()
        return self._cliente

    def chamar(self, model, max_tokens, system, messages):
        return self._sdk().messages.create(model=self.modelo_para(model), max_tokens=max_tokens, system=system,
                                           messages=list(messages))


# ----------------------------------------------------------------------------------------------- cliente

def _fim_do_dia_no_pacifico(agora: float) -> float:
    """A cota diária do Gemini volta à meia-noite do horário do Pacífico."""
    try:
        from zoneinfo import ZoneInfo
        pt = ZoneInfo("America/Los_Angeles")
        local = datetime.fromtimestamp(agora, pt)
        amanha = (local + timedelta(days=1)).replace(hour=0, minute=5, second=0, microsecond=0)
        return amanha.timestamp()
    except Exception:
        return agora + 12 * 3600


class ClienteLLM:
    """Tenta os provedores na ordem; lembra (em arquivo) quando a cota gratuita acabou."""

    def __init__(self, provedores: Sequence[Any], estado_path: Optional[Path] = None, *,
                 agora: Callable[[], float] = time.time, avisar: Callable[[str], None] = print):
        if not provedores:
            raise ValueError("nenhum provedor configurado")
        self.provedores = list(provedores)
        self.estado_path = Path(estado_path) if estado_path else None
        self.agora, self.avisar = agora, avisar
        self.messages = self
        self.uso: dict[str, dict] = {}
        self._desativados: dict[str, str] = {}                           # só nesta execução (chave inválida etc.)
        self._avisados: set[str] = set()

    # -- estado em arquivo
    def _ler_estado(self) -> dict:
        try:
            return json.loads(self.estado_path.read_text(encoding="utf-8")) if self.estado_path else {}
        except (OSError, ValueError):
            return {}

    def _gravar_pausa(self, nome: str, ate: float, motivo: str) -> None:
        if not self.estado_path:
            return
        estado = self._ler_estado()
        estado[nome] = {"ate": ate, "motivo": motivo}
        try:
            self.estado_path.parent.mkdir(parents=True, exist_ok=True)
            self.estado_path.write_text(json.dumps(estado), encoding="utf-8")
        except OSError:
            pass

    def _em_pausa(self, nome: str) -> Optional[dict]:
        p = self._ler_estado().get(nome)
        return p if p and p.get("ate", 0) > self.agora() else None

    def _avisar_uma_vez(self, chave: str, texto: str) -> None:
        if chave not in self._avisados:
            self._avisados.add(chave)
            self.avisar(texto)

    # -- chamada
    def create(self, *, model: Optional[str] = None, max_tokens: int, system: str = "", messages: Sequence[dict], **_):
        erros = []
        for prov in self.provedores:
            if prov.nome in self._desativados:
                erros.append(f"{prov.nome}: {self._desativados[prov.nome]}")
                continue
            pausa = self._em_pausa(prov.nome)
            if pausa:
                ate = datetime.fromtimestamp(pausa["ate"]).strftime("%d/%m %H:%M")
                self._avisar_uma_vez(f"pausa-{prov.nome}", f"[llm] {prov.nome} em pausa até {ate} ({pausa.get('motivo')}); pulando.")
                erros.append(f"{prov.nome}: em pausa até {ate}")
                continue
            try:
                resposta = prov.chamar(model, max_tokens, system, messages)
            except CotaEsgotada as e:
                ate = _fim_do_dia_no_pacifico(self.agora()) if e.diaria else self.agora() + 120
                self._gravar_pausa(prov.nome, ate, "cota diária esgotada" if e.diaria else "limite por minuto")
                self._avisar_uma_vez(f"cota-{prov.nome}", f"[llm] {prov.nome}: {'cota gratuita do dia esgotada' if e.diaria else 'limite por minuto'}"
                                                         f"; trocando de provedor.")
                erros.append(f"{prov.nome}: {e}")
                continue
            except ProvedorIndisponivel as e:
                if e.permanente:
                    self._desativados[prov.nome] = str(e)
                self._avisar_uma_vez(f"falha-{prov.nome}-{e}", f"[llm] {prov.nome} indisponível ({e}); tentando o próximo.")
                erros.append(f"{prov.nome}: {e}")
                continue
            self._contar(prov.nome, getattr(resposta, "usage", None))
            return resposta
        raise LLMIndisponivel("Nenhum provedor de IA conseguiu responder:\n  " + "\n  ".join(erros))

    # -- contabilidade
    def _contar(self, nome: str, usage: Any) -> None:
        u = self.uso.setdefault(nome, {"chamadas": 0, "entrada": 0, "saida": 0, "cache_escrita": 0, "cache_leitura": 0})
        u["chamadas"] += 1
        u["entrada"] += getattr(usage, "input_tokens", 0) or 0
        u["saida"] += getattr(usage, "output_tokens", 0) or 0
        u["cache_escrita"] += getattr(usage, "cache_creation_input_tokens", 0) or 0
        u["cache_leitura"] += getattr(usage, "cache_read_input_tokens", 0) or 0

    def custo_claude(self) -> Optional[float]:
        u = self.uso.get("claude")
        if not u:
            return 0.0
        preco = next((p for chave, p in PRECOS_CLAUDE.items() if chave in self._modelo_claude()), None)
        if preco is None:
            return None
        return (u["entrada"] * preco[0] + u["saida"] * preco[1] + u["cache_escrita"] * preco[2]
                + u["cache_leitura"] * preco[3]) / 1e6

    def _modelo_claude(self) -> str:
        return next((p.modelo for p in self.provedores if p.nome == "claude"), "")

    def resumo(self) -> str:
        if not self.uso:
            return "IA: nenhuma chamada nesta execução."
        partes = []
        if "gemini" in self.uso:
            partes.append(f"Gemini {self.uso['gemini']['chamadas']} chamada(s) (plano gratuito)")
        if "claude" in self.uso:
            u, c = self.uso["claude"], self.custo_claude()
            tokens = u["entrada"] + u["cache_escrita"] + u["cache_leitura"]
            custo = f" ≈ US$ {c:.3f} (preço de lista)" if c is not None else ""
            partes.append(f"Claude {u['chamadas']} chamada(s), {tokens} tokens de entrada / {u['saida']} de saída{custo}")
        return "IA: " + " | ".join(partes)


def _chave_gemini() -> str:
    return os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or ""


def ha_chave() -> bool:
    return bool(_chave_gemini() or os.environ.get("ANTHROPIC_API_KEY"))


def criar_cliente_llm(estado_path: Optional[Path] = None, **kw) -> ClienteLLM:
    """Monta o cliente conforme as chaves e o LIVROS_LLM. Sai com mensagem clara se faltar chave."""
    modo = (os.environ.get("LIVROS_LLM") or "auto").strip().lower()
    if modo not in ("auto", "gemini", "claude"):
        sys.exit(f"LIVROS_LLM inválido: {modo!r} (use auto, gemini ou claude)")
    provedores = []
    if modo in ("auto", "gemini") and _chave_gemini():
        provedores.append(ProvedorGemini(
            _chave_gemini(), os.environ.get("LIVROS_MODELO_GEMINI") or GEMINI_MODELO_PADRAO,
            espera_max=float(os.environ.get("LIVROS_GEMINI_ESPERA_MAX") or 45)))
    if modo in ("auto", "claude") and os.environ.get("ANTHROPIC_API_KEY"):
        provedores.append(ProvedorClaude(os.environ.get("LIVROS_MODELO_CLAUDE") or CLAUDE_MODELO_PADRAO))
    if not provedores:
        faltando = {"gemini": "GEMINI_API_KEY (grátis em https://aistudio.google.com/app/apikey)",
                    "claude": "ANTHROPIC_API_KEY", "auto": "GEMINI_API_KEY e/ou ANTHROPIC_API_KEY"}[modo]
        sys.exit(f"Defina {faltando} (ambiente ou .env).")
    return ClienteLLM(provedores, estado_path, **kw)
