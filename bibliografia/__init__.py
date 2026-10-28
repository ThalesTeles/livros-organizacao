"""
bibliografia: descobre quais livros do PPC ainda faltam no seu acervo.

Fluxo (cada tipo é analisado separadamente, de propósito):

    python3 -m bibliografia basica          # lacunas da bibliografia BÁSICA
    python3 -m bibliografia complementar    # lacunas da bibliografia COMPLEMENTAR

Camadas (cada módulo faz uma coisa e só conhece os de baixo):

    modelos     dados do domínio (Obra, Livro, Resultado...), sem I/O
    casamento   comparação de títulos/autores/edição/volume, puro e testável
    acervo      lê o seu acervo (livros.csv) e devolve `Livro`
    ppc         lê o texto do PPC e extrai a bibliografia (Claude, atrás de uma interface)
    analise     serviço: compara PPC x acervo e classifica cada obra (ok / ajustar CSV / ausente)
    relatorio   gera o relatório em Markdown, CSV e resumo no terminal
    ppc_markdown converte o PDF do PPC em Markdown compacto (python3 -m bibliografia.ppc_markdown)
    cli         monta tudo (injeção de dependências) e interpreta a linha de comando

Dependências externas só em `ppc.ExtratorClaude` (SDK anthropic) e em `nucleo` (CSV, caches, .env).
Testes: python3 -m unittest discover -s bibliografia/tests -t .
"""
