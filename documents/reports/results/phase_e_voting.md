# Ensembles por votação — Fase E.5

Hard voting majoritário a partir das predições out-of-fold dos modelos individuais. Sem retreino. Empates são resolvidos pela maior macro-F1 média dos membros que votaram em cada classe; empate residual usa o menor rótulo numérico para manter reprodutibilidade.

## Ensembles

| Ensemble | Status | n_membros | Membros | Macro-F1 média | Macro-F1 dp | Accuracy média | Precision macro | Recall macro |
|---|---|---:|---|---:|---:|---:|---:|---:|

## Modelos individuais (referência)

| Modelo | Macro-F1 média | Macro-F1 dp |
|---|---:|---:|
| `df_random_forest` | 0.6838 | 0.0102 |
| `bc_random_forest` | 0.6343 | 0.0124 |
