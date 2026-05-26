# Voting Ensembles — Fase G

Ensembles de hard-voting simples construídos sobre as predições out-of-fold (OOF) geradas na Fase E. Nenhum modelo é retreinado. Os membros são os top-N modelos individuais globais por macro-F1 média na Fase E, independente de representação. Em empate de votos, o tie-break usa a macro-F1 média dos membros que votaram na classe; empate residual → menor rótulo.

## Modelos individuais (referência)

| Modelo | Repr. | Macro-F1 média | Macro-F1 dp | Folds |
|---|---|---:|---:|---:|
| `df_gradient_boosting` | DF | 0.6908 | 0.0093 | 15/15 |
| `df_random_forest` | DF | 0.6733 | 0.0076 | 15/15 |
| `df_decision_tree` | DF | 0.6727 | 0.0100 | 15/15 |
| `df_logistic_regression` | DF | 0.6707 | 0.0110 | 15/15 |
| `df_linear_svc` | DF | 0.6557 | 0.0085 | 15/15 |
| `bc_gradient_boosting` | BC | 0.6433 | 0.0121 | 15/15 |
| `bc_random_forest` | BC | 0.6326 | 0.0122 | 15/15 |
| `bc_logistic_regression` | BC | 0.6236 | 0.0096 | 15/15 |
| `bc_linear_svc` | BC | 0.6147 | 0.0118 | 15/15 |
| `df_naive_bayes` | DF | 0.5905 | 0.0093 | 15/15 |
| `bc_naive_bayes` | BC | 0.5535 | 0.0090 | 15/15 |
| `bc_decision_tree` | BC | 0.5475 | 0.0116 | 15/15 |

## Resultados dos ensembles

| Ensemble | N | Membros | Folds | Macro-F1 média | Macro-F1 dp | Accuracy média |
|---|---:|---|---:|---:|---:|---:|
| `voting_top3` | 3 | `df_gradient_boosting`, `df_random_forest`, `df_decision_tree` | 15/15 | 0.6941 | 0.0096 | 0.7080 |
| `voting_top5` | 5 | `df_gradient_boosting`, `df_random_forest`, `df_decision_tree`, `df_logistic_regression`, `df_linear_svc` | 15/15 | 0.6932 | 0.0076 | 0.7082 |
| `voting_top7` | 7 | `df_gradient_boosting`, `df_random_forest`, `df_decision_tree`, `df_logistic_regression`, `df_linear_svc`, `bc_gradient_boosting`, `bc_random_forest` | 15/15 | 0.6936 | 0.0085 | 0.7071 |

## Comparação: melhor modelo individual vs melhor ensemble

| Item | Macro-F1 |
|---|---:|
| Melhor modelo individual (`df_gradient_boosting`) | 0.6908 |
| Melhor ensemble (`voting_top3`) | 0.6941 |
| Delta (ensemble − individual) | +0.0033 |

## Artefatos

- `experiments/voting/<voting_id>/metrics_per_fold.json`
- `experiments/voting/<voting_id>/predictions_per_fold.jsonl`
- `experiments/voting/voting_summary.json`
- `documents/reports/results/phase_g_voting.md`
