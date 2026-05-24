# Fase H — Seleção do Melhor Modelo por Representação

Ranqueamento dos modelos individuais (Fase E) e ensembles de votação (Fase G) por macro-F1 médio nos outer folds. Seleção de `melhor_BC` e `melhor_DF` entre os modelos individuais (backbone §13.8). Desempate por menor desvio padrão.

## 1. Ranking — Modelos individuais

| # | Modelo | Repr. | Algoritmo | Macro-F1 média | Macro-F1 dp | Accuracy média | Folds |
|---|---|---|---|---:|---:|---:|---:|
| 1 | `df_gradient_boosting` ★DF | DF | gradient_boosting | 0.6908 | 0.0093 | 0.6978 | 15/15 |
| 2 | `df_random_forest` | DF | random_forest | 0.6733 | 0.0076 | 0.7034 | 15/15 |
| 3 | `df_decision_tree` | DF | decision_tree | 0.6727 | 0.0100 | 0.6876 | 15/15 |
| 4 | `df_logistic_regression` | DF | logistic_regression | 0.6707 | 0.0110 | 0.6944 | 15/15 |
| 5 | `df_linear_svc` | DF | linear_svc | 0.6566 | 0.0086 | 0.6599 | 15/15 |
| 6 | `bc_gradient_boosting` ★BC | BC | gradient_boosting | 0.6433 | 0.0121 | 0.6442 | 15/15 |
| 7 | `bc_random_forest` | BC | random_forest | 0.6326 | 0.0122 | 0.6534 | 15/15 |
| 8 | `bc_logistic_regression` | BC | logistic_regression | 0.6236 | 0.0096 | 0.6212 | 15/15 |
| 9 | `bc_linear_svc` | BC | linear_svc | 0.5927 | 0.0090 | 0.6131 | 15/15 |
| 10 | `df_naive_bayes` | DF | naive_bayes | 0.5905 | 0.0093 | 0.5874 | 15/15 |
| 11 | `bc_naive_bayes` | BC | naive_bayes | 0.5535 | 0.0090 | 0.5636 | 15/15 |
| 12 | `bc_decision_tree` | BC | decision_tree | 0.5475 | 0.0116 | 0.5540 | 15/15 |

## 2. Comparação BC vs DF por algoritmo

| Algoritmo | BC macro-F1 | BC dp | DF macro-F1 | DF dp | Δ (DF − BC) |
|---|---:|---:|---:|---:|---:|
| decision_tree | 0.5475 | 0.0116 | 0.6727 | 0.0100 | +0.1251 |
| gradient_boosting | 0.6433 | 0.0121 | 0.6908 | 0.0093 | +0.0475 |
| linear_svc | 0.5927 | 0.0090 | 0.6566 | 0.0086 | +0.0640 |
| logistic_regression | 0.6236 | 0.0096 | 0.6707 | 0.0110 | +0.0471 |
| naive_bayes | 0.5535 | 0.0090 | 0.5905 | 0.0093 | +0.0370 |
| random_forest | 0.6326 | 0.0122 | 0.6733 | 0.0076 | +0.0407 |

## 3. Ensembles de votação (Fase G)

| Ensemble | Membros | Folds | Macro-F1 média | Macro-F1 dp |
|---|---|---:|---:|---:|
| `voting_top3_BC_DF` | `bc_gradient_boosting`, `bc_random_forest`, `bc_logistic_regression`, `df_gradient_boosting`, `df_random_forest`, `df_decision_tree` | 15/15 | 0.6944 | 0.0095 |
| `voting_top3_DF` | `df_gradient_boosting`, `df_random_forest`, `df_decision_tree` | 15/15 | 0.6941 | 0.0096 |
| `voting_top5_DF` | `df_gradient_boosting`, `df_random_forest`, `df_decision_tree`, `df_logistic_regression`, `df_linear_svc` | 15/15 | 0.6939 | 0.0080 |
| `voting_all` | `bc_decision_tree`, `bc_gradient_boosting`, `bc_linear_svc`, `bc_logistic_regression`, `bc_naive_bayes`, `bc_random_forest`, `df_decision_tree`, `df_gradient_boosting`, `df_linear_svc`, `df_logistic_regression`, `df_naive_bayes`, `df_random_forest` | 15/15 | 0.6902 | 0.0102 |
| `voting_top3_BC` | `bc_gradient_boosting`, `bc_random_forest`, `bc_logistic_regression` | 15/15 | 0.6495 | 0.0116 |
| `voting_top5_BC` | `bc_gradient_boosting`, `bc_random_forest`, `bc_logistic_regression`, `bc_linear_svc`, `bc_naive_bayes` | 15/15 | 0.6418 | 0.0091 |

### Ganho dos ensembles vs melhor modelo individual

| Ensemble | Melhor individual (referência) | Delta macro-F1 |
|---|---|---:|
| `voting_top3_BC_DF` | melhor individual geral | +0.0036 |
| `voting_top3_DF` | `df_gradient_boosting` | +0.0033 |
| `voting_top5_DF` | `df_gradient_boosting` | +0.0031 |
| `voting_all` | melhor individual geral | -0.0006 |
| `voting_top3_BC` | `bc_gradient_boosting` | +0.0063 |
| `voting_top5_BC` | `bc_gradient_boosting` | -0.0015 |

## 4. Seleção final

### melhor_BC: `bc_gradient_boosting`

- **Algoritmo**: gradient_boosting
- **Representação**: BC
- **Macro-F1 média**: 0.6433 ± 0.0121
- **Accuracy média**: 0.6442
- **Folds**: 15/15
- **Posição no ranking BC**: rank 1
- **Justificativa**: maior macro-F1 médio na representação BC; desempate por desvio padrão não foi necessário.

### melhor_DF: `df_gradient_boosting`

- **Algoritmo**: gradient_boosting
- **Representação**: DF
- **Macro-F1 média**: 0.6908 ± 0.0093
- **Accuracy média**: 0.6978
- **Folds**: 15/15
- **Posição no ranking DF**: rank 1
- **Justificativa**: maior macro-F1 médio na representação DF; desempate por desvio padrão não foi necessário.

## 5. Hiperparâmetros por fold — modelos selecionados

### bc_gradient_boosting

**Configuração mais frequente** (across 15 outer folds):
- `class_weight` = `balanced`
- `learning_rate` = `0.05`
- `max_iter` = `200`
- `max_leaf_nodes` = `31`

| Fold | inner macro-F1 | Parâmetros |
|---|---:|---|
| r1_f1 | 0.6381 | `class_weight=balanced`, `learning_rate=0.05`, `max_iter=200`, `max_leaf_nodes=15` |
| r1_f2 | 0.6308 | `class_weight=balanced`, `learning_rate=0.05`, `max_iter=200`, `max_leaf_nodes=31` |
| r1_f3 | 0.6350 | `class_weight=balanced`, `learning_rate=0.05`, `max_iter=200`, `max_leaf_nodes=31` |
| r1_f4 | 0.6438 | `class_weight=balanced`, `learning_rate=0.05`, `max_iter=200`, `max_leaf_nodes=31` |
| r1_f5 | 0.6309 | `class_weight=balanced`, `learning_rate=0.05`, `max_iter=200`, `max_leaf_nodes=31` |
| r2_f1 | 0.6330 | `class_weight=balanced`, `learning_rate=0.05`, `max_iter=200`, `max_leaf_nodes=15` |
| r2_f2 | 0.6323 | `class_weight=balanced`, `learning_rate=0.05`, `max_iter=200`, `max_leaf_nodes=31` |
| r2_f3 | 0.6254 | `class_weight=balanced`, `learning_rate=0.05`, `max_iter=200`, `max_leaf_nodes=31` |
| r2_f4 | 0.6388 | `class_weight=balanced`, `learning_rate=0.05`, `max_iter=200`, `max_leaf_nodes=31` |
| r2_f5 | 0.6340 | `class_weight=balanced`, `learning_rate=0.05`, `max_iter=200`, `max_leaf_nodes=31` |
| r3_f1 | 0.6343 | `class_weight=balanced`, `learning_rate=0.05`, `max_iter=200`, `max_leaf_nodes=31` |
| r3_f2 | 0.6276 | `class_weight=balanced`, `learning_rate=0.05`, `max_iter=200`, `max_leaf_nodes=31` |
| r3_f3 | 0.6235 | `class_weight=balanced`, `learning_rate=0.05`, `max_iter=200`, `max_leaf_nodes=31` |
| r3_f4 | 0.6381 | `class_weight=balanced`, `learning_rate=0.05`, `max_iter=200`, `max_leaf_nodes=31` |
| r3_f5 | 0.6337 | `class_weight=balanced`, `learning_rate=0.05`, `max_iter=200`, `max_leaf_nodes=31` |

### df_gradient_boosting

**Configuração mais frequente** (across 15 outer folds):
- `class_weight` = `balanced`
- `learning_rate` = `0.05`
- `max_iter` = `200`
- `max_leaf_nodes` = `31`

| Fold | inner macro-F1 | Parâmetros |
|---|---:|---|
| r1_f1 | 0.6893 | `class_weight=balanced`, `learning_rate=0.05`, `max_iter=200`, `max_leaf_nodes=31` |
| r1_f2 | 0.6889 | `class_weight=balanced`, `learning_rate=0.05`, `max_iter=200`, `max_leaf_nodes=15` |
| r1_f3 | 0.6870 | `class_weight=balanced`, `learning_rate=0.05`, `max_iter=200`, `max_leaf_nodes=15` |
| r1_f4 | 0.6901 | `class_weight=balanced`, `learning_rate=0.05`, `max_iter=200`, `max_leaf_nodes=31` |
| r1_f5 | 0.6928 | `class_weight=balanced`, `learning_rate=0.1`, `max_iter=200`, `max_leaf_nodes=31` |
| r2_f1 | 0.6921 | `class_weight=balanced`, `learning_rate=0.05`, `max_iter=200`, `max_leaf_nodes=31` |
| r2_f2 | 0.6867 | `class_weight=balanced`, `learning_rate=0.05`, `max_iter=200`, `max_leaf_nodes=31` |
| r2_f3 | 0.6893 | `class_weight=balanced`, `learning_rate=0.1`, `max_iter=200`, `max_leaf_nodes=31` |
| r2_f4 | 0.6933 | `class_weight=balanced`, `learning_rate=0.05`, `max_iter=200`, `max_leaf_nodes=31` |
| r2_f5 | 0.6896 | `class_weight=balanced`, `learning_rate=0.05`, `max_iter=200`, `max_leaf_nodes=31` |
| r3_f1 | 0.6880 | `class_weight=balanced`, `learning_rate=0.05`, `max_iter=200`, `max_leaf_nodes=31` |
| r3_f2 | 0.6912 | `class_weight=balanced`, `learning_rate=0.05`, `max_iter=200`, `max_leaf_nodes=31` |
| r3_f3 | 0.6858 | `class_weight=balanced`, `learning_rate=0.05`, `max_iter=200`, `max_leaf_nodes=31` |
| r3_f4 | 0.6894 | `class_weight=balanced`, `learning_rate=0.05`, `max_iter=200`, `max_leaf_nodes=31` |
| r3_f5 | 0.6923 | `class_weight=balanced`, `learning_rate=0.1`, `max_iter=500`, `max_leaf_nodes=31` |

## 6. Matrizes de confusão agregadas (OOF — todos os folds)

> Cada deck aparece 3× nas predições OOF (uma vez por repeat). Total: 12.135 × 3 = 36.405 entradas.

**bc_gradient_boosting** — linhas = verdadeiro, colunas = previsto

| True \ Pred | 2 | 3 | 4 |
|---|---|---|---|
| **2** | 5343 | 1536 | 84 | *(n=6963)*
| **3** | 4497 | 10699 | 3455 | *(n=18651)*
| **4** | 659 | 2721 | 7411 | *(n=10791)*

**Métricas por classe — bc_gradient_boosting** (calculadas sobre a matriz agregada)

| Classe | Precisão | Recall | F1 |
|---|---:|---:|---:|
| 2 | 0.5089 | 0.7673 | 0.6120 |
| 3 | 0.7154 | 0.5736 | 0.6367 |
| 4 | 0.6768 | 0.6868 | 0.6818 |

**df_gradient_boosting** — linhas = verdadeiro, colunas = previsto

| True \ Pred | 2 | 3 | 4 |
|---|---|---|---|
| **2** | 5303 | 1530 | 130 | *(n=6963)*
| **3** | 4086 | 12715 | 1850 | *(n=18651)*
| **4** | 440 | 2967 | 7384 | *(n=10791)*

**Métricas por classe — df_gradient_boosting** (calculadas sobre a matriz agregada)

| Classe | Precisão | Recall | F1 |
|---|---:|---:|---:|
| 2 | 0.5395 | 0.7616 | 0.6316 |
| 3 | 0.7387 | 0.6817 | 0.7091 |
| 4 | 0.7886 | 0.6843 | 0.7327 |

## 7. Artefatos

- `experiments/best_models.json` — seleção consumida pela Fase J
- `documents/reports/results/phase_h_best_models.md` — este relatório
