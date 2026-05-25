# Nested CV — Fase E

## Objetivo

Treinar os modelos individuais (10 a 14, cada algoritmo da união `A_DF ∪ A_BC` em ambas as representações), sempre prevendo `y1`, com nested cross-validation sem vazamento entre folds.

## Configuração

- Representações: DF, BC
- Algoritmos: decision_tree, gradient_boosting, linear_svc, logistic_regression, naive_bayes, random_forest
- Outer CV: 5 folds × repeats `1, 2, 3`
- Inner CV: 3 folds
- `bc_min_df`: 10
- `use_tfidf`: False
- Linhas modeláveis: 12135

## Resultados

| Modelo | Macro-F1 média | Macro-F1 dp | Accuracy média | Precision macro média | Recall macro média |
|---|---:|---:|---:|---:|---:|
| df_decision_tree | 0.6727 | 0.0100 | 0.6876 | 0.7187 | 0.6811 |
| df_gradient_boosting | 0.6908 | 0.0093 | 0.6978 | 0.6899 | 0.7092 |
| df_linear_svc | 0.6557 | 0.0085 | 0.6584 | 0.6461 | 0.6825 |
| df_logistic_regression | 0.6707 | 0.0110 | 0.6944 | 0.6952 | 0.6569 |
| df_naive_bayes | 0.5905 | 0.0093 | 0.5874 | 0.5950 | 0.6389 |
| df_random_forest | 0.6733 | 0.0076 | 0.7034 | 0.7108 | 0.6541 |
| bc_decision_tree | 0.5475 | 0.0116 | 0.5540 | 0.5416 | 0.5653 |
| bc_gradient_boosting | 0.6433 | 0.0121 | 0.6442 | 0.6343 | 0.6759 |
| bc_linear_svc | 0.6147 | 0.0118 | 0.6281 | 0.6088 | 0.6231 |
| bc_logistic_regression | 0.6236 | 0.0096 | 0.6212 | 0.6197 | 0.6728 |
| bc_naive_bayes | 0.5535 | 0.0090 | 0.5636 | 0.5456 | 0.5687 |
| bc_random_forest | 0.6326 | 0.0122 | 0.6534 | 0.6424 | 0.6262 |

## Testes Estatísticos

- Friedman: statistic=158.8359, p=0.000000.
- Nemenyi: diferença crítica=4.3025 para alpha=0.05.

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

## Google Drive

- `_geral_`: skipped_run_local

## Problemas Encontrados

- Nenhum problema operacional registrado nesta rodada.
