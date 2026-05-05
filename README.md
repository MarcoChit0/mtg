# MTG Archidekt Pipeline

Pipeline em Python para coletar decks Commander publicos do Archidekt e transformar os dados raw em arquivos JSONL para analise posterior.

O projeto usa `uv` para gerenciar ambiente, lockfile e comandos.

## Requisitos

- Python gerenciado pelo `uv`
- `uv` instalado
- Acesso a internet para a etapa de extracao

Para conferir se o `uv` esta instalado:

```bash
uv --version
```

## Instalacao

Na raiz do projeto:

```bash
uv sync
```

Isso cria o ambiente virtual local e instala o pacote definido em `pyproject.toml`.

## Estrutura do projeto

```text
.
+-- documents/
|   +-- backbone.md
|   +-- archidekt_pipeline.md
+-- scripts/
|   +-- fetch_archidekt_raw.py
|   +-- process_archidekt_raw.py
+-- tests/
|   +-- test_archidekt_pipeline.py
+-- pyproject.toml
+-- uv.lock
+-- README.md
```

Diretorios gerados durante o uso:

```text
data/
+-- raw/
|   +-- archidekt/
+-- processed/
    +-- archidekt/
```

O diretorio `data/` fica no `.gitignore`, pois os dados extraidos podem ficar grandes e sao artefatos locais.

## Visao geral da pipeline

A pipeline tem duas etapas.

1. `fetch-archidekt-raw`

   Baixa dados do Archidekt e salva apenas raws de decks validos para o escopo do projeto.

2. `process-archidekt-raw`

   Le os raws salvos e cria arquivos JSONL processados, separados em decks, cartas e relacao deck-carta.

O segundo script nao chama a API do Archidekt. Ele trabalha somente com os arquivos raw ja salvos.

## Etapa 1: extrair raws do Archidekt

Comando basico:

```bash
uv run fetch-archidekt-raw --max-decks 50 --resume
```

Esse comando tenta salvar 50 decks validos.

Importante: `--max-decks` conta decks validos salvos, nao candidatos baixados. Se alguns candidatos forem invalidos, o script continua buscando ate salvar a quantidade pedida ou ate acabar a busca.

### Entradas esperadas

Esse script nao precisa de arquivos de entrada. Ele consulta a API publica do Archidekt.

Endpoints usados:

```text
https://archidekt.com/api/decks/v3/
https://archidekt.com/api/decks/{deck_id}/
```

### Saidas geradas

Por padrao, os arquivos sao escritos em:

```text
data/raw/archidekt/
```

Arquivos:

- `raw_deck_search_pages.jsonl`
  - paginas raw da busca/listagem do Archidekt;
  - util para auditoria da extracao.

- `raw_deck_details.jsonl`
  - detalhes raw completos dos decks validos;
  - este e o arquivo principal da etapa raw.

- `fetch_manifest.jsonl`
  - resumo de cada execucao;
  - inclui parametros usados, quantidade salva, quantidade rejeitada e motivos de rejeicao.

### Parametros principais

```bash
uv run fetch-archidekt-raw --help
```

Parametros:

- `--min-views`
  - minimo de visualizacoes no Archidekt;
  - padrao: `1000`.

- `--brackets`
  - brackets EDH aceitos;
  - padrao: `2 3 4`.

- `--out-dir`
  - diretorio de saida raw;
  - padrao: `data/raw/archidekt`.

- `--sleep-sec`
  - pausa entre chamadas da API;
  - padrao: `0.25`.

- `--max-decks`
  - numero maximo de decks validos a salvar nesta execucao;
  - se omitido, tenta coletar todos os candidatos encontrados acima do limite de views.

- `--resume`
  - pula decks ja presentes em `raw_deck_details.jsonl`.

- `--dry-run`
  - mostra quais detalhes seriam buscados, sem salvar payloads de deck.

### Exemplos

Coletar 50 decks validos:

```bash
uv run fetch-archidekt-raw --max-decks 50 --resume
```

Coletar apenas bracket 3:

```bash
uv run fetch-archidekt-raw --brackets 3 --max-decks 100 --resume
```

Coletar com minimo de 500 views:

```bash
uv run fetch-archidekt-raw --min-views 500 --max-decks 100 --resume
```

## Etapa 2: processar raws

Comando basico:

```bash
uv run process-archidekt-raw --overwrite
```

### Entradas esperadas

Por padrao, o script espera:

```text
data/raw/archidekt/raw_deck_details.jsonl
```

Esse arquivo e criado pela etapa `fetch-archidekt-raw`.

### Saidas geradas

Por padrao, os arquivos sao escritos em:

```text
data/processed/archidekt/
```

Arquivos:

- `cards.jsonl`
  - uma linha por carta canonica unica;
  - usa `card.oracleCard.uid` como identificador;
  - preserva o raw canonico de `card.oracleCard`.

- `decks.jsonl`
  - uma linha por snapshot de deck aceito;
  - inclui metadata do deck, timestamp de extracao e mainboard processado.

- `deck_cards.jsonl`
  - formato longo;
  - uma linha por carta incluida em cada snapshot.

- `processing_manifest.jsonl`
  - resumo de cada execucao do processamento.

- `rejected_decks.jsonl`
  - decks rejeitados durante o processamento;
  - normalmente deve ficar vazio se os raws foram gerados pela versao atual do fetcher;
  - ainda e util caso regras mudem ou existam raws antigos.

### Parametros principais

```bash
uv run process-archidekt-raw --help
```

Parametros:

- `--raw-dir`
  - diretorio com `raw_deck_details.jsonl`;
  - padrao: `data/raw/archidekt`.

- `--out-dir`
  - diretorio de saida processada;
  - padrao: `data/processed/archidekt`.

- `--min-views`
  - minimo de visualizacoes aceito no processamento;
  - padrao: `1000`.

- `--brackets`
  - brackets aceitos;
  - padrao: `2 3 4`.

- `--overwrite`
  - remove arquivos processados anteriores antes de escrever novos.

### Exemplos

Processar dados com os caminhos padrao:

```bash
uv run process-archidekt-raw --overwrite
```

Processar raws de outro diretorio:

```bash
uv run process-archidekt-raw \
  --raw-dir data/raw/archidekt_test \
  --out-dir data/processed/archidekt_test \
  --overwrite
```

## Regras de validade dos decks

Um deck so e salvo/processado se:

- for publico;
- nao for unlisted;
- tiver formato Commander (`deckFormat == 3`);
- tiver bracket informado entre `2` e `4`;
- tiver pelo menos `1000` views, por padrao;
- tiver exatamente 100 cartas no deck Commander incluido.

Para calcular o total de 100 cartas:

- comandantes contam dentro das 100 cartas;
- Maybeboard e excluido;
- Sideboard e excluido;
- Tokens & Extras e excluido;
- Companion e excluido;
- cartas deletadas sao excluidas;
- categorias com `includedInDeck == false` sao excluidas;
- a categoria `Tokens`, quando incluida normalmente, e mantida.

Validacao Commander pragmatica:

- exige pelo menos um comandante;
- aceita multiplos comandantes;
- identifica comandantes por categoria `Commander` ou categoria com `isPremier == true`;
- exige cartas legais em Commander;
- aplica singleton por `oracle_uid`, com excecao para terrenos basicos e cartas que permitem multiplas copias;
- valida identidade de cor pela uniao das identidades de cor dos comandantes.

## Cartas canonicas

O projeto ignora printings e aparencia da carta.

Nao sao usados como dado principal:

- edicao;
- collector number;
- imagem;
- arte;
- foil/non-foil;
- identificadores de printing.

A identidade da carta e:

```text
card.oracleCard.uid
```

O conteudo canonico salvo vem de:

```text
card.oracleCard
```

## Rodar testes

```bash
uv run python -m unittest discover -s tests -v
```

Os testes usam mocks e nao dependem de internet.

## Fluxo recomendado

Para uma coleta pequena:

```bash
uv sync
uv run fetch-archidekt-raw --max-decks 50 --resume
uv run process-archidekt-raw --overwrite
uv run python -m unittest discover -s tests -v
```

Para aumentar a base:

```bash
uv run fetch-archidekt-raw --max-decks 500 --resume
uv run process-archidekt-raw --overwrite
```

Para tentar coletar todos os decks encontrados acima do limite de views:

```bash
uv run fetch-archidekt-raw --resume
uv run process-archidekt-raw --overwrite
```
