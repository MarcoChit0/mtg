# Testes Estatísticos — Fase E

<<<<<<< Updated upstream
<<<<<<< Updated upstream
<<<<<<< Updated upstream
- Friedman statistic: `133.152727`
=======
- Friedman statistic: `161.430769`
>>>>>>> Stashed changes
=======
- Friedman statistic: `132.120000`
>>>>>>> Stashed changes
=======
- Friedman statistic: `131.349091`
>>>>>>> Stashed changes
- Friedman p-value: `0.000000`
- Nemenyi critical difference (alpha=0.05): `4.302527`

## Ranks Médios

| Modelo | Rank médio |
|---|---:|
<<<<<<< Updated upstream
<<<<<<< Updated upstream
| `df_gradient_boosting` | 1.0000 |
<<<<<<< Updated upstream
| `df_logistic_regression` | 2.0667 |
| `df_random_forest` | 3.1333 |
| `df_linear_svc` | 3.8000 |
| `bc_gradient_boosting` | 5.0000 |
=======
| `df_gradient_boosting` | 1.0667 |
| `df_logistic_regression` | 2.0667 |
| `df_random_forest` | 3.2000 |
| `df_linear_svc` | 4.0000 |
| `bc_gradient_boosting` | 4.6667 |
>>>>>>> Stashed changes
| `bc_logistic_regression` | 6.0667 |
| `bc_linear_svc` | 7.3333 |
| `df_naive_bayes` | 7.6000 |
| `bc_naive_bayes` | 9.0000 |
| `bc_random_forest` | 10.0000 |

## Nemenyi

<<<<<<< Updated upstream
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
=======
| `df_gradient_boosting` | 1.0667 |
| `df_decision_tree` | 2.5333 |
| `df_logistic_regression` | 2.6667 |
| `df_random_forest` | 3.9333 |
| `df_linear_svc` | 4.8000 |
| `bc_gradient_boosting` | 6.0000 |
| `bc_logistic_regression` | 7.0667 |
| `bc_linear_svc` | 8.3333 |
| `df_naive_bayes` | 8.6000 |
| `bc_naive_bayes` | 10.3333 |
| `bc_decision_tree` | 10.7333 |
| `bc_random_forest` | 11.9333 |

## Nemenyi

- `bc_decision_tree` vs `bc_gradient_boosting`: rank diff `4.7333`.
- `bc_decision_tree` vs `df_decision_tree`: rank diff `8.2000`.
- `bc_decision_tree` vs `df_gradient_boosting`: rank diff `9.6667`.
- `bc_decision_tree` vs `df_linear_svc`: rank diff `5.9333`.
- `bc_decision_tree` vs `df_logistic_regression`: rank diff `8.0667`.
- `bc_decision_tree` vs `df_random_forest`: rank diff `6.8000`.
- `bc_gradient_boosting` vs `bc_naive_bayes`: rank diff `4.3333`.
- `bc_gradient_boosting` vs `bc_random_forest`: rank diff `5.9333`.
- `bc_gradient_boosting` vs `df_gradient_boosting`: rank diff `4.9333`.
- `bc_linear_svc` vs `df_decision_tree`: rank diff `5.8000`.
- `bc_linear_svc` vs `df_gradient_boosting`: rank diff `7.2667`.
- `bc_linear_svc` vs `df_logistic_regression`: rank diff `5.6667`.
- `bc_linear_svc` vs `df_random_forest`: rank diff `4.4000`.
- `bc_logistic_regression` vs `bc_random_forest`: rank diff `4.8667`.
- `bc_logistic_regression` vs `df_decision_tree`: rank diff `4.5333`.
- `bc_logistic_regression` vs `df_gradient_boosting`: rank diff `6.0000`.
- `bc_logistic_regression` vs `df_logistic_regression`: rank diff `4.4000`.
- `bc_naive_bayes` vs `df_decision_tree`: rank diff `7.8000`.
- `bc_naive_bayes` vs `df_gradient_boosting`: rank diff `9.2667`.
- `bc_naive_bayes` vs `df_linear_svc`: rank diff `5.5333`.
- `bc_naive_bayes` vs `df_logistic_regression`: rank diff `7.6667`.
- `bc_naive_bayes` vs `df_random_forest`: rank diff `6.4000`.
- `bc_random_forest` vs `df_decision_tree`: rank diff `9.4000`.
- `bc_random_forest` vs `df_gradient_boosting`: rank diff `10.8667`.
- `bc_random_forest` vs `df_linear_svc`: rank diff `7.1333`.
- `bc_random_forest` vs `df_logistic_regression`: rank diff `9.2667`.
- `bc_random_forest` vs `df_random_forest`: rank diff `8.0000`.
- `df_decision_tree` vs `df_naive_bayes`: rank diff `6.0667`.
- `df_gradient_boosting` vs `df_naive_bayes`: rank diff `7.5333`.
- `df_logistic_regression` vs `df_naive_bayes`: rank diff `5.9333`.
- `df_naive_bayes` vs `df_random_forest`: rank diff `4.6667`.
>>>>>>> Stashed changes
=======
| `df_random_forest` | 2.4000 |
| `df_logistic_regression` | 2.6667 |
| `df_linear_svc` | 3.9333 |
| `bc_random_forest` | 5.3333 |
| `bc_gradient_boosting` | 5.6667 |
| `bc_logistic_regression` | 7.0667 |
| `bc_linear_svc` | 8.3333 |
| `df_naive_bayes` | 8.6000 |
| `bc_naive_bayes` | 10.0000 |

## Nemenyi

- `bc_gradient_boosting` vs `bc_naive_bayes`: rank diff `4.3333`.
- `bc_gradient_boosting` vs `df_gradient_boosting`: rank diff `4.6667`.
- `bc_linear_svc` vs `df_gradient_boosting`: rank diff `7.3333`.
- `bc_linear_svc` vs `df_linear_svc`: rank diff `4.4000`.
- `bc_linear_svc` vs `df_logistic_regression`: rank diff `5.6667`.
- `bc_linear_svc` vs `df_random_forest`: rank diff `5.9333`.
- `bc_logistic_regression` vs `df_gradient_boosting`: rank diff `6.0667`.
- `bc_logistic_regression` vs `df_logistic_regression`: rank diff `4.4000`.
- `bc_logistic_regression` vs `df_random_forest`: rank diff `4.6667`.
- `bc_naive_bayes` vs `bc_random_forest`: rank diff `4.6667`.
- `bc_naive_bayes` vs `df_gradient_boosting`: rank diff `9.0000`.
- `bc_naive_bayes` vs `df_linear_svc`: rank diff `6.0667`.
- `bc_naive_bayes` vs `df_logistic_regression`: rank diff `7.3333`.
- `bc_naive_bayes` vs `df_random_forest`: rank diff `7.6000`.
- `bc_random_forest` vs `df_gradient_boosting`: rank diff `4.3333`.
- `df_gradient_boosting` vs `df_naive_bayes`: rank diff `7.6000`.
- `df_linear_svc` vs `df_naive_bayes`: rank diff `4.6667`.
- `df_logistic_regression` vs `df_naive_bayes`: rank diff `5.9333`.
- `df_naive_bayes` vs `df_random_forest`: rank diff `6.2000`.
>>>>>>> Stashed changes
=======
- `bc_gradient_boosting` vs `bc_naive_bayes`: rank diff `4.3333`.
- `bc_gradient_boosting` vs `bc_random_forest`: rank diff `5.3333`.
- `bc_gradient_boosting` vs `df_gradient_boosting`: rank diff `3.6000`.
- `bc_linear_svc` vs `df_gradient_boosting`: rank diff `6.2667`.
- `bc_linear_svc` vs `df_logistic_regression`: rank diff `5.2667`.
- `bc_linear_svc` vs `df_random_forest`: rank diff `4.1333`.
- `bc_logistic_regression` vs `bc_random_forest`: rank diff `3.9333`.
- `bc_logistic_regression` vs `df_gradient_boosting`: rank diff `5.0000`.
- `bc_logistic_regression` vs `df_logistic_regression`: rank diff `4.0000`.
- `bc_naive_bayes` vs `df_gradient_boosting`: rank diff `7.9333`.
- `bc_naive_bayes` vs `df_linear_svc`: rank diff `5.0000`.
- `bc_naive_bayes` vs `df_logistic_regression`: rank diff `6.9333`.
- `bc_naive_bayes` vs `df_random_forest`: rank diff `5.8000`.
- `bc_random_forest` vs `df_gradient_boosting`: rank diff `8.9333`.
- `bc_random_forest` vs `df_linear_svc`: rank diff `6.0000`.
- `bc_random_forest` vs `df_logistic_regression`: rank diff `7.9333`.
- `bc_random_forest` vs `df_random_forest`: rank diff `6.8000`.
- `df_gradient_boosting` vs `df_naive_bayes`: rank diff `6.5333`.
- `df_linear_svc` vs `df_naive_bayes`: rank diff `3.6000`.
- `df_logistic_regression` vs `df_naive_bayes`: rank diff `5.5333`.
- `df_naive_bayes` vs `df_random_forest`: rank diff `4.4000`.
>>>>>>> Stashed changes

## Wilcoxon Pareado

| Modelo A | Modelo B | Statistic | p-value |
|---|---|---:|---:|
| `bc_decision_tree` | `bc_gradient_boosting` | 0.0000 | 0.000061 |
| `bc_decision_tree` | `bc_linear_svc` | 0.0000 | 0.000061 |
| `bc_decision_tree` | `bc_logistic_regression` | 0.0000 | 0.000061 |
| `bc_decision_tree` | `bc_naive_bayes` | 33.0000 | 0.135376 |
| `bc_decision_tree` | `bc_random_forest` | 1.0000 | 0.000122 |
| `bc_decision_tree` | `df_decision_tree` | 0.0000 | 0.000061 |
| `bc_decision_tree` | `df_gradient_boosting` | 0.0000 | 0.000061 |
| `bc_decision_tree` | `df_linear_svc` | 0.0000 | 0.000061 |
| `bc_decision_tree` | `df_logistic_regression` | 0.0000 | 0.000061 |
| `bc_decision_tree` | `df_naive_bayes` | 0.0000 | 0.000061 |
| `bc_decision_tree` | `df_random_forest` | 0.0000 | 0.000061 |
| `bc_gradient_boosting` | `bc_linear_svc` | 0.0000 | 0.000061 |
| `bc_gradient_boosting` | `bc_logistic_regression` | 0.0000 | 0.000061 |
| `bc_gradient_boosting` | `bc_naive_bayes` | 0.0000 | 0.000061 |
<<<<<<< Updated upstream
| `bc_gradient_boosting` | `bc_random_forest` | 0.0000 | 0.000061 |
| `bc_gradient_boosting` | `df_decision_tree` | 0.0000 | 0.000061 |
=======
| `bc_gradient_boosting` | `bc_random_forest` | 32.0000 | 0.120544 |
>>>>>>> Stashed changes
| `bc_gradient_boosting` | `df_gradient_boosting` | 0.0000 | 0.000061 |
| `bc_gradient_boosting` | `df_linear_svc` | 8.0000 | 0.001526 |
| `bc_gradient_boosting` | `df_logistic_regression` | 1.0000 | 0.000122 |
| `bc_gradient_boosting` | `df_naive_bayes` | 0.0000 | 0.000061 |
| `bc_gradient_boosting` | `df_random_forest` | 1.0000 | 0.000122 |
| `bc_linear_svc` | `bc_logistic_regression` | 2.0000 | 0.000183 |
| `bc_linear_svc` | `bc_naive_bayes` | 0.0000 | 0.000061 |
| `bc_linear_svc` | `bc_random_forest` | 0.0000 | 0.000061 |
| `bc_linear_svc` | `df_decision_tree` | 0.0000 | 0.000061 |
| `bc_linear_svc` | `df_gradient_boosting` | 0.0000 | 0.000061 |
| `bc_linear_svc` | `df_linear_svc` | 0.0000 | 0.000061 |
| `bc_linear_svc` | `df_logistic_regression` | 0.0000 | 0.000061 |
| `bc_linear_svc` | `df_naive_bayes` | 43.0000 | 0.359131 |
| `bc_linear_svc` | `df_random_forest` | 0.0000 | 0.000061 |
| `bc_logistic_regression` | `bc_naive_bayes` | 0.0000 | 0.000061 |
| `bc_logistic_regression` | `bc_random_forest` | 0.0000 | 0.000061 |
| `bc_logistic_regression` | `df_decision_tree` | 0.0000 | 0.000061 |
| `bc_logistic_regression` | `df_gradient_boosting` | 0.0000 | 0.000061 |
| `bc_logistic_regression` | `df_linear_svc` | 0.0000 | 0.000061 |
| `bc_logistic_regression` | `df_logistic_regression` | 0.0000 | 0.000061 |
| `bc_logistic_regression` | `df_naive_bayes` | 0.0000 | 0.000061 |
| `bc_logistic_regression` | `df_random_forest` | 0.0000 | 0.000061 |
| `bc_naive_bayes` | `bc_random_forest` | 0.0000 | 0.000061 |
| `bc_naive_bayes` | `df_decision_tree` | 0.0000 | 0.000061 |
| `bc_naive_bayes` | `df_gradient_boosting` | 0.0000 | 0.000061 |
| `bc_naive_bayes` | `df_linear_svc` | 0.0000 | 0.000061 |
| `bc_naive_bayes` | `df_logistic_regression` | 0.0000 | 0.000061 |
| `bc_naive_bayes` | `df_naive_bayes` | 0.0000 | 0.000061 |
| `bc_naive_bayes` | `df_random_forest` | 0.0000 | 0.000061 |
| `bc_random_forest` | `df_decision_tree` | 0.0000 | 0.000061 |
| `bc_random_forest` | `df_gradient_boosting` | 0.0000 | 0.000061 |
| `bc_random_forest` | `df_linear_svc` | 0.0000 | 0.000061 |
| `bc_random_forest` | `df_logistic_regression` | 0.0000 | 0.000061 |
| `bc_random_forest` | `df_naive_bayes` | 0.0000 | 0.000061 |
| `bc_random_forest` | `df_random_forest` | 0.0000 | 0.000061 |
| `df_decision_tree` | `df_gradient_boosting` | 2.0000 | 0.000183 |
| `df_decision_tree` | `df_linear_svc` | 0.0000 | 0.000061 |
| `df_decision_tree` | `df_logistic_regression` | 49.0000 | 0.561401 |
| `df_decision_tree` | `df_naive_bayes` | 0.0000 | 0.000061 |
| `df_decision_tree` | `df_random_forest` | 13.0000 | 0.005371 |
| `df_gradient_boosting` | `df_linear_svc` | 0.0000 | 0.000061 |
| `df_gradient_boosting` | `df_logistic_regression` | 1.0000 | 0.000122 |
| `df_gradient_boosting` | `df_naive_bayes` | 0.0000 | 0.000061 |
| `df_gradient_boosting` | `df_random_forest` | 0.0000 | 0.000061 |
| `df_linear_svc` | `df_logistic_regression` | 0.0000 | 0.000061 |
| `df_linear_svc` | `df_naive_bayes` | 0.0000 | 0.000061 |
| `df_linear_svc` | `df_random_forest` | 2.0000 | 0.000183 |
| `df_logistic_regression` | `df_naive_bayes` | 0.0000 | 0.000061 |
<<<<<<< Updated upstream
<<<<<<< Updated upstream
| `df_logistic_regression` | `df_random_forest` | 1.0000 | 0.000122 |
=======
| `df_logistic_regression` | `df_random_forest` | 40.0000 | 0.276855 |
>>>>>>> Stashed changes
=======
| `df_logistic_regression` | `df_random_forest` | 1.0000 | 0.000122 |
>>>>>>> Stashed changes
| `df_naive_bayes` | `df_random_forest` | 0.0000 | 0.000061 |
