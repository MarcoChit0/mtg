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
|   +-- download_archidekt_processed.py
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

0. `restore-archidekt-raw`

   Baixa o arquivo raw compartilhado no Google Drive e restaura os JSONL em `data/raw/archidekt`.

1. `fetch-archidekt-raw`

   Baixa dados do Archidekt e salva apenas raws de decks validos para o escopo do projeto.

2. `process-archidekt-raw` — **duas fases**:
   - **Fase A (ingest)**: le os raws, deduplica por `deck_id`, por lista de cartas (fingerprint SHA-256) e contra snapshots ja processados; escreve `cards.jsonl` e `decks.jsonl`. O mainboard de cada deck e armazenado inline no proprio registro de `decks.jsonl` (nao ha mais `deck_cards.jsonl`).
   - **Fase B (enrich y2)**: para cada deck sem rotulo da calculadora externa, abre uma instancia headless de Chromium, submete o decklist em https://edhpowerlevel.com/, e anexa o campo `edhpowerlevel` (com o `commander_bracket`, Power Level, Score, etc.) ao registro do deck. Pode ser pulada com `--skip-y2` ou executada isolada com `--y2-only`.

3. `build-archidekt-features`

   Le `decks.jsonl` + `cards.jsonl` (e opcionalmente o raw, para preco e raridade) e gera as duas representacoes prontas para modelagem: `deck_features.jsonl` (Deck Features descritas na secao 11 do backbone) e `bag_of_cards.jsonl` (Bag of Cards esparso por snapshot).

Os scripts 2 e 3 nao chamam a API do Archidekt. A Fase B do script 2 e a unica chamada de rede fora da Etapa 1.

## Etapa 0: restaurar raws do Google Drive

### Requisitos do Google Drive

Este script nao usa a API autenticada do Google Drive, OAuth, nem login no navegador. Ele baixa o arquivo pelo link publico de compartilhamento do proprio Drive. Para funcionar, o arquivo precisa estar compartilhado assim:

1. No Google Drive, coloque os raws em um arquivo ZIP. O arquivo usado neste projeto e:

```text
MTG/DATA/Archive.zip
```

2. Dentro do ZIP devem existir estes tres arquivos, em qualquer pasta ou na raiz do ZIP:

```text
fetch_manifest.jsonl
raw_deck_details.jsonl
raw_deck_search_pages.jsonl
```

3. Clique com botao direito em `Archive.zip` no Drive, abra **Compartilhar**, e altere o acesso geral para:

```text
Qualquer pessoa com o link
```

ou, em ingles:

```text
Anyone with the link
```

4. Copie o link do arquivo ZIP. O link deve ter este formato:

```text
https://drive.google.com/file/d/<FILE_ID>/view?usp=sharing
```

O script extrai o `<FILE_ID>` automaticamente. Tambem e possivel passar so o id com `--file-id`.

Importante: o caminho `MTG/DATA/Archive.zip` ajuda voce a encontrar o arquivo na sua conta, mas o script nao consegue baixar pelo caminho interno do Drive. Ele precisa do link compartilhavel do arquivo ou do `file_id`.

Como o ZIP e grande, o Google Drive mostra o aviso "Google Drive can't scan this file for viruses". O script ja trata esse aviso e segue o botao "Download anyway" automaticamente. Se o arquivo estiver restrito, o Drive devolve uma pagina de login e o script falha; nesse caso, confira o compartilhamento "Qualquer pessoa com o link".

Espaco em disco recomendado para esta restauracao:

- aproximadamente `618 MB` para `Archive.zip`;
- aproximadamente `4.3 GB` para `raw_deck_details.jsonl`;
- mais os dados processados em `data/processed/archidekt`.

Na pratica, deixe pelo menos `6-8 GB` livres para a etapa raw + processada.

Comando basico:

```bash
uv run restore-archidekt-raw
```

Por padrao, esse comando baixa o `Archive.zip` compartilhado no Google Drive, extrai os raws e roda `process-archidekt-raw --skip-y2` para gerar os dados processados sem chamar a calculadora externa.

Para usar outro link do Drive:

```bash
uv run restore-archidekt-raw --drive-url "https://drive.google.com/file/d/<FILE_ID>/view?usp=sharing"
```

Raw restaurado:

```text
data/raw/archidekt/fetch_manifest.jsonl
data/raw/archidekt/raw_deck_details.jsonl
data/raw/archidekt/raw_deck_search_pages.jsonl
```

Processado gerado:

```text
data/processed/archidekt/cards.jsonl
data/processed/archidekt/decks.jsonl
data/processed/archidekt/processing_manifest.jsonl
data/processed/archidekt/rejected_decks.jsonl
```

Se `data/raw/archidekt/Archive.zip` ja existir, o script reutiliza o arquivo local. Se os JSONL raw ja existirem, eles sao preservados; use `--overwrite` para sobrescrever. Para sobrescrever os processados, use `--process-overwrite`.

Parametros uteis:

- `--drive-url URL` — usa outro link do Google Drive.
- `--file-id ID` — usa diretamente o id do arquivo do Drive.
- `--out-dir DIR` — diretorio de destino; padrao `data/raw/archidekt`.
- `--processed-dir DIR` — diretorio processado; padrao `data/processed/archidekt`.
- `--archive PATH` — caminho local do zip; padrao `<out-dir>/Archive.zip`.
- `--force-download` — baixa novamente mesmo se o zip ja existir.
- `--overwrite` — sobrescreve JSONL ja existentes.
- `--download-only` — baixa o zip sem extrair.
- `--skip-process` — restaura apenas os raws, sem processar.
- `--process-overwrite` — passa `--overwrite` para o processamento.
- `--process-y2` — tambem roda o enriquecimento do EDHPowerLevel; por padrao ele fica desligado.
- `--workers N` — workers usados se `--process-y2` estiver ativo.

## Etapa 0b: restaurar processados do Google Drive

Use esta etapa quando voce ja tem o ZIP processado pronto no Drive:

```text
MTG/DATA/processed.zip
```

Assim como na restauracao raw, o script precisa do link compartilhavel do
arquivo ou do `file_id`; o caminho interno `MTG/DATA/processed.zip` serve para
encontrar o arquivo no Drive, mas nao e suficiente para baixar sem API
autenticada.

### Como rodar

Entre na raiz do projeto:

```bash
cd /Users/macsilva/Desktop/mtg
```

Se o arquivo `processed.zip` ja estiver na raiz do projeto, rode:

```bash
uv run restore-archidekt-processed --overwrite
```

Isso extrai os dados para:

```text
data/processed/archidekt/
```

e imprime o relatorio no terminal. Para salvar o relatorio em arquivo:

```bash
uv run restore-archidekt-processed \
  --overwrite \
  --report-path data/processed/archidekt/processed_restore_report.json
```

Para baixar direto do Google Drive:

```bash
uv run restore-archidekt-processed \
  --drive-url "https://drive.google.com/file/d/<FILE_ID>/view?usp=sharing" \
  --overwrite
```

Tambem da para exportar o link via ambiente e deixar o comando limpo:

```bash
export ARCHIDEKT_PROCESSED_DRIVE_URL="https://drive.google.com/file/d/<FILE_ID>/view?usp=sharing"
uv run restore-archidekt-processed --overwrite
```

Antes de baixar pelo Drive, confira que o arquivo esta compartilhado como
`Qualquer pessoa com o link`.

O comando extrai os arquivos esperados para `data/processed/archidekt` e, por
padrao, imprime um relatorio JSON com:

- quantidade de snapshots e decks unicos;
- distribuicao de brackets Archidekt e EDHPowerLevel;
- cobertura de rotulos EDHPowerLevel;
- distribuicao de identidades de cor e comandantes mais frequentes;
- checagens de `mainboard_count == 100`, alinhamento de `snapshot_id` entre
  `decks.jsonl`, `deck_features.jsonl` e `bag_of_cards.jsonl`, e cobertura de
  cartas referenciadas em `cards.jsonl`.

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
  - pausa por worker apos chamadas de detalhe, e tambem entre paginas de busca;
  - padrao: `0.25`.

- `--max-decks`
  - numero maximo de decks validos a salvar nesta execucao;
  - se omitido, tenta coletar todos os candidatos encontrados acima do limite de views.

- `--workers`
  - numero de workers paralelos buscando payloads de detalhe do Archidekt;
  - padrao: `1`.

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

Coletar com 32 workers de detalhe:

```bash
uv run fetch-archidekt-raw --max-decks 1000 --resume --workers 32
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
- `--workers N` — numero de browsers Chromium paralelos consultando o EDHPowerLevel (padrao `1`).

### Sobre a calculadora externa (Fase B)

O site `https://edhpowerlevel.com/` nao tem API publica: o calculo roda no navegador. Esta etapa usa Playwright + Chromium para abrir a pagina, colar o decklist (formato `<qty> <card name>`), clicar *Analyze* e extrair o `Commander Bracket` recomendado (alem das outras metricas que o site exibe).

Latencia tipica: **~7-8 segundos por deck** (dominado por `--y2-analysis-wait`). Para uma base de 12-13k decks, planeje **~24-30 horas de wall time**. Use `--y2-max-decks` para fracionar a execucao; o progresso fica salvo em `edhpowerlevel_results.jsonl` e em `decks.jsonl` (reescrito a cada `--y2-flush-every` analises).

Com `--workers`, cada worker abre seu proprio Playwright + Chromium. Por exemplo, `--workers 32` tenta manter 32 analises simultaneas, mas tambem consome muita RAM e pode acionar rate-limit ou instabilidade do site.

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

Rodar a Fase B com 32 browsers em paralelo:

```bash
uv run process-archidekt-raw --y2-only --workers 32 --y2-sleep 0
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

O `process-archidekt-raw` faz uma checagem antes de abrir os workers. Se o Chromium do Playwright nao estiver instalado, ele para antes de iniciar as threads e mostra esse comando. Em Ubuntu/Debian, se o Chromium estiver instalado mas faltarem bibliotecas do sistema, rode tambem:

```bash
uv run playwright install-deps chromium
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
