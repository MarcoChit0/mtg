# Report da Fase C — Pré-processamento

*Gerado automaticamente em `2026-05-21T13:56:43.572757+00:00`.*

## Objetivo

Congelar a base modelável (`y1, y2 ∈ {2,3,4}`) e registrar as transformações sem vazamento aplicadas pelos modelos das Fases D e E. O alvo único é `y1` (`archidekt_edh_bracket`); `y2` é preservado para comparação descritiva (Fase G), nunca como feature.

## Entrada e saída

| Item | Valor |
|---|---|
| Origem | `data/processed/archidekt/deck_features.jsonl` |
| Snapshot ids modeláveis | `data/processed/archidekt/modeling_snapshot_ids.json` |
| Decks excluídos (audit) | `data/processed/archidekt/modeling_excluded.jsonl` |
| Manifesto JSON | `data/processed/archidekt/modeling_dataset_manifest.json` |

## C.1 Filtro da base modelável

Mantém apenas decks com `y1 ∈ {2,3,4}` e `y2 ∈ {2,3,4}`. Os excluídos não são removidos do snapshot original — ficam preservados em `modeling_excluded.jsonl` para análise qualitativa (Fase B) e auditoria.

| Métrica | Valor |
|---|---:|
| Total de decks no snapshot | 12,950 |
| Decks incluídos | 12,135 |
| Decks excluídos | 815 |

### Motivos de exclusão

| Motivo | Quantidade |
|---|---:|
| `y2_out_of_range:5` | 422 |
| `y2_out_of_range:1` | 393 |

## C.2 Deck Features

Aplicado fold a fold pelos modelos da Fase D/E (fit apenas no treino do fold), via `scripts/preprocessing.py::DeckFeaturePreprocessor`:

- inferência das colunas numéricas permitidas, excluindo `y1`, `y2`, `delta`, `abs_delta`, `edhpowerlevel`, `edhpowerlevel_bracket` e metadados;
- imputação por mediana do treino para colunas `edhrec_rank_*` e `salt_*`;
- winsorização de `price_total` no p99 do treino;
- remoção de colunas com variância zero no treino;
- `StandardScaler` opcional (ligado para `logistic_regression`, `linear_svc` e `knn`; desligado para árvores, ensembles e Naive Bayes).

## C.3 Bag of Cards

Aplicado fold a fold pelos modelos da Fase D/E, via `scripts/preprocessing.py::BagOfCardsPreprocessor`:

- contagem por carta usando somente o treino do fold (sem vazamento de cartas de teste);
- pruning por `bc_min_df` (valor decidido na Fase D entre `{5, 10, 20}`);
- matriz `scipy.sparse.csr_matrix`;
- variante `use_tfidf` disponível mas **desligada** na Fase D; pode ser ativada como hiperparâmetro em fases posteriores para algoritmos que se beneficiam de IDF (ex.: `LinearSVC`). Permanece incompatível com `MultinomialNB`.

## C.4 Antivazamento

- Toda transformação faz `fit` apenas no treino do fold (nunca no teste).
- `y2`, `delta`, `abs_delta` e todos os campos `edhpowerlevel.*` (score, power_level, etc.) **nunca** entram em `X` — bloqueio explícito em `is_leakage_column`.
- `y1` é o único target; não há modelo previsto para `y2`.
- Os mesmos folds são usados para todos os algoritmos em cada repeat (ver `experiments/folds.json` gerado pela Fase E).

## Saídas geradas

- `snapshot_ids`: `data/processed/archidekt/modeling_snapshot_ids.json`
- `excluded`: `data/processed/archidekt/modeling_excluded.jsonl`
- `manifest`: `data/processed/archidekt/modeling_dataset_manifest.json`

## Próximo passo

Executar `uv run run-mtg-pipeline spot-checking` para a Fase D — o filtro acima alimenta o seletor top-5 por representação que define o conjunto da Fase E.
