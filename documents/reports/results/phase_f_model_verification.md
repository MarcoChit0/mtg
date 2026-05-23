# Verificação de Modelos — Fase F

## F.1 Completude

Modelos incluídos na análise: **12**

Flag `--all`: não — modelos parciais aceitos


| Modelo | Representação | Algoritmo | Folds | Macro-F1 média | Macro-F1 dp |
|---|---|---|---:|---:|---:|
| `bc_decision_tree` | BC | decision_tree | 15/15 | 0.5475 | 0.0116 |
| `bc_gradient_boosting` | BC | gradient_boosting | 15/15 | 0.6433 | 0.0121 |
| `bc_linear_svc` | BC | linear_svc | 15/15 | 0.5927 | 0.0090 |
| `bc_logistic_regression` | BC | logistic_regression | 15/15 | 0.6035 | 0.0116 |
| `bc_naive_bayes` | BC | naive_bayes | 15/15 | 0.5535 | 0.0090 |
| `bc_random_forest` | BC | random_forest | 15/15 | 0.6326 | 0.0122 |
| `df_decision_tree` | DF | decision_tree | 15/15 | 0.6727 | 0.0100 |
| `df_gradient_boosting` | DF | gradient_boosting | 15/15 | 0.6908 | 0.0093 |
| `df_linear_svc` | DF | linear_svc | 15/15 | 0.6566 | 0.0086 |
| `df_logistic_regression` | DF | logistic_regression | 15/15 | 0.6707 | 0.0110 |
| `df_naive_bayes` | DF | naive_bayes | 15/15 | 0.5905 | 0.0093 |
| `df_random_forest` | DF | random_forest | 15/15 | 0.6733 | 0.0076 |

### Avisos

- [OPTIONAL MISSING] bc_linear_svc: cv_results_per_fold.jsonl not found
- [OPTIONAL MISSING] bc_linear_svc: checkpoint_state.json not found
- [OPTIONAL MISSING] bc_logistic_regression: cv_results_per_fold.jsonl not found
- [OPTIONAL MISSING] df_linear_svc: cv_results_per_fold.jsonl not found

✅ Todos os modelos compartilham os mesmos fold IDs.


## F.2 GroupKFold por Comandante

Avalia cada modelo com `GroupKFold(n_splits=5)` agrupando decks pelo mesmo comandante (ou par de comandantes). Um gap grande indica que o modelo depende de padrões associados a comandantes específicos já vistos no treino.

| Modelo | Macro-F1 grupo (média) | Macro-F1 grupo (dp) | Macro-F1 estratificado | Gap (Estratif. − Grupo) |
|---|---:|---:|---:|---:|
| `bc_decision_tree` | 0.5581 | 0.0146 | 0.5475 | -0.0106 |
| `bc_gradient_boosting` | 0.6543 | 0.0036 | 0.6433 | -0.0111 |
| `bc_linear_svc` | 0.5528 | 0.0049 | 0.5927 | +0.0398 |
| `bc_logistic_regression` | 0.6020 | 0.0090 | 0.6035 | +0.0015 |
| `bc_naive_bayes` | 0.5781 | 0.0055 | 0.5535 | -0.0246 |
| `bc_random_forest` | 0.5655 | 0.0051 | 0.6326 | +0.0671 |
| `df_decision_tree` | 0.6120 | 0.0164 | 0.6727 | +0.0606 |
| `df_gradient_boosting` | 0.7032 | 0.0066 | 0.6908 | -0.0124 |
| `df_linear_svc` | 0.6528 | 0.0060 | 0.6566 | +0.0038 |
| `df_logistic_regression` | 0.6893 | 0.0085 | 0.6707 | -0.0186 |
| `df_naive_bayes` | 0.6388 | 0.0134 | 0.5905 | -0.0484 |
| `df_random_forest` | 0.6844 | 0.0103 | 0.6733 | -0.0111 |

## Artefatos

- `experiments/model_verification/group_kfold_results.json`
- `documents/reports/results/phase_f_model_verification.md`
- `documents/reports/results/phase_f_statistical_tests.md`
