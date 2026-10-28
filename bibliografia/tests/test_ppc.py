import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from bibliografia.ppc import ExtratorClaude, disciplinas_do_ppc, requisitos_de_json


class ClienteFalso:
    """Imita a API: responde a lista de disciplinas, ou a bibliografia só das disciplinas pedidas no lote.
    `limite_por_resposta`: acima disso a resposta vem 'truncada' (stop_reason=max_tokens), como no erro real."""

    def __init__(self, resposta=None, disciplinas_da_lista=(), limite_por_resposta=None, falhar_na_chamada=None):
        self.resposta, self.lista = resposta, list(disciplinas_da_lista)
        self.limite, self.falhar_na = limite_por_resposta, falhar_na_chamada
        self.chamadas, self.lotes, self.listagens = 0, [], 0
        self.messages = self

    def create(self, **kwargs):
        self.chamadas += 1
        if self.falhar_na == self.chamadas:
            raise ConnectionError("rede caiu")
        self.ultimo_system = kwargs["system"]
        pergunta = kwargs["messages"][0]["content"][1]["text"]

        def resp(texto, parada="end_turn"):
            return SimpleNamespace(content=[SimpleNamespace(type="text", text=texto)], stop_reason=parada)

        if "lista as disciplinas" in kwargs["system"]:
            self.listagens += 1
            return resp(json.dumps(self.lista))
        if self.resposta is not None:                                    # modo antigo: sempre a mesma resposta
            return resp("Segue:\n" + json.dumps(self.resposta))
        pedidas = [l[2:] for l in pergunta.split("Disciplinas a extrair:\n")[1].splitlines()]
        self.lotes.append(pedidas)
        if self.limite and len(pedidas) > self.limite:
            return resp('[{"disciplina": "x", "obras": [{"titulo": "cortad', parada="max_tokens")
        dados = [{"disciplina": d.split(" - ", 1)[1], "pasta": f"p-{d[3:8]}",
                  "obras": [{"titulo": f"Obra de {d[:8]}", "autores": "AUTOR, A.", "edicao": "1", "ano": 2000}]}
                 for d in pedidas]
        return resp(json.dumps(dados))


def ppc_com(n):
    """Texto de PPC com n disciplinas no formato do PDF extraído (e uma delas no formato do .md gerado)."""
    linhas = [f"CPT{i:05d} - DISCIPLINA {i}\nEmenta\nTexto." for i in range(1, n + 1)]
    return "\n".join(linhas) + "\n## CPT09999 - DISCIPLINA DO MD\n"


DADOS = [{"disciplina": "Cálculo III", "pasta": "calculo-diferencial-e-integral-3",
          "obras": [{"titulo": "Cálculo", "autores": "STEWART, J.", "edicao": "7", "ano": 2013}, {"titulo": ""}, "lixo"]},
         {"disciplina": "Inglês", "obras": []}, "ignorar", {"pasta": ""}]


class TestParsing(unittest.TestCase):
    def test_descarta_malformados(self):
        reqs = requisitos_de_json(DADOS)
        self.assertEqual([r.pasta for r in reqs], ["calculo-diferencial-e-integral-3", "ingles"])
        self.assertEqual(len(reqs[0].obras), 1)
        self.assertEqual(reqs[0].obras[0].ano, 2013)
        self.assertEqual(reqs[1].obras, ())


class TestExtrator(unittest.TestCase):
    def test_usa_cache_na_segunda_chamada(self):
        cliente = ClienteFalso()
        with tempfile.TemporaryDirectory() as d:
            ex = ExtratorClaude(cliente, "modelo-x", cache_path=Path(d) / "c.json")
            a = ex.extrair("basica", ppc_com(5), ["ingles"])
            n = cliente.chamadas
            b = ex.extrair("basica", ppc_com(5), ["ingles"])
            self.assertEqual(a, b)
            self.assertEqual(cliente.chamadas, n)                        # nada novo na segunda vez
            ex.extrair("complementar", ppc_com(5), ["ingles"])           # outro tipo: chamadas novas
            self.assertGreater(cliente.chamadas, n)
            self.assertIn("complementar", cliente.ultimo_system)

    def test_tipo_invalido(self):
        with self.assertRaises(ValueError):
            ExtratorClaude(ClienteFalso(), "m").extrair("optativa", "x", [])


class TestLista(unittest.TestCase):
    def test_acha_disciplinas_no_pdf_e_no_md_sem_repetir(self):
        texto = ppc_com(3) + "\n## CPT00001 - DISCIPLINA 1\n"
        self.assertEqual(disciplinas_do_ppc(texto),
                         ["CPT00001 - DISCIPLINA 1", "CPT00002 - DISCIPLINA 2", "CPT00003 - DISCIPLINA 3",
                          "CPT09999 - DISCIPLINA DO MD"])

    def test_primeira_linha_da_pagina_do_pdf_comeca_com_avanco_de_pagina(self):
        texto = "CPT00001 - A\nEmenta\n61\n\n\fCPT00002 - B\nEmenta\n"
        self.assertEqual(disciplinas_do_ppc(texto), ["CPT00001 - A", "CPT00002 - B"])

    def test_ignora_o_que_nao_e_disciplina(self):
        self.assertEqual(disciplinas_do_ppc("Básico Comum\nMAT1 - X\nEmenta\n14. EMENTAS"), [])


class TestLotes(unittest.TestCase):
    def extrator(self, cliente, d, lote=8):
        return ExtratorClaude(cliente, "m", cache_path=Path(d) / "c.json", lote=lote)

    def test_pede_em_lotes_e_junta_na_ordem(self):
        cliente = ClienteFalso()
        with tempfile.TemporaryDirectory() as d:
            reqs = self.extrator(cliente, d, lote=8).extrair("complementar", ppc_com(19), ["x"])      # 19 + 1 do md = 20
        self.assertEqual([len(l) for l in cliente.lotes], [8, 8, 4])
        self.assertEqual(len(reqs), 20)
        self.assertEqual(reqs[0].nome, "DISCIPLINA 1")
        self.assertEqual(reqs[-1].nome, "DISCIPLINA DO MD")
        self.assertTrue(all(len(r.obras) == 1 for r in reqs))

    def test_cada_lote_so_recebe_as_suas_disciplinas(self):
        cliente = ClienteFalso()
        with tempfile.TemporaryDirectory() as d:
            self.extrator(cliente, d, lote=3).extrair("basica", ppc_com(6), [])
        self.assertTrue(set(cliente.lotes[0]).isdisjoint(cliente.lotes[1]))

    def test_resposta_truncada_divide_o_lote_ao_meio(self):
        cliente = ClienteFalso(limite_por_resposta=3)
        with tempfile.TemporaryDirectory() as d:
            reqs = self.extrator(cliente, d, lote=8).extrair("complementar", ppc_com(15), [])
        self.assertEqual(len(reqs), 16)                                  # nada se perdeu
        tamanhos = [len(l) for l in cliente.lotes]
        self.assertEqual(max(tamanhos), 8)                                # tentou o lote cheio...
        self.assertLessEqual(min(tamanhos), 3)                            # ...e foi dividindo até a resposta caber
        aceitos = [l for l in cliente.lotes if len(l) <= 3]
        self.assertEqual(sum(len(l) for l in aceitos), 16)                # as respostas aceitas cobrem tudo, sem repetir

    def test_disciplina_sozinha_que_estoura_da_erro_claro(self):
        cliente = ClienteFalso(limite_por_resposta=0)
        cliente.limite = 0.5                                              # qualquer resposta excede
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(RuntimeError, "limite de saída"):
                self.extrator(cliente, d, lote=2).extrair("basica", ppc_com(5), [])

    def test_falha_no_meio_retoma_sem_refazer_os_lotes_prontos(self):
        with tempfile.TemporaryDirectory() as d:
            c1 = ClienteFalso(falhar_na_chamada=3)                         # 1º e 2º lotes passam, o 3º cai
            with self.assertRaises(ConnectionError):
                self.extrator(c1, d, lote=4).extrair("complementar", ppc_com(11), [])
            c2 = ClienteFalso()
            reqs = self.extrator(c2, d, lote=4).extrair("complementar", ppc_com(11), [])
        self.assertEqual(len(reqs), 12)
        self.assertEqual(len(c2.lotes), 1)                                 # só o lote que faltava

    def test_sem_codigos_no_texto_pergunta_a_lista_ao_modelo(self):
        lista = [f"CPT{i:05d} - D{i}" for i in range(1, 8)]
        cliente = ClienteFalso(disciplinas_da_lista=lista)
        with tempfile.TemporaryDirectory() as d:
            reqs = self.extrator(cliente, d, lote=4).extrair("basica", "texto sem códigos " * 50, [])
        self.assertEqual(cliente.listagens, 1)
        self.assertEqual(len(reqs), 7)


if __name__ == "__main__":
    unittest.main()
