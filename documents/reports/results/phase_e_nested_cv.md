# Nested CV — Fase E

## Objetivo

Treinar os modelos individuais definidos pela união `A_DF ∪ A_BC`, sempre prevendo `y1`, com nested cross-validation sem vazamento entre folds.

> Observação: este report registra uma rodada anterior com 10 modelos. O spot-check atual seleciona 6 algoritmos na união, portanto a rodada completa atual da Fase E precisa produzir 12 modelos, adicionando `df_decision_tree` e `bc_decision_tree`.

## Configuração

- Representações: DF, BC
- Algoritmos: gradient_boosting, logistic_regression, random_forest, linear_svc, naive_bayes
- Outer CV: 5 folds × repeats `1, 2, 3`
- Inner CV: 3 folds
- `bc_min_df`: 10
- `use_tfidf`: False
- Linhas modeláveis: 12135

## Resultados

| Modelo | Macro-F1 média | Macro-F1 dp | Accuracy média | Precision macro média | Recall macro média |
|---|---:|---:|---:|---:|---:|
| df_gradient_boosting | 0.6901 | 0.0081 | 0.7129 | 0.7178 | 0.6776 |
| df_logistic_regression | 0.6679 | 0.0105 | 0.6905 | 0.6897 | 0.6556 |
| df_random_forest | 0.6618 | 0.0113 | 0.7042 | 0.7185 | 0.6369 |
| df_linear_svc | 0.6566 | 0.0086 | 0.6599 | 0.6471 | 0.6821 |
| df_naive_bayes | 0.5779 | 0.0086 | 0.5749 | 0.5856 | 0.6273 |
| bc_gradient_boosting | 0.6257 | 0.0113 | 0.6610 | 0.6567 | 0.6100 |
| bc_logistic_regression | 0.6035 | 0.0116 | 0.6131 | 0.5964 | 0.6197 |
| bc_random_forest | 0.5221 | 0.0128 | 0.6361 | 0.6805 | 0.5122 |
| bc_linear_svc | 0.5927 | 0.0090 | 0.6131 | 0.5902 | 0.5956 |
| bc_naive_bayes | 0.5544 | 0.0094 | 0.5642 | 0.5464 | 0.5695 |

## Testes Estatísticos

- Friedman: statistic=132.9782, p=0.000000.
- Nemenyi: diferença crítica=3.4976 para alpha=0.05.

## Artefatos

- `experiments/seeds.json`
- `experiments/folds.json`
- `experiments/nested_cv_summary.json`
- `experiments/<representação>_<algoritmo>/metrics_per_fold.json`
- `experiments/<representação>_<algoritmo>/best_hyperparams_per_fold.json`
- `experiments/<representação>_<algoritmo>/predictions_per_fold.jsonl`
- `experiments/<representação>_<algoritmo>/cv_results_per_fold.jsonl`
- `experiments/<representação>_<algoritmo>/checkpoint_state.json`
- `experiments/<representação>_<algoritmo>/checkpoints/<assinatura>/<outer_fold>.json`
- `experiments/archives/<representação>_<algoritmo>.zip` quando upload via Drive estiver habilitado
- `documents/reports/statistical_tests.md`

## Problemas Encontrados

- Nenhum problema operacional registrado nesta rodada.
