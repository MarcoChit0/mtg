# Implementação — Fase E: Nested CV

> Implementation report. **Público**: colaborador novo ou agente LLM que vai mexer em nested CV, grids, checkpoints ou integração com o Google Drive. Resultados da implementação atual vivem em [../results/phase_e_nested_cv.md](../results/phase_e_nested_cv.md) e [../results/phase_e_statistical_tests.md](../results/phase_e_statistical_tests.md). A separação conceitual posterior em Fase F (verificação) e Fase G (voting) está documentada no [action_plan.md](../../action_plan.md), mas não foi implementada neste momento.

## Objetivo

Fase E treina todos os modelos individuais selecionados na Fase D (`|union| × 2`, hoje 10 a 14) com nested cross-validation. Ela publica artefatos no Drive compartilhado quando o colaborador não usa `--run-local`.

## O que foi construído

| Componente | Arquivo | Responsabilidade |
|---|---|---|
| Driver Fase E | [scripts/phase_e_nested_cv.py](../../../scripts/phase_e_nested_cv.py) | Nested CV, grid search com progresso, checkpoints, testes estatísticos, uploads Drive por modelo |
| Integração Drive | [scripts/sync_experiments_drive.py](../../../scripts/sync_experiments_drive.py) | Upload por modelo, bundles (spot_check/voting/shared), publish manifest, download público |
| Driver de pipeline | [scripts/run_pipeline.py](../../../scripts/run_pipeline.py) | Compõe stages `train` (check-write → train → publish-manifest) |
| Pré-processadores | [scripts/preprocessing.py](../../../scripts/preprocessing.py) | `DeckFeaturePreprocessor` e `BagOfCardsPreprocessor` usados como steps de `Pipeline` (ver Fase C) |

## Saídas locais geradas por rodada

| Caminho | Conteúdo |
|---|---|
| `experiments/seeds.json` | Random state principal + seeds dos 3 repeats + fórmulas derivadas |
| `experiments/folds.json` | Índices outer/inner por repeat (deterministicamente derivados de y + seeds) |
| `experiments/<modelo>/metrics_per_fold.json` | Métricas por fold + agregadas (mean/std) + matriz de confusão |
| `experiments/<modelo>/best_hyperparams_per_fold.json` | Vencedor da grid search inner em cada outer fold |
| `experiments/<modelo>/predictions_per_fold.jsonl` | OOF predictions por linha (consumido pelas fases posteriores) |
| `experiments/<modelo>/cv_results_per_fold.jsonl` | Toda a grid search (todas as configurações × scores) |
| `experiments/<modelo>/checkpoint_state.json` | Estado de retomada |
| `experiments/<modelo>/checkpoints/<sig>/<fold>.json` | Checkpoint por outer fold; signature = sha256 da config |
| `experiments/nested_cv_summary.json` | Sumário consolidado da rodada |
| `experiments/statistical_tests.json` | Friedman/Nemenyi/Wilcoxon pareado |
| `documents/reports/results/phase_e_nested_cv.md` | Auto-gerado: tabela de modelos |
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

`sklearn.GridSearchCV` é prático mas não dá feedback de progresso por configuração, e não checkpointa. Mesmo com grids compactos, cada configuração roda 3 inner folds dentro de cada outer fold, então ficar sem feedback é ruim. Solução: `inner_grid_search_with_progress()` em [phase_e_nested_cv.py](../../../scripts/phase_e_nested_cv.py) faz o loop manualmente:

```python
for config_index, params in enumerate(ParameterGrid(grid)):
    for inner_train, inner_valid in inner_cv.split(...):
        clone(pipeline).set_params(**params).fit(...).predict(...)
        # acumula scores, fit_times, score_times
    if config_index % update_every == 0:
        print_inner_grid_progress(...)
```

Mesma semântica do sklearn (refit no full train com melhor config), com barra de progresso por config.

### Grids compactados para 24 configs por algoritmo

Guarda-corpo de custo atualizado em 2026-05-21: a execução real mostrou que os grids de 72-192 configs ainda são caros demais, principalmente em BC. `full_param_grid(alg, rep)` em [phase_e_nested_cv.py](../../../scripts/phase_e_nested_cv.py) agora usa **24 configurações por algoritmo**, preservando os knobs mais relevantes:

| Algoritmo | Grid | Total |
|---|---|---:|
| DecisionTree | max_depth ∈ {None,10,20}, min_samples_leaf ∈ {1,5}, ccp_alpha ∈ {0,0.005}, class_weight ∈ {None,balanced} | 24 |
| RandomForest | n_estimators ∈ {100,250,500}, max_features ∈ {sqrt,log2}, min_samples_leaf ∈ {1,2}, class_weight ∈ {None,balanced} | 24 |
| GradientBoosting | max_iter ∈ {200,500}, lr ∈ {0.05,0.1,0.2}, max_leaf_nodes ∈ {15,31}, class_weight ∈ {None,balanced} | 24 |
| MultinomialNB | alpha ∈ {1e-3, 1e-2, 0.05, 0.1, 0.5, 1, 2, 5, 10, 25, 50, 100} × fit_prior ∈ {True,False} | 24 |
| GaussianNB | var_smoothing ∈ 24 valores log-espaçados (1e-12 → 1e-3) | 24 |
| LogReg | C ∈ {0.001, 0.1, 1, 100} × class_weight ∈ {None, balanced} × l1_ratio ∈ {0, 0.5, 1} — estimador usa `solver='saga'`; em sklearn <1.8 também define `penalty='elasticnet'` para compatibilidade | 24 |
| LinearSVC | C ∈ {0.001, 0.01, 0.1, 1, 10, 100} × class_weight ∈ {None, balanced} × penalty ∈ {l1, l2} — estimador usa `dual='auto'` + `loss='squared_hinge'` | 24 |
| KNN | n_neighbors ∈ {3,5,7,11,19,31}, weights ∈ {uniform,distance}, p ∈ {1,2} | 24 |

`MAX_GRID_CONFIGS = 24` é constante exportada; `test_all_grids_fit_within_max_configs` em [tests/test_phase_e_nested_cv.py](../../../tests/test_phase_e_nested_cv.py) faz o sanity-check no CI.

### Auditoria contra a literatura (2026-05-20)

Cada grid foi revisado contra a referência canônica do algoritmo. Mudanças aplicadas:

| Algoritmo | Mudança | Referência |
|---|---|---|
| `DecisionTree` | `min_samples_split` → `ccp_alpha` (cost-complexity pruning) | Breiman/Hastie *ESL* §9.2; sklearn user guide §1.10.4 (pruning é o regularizador canônico do CART) |
| `HistGradientBoosting` | `max_depth` → `max_leaf_nodes` | LightGBM paper (Ke et al. 2017); sklearn user guide diz explicitamente "max_leaf_nodes is the main complexity parameter" |
| `LogisticRegression` | `l1_ratio ∈ {0, 0.5, 1}` no grid (`penalty='elasticnet'` só em sklearn <1.8) | Zou & Hastie 2005 (ElasticNet domina L1 puro quando há features correlacionadas — relevante para BC com cartas de combo) |
| LR e LinearSVC | `fit_intercept` removido do grid | Hastie *ESL* §4.4 e LIBLINEAR (Fan et al. 2008) convergem em "intercept=True é a escolha universal" |
| Todos com suporte | `class_weight ∈ {None, balanced}` | Resposta direta ao imbalance de y1 (52% / 21% / 27%) com macro-F1 como métrica |

#### Bug histórico corrigido em 2026-05-20

Uma versão histórica da LR tinha `l1_ratio` no grid sem ativar ElasticNet no estimador em versões antigas do sklearn. Nessas versões, sklearn ignora silenciosamente `l1_ratio` quando `penalty != 'elasticnet'`. O fix atual mantém compatibilidade: em sklearn 1.8+ o script deixa `penalty` no default e usa `l1_ratio` diretamente para evitar `FutureWarning`; em versões antigas define `penalty='elasticnet'`.

#### Re-auditoria sob o teto de 24 configs (2026-05-21)

Quando o budget caiu para `MAX_GRID_CONFIGS = 24` (BC inviável com grids maiores), revisitamos cada grid contra a literatura:

| Algoritmo | Mudança | Justificativa |
|---|---|---|
| `LogisticRegression` | C `{0.01, 0.1, 1, 10}` → `{0.001, 0.1, 1, 100}` | Hastie *ESL* §4.4 + Pedregosa et al. recomendam C log-spaced em 5+ ordens de magnitude. A janela antiga (4 ordens) corria risco de não cobrir o ótimo em BC com `class_weight='balanced'` + `l1_ratio=1.0` (L1 + reescalonamento de classe empurram o ótimo para C pequeno). Mesmo número de configs, faixa mais larga. |
| `HistGradientBoosting` | `max_iter(3) × lr(2)` → `max_iter(2) × lr(3)` | Chen & Guestrin 2016 (XGBoost) e Ke et al. 2017 (LightGBM) convergem em "`learning_rate` é o #1 knob de boosting". A versão anterior tinha 2 lr's e 3 max_iter's — invertido para priorizar lr. Novo grid: lr ∈ {0.05, 0.1, 0.2} (conservador/moderado/agressivo) × max_iter ∈ {200, 500} (dá ao lr=0.05 chance de convergir). |

Demais 5 grids (`DecisionTree`, `RandomForest`, `LinearSVC`, `MultinomialNB`, `GaussianNB`) já cobriam os top-2 knobs da literatura — não mudaram.

### Por que 24 configs e não busca aleatória/halving

Discutimos grid completo, RandomizedSearchCV e HalvingGridSearch. Grid completo de 24 configs é mais fácil de auditar: todas as configs ficam documentadas e aparecem em `cv_results_per_fold.jsonl`. Halving/Random ficam como fallback futuro se até 24 configs ainda se mostrar inviável para algum algoritmo/representação.

#### Corte operacional do grid de GradientBoosting em BC

Durante a execução real em servidor, `bc_gradient_boosting` começou com `dense_conversion=True` e levou minutos por configuração no primeiro outer fold; a projeção para o grid completo ficava em vários dias. O custo vem da combinação BC esparso → matriz densa + HistGradientBoosting.

Para preservar uma versão forte do modelo sem travar a Fase E, o grid foi reduzido para **24 configs**:

- removido `max_iter=500`, o maior multiplicador direto de tempo;
- removido `learning_rate=0.01`, que normalmente exige mais iterações para competir;
- removido `max_leaf_nodes=63`, a opção mais cara de complexidade;
- removido `l2_regularization`, mantendo o default;
- mantido `max_leaf_nodes ∈ {15,31}`, o principal controle de complexidade recomendado pela literatura;
- mantido `class_weight`, importante para macro-F1.

Essa é uma redução por viabilidade computacional documentada, não uma mudança metodológica silenciosa.

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

**Com `--from-spot-check`** (default no `train` do `run_pipeline`): cada algoritmo da união é treinado em ambas as representações. Isso preserva a comparação BC vs DF justa por algoritmo — mesmo um algoritmo que só foi top-5 em uma das duas representações é treinado nas duas para as fases posteriores poderem ranquear.

### Checkpoints por outer fold

Cada outer fold gera um arquivo `checkpoints/<sig>/<fold_id>.json` com metrics, best_params, predictions e cv_results. A `signature_id` é `sha256(config payload)[:16]` cobrindo grid + folds + parâmetros do estimador. Se você muda grid/seeds, signature muda, checkpoint antigo é ignorado → reexecução do zero. Crucial: previne usar checkpoints com grid inválido após mudança de design.

`--force-rerun` ignora checkpoints existentes mesmo com signature batendo (útil para auditar não-determinismo cross-machine).

### Voting — código legado, sem execução automática

6 ensembles fixos em `VOTING_SPECS`:

```
voting_top3_BC   : 3 BC models
voting_top5_BC   : 5 BC models
voting_top3_DF   : 3 DF models
voting_top5_DF   : 5 DF models
voting_top3_BC_DF: 3 BC + 3 DF
voting_all       : todos os modelos individuais
```

`hard_vote(predictions)`: `Counter` → classe com `max(count)`; em empate, vence a classe cuja coalizão de modelos votantes tem maior macro-F1 média. Empate residual usa o menor rótulo numérico (`min(labels)`) para manter determinismo cross-machine/cross-thread.

Voting **não retreina**: usa as `predictions_per_fold.jsonl` persistidas. No plano atualizado, essa lógica deve sair da Fase E e virar uma etapa posterior à verificação dos modelos; por enquanto não há script separado implementado para isso e a Fase E não dispara voting automaticamente.

### Testes estatísticos

- **Friedman**: aplicado sobre a matriz `n_folds × n_models` de macro-F1. H0 = todos os modelos têm a mesma distribuição de rank. p < 0,05 indica que pelo menos um difere.
- **Nemenyi**: pós-Friedman, computa a diferença crítica `q_alpha * sqrt(k(k+1)/(6n))`. Pares cujo diff de rank médio supera CD são significativamente diferentes em α=0,05.
- **Wilcoxon signed-rank pareado**: por par, compara as macro-F1 dos 15 folds (pareadas porque os folds são os mesmos). p-valores não corrigidos para múltiplas comparações — a interpretação é exploratória.

Requer ≥ 2 modelos e ≥ 3 folds usáveis. Se faltar, `status: "insufficient_data"` e o report fala.

### Integração Drive (colaboradores)

Quando `train` roda sem `--run-local`:

1. **Pre-flight**: `check_drive_write` no início falha cedo se o colaborador não tem permissão.
2. **Upload por modelo**: ao terminar cada modelo, `enqueue_drive_upload()` submete pra `ThreadPoolExecutor(max_workers=1)` — uploads acontecem em paralelo com o próximo treino, mas serializados entre si (evita rate limit no Drive).
3. **Upload de bundle shared**: ao final da Fase E, `enqueue_bundle_drive_upload()` sobe `shared` (= seeds.json + folds.json).
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

- **Adicionar algoritmo**: atualizar `SELECTED_ALGORITHMS`, `estimator_for`, `pipeline_for`, `needs_df_scaling`, `full_param_grid`. Adicionar test em `test_all_grids_fit_within_max_configs` (o contrato atual é grid com 24 configs). Atualizar também `ALGORITHMS` em Phase D pra que apareça no spot-check.
- **Mudar grids**: vai invalidar checkpoints antigos (signature muda). Considere isso no orçamento de re-run.
- **Mudar tie-break do voting**: requer recálculo dos ensembles, mas não retreina modelos individuais.
- **NÃO rodar voting antes da verificação**: o plano atualizado coloca completude, GroupKFold por comandante e testes estatísticos antes de qualquer votação.
- **NÃO subir bundles antes do manifest final**: o `lsjson` na publicação varre tudo no remote — se você inverte, modelos novos podem ser referenciados pelo manifest velho.
- **NÃO trocar `MAX_GRID_CONFIGS` sem rever cada grid**: `test_all_grids_fit_within_max_configs` ainda passa mas você pode estar regredindo na variância de hiperparâmetros explorados.
- **Cuidado com `--max-grid-values`**: corta cada hiperparâmetro pros primeiros N valores. Útil pra smoke test (`--max-grid-values 1`); fatal pra rodada de produção. Tests usam isso explicitamente.

## Problemas encontrados e correções

| Problema | Diagnóstico | Correção |
|---|---|---|
| RF grid original com 864 configs (4×4×2×3×3×3×1) | Inviável na nested CV; inflava runtime sem ganho proporcional | Reduzido em etapas até 24 configs (n_estimators × max_features × min_samples_leaf × class_weight); `bootstrap=True`, `criterion=gini` e `max_depth=None` fixos |
| GridSearchCV sem feedback de progresso | Frustrante em runs de horas | Loop manual com `print_inner_grid_progress` por config |
| Voting `voting_all10` (nome com `10`) | Misnomer quando a união tem 6 ou 7 algoritmos (= 12 ou 14 modelos) | Renomeado para `voting_all` (covers all individual models present) |
| Checkpoints antigos com grid velho ainda eram lidos | Resultados misturavam grids | `signature_id = sha256(grid + folds + params)`; checkpoint só é restaurado se signature bater |
| `HistGradientBoosting` em CSR esparso | API não aceita | `SparseToDenseTransformer` antes do clf |
| Upload Drive falhando em meio do run | Frustrava perder horas de treino | Upload em ThreadPoolExecutor; falhas registradas como problems mas run continua OK |
| Tests com `--algorithms naive_bayes --representations DF` | Não passam pelo `--from-spot-check` flow | `build_model_plan` cai no caminho cartesiano quando `--from-spot-check` não está setado |
| `MODEL_ID_RE` rejeitava nomes de bundle com maiúscula (`voting_top3_BC`) | Tentar fazer upload-bundle desses nomes quebraria | Bundles seguem nomes lowercase (`voting`, `spot_check`, `shared`); voting_<nome>_BC vive **dentro** do bundle voting.zip |
