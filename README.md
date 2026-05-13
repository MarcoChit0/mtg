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
|   +-- edhpowerlevel_client.py
|   +-- build_features.py
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

A pipeline tem tres etapas.

1. `fetch-archidekt-raw`

   Baixa dados do Archidekt e salva apenas raws de decks validos para o escopo do projeto.

2. `process-archidekt-raw` — **duas fases**:
   - **Fase A (ingest)**: le os raws, deduplica por `deck_id`, por lista de cartas (fingerprint SHA-256) e contra snapshots ja processados; escreve `cards.jsonl` e `decks.jsonl`. O mainboard de cada deck e armazenado inline no proprio registro de `decks.jsonl` (nao ha mais `deck_cards.jsonl`).
   - **Fase B (enrich y2)**: para cada deck sem rotulo da calculadora externa, abre uma instancia headless de Chromium, submete o decklist em https://edhpowerlevel.com/, e anexa o campo `edhpowerlevel` (com o `commander_bracket`, Power Level, Score, etc.) ao registro do deck. Pode ser pulada com `--skip-y2` ou executada isolada com `--y2-only`.

3. `build-archidekt-features`

   Le `decks.jsonl` + `cards.jsonl` (e opcionalmente o raw, para preco e raridade) e gera as duas representacoes prontas para modelagem: `deck_features.jsonl` (Deck Features descritas na secao 11 do backbone) e `bag_of_cards.jsonl` (Bag of Cards esparso por snapshot).

Os scripts 2 e 3 nao chamam a API do Archidekt. A Fase B do script 2 e a unica chamada de rede fora da Etapa 1.

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

- `--no-progress`
  - desliga a barra de progresso no stderr;
  - util quando a saida vai para arquivo ou pipeline.

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

- `cards.jsonl` — uma linha por carta canonica unica (`card.oracleCard.uid` como id); preserva o raw de `card.oracleCard`.

- `decks.jsonl` — uma linha por snapshot de deck aceito. Inclui:
  - metadata do deck (`raw_deck_metadata`);
  - timestamp de extracao (`fetched_at`);
  - mainboard inline (campo `mainboard`, com uma entrada por carta-no-deck);
  - `owner_id` do criador no Archidekt (para analises por usuario);
  - **`archidekt_edh_bracket`** — rotulo `y1` (percepcao comunitaria);
  - **`edhpowerlevel`** — rotulo `y2` (saida da calculadora). `None` enquanto a Fase B nao tiver enriquecido o deck; um dict com `commander_bracket`, `power_level`, `tipping_point`, `score`, `efficiency`, `impact`, `average_playability` apos sucesso; um dict com `error` se a tentativa falhou.

- `processing_manifest.jsonl` — resumo de cada execucao (Fase A + Fase B), incluindo distribuicao de brackets retornados pela calculadora.

- `rejected_decks.jsonl` — decks rejeitados durante o processamento.

- `edhpowerlevel_results.jsonl` — log append-only da Fase B (uma linha por tentativa de consulta). Serve como write-ahead log: se a Fase B for interrompida, na proxima execucao o estado e reaplicado a `decks.jsonl` antes de retomar de onde parou.

### Parametros principais

```bash
uv run process-archidekt-raw --help
```

Parametros gerais:

- `--raw-dir` (padrao `data/raw/archidekt`).
- `--out-dir` (padrao `data/processed/archidekt`).
- `--min-views` (padrao `1000`).
- `--brackets` (padrao `2 3 4`).
- `--overwrite` — remove todos os arquivos processados antes de escrever novos.

Parametros da Fase B (EDHPowerLevel):

- `--skip-y2` — pula a Fase B; util quando voce so quer ingerir.
- `--y2-only` — pula a Fase A e roda apenas a Fase B sobre `decks.jsonl` existente.
- `--y2-max-decks N` — limita quantos decks consultar nesta execucao (resume-friendly).
- `--y2-sleep S` — segundos entre consultas (padrao `0.5`).
- `--y2-analysis-wait S` — segundos para esperar o calculo renderizar apos clicar Analyze (padrao `6.0`).
- `--y2-recycle-every N` — recria a pagina a cada N analises (padrao `50`).
- `--y2-flush-every N` — reescreve `decks.jsonl` com o progresso atual a cada N analises (padrao `25`).
- `--y2-headed` — abre o Chromium com janela visivel (debug).
- `--y2-retry-failed` — re-consulta decks cujo y2 anterior tenha sido um erro.

### Sobre a calculadora externa (Fase B)

O site `https://edhpowerlevel.com/` nao tem API publica: o calculo roda no navegador. Esta etapa usa Playwright + Chromium para abrir a pagina, colar o decklist (formato `<qty> <card name>`), clicar *Analyze* e extrair o `Commander Bracket` recomendado (alem das outras metricas que o site exibe).

Latencia tipica: **~7-8 segundos por deck** (dominado por `--y2-analysis-wait`). Para uma base de 12-13k decks, planeje **~24-30 horas de wall time**. Use `--y2-max-decks` para fracionar a execucao; o progresso fica salvo em `edhpowerlevel_results.jsonl` e em `decks.jsonl` (reescrito a cada `--y2-flush-every` analises).

### Exemplos

Pipeline completo (Fase A + Fase B):

```bash
uv run process-archidekt-raw --overwrite
```

So ingest, sem chamar a calculadora:

```bash
uv run process-archidekt-raw --overwrite --skip-y2
```

So enriquecer y2 sobre `decks.jsonl` existente:

```bash
uv run process-archidekt-raw --y2-only
```

Rodar a Fase B em lotes (por exemplo, 500 decks por vez):

```bash
uv run process-archidekt-raw --y2-only --y2-max-decks 500
```

Re-tentar decks que falharam:

```bash
uv run process-archidekt-raw --y2-only --y2-retry-failed
```

### Setup do Playwright

A primeira execucao com Phase B precisa do navegador instalado:

```bash
uv sync
uv run playwright install chromium
```

## Etapa 3: construir features para modelagem

Comando basico:

```bash
uv run build-archidekt-features --overwrite
```

### Entradas esperadas

```text
data/processed/archidekt/decks.jsonl
data/processed/archidekt/cards.jsonl
data/raw/archidekt/raw_deck_details.jsonl   # opcional, para preco e raridade
```

### Saidas geradas

Por padrao, os arquivos sao escritos em `data/processed/archidekt/`:

- `deck_features.jsonl`
  - uma linha por snapshot de deck;
  - cobre as features das secoes 11.1.A ate 11.1.J (Estrutura, Cores, Mana base, Curva, Tipos, Categorias, Flags de bracket, Combos, Popularidade/Preco/Salt, Raridade);
  - cobre as features secundarias 11.2.K (Keywords), 11.2.L (Supertipos/Subtipos) e 11.2.M (Multiface/Layout);
  - inclui `archidekt_edh_bracket` como rotulo `y1`.

- `bag_of_cards.jsonl`
  - uma linha por snapshot;
  - campo `counts` mapeia `oracle_uid` -> quantidade no mainboard;
  - basicos contam por quantidade; cartas multiface contam como um slot.

- `feature_manifest.jsonl`
  - resumo de cada execucao (decks processados, lookup de printing carregado, erros agregados).

### Parametros principais

```bash
uv run build-archidekt-features --help
```

- `--processed-dir` (padrao `data/processed/archidekt`): diretorio com `decks.jsonl`/`cards.jsonl`.
- `--raw-dir` (padrao `data/raw/archidekt`): usado para juntar `rarity` e `prices`, que sao de nivel de printing e nao ficam em `cards.jsonl`.
- `--out-dir` (padrao igual a `--processed-dir`).
- `--no-printing-features`: pula a leitura do raw; preco e raridade saem como `0`/`None`.
- `--overwrite`: substitui as saidas existentes em vez de pular snapshots ja gerados.

### Notas sobre features de preco e raridade

Preco e raridade dependem da printing especifica de cada slot do deck. Como `cards.jsonl` so guarda o `oracleCard` canonico, o script reabre `raw_deck_details.jsonl` e indexa `(deck_id, deck_row_id) -> {rarity, prices}` para anexar essas features. Preco usa preferencialmente TCGPlayer paper non-foil (`tcg`), com fallback para outros vendors de papel.

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
uv run build-archidekt-features --overwrite
uv run python -m unittest discover -s tests -v
```

Para aumentar a base:

```bash
uv run fetch-archidekt-raw --max-decks 500 --resume
uv run process-archidekt-raw --overwrite
uv run build-archidekt-features --overwrite
```

Para tentar coletar todos os decks encontrados acima do limite de views:

```bash
uv run fetch-archidekt-raw --resume
uv run process-archidekt-raw --overwrite
uv run build-archidekt-features --overwrite
```
