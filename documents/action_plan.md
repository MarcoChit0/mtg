# Plano de Ação — Modelagem da Divergência entre Brackets de Commander

Plano sequencial para concluir o projeto descrito em [backbone.md](backbone.md), atendendo às exigências do [enunciado.pdf](enunciado.pdf). Cada fase tem **objetivo**, **saídas** e **decisões firmadas**.

**Pergunta central**: em que medida `y1` (Archidekt) diverge de `y2` (EDHPowerLevel), e quais características do deck explicam essa divergência?

## Convenção de reports por fase

Cada fase tem **dois reports separados** por público-alvo, ambos em `documents/reports/`:

- **`results/`** — snapshot da rodada atual (tabelas, métricas, distribuições). Auto-gerado a cada execução do script da fase; descartável e regerável.
- **`implementation/`** — narrativa de implementação (objetivo, o que foi construído, como, decisões + porquês, problemas + correções, pontos de extensão). Escrito à mão; vive enquanto o projeto vive; é o que um colaborador novo ou agente LLM lê antes de mexer no código.

| Fase | Results (auto-gerado) | Implementation (à mão) |
|---|---|---|
| A | [reports/results/phase_a_data_collection.md](reports/results/phase_a_data_collection.md) | [reports/implementation/phase_a_data_collection.md](reports/implementation/phase_a_data_collection.md) |
| B | [reports/results/phase_b_eda.md](reports/results/phase_b_eda.md) + [reports/results/phase_b_divergence.md](reports/results/phase_b_divergence.md) | [reports/implementation/phase_b_eda_divergence.md](reports/implementation/phase_b_eda_divergence.md) |
| C | [reports/results/phase_c_preprocessing.md](reports/results/phase_c_preprocessing.md) | [reports/implementation/phase_c_preprocessing.md](reports/implementation/phase_c_preprocessing.md) |
| D | [reports/results/phase_d_spot_checking.md](reports/results/phase_d_spot_checking.md) | [reports/implementation/phase_d_spot_checking.md](reports/implementation/phase_d_spot_checking.md) |
| E | [reports/results/phase_e_nested_cv.md](reports/results/phase_e_nested_cv.md) | [reports/implementation/phase_e_nested_cv.md](reports/implementation/phase_e_nested_cv.md) |
| F | `reports/results/phase_f_model_verification.md` + `reports/results/phase_f_statistical_tests.md` | `reports/implementation/phase_f_model_verification.md` |
| G | `reports/results/phase_g_voting.md` | `reports/implementation/phase_g_voting.md` |
| H | `reports/results/best_models.md` | `reports/implementation/phase_h_best_models.md` |
| I | `reports/results/model_vs_calculator.md` | `reports/implementation/phase_i_model_vs_calculator.md` |
| J | `reports/results/interpretability.md` | `reports/implementation/phase_j_interpretability.md` |
| K | `reports/results/article.md` + `reports/results/ai_usage.md` | `reports/implementation/phase_k_article.md` |
| L | `reports/results/ood_report.md` | `reports/implementation/phase_l_ood.md` |
| M | `reports/results/stacking_results.md` | `reports/implementation/phase_m_stacking.md` |

## 0. Estado atual

| Item | Valor |
|---|---|
| Decks Archidekt (y1 ∈ {2,3,4}, ≥1000 views, 100 cartas) | 12.950 |
| Decks com y2 | 12.950 (todos rotulados após bugfix de scraper em 2026-05-15) |
| Distribuição y2 | 1: 393 · 2: 1.911 · 3: 6.059 · 4: 4.165 · 5: 422 |
| Base modelável (y1 e y2 ∈ {2,3,4}) | 12.135 |
| `deck_features.jsonl` (114 features) | ✓ sincronizado pós-relabel |
| `bag_of_cards.jsonl` (sparse) | ✓ sincronizado pós-relabel |

Os 815 decks com y2 ∈ {1, 5} ficam fora do treino mas são preservados para análise qualitativa (Fase B).

**Variabilidade temporal do y2** (backbone §3): a calculadora EDHPowerLevel incorpora preço e popularidade no cálculo, sinais que evoluem com o tempo. Empiricamente (Fase A, 90 decks): **87/90 (96,7%) reconsultados receberam o mesmo `commander_bracket`**; as 3 divergências foram todas decks de fronteira (Δ `power_level` ≤ 0,3). Modelagem segue tratando y2 como rótulo fixo (snapshot da coleta), mas o artigo deve documentar essa flutuação como limitação.

## Fase B — EDA + análise direta da divergência ✓ concluída

Implementada em [scripts/phase_b_eda_divergence.py](../scripts/phase_b_eda_divergence.py). Saídas em [reports/results/phase_b_eda.md](reports/results/phase_b_eda.md), [reports/results/phase_b_divergence.md](reports/results/phase_b_divergence.md) e `documents/reports/results/figures/{eda,divergence}/`. Achados principais:

- Base modelável (y1, y2 ∈ {2,3,4}): **12.135 decks**.
- Concordância exata y1=y2: **60,9%** · dentro de ±1: **97,7%** · dentro de ±2: **100%**.
- `|Δ|` médio: 0,414.
- Tendência direcional: y2>y1 em 23,5% vs y2<y1 em 15,6% — calculadora classifica mais "alto" que o usuário.
- 815 decks (6,3%) com y2 ∈ {1, 5} — analisados em subseção dedicada e descartados da modelagem.

## Fase C — Pré-processamento ✓ concluída

Implementada em [scripts/preprocessing.py](../scripts/preprocessing.py) e [scripts/phase_c_filter_dataset.py](../scripts/phase_c_filter_dataset.py). O results report [reports/results/phase_c_preprocessing.md](reports/results/phase_c_preprocessing.md) **é regerado automaticamente** a cada `uv run run-mtg-pipeline init`. A narrativa de implementação (decisões + porquês + armadilhas) vive em [reports/implementation/phase_c_preprocessing.md](reports/implementation/phase_c_preprocessing.md). Última rodada confirmou **12.135 decks incluídos** e **815 excluídos** (`y2=1`: 393 · `y2=5`: 422).

Alvo único de treino: `y1`. `y2` é mantido apenas para comparação descritiva (Fase I), nunca como feature.

### C.1 Filtros prévios
Manter y1 e y2 ∈ {2,3,4} (12.135 decks). Descartados salvos em `data/processed/archidekt/modeling_excluded.jsonl`.

### C.2 Deck Features
- Imputação: mediana do treino para `edhrec_rank_*` e `salt_*`.
- Winsorização de `price_total` no p99 do treino.
- `StandardScaler` para SVM/lineares; opcional para árvores.
- Remover features de variância zero no treino.

### C.3 Bag of Cards
- Matriz esparsa `(n_decks, n_cards)` com quantidade.
- Pruning: remover cartas com presença < `bc_min_df` no treino. Valor decidido no spot-check (testar 5, 10, 20).
- **Variante TF-IDF** (backbone §10.1): fica disponível no pipeline, mas **não é ativada no spot-check da Fase D**. Será tratada depois como hiperparâmetro/variante para algoritmos que se beneficiam de ponderação por IDF (`LinearSVC`, regressão logística). Permanece desabilitada para `MultinomialNB` (assume contagens inteiras, suposição incompatível com TF-IDF).

### C.4 Antivazamento
- Toda transformação fit somente no treino do fold.
- `y2`, `delta`, `abs_delta` e todos os campos `edhpowerlevel.*` (score, power_level, etc.) **nunca** entram em X.
- `y1` é o único target; não há predição de `y2` no projeto.

## Fase D — Spot-checking ✓ concluída (feedback da professora, 2026-05-19)

Implementada em [scripts/phase_d_spot_check.py](../scripts/phase_d_spot_check.py). Saídas em [reports/results/phase_d_spot_checking.md](reports/results/phase_d_spot_checking.md), `experiments/spot_check/results.jsonl` e `experiments/spot_check/summary.json`. Narrativa de implementação em [reports/implementation/phase_d_spot_checking.md](reports/implementation/phase_d_spot_checking.md).

Mudanças vs. desenho anterior (orientação direta da professora):

- **Pool de 7 candidatos viáveis em ambas as representações**: Decision Tree, Random Forest, Gradient Boosting, Naive Bayes, Logistic Regression, LinearSVC, KNN. `SVC(kernel='rbf')` e `SVC(kernel='poly')` foram removidos do pool — a regra é usar apenas algoritmos que rodam tanto em BC quanto em DF, e kernels não-lineares não escalam para BC esparso de alta dimensionalidade.
- **N=5 repetições por combinação** com seeds `{1, 2, 3, 4, 5}` (hold-outs estratificados 80/20 distintos). Reportamos média e desvio padrão de macro-F1 (e demais métricas) por (algoritmo, representação, `bc_min_df`).
- **Top-5 por representação**: ranqueamos por macro-F1 média e selecionamos os **5 melhores em BC** e os **5 melhores em DF** independentemente. A união (`A_uniao = A_BC ∪ A_DF`) define os algoritmos que vão para a Fase E — pode incluir até os 7 candidatos. **Em Fase E, cada algoritmo da união é treinado em ambas as representações** (BC e DF), gerando `|A_uniao| × 2` modelos: 10 se a união tiver 5, 12 se tiver 6, 14 se tiver 7.
- `bc_min_df` testado em {5, 10, 20}; escolhido pelo melhor macro-F1 médio agregando sobre algoritmos × seeds em BC. TF-IDF desativado nesta fase.

### D.1 Algoritmos candidatos (pool comum)
| Algoritmo | Viés | Classe sklearn | Obs |
|---|---|---|---|
| Decision Tree | árvore | `DecisionTreeClassifier` | — |
| Random Forest | bagging | `RandomForestClassifier` | — |
| Gradient Boosting | boosting | `HistGradientBoostingClassifier` | BC converte CSR para dense de forma controlada |
| Naive Bayes | probabilístico | `MultinomialNB` (BC) / `GaussianNB` (DF) | — |
| Logistic Regression | linear paramétrico | `LogisticRegression` | `solver='lbfgs'` (DF) / `'saga'` (BC esparso) |
| LinearSVC | margem linear | `LinearSVC` | escala bem em BC esparso |
| KNN | distância | `KNeighborsClassifier` | em DF requer `StandardScaler`; em BC esparso é mantido como sonda empírica |

**7 candidatos para DF e 7 candidatos para BC** — pool simétrico, conforme a restrição da professora. Cobrem os vieses indutivos do backbone §13.3 (árvore, bagging, boosting, probabilístico, linear paramétrico, margem linear, distância). Kernels não-lineares (`SVC` RBF/poly) ficam **fora do projeto** porque não atendem ao critério de viabilidade dupla.

### D.2 Procedimento
Para cada combinação `(algoritmo, representação, bc_min_df)`:

1. Repetir 5 vezes (`random_state ∈ {1, 2, 3, 4, 5}`):
   - hold-out estratificado 80/20 por `y1` usando a seed;
   - fit de pré-processamento somente no treino do fold;
   - treino com defaults do sklearn (exceto pequenos ajustes de convergência/solver);
   - avaliar no teste: macro-F1, accuracy, precision_macro, recall_macro, tempo.
2. Agregar média e desvio padrão das 5 rodadas.
3. Repetir para `bc_min_df ∈ {5, 10, 20}` em BC; DF tem `bc_min_df=None`.

`use_tfidf=False` em toda a Fase D.

**Saída**: `documents/reports/results/phase_d_spot_checking.md` com tabela de média±dp por combinação, ranking por representação e top-5 de cada representação. `experiments/spot_check/results.jsonl` contém uma linha por (algoritmo, representação, `bc_min_df`, seed). `experiments/spot_check/summary.json` registra o `best_bc_min_df`, os rankings agregados e as listas `top5_DF` e `top5_BC` consumidas pela Fase E.

### D.3 Seleção dos modelos para a Fase E
O spot-checking é a etapa de filtragem. A decisão é por representação, mas o que importa para a Fase E é a união:

```text
A_DF = top-5 algoritmos por macro-F1 média no spot-check em DF
A_BC = top-5 algoritmos por macro-F1 média no spot-check em BC
A_uniao = A_DF ∪ A_BC   # 5 a 7 algoritmos distintos
```

Em Fase E treinamos **|A_uniao| × 2 modelos** — cada algoritmo da união em ambas as representações (BC e DF):

```text
modelos_E = {(alg, rep) : alg ∈ A_uniao, rep ∈ {BC, DF}}
```

Assim:

- 5 algoritmos na união → 10 modelos
- 6 algoritmos na união → 12 modelos
- 7 algoritmos na união → 14 modelos

Mesmo que um algoritmo só apareça no top-5 de uma representação, ele entra na Fase E em ambas — a comparação BC vs DF para cada algoritmo é parte do que a Fase H precisa para decidir o melhor de cada lado. O top-5 por representação serve para garantir que algoritmos competitivos em pelo menos uma representação avancem; uma vez selecionados, ambos os lados são treinados.

Critério de desempate: desvio padrão menor (estabilidade) e diversidade de vieses indutivos quando o ranking puro concentrar muitos algoritmos da mesma família (ex: 3 ensembles no topo). A decisão final é registrada em `documents/reports/results/phase_d_spot_checking.md` com justificativa explícita.

Combinações que falharem por erro no spot-check ficam fora automaticamente.

## Fase E — Nested CV ✓ concluída (2026-05-24)

Implementada em [scripts/phase_e_nested_cv.py](../scripts/phase_e_nested_cv.py), com entrypoint `phase-e-nested-cv`. A execução completa é sob demanda por custo computacional. Também é possível reexecutar apenas um algoritmo/modelo, por exemplo `uv run phase-e-nested-cv --model random_forest` para DF+BC ou `uv run phase-e-nested-cv --model random_forest --feature df` para uma representação específica. A execução salva checkpoints por outer fold em `experiments/<modelo>/checkpoints/<assinatura>/` e retoma automaticamente execuções interrompidas; usar `--force-rerun` para ignorar checkpoints e recalcular.

Alvo único: `y1`. **10 a 14 modelos** a treinar (cada algoritmo da união `A_uniao = A_DF ∪ A_BC` em ambas as representações), conforme §D.3. Para a seleção atual da Fase D, `|A_uniao|=6`, então a rodada completa da Fase E deve produzir **12 modelos**. As listas são lidas de `experiments/spot_check/summary.json`.

Restrição de custo (orientação atualizada em 2026-05-21): a execução real mostrou que os grids de 72-192 configs ainda ficam caros demais na Fase E, principalmente em BC. Para esta versão, adotamos **~24 configurações por grid**. O corte preserva as variações principais de cada algoritmo e reduz o custo do nested CV sem trocar a metodologia.

### E.1 Esquema
```text
outer:  StratifiedKFold(n_splits=5, shuffle=True, random_state=r)
        r ∈ {1, 2, 3}            # 15 outer evaluations por (fs, algo)
inner:  StratifiedKFold(n_splits=3, shuffle=True, random_state=r+100)
                                 # busca em grid controlada pelo script otimiza hiperparâmetros
```

Métrica de seleção interna: **macro-F1**. Métricas reportadas: macro-F1, accuracy, precision_macro, recall_macro, confusion matrix.

Folds idênticos para todos os modelos individuais (10 a 14) em cada repeat. Seeds em `experiments/seeds.json`. Biblioteca: **scikit-learn** para estimadores, folds e métricas; a busca em grid do inner CV é controlada pelo script para permitir barra de progresso por configuração e checkpoint por outer fold.

**Predições out-of-fold salvas** para todos os modelos — reutilizadas nas Fases F, G, I e M sem retreino.

### E.2 Grids de hiperparâmetros
Grids definidos para todos os 7 candidatos da Fase D (apenas os que aparecem em `A_uniao` são executados). Todos usam **24 configurações** para manter os algoritmos comparáveis e viáveis no runtime atual. Nenhum dos candidatos tem variante `*CV` com grids embutidos no sklearn que cubra exatamente o que queremos (`LogisticRegressionCV` existe e oferece grade automática de `Cs`, mas usamos uma busca em grid uniforme no script para padronização, progresso e checkpoint). Valores baseados no sklearn user guide / Géron / Hastie, com auditoria de literatura em 2026-05-20 e corte operacional em 2026-05-21:

| Algoritmo | Grid | Total |
|---|---|---:|
| `DecisionTreeClassifier` | `max_depth ∈ {None, 10, 20}`, `min_samples_leaf ∈ {1, 5}`, `ccp_alpha ∈ {0.0, 5e-3}`, `class_weight ∈ {None, balanced}` | 24 |
| `RandomForestClassifier` | `n_estimators ∈ {100, 250, 500}`, `max_features ∈ {sqrt, log2}`, `min_samples_leaf ∈ {1, 2}`, `class_weight ∈ {None, balanced}` | 24 |
| `HistGradientBoostingClassifier` | `max_iter ∈ {200, 500}`, `learning_rate ∈ {0.05, 0.1, 0.2}`, `max_leaf_nodes ∈ {15, 31}`, `class_weight ∈ {None, balanced}` | 24 |
| `MultinomialNB` (BC) | `alpha ∈ {1e-3, 1e-2, 0.05, 0.1, 0.5, 1, 2, 5, 10, 25, 50, 100}`, `fit_prior ∈ {True, False}` | 24 |
| `GaussianNB` (DF) | `var_smoothing ∈ np.logspace(-12, -3, 24)` | 24 |
| `LogisticRegression` | `solver='saga'`, `C ∈ {0.001, 0.1, 1, 100}`, `class_weight ∈ {None, balanced}`, `l1_ratio ∈ {0.0, 0.5, 1.0}` (`penalty='elasticnet'` só em sklearn <1.8) | 24 |
| `LinearSVC` | `dual='auto'`, `loss='squared_hinge'`, `C ∈ {0.001, 0.01, 0.1, 1, 10, 100}`, `class_weight ∈ {None, balanced}`, `penalty ∈ {l1, l2}` | 24 |
| `KNeighborsClassifier` | `n_neighbors ∈ {3, 5, 7, 11, 19, 31}`, `weights ∈ {uniform, distance}`, `p ∈ {1, 2}` | 24 |

Busca em grid no inner; trocar para busca aleatória/halving se algum grid de 24 configs ainda se mostrar inviável. `random_state=42` onde aplicável. As principais decisões pós-auditoria de literatura (2026-05-20) e corte operacional (2026-05-21) foram:

- **`DecisionTree`**: `ccp_alpha` em vez de `min_samples_split` (Breiman/Hastie *Elements of Statistical Learning* §9.2 + sklearn user guide §1.10.4 — cost-complexity pruning é o regularizador canônico).
- **`HistGradientBoosting`**: `max_leaf_nodes` em vez de `max_depth` (LightGBM paper, Ke et al. 2017; sklearn user guide explicitamente recomenda `max_leaf_nodes` como knob principal para HistGB).
- **Corte global para ~24 configs**: a execução em BC ficou muito mais lenta que o previsto. Preservamos os principais knobs por algoritmo e removemos knobs secundários ou faixas mais custosas: `criterion` em DT, `max_depth` em RF, `l2_regularization` e `max_leaf_nodes=63` em HistGB, malhas finas demais de `C` nos lineares e resoluções excessivas de smoothing em NB.
- **`HistGradientBoosting` em BC foi excepcionalmente caro**: a combinação Bag of Cards + conversão densa (`dense_conversion=True`) levou minutos por configuração e projetava vários dias para concluir a representação BC no grid completo. Para manter a Fase E viável, o grid foi cortado para 24 configs, removendo `max_iter=500`, `learning_rate=0.01`, `max_leaf_nodes=63` e `l2_regularization`. Mantivemos `max_leaf_nodes ∈ {15,31}`, o principal controle de complexidade, além de `class_weight`.
- **Estimadores com suporte recebem `class_weight ∈ {None, balanced}`** porque a métrica principal é macro-F1 e a base é imbalanceada (y1=2 com 21% vs y1=3 com 52%).
- **`LogisticRegression`** usa `solver='saga'`, com `l1_ratio ∈ {0.0, 0.5, 1.0}` cobrindo o espectro completo L2 → elastic → L1 num único grid simétrico para BC e DF; `penalty='elasticnet'` é definido apenas em sklearn <1.8, porque sklearn 1.8+ depreciou `penalty` em favor de `l1_ratio`/`C` (Zou & Hastie 2005 sobre ElasticNet em problemas com features correlacionadas — relevante para cartas de combo em BC).
- **`LinearSVC`** usa `dual='auto'` + `loss='squared_hinge'`, com `penalty ∈ {l1, l2}` simétrico em BC e DF (LIBLINEAR / Fan et al. 2008).
- **`fit_intercept`** foi **removido** dos grids lineares — Hastie et al. §4.4 e LIBLINEAR docs convergem em "intercept=True é a escolha universal"; o orçamento foi concentrado em `C`, `class_weight` e regularização.
- **`KNN`** ficou fora da união (rank 7 em ambas as representações no spot-check) — não treinado na Fase E.

**Saídas E**: `experiments/<fs>_<algo>/{best_hyperparams_per_fold.json, predictions_per_fold.jsonl, cv_results_per_fold.jsonl, metrics_per_fold.json, checkpoint_state.json, checkpoints/...}`, `experiments/archives/<fs>_<algo>.zip` quando upload via Drive estiver habilitado, `experiments/seeds.json`, `experiments/folds.json`, `experiments/nested_cv_summary.json`, `documents/reports/results/phase_e_nested_cv.md`.

## Fase F — Verificação dos modelos individuais ✓ concluída (2026-05-24)

> Script: `scripts/phase_f_model_verification.py` · Entrypoint: `uv run phase-f-model-verification`
> Implementation report: `documents/reports/implementation/phase_f_model_verification.md`

Executada com `--all --group-kfold` sobre os 12 modelos completos. Todas as sub-fases concluídas.

- F.1: 12/12 modelos com 15/15 folds ✓
- F.2: GroupKFold por comandante — `group_kfold_results.json` gerado ✓
- F.3: Friedman p≈0, 28 pares Nemenyi significativos ✓

### F.1 Checagem de completude

Para cada modelo esperado em `A_uniao × {DF, BC}`:

- exigir 15/15 outer folds completos (sem `--all`: aceita mínimo de 5 folds via `--min-folds`);
- exigir `metrics_per_fold.json`, `best_hyperparams_per_fold.json`, `predictions_per_fold.jsonl`;
- arquivos opcionais (sem bloquear modelo): `cv_results_per_fold.jsonl`, `checkpoint_state.json`;
- confirmar que todos compartilham as mesmas seeds, folds, número de linhas e rótulos.

### F.2 GroupKFold por comandante

Rodada auxiliar com `GroupKFold(n_splits=5)` por `commander_oracle_uids`, sem repeat e sem nova busca de hiperparâmetros. Mede o quanto o desempenho cai quando comandantes vistos no treino não aparecem no teste.

Reportar **gap macro-F1 (Stratified − Group)** por modelo:

- gap pequeno: o modelo aprendeu padrões mais gerais de deck;
- gap grande: o modelo depende mais de comandantes/arquetipos específicos já vistos.

Ativado com `--group-kfold` (mais lento — re-treina cada modelo 5 vezes).

### F.3 Testes estatísticos

Sobre os outer scores disponíveis:

- múltiplos algoritmos: Friedman + Nemenyi;
- pares de modelos: Wilcoxon signed-rank por fold;
- ranking médio por modelo e por representação.

**Saídas F**: `documents/reports/results/phase_f_model_verification.md`, `documents/reports/results/phase_f_statistical_tests.md`, `experiments/model_verification/group_kfold_results.json` (se `--group-kfold`).

## Fase G — Ensembles por votação (sem retreino) ✓ concluída (2026-05-24)

> Script: `scripts/phase_g_voting.py` · Entrypoint: `uv run --no-sync python -m scripts.phase_g_voting`
> Implementation report: `documents/reports/implementation/phase_g_voting.md`

Executada com `--all --force-recompute` após F concluída. 6 ensembles computados sobre os 12 modelos completos (15/15 folds cada). Melhor ensemble: `voting_top3_BC_DF` com macro-F1=0.6944 (+0.0036 vs melhor individual `df_gradient_boosting`=0.6908).

Solicitado pela professora: avaliar o desempenho de combinações dos melhores modelos via votação majoritária (hard vote) sobre as predições out-of-fold já produzidas na Fase E. Como todas as predições OOF compartilham o mesmo conjunto de folds, a votação é exata por linha e por fold — não há retreino.

6 ensembles definidos:

| Nome | Membros | Tamanho |
|---|---|---:|
| `voting_top3_BC` | top-3 modelos BC ranqueados por macro-F1 média na Fase E | 3 |
| `voting_top5_BC` | top-5 modelos BC | 5 |
| `voting_top3_DF` | top-3 modelos DF | 3 |
| `voting_top5_DF` | top-5 modelos DF | 5 |
| `voting_top3_BC_DF` | top-3 BC + top-3 DF | 6 |
| `voting_all` | todos os modelos da Fase E disponíveis (12 com a Fase E completa) | 10–14 |

Regras:

- Hard voting (maioria simples). Empate → classe com maior macro-F1 médio dos membros que a previram; empate residual → menor rótulo numérico.
- Para cada outer fold, agrega predições OOF e computa macro-F1, accuracy, precision/recall por classe e matriz de confusão.
- Reportar média ± desvio padrão dos folds compartilhados (até 15 quando Fase E concluída).
- Predições OOF dos 6 ensembles salvas para Fases I e J.

**Saídas G**: `experiments/voting/{voting_<nome>/metrics_per_fold.json, predictions_per_fold.jsonl}`, `experiments/voting/voting_summary.json`, `documents/reports/results/phase_g_voting.md`.

## Fase H — Melhor modelo por representação ✓ concluída (2026-05-24)

> Script: `scripts/phase_h_best_models.py` · Entrypoint: `uv run --no-sync python -m scripts.phase_h_best_models`
> Implementation report: `documents/reports/implementation/phase_h_best_models.md`

Ranking completo dos 12 modelos individuais + 6 ensembles de votação por macro-F1 médio. Seleção determinística por `argmax macro_F1`, desempate por menor std.

**Resultado:**
- `melhor_BC` = `bc_gradient_boosting` — macro-F1 = 0.6433 ± 0.0121 (15/15 folds)
- `melhor_DF` = `df_gradient_boosting` — macro-F1 = 0.6908 ± 0.0093 (15/15 folds)

Artefato de seleção: `experiments/best_models.json` (consumido pela Fase J).

Relatório inclui: ranking completo, tabela BC vs DF por algoritmo, ganho/perda de cada ensemble vs melhor individual, hiperparâmetros por fold dos dois selecionados, matrizes de confusão agregadas (36.405 predições OOF).

## Fase I — Comparação das predições dos modelos com a calculadora ✓ concluída (2026-05-24)

> Script: `scripts/phase_i_model_vs_calculator.py` · Entrypoint: `uv run --no-sync python -m scripts.phase_i_model_vs_calculator`
> Implementation report: `documents/reports/implementation/phase_i_model_vs_calculator.md`

**Descritivo, sem retreino**. 18 modelos analisados (12 individuais + 6 ensembles). O relatório compara primeiro `y1` real do Archidekt contra `y2` da calculadora e, na mesma base OOF, compara `ŷ1` de cada modelo contra `y2`. Para ambos os blocos reporta concordância exata, concordância ±1, |Δ| médio, macro-F1 vs y2 e matriz de confusão. Subset analysis: decks concordantes (y1=y2) vs discordantes (y1≠y2).

**Resultados principais:**
- Maior concordância global: `df_random_forest` (69,3%).
- Menor concordância global: `bc_decision_tree` (54,2%).
- Maior gap absoluto global: `df_gradient_boosting` (0,0508).
- Menor gap absoluto global: `bc_naive_bayes` (0,0010).

## Fase J — Interpretabilidade ✓ concluída (2026-05-24)

> Script: `scripts/phase_j_interpretability.py` · Entrypoint: `uv run --no-sync python -m scripts.phase_j_interpretability`
> Implementation report: `documents/reports/implementation/phase_j_interpretability.md`

**Dois modelos**: `melhor_BC` (`bc_gradient_boosting`) e `melhor_DF` (`df_gradient_boosting`), definidos em `experiments/best_models.json`.

**DF — Permutation importance** (hold-out 80/20, n_val=2.427):
- `game_changer_count` domina com PI=0.228 (vs 2º em 0.029 — mais de 7× mais importante)
- `mass_land_denial_count`, `unique_atomic_combo_refs_count`, `tutor_count` completam top-4
- Direção clara: `game_changer_count` varia 0.001 → 1.499 → 4.146 nos brackets 2→3→4
- Divergência: decks concordantes (ŷ1=y2) têm 2.3× mais Game Changers que divergentes

**BC — Lift analysis sobre OOF predictions** (36.405 entradas):
- Bracket 2: cartas tribal/animal (Owlbear, Bear Cub) — tema casual
- Bracket 4: stax/prisão (Blood Moon, Ruination), fast mana (Chrome Mox, Mox Diamond, Mana Vault), tutors (Imperial Seal), combos (Food Chain), turnos extras
- Concordância alta: Blood Moon, Imperial Seal, Force of Will — cartas objetivamente fortes reconhecidas por ambas as fontes
- Sub-previstos (ŷ1 < y2): Vorinclex, Expropriate, Time Stretch — sinais que a calculadora penaliza mais que a comunidade

**Saídas**:
- `documents/reports/results/phase_j_interpretability.md` — auto-gerado
- `documents/reports/implementation/phase_j_interpretability.md` — este relatório
- `experiments/phase_j_interpretability/` — artefatos intermediários (PI raw, lift por classe, divergência)

## Fase K — Artigo

Escrito imediatamente após a interpretabilidade, com o resultado principal já fechado. Se Fase L (OOD) ou Fase M (stacking) forem executadas depois, **adicionar seções extras ao artigo** descrevendo esses experimentos (insertable nas seções de Resultados e Discussão).

Template Moodle (coluna única, ≤20 pág.):
1. Introdução · 2. Trabalhos relacionados · 3. Métodos (coleta, escopo, BC/DF, nested CV, verificação, reprodutibilidade) · 4. Resultados (B, E, F, G, H, I, J) · 5. Discussão · 6. Conclusão · 7. Referências · 8. Apêndices.

Seções extras condicionais:
- 4.x **Generalização fora da distribuição** — só se Fase L rodar.
- 4.y **Stacking** — só se Fase M rodar.

Se usar IA generativa: `documents/reports/ai_usage.md` com prompts e limitações.

## Fase L — Out-of-distribution (opcional)

Coletar decks com 500 ≤ views < 1000. Aplicar melhores modelos **sem retreinar**. Comparar macro-F1 dentro vs fora.

**Saída**: `documents/reports/ood_report.md`. Se executada, adicionar seção 4.x no artigo (Fase K).

## Fase M — Stacking (opcional, se houver tempo)

Movida para o final do plano por ser estritamente complementar — não é exigida pelo enunciado e seu valor depende de termos os modelos individuais (10 a 14) e os 6 ensembles de votação bem caracterizados e a comparação contra `y2` já fechada. Só faz sentido depois de G, H, I e J. Em particular, voting (G) é entregue como parte obrigatória do projeto; stacking continua opcional como passo extra.

Base learners: os modelos individuais da Fase E (10 a 14, todos prevendo y1).
Meta-learner: `LogisticRegression`.
Meta-target: y1.
Folds: os mesmos outer folds da Fase E (sem leakage).

Avaliar:
- macro-F1 do stacking vs macro-F1 do melhor modelo individual vs melhor ensemble de votação (ganho do meta-learner);
- concordância do stacking com `y2` vs concordância média dos modelos individuais e dos ensembles.

**Saída**: `documents/reports/stacking_results.md`. Se executada, adicionar seção 4.y no artigo (Fase K).

## Apêndice 1 — Reprodutibilidade

```text
experiments/
├── seeds.json
├── folds/{outer_r{1,2,3}.json, inner_r{1,2,3}.json, group_kfold.json}
├── <fs>_<algo>/{best_hyperparams_per_fold.json, predictions_per_fold.jsonl, metrics_per_fold.json}
├── spot_check/{results.jsonl, summary.json}
├── voting/{voting_summary.json, voting_<nome>/{predictions_per_fold.jsonl, metrics_per_fold.json}}
├── stacking/{predictions.jsonl, metrics.json}   # se Fase M rodar
└── manifest.json   # SHA-256 dos JSONL de entrada + versões
```

Total: `|A_uniao| × 2` subpastas de modelo individuais (10 se a união tiver 5 algoritmos, 12 se 6, 14 se 7), 6 subpastas de votação e os agregados de spot-check. Todos alvejam `y1`.

Ambiente já é reprodutível via `pyproject.toml` + `uv.lock`.

## Apêndice 2 — Mapeamento ao enunciado

| Exigência | Fase | Observação |
|---|---|---|
| EDA | B | ✓ concluída |
| Pré-processamento | C | dentro do pipeline de fold (sem leakage) |
| ≥5 algoritmos diversos | D | Pool comum de 7 candidatos para BC e DF: DT, RF, GB, NB, LR, LinearSVC, KNN. SVC RBF/Poly foram retirados por não serem viáveis em BC. |
| Spot-checking | D | re-desenhada: N=5 repetições com seeds {1..5}, média ± dp; top-5 selecionado por representação; união forma `A_DF ∪ A_BC` para a Fase E. |
| Otimização sem leakage | E | nested CV (3-fold inner, 5-fold outer × 3 repeats) sobre os `|A_uniao| × 2` modelos (cada algoritmo da união em ambas as representações); grids compactados para ~24 configs por algoritmo. |
| Folds idênticos entre algoritmos | E/F/G | seeds fixas, mesma divisão para todos os modelos individuais e os 6 ensembles de votação |
| Seeds | E + Apêndice 1 | salvas em `experiments/seeds.json` (modelos) e `experiments/spot_check/summary.json` (spot-check N=5) |
| Média ± desvio nos outer folds | E, F, G | 15 outer scores por modelo individual, verificação auxiliar e ensemble |
| Ensemble por votação | G | 6 ensembles (top-3/top-5 BC, top-3/top-5 DF, top-3+top-3, todos os modelos individuais) a partir das predições OOF, sem retreino; só roda depois da verificação da Fase F |
| Interpretação de um modelo | J | excedido: 2 modelos (melhor BC + melhor DF) |
| Artigo científico | K | template Moodle, ≤20 pág; seções extras se L/M rodarem |
| Reprodutibilidade | Apêndice 1 | código + dados + seeds + folds + predições |

## Apêndice 3 — Cronograma

Prazos: código + artigo **2026-05-28 23:59** · peer review **2026-06-02 a 2026-06-09** · apresentação **2026-06-16**.

Hoje **2026-05-20** — 8 dias até o prazo de 2026-05-28 23:59.

| Fase | Dias | Status |
|---|---|---|
| ~~A~~ | — | ✓ concluída |
| ~~B~~ | — | ✓ concluída |
| ~~C~~ | — | ✓ concluída |
| ~~D~~ | — | ✓ concluída com N=5 e top-5 por representação |
| ~~E~~ | — | ✓ concluída (2026-05-24) — 12/12 modelos, 15/15 folds cada |
| ~~F~~ | — | ✓ concluída (2026-05-24) — 12/12 modelos, F.1+F.2+F.3 completos com `--all --group-kfold` |
| ~~G~~ | — | ✓ concluída (2026-05-24) — 6 ensembles, melhor: `voting_top3_BC_DF` F1=0.6944, com `--all --force-recompute` |
| ~~H~~ | — | ✓ concluída (2026-05-24) — melhor_BC=bc_gradient_boosting (F1=0.6433), melhor_DF=df_gradient_boosting (F1=0.6908) |
| ~~I~~ | — | ✓ concluída (2026-05-24) — destaques globais com maior/menor concordância e maior/menor gap absoluto |
| ~~J~~ | — | ✓ concluída (2026-05-24) — PI: game_changer_count domina DF; BC: Blood Moon, Mana Vault em bracket 4 |
| K (artigo) | 3 | escrita do artigo (seções extras se L/M rodarem) |
| L (opcional) | 0,5 | OOD — vira seção extra do artigo se feito |
| M (opcional) | 1 | stacking — vira seção extra do artigo se feito |

Soma do caminho obrigatório restante (E+F+G+H+I+J+K): **8,0-9,5 dias**. Com 8 dias disponíveis, a margem é apertada — os grids ~24 da Fase E e a seleção top-5 por representação cortam o custo total da nested CV. Mitigações em ordem de prioridade: (1) não rodar Fase M (stacking, opcional); (2) não rodar Fase L (OOD, opcional); (3) fazer GroupKFold da Fase F com melhor hiperparâmetro já escolhido, sem nova busca pesada; (4) reduzir ainda mais ou pular o BC de algoritmos excepcionalmente caros se necessário; (5) cortar `voting_all` se o cálculo das predições agregadas estourar tempo (mantemos `voting_top3_*` e `voting_top5_*`).

Caso o cronograma comporte, L e M rodam **depois** do artigo (Fase K) e geram seções extras incluídas em revisão final.
