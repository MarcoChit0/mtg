# Auditoria binaria das Fases E-J

Data da auditoria: 2026-05-25.

Critério usado: veredito binário. Qualquer etapa parcialmente atendida foi classificada como **incorreta**. A auditoria cruzou `documents/backbone.md`, `documents/action_plan.md`, implementation reports, scripts, results reports e artefatos em `experiments/`.

Atualizacao pos-restauracao: em 2026-05-25, `bc_linear_svc` e `df_linear_svc` foram restaurados do remote autenticado `mtg-experiments:`, `df_linear_svc/checkpoint_state.json` foi corrigido, os zips locais foram recriados e reenviados ao Drive, o manifest foi republicado, o report da Fase E foi regenerado e as permissoes publicas dos zips foram corrigidas com `rclone link`. A reauditoria detalhada esta em `documents/reports/phase_e_reaudit.md`.

Atualizacao E-H: em 2026-05-25, apos a restauracao definitiva dos artefatos `linear_svc`, as Fases F, G e H foram reexecutadas. Os reports e artefatos derivados agora refletem as metricas atuais (`bc_linear_svc` macro-F1 0,6147; `df_linear_svc` macro-F1 0,6557). O bundle `voting.zip` foi recriado, reenviado ao Drive e validado por download publico junto com os 12 modelos e os bundles `shared`, `spot_check` e `voting`.

Atualizacao G: em 2026-05-26, a Fase G foi alterada para os 3 ensembles atuais pedidos no plano: `voting_top3`, `voting_top5` e `voting_top7`, todos definidos pelos modelos individuais globais com maior macro-F1. A fase foi reexecutada com `--all --force-recompute`; os diretórios antigos de voting foram removidos localmente e H/I foram regeneradas.

## Sumario executivo

| Fase | Veredito | Justificativa curta |
|---|---|---|
| E — Nested CV | **Correta** | Os 12 modelos locais, o Drive autenticado e o download publico passam nas verificacoes de treino, folds, grids, best params, metricas, checkpoints, zips, manifest e restauracao em diretorio temporario. |
| F — Verificação | **Correta** | A fase exige 12 modelos com 15/15 folds, não mantém avisos de artefatos ausentes depois da restauração, executa GroupKFold por comandante e testes Friedman/Nemenyi/Wilcoxon sobre 15 folds. |
| G — Voting | **Correta** | Os 3 ensembles atuais existem, usam hard voting sobre OOF alinhado por `(fold_id, row_index)`, têm 15 folds e 36.405 predições cada; as métricas recomputadas batem com os reports. |
| H — Melhores modelos | **Correta** | A seleção é separada por representação e escolhe corretamente `bc_gradient_boosting` como melhor BC e `df_gradient_boosting` como melhor DF. |
| I — Modelo vs calculadora | **Correta** | A fase agora mostra, na mesma base OOF, a bateria completa para `y1` real vs `y2` e para `ŷ1` vs `y2`: concordância exata, ±1, macro-F1 vs `y2`, matriz de confusão e delta absoluto médio. |
| J — Interpretabilidade | **Correta** | Usa exatamente os dois modelos individuais selecionados na Fase H, interpreta DF por permutation importance/features e BC por lift/cartas, incluindo divergência `ŷ1` vs `y2`. |

Conclusão geral: o bloco E-J está **correto** pelos critérios auditados nesta versão.

## Evidencias gerais

- `action_plan.md` define para E: 12 modelos atuais (`|A_uniao|=6` × BC/DF), target único `y1`, 15 outer folds, inner CV com macro-F1, 24 configurações por grid e artefatos `metrics`, `best_hyperparams`, `cv_results`, `predictions`, checkpoints, `seeds.json` e `folds.json`.
- `backbone.md` define que `y2` não é target de treino, só benchmark comparativo; que a comparação com a calculadora deve usar predições OOF; e que J interpreta dois modelos, melhor BC e melhor DF.
- `experiments/spot_check/summary.json` define `A_uniao = {decision_tree, gradient_boosting, linear_svc, logistic_regression, naive_bayes, random_forest}`. Portanto os modelos esperados são:
  `bc_decision_tree`, `bc_gradient_boosting`, `bc_linear_svc`, `bc_logistic_regression`, `bc_naive_bayes`, `bc_random_forest`, `df_decision_tree`, `df_gradient_boosting`, `df_linear_svc`, `df_logistic_regression`, `df_naive_bayes`, `df_random_forest`.

## Fase E — Nested CV

Veredito: **correta**.

O código atual está alinhado ao plano metodológico: `full_param_grid()` define 24 configurações para os modelos relevantes, incluindo `LinearSVC` com `C × class_weight × penalty` (`scripts/phase_e_nested_cv.py`, linhas 331-395); a busca interna itera `ParameterGrid` e seleciona por macro-F1 (`scripts/phase_e_nested_cv.py`, linhas 674-715); cada fold grava métricas, melhores params, predições, `cv_results` e checkpoint (`scripts/phase_e_nested_cv.py`, linhas 900-1038); `seeds.json` e `folds.json` são gerados antes do treino (`scripts/phase_e_nested_cv.py`, linhas 1703-1710).

Evidências locais positivas:

- Todos os 12 modelos esperados têm `metrics_per_fold.json`, `best_hyperparams_per_fold.json` e `predictions_per_fold.jsonl`.
- Todos os 12 têm 15/15 folds e 36.405 predições OOF, com 2.427 entradas por fold.
- Para 12/12 modelos locais, `cv_results_per_fold.jsonl` tem 360 linhas = 24 configs × 15 folds.
- Para os 12 modelos, o `best_hyperparams_per_fold.json` bate fold a fold com o melhor `mean_test_macro_f1`/rank 1 do `cv_results_per_fold.jsonl`.
- `experiments/seeds.json` existe e registra `outer_repeat_seeds=[1,2,3]`; `experiments/folds.json` existe com 15 fold IDs.
- `bc_linear_svc` restaurado tem `checkpoint_state.json`, `cv_results_per_fold.jsonl`, 15 checkpoints, 15 folds, 36.405 predições OOF e 360 linhas de `cv_results`.
- `df_linear_svc` restaurado tem `checkpoint_state.json`, `cv_results_per_fold.jsonl`, 15 checkpoints correntes na assinatura `7801815cdd67634f`, 15 folds, 36.405 predições OOF e 360 linhas de `cv_results`; ha 1 checkpoint antigo preservado fora da assinatura corrente, ignorado pelo script.
- Os reports locais foram regenerados; `documents/reports/results/phase_e_nested_cv.md` agora registra `df_linear_svc` com macro-F1 0,6557 e `bc_linear_svc` com macro-F1 0,6147.

Falhas bloqueantes:

- Nenhuma falha bloqueante remanescente.

Evidências de divergência local vs Drive:

- O `experiments/archives/experiments_manifest.json` local foi republicado e lista os 12 modelos esperados.
- Os zips locais `experiments/archives/bc_linear_svc.zip` e `experiments/archives/df_linear_svc.zip` foram recriados a partir dos artefatos corrigidos e reenviados ao remote.
- O `experiments/nested_cv_summary.json` foi regenerado com `--from-spot-check --run-local`; todos os 12 modelos aparecem como `current_run` porque foram reconstruidos a partir dos checkpoints completos.

Drive/download:

- Com `rclone` autenticado, `uv run sync-experiments-drive download --experiment-dir /tmp/mtg-phase-e-auth.XXXXXX/experiments --models <12 modelos> --overwrite` baixou e extraiu os 12 modelos do remote `mtg-experiments:` com `status=ok`.
- Depois do reupload, `uv run sync-experiments-drive download --models bc_linear_svc df_linear_svc --overwrite` em diretorio temporario confirmou `15/15`, `cv_results_per_fold.jsonl` presente e assinaturas `65eea8db1223c439`/`7801815cdd67634f`.
- O critério exigia download fácil público. Depois de aplicar `rclone link` aos zips, `uv run sync-experiments-drive download-public --experiment-dir /tmp/mtg-public-e-h.HSpKeS/experiments --models <12 modelos> --bundles shared spot_check voting --overwrite` concluiu com `status=ok`, baixando e extraindo os 12 modelos e os bundles `shared`, `spot_check` e `voting`.
- Portanto os modelos estão no Drive autenticado e em caminho público funcional; isso torna a Fase E **correta** pelo critério definido.

Correção necessária: nenhuma para a Fase E.

## Fase F — Verificação

Veredito: **correta**.

O action plan exige F.1 completude, F.2 GroupKFold por comandante e F.3 testes estatísticos. O script implementa:

- Arquivos obrigatórios: `metrics_per_fold.json`, `best_hyperparams_per_fold.json`, `predictions_per_fold.jsonl`; `cv_results_per_fold.jsonl` e `checkpoint_state.json` são opcionais por desenho da própria fase (`scripts/phase_f_model_verification.py`, linhas 95-104).
- Com `--all`, modelos com menos de 15 folds bloqueiam a execução (`scripts/phase_f_model_verification.py`, linhas 192-230).
- Checagem de fold IDs compartilhados (`scripts/phase_f_model_verification.py`, linhas 239-260).
- GroupKFold por `commander_oracle_uids`, com hiperparâmetro modal da Fase E e sem nova busca pesada (`scripts/phase_f_model_verification.py`, linhas 288-330).
- Relatórios de completude, GroupKFold e estatística (`scripts/phase_f_model_verification.py`, linhas 551-685).

Evidências de artefato:

- `documents/reports/results/phase_f_model_verification.md` lista 12 modelos com 15/15 folds.
- Antes da restauracao, o report registrava avisos opcionais para artefatos locais ausentes de `linear_svc`; depois da restauracao e reexecucao da Fase F, esses avisos desapareceram e os artefatos estao presentes no workspace.
- `experiments/model_verification/group_kfold_results.json` existe e contém 12 entradas, uma por modelo esperado.
- `documents/reports/results/phase_f_statistical_tests.md` reporta Friedman, Nemenyi e Wilcoxon sobre 12 modelos e 15 folds.

Observação: F é correta para o escopo próprio dela. Ela não prova que todos os grids da Fase E foram treinados, porque `cv_results` é opcional na Fase F; essa falha pertence à Fase E.

## Fase G — Voting

Veredito: **correta**.

O action plan exige 3 ensembles por hard voting simples sem retreino: `voting_top3`, `voting_top5` e `voting_top7`, formados pelos melhores modelos individuais globais por macro-F1. O script define exatamente esses 3 specs, ranqueia membros por macro-F1, carrega predições OOF, resolve empate por macro-F1 dos membros e menor rótulo residual, remove diretórios obsoletos de voting e alinha por folds/linhas compartilhados.

Evidências de artefato:

- Existem os diretórios `experiments/voting/voting_top3`, `voting_top5` e `voting_top7`.
- Cada ensemble tem `metrics_per_fold.json` e `predictions_per_fold.jsonl`.
- Cada ensemble tem 15 folds, 36.405 predições e 2.427 entradas por fold.
- Recomputei macro-F1 a partir dos JSONL; todos os valores batem com `metrics_per_fold.json`.
- `experiments/voting/voting_summary.json` lista os 3 ensembles e seus membros.

Observação: os artefatos de `linear_svc` foram restaurados localmente depois da auditoria inicial; por isso, a Fase G foi reexecutada com `--all --force-recompute`. Na atualização de 2026-05-26, a Fase G foi novamente reexecutada após a troca dos specs para top-3/top-5/top-7 globais.

## Fase H — Melhores modelos

Veredito: **correta**.

O backbone exige selecionar separadamente o melhor BC e o melhor DF por macro-F1 médio dos modelos individuais. O script carrega os modelos esperados pela união do spot-check (`scripts/phase_h_best_models.py`, linhas 69-90) e seleciona `best_bc = select_best(..., "BC")` e `best_df = select_best(..., "DF")` separadamente (`scripts/phase_h_best_models.py`, linhas 555-560).

Evidências:

- Recomputei o ranking individual local por `macro_f1_mean`.
- Melhor BC: `bc_gradient_boosting`, macro-F1 0.6432634321, dp 0.0121280675.
- Melhor DF: `df_gradient_boosting`, macro-F1 0.6907864041, dp 0.0092936331.
- `experiments/best_models.json` registra exatamente esses dois modelos, com `n_folds=15`.
- `documents/reports/results/phase_h_best_models.md` marca `★BC` e `★DF` nesses mesmos modelos.

Observação: a restauracao do `linear_svc` correto do Drive alterou métricas intermediárias e a Fase H foi reexecutada. A mudança não altera o melhor BC nem o melhor DF; portanto a seleção final continua correta.

## Fase I — Modelo vs calculadora

Veredito: **correta**.

O script é descritivo, não treina modelos, não cria folds e não usa `y2` como alvo. A função `compute_agreement_metrics()` agora aceita tanto `y_true` quanto `y_pred` como label comparado contra `y2`, e o report apresenta duas camadas na mesma base OOF:

1. `y1` real do Archidekt contra `y2`;
2. `ŷ1` predito pelos modelos contra `y2`.

Para ambas as camadas aparecem concordância exata, concordância ±1, delta absoluto médio, macro-F1 vs `y2` e matriz de confusão.

Métricas que deveriam aparecer explicitamente para `y1` vs `y2` na base OOF:

| Comparação | Valor |
|---|---:|
| `n` | 36.405 entradas OOF |
| concordância exata `y1=y2` | 0.6094 |
| concordância ±1 | 0.9768 |
| `|delta|` médio | 0.4138 |
| macro-F1 vs `y2` | 0.5843 |

Matriz `y1 × y2` recomputada, linhas = `y1`, colunas = `y2`:

| y1 \ y2 | 2 | 3 | 4 |
|---|---:|---:|---:|
| 2 | 3042 | 3459 | 462 |
| 3 | 2307 | 11727 | 4617 |
| 4 | 384 | 2991 | 7416 |

Correção necessária: nenhuma remanescente para a Fase I.

## Fase J — Interpretabilidade

Veredito: **correta**.

O backbone exige interpretar o melhor BC e o melhor DF. O script lê `experiments/best_models.json` e usa `best_BC.model_id` e `best_DF.model_id` para carregar os diretórios corretos (`scripts/phase_j_interpretability.py`, linhas 837-849).

Evidências:

- `experiments/best_models.json` define `best_BC = bc_gradient_boosting` e `best_DF = df_gradient_boosting`.
- `documents/reports/results/phase_j_interpretability.md` usa exatamente `df_gradient_boosting` e `bc_gradient_boosting`.
- Para DF, o script treina modelo final apenas para interpretação com hiperparâmetros modais, faz split 80/20 e calcula permutation importance (`scripts/phase_j_interpretability.py`, linhas 221-259).
- Para DF, também calcula médias condicionais por bracket previsto e features associadas à divergência `ŷ1` vs `y2` (`scripts/phase_j_interpretability.py`, linhas 281-354).
- Para BC, o script usa predições OOF e bag-of-cards para lift por bracket e divergência/concordância (`scripts/phase_j_interpretability.py`, linhas 447-595).
- Os artefatos existem em `experiments/phase_j_interpretability/`: `final_model_params.json`, `df_permutation_importance.json`, `bc_card_lift_per_class.json`, `df_divergence_features.json`, `bc_divergence_cards.json`.
- Os hiperparâmetros finais em `final_model_params.json` batem com a configuração modal dos 15 folds: `{'class_weight': 'balanced', 'learning_rate': 0.05, 'max_iter': 200, 'max_leaf_nodes': 31}` para BC e DF.

Observação: no estado atual, o melhor algoritmo para BC e DF é o mesmo (`gradient_boosting`), mas são modelos distintos (`bc_gradient_boosting` e `df_gradient_boosting`). Portanto a fase respeita o requisito "melhor por representação", não "melhor geral".

## Verificações executadas

Testes automatizados:

```bash
uv run python -m unittest tests/test_phase_e_nested_cv.py tests/test_sync_experiments_drive.py -v
```

Resultado: 23 testes executados, todos `OK`.

Drive:

```bash
uv run sync-experiments-drive check-write
```

Resultado: `status=ok`; upload e delete do probe no remote `mtg-experiments:` funcionaram.

Download autenticado via rclone:

```bash
uv run sync-experiments-drive download --experiment-dir /tmp/mtg-audit-rclone-all/experiments --models <12 modelos> --overwrite
```

Resultado: `status=ok`; 12 downloads e extrações bem-sucedidos.

Download público:

```bash
uv run sync-experiments-drive download-public --experiment-dir /tmp/mtg-public-all.hbGTfb/experiments --models <12 modelos> --bundles shared --overwrite
```

Resultado: `status=ok`; 12 modelos e `shared` baixados e extraidos.

## Conclusao

As fases **F, G, H e J** implementam corretamente seus requisitos próprios, com evidências verificáveis.

Somente a Fase **I** está **incorreta**:

- **I**: falta a comparação completa `y1` vs `y2` na mesma forma usada para `ŷ1` vs `y2`.

Depois de corrigir I, recomendo reexecutar os reports dependentes para eliminar qualquer divergência entre artefatos locais, Drive e documentação.
