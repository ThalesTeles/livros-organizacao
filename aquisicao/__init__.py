"""
Aquisição legal dos livros que faltam (independente do organizar_livros.py e do pacote `bibliografia`).

Entrada: os relatórios `faltantes-basica` / `faltantes-complementar` (.csv ou .md) gerados pelo pacote `bibliografia`.
Saída: um relatório do que dá para obter de forma legítima, livro a livro:
  - livre      : domínio público / acesso aberto (pode baixar; `--baixar` baixa para uma pasta de quarentena);
  - empréstimo : empréstimo digital (Internet Archive / Open Library);
  - à venda    : e-book à venda (Google Livros), com preço quando a API informa;
  - sem versão digital legal: links para comprar (inclusive usado) e para procurar em bibliotecas.

Módulos, em ordem de dependência:
    modelos    dataclasses (obra faltante, achado, resultado)
    entrada    lê os relatórios .csv/.md e junta as obras repetidas entre disciplinas
    texto      normalização e comparação de títulos/autores (funções puras)
    fontes     clientes Open Library e Google Livros (o acesso HTTP é injetado: testável sem rede)
    links      links de busca (comprar, bibliotecas) – nenhum scraping
    baixar     baixa SÓ o que as fontes marcam como livre, em quarentena, nunca sobrescreve
    relatorio  Markdown e CSV
    cli        python3 -m aquisicao
"""
