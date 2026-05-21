# Nested CV — Fase E

## Objetivo

Treinar os modelos individuais (10 a 14, cada algoritmo da união `A_DF ∪ A_BC` em ambas as representações), sempre prevendo `y1`, com nested cross-validation sem vazamento entre folds.

## Configuração

- Representações: DF, BC
- Algoritmos: naive_bayes
- Outer CV: 5 folds × repeats `1, 2, 3`
- Inner CV: 3 folds
- `bc_min_df`: 10
- `use_tfidf`: False
- Linhas modeláveis: 12135

## Resultados

| Modelo | Macro-F1 média | Macro-F1 dp | Accuracy média | Precision macro média | Recall macro média |
|---|---:|---:|---:|---:|---:|
| df_gradient_boosting | 0.6901 | 0.0081 | 0.7129 | 0.7178 | 0.6776 |
| df_linear_svc | 0.6566 | 0.0086 | 0.6599 | 0.6471 | 0.6821 |
| df_logistic_regression | 0.6710 | 0.0102 | 0.6946 | 0.6955 | 0.6573 |
| df_naive_bayes | 0.5905 | 0.0093 | 0.5874 | 0.5950 | 0.6389 |
| df_random_forest | 0.6618 | 0.0113 | 0.7042 | 0.7185 | 0.6369 |
| bc_gradient_boosting | 0.6257 | 0.0113 | 0.6610 | 0.6567 | 0.6100 |
| bc_linear_svc | 0.5927 | 0.0090 | 0.6131 | 0.5902 | 0.5956 |
| bc_logistic_regression | 0.6035 | 0.0116 | 0.6131 | 0.5964 | 0.6197 |
| bc_naive_bayes | 0.5535 | 0.0090 | 0.5636 | 0.5456 | 0.5687 |
| bc_random_forest | 0.5221 | 0.0128 | 0.6361 | 0.6805 | 0.5122 |

## Testes Estatísticos

- Friedman: statistic=133.1527, p=0.000000.
- Nemenyi: diferença crítica=3.4976 para alpha=0.05.

## Artefatos

- `experiments/seeds.json`
- `experiments/folds.json`
- `experiments/nested_cv_summary.json`
- `experiments/<representação>_<algoritmo>/metrics_per_fold.json`
- `experiments/<representação>_<algoritmo>/best_hyperparams_per_fold.json`
- `experiments/<representação>_<algoritmo>/cv_results_per_fold.jsonl`
- `experiments/<representação>_<algoritmo>/predictions_per_fold.jsonl`
- `experiments/<representação>_<algoritmo>/checkpoint_state.json`
- `experiments/<representação>_<algoritmo>/checkpoints/<assinatura>/<outer_fold>.json`
- `experiments/archives/<representação>_<algoritmo>.zip` quando upload via Drive estiver habilitado
- `documents/reports/results/phase_e_nested_cv.md`
- `documents/reports/results/phase_e_statistical_tests.md`

## Google Drive

- `df_naive_bayes`: ok
- `bc_naive_bayes`: ok
- `_geral_`: ok

## Problemas Encontrados

- Nenhum problema operacional registrado nesta rodada.
