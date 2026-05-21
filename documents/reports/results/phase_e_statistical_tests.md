# Testes Estatísticos — Fase E

- Friedman statistic: `133.152727`
- Friedman p-value: `0.000000`
- Nemenyi critical difference (alpha=0.05): `3.497584`

## Ranks Médios

| Modelo | Rank médio |
|---|---:|
| `df_gradient_boosting` | 1.0000 |
| `df_logistic_regression` | 2.0667 |
| `df_random_forest` | 3.1333 |
| `df_linear_svc` | 3.8000 |
| `bc_gradient_boosting` | 5.0000 |
| `bc_logistic_regression` | 6.0667 |
| `bc_linear_svc` | 7.3333 |
| `df_naive_bayes` | 7.6000 |
| `bc_naive_bayes` | 9.0000 |
| `bc_random_forest` | 10.0000 |

## Nemenyi

- `bc_gradient_boosting` vs `bc_naive_bayes`: rank diff `4.0000`.
- `bc_gradient_boosting` vs `bc_random_forest`: rank diff `5.0000`.
- `bc_gradient_boosting` vs `df_gradient_boosting`: rank diff `4.0000`.
- `bc_linear_svc` vs `df_gradient_boosting`: rank diff `6.3333`.
- `bc_linear_svc` vs `df_linear_svc`: rank diff `3.5333`.
- `bc_linear_svc` vs `df_logistic_regression`: rank diff `5.2667`.
- `bc_linear_svc` vs `df_random_forest`: rank diff `4.2000`.
- `bc_logistic_regression` vs `bc_random_forest`: rank diff `3.9333`.
- `bc_logistic_regression` vs `df_gradient_boosting`: rank diff `5.0667`.
- `bc_logistic_regression` vs `df_logistic_regression`: rank diff `4.0000`.
- `bc_naive_bayes` vs `df_gradient_boosting`: rank diff `8.0000`.
- `bc_naive_bayes` vs `df_linear_svc`: rank diff `5.2000`.
- `bc_naive_bayes` vs `df_logistic_regression`: rank diff `6.9333`.
- `bc_naive_bayes` vs `df_random_forest`: rank diff `5.8667`.
- `bc_random_forest` vs `df_gradient_boosting`: rank diff `9.0000`.
- `bc_random_forest` vs `df_linear_svc`: rank diff `6.2000`.
- `bc_random_forest` vs `df_logistic_regression`: rank diff `7.9333`.
- `bc_random_forest` vs `df_random_forest`: rank diff `6.8667`.
- `df_gradient_boosting` vs `df_naive_bayes`: rank diff `6.6000`.
- `df_linear_svc` vs `df_naive_bayes`: rank diff `3.8000`.
- `df_logistic_regression` vs `df_naive_bayes`: rank diff `5.5333`.
- `df_naive_bayes` vs `df_random_forest`: rank diff `4.4667`.

## Wilcoxon Pareado

| Modelo A | Modelo B | Statistic | p-value |
|---|---|---:|---:|
| `bc_gradient_boosting` | `bc_linear_svc` | 0.0000 | 0.000061 |
| `bc_gradient_boosting` | `bc_logistic_regression` | 0.0000 | 0.000061 |
| `bc_gradient_boosting` | `bc_naive_bayes` | 0.0000 | 0.000061 |
| `bc_gradient_boosting` | `bc_random_forest` | 0.0000 | 0.000061 |
| `bc_gradient_boosting` | `df_gradient_boosting` | 0.0000 | 0.000061 |
| `bc_gradient_boosting` | `df_linear_svc` | 0.0000 | 0.000061 |
| `bc_gradient_boosting` | `df_logistic_regression` | 0.0000 | 0.000061 |
| `bc_gradient_boosting` | `df_naive_bayes` | 0.0000 | 0.000061 |
| `bc_gradient_boosting` | `df_random_forest` | 0.0000 | 0.000061 |
| `bc_linear_svc` | `bc_logistic_regression` | 2.0000 | 0.000183 |
| `bc_linear_svc` | `bc_naive_bayes` | 0.0000 | 0.000061 |
| `bc_linear_svc` | `bc_random_forest` | 0.0000 | 0.000061 |
| `bc_linear_svc` | `df_gradient_boosting` | 0.0000 | 0.000061 |
| `bc_linear_svc` | `df_linear_svc` | 0.0000 | 0.000061 |
| `bc_linear_svc` | `df_logistic_regression` | 0.0000 | 0.000061 |
| `bc_linear_svc` | `df_naive_bayes` | 43.0000 | 0.359131 |
| `bc_linear_svc` | `df_random_forest` | 0.0000 | 0.000061 |
| `bc_logistic_regression` | `bc_naive_bayes` | 0.0000 | 0.000061 |
| `bc_logistic_regression` | `bc_random_forest` | 0.0000 | 0.000061 |
| `bc_logistic_regression` | `df_gradient_boosting` | 0.0000 | 0.000061 |
| `bc_logistic_regression` | `df_linear_svc` | 0.0000 | 0.000061 |
| `bc_logistic_regression` | `df_logistic_regression` | 0.0000 | 0.000061 |
| `bc_logistic_regression` | `df_naive_bayes` | 0.0000 | 0.000061 |
| `bc_logistic_regression` | `df_random_forest` | 0.0000 | 0.000061 |
| `bc_naive_bayes` | `bc_random_forest` | 0.0000 | 0.000061 |
| `bc_naive_bayes` | `df_gradient_boosting` | 0.0000 | 0.000061 |
| `bc_naive_bayes` | `df_linear_svc` | 0.0000 | 0.000061 |
| `bc_naive_bayes` | `df_logistic_regression` | 0.0000 | 0.000061 |
| `bc_naive_bayes` | `df_naive_bayes` | 0.0000 | 0.000061 |
| `bc_naive_bayes` | `df_random_forest` | 0.0000 | 0.000061 |
| `bc_random_forest` | `df_gradient_boosting` | 0.0000 | 0.000061 |
| `bc_random_forest` | `df_linear_svc` | 0.0000 | 0.000061 |
| `bc_random_forest` | `df_logistic_regression` | 0.0000 | 0.000061 |
| `bc_random_forest` | `df_naive_bayes` | 0.0000 | 0.000061 |
| `bc_random_forest` | `df_random_forest` | 0.0000 | 0.000061 |
| `df_gradient_boosting` | `df_linear_svc` | 0.0000 | 0.000061 |
| `df_gradient_boosting` | `df_logistic_regression` | 0.0000 | 0.000061 |
| `df_gradient_boosting` | `df_naive_bayes` | 0.0000 | 0.000061 |
| `df_gradient_boosting` | `df_random_forest` | 0.0000 | 0.000061 |
| `df_linear_svc` | `df_logistic_regression` | 0.0000 | 0.000061 |
| `df_linear_svc` | `df_naive_bayes` | 0.0000 | 0.000061 |
| `df_linear_svc` | `df_random_forest` | 26.0000 | 0.055359 |
| `df_logistic_regression` | `df_naive_bayes` | 0.0000 | 0.000061 |
| `df_logistic_regression` | `df_random_forest` | 1.0000 | 0.000122 |
| `df_naive_bayes` | `df_random_forest` | 0.0000 | 0.000061 |
