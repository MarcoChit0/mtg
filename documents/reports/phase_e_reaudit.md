# Reauditoria da Fase E

Data: 2026-05-25.

Veredito binario: **correta**.

Motivo do veredito: todas as verificacoes de treino, folds, grids, melhores hiperparametros, predicoes, metricas, checkpoints, reports locais, zips locais, manifest, Drive autenticado e download publico passaram. O problema remanescente era permissao publica nos zips do Drive; ele foi corrigido aplicando `rclone link` a todos os zips referenciados pelo manifest.

## Passo a passo

### 1. Requisitos oficiais

Fontes relidas:

- `documents/backbone.md`
- `documents/action_plan.md`
- `documents/reports/implementation/phase_e_nested_cv.md`
- `documents/reports/results/phase_e_nested_cv.md`

Requisitos aplicaveis:

- A Fase D define `A_uniao` como a uniao dos top-5 por representacao.
- A Fase E deve treinar cada algoritmo de `A_uniao` em **BC** e **DF**.
- A selecao atual tem `|A_uniao|=6`, portanto sao esperados **12 modelos**.
- Alvo unico: `y1`; `y2` nao entra no treino.
- Outer CV: 5 folds x 3 repeats = **15 folds por modelo**.
- Inner CV: 3 folds, otimizando macro-F1.
- Grid atual: **24 configuracoes por algoritmo/representacao**.
- Saidas esperadas por modelo: `metrics_per_fold.json`, `best_hyperparams_per_fold.json`, `predictions_per_fold.jsonl`, `cv_results_per_fold.jsonl`, `checkpoint_state.json` e checkpoints por fold.
- `experiments/seeds.json` e `experiments/folds.json` devem ser compartilhados.
- Os modelos devem estar no Drive e ser faceis de baixar.

Conclusao: requisitos claros e rastreaveis.

### 2. Modelos esperados

`experiments/spot_check/summary.json` registra:

```text
A_uniao = decision_tree, gradient_boosting, linear_svc, logistic_regression, naive_bayes, random_forest
```

Modelos esperados:

```text
df_decision_tree
df_gradient_boosting
df_linear_svc
df_logistic_regression
df_naive_bayes
df_random_forest
bc_decision_tree
bc_gradient_boosting
bc_linear_svc
bc_logistic_regression
bc_naive_bayes
bc_random_forest
```

Conclusao: os 12 modelos esperados existem localmente.

### 3. Implementacao

`scripts/phase_e_nested_cv.py` foi relido. A implementacao:

- monta o plano a partir do spot-check quando `--from-spot-check` e usado;
- treina cada algoritmo em BC e DF;
- gera folds outer compartilhados;
- usa `StratifiedKFold` externo e interno;
- calcula grids por `full_param_grid()`;
- grava `cv_results_per_fold.jsonl`, melhores parametros, metricas, predicoes e checkpoints;
- inclui `LinearSVC` com `C x class_weight x penalty`, totalizando 24 configuracoes;
- faz upload por modelo e publica manifest quando executado sem `--run-local`.

Durante a reauditoria, corrigi a geracao do report para listar os algoritmos efetivamente presentes em `model_plan`; antes, uma regeneracao com `--from-spot-check` ainda mostrava `knn` na configuracao textual, embora `knn` nao estivesse nos 12 resultados.

Conclusao: implementacao correta para o escopo da Fase E.

### 4. Artefatos locais por modelo

Auditoria programatica sobre os 12 modelos:

| Checagem | Resultado |
|---|---:|
| modelos esperados presentes | 12/12 |
| modelos com arquivos obrigatorios | 12/12 |
| folds por modelo | 15/15 |
| linhas OOF por modelo | 36.405 |
| linhas de `cv_results` por modelo | 360 |
| configuracoes por fold | 24 |
| `best_hyperparams` vs melhor `mean_test_macro_f1`/rank 1 | 0 divergencias |
| metricas recomputadas a partir de predicoes | 0 divergencias |
| alinhamento OOF por `(fold_id, row_index, snapshot_id)` entre modelos | correto |
| checkpoint dir corrente com 15 arquivos | 12/12 |

Metricas agregadas atuais:

| Modelo | Macro-F1 media | Macro-F1 dp |
|---|---:|---:|
| df_decision_tree | 0.6726523425 | 0.0100210075 |
| df_gradient_boosting | 0.6907864041 | 0.0092936331 |
| df_linear_svc | 0.6556936971 | 0.0084520356 |
| df_logistic_regression | 0.6706988772 | 0.0110270566 |
| df_naive_bayes | 0.5904702793 | 0.0093063880 |
| df_random_forest | 0.6732750782 | 0.0075889324 |
| bc_decision_tree | 0.5475265389 | 0.0116138944 |
| bc_gradient_boosting | 0.6432634321 | 0.0121280675 |
| bc_linear_svc | 0.6146700144 | 0.0118128465 |
| bc_logistic_regression | 0.6235789885 | 0.0096344092 |
| bc_naive_bayes | 0.5535185580 | 0.0089910749 |
| bc_random_forest | 0.6325801512 | 0.0122486544 |

Conclusao: os artefatos locais de treino da Fase E estao corretos.

### 5. `linear_svc`

Problemas corrigidos nesta reauditoria:

- `bc_linear_svc` e `df_linear_svc` foram restaurados do Drive autenticado.
- `df_linear_svc/checkpoint_state.json` tinha marcadores de conflito; foi reconstituido para a assinatura correta `7801815cdd67634f`.
- Os arquivos texto restaurados de `linear_svc` foram normalizados para LF.
- `bc_linear_svc.zip` e `df_linear_svc.zip` foram recriados a partir dos artefatos locais corrigidos.
- Os dois zips foram reenviados para `mtg-experiments:`.
- O manifest foi republicado.

Validacao dos zips locais:

```text
bc_linear_svc.zip 15/15 signature=65eea8db1223c439 cv_results=true
df_linear_svc.zip 15/15 signature=7801815cdd67634f cv_results=true
```

Conclusao: `linear_svc` local, zip local e Drive autenticado estao corrigidos.

### 6. Reports locais

`uv run phase-e-nested-cv --from-spot-check --run-local --quiet-progress` foi executado para regenerar:

- `experiments/nested_cv_summary.json`
- `documents/reports/results/phase_e_nested_cv.md`

O report agora lista exatamente:

```text
decision_tree, gradient_boosting, linear_svc, logistic_regression, naive_bayes, random_forest
```

e reflete as metricas restauradas de `linear_svc`:

```text
df_linear_svc macro-F1 = 0.6557
bc_linear_svc macro-F1 = 0.6147
```

Conclusao: reports locais da Fase E estao coerentes com os artefatos atuais.

### 7. Drive e download

Drive autenticado:

- `uv run sync-experiments-drive list` lista os 12 zips esperados no remote `mtg-experiments:`.
- `experiments/archives/experiments_manifest.json` schema v2 lista os 12 modelos esperados.
- Download autenticado dos 12 modelos em diretorio temporario concluiu com `status=ok`.
- Download autenticado de `bc_linear_svc` e `df_linear_svc` depois do reupload confirmou `15/15`, `cv_results_per_fold.jsonl` presente e assinaturas corretas.

Download publico:

```bash
uv run sync-experiments-drive download-public --experiment-dir <tmp>/experiments --models bc_linear_svc --bundles shared --overwrite
```

Resultado depois da correcao de permissao: `status=ok`, com download e extracao de `bc_linear_svc.zip` e `shared.zip` em diretorio temporario.

Prova completa:

```bash
uv run sync-experiments-drive download-public --experiment-dir /tmp/mtg-public-all.hbGTfb/experiments --models df_decision_tree df_gradient_boosting df_linear_svc df_logistic_regression df_naive_bayes df_random_forest bc_decision_tree bc_gradient_boosting bc_linear_svc bc_logistic_regression bc_naive_bayes bc_random_forest --bundles shared --overwrite
```

Resultado: `status=ok`; 12 modelos e o bundle `shared` baixados e extraidos em diretorio temporario.

Conclusao: Drive autenticado correto; download publico correto.

### 8. Testes

Comandos executados:

```bash
uv run python -m unittest tests/test_phase_e_nested_cv.py tests/test_sync_experiments_drive.py -v
```

Resultado:

```text
Ran 23 tests in 7.116s
OK
```

## Conclusao

A Fase E esta **correta**:

- 12/12 modelos esperados existem;
- todos tem 15 folds;
- todos tem 24 configuracoes por fold;
- melhores hiperparametros batem com `cv_results`;
- metricas batem com predicoes OOF;
- folds/seeds sao compartilhados;
- reports locais foram regenerados;
- zips locais e Drive autenticado foram corrigidos.
- download publico dos 12 modelos + `shared` funciona em diretorio temporario sem `rclone` autenticado.
