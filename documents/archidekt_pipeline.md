# Implementacao do passo de coleta Archidekt

Este documento registra como foi implementado o primeiro passo operacional descrito em `documents/backbone.md`: coletar decks publicos de Commander do Archidekt, filtrar decks validos dentro do escopo e preparar uma base raw/processada para etapas futuras de Bag of Cards e Deck Features.

O objetivo aqui nao e ensinar um usuario novo a rodar o projeto. Esse papel fica no `README.md`. Este arquivo existe para documentar as escolhas internas, os detalhes de validacao e os contratos de dados que sustentam a implementacao.

## Relacao com o backbone

O `backbone.md` define que a base deve vir do Archidekt e que, nesta etapa, o raw JSON do Archidekt e suficiente. Tambem define que os decks considerados devem ser:

- publicos;
- formato Commander;
- legais e validos para Commander;
- com pelo menos 1000 visualizacoes inicialmente;
- com bracket informado;
- bracket entre 2 e 4;
- exatamente 100 cartas no mainboard;
- sem Maybeboard, Sideboard, Tokens/Extras ou qualquer item fora do deck principal.

A implementacao atual cobre esse recorte por meio de dois scripts:

- `scripts/fetch_archidekt_raw.py`
- `scripts/process_archidekt_raw.py`

A decisao final foi salvar raw apenas de decks que ja passam nos filtros do projeto. Isso reduz lixo persistido em `data/raw/archidekt/raw_deck_details.jsonl`. Mesmo assim, a arquitetura permanece em duas etapas: a extracao chama o Archidekt; o processamento trabalha apenas sobre raw salvo.

## Decisao arquitetural: duas etapas

A pipeline foi separada para manter uma fronteira clara entre coleta e transformacao:

1. `fetch_archidekt_raw.py`
   - chama a API do Archidekt;
   - busca paginas de listagem;
   - baixa detalhes completos dos decks candidatos;
   - valida os detalhes completos;
   - salva somente raws de decks validos.

2. `process_archidekt_raw.py`
   - nao chama a API;
   - le `raw_deck_details.jsonl`;
   - deduplica cartas canonicas;
   - escreve tabelas JSONL para uso analitico.

Essa separacao permite que a etapa futura de feature engineering seja refeita sem depender de novas chamadas ao Archidekt, desde que os raws validos ja estejam salvos.

## API do Archidekt usada

Foram verificados empiricamente dois endpoints publicos:

```text
https://archidekt.com/api/decks/v3/?deckFormat=3&edhBracket={bracket}&orderBy=-viewCount&page={page}
https://archidekt.com/api/decks/{deck_id}/
```

Observacoes importantes:

- `deckFormat == 3` representa Commander.
- `edhBracket` vem no detalhe e na listagem.
- A listagem retorna `results`, com metadados suficientes para selecionar candidatos iniciais.
- O campo `count` da listagem nao deve ser usado como unica fonte para decidir quando parar; a implementacao pagina ate pagina vazia, pagina abaixo do minimo de views ou limite de decks validos salvo.
- O detalhe do deck contem `cards`, `categories`, `viewCount`, `private`, `unlisted`, `deckFormat`, `edhBracket`, `updatedAt` e os metadados canonicos das cartas em `card.oracleCard`.

## Contrato de raw salvo

O arquivo `raw_deck_details.jsonl` deve conter somente decks validos para o escopo atual.

Cada linha e um wrapper com metadados de fetch:

```text
record_type
run_id
fetched_at
deck_id
detail_url
status
response
```

O campo `response` preserva o detalhe completo retornado pelo Archidekt para aquele deck valido. O timestamp `fetched_at` e importante porque o mesmo deck pode mudar ao longo do tempo.

Os candidatos invalidos nao sao salvos em `raw_deck_details.jsonl`. Seus motivos de rejeicao ficam agregados no `fetch_manifest.jsonl`, nao como payload completo persistido.

## Contrato de processamento

O processamento gera quatro saidas principais:

- `cards.jsonl`
- `decks.jsonl`
- `deck_cards.jsonl`
- `processing_manifest.jsonl`

Tambem existe `rejected_decks.jsonl` como protecao para raws antigos ou mudancas futuras de regra. Com raws gerados pela versao atual do fetcher, a expectativa e que esse arquivo fique vazio ou quase vazio.

### `cards.jsonl`

Unidade: carta canonica unica.

Identificador:

```text
card.oracleCard.uid
```

O registro preserva `raw_oracle_card`, isto e, o objeto `card.oracleCard` do Archidekt. Isso esta alinhado ao backbone, que quer cartas como entidades estaticas e independentes dos snapshots de deck.

Nao ha tabela de printings. Essa foi uma decisao explicita: o projeto nao pretende modelar aparencia, edicao, collector number, foil, arte ou variacao de printing.

### `decks.jsonl`

Unidade: snapshot de deck aceito.

O snapshot usa:

```text
snapshot_id = archidekt:{deck_id}:{fetched_at}
```

Isso evita sobrescrever o mesmo deck em coletas diferentes. Se o criador alterar a lista, uma nova coleta gera um novo snapshot.

O registro contem:

- metadados do deck;
- bracket Archidekt;
- view count;
- timestamp de extracao;
- comandantes detectados;
- contagem de mainboard;
- mainboard processado com ponteiros para `oracle_uid`;
- `raw_deck_metadata` sem duplicar os objetos raw das cartas.

### `deck_cards.jsonl`

Unidade: relacao longa deck-carta.

Esse arquivo facilita carregar os dados em pandas/R sem explodir manualmente `decks.jsonl`.

Cada linha contem:

- `snapshot_id`;
- `deck_id`;
- `fetched_at`;
- `oracle_uid`;
- `oracle_name`;
- `quantity`;
- categorias da carta naquele deck;
- flag `is_commander`;
- metadados do row do deck no Archidekt.

## Definicao operacional de mainboard

O Archidekt permite categorias customizadas. Por isso, a implementacao nao confia apenas no campo `size` da listagem.

O mainboard do projeto e calculado a partir do detalhe completo:

1. Comeca em `response.cards`.
2. Remove rows com `deletedAt != null`.
3. Remove rows com `companion == true`.
4. Remove rows em categorias normalizadas como:
   - `Maybeboard`;
   - `Sideboard`;
   - `Tokens & Extras`.
5. Remove rows em qualquer categoria do deck com `includedInDeck == false`.
6. Mantem a categoria `Tokens` quando ela e uma categoria normal incluida no deck.
7. Soma `quantity`.
8. Aceita somente se a soma final for exatamente 100.

Comandantes contam dentro dessas 100 cartas.

## Normalizacao de categorias

Categorias sao normalizadas com `casefold` e remocao de caracteres nao alfanumericos.

Isso faz variantes como estas cairem no mesmo criterio:

```text
Tokens & Extras
tokens extras
Tokens/Extras
```

O objetivo e reduzir fragilidade contra pequenas diferencas de escrita no Archidekt.

## Deteccao de comandante

Inicialmente a implementacao procurava a categoria literal `Commander`. Durante a validacao com raws reais, apareceu um caso em que a categoria premier foi renomeada para `My Baeba`, contendo `Baba Lysaga, Night Witch`.

Por isso, a regra atual e:

- uma carta e comandante se estiver em categoria normalizada como `Commander`; ou
- se estiver em uma categoria do deck com `isPremier == true`.

Essa regra reflete melhor o comportamento do Archidekt: `isPremier` nao e um campo da carta, mas um campo da categoria do deck que marca o slot principal/premier, normalmente usado para comandante.

Decks com multiplos comandantes sao aceitos. A identidade de cor do deck e calculada como a uniao das identidades de cor dos comandantes detectados.

## Validacao Commander pragmatica

O backbone pede decks legais e validos para o formato. A implementacao adotou uma validacao pragmatica, sem tentar reproduzir todas as excecoes completas das regras oficiais.

Regras implementadas:

- exigir pelo menos um comandante detectado;
- aceitar multiplos comandantes;
- exigir `oracleCard.legalities.commander == "legal"` para toda carta incluida;
- aplicar singleton por `oracle_uid`;
- permitir multiplas copias de terrenos basicos;
- permitir multiplas copias quando o texto oracle indica permissao explicita;
- validar identidade de cor contra a uniao dos comandantes.

Limite conhecido: a implementacao nao valida todos os mecanismos especificos de elegibilidade de comandante, como combinacoes detalhadas de partner/background/doctor. Essa escolha foi feita para manter a primeira coleta robusta e pratica sem criar uma engine completa de regras de Commander.

## Identidade canonica da carta

O projeto usa:

```text
card.oracleCard.uid
```

como identificador canonico da carta.

Motivo:

- Bag of Cards deve representar a identidade da carta, nao a impressao especifica;
- cartas multiface continuam sendo uma unica carta no deck;
- metadados relevantes para features futuras estao no `oracleCard`;
- printings podem introduzir variacao irrelevante para o objetivo cientifico do projeto.

Campos como edicao, collector number, imagem e foil sao ignorados como dados principais.

## Relacao com Bag of Cards e Deck Features

A etapa atual nao cria ainda as matrizes finais de features. Ela prepara os dados para isso.

Para Bag of Cards:

- `deck_cards.jsonl` fornece `snapshot_id`, `oracle_uid` e `quantity`;
- cada `oracle_uid` pode virar uma coluna;
- `quantity` vira o valor da feature.

Para Deck Features:

- `cards.jsonl` preserva `oracleCard`, com tipos, cores, CMC, keywords, legalidades, combos, salt, EDHREC rank e flags de bracket;
- `decks.jsonl` preserva categorias e metadata do deck;
- um processador futuro pode agregar essas informacoes por `snapshot_id`.

## Deduplicacao

Cartas sao deduplicadas por `oracle_uid`.

Decks nao sao deduplicados apenas por `deck_id`, porque o mesmo deck pode mudar com o tempo. O identificador de snapshot inclui `fetched_at`.

Quando o processamento e rodado sem `--overwrite`, snapshots ja processados sao pulados para evitar duplicacao acidental.

## Manifests e auditoria

Foram criados manifests para tornar execucoes auditaveis:

- `fetch_manifest.jsonl`
  - parametros de coleta;
  - paginas buscadas;
  - payloads tentados;
  - decks validos salvos;
  - candidatos rejeitados;
  - razoes agregadas de rejeicao.

- `processing_manifest.jsonl`
  - raws lidos;
  - decks aceitos;
  - decks rejeitados;
  - cartas novas escritas;
  - rows deck-carta escritas.

Esses manifests ajudam a verificar se mudancas de regra alteraram muito a amostra.

## Testes implementados

Os testes ficam em `tests/test_archidekt_pipeline.py` e usam mocks, sem rede.

Eles cobrem os pontos que mais afetam a integridade da base:

- fetcher salva apenas decks validos;
- `--max-decks` conta decks validos salvos;
- `--resume` evita refetch de deck ja salvo;
- multiplos comandantes;
- categoria premier renomeada;
- exclusao de zonas fora do mainboard;
- manutencao de `Tokens` como categoria estrategica;
- rejeicao por legalidade;
- rejeicao por singleton;
- rejeicao por identidade de cor;
- deduplicacao de cartas e snapshots.

## Estado atual e proximos passos

Estado atual:

- coleta Archidekt implementada;
- validacao pragmatica implementada;
- armazenamento JSONL implementado;
- projeto convertido para `uv`;
- testes unitarios implementados.

Proximos passos naturais:

- criar processador de features para Bag of Cards;
- criar processador de Deck Features conforme secoes 10 e 11 do backbone;
- integrar a calculadora externa para gerar `y2`;
- construir EDA inicial sobre os JSONL processados.
