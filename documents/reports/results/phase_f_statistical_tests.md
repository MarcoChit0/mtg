# Testes Estatísticos — Fase F

Modelos incluídos: **12** · Folds usados por modelo: **15**

**Friedman**: statistic=159.7692, p=0.000000

**Nemenyi**: diferença crítica=4.3025 para alpha=0.05


## Ranks Médios

| Modelo | Rank médio |
|---|---:|
| `df_gradient_boosting` | 1.0667 |
| `df_random_forest` | 2.8000 |
| `df_decision_tree` | 3.0000 |
| `df_logistic_regression` | 3.2667 |
| `df_linear_svc` | 5.1333 |
| `bc_gradient_boosting` | 5.8667 |
| `bc_random_forest` | 6.8667 |
| `bc_logistic_regression` | 8.0667 |
| `bc_linear_svc` | 9.3333 |
| `df_naive_bayes` | 9.6000 |
| `bc_naive_bayes` | 11.3333 |
| `bc_decision_tree` | 11.6667 |

## Nemenyi — pares significativos (CD=4.3025)

| Modelo A | Modelo B | Diferença de rank |
|---|---|---:|
| `bc_decision_tree` | `df_gradient_boosting` | 10.6000 |
| `bc_naive_bayes` | `df_gradient_boosting` | 10.2667 |
| `bc_decision_tree` | `df_random_forest` | 8.8667 |
| `bc_decision_tree` | `df_decision_tree` | 8.6667 |
| `bc_naive_bayes` | `df_random_forest` | 8.5333 |
| `df_gradient_boosting` | `df_naive_bayes` | 8.5333 |
| `bc_decision_tree` | `df_logistic_regression` | 8.4000 |
| `bc_naive_bayes` | `df_decision_tree` | 8.3333 |
| `bc_linear_svc` | `df_gradient_boosting` | 8.2667 |
| `bc_naive_bayes` | `df_logistic_regression` | 8.0667 |
| `bc_logistic_regression` | `df_gradient_boosting` | 7.0000 |
| `df_naive_bayes` | `df_random_forest` | 6.8000 |
| `df_decision_tree` | `df_naive_bayes` | 6.6000 |
| `bc_decision_tree` | `df_linear_svc` | 6.5333 |
| `bc_linear_svc` | `df_random_forest` | 6.5333 |
| `bc_linear_svc` | `df_decision_tree` | 6.3333 |
| `df_logistic_regression` | `df_naive_bayes` | 6.3333 |
| `bc_naive_bayes` | `df_linear_svc` | 6.2000 |
| `bc_linear_svc` | `df_logistic_regression` | 6.0667 |
| `bc_decision_tree` | `bc_gradient_boosting` | 5.8000 |
| `bc_random_forest` | `df_gradient_boosting` | 5.8000 |
| `bc_gradient_boosting` | `bc_naive_bayes` | 5.4667 |
| `bc_logistic_regression` | `df_random_forest` | 5.2667 |
| `bc_logistic_regression` | `df_decision_tree` | 5.0667 |
| `bc_decision_tree` | `bc_random_forest` | 4.8000 |
| `bc_gradient_boosting` | `df_gradient_boosting` | 4.8000 |
| `bc_logistic_regression` | `df_logistic_regression` | 4.8000 |
| `bc_naive_bayes` | `bc_random_forest` | 4.4667 |
| `df_linear_svc` | `df_naive_bayes` | 4.4667 |

## Wilcoxon Pareado

| Modelo A | Modelo B | Statistic | p-value | Significativo (α=0.05) |
|---|---|---:|---:|:---:|
| `bc_decision_tree` | `bc_gradient_boosting` | 0.0000 | 0.000061 | ✓ |
| `bc_decision_tree` | `bc_linear_svc` | 0.0000 | 0.000061 | ✓ |
| `bc_decision_tree` | `bc_logistic_regression` | 0.0000 | 0.000061 | ✓ |
| `bc_decision_tree` | `bc_naive_bayes` | 33.0000 | 0.135376 |  |
| `bc_decision_tree` | `bc_random_forest` | 0.0000 | 0.000061 | ✓ |
| `bc_decision_tree` | `df_decision_tree` | 0.0000 | 0.000061 | ✓ |
| `bc_decision_tree` | `df_gradient_boosting` | 0.0000 | 0.000061 | ✓ |
| `bc_decision_tree` | `df_linear_svc` | 0.0000 | 0.000061 | ✓ |
| `bc_decision_tree` | `df_logistic_regression` | 0.0000 | 0.000061 | ✓ |
| `bc_decision_tree` | `df_naive_bayes` | 0.0000 | 0.000061 | ✓ |
| `bc_decision_tree` | `df_random_forest` | 0.0000 | 0.000061 | ✓ |
| `bc_gradient_boosting` | `bc_linear_svc` | 0.0000 | 0.000061 | ✓ |
| `bc_gradient_boosting` | `bc_logistic_regression` | 0.0000 | 0.000061 | ✓ |
| `bc_gradient_boosting` | `bc_naive_bayes` | 0.0000 | 0.000061 | ✓ |
| `bc_gradient_boosting` | `bc_random_forest` | 9.0000 | 0.002014 | ✓ |
| `bc_gradient_boosting` | `df_decision_tree` | 0.0000 | 0.000061 | ✓ |
| `bc_gradient_boosting` | `df_gradient_boosting` | 0.0000 | 0.000061 | ✓ |
| `bc_gradient_boosting` | `df_linear_svc` | 8.0000 | 0.001526 | ✓ |
| `bc_gradient_boosting` | `df_logistic_regression` | 1.0000 | 0.000122 | ✓ |
| `bc_gradient_boosting` | `df_naive_bayes` | 0.0000 | 0.000061 | ✓ |
| `bc_gradient_boosting` | `df_random_forest` | 0.0000 | 0.000061 | ✓ |
| `bc_linear_svc` | `bc_logistic_regression` | 2.0000 | 0.000183 | ✓ |
| `bc_linear_svc` | `bc_naive_bayes` | 0.0000 | 0.000061 | ✓ |
| `bc_linear_svc` | `bc_random_forest` | 0.0000 | 0.000061 | ✓ |
| `bc_linear_svc` | `df_decision_tree` | 0.0000 | 0.000061 | ✓ |
| `bc_linear_svc` | `df_gradient_boosting` | 0.0000 | 0.000061 | ✓ |
| `bc_linear_svc` | `df_linear_svc` | 0.0000 | 0.000061 | ✓ |
| `bc_linear_svc` | `df_logistic_regression` | 0.0000 | 0.000061 | ✓ |
| `bc_linear_svc` | `df_naive_bayes` | 43.0000 | 0.359131 |  |
| `bc_linear_svc` | `df_random_forest` | 0.0000 | 0.000061 | ✓ |
| `bc_logistic_regression` | `bc_naive_bayes` | 0.0000 | 0.000061 | ✓ |
| `bc_logistic_regression` | `bc_random_forest` | 0.0000 | 0.000061 | ✓ |
| `bc_logistic_regression` | `df_decision_tree` | 0.0000 | 0.000061 | ✓ |
| `bc_logistic_regression` | `df_gradient_boosting` | 0.0000 | 0.000061 | ✓ |
| `bc_logistic_regression` | `df_linear_svc` | 0.0000 | 0.000061 | ✓ |
| `bc_logistic_regression` | `df_logistic_regression` | 0.0000 | 0.000061 | ✓ |
| `bc_logistic_regression` | `df_naive_bayes` | 0.0000 | 0.000061 | ✓ |
| `bc_logistic_regression` | `df_random_forest` | 0.0000 | 0.000061 | ✓ |
| `bc_naive_bayes` | `bc_random_forest` | 0.0000 | 0.000061 | ✓ |
| `bc_naive_bayes` | `df_decision_tree` | 0.0000 | 0.000061 | ✓ |
| `bc_naive_bayes` | `df_gradient_boosting` | 0.0000 | 0.000061 | ✓ |
| `bc_naive_bayes` | `df_linear_svc` | 0.0000 | 0.000061 | ✓ |
| `bc_naive_bayes` | `df_logistic_regression` | 0.0000 | 0.000061 | ✓ |
| `bc_naive_bayes` | `df_naive_bayes` | 0.0000 | 0.000061 | ✓ |
| `bc_naive_bayes` | `df_random_forest` | 0.0000 | 0.000061 | ✓ |
| `bc_random_forest` | `df_decision_tree` | 0.0000 | 0.000061 | ✓ |
| `bc_random_forest` | `df_gradient_boosting` | 0.0000 | 0.000061 | ✓ |
| `bc_random_forest` | `df_linear_svc` | 0.0000 | 0.000061 | ✓ |
| `bc_random_forest` | `df_logistic_regression` | 0.0000 | 0.000061 | ✓ |
| `bc_random_forest` | `df_naive_bayes` | 0.0000 | 0.000061 | ✓ |
| `bc_random_forest` | `df_random_forest` | 0.0000 | 0.000061 | ✓ |
| `df_decision_tree` | `df_gradient_boosting` | 0.0000 | 0.000061 | ✓ |
| `df_decision_tree` | `df_linear_svc` | 0.0000 | 0.000061 | ✓ |
| `df_decision_tree` | `df_logistic_regression` | 47.0000 | 0.488708 |  |
| `df_decision_tree` | `df_naive_bayes` | 0.0000 | 0.000061 | ✓ |
| `df_decision_tree` | `df_random_forest` | 53.0000 | 0.719727 |  |
| `df_gradient_boosting` | `df_linear_svc` | 0.0000 | 0.000061 | ✓ |
| `df_gradient_boosting` | `df_logistic_regression` | 1.0000 | 0.000122 | ✓ |
| `df_gradient_boosting` | `df_naive_bayes` | 0.0000 | 0.000061 | ✓ |
| `df_gradient_boosting` | `df_random_forest` | 0.0000 | 0.000061 | ✓ |
| `df_linear_svc` | `df_logistic_regression` | 0.0000 | 0.000061 | ✓ |
| `df_linear_svc` | `df_naive_bayes` | 0.0000 | 0.000061 | ✓ |
| `df_linear_svc` | `df_random_forest` | 2.0000 | 0.000183 | ✓ |
| `df_logistic_regression` | `df_naive_bayes` | 0.0000 | 0.000061 | ✓ |
| `df_logistic_regression` | `df_random_forest` | 39.0000 | 0.252380 |  |
| `df_naive_bayes` | `df_random_forest` | 0.0000 | 0.000061 | ✓ |
