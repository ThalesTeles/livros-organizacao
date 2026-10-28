# Organizador de livros da faculdade

Ferramenta de linha de comando que organiza a biblioteca de PDFs/e-books de um curso:

- **padroniza os nomes** dos arquivos (`titulo_autor_edicao.ext`);
- **liga cada livro às disciplinas** em que ele é usado, separando **bibliografia básica** e **complementar** conforme o PPC;
- mantém uma **pasta de links simbólicos por disciplina** no seu computador;
- **envia para o Google Drive** (via `rclone`) uma cópia de cada livro e, nas pastas de disciplina do Drive, **atalhos** para ela;
- **organiza sozinha** um livro novo jogado na pasta `livros/`;
- (pacote `bibliografia`) **descobre quais livros do PPC ainda faltam** no seu acervo.

Identificar título/autor/edição e classificar pelo PPC usa a API do Claude. Todo o resto é local.

---

## Sumário

1. [Como as pastas ficam](#1-como-as-pastas-ficam)
2. [Instalação](#2-instalação)
3. [Configuração](#3-configuração)
4. [O `livros.csv`](#4-o-livroscsv)
5. [Primeiros passos](#5-primeiros-passos)
6. [Uso no dia a dia](#6-uso-no-dia-a-dia)
7. [Referência dos comandos](#7-referência-dos-comandos)
8. [Google Drive](#8-google-drive)
9. [Automação com systemd](#9-automação-com-systemd)
10. [Livros que faltam: o pacote `bibliografia`](#10-livros-que-faltam-o-pacote-bibliografia)
11. [Como o código está organizado](#11-como-o-código-está-organizado)
12. [Segurança e limites](#12-segurança-e-limites)
13. [Problemas comuns](#13-problemas-comuns)

---

## 1. Como as pastas ficam

No computador (os caminhos abaixo são os padrões):

```
~/documents/estudos/faculdade/
├── livros/                          ← TODOS os livros reais, com nome padronizado.
│                                      É aqui que você joga um livro novo.
├── livros-organizacao/              ← tudo da ferramenta (nada disso fica solto em livros/)
│   ├── organizar_livros.py
│   ├── nucleo.py
│   ├── llm.py                       ← cliente de IA: Gemini grátis -> Claude Haiku (troca automática)
│   ├── bibliografia/                ← pacote que procura livros faltantes
│   ├── livros.csv                   ← a planilha mestra
│   ├── cache/                       ← respostas da API já pagas (ia, ppc, bibliografia)
│   ├── backups/                     ← cópias automáticas do CSV (as 10 últimas)
│   ├── relatorios/                  ← relatórios do pacote `bibliografia`
│   └── .env                         ← chave da API (opcional, veja a seção 3)
├── informacoes-do-curso/ementa.pdf  ← o PPC
└── <disciplina>/
    └── livros/
        ├── basica/                  ← links simbólicos para livros/…
        └── complementar/
```

No Google Drive (destino `gdrive:faculdade`, por exemplo):

```
faculdade/
├── livros/                                    ← os arquivos reais (um por livro)
└── <disciplina>/{basica,complementar}/<livro> ← atalhos do Drive para livros/<livro>
```

Cada livro existe **uma vez** como arquivo real; as pastas de disciplina só apontam para ele.

### Nome padrão dos arquivos

`titulo_autor_edicao.ext` — minúsculo, sem acento, **hífen dentro de cada campo** e **underline só entre os campos**. Sem edição, o campo vira `sem-ed`.

| Antes | Depois |
|---|---|
| `Algoritmos - Teoria e Prática (Thomas H. Cormen, ...).pdf` | `algoritmos-teoria-e-pratica_cormen-et-al_3.pdf` |
| `Cálculo Vol.1 - James Stewart.pdf` | `calculo-vol-1_stewart_7.pdf` |
| `Practical Vim - Drew Neil_1241.pdf` | `practical-vim_neil_sem-ed.pdf` |

Autor: só sobrenomes; até 2 autores unidos por `-e-` (`marconi-e-lakatos`); 3 ou mais viram `primeiro-et-al`.

---

## 2. Instalação

**Arquivos** (copie para `livros-organizacao/`): `organizar_livros.py`, `nucleo.py` e a pasta `bibliografia/`. O `organizar_livros.py` e o `nucleo.py` **precisam ficar na mesma pasta**. Rode sempre a partir dessa pasta:

```bash
cd ~/documents/estudos/faculdade/livros-organizacao
```

**Dependências:**

| O quê | Para quê | Obrigatório? |
|---|---|---|
| Python 3.10+ | tudo | sim |
| `pip install anthropic` | `ia`, `ppc`, `novos`, `recolher`, `bibliografia` | para os comandos que usam a API |
| `poppler` (`pdftotext`, `pdftoppm`, `pdfinfo`) | ler PDFs; `pdftoppm` para PDFs escaneados; `pdfinfo` para `recolher --varrer` | sim, para ler PDFs |
| `rclone` | `drive` e envio automático | só para o Google Drive |
| `pip install pypdf` | alternativa ao `pdftotext` e leitura do autor nos metadados | opcional |
| `notify-send` | aviso na área de trabalho quando algo precisa de revisão | opcional |

No Arch: `sudo pacman -S poppler rclone`.

---

## 3. Configuração

### IA: Gemini grátis primeiro, Claude Haiku quando a cota acabar

Os comandos que usam IA (`ia`, `ppc`, `novos` e a extração do PPC no pacote `bibliografia`) passam pelo módulo `llm.py`, que tenta os provedores nesta ordem:

1. **Gemini** (plano gratuito do Google AI Studio, chave grátis em <https://aistudio.google.com/app/apikey>, sem cartão);
2. **Claude Haiku 4.5** (`claude-haiku-4-5-20251001`, o mais barato), só quando o Gemini não puder: cota do dia esgotada, chave recusada, resposta bloqueada ou fora do ar.

Limite "por minuto" do Gemini: o script espera até 45 s e tenta de novo (de graça) antes de trocar. Cota **diária** esgotada: a troca é imediata e fica registrada em `cache/livros.llm_estado_cache.json`; as próximas execuções nem tentam o Gemini até a cota voltar (meia-noite do horário do Pacífico, cerca das 4h da manhã em Brasília). No fim de cada comando aparece quanto foi usado, por exemplo `IA: Gemini 12 chamada(s) (plano gratuito) | Claude 3 chamada(s), 41230 tokens de entrada / 2100 de saída ≈ US$ 0.045`.

```bash
printf 'GEMINI_API_KEY=...\nANTHROPIC_API_KEY=sk-ant-...\n' >> .env
```

Só uma das chaves também funciona (usa só aquele provedor). Na camada gratuita a Google pode usar o conteúdo enviado para melhorar seus produtos (aqui: texto do PPC e primeiras páginas dos livros).

### Chave da API

`GEMINI_API_KEY` e `ANTHROPIC_API_KEY` podem estar no ambiente ou em um arquivo `.env` (linhas `CHAVE=valor`, `export CHAVE=valor`, aspas e `#` são aceitos). Ele é procurado nesta ordem, e **o ambiente sempre vence** o arquivo:

1. `./.env` (pasta de onde você roda o comando)
2. `livros-organizacao/.env`
3. `faculdade/.env`
4. `~/.config/livros-organizar.env`

```bash
printf 'ANTHROPIC_API_KEY=sk-ant-...\nLIVROS_RCLONE=gdrive:faculdade\n' > .env
chmod 600 .env     # e não versione este arquivo
```

### Variáveis

| Variável | Para quê | Onde pode ficar |
|---|---|---|
| `GEMINI_API_KEY` | chave gratuita do Google AI Studio (`GOOGLE_API_KEY` também vale) | ambiente ou `.env` |
| `ANTHROPIC_API_KEY` | chave da API da Anthropic (paga; só é usada quando o Gemini não puder) | ambiente ou `.env` |
| `LIVROS_LLM` | `auto` (padrão: Gemini → Claude), `gemini` (só Gemini) ou `claude` (só Claude) | ambiente ou `.env` |
| `LIVROS_MODELO_GEMINI` / `LIVROS_MODELO_CLAUDE` | trocam os modelos (padrão `gemini-2.5-flash` / `claude-haiku-4-5-20251001`) | ambiente ou `.env` |
| `LIVROS_GEMINI_ESPERA_MAX` | segundos que vale esperar um limite "por minuto" do Gemini antes de trocar (padrão 45) | ambiente ou `.env` |
| `LIVROS_RCLONE` | destino do Drive, ex.: `gdrive:faculdade`. **Sem isso, nada é enviado ao Drive.** | ambiente ou `.env` |
| `LIVROS_RCLONE_ARGS` | opções extras do rclone, ex.: `--checksum` | ambiente ou `.env` |
| `LIVROS_RAIZ` | se a sua pasta não for `~/documents/estudos/faculdade` | **só no ambiente** (`export`), não no `.env` |

Tudo o mais tem opção de linha de comando (`--raiz`, `--livros`, `--csv`, `--ppc`, `--rclone`…). Os padrões derivam da raiz: `livros = <raiz>/livros`, `csv = <raiz>/livros-organizacao/livros.csv`, `ppc = <raiz>/informacoes-do-curso/ementa.pdf`.

---

## 4. O `livros.csv`

É a **fonte da verdade**. Cada comando lê o CSV, faz uma etapa e grava de volta; o que mexe em arquivos sai sempre dele. Separador `;`, codificação UTF-8. Abra no LibreOffice ou Excel.

| Coluna | Significado |
|---|---|
| `arquivo` | caminho do livro relativo a `livros/` |
| `disciplinas` | disciplinas separadas por `\|`, cada uma com tipo: `algoritmos:basica\|estrutura-de-dados:complementar` |
| `titulo`, `autor`, `edicao` | usados para montar o nome padrão |
| `revisar` | `sim` = a ferramenta não teve certeza; o livro **não é renomeado nem vai ao Drive** até você corrigir e apagar o `sim` |
| `ignorar` | qualquer valor (ex.: `x`) = o livro é pulado por todos os comandos |

Detalhes úteis:

- **Disciplina sem tipo** (`algoritmos`) = ainda não classificada; conta como complementar até o `ppc` classificar.
- O **nome da disciplina** é o nome da pasta (`calculo-diferencial-e-integral-3`). A ferramenta cria a pasta se ela não existir.
- Um livro pode estar em várias disciplinas, com tipos diferentes em cada uma.
- Antes de cada gravação o CSV ganha um backup em `backups/`.

---

## 5. Primeiros passos

Faça nesta ordem. **Todos os comandos que mexem em arquivos têm `--simular`**: rode com ele primeiro e só então sem.

```bash
# 1. gera o CSV a partir dos links simbólicos que você já tem (não sobrescreve um CSV existente)
python3 organizar_livros.py manifesto

# 2. lê as primeiras páginas de cada livro e preenche título/autor/edição
python3 organizar_livros.py ia --limite 3        # teste com 3 livros
python3 organizar_livros.py ia

# 3. classifica cada livro em básica/complementar usando o PPC
python3 organizar_livros.py ppc

# 4. confira o CSV (principalmente as linhas com revisar=sim) e corrija à mão

# 5. se suas pastas de disciplina usam underline, padronize para hífen
python3 organizar_livros.py pastas --simular
python3 organizar_livros.py pastas

# 6. renomeia os livros e cria os links <disciplina>/livros/{basica,complementar}/
python3 organizar_livros.py local --simular
python3 organizar_livros.py local

# 7. envia ao Drive (veja a seção 8)
python3 organizar_livros.py drive --rclone-args=--dry-run
python3 organizar_livros.py drive
```

---

## 6. Uso no dia a dia

### Chegou um livro novo

Copie o arquivo **direto para `livros/`** (não para uma subpasta) e rode:

```bash
python3 organizar_livros.py novos --simular     # só lista o que é novo
python3 organizar_livros.py novos
```

O `novos` faz, só para os livros que ainda não estão no CSV:

1. espera o arquivo ficar 20 s sem alteração (para não pegar uma cópia pela metade);
2. cria uma linha no CSV (`revisar=sim`) com um palpite pelo nome do arquivo;
3. **`ia`**: lê as primeiras páginas e corrige título, autor e edição;
4. **`ppc`**: propõe disciplina e tipo (básica/complementar); se o modelo está confiante e a pasta existe, a marca `revisar` sai;
5. **`local`**: renomeia e cria os links, só dos que não ficaram com `revisar=sim`;
6. **`drive`**, se `LIVROS_RCLONE` estiver definido;
7. mostra um resumo e avisa na área de trabalho se algum livro precisa de revisão.

Se o modelo não teve confiança, o livro **fica onde está**, com `revisar=sim`. Corrija o CSV e rode:

```bash
python3 organizar_livros.py local
python3 organizar_livros.py drive
```

(`novos` não pega o livro de novo, porque ele já está no CSV.)

### Livros espalhados dentro das pastas de disciplina

```bash
python3 organizar_livros.py recolher --varrer      # lista candidatos e PDFs longos suspeitos
python3 organizar_livros.py recolher --simular
python3 organizar_livros.py recolher               # só os de pastas livros/, livro/, livros_*/
python3 organizar_livros.py recolher --tudo --excluir estagio/ prova_2_ia   # tudo do --varrer, menos o excluído
python3 organizar_livros.py recolher "paradigmas-de-programacao/watt.pdf"   # arquivos escolhidos
```

O `recolher` **move** (não copia) os arquivos para `livros/`, usa a pasta de origem como disciplina do livro e depois roda o mesmo processo do `novos`. Cópias idênticas de algo que já está em `livros/` (mesmo conteúdo) não são movidas; o script avisa.

### Mudou arquivos à mão (moveu, tirou de subpasta)?

```bash
python3 organizar_livros.py reconciliar --simular
python3 organizar_livros.py reconciliar
```

Acerta a coluna `arquivo` do CSV procurando o mesmo nome dentro de `livros/`. No fim lista os arquivos de `livros/` que ainda não estão no CSV.

### Mudou a disciplina ou o tipo de um livro?

Edite a coluna `disciplinas` no CSV (ex.: troque `algoritmos:complementar` por `algoritmos:basica`) e rode `local` e depois `drive`. Os links e os atalhos antigos saem sozinhos.

---

## 7. Referência dos comandos

`python3 organizar_livros.py <comando> --help` mostra todas as opções.

| Comando | O que faz | Opções principais |
|---|---|---|
| `manifesto` | gera o CSV a partir dos links simbólicos existentes | `--forcar` (sobrescrever um CSV existente) |
| `ia` | preenche título/autor/edição lendo as primeiras páginas, **só dos livros ainda não conferidos** (`revisar=sim` ou sem título/autor) | `--limite N`, `--paginas N`, `--todos` (reprocessa tudo; pode alterar nomes), `--refazer` |
| `ppc` | classifica livros em básica/complementar e propõe disciplinas para os que não têm | `--paginas 40-160` (trecho do PPC), `--mesclar`, `--refazer`, `--limite N` |
| `pastas` | renomeia pastas de disciplina de `_` para `-` | `--todas`, `--incluir PASTA…`, `--simular` |
| `local` | renomeia os livros e cria os links por disciplina e tipo | `--simular`, `--achatar`, `--aceitar-sem-autor` |
| `liberar` | recalcula `revisar=sim` com as respostas já guardadas (sem API): libera quem a IA e o PPC identificaram com confiança alta e diz o motivo dos que continuam | `--simular` |
| `reconciliar` | acerta o caminho `arquivo` do CSV depois de mover livros à mão | `--simular` |
| `drive` | envia `livros/` ao Drive e cria os atalhos | `--rclone`, `--rclone-args`, `--limpar-copias`, `--sem-podar`, `--simular` |
| `novos` | organiza os livros novos de `livros/` (ia + ppc + local + drive) | `--simular`, `--estavel N`, `--aplicar-tudo`, `--rclone` |
| `recolher` | move livros soltos nas pastas de disciplina para `livros/` e organiza | `--varrer`, `--tudo`, `--excluir TEXTO…`, `--paginas-min N`, `--simular` |

Notas sobre as opções:

- **`ppc`**: por padrão só dá tipo às disciplinas **sem tipo** e **não acrescenta disciplinas** a livros que já têm. `--mesclar` deixa o modelo acrescentar; `--refazer` ignora o cache e reclassifica tudo, **inclusive tipos que você já corrigiu à mão**. Livros que não constam no PPC viram *complementar*.
- **`ia`**: o cache é indexado pelo **conteúdo** do arquivo (tamanho + hash do 1º MiB), então renomear um livro não gasta API de novo. Com `--todos` ele sobrescreve título/autor/edição até dos livros já conferidos e mostra linhas `MUDOU`; como o `local` renomeia os arquivos conforme o CSV, compare com o backup antes de rodá-lo.
- **Substituir um PDF**: apague o arquivo ruim, coloque o bom em `livros/` e rode `novos` (ou `local`). Se o nome padrão for o mesmo de uma linha cujo arquivo não existe mais, as duas viram uma só: fica o arquivo novo com as disciplinas e tipos das duas. No Drive, o `drive` envia o novo por cima do antigo (mesmo nome), e os atalhos continuam valendo.
- **Pasta de disciplina nova**: se o PPC pede uma disciplina que ainda não tem pasta, ela é criada sozinha pelo `local`; só a *confiança* da IA e do PPC decide se o livro precisa de revisão.
- **`ppc`**: uma resposta "nenhuma disciplina" só vale para a lista de pastas daquele momento; criar uma pasta nova faz o livro ser perguntado de novo.
- **`ia` e `ppc`** não têm `--simular` (eles só falam com a API e gravam o CSV, que tem backup); para testar, use `--limite`.
- **`local`**: remove **somente links simbólicos**: os quebrados, os de livros renomeados e os que ficaram em `<disciplina>/livros/` sem fazer mais parte do plano. Nunca apaga livros nem arquivos reais. Se uma disciplina já tem `livro/` ou `livros_texto/`, ele avisa, porque vai criar `livros/` ao lado.
- **`novos --aplicar-tudo`**: renomeia também livros com `revisar=sim`, se tiverem disciplina, título e autor.

---

## 8. Google Drive

### Como funciona o `drive`

1. Sobe para `<remoto>/livros` os livros **prontos** (sem `revisar=sim` e já renomeados) com um único `rclone copy --files-from`. O rclone pula o que já está igual.
2. Lista o Drive e cria, com `rclone backend shortcut`, um **atalho do Drive** em `<disciplina>/{basica,complementar}/` para cada livro. Atalhos que já existem não são recriados; pastas que faltam são criadas.
3. **Recria atalhos que apontam para outro arquivo** (acontece quando você troca um PDF: o antigo sai do Drive, o novo entra com outro ID e o atalho antigo, de mesmo nome, ficaria quebrado). O script compara o ID do alvo do atalho com o ID do arquivo atual em `livros/`. Na simulação (`--simular`) o arquivo novo não é enviado, então essa checagem só acontece na execução de verdade.
4. **Poda atalhos obsoletos** (livro que mudou de tipo/disciplina, foi renomeado ou saiu do CSV). Só atalhos: nunca arquivos reais. `--sem-podar` desliga.
5. Informa arquivos de `livros/` no Drive que não correspondem a nenhum livro pronto (por exemplo, o nome antigo de um livro renomeado). **Não apaga arquivos reais**; revise pelo navegador.

### Configurar

```bash
rclone listremotes                                  # ex.: gdrive:
echo 'LIVROS_RCLONE=gdrive:faculdade' >> .env       # pasta de destino no Drive
python3 organizar_livros.py drive --simular
python3 organizar_livros.py drive --rclone-args=--dry-run   # nada é enviado
python3 organizar_livros.py drive
```

`--rclone-args=--dry-run` (ou `-n`) conta como simulação: nada é enviado e nenhum atalho é criado.

### Limpar um envio antigo

Se alguma vez foram enviadas **cópias reais** para dentro das pastas de disciplina do Drive, elas contam como "já existente" e impedem o atalho:

```bash
python3 organizar_livros.py drive --limpar-copias --simular
python3 organizar_livros.py drive --limpar-copias      # vão para a lixeira do Drive
```

A distinção entre cópia real e atalho depende de um recurso do `rclone` mais novo (o ID de um atalho vem com uma tabulação). Esvazie a lixeira pelo navegador para liberar cota.

### Atenção

- Um atalho só abre para quem também tem acesso ao arquivo original em `livros/`. Ao compartilhar a pasta `faculdade/`, compartilhe a pasta inteira.
- O `client_id` compartilhado do `rclone` está sendo desativado em 2026. Crie o seu em <https://rclone.org/drive/#making-your-own-client-id>.
- Na primeira vez, confira alguns atalhos no navegador (devem aparecer com o ícone de atalho) e a cota com `rclone about gdrive:`.

---

## 9. Automação com systemd

Para organizar um livro **assim que ele é copiado para `livros/`**:

```bash
mkdir -p ~/.config/systemd/user
cp livros-organizar.path livros-organizar.service ~/.config/systemd/user/
# ajuste no .service o caminho do python (venv com o pacote "anthropic") e o remoto do rclone
systemctl --user daemon-reload
systemctl --user enable --now livros-organizar.path
journalctl --user -u livros-organizar.service -f        # acompanhar
```

- Só o **primeiro nível** de `livros/` é vigiado: jogue o arquivo direto lá.
- O serviço roda `novos`; a chave da API vem do `.env` (ou de `~/.config/livros-organizar.env`).
- Uma trava (`livros-organizacao/.lock`) impede duas execuções ao mesmo tempo.

---

### Converter o PPC para Markdown (menos tokens)

`ppc`, `novos`, `recolher` e `bibliografia` mandam o PPC inteiro à API. O PDF extraído tem ~68 mil caracteres; o Markdown gerado a partir dele é mais regular (sem números de página nem quebras de linha no meio de frases):

```bash
python3 -m bibliografia.ppc_markdown ../informacoes-do-curso/ementa.pdf --verificar
# gera ../informacoes-do-curso/ementa.md   (completo: ementas + referências)
python3 -m bibliografia.ppc_markdown ../informacoes-do-curso/ementa.pdf -o ../informacoes-do-curso/ementa-referencias.md --so-referencias
```

| Arquivo | Tamanho | Quando usar |
|---|---:|---|
| `ementa.pdf` (texto extraído) | ~68 mil caracteres | referência |
| `ementa.md` | ~66 mil (−3%) | `ppc`, `novos`, `recolher`: usam as ementas para propor disciplinas |
| `ementa-referencias.md` | ~42 mil (−37%) | `python3 -m bibliografia basica|complementar --ppc …`: só precisa das bibliografias |

- Nenhuma palavra do PPC é removida nem reordenada. `--verificar` compara letra a letra o PDF com o Markdown e acusa qualquer diferença.
- O que muda: somem os números de página e as quebras de linha dentro de frases e referências; os cabeçalhos viram sempre **Básica**/**Complementar**; disciplinas com ementa e referências idênticas (estágios, TCC, tópicos especiais) mostram todos os títulos e o conteúdo uma vez (`--sem-agrupar` desliga); um punhado de defeitos de extração do PDF é remendado de forma explícita (lista em `CORRECOES_DE_TEXTO`, no código).
- **Padrão automático:** se existir `informacoes-do-curso/ementa.md`, ela passa a ser o PPC padrão no lugar do PDF. Para voltar ao PDF, passe `--ppc …/ementa.pdf`.
- `--paginas` só vale para PDF. Se o PPC mudar, gere o `.md` de novo.

## 10. Livros que faltam: o pacote `bibliografia`

Lê o PPC, extrai a bibliografia e diz **o que ainda não está no seu acervo**. **Um tipo de cada vez, de propósito.**

```bash
python3 -m bibliografia basica                      # bibliografia BÁSICA
python3 -m bibliografia basica --so-sem-livros      # só disciplinas sem nenhum livro básico
python3 -m bibliografia complementar                # a complementar, quando quiser
python3 -m bibliografia basica --disciplina redes engenharia   # filtra por trecho do nome da pasta
python3 -m bibliografia basica --sem-arquivos       # só terminal, sem gravar relatório
```

Opções comuns: `--ppc`, `--paginas`, `--csv`, `--raiz`, `--saida`, `--modelo`, `--refazer` (ignora o cache da extração).

**O que acontece:**

1. O Claude extrai a bibliografia do tipo pedido, por disciplina (uma chamada, em cache por tipo, PPC e modelo).
2. Cada obra é comparada com o `livros.csv` por título, autores e volume. **A edição não impede o casamento** (o PPC costuma citar edições antigas); só é sinalizada.
3. Cada obra recebe uma situação:

   | Situação | Significado |
   |---|---|
   | `ok` | está no acervo e vinculada à disciplina com o tipo certo |
   | `tipo_diferente` | vinculada, mas com outro tipo (ex.: o PPC diz básica, o CSV diz complementar) |
   | `sem_vinculo` | está no acervo, mas não ligada a essa disciplina |
   | `ausente` | não está no acervo |

**Saídas** (em `livros-organizacao/relatorios/`):

- `faltantes-basica.md`: resumo por disciplina; **disciplinas sem nenhum livro do tipo (prioridade)** com caixas de seleção, termo de busca e "talvez já tenha"; ajustes sugeridos no CSV; edições diferentes da citada.
- `faltantes-basica.csv`: o mesmo em planilha.

O termo de busca (título, autor, edição) serve para procurar a obra no catálogo da biblioteca da universidade. A ferramenta **não gera links de download**.

---

**Como o casamento decide (e o que ele evita).** Título e autores são comparados palavra a palavra. Se cada título tem palavras que o outro não tem ("C: Como Programar" × "Java: Como Programar", "Organização Estruturada de Computadores" × "Redes de Computadores"), é outra obra. Um título contido no outro só vale se for o começo (subtítulo acrescentado): "Álgebra Linear" não casa com "Geometria Analítica e Álgebra Linear". Subtítulos diferentes são tolerados quando todos os autores do livro estão no PPC. Autores são comparados do jeito que o PPC costuma escrever: com erro de digitação ("LEITHOULD", "TANEMBAUM"), vários nomes numa vírgula só ("FINGER, MELO E SILVA"), sobrenome antes do ponto ("Pressman. Rogers") e sigla ("PMI"). Se o PPC cita algum nome, o livro precisa ter pelo menos um autor em comum, mesmo com título idêntico.

**Traduções.** Se o PPC cita a tradução e você tem o original (ou o contrário), os títulos não batem. Quando um livro já vinculado à disciplina, com o mesmo tipo, é de todos os autores citados e nenhuma outra obra da disciplina o usou, ele conta como presente, mas aparece na seção **3b** do relatório para você confirmar.

**Extração do PPC em lotes.** A bibliografia é pedida à API por lotes de 8 disciplinas (as disciplinas são reconhecidas pelo código, `CPT01003 - ALGORITMOS`, no PDF ou no `.md`). Cada lote vai para o cache assim que termina: se a rede cair no meio, a próxima execução retoma de onde parou. Se uma resposta for cortada pelo limite de saída do modelo, o lote é dividido ao meio automaticamente. Para a análise da bibliografia, prefira o PPC sem ementas (`--ppc ../informacoes-do-curso/ementa-referencias.md`): é 1/3 menor e as chamadas seguintes leem o PPC do cache de prompt.

**Equivalências que você decide (`equivalencias.csv`).** Quando o PPC cita uma edição que o acervo só tem em outra versão (ex.: o PPC pede *Adobe Flex 4 Training from the Source* e você tem o *Flex 4.5 Fundamentals*, dos mesmos autores), o pacote não adivinha: você declara. Crie `livros-organizacao/equivalencias.csv` (ao lado do `livros.csv`; ou use `--equivalencias ARQ`):

```
pasta;obra;arquivo
tecnologias-de-desenvolvimento-de-interface-grafica;Adobe Flex 4 Training from the Source;adobe-flex-4-5-fundamentals_labriola-tapper-e-boles_sem-ed.pdf
```

- `obra` é um **trecho** do título como o PPC escreve (sem diferenciar maiúsculas e acentos); `arquivo` é o nome em `livros/` (coluna `arquivo` do `livros.csv`); `pasta` é opcional (vazio = vale em qualquer disciplina).
- A equivalência diz qual livro é a obra, mas **não cria vínculo**: o livro continua precisando estar ligado à disciplina com o tipo certo (senão aparece na seção 3 para ajustar).
- Linhas em branco e as que começam com `#` são ignoradas. Se o `arquivo` não existir no acervo, o relatório avisa no terminal.

**Disciplinas sem bibliografia do tipo** (estágios, TCC, tópicos especiais, ou qualquer uma cuja ementa muda com o professor) ficam **de fora** do relatório por padrão: nada de linha na tabela nem seção 5. `--incluir-sem-bibliografia` traz de volta.

**As sugestões da seção 3 não são aplicadas sozinhas.** Confira cada uma antes de editar o CSV; depois rode `local` e `drive`.


## 11. Como obter os livros que faltam: o pacote `aquisicao`

Pacote separado (usa só a biblioteca padrão; não depende do `organizar_livros.py`). Lê os relatórios `faltantes-basica` e `faltantes-complementar` (`.csv` ou `.md`) e diz, livro a livro, como conseguir **por vias legítimas**:

```bash
cd livros-organizacao
python3 -m aquisicao relatorios/faltantes-basica.csv relatorios/faltantes-complementar.csv
# sem internet, só os links de busca:     --sem-rede
# baixar o que for de acesso livre:       --baixar   (vai para aquisicao-baixados/, nunca direto para livros/)
```

Saída: `relatorios/aquisicao.md` e `aquisicao.csv`, com quatro grupos: (1) acesso livre (domínio público/acesso aberto), (2) empréstimo digital no Internet Archive/Open Library, (3) e-book à venda (Google Livros, com preço quando a API informa), (4) sem versão digital legal: links para comprar (inclusive usado, na Estante Virtual), procurar em bibliotecas (WorldCat) etc. O mesmo livro em várias disciplinas aparece uma vez.

- As fontes (Open Library e Google Livros) dizem nos próprios metadados se o livro é de acesso livre; **só isso** é baixado, o arquivo é conferido como PDF, nada é sobrescrito e a origem fica registrada em `baixados.csv`.
- Os downloads ficam em quarentena de propósito: se caíssem em `livros/`, o `novos` os processaria na hora.
- O script não procura PDFs em sites sem autorização de distribuição.

## 12. Como o código está organizado

```
organizar_livros.py      ferramenta principal: um comando por etapa (manifesto, ia, ppc, local, drive, novos…)
nucleo.py                código compartilhado: caminhos padrão, slug, CSV, cache, backup, .env, leitura do PPC
llm.py                   cliente de IA com troca automática: Gemini (grátis) -> Claude Haiku 4.5; guarda o estado da cota
bibliografia/
├── modelos.py           dados do domínio (Obra, Livro, Resultado…), sem I/O
├── casamento.py         comparação de títulos/autores/volume/edição (funções puras)
├── acervo.py            lê o livros.csv e devolve objetos Livro
├── ppc.py               extração da bibliografia (interface + implementação com Claude)
├── analise.py           serviço: compara PPC x acervo e classifica cada obra
├── relatorio.py         gera Markdown, CSV e resumo do terminal
├── ppc_markdown.py      converte o PDF do PPC em Markdown compacto (e verifica que nada se perdeu)
├── cli.py               monta as peças e interpreta a linha de comando
└── tests/               101 testes (unittest) do `bibliografia` + 17 do `aquisicao`, sem rede (inclui casos reais do PPC)
```

Princípios: cada módulo faz uma coisa e só conhece os de baixo; a API fica atrás de uma interface (`ExtratorDeBibliografia`), então os testes usam um extrator falso; funções puras para o que é decisão (casamento, análise); efeitos colaterais (disco, rede, rclone) nas bordas.

**Testes:**

```bash
python3 -m unittest discover -s bibliografia/tests -t .
```

---

## 13. Segurança e limites

- **Nada apaga livros.** `local` remove só links simbólicos; `drive` poda só atalhos; `--limpar-copias` remove só cópias reais das pastas de disciplina do Drive (vão para a lixeira); arquivos reais em `livros/` nunca são tocados no Drive.
- **Backups**: o CSV é copiado para `backups/` antes de cada gravação (as 10 últimas ficam).
- **Privacidade**: o texto das primeiras páginas de cada livro (ou imagens, se o PDF for escaneado), os títulos do `livros.csv` e o texto do PPC são enviados à API da Anthropic. A chave fica só no seu ambiente ou `.env`.
- **Custo**: depende do modelo e do tamanho do PPC. Pela experiência no seu acervo, a identificação de ~10 livros custa centavos e uma rodada do `ppc` fica na casa de décimos de dólar (o PPC inteiro é enviado e usa cache de prompt). Os resultados ficam em `cache/`; use `--refazer` só se precisar.
- **Confiança do modelo**: o campo "motivo" que o `ppc` imprime é texto do modelo e pode estar errado. O que vale é o PPC. Confira as linhas `[baixa]` e `[media]`.
- **Direitos autorais**: antes de compartilhar a pasta do Drive com colegas, confira se você pode distribuir cada obra.

---

## 14. Problemas comuns

| Sintoma | Causa e solução |
|---|---|
| `Defina GEMINI_API_KEY ... e/ou ANTHROPIC_API_KEY` | nenhuma chave no ambiente nem em um `.env` dos locais da seção 3 |
| `[llm] gemini em pausa até ... (cota diária esgotada)` | normal: o Gemini grátis acabou por hoje e o Claude Haiku assumiu; volta sozinho no dia seguinte |
| `Nenhum provedor de IA conseguiu responder` | só há uma chave e ela falhou/esgotou, ou as duas falharam; leia as linhas seguintes da mensagem |
| `--modelo` | o padrão agora é `auto` (cada provedor usa o seu); `--modelo claude-sonnet-5-5` força um Claude mais forte nas chamadas que caírem no Claude |
| `ModuleNotFoundError: nucleo` | `organizar_livros.py`/`bibliografia` rodando fora de `livros-organizacao/`, ou `nucleo.py` não foi copiado junto |
| `arquivo não existe` nas linhas do `local` | você moveu arquivos à mão; rode `reconciliar` |
| `As pastas abaixo ainda usam underline` | rode `pastas` antes do `local` (evita pastas duplicadas) |
| O `ia` mudou nomes de livros que eu já tinha conferido | foi rodado com `--todos` (ou numa versão antiga, que reprocessava tudo). Restaure o CSV de `backups/` anterior ao `ia` antes de rodar o `local` |
| Criei a pasta da disciplina, mas o livro continua sem disciplina | a resposta antiga estava em cache; agora o `ppc` reconhece a pasta nova sozinho. Em versão antiga: apague a chave do livro em `cache/livros.ppc_cache.json` |
| Muitos livros novos ficaram com `revisar=sim` apesar de a IA e o PPC terem dado confiança "alta" | versão antiga do script (o cache da `ia` passou a ser por conteúdo e o `ppc` não o encontrava). Atualize e rode `liberar --simular`; a saída do `novos` agora mostra o motivo de cada pendência entre colchetes |
| O `ppc` propôs uma disciplina do PPC que ainda não tem pasta (ex.: `metodos-formais`) | não é problema: a pasta `<disciplina>/livros/<tipo>/` é criada automaticamente pelo `local` (e o `novos` avisa "Pastas de disciplina criadas automaticamente"). Se o nome criado não for o que você queria, renomeie a pasta e corrija a coluna `disciplinas` do CSV |
| Livro ficou em `livros/` com nome original | `revisar=sim` no CSV; corrija a linha, apague o `sim` e rode `local` |
| Troquei um PDF ruim por outro do mesmo livro e o novo não é renomeado ("nome duplicado") | versão antiga: a linha do arquivo apagado continuava no CSV. Agora o `local` junta as duas linhas ("substituição: ..."), mantém as disciplinas e tipos das duas, renomeia o arquivo novo e o `drive` sobrescreve o antigo no Drive |
| `nome duplicado` | dois livros geram o mesmo nome (mesmo título, autor e edição); ajuste a edição/título ou marque um com `x` |
| Nada vai ao Drive | `LIVROS_RCLONE` não definido, ou os livros ainda têm `revisar=sim`/não foram renomeados |
| `rclone` não cria atalhos | a origem precisa existir no Drive primeiro (o envio de `livros/` falhou?); veja o código de saída do `rclone copy` |
| Atalhos viraram arquivos "reais" no Drive | envio antigo: use `drive --limpar-copias` |
| `novos` não faz nada | o arquivo já está no CSV, não está no primeiro nível de `livros/`, ou ainda está sendo gravado |
| `LIVROS_RAIZ` no `.env` não funciona | ele é lido antes do `.env`; exporte no shell |
| O `ppc` continua lendo o PDF | só passa a usar o `.md` se `informacoes-do-curso/ementa.md` existir antes de rodar; senão passe `--ppc …/ementa.md` |
