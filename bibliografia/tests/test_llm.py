import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import llm
from llm import (ClienteLLM, CotaEsgotada, LLMIndisponivel, ProvedorClaude, ProvedorGemini, ProvedorIndisponivel,
                 analisar_429, corpo_gemini, criar_cliente_llm)

MSGS = [{"role": "user", "content": [{"type": "text", "text": "PPC", "cache_control": {"type": "ephemeral"}},
                                      {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": "QUJD"}},
                                      {"type": "text", "text": "pergunta"}]}]
SISTEMA = "Responda SOMENTE com um array JSON."


def ok(texto="[1]", parada="STOP", uso=None):
    return 200, {"candidates": [{"content": {"parts": [{"text": texto}]}, "finishReason": parada}],
                 "usageMetadata": uso or {"promptTokenCount": 100, "candidatesTokenCount": 7}}


def erro_429(diaria=False, atraso="20s", msg="You exceeded your current quota"):
    quota = "GenerateRequestsPerDayPerProjectPerModel-FreeTier" if diaria else "GenerateRequestsPerMinutePerProjectPerModel-FreeTier"
    return 429, {"error": {"code": 429, "message": msg, "status": "RESOURCE_EXHAUSTED", "details": [
        {"@type": "type.googleapis.com/google.rpc.QuotaFailure", "violations": [{"quotaId": quota}]},
        {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": atraso}]}}


class HttpFalso:
    def __init__(self, *respostas):
        self.respostas, self.chamadas = list(respostas), []

    def __call__(self, url, corpo, chave):
        self.chamadas.append((url, corpo, chave))
        r = self.respostas.pop(0) if len(self.respostas) > 1 else self.respostas[0]
        if isinstance(r, Exception):
            raise r
        return r


class ClaudeFalso:
    """Imita o SDK da Anthropic."""
    def __init__(self):
        self.chamadas, self.messages = [], self

    def create(self, **kw):
        self.chamadas.append(kw)
        return SimpleNamespace(content=[SimpleNamespace(type="text", text="[2]")], stop_reason="end_turn",
                               usage=SimpleNamespace(input_tokens=1000, output_tokens=100,
                                                     cache_creation_input_tokens=0, cache_read_input_tokens=0))


def gemini(http, **kw):
    return ProvedorGemini("chave", http=http, dormir=lambda s: None, **kw)


def cliente(provedores, estado=None, relogio=None):
    avisos = []
    c = ClienteLLM(provedores, estado, agora=relogio or (lambda: 1_000_000.0), avisar=avisos.append)
    c.avisos = avisos
    return c


class TestTraducaoParaOGemini(unittest.TestCase):
    def test_corpo(self):
        corpo = corpo_gemini("gemini-2.5-flash", 500, SISTEMA, MSGS)
        partes = corpo["contents"][0]["parts"]
        self.assertEqual(partes[0], {"text": "PPC"})                                    # cache_control some
        self.assertEqual(partes[1], {"inlineData": {"mimeType": "image/jpeg", "data": "QUJD"}})
        self.assertEqual(corpo["systemInstruction"]["parts"][0]["text"], SISTEMA)
        cfg = corpo["generationConfig"]
        self.assertEqual((cfg["maxOutputTokens"], cfg["temperature"], cfg["responseMimeType"]), (500, 0, "application/json"))
        self.assertEqual(cfg["thinkingConfig"], {"thinkingBudget": 0})

    def test_sem_json_no_prompt_nao_forca_json_e_pro_nao_desliga_pensamento(self):
        cfg = corpo_gemini("gemini-2.5-pro", 10, "Seja breve.", MSGS)["generationConfig"]
        self.assertNotIn("responseMimeType", cfg)
        self.assertNotIn("thinkingConfig", cfg)

    def test_resposta_usa_a_interface_do_sdk_da_anthropic(self):
        r = gemini(HttpFalso(ok("[1]", uso={"promptTokenCount": 100, "candidatesTokenCount": 7, "thoughtsTokenCount": 3}))) \
            .chamar("auto", 100, SISTEMA, MSGS)
        self.assertEqual((r.content[0].type, r.content[0].text, r.stop_reason), ("text", "[1]", "end_turn"))
        self.assertEqual((r.usage.input_tokens, r.usage.output_tokens), (100, 10))

    def test_max_tokens_vira_stop_reason_max_tokens(self):
        r = gemini(HttpFalso(ok('[{"a": "cort', parada="MAX_TOKENS"))).chamar("auto", 100, SISTEMA, MSGS)
        self.assertEqual(r.stop_reason, "max_tokens")

    def test_modelo_pedido(self):
        http = HttpFalso(ok())
        g = gemini(http)
        g.chamar("claude-haiku-4-5-20251001", 10, SISTEMA, MSGS)           # nome de outro provedor: usa o padrão
        g.chamar("gemini-2.5-flash-lite", 10, SISTEMA, MSGS)
        self.assertIn("gemini-2.5-flash:generateContent", http.chamadas[0][0])
        self.assertIn("gemini-2.5-flash-lite:generateContent", http.chamadas[1][0])


class TestErrosDoGemini(unittest.TestCase):
    def test_analisa_429(self):
        self.assertEqual(analisar_429(erro_429(diaria=True)[1])[:2], (True, 20.0))
        self.assertEqual(analisar_429(erro_429(diaria=False, atraso="0.5s")[1])[:2], (False, 0.5))
        self.assertTrue(analisar_429(erro_429(msg="quota exceeded, limit: 0")[1])[2])

    def test_limite_por_minuto_espera_e_tenta_de_novo(self):
        esperas = []
        http = HttpFalso(erro_429(atraso="20s"), ok("[1]"))
        g = ProvedorGemini("k", http=http, dormir=esperas.append)
        self.assertEqual(g.chamar("auto", 10, SISTEMA, MSGS).content[0].text, "[1]")
        self.assertEqual(esperas, [21.0])
        self.assertEqual(len(http.chamadas), 2)

    def test_espera_longa_demais_vira_cota_esgotada(self):
        with self.assertRaises(CotaEsgotada) as cm:
            gemini(HttpFalso(erro_429(atraso="300s"))).chamar("auto", 10, SISTEMA, MSGS)
        self.assertFalse(cm.exception.diaria)

    def test_cota_diaria(self):
        with self.assertRaises(CotaEsgotada) as cm:
            gemini(HttpFalso(erro_429(diaria=True))).chamar("auto", 10, SISTEMA, MSGS)
        self.assertTrue(cm.exception.diaria)

    def test_modelo_fora_do_plano_gratuito(self):
        with self.assertRaises(ProvedorIndisponivel) as cm:
            gemini(HttpFalso(erro_429(msg="Quota exceeded ... limit: 0"))).chamar("auto", 10, SISTEMA, MSGS)
        self.assertTrue(cm.exception.permanente)

    def test_chave_recusada_e_permanente(self):
        with self.assertRaises(ProvedorIndisponivel) as cm:
            gemini(HttpFalso((403, {"error": {"message": "API key not valid"}}))).chamar("auto", 10, SISTEMA, MSGS)
        self.assertTrue(cm.exception.permanente)

    def test_erro_de_servidor_tenta_de_novo_e_depois_desiste(self):
        http = HttpFalso((503, {}))
        with self.assertRaises(ProvedorIndisponivel):
            gemini(http).chamar("auto", 10, SISTEMA, MSGS)
        self.assertEqual(len(http.chamadas), 3)

    def test_resposta_bloqueada_ou_vazia(self):
        with self.assertRaises(ProvedorIndisponivel):
            gemini(HttpFalso((200, {"promptFeedback": {"blockReason": "SAFETY"}}))).chamar("auto", 10, SISTEMA, MSGS)

    def test_modelo_sem_opcao_de_pensamento_repete_sem_ela(self):
        http = HttpFalso((400, {"error": {"message": "Budget 0 is invalid: thinking can't be disabled"}}), ok())
        gemini(http).chamar("auto", 10, SISTEMA, MSGS)
        self.assertNotIn("thinkingConfig", http.chamadas[1][1]["generationConfig"])


class TestTrocaDeProvedor(unittest.TestCase):
    def test_usa_o_gemini_enquanto_houver_cota(self):
        http, claude = HttpFalso(ok("[1]")), ClaudeFalso()
        c = cliente([gemini(http), ProvedorClaude(cliente=claude)])
        r = c.messages.create(model="auto", max_tokens=100, system=SISTEMA, messages=MSGS)
        self.assertEqual(r.content[0].text, "[1]")
        self.assertEqual(claude.chamadas, [])
        self.assertIn("Gemini 1 chamada", c.resumo())
        self.assertNotIn("Claude", c.resumo())

    def test_cota_diaria_acabou_troca_para_o_claude_haiku_e_lembra(self):
        with tempfile.TemporaryDirectory() as d:
            estado = Path(d) / "cache" / "llm_estado.json"
            http1, claude = HttpFalso(erro_429(diaria=True)), ClaudeFalso()
            c1 = cliente([gemini(http1), ProvedorClaude(cliente=claude)], estado)
            r = c1.create(model="auto", max_tokens=100, system=SISTEMA, messages=MSGS)
            self.assertEqual(r.content[0].text, "[2]")
            self.assertEqual(claude.chamadas[0]["model"], "claude-haiku-4-5-20251001")
            self.assertTrue(any("trocando de provedor" in a for a in c1.avisos))
            self.assertIn("gemini", json.loads(estado.read_text()))
            # outra execução (outro processo) no mesmo dia: nem tenta o Gemini
            http2 = HttpFalso(ok("[1]"))
            c2 = cliente([gemini(http2), ProvedorClaude(cliente=claude)], estado)
            c2.create(model="auto", max_tokens=100, system=SISTEMA, messages=MSGS)
            self.assertEqual(http2.chamadas, [])
            self.assertEqual(len(claude.chamadas), 2)
            self.assertTrue(any("em pausa" in a for a in c2.avisos))

    def test_depois_da_pausa_volta_para_o_gemini(self):
        with tempfile.TemporaryDirectory() as d:
            estado = Path(d) / "llm_estado.json"
            agora = [1_000_000.0]
            c1 = cliente([gemini(HttpFalso(erro_429(diaria=True))), ProvedorClaude(cliente=ClaudeFalso())], estado, lambda: agora[0])
            c1.create(model="auto", max_tokens=1, system=SISTEMA, messages=MSGS)
            agora[0] += 3 * 86400                                              # três dias depois
            http = HttpFalso(ok("[1]"))
            c2 = cliente([gemini(http), ProvedorClaude(cliente=ClaudeFalso())], estado, lambda: agora[0])
            r = c2.create(model="auto", max_tokens=1, system=SISTEMA, messages=MSGS)
            self.assertEqual((r.content[0].text, len(http.chamadas)), ("[1]", 1))

    def test_falha_comum_do_gemini_usa_o_claude_so_nessa_chamada(self):
        with tempfile.TemporaryDirectory() as d:
            estado = Path(d) / "e.json"
            http = HttpFalso((503, {}), (503, {}), (503, {}), ok("[1]"))
            claude = ClaudeFalso()
            c = cliente([gemini(http), ProvedorClaude(cliente=claude)], estado)
            self.assertEqual(c.create(model="auto", max_tokens=1, system=SISTEMA, messages=MSGS).content[0].text, "[2]")
            self.assertFalse(estado.exists())                                  # sem pausa persistida
            self.assertEqual(c.create(model="auto", max_tokens=1, system=SISTEMA, messages=MSGS).content[0].text, "[1]")

    def test_chave_invalida_desativa_o_gemini_nesta_execucao(self):
        http = HttpFalso((403, {"error": {"message": "API key not valid"}}))
        claude = ClaudeFalso()
        c = cliente([gemini(http), ProvedorClaude(cliente=claude)])
        for _ in range(3):
            c.create(model="auto", max_tokens=1, system=SISTEMA, messages=MSGS)
        self.assertEqual(len(http.chamadas), 1)                                # não insiste
        self.assertEqual(len(claude.chamadas), 3)

    def test_modelo_claude_explicito_so_vale_para_o_claude(self):
        claude = ClaudeFalso()
        c = cliente([gemini(HttpFalso(erro_429(diaria=True))), ProvedorClaude(cliente=claude)])
        c.create(model="claude-sonnet-5-5", max_tokens=1, system=SISTEMA, messages=MSGS)
        self.assertEqual(claude.chamadas[0]["model"], "claude-sonnet-5-5")

    def test_so_gemini_e_cota_esgotada_da_erro_claro(self):
        c = cliente([gemini(HttpFalso(erro_429(diaria=True)))])
        with self.assertRaisesRegex(LLMIndisponivel, "Nenhum provedor"):
            c.create(model="auto", max_tokens=1, system=SISTEMA, messages=MSGS)

    def test_resumo_estima_o_custo_do_haiku(self):
        claude = ClaudeFalso()
        c = cliente([ProvedorClaude(cliente=claude)])
        c.create(model="auto", max_tokens=1, system=SISTEMA, messages=MSGS)
        # 1000 tokens de entrada a US$ 1/M + 100 de saída a US$ 5/M
        self.assertAlmostEqual(c.custo_claude(), 0.0015, places=6)
        self.assertIn("Claude 1 chamada", c.resumo())

    def test_sem_nenhuma_chamada(self):
        self.assertIn("nenhuma chamada", cliente([ProvedorClaude(cliente=ClaudeFalso())]).resumo())


class TestConfiguracaoPorAmbiente(unittest.TestCase):
    def montar(self, **env):
        base = {k: "" for k in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "ANTHROPIC_API_KEY", "LIVROS_LLM",
                                "LIVROS_MODELO_GEMINI", "LIVROS_MODELO_CLAUDE")}
        with mock.patch.dict(os.environ, {**base, **env}):
            return criar_cliente_llm()

    def test_as_duas_chaves_gemini_primeiro(self):
        c = self.montar(GEMINI_API_KEY="g", ANTHROPIC_API_KEY="a")
        self.assertEqual([p.nome for p in c.provedores], ["gemini", "claude"])
        self.assertEqual(c.provedores[1].modelo, "claude-haiku-4-5-20251001")

    def test_so_uma_chave(self):
        self.assertEqual([p.nome for p in self.montar(ANTHROPIC_API_KEY="a").provedores], ["claude"])
        self.assertEqual([p.nome for p in self.montar(GOOGLE_API_KEY="g").provedores], ["gemini"])

    def test_modo_forcado(self):
        c = self.montar(GEMINI_API_KEY="g", ANTHROPIC_API_KEY="a", LIVROS_LLM="claude")
        self.assertEqual([p.nome for p in c.provedores], ["claude"])

    def test_modelos_por_variavel(self):
        c = self.montar(GEMINI_API_KEY="g", ANTHROPIC_API_KEY="a", LIVROS_MODELO_GEMINI="gemini-2.5-flash-lite",
                        LIVROS_MODELO_CLAUDE="claude-sonnet-5-5")
        self.assertEqual([p.modelo for p in c.provedores], ["gemini-2.5-flash-lite", "claude-sonnet-5-5"])

    def test_sem_chave_ou_modo_invalido_sai_com_mensagem(self):
        with self.assertRaises(SystemExit):
            self.montar()
        with self.assertRaises(SystemExit):
            self.montar(GEMINI_API_KEY="g", LIVROS_LLM="outro")


if __name__ == "__main__":
    unittest.main()
