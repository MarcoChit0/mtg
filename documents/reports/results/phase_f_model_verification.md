# Verificação de Modelos — Fase F

## F.1 Completude

Modelos incluídos na análise: **12**

Flag `--all`: sim — todos os modelos exigidos


| Modelo | Representação | Algoritmo | Folds | Macro-F1 média | Macro-F1 dp |
|---|---|---|---:|---:|---:|
| `bc_decision_tree` | BC | decision_tree | 15/15 | 0.5475 | 0.0116 |
| `bc_gradient_boosting` | BC | gradient_boosting | 15/15 | 0.6433 | 0.0121 |
| `bc_linear_svc` | BC | linear_svc | 15/15 | 0.6147 | 0.0118 |
| `bc_logistic_regression` | BC | logistic_regression | 15/15 | 0.6236 | 0.0096 |
| `bc_naive_bayes` | BC | naive_bayes | 15/15 | 0.5535 | 0.0090 |
| `bc_random_forest` | BC | random_forest | 15/15 | 0.6326 | 0.0122 |
| `df_decision_tree` | DF | decision_tree | 15/15 | 0.6727 | 0.0100 |
| `df_gradient_boosting` | DF | gradient_boosting | 15/15 | 0.6908 | 0.0093 |
| `df_linear_svc` | DF | linear_svc | 15/15 | 0.6557 | 0.0085 |
| `df_logistic_regression` | DF | logistic_regression | 15/15 | 0.6707 | 0.0110 |
| `df_naive_bayes` | DF | naive_bayes | 15/15 | 0.5905 | 0.0093 |
| `df_random_forest` | DF | random_forest | 15/15 | 0.6733 | 0.0076 |

✅ Todos os modelos compartilham os mesmos fold IDs.


## F.2 GroupKFold por Comandante

Avalia cada modelo com `GroupKFold(n_splits=5)` agrupando decks pelo mesmo comandante (ou par de comandantes). Um gap grande indica que o modelo depende de padrões associados a comandantes específicos já vistos no treino.

| Modelo | Macro-F1 grupo (média) | Macro-F1 grupo (dp) | Macro-F1 estratificado | Gap (Estratif. − Grupo) |
|---|---:|---:|---:|---:|
| `bc_decision_tree` | 0.5590 | 0.0178 | 0.5475 | -0.0115 |
| `bc_gradient_boosting` | 0.6496 | 0.0058 | 0.6433 | -0.0064 |
| `bc_linear_svc` | 0.5541 | 0.0077 | 0.6147 | +0.0605 |
| `bc_logistic_regression` | 0.6040 | 0.0069 | 0.6236 | +0.0196 |
| `bc_naive_bayes` | 0.5818 | 0.0092 | 0.5535 | -0.0282 |
| `bc_random_forest` | 0.5682 | 0.0097 | 0.6326 | +0.0644 |
| `df_decision_tree` | 0.6123 | 0.0057 | 0.6727 | +0.0603 |
| `df_gradient_boosting` | 0.7021 | 0.0105 | 0.6908 | -0.0113 |
| `df_linear_svc` | 0.6544 | 0.0115 | 0.6557 | +0.0013 |
| `df_logistic_regression` | 0.6848 | 0.0108 | 0.6707 | -0.0141 |
| `df_naive_bayes` | 0.6080 | 0.0140 | 0.5905 | -0.0175 |
| `df_random_forest` | 0.6836 | 0.0088 | 0.6733 | -0.0104 |

## Artefatos

- `experiments/model_verification/group_kfold_results.json`
- `documents/reports/results/phase_f_model_verification.md`
- `documents/reports/results/phase_f_statistical_tests.md`
