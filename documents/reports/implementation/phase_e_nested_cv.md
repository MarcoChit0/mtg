# Implementação — Fase E: Nested CV + Voting + Testes Estatísticos

> Implementation report. **Público**: colaborador novo ou agente LLM que vai mexer em nested CV, grids, voting, testes estatísticos ou na integração com o Google Drive. Resultados (métricas por modelo, métricas por ensemble, Friedman/Nemenyi/Wilcoxon) vivem em [../results/phase_e_nested_cv.md](../results/phase_e_nested_cv.md), [../results/phase_e_voting.md](../results/phase_e_voting.md) e [../results/phase_e_statistical_tests.md](../results/phase_e_statistical_tests.md).

## Objetivo

Treinar todos os modelos individuais selecionados na Fase D (`|union| × 2`, hoje 10 a 14) com nested cross-validation, computar ensembles por votação majoritária a partir das predições out-of-fold, rodar testes estatísticos pareados, e (se colaborador) publicar artefatos no Drive compartilhado para que outros colaboradores e usuários externos reproduzam.

## O que foi construído

| Componente | Arquivo | Responsabilidade |
|---|---|---|
| Driver principal | [scripts/phase_e_nested_cv.py](../../../scripts/phase_e_nested_cv.py) (~1800 linhas) | Nested CV, grid search com progresso, checkpoints, voting, testes estatísticos, uploads Drive |
| Integração Drive | [scripts/sync_experiments_drive.py](../../../scripts/sync_experiments_drive.py) | Upload por modelo, bundles (spot_check/voting/shared), publish manifest, download público |
| Driver de pipeline | [scripts/run_pipeline.py](../../../scripts/run_pipeline.py) | Compõe stages `train` (check-write → train → publish-manifest) com defaults razoáveis |
| Pré-processadores | [scripts/preprocessing.py](../../../scripts/preprocessing.py) | `DeckFeaturePreprocessor` e `BagOfCardsPreprocessor` usados como steps de `Pipeline` (ver Fase C) |

## Saídas locais geradas por rodada

| Caminho | Conteúdo |
|---|---|
| `experiments/seeds.json` | Random state principal + seeds dos 3 repeats + fórmulas derivadas |
| `experiments/folds.json` | Índices outer/inner por repeat (deterministicamente derivados de y + seeds) |
| `experiments/<modelo>/metrics_per_fold.json` | Métricas por fold + agregadas (mean/std) + matriz de confusão |
| `experiments/<modelo>/best_hyperparams_per_fold.json` | Vencedor da grid search inner em cada outer fold |
| `experiments/<modelo>/predictions_per_fold.jsonl` | OOF predictions por linha (consumido pelo voting + Fase G) |
| `experiments/<modelo>/cv_results_per_fold.jsonl` | Toda a grid search (todas as configurações × scores) |
| `experiments/<modelo>/checkpoint_state.json` | Estado de retomada |
| `experiments/<modelo>/checkpoints/<sig>/<fold>.json` | Checkpoint por outer fold; signature = sha256 da config |
| `experiments/voting/voting_<nome>/{metrics,predictions}_per_fold.{json,jsonl}` | 6 ensembles |
| `experiments/voting/voting_summary.json` | Resumo dos ensembles |
| `experiments/nested_cv_summary.json` | Sumário consolidado da rodada |
| `experiments/statistical_tests.json` | Friedman/Nemenyi/Wilcoxon pareado |
| `documents/reports/results/phase_e_nested_cv.md` | Auto-gerado: tabela de modelos |
| `documents/reports/results/phase_e_voting.md` | Auto-gerado: tabela de ensembles |
| `documents/reports/results/phase_e_statistical_tests.md` | Auto-gerado: ranks médios + significância |

## Como foi construído (decisões + porquês)

### Esquema de folds (StratifiedKFold 5 × 3 repeats)

```
outer_seed ∈ {1, 2, 3}
outer       = StratifiedKFold(n_splits=5, shuffle=True, random_state=outer_seed)
inner_seed  = outer_seed + 100
inner       = StratifiedKFold(n_splits=3, shuffle=True, random_state=inner_seed)
estimator   = random_state = base_random_state + outer_seed * 100 + outer_fold
```

15 outer evaluations por modelo. As mesmas fold ids são compartilhadas por todos os modelos → comparações pareadas (Wilcoxon, Friedman) são válidas. Folds são re-derivados a cada rodada a partir de `y`+seeds — não são lidos de `folds.json` em runtime (o arquivo é só audit). Isso garante que machine A e machine B produzem os mesmos folds dado o mesmo `deck_features.jsonl`.

### Grid search progresso-aware (não usa `GridSearchCV` do sklearn)

`sklearn.GridSearchCV` é prático mas não dá feedback de progresso por configuração, e não checkpointa. Para um grid de até 192 configs × 3 inner folds × outer fold, rodar horas sem feedback é frustrante. Solução: `inner_grid_search_with_progress()` em [phase_e_nested_cv.py](../../../scripts/phase_e_nested_cv.py) faz o loop manualmente:

```python
for config_index, params in enumerate(ParameterGrid(grid)):
    for inner_train, inner_valid in inner_cv.split(...):
        clone(pipeline).set_params(**params).fit(...).predict(...)
        # acumula scores, fit_times, score_times
    if config_index % update_every == 0:
        print_inner_grid_progress(...)
```

Mesma semântica do sklearn (refit no full train com melhor config), com barra de progresso por config.

### Grids limitados a 192 configs por algoritmo

Guarda-corpo de custo atualizado em 2026-05-20: 192 configurações por algoritmo é a ordem de grandeza máxima aceita para manter a nested CV viável. `full_param_grid(alg, rep)` em [phase_e_nested_cv.py](../../../scripts/phase_e_nested_cv.py):

| Algoritmo | Grid | Total |
|---|---|---:|
| DecisionTree | max_depth ∈ {None,5,10,20,40}, min_samples_leaf ∈ {1,2,5,10}, ccp_alpha ∈ {0,0.005}, criterion ∈ {gini,entropy}, class_weight ∈ {None,balanced} | 160 |
| RandomForest | n_estimators ∈ {100,250,500,1000}, max_depth ∈ {10,20,40,None}, max_features ∈ {sqrt,log2}, min_samples_leaf ∈ {1,2,4}, class_weight ∈ {None,balanced} | 192 |
| GradientBoosting | max_iter ∈ {100,200,300,500}, lr ∈ {0.01,0.05,0.1}, max_leaf_nodes ∈ {15,31,63}, l2 ∈ {0,0.1}, class_weight ∈ {None,balanced} | 144 |
| MultinomialNB | alpha ∈ 48 valores × fit_prior ∈ {True,False} | 96 |
| GaussianNB | var_smoothing ∈ 96 valores | 96 |
| LogReg | C ∈ 16 valores log-espaçados (1e-4 → 3e3) × class_weight ∈ {None, balanced} × l1_ratio ∈ {0, 0.5, 1} — estimador usa `penalty='elasticnet'` + `solver='saga'` | 96 |
| LinearSVC | C ∈ 24 valores log-espaçados (1e-4 → 5e3) × class_weight ∈ {None, balanced} × penalty ∈ {l1, l2} — estimador usa `dual='auto'` + `loss='squared_hinge'` | 96 |
| KNN | (fora da união, não é treinado) | — |

`MAX_GRID_CONFIGS = 192` é constante exportada; `test_all_grids_fit_within_max_configs` em [tests/test_phase_e_nested_cv.py](../../../tests/test_phase_e_nested_cv.py) faz o sanity-check no CI. Todos os grids dos 6 algoritmos da união caem em **[92, 192]** (floor garante exploração mínima, ceiling garante runtime).

### Auditoria contra a literatura (2026-05-20)

Cada grid foi revisado contra a referência canônica do algoritmo. Mudanças aplicadas:

| Algoritmo | Mudança | Referência |
|---|---|---|
| `DecisionTree` | `min_samples_split` → `ccp_alpha` (cost-complexity pruning) | Breiman/Hastie *ESL* §9.2; sklearn user guide §1.10.4 (pruning é o regularizador canônico do CART) |
| `HistGradientBoosting` | `max_depth` → `max_leaf_nodes` | LightGBM paper (Ke et al. 2017); sklearn user guide diz explicitamente "max_leaf_nodes is the main complexity parameter" |
| `LogisticRegression` | `penalty='elasticnet'` no estimador + `l1_ratio ∈ {0, 0.5, 1}` no grid | Zou & Hastie 2005 (ElasticNet domina L1 puro quando há features correlacionadas — relevante para BC com cartas de combo) |
| LR e LinearSVC | `fit_intercept` removido do grid | Hastie *ESL* §4.4 e LIBLINEAR (Fan et al. 2008) convergem em "intercept=True é a escolha universal" |
| Todos com suporte | `class_weight ∈ {None, balanced}` | Resposta direta ao imbalance de y1 (52% / 21% / 27%) com macro-F1 como métrica |

#### Bug histórico corrigido em 2026-05-20

A versão anterior da LR tinha `l1_ratio` no grid sem `penalty='elasticnet'` no estimador. Sklearn ignora silenciosamente `l1_ratio` quando `penalty != 'elasticnet'`, então das 144 configs originais apenas 48 eram distintas. O fix simultâneo (penalty='elasticnet' no estimador + remoção de `fit_intercept`) trouxe o grid para 96 configs **todas distintas**.

### Por que cap em 192 e não busca aleatória/halving

Discutimos os três (grid completo, RandomizedSearchCV, HalvingGridSearch). Grid completo dentro do cap é mais fácil de auditar (todas as configs documentadas, resultados em `cv_results_per_fold.jsonl`) e a professora preferiu reproducibilidade explícita. Halving/Random ficaram como fallback futuro se algum grid se mostrar inviável.

### `SparseToDenseTransformer` para `HistGradientBoosting` e `DecisionTree` em BC

`HistGradientBoostingClassifier` exige dense; `DecisionTreeClassifier` aceita esparso mas com performance degradada nessa dim. `pipeline_for()` insere um `SparseToDenseTransformer` entre `BagOfCardsPreprocessor` e o estimador nesses dois casos. Memória: BC com `bc_min_df=10` produz matriz ~12k × ~11k. Densificar usa ~1 GB — aceitável na máquina do projeto.

### Plano de modelos: `build_model_plan()` + `--from-spot-check`

Dois modos:

```python
if args.from_spot_check and args.model is None and args.feature is None:
    union = sorted(top5_DF ∪ top5_BC)  # lido de experiments/spot_check/summary.json
    plan = [(rep, alg) for rep in {"DF","BC"} for alg in union]
else:
    plan = [(rep, alg) for rep in args.representations for alg in args.algorithms]
```

**Sem `--from-spot-check`**: cartesiano direto, usado por testes e quando o usuário força um modelo específico.

**Com `--from-spot-check`** (default no `train` do `run_pipeline`): cada algoritmo da união é treinado em ambas as representações. Isso preserva a comparação BC vs DF justa por algoritmo — mesmo um algoritmo que só foi top-5 em uma das duas representações é treinado nas duas pra Fase F poder ranquear.

### Checkpoints por outer fold

Cada outer fold gera um arquivo `checkpoints/<sig>/<fold_id>.json` com metrics, best_params, predictions e cv_results. A `signature_id` é `sha256(config payload)[:16]` cobrindo grid + folds + parâmetros do estimador. Se você muda grid/seeds, signature muda, checkpoint antigo é ignorado → reexecução do zero. Crucial: previne usar checkpoints com grid inválido após mudança de design.

`--force-rerun` ignora checkpoints existentes mesmo com signature batendo (útil para auditar não-determinismo cross-machine).

### Voting (E.5) — hard vote determinístico

6 ensembles fixos em `VOTING_SPECS`:

```
voting_top3_BC   : 3 BC models
voting_top5_BC   : 5 BC models
voting_top3_DF   : 3 DF models
voting_top5_DF   : 5 DF models
voting_top3_BC_DF: 3 BC + 3 DF
voting_all       : todos os modelos individuais
```

`hard_vote(predictions)`: `Counter` → classe com `max(count)`; em empate, **menor classe vence** (`min(labels)`). Tie-break determinístico cross-machine, cross-thread. Empate ponderado por macro-F1 está documentado no [`backbone.md`](../../backbone.md) como ideal mas não implementado — exigiria persistir per-class F1 por membro, que não fazemos hoje. O comportamento atual é uma simplificação consciente.

Voting **não retrina**: usa as predictions_per_fold.jsonl persistidas. Aposentar voting → re-rodar Phase E → recomputar voting é uma operação só do final do script (`run_voting_ensembles()`).

### Testes estatísticos

- **Friedman**: aplicado sobre a matriz `n_folds × n_models` de macro-F1. H0 = todos os modelos têm a mesma distribuição de rank. p < 0,05 indica que pelo menos um difere.
- **Nemenyi**: pós-Friedman, computa a diferença crítica `q_alpha * sqrt(k(k+1)/(6n))`. Pares cujo diff de rank médio supera CD são significativamente diferentes em α=0,05.
- **Wilcoxon signed-rank pareado**: por par, compara as macro-F1 dos 15 folds (pareadas porque os folds são os mesmos). p-valores não corrigidos para múltiplas comparações — a interpretação é exploratória.

Requer ≥ 2 modelos e ≥ 3 folds usáveis. Se faltar, `status: "insufficient_data"` e o report fala.

### Integração Drive (colaboradores)

Quando `train` roda sem `--run-local`:

1. **Pre-flight**: `check_drive_write` no início falha cedo se o colaborador não tem permissão.
2. **Upload por modelo**: ao terminar cada modelo, `enqueue_drive_upload()` submete pra `ThreadPoolExecutor(max_workers=1)` — uploads acontecem em paralelo com o próximo treino, mas serializados entre si (evita rate limit no Drive).
3. **Upload de bundles**: ao final, `enqueue_bundle_drive_upload()` para `voting` e `shared` (= seeds.json + folds.json).
4. **Publish manifest**: `run_pipeline` adiciona uma stage final que detecta bundles locais e re-publica `experiments_manifest.json` (schema v2).

Falha de upload **não invalida** o run: `collect_drive_uploads()` registra o erro em `summary["problems"]` mas o run termina com `status: "ok"` e métricas locais válidas.

### Reprodutibilidade cross-machine

Tudo que afeta resultados é seed-derivado:

- `train_test_split` no Phase D usa `random_state=seed` (1..5).
- Phase E `StratifiedKFold` usa `random_state=outer_seed` ou `outer_seed+100`.
- Estimadores recebem `random_state = base + outer*100 + fold`.
- Voting tie-break usa a macro-F1 média dos membros que votaram em cada classe, com menor classe como fallback determinístico.

Dado mesmo `deck_features.jsonl` + mesmas seeds + mesmas versões de sklearn (pinadas via `uv.lock`), duas máquinas produzem resultados byte-idênticos. Único caveat: diferenças de BLAS (Accelerate macOS vs MKL Linux) podem causar epsilons em `1e-15` — não muda o ranking macro mas pode flutuar a 5ª casa decimal.

## Pontos de extensão / armadilhas

- **Adicionar algoritmo**: atualizar `SELECTED_ALGORITHMS`, `estimator_for`, `pipeline_for`, `needs_df_scaling`, `full_param_grid`. Adicionar test em `test_all_grids_fit_within_max_configs` (passa automaticamente se o grid couber em 192). Atualizar também `ALGORITHMS` em Phase D pra que apareça no spot-check.
- **Mudar grids**: vai invalidar checkpoints antigos (signature muda). Considere isso no orçamento de re-run.
- **Mudar tie-break do voting**: requer recálculo dos arquivos de voting, mas não retreina modelos individuais.
- **NÃO mover voting pra antes de todos os modelos terminarem**: voting requer OOF predictions completas. Se algum modelo está em retomada, voting não roda corretamente — `select_voting_members` filtra modelos sem aggregate.
- **NÃO subir voting/shared antes do manifest**: a ordem é: modelos → voting/shared → publish-manifest. O `lsjson` na publicação varre tudo no remote — se você inverte, modelos novos podem ser referenciados pelo manifest velho.
- **NÃO trocar `MAX_GRID_CONFIGS` sem rever cada grid**: `test_all_grids_fit_within_max_configs` ainda passa mas você pode estar regredindo na variância de hiperparâmetros explorados.
- **Cuidado com `--max-grid-values`**: corta cada hiperparâmetro pros primeiros N valores. Útil pra smoke test (`--max-grid-values 1`); fatal pra rodada de produção. Tests usam isso explicitamente.

## Problemas encontrados e correções

| Problema | Diagnóstico | Correção |
|---|---|---|
| RF grid original com 864 configs (4×4×2×3×3×3×1) | Inviável dentro de 192; inflava runtime sem ganho proporcional | Reduzido para 192 configs (n_estimators × max_depth × max_features × min_samples_leaf × class_weight); `bootstrap=True` e `criterion=gini` fixos |
| GridSearchCV sem feedback de progresso | Frustrante em runs de horas | Loop manual com `print_inner_grid_progress` por config |
| Voting `voting_all10` (nome com `10`) | Misnomer quando a união tem 6 ou 7 algoritmos (= 12 ou 14 modelos) | Renomeado para `voting_all` (covers all individual models present) |
| Checkpoints antigos com grid velho ainda eram lidos | Resultados misturavam grids | `signature_id = sha256(grid + folds + params)`; checkpoint só é restaurado se signature bater |
| `HistGradientBoosting` em CSR esparso | API não aceita | `SparseToDenseTransformer` antes do clf |
| Upload Drive falhando em meio do run | Frustrava perder horas de treino | Upload em ThreadPoolExecutor; falhas registradas como problems mas run continua OK |
| Tests com `--algorithms naive_bayes --representations DF` | Não passam pelo `--from-spot-check` flow | `build_model_plan` cai no caminho cartesiano quando `--from-spot-check` não está setado |
| `MODEL_ID_RE` rejeitava nomes de bundle com maiúscula (`voting_top3_BC`) | Tentar fazer upload-bundle desses nomes quebraria | Bundles seguem nomes lowercase (`voting`, `spot_check`, `shared`); voting_<nome>_BC vive **dentro** do bundle voting.zip |
