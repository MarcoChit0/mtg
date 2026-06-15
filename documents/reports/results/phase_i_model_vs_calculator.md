# Fase I — Comparação das Predições dos Modelos com a Calculadora (y2)

> Análise **descritiva** — sem retreino, sem novos folds. Os modelos foram treinados para prever `y1` (bracket comunitário Archidekt). As predições OOF `ŷ1` são comparadas aqui contra `y2` (EDHPowerLevel calculator) para medir o grau de alinhamento entre percepção comunitária e avaliação automática. `y2` nunca foi alvo de treinamento (backbone §5).

Base: 36405 entradas OOF (12.135 decks × 3 repeats). `y2` é estável por deck (0 inconsistências entre folds).

**Importante**: a Fase I não treina nem retreina modelos. Ela apenas lê as predições out-of-fold já salvas pela Fase E (`experiments/<modelo>/predictions_per_fold.jsonl`) e pela Fase G (`experiments/voting/<ensemble>/predictions_per_fold.jsonl`) e compara `ŷ1` com `y2`.

## 1. Referência direta: y1 real do Archidekt vs y2

Esta é a comparação sem modelo: `y1` é o bracket real extraído do Archidekt e `y2` é o bracket calculado pela EDHPowerLevel. Ela é calculada na mesma base OOF usada pelos modelos, para manter a comparação direta com `ŷ1`.

| Comparação | n | Concord. exata | Concord. ±1 | Delta abs. médio | Macro-F1 vs y2 |
|---|---:|---:|---:|---:|---:|
| `y1` real vs `y2` | 36405 | 60.9% | 97.7% | 0.414 | 0.5843 |

**`y1` real vs `y2`** — linhas = y1 real do Archidekt, colunas = y2 (calculadora)

| y1 \ y2 | 2 | 3 | 4 |
|---|---|---|---|
| **2** | 3042 | 3459 | 462 | *(n=6963)*
| **3** | 2307 | 11727 | 4617 | *(n=18651)*
| **4** | 384 | 2991 | 7416 | *(n=10791)*

## 2. Concordância de ŷ1 com y2 — todos os modelos

Aqui `ŷ1` é o label predito por cada modelo treinado em `y1`. A tabela usa exatamente as mesmas métricas da seção anterior, agora trocando `y1` real por `ŷ1`.

| Modelo | Tipo | Repr. | Macro-F1 (y1) | Concord. exata ŷ1=y2 | Concord. ±1 | Delta abs. médio | Macro-F1 vs y2 |
|---|---|---|---:|---:|---:|---:|---:|
| `df_random_forest` | individual | DF | 0.6733 | 69.3% | 99.5% | 0.312 | 0.6674 |
| `df_logistic_regression` | individual | DF | 0.6707 | 68.8% | 99.3% | 0.319 | 0.6665 |
| `voting_top7` | ensemble | BC+DF | 0.6936 | 68.4% | 99.0% | 0.326 | 0.6707 |
| `voting_top5` | ensemble | DF | 0.6932 | 68.2% | 99.1% | 0.327 | 0.6672 |
| `bc_random_forest` | individual | BC | 0.6326 | 66.9% | 98.8% | 0.343 | 0.6540 |
| `voting_top3` | ensemble | DF | 0.6941 | 66.7% | 98.7% | 0.346 | 0.6499 |
| `df_linear_svc` | individual | DF | 0.6557 | 65.0% | 98.6% | 0.365 | 0.6466 |
| `df_decision_tree` | individual | DF | 0.6727 | 64.8% | 97.8% | 0.374 | 0.6291 |
| `df_gradient_boosting` | individual | DF | 0.6908 | 64.0% | 98.1% | 0.379 | 0.6323 |
| `bc_gradient_boosting` | individual | BC | 0.6433 | 60.3% | 97.3% | 0.424 | 0.5984 |
| `bc_linear_svc` | individual | BC | 0.6147 | 59.2% | 97.8% | 0.430 | 0.5753 |
| `bc_logistic_regression` | individual | BC | 0.6236 | 58.6% | 96.9% | 0.445 | 0.5863 |
| `bc_naive_bayes` | individual | BC | 0.5535 | 55.5% | 97.1% | 0.474 | 0.5462 |
| `df_naive_bayes` | individual | DF | 0.5905 | 54.5% | 97.3% | 0.481 | 0.5490 |
| `bc_decision_tree` | individual | BC | 0.5475 | 54.2% | 96.6% | 0.492 | 0.5328 |

## 3. Contingência triádica: y1 × y2 × ŷ1

A análise triádica localiza a discordância diretamente. Para o melhor preditor comunitário individual (`df_gradient_boosting`), cada célula `y1 != y2` mostra se a predição segue a comunidade (`y1`), segue a calculadora (`y2`) ou escolhe outro bracket.

| y1 | y2 | n | Segue y1 | Segue y2 | Outro |
|---:|---:|---:|---:|---:|---:|
| 2 | 3 | 3459 | 68.5% | 29.3% | 2.3% |
| 2 | 4 | 462 | 44.6% | 9.3% | 46.1% |
| 3 | 2 | 2307 | 25.9% | 70.6% | 3.5% |
| 3 | 4 | 4617 | 75.5% | 18.8% | 5.6% |
| 4 | 2 | 384 | 18.8% | 40.1% | 41.1% |
| 4 | 3 | 2991 | 30.8% | 61.6% | 7.6% |
| **Todos** | **discordantes** | **14220** | **53.8%** | **39.0%** | **7.2%** |

Nas células concordantes (`y1 == y2`), `df_gradient_boosting` prediz o rótulo compartilhado em 80.0% das linhas OOF.


## 4. Análise por subconjunto: decks concordantes vs discordantes

> **Concordante**: decks onde `y1 == y2` — comunidade e calculadora atribuem o mesmo bracket.
> **Discordante**: decks onde `y1 != y2` — as fontes divergem.
> Métricas: concordância exata entre ŷ1 e y2 dentro de cada subconjunto. A tabela está ordenada pela concordância no subconjunto discordante, que é onde a divergência entre as fontes aparece.

| Modelo | Tipo | Concord. exata (todos) | Concord. exata (y1=y2, n≈7395×3) | Concord. exata (y1≠y2, n≈4740×3) |
|---|---|---:|---:|---:|
| `bc_random_forest` | individual | 66.9% | 78.4% | 49.0% |
| `df_logistic_regression` | individual | 68.8% | 83.3% | 46.3% |
| `df_random_forest` | individual | 69.3% | 84.3% | 45.8% |
| `df_linear_svc` | individual | 65.0% | 77.6% | 45.3% |
| `voting_top7` | ensemble | 68.4% | 83.9% | 44.1% |
| `voting_top5` | ensemble | 68.2% | 84.0% | 43.6% |
| `bc_naive_bayes` | individual | 55.5% | 63.2% | 43.3% |
| `bc_decision_tree` | individual | 54.2% | 61.3% | 43.1% |
| `voting_top3` | ensemble | 66.7% | 82.7% | 41.5% |
| `df_decision_tree` | individual | 64.8% | 79.7% | 41.5% |
| `bc_linear_svc` | individual | 59.2% | 70.6% | 41.3% |
| `bc_logistic_regression` | individual | 58.6% | 69.8% | 41.1% |
| `bc_gradient_boosting` | individual | 60.3% | 72.8% | 40.8% |
| `df_naive_bayes` | individual | 54.5% | 64.4% | 39.1% |
| `df_gradient_boosting` | individual | 64.0% | 80.0% | 39.0% |

## 5. Destaques globais

Considerando todos os modelos e ensembles juntos, seleciono apenas três casos: maior concordância, menor concordância e melhor preditor comunitário individual. Isso mantém a seção focada nos extremos realmente informativos, independente de a origem ser `BC`, `DF` ou `BC+DF`.

| Caso | Modelo | Tipo | Repr. | Concord. exata | Macro-F1 (y1) | Macro-F1 vs y2 | Justificativa |
|---|---|---|---|---:|---:|---:|---|
| maior concordância | `df_random_forest` | individual | DF | 69.3% | 0.6733 | 0.6674 | maior concordância exata com y2 entre todos os modelos (69.3%) |
| menor concordância | `bc_decision_tree` | individual | BC | 54.2% | 0.5475 | 0.5328 | menor concordância exata com y2 entre todos os modelos (54.2%) |
| melhor preditor comunitário individual | `df_gradient_boosting` | individual | DF | 64.0% | 0.6908 | 0.6323 | maior macro-F1 contra y1 entre os modelos individuais (0.6908) |

## 6. Matrizes de confusão ŷ1 × y2 — destaques globais

> Linhas = ŷ1 (o que o modelo previu para bracket comunitário), colunas = y2 (o que a calculadora atribuiu). A diagonal principal = concordância exata ŷ1 = y2.

As matrizes abaixo somam 36405 entradas porque são calculadas sobre predições OOF: 12.135 decks × 3 repeats. Assim, cada deck pode contribuir até três vezes, uma por repeat.

### `df_random_forest` (maior concordância)

Justificativa: maior concordância exata com y2 entre todos os modelos (69.3%).

**df_random_forest** — linhas = ŷ1 (previsto pelo modelo), colunas = y2 (calculadora)

| ŷ1 \ y2 | 2 | 3 | 4 |
|---|---|---|---|
| **2** | 3518 | 2375 | 102 | *(n=5995)*
| **3** | 2142 | 14829 | 5523 | *(n=22494)*
| **4** | 73 | 973 | 6870 | *(n=7916)*

### `bc_decision_tree` (menor concordância)

Justificativa: menor concordância exata com y2 entre todos os modelos (54.2%).

**bc_decision_tree** — linhas = ŷ1 (previsto pelo modelo), colunas = y2 (calculadora)

| ŷ1 \ y2 | 2 | 3 | 4 |
|---|---|---|---|
| **2** | 3516 | 4488 | 820 | *(n=8824)*
| **3** | 1811 | 9511 | 4976 | *(n=16298)*
| **4** | 406 | 4178 | 6699 | *(n=11283)*

### `df_gradient_boosting` (melhor preditor comunitário individual)

Justificativa: maior macro-F1 contra y1 entre os modelos individuais (0.6908).

**df_gradient_boosting** — linhas = ŷ1 (previsto pelo modelo), colunas = y2 (calculadora)

| ŷ1 \ y2 | 2 | 3 | 4 |
|---|---|---|---|
| **2** | 4511 | 4794 | 524 | *(n=9829)*
| **3** | 1061 | 11483 | 4668 | *(n=17212)*
| **4** | 161 | 1900 | 7303 | *(n=9364)*

## 7. Discussão comparativa

A leitura global destaca os extremos relevantes. Maior concordância identifica o modelo mais próximo da calculadora; menor concordância identifica o mais distante; a contingência triádica mostra, para o melhor preditor comunitário individual, para qual fonte as predições caminham quando `y1` e `y2` discordam.

## 8. Comparação compacta: `y1` vs `y2` e melhor `ŷ1` vs `y2`

| Comparação | Concord. exata | Concord. ±1 | Delta abs. médio | Macro-F1 vs y2 |
|---|---:|---:|---:|---:|
| `y1` real vs `y2` | 60.9% | 97.7% | 0.414 | 0.5843 |
| melhor `ŷ1` vs `y2` (`df_random_forest`) | 69.3% | 99.5% | 0.312 | 0.6674 |

## 9. Artefatos

- `documents/reports/results/phase_i_model_vs_calculator.md` — este relatório
- Todos os dados lidos de `experiments/*/predictions_per_fold.jsonl` (campo `y2`)
- Nenhum novo artefato gerado em `experiments/` — análise puramente descritiva
