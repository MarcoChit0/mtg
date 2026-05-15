# Plano de Ação — Modelagem da Divergência entre Brackets de Commander

Plano sequencial para concluir o projeto descrito em [backbone.md](backbone.md), atendendo às exigências do [enunciado.pdf](enunciado.pdf). Cada fase tem **objetivo**, **saídas** e **decisões firmadas**.

**Pergunta central**: em que medida `y1` (Archidekt) diverge de `y2` (EDHPowerLevel), e quais características do deck explicam essa divergência?

## 0. Estado atual

| Item | Valor |
|---|---|
| Decks Archidekt (y1 ∈ {2,3,4}, ≥1000 views, 100 cartas) | 12.950 |
| Decks com y2 | 12.950 (todos rotulados após bugfix de scraper em 2026-05-15) |
| Distribuição y2 | 1: 393 · 2: 1.911 · 3: 6.059 · 4: 4.165 · 5: 422 |
| Base modelável (y1 e y2 ∈ {2,3,4}) | ~12.135 |
| `deck_features.jsonl` (114 features) | ✓ |
| `bag_of_cards.jsonl` (sparse) | ✓ |

Os 815 decks com y2 ∈ {1, 5} ficam fora do treino mas são preservados para análise qualitativa (Fase B).

## Fase A — Sanity check

Amostrar 30 decks (10 por bracket y1, seed fixa) e validar:

- **A.1 Scrapper**: re-fetch dos 30 decks pela API do Archidekt. Se `updatedAt` live > `fetched_at` do snapshot, marcar como "modificado após scrap" e pular. Nos restantes, conferir `edhBracket`, comandantes, cores e tamanho do mainboard contra o salvo.
- **A.2 Calculadora**: `uv run validate-edhpowerlevel-labels --sample-size 30 --workers 4` e comparar `commander_bracket` contra o salvo.
- **A.3 Features**: re-rodar `build_deck_features` sobre os registros salvos e diffar todas as 114 features contra `deck_features.jsonl`. Diff deve ser zero (mesmo input + código → mesmo output). Adicional: spot-check manual de `unique_card_count`, `deck_color_count`, `land_count`, contagens por tipo, `game_changer_count`, buckets de curva em 3-5 decks contra a página.

A.1 e A.3 são automatizados em `scripts/sanity_check_phase_a.py` (`uv run sanity-check-phase-a --per-bracket 10`). Saídas:
- `data/processed/archidekt/sanity_check_phase_a.json`
- `documents/sample_reports/sanity_check_phase_a.md`

**Critério de passagem**: A.2 com 100% match em `commander_bracket`; A.3 com diff zero contra o salvo; A.1 sem mismatches estruturais nos decks não-modificados (decks pulados por edição posterior são aceitáveis).

## Fase B — EDA + análise direta da divergência

Independente de modelos. Já produz resultado científico (backbone §13.1, §14).

### B.1 EDA
Distribuições de y1, y2, cores, curva, lands, preço (log), salt, EDHREC rank. Faltantes, outliers, balanceamento de classes, correlação entre features.

### B.2 Divergência
```text
delta     = y2 - y1
abs_delta = |y2 - y1|
```
Calcular: agreement exato, agreement ±1, distribuição de Δ, matriz y1×y2, proporções `y2 > y1` / `y2 < y1`, `|Δ|` médio e mediano. Cortar por comandante, cor, presença de game changers/combos, preço.

Subseção dedicada aos decks com y2 ∈ {1, 5}.

**Saídas**: `documents/eda_report.md`, `documents/divergence_report.md`, figuras em `documents/figures/`.

## Fase C — Pré-processamento

### C.1 Filtros prévios
Manter y1 e y2 ∈ {2,3,4}. Descartados salvos em `data/processed/archidekt/modeling_excluded.jsonl`.

### C.2 Deck Features
- Imputação: mediana do treino para `edhrec_rank_*` e `salt_*`.
- Winsorização de `price_total` no p99 do treino.
- `StandardScaler` para SVM/lineares; opcional para árvores.
- Remover features de variância zero no treino.

### C.3 Bag of Cards
- Matriz esparsa `(n_decks, n_cards)` com quantidade.
- Pruning: remover cartas com presença < `min_df` no treino. Valor decidido no spot-check.
- TF-IDF como variante apenas para SVM (não para NB multinomial).

### C.4 Antivazamento
- Toda transformação fit somente no treino do fold.
- `y1` não entra ao prever `y2`, e vice-versa.
- `delta`, `abs_delta` nunca em X.
- Campos `edhpowerlevel.*` (score, power_level, etc.) não viram features de y1.

## Fase D — Spot-checking

### D.1 Algoritmos
| Algoritmo | Viés | Classe sklearn |
|---|---|---|
| Decision Tree | árvore | `DecisionTreeClassifier` |
| Random Forest | bagging | `RandomForestClassifier` |
| Gradient Boosting | boosting | `GradientBoostingClassifier` / `HistGradientBoostingClassifier` |
| Naive Bayes | probabilístico | `MultinomialNB` (BC) / `GaussianNB` (DF) |
| SVM | margem + linear | `LinearSVC` |

### D.2 Procedimento
Hold-out 80/20 estratificado por (label, fs). Defaults. Reportar macro-F1, accuracy, tempo. Fixar `min_df` do BC nessa fase (testar 5, 10, 20).

**Saída**: `documents/spot_check_results.md`.

## Fase E — Nested CV

### E.1 Esquema
```text
outer:  StratifiedKFold(n_splits=5, shuffle=True, random_state=r)
        r ∈ {1, 2, 3}            # 15 outer evaluations
inner:  StratifiedKFold(n_splits=3, shuffle=True, random_state=r+100)
```

Métrica de seleção: **macro-F1**. Métricas reportadas: macro-F1, accuracy, precision_macro, recall_macro, confusion matrix.

Folds idênticos para todos os algoritmos em cada (label, fs, repeat). Seeds em `experiments/seeds.json`.

### E.2 Grids
| Algoritmo | Grid |
|---|---|
| DT | `max_depth ∈ {None, 8, 16, 32}`, `min_samples_leaf ∈ {1, 5, 20}` |
| RF | `n_estimators ∈ {200, 500}`, `max_features ∈ {sqrt, log2}`, `max_depth ∈ {None, 20}` |
| GB | `n_estimators ∈ {100, 300}`, `learning_rate ∈ {0.05, 0.1}`, `max_depth ∈ {3, 5}` |
| NB | `alpha ∈ {0.01, 0.1, 1.0}` (Multinomial) |
| LinearSVC | `C ∈ {0.01, 0.1, 1, 10}`, `class_weight ∈ {None, balanced}` |

`GridSearchCV` no inner; trocar para `RandomizedSearchCV` se inviável.

### E.3 GroupKFold por comandante (análise auxiliar)
Uma rodada extra com `GroupKFold(n_splits=5)` por `commander_signature`, sem repeat. Reportar gap macro-F1 (Stratified − Group) em `documents/grouped_cv_report.md`.

### E.4 Testes estatísticos
- Múltiplos algoritmos: Friedman + Nemenyi sobre os 15 outer scores.
- Pareado: Wilcoxon signed-rank por fold.

**Saídas**: `experiments/<label>_<fs>_<algo>/{best_hyperparams_per_fold.json, predictions_per_fold.jsonl, metrics_per_fold.json}`, `documents/statistical_tests.md`.

## Fase F — Melhor modelo por (label, fs)

Ranquear por macro-F1 médio nos outer folds. Desvio padrão como desempate. Decisão registrada manualmente em `documents/best_models_per_combo.md`.

Comparações: BC vs DF para cada label; mesmo algoritmo entre labels.

## Fase G — Transferência cross-label

Para cada fs ∈ {BC, DF}:
- `M_fs_y1` aplicado a y2 (macro-F1 e confusion).
- `M_fs_y2` aplicado a y1.

Subset analysis: performance no conjunto `y1 == y2` vs `y1 ≠ y2` (o subset divergente é o interessante).

**Saída**: `documents/cross_label_transfer.md`.

## Fase H — Stacking (4 experimentos)

Base learners = predições out-of-fold da Fase E. Meta-learner: `LogisticRegression`. Mesmos outer folds da Fase E.

| Exp | Base learners | Meta-target | Comparado contra |
|---|---|---|---|
| H.1 | M_BC_y1, M_DF_y1, M_BC_y2, M_DF_y2 | y1 | H.3 |
| H.2 | M_BC_y1, M_DF_y1, M_BC_y2, M_DF_y2 | y2 | H.4 |
| H.3 | M_BC_y1, M_DF_y1 | y1 | controle (sem cross-label) |
| H.4 | M_BC_y2, M_DF_y2 | y2 | controle |

H.1 > H.3 ⇒ info de y2 ajuda a prever y1. Idem para H.2 vs H.4.

**Saída**: `documents/stacking_results.md`.

## Fase I — Interpretabilidade

**Modelo principal**: melhor (label, fs) por macro-F1 (prováv. DF baseado em árvore — mais interpretável).

Análise profunda:
- Feature importance (SHAP para árvores, coeficientes para lineares, permutation como fallback).
- Top 10-15 features com direção do efeito.
- Features associadas a erros e a `delta > 0` vs `delta < 0`.

Análises secundárias (1 parágrafo cada): outros 3 (label, fs); para BC, top-20 cartas por classe.

**Saída**: `documents/interpretability.md`.

## Fase J — Out-of-distribution (opcional)

Coletar decks com 500 ≤ views < 1000. Aplicar melhores modelos **sem retreinar**. Comparar macro-F1 dentro vs fora.

**Saída**: `documents/ood_report.md`.

## Fase K — Artigo

Template Moodle (coluna única, ≤20 pág.):
1. Introdução · 2. Trabalhos relacionados · 3. Métodos (coleta, escopo, BC/DF, nested CV, reprodutibilidade) · 4. Resultados (B, E, G, H, I, J) · 5. Discussão · 6. Conclusão · 7. Referências · 8. Apêndices.

Se usar IA generativa: `documents/ai_usage.md` com prompts e limitações.

## Apêndice 1 — Reprodutibilidade

```text
experiments/
├── seeds.json
├── folds/{outer_r{1,2,3}.json, inner_r{1,2,3}.json, group_kfold.json}
├── <label>_<fs>_<algo>/{best_hyperparams_per_fold.json, predictions_per_fold.jsonl, metrics_per_fold.json}
├── stacking/{h{1,2,3,4}_predictions.jsonl, h*_metrics.json}
└── manifest.json   # SHA-256 dos JSONL de entrada + versões
```

Ambiente já é reprodutível via `pyproject.toml` + `uv.lock`.

## Apêndice 2 — Mapeamento ao enunciado

| Exigência | Fase |
|---|---|
| EDA | B |
| Pré-processamento | C |
| ≥5 algoritmos diversos | D, E |
| Spot-checking | D |
| Otimização sem leakage | E |
| Folds idênticos entre algoritmos | E.1 |
| Seeds | E + Apêndice 1 |
| Média ± desvio nos outer folds | E, F |
| Interpretação de um modelo | I |
| Artigo científico | K |
| Reprodutibilidade | Apêndice 1 |

## Apêndice 3 — Cronograma

Prazos: código + artigo **2026-05-28 23:59** · peer review **2026-06-02 a 2026-06-09** · apresentação **2026-06-16**.

Hoje **2026-05-14** — 14 dias.

| Fase | Dias |
|---|---|
| A | 0,5 |
| B | 1,5 |
| C | 1 |
| D | 1 |
| E | 3-4 |
| F | 0,5 |
| G | 0,5 |
| H | 1 |
| I | 1,5 |
| J (opcional) | 0,5 |
| K (artigo) | 3 |

Margem ~1 dia. Se atrasar: J e E.3 são as primeiras candidatas a virarem "trabalho futuro".
