# Fase I — Comparação das Predições dos Modelos com a Calculadora (y2)

> Análise **descritiva** — sem retreino, sem novos folds. Os modelos foram treinados para prever `y1` (bracket comunitário Archidekt). As predições OOF `ŷ1` são comparadas aqui contra `y2` (EDHPowerLevel calculator) para medir o grau de alinhamento entre percepção comunitária e avaliação automática. `y2` nunca foi alvo de treinamento (backbone §5).

Base: 36405 entradas OOF (12.135 decks × 3 repeats). `y2` é estável por deck (0 inconsistências entre folds).

## 1. Concordância com y2 — todos os modelos

| Modelo | Tipo | Repr. | Macro-F1 (y1) | Concord. exata ŷ1=y2 | Concord. ±1 | |Δ| médio | Macro-F1 vs y2 |
|---|---|---|---:|---:|---:|---:|---:|
| `df_random_forest` | individual | DF | 0.6733 | 69.3% | 99.5% | 0.312 | 0.6674 |
| `df_logistic_regression` | individual | DF | 0.6707 | 68.8% | 99.3% | 0.319 | 0.6665 |
| `voting_top5_DF` | ensemble | DF | 0.6939 | 68.1% | 99.0% | 0.328 | 0.6659 |
| `voting_all` | ensemble | BC+DF | 0.6902 | 67.0% | 98.7% | 0.343 | 0.6604 |
| `bc_random_forest` | individual | BC | 0.6326 | 66.9% | 98.8% | 0.343 | 0.6540 |
| `voting_top3_BC_DF` | ensemble | BC+DF | 0.6944 | 66.7% | 98.5% | 0.348 | 0.6539 |
| `voting_top3_DF` | ensemble | DF | 0.6941 | 66.7% | 98.7% | 0.346 | 0.6499 |
| `df_decision_tree` | individual | DF | 0.6727 | 64.8% | 97.8% | 0.374 | 0.6291 |
| `df_linear_svc` | individual | DF | 0.6566 | 64.3% | 98.5% | 0.373 | 0.6393 |
| `df_gradient_boosting` | individual | DF | 0.6908 | 64.0% | 98.1% | 0.379 | 0.6323 |
| `voting_top5_BC` | ensemble | BC | 0.6418 | 62.6% | 97.9% | 0.395 | 0.6183 |
| `voting_top3_BC` | ensemble | BC | 0.6495 | 62.3% | 97.7% | 0.401 | 0.6184 |
| `bc_gradient_boosting` | individual | BC | 0.6433 | 60.3% | 97.3% | 0.424 | 0.5984 |
| `bc_logistic_regression` | individual | BC | 0.6236 | 58.6% | 96.9% | 0.445 | 0.5863 |
| `bc_linear_svc` | individual | BC | 0.5927 | 58.1% | 97.9% | 0.441 | 0.5588 |
| `bc_naive_bayes` | individual | BC | 0.5535 | 55.5% | 97.1% | 0.474 | 0.5462 |
| `df_naive_bayes` | individual | DF | 0.5905 | 54.5% | 97.3% | 0.481 | 0.5490 |
| `bc_decision_tree` | individual | BC | 0.5475 | 54.2% | 96.6% | 0.492 | 0.5328 |

## 2. Gap entre desempenho em y1 e concordância com y2

> Um gap positivo grande significa que o modelo aprendeu bem `y1` mas diverge da calculadora — aprendeu particularidades da percepção comunitária. Gap negativo ou próximo de zero indica alinhamento estrutural entre os dois rótulos.

| Modelo | Tipo | Macro-F1 (y1) | Concord. exata (y2) | Gap (F1 − concord.) |
|---|---|---:|---:|---:|
| `df_gradient_boosting` | individual | 0.6908 | 64.0% | +0.0508 |
| `df_naive_bayes` | individual | 0.5905 | 54.5% | +0.0450 |
| `bc_gradient_boosting` | individual | 0.6433 | 60.3% | +0.0402 |
| `bc_logistic_regression` | individual | 0.6236 | 58.6% | +0.0380 |
| `voting_top3_BC_DF` | ensemble | 0.6944 | 66.7% | +0.0277 |
| `voting_top3_DF` | ensemble | 0.6941 | 66.7% | +0.0276 |
| `voting_top3_BC` | ensemble | 0.6495 | 62.3% | +0.0270 |
| `df_decision_tree` | individual | 0.6727 | 64.8% | +0.0251 |
| `voting_all` | ensemble | 0.6902 | 67.0% | +0.0202 |
| `voting_top5_BC` | ensemble | 0.6418 | 62.6% | +0.0162 |
| `df_linear_svc` | individual | 0.6566 | 64.3% | +0.0139 |
| `voting_top5_DF` | ensemble | 0.6939 | 68.1% | +0.0124 |
| `bc_linear_svc` | individual | 0.5927 | 58.1% | +0.0121 |
| `bc_decision_tree` | individual | 0.5475 | 54.2% | +0.0057 |
| `bc_naive_bayes` | individual | 0.5535 | 55.5% | -0.0010 |
| `df_logistic_regression` | individual | 0.6707 | 68.8% | -0.0177 |
| `df_random_forest` | individual | 0.6733 | 69.3% | -0.0194 |
| `bc_random_forest` | individual | 0.6326 | 66.9% | -0.0367 |

## 3. Análise por subconjunto: decks concordantes vs discordantes

> **Concordante**: decks onde `y1 == y2` — comunidade e calculadora atribuem o mesmo bracket.
> **Discordante**: decks onde `y1 != y2` — as fontes divergem.
> Métricas: concordância exata entre ŷ1 e y2 dentro de cada subconjunto.

| Modelo | Tipo | Concord. exata (todos) | Concord. exata (y1=y2, n≈7395×3) | Concord. exata (y1≠y2, n≈4740×3) |
|---|---|---:|---:|---:|
| `df_random_forest` | individual | 69.3% | 84.3% | 45.8% |
| `df_logistic_regression` | individual | 68.8% | 83.3% | 46.3% |
| `voting_top5_DF` | ensemble | 68.1% | 84.0% | 43.4% |
| `voting_all` | ensemble | 67.0% | 82.4% | 43.0% |
| `bc_random_forest` | individual | 66.9% | 78.4% | 49.0% |
| `voting_top3_BC_DF` | ensemble | 66.7% | 82.6% | 41.8% |
| `voting_top3_DF` | ensemble | 66.7% | 82.7% | 41.5% |
| `df_decision_tree` | individual | 64.8% | 79.7% | 41.5% |
| `df_linear_svc` | individual | 64.3% | 77.1% | 44.2% |
| `df_gradient_boosting` | individual | 64.0% | 80.0% | 39.0% |
| `voting_top5_BC` | ensemble | 62.6% | 74.9% | 43.3% |
| `voting_top3_BC` | ensemble | 62.3% | 74.9% | 42.6% |
| `bc_gradient_boosting` | individual | 60.3% | 72.8% | 40.8% |
| `bc_logistic_regression` | individual | 58.6% | 69.8% | 41.1% |
| `bc_linear_svc` | individual | 58.1% | 68.6% | 41.7% |
| `bc_naive_bayes` | individual | 55.5% | 63.2% | 43.3% |
| `df_naive_bayes` | individual | 54.5% | 64.4% | 39.1% |
| `bc_decision_tree` | individual | 54.2% | 61.3% | 43.1% |

## 4. Matrizes de confusão ŷ1 × y2 — modelos de destaque

> Linhas = ŷ1 (o que o modelo previu para bracket comunitário), colunas = y2 (o que a calculadora atribuiu). A diagonal principal = concordância exata ŷ1 = y2.

### `df_random_forest` (maior concordância com y2)

**df_random_forest** — linhas = ŷ1 (previsto pelo modelo), colunas = y2 (calculadora)

| ŷ1 \ y2 | 2 | 3 | 4 |
|---|---|---|---|
| **2** | 3518 | 2375 | 102 | *(n=5995)*
| **3** | 2142 | 14829 | 5523 | *(n=22494)*
| **4** | 73 | 973 | 6870 | *(n=7916)*

### `bc_decision_tree` (menor concordância com y2)

**bc_decision_tree** — linhas = ŷ1 (previsto pelo modelo), colunas = y2 (calculadora)

| ŷ1 \ y2 | 2 | 3 | 4 |
|---|---|---|---|
| **2** | 3516 | 4488 | 820 | *(n=8824)*
| **3** | 1811 | 9511 | 4976 | *(n=16298)*
| **4** | 406 | 4178 | 6699 | *(n=11283)*

### `df_gradient_boosting` (maior gap F1(y1)−concord.(y2))

**df_gradient_boosting** — linhas = ŷ1 (previsto pelo modelo), colunas = y2 (calculadora)

| ŷ1 \ y2 | 2 | 3 | 4 |
|---|---|---|---|
| **2** | 4511 | 4794 | 524 | *(n=9829)*
| **3** | 1061 | 11483 | 4668 | *(n=17212)*
| **4** | 161 | 1900 | 7303 | *(n=9364)*

## 5. Discussão comparativa

**Maior concordância com y2**: `df_random_forest` (69.3% de concordância exata). Apesar de ter sido treinado exclusivamente em `y1`, este modelo alinha suas predições à calculadora em quase 69.3% dos decks — indicando que os sinais estruturais capturados pelo modelo coincidem parcialmente com os critérios objetivos usados por EDHPowerLevel.

**Menor concordância com y2**: `bc_decision_tree` (54.2% de concordância exata). A baixa concordância sugere que este modelo captou padrões de percepção comunitária mais distantes da lógica da calculadora — possivelmente porque a representação ou o algoritmo enfatiza sinais que o usuário do Archidekt considera, mas que EDHPowerLevel não pondera da mesma forma.

**Maior gap F1(y1) − concordância(y2)**: `df_gradient_boosting` (gap = +0.0508). Um gap positivo indica que o modelo performa bem em prever `y1`, mas essa performance vem de aprender particularidades da percepção comunitária que não se traduzem em alinhamento com a calculadora. Esse tipo de modelo é o mais informativo para entender a divergência entre as duas fontes.

## 6. Referência: concordância direta y1 vs y2 (Fase B)

Para contextualizar os números acima, a Fase B reportou que `y1` e `y2` concordam exatamente em **60,9%** dos decks da base modelável, e dentro de ±1 em **97,7%**. Os modelos treinados em `y1` tendem a produzir `ŷ1` próximos de `y1`, portanto espera-se concordância similar com `y2` — ligeiramente diferente dependendo do viés e representação do algoritmo.

## 7. Artefatos

- `documents/reports/results/phase_i_model_vs_calculator.md` — este relatório
- Todos os dados lidos de `experiments/*/predictions_per_fold.jsonl` (campo `y2`)
- Nenhum novo artefato gerado em `experiments/` — análise puramente descritiva
