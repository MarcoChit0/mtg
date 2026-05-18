# Report da Fase C — Pré-processamento

## Objetivo

A Fase C teve como objetivo congelar a base modelável e implementar transformações sem vazamento para as duas representações que serão usadas nos modelos:

- Deck Features (`DF`): features agregadas por deck.
- Bag of Cards (`BC`): matriz esparsa carta × deck.

O alvo único de treino é `y1` (`archidekt_edh_bracket`). `y2` é preservado apenas para análise descritiva e comparação posterior, nunca como feature.

## O que foi feito

1. Implementado o filtro da base modelável em `scripts/phase_c_filter_dataset.py`.
2. Implementados transformadores sklearn-compatible em `scripts/preprocessing.py`.
3. Gerados os artefatos:
   - `data/processed/archidekt/modeling_snapshot_ids.json`
   - `data/processed/archidekt/modeling_excluded.jsonl`
   - `data/processed/archidekt/modeling_dataset_manifest.json`
4. Testada a materialização real das duas representações com os dados atuais.
5. Validado que colunas de vazamento não entram em `X`.

## Como foi feito

### C.1 Filtro da base modelável

O filtro mantém apenas decks com `y1` e `y2` em `{2,3,4}`. O resultado registrado em `modeling_dataset_manifest.json` foi:

| Métrica | Valor |
|---|---:|
| Total de decks no snapshot | 12.950 |
| Decks incluídos na modelagem | 12.135 |
| Decks excluídos | 815 |
| Excluídos por `y2=1` | 393 |
| Excluídos por `y2=5` | 422 |

Os excluídos não foram apagados; eles ficam em `modeling_excluded.jsonl` para análise qualitativa e discussão.

### C.2 Deck Features

`DeckFeaturePreprocessor` executa no `fit`:

- inferência das colunas numéricas permitidas;
- remoção de `y1`, `y2`, `delta`, `abs_delta`, `edhpowerlevel`, `edhpowerlevel_bracket` e metadados;
- imputação por mediana do treino para `edhrec_rank_*` e `salt_*`;
- winsorização de `price_total` no p99 do treino;
- remoção de variância zero no treino;
- `StandardScaler` opcional para modelos lineares, SVM e KNN.

Na checagem real, a representação DF materializou:

| Item | Valor |
|---|---:|
| Linhas | 12.135 |
| Colunas após remoção de variância zero | 102 |
| Colunas de vazamento detectadas | 0 |

### C.3 Bag of Cards

`BagOfCardsPreprocessor` executa no `fit`:

- contagem de presença por carta apenas no treino;
- pruning por `bc_min_df` no experimento de BC (internamente, o transformador usa o nome sklearn-convencional `min_df`);
- construção de matriz CSR esparsa;
- opção `use_tfidf`, para modelos que podem se beneficiar de IDF em fases posteriores. Na Fase D, TF-IDF fica desligado.

Na checagem real de Fase C com `bc_min_df=10`, a representação BC materializou:

| Item | Valor |
|---|---:|
| Linhas | 12.135 |
| Colunas/cartas após pruning | 11.114 |

## Problemas encontrados e correções

| Problema | Impacto | Correção |
|---|---|---|
| `scripts/preprocessing.py` estava aberto no IDE, mas não existia no repositório | A Fase C não era reprodutível em código | Criado `scripts/preprocessing.py` com transformadores reutilizáveis |
| `pyproject.toml` já apontava para `phase-c-filter-dataset`, mas o script não existia | O console script quebraria em ambiente limpo | Criado `scripts/phase_c_filter_dataset.py` |
| Risco de vazamento de `y2` ou campos da calculadora | Resultados de modelagem ficariam inválidos | Bloqueio explícito de labels, deltas e campos `edhpowerlevel*` na inferência de colunas |
| Necessidade de aplicar mediana/p99/vocabulário somente no treino | Vazamento fold→treino em CV | Transformadores seguem API `fit/transform`; toda estatística é aprendida no `fit` |
| Reprodutibilidade a partir do Google Drive | Rodar em diretórios temporários precisava respeitar paths configuráveis | `run-mtg-pipeline` restaura o snapshot processado e roda C até o manifest sem reconsultar `y2` |

## Testes e validação

Testes adicionados em `tests/test_phase_c_preprocessing.py` cobrem:

- filtro de incluídos/excluídos;
- geração dos audit rows de exclusão;
- remoção de colunas de vazamento;
- imputação por mediana aprendida no treino;
- winsorização por p99 do treino;
- scaler opcional;
- pruning `bc_min_df` da Bag of Cards;
- variante TF-IDF.

Comando validado:

```bash
uv run python -m unittest discover -s tests -v
```

Resultado da última validação: 31 testes passaram.

## Estado final da Fase C

A Fase C está concluída. A base modelável está congelada em 12.135 decks, as exclusões estão auditadas e os transformadores estão prontos para Fase D e Fase E sem vazamento.
