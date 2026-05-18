# Plano de Ação — Modelagem da Divergência entre Brackets de Commander

Plano sequencial para concluir o projeto descrito em [backbone.md](backbone.md), atendendo às exigências do [enunciado.pdf](enunciado.pdf). Cada fase tem **objetivo**, **saídas** e **decisões firmadas**.

**Pergunta central**: em que medida `y1` (Archidekt) diverge de `y2` (EDHPowerLevel), e quais características do deck explicam essa divergência?

## Convenção de reports por fase

Cada fase concluída deve gerar um report em `documents/` com quatro blocos mínimos: **o que era para ser feito**, **o que foi feito**, **como foi feito** e **problemas encontrados + correções**. Esses reports são insumos diretos para o artigo final e devem ser atualizados quando uma fase for reexecutada.

Reports consolidados atuais:

| Fase | Report |
|---|---|
| A | [phase_a_report.md](phase_a_report.md) |
| B | [eda_report.md](eda_report.md) + [divergence_report.md](divergence_report.md) |
| C | [preprocessing_report.md](preprocessing_report.md) |
| D | [spot_check_results.md](spot_check_results.md) após a rodada completa |

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

Implementada em [scripts/phase_b_eda_divergence.py](../scripts/phase_b_eda_divergence.py). Saídas em [documents/eda_report.md](eda_report.md), [documents/divergence_report.md](divergence_report.md) e `documents/figures/{eda,divergence}/`. Achados principais:

- Base modelável (y1, y2 ∈ {2,3,4}): **12.135 decks**.
- Concordância exata y1=y2: **60,9%** · dentro de ±1: **97,7%** · dentro de ±2: **100%**.
- `|Δ|` médio: 0,414.
- Tendência direcional: y2>y1 em 23,5% vs y2<y1 em 15,6% — calculadora classifica mais "alto" que o usuário.
- 815 decks (6,3%) com y2 ∈ {1, 5} — analisados em subseção dedicada e descartados da modelagem.

## Fase C — Pré-processamento ✓ concluída

Implementada em [scripts/preprocessing.py](../scripts/preprocessing.py) e [scripts/phase_c_filter_dataset.py](../scripts/phase_c_filter_dataset.py). Report consolidado em [preprocessing_report.md](preprocessing_report.md). O filtro C.1 foi reexecutado em 2026-05-18 e confirmou **12.135 decks incluídos** e **815 excluídos** (`y2=1`: 393 · `y2=5`: 422).

Alvo único de treino: `y1`. `y2` é mantido apenas para comparação descritiva (Fase G), nunca como feature.

### C.1 Filtros prévios
Manter y1 e y2 ∈ {2,3,4} (12.135 decks). Descartados salvos em `data/processed/archidekt/modeling_excluded.jsonl`.

### C.2 Deck Features
- Imputação: mediana do treino para `edhrec_rank_*` e `salt_*`.
- Winsorização de `price_total` no p99 do treino.
- `StandardScaler` para SVM/lineares; opcional para árvores.
- Remover features de variância zero no treino.

### C.3 Bag of Cards
- Matriz esparsa `(n_decks, n_cards)` com quantidade.
- Pruning: remover cartas com presença < `bc_min_df` no treino. Valor decidido no spot-check (testar 1, 5, 10, 20).
- **Variante TF-IDF** (backbone §10.1): fica disponível no pipeline, mas **não é ativada no spot-check da Fase D**. Será tratada depois como hiperparâmetro/variante para algoritmos que se beneficiam de ponderação por IDF (`LinearSVC`, regressão logística). Permanece desabilitada para `MultinomialNB` (assume contagens inteiras, suposição incompatível com TF-IDF).

### C.4 Antivazamento
- Toda transformação fit somente no treino do fold.
- `y2`, `delta`, `abs_delta` e todos os campos `edhpowerlevel.*` (score, power_level, etc.) **nunca** entram em X.
- `y1` é o único target; não há predição de `y2` no projeto.

## Fase D — Spot-checking ✓ concluída

Implementada em [scripts/phase_d_spot_check.py](../scripts/phase_d_spot_check.py). Saídas em [spot_check_results.md](spot_check_results.md), `experiments/spot_check/results.jsonl` e `experiments/spot_check/summary.json`.

Resultado da rodada completa após correção do desenho:

- Hold-out estratificado 80/20: 9.708 treino · 2.427 teste.
- `bc_min_df` testado para BC: 1, 5, 10, 20; escolhido **bc_min_df=10** pela média de macro-F1 em BC; TF-IDF desativado nesta fase.
- Seleção final dos 5 algoritmos feita manualmente a partir do spot-check, mantendo o **mesmo conjunto para DF e BC** para facilitar comparação direta entre representações. A diferença de performance entre os candidatos de borda não justificou usar conjuntos diferentes.
- Kernels não-lineares de SVM (`SVC(kernel='rbf')`, `SVC(kernel='poly')`) são testados **apenas em DF**. Embora o sklearn aceite sparse em alguns caminhos, o custo de kernels não-lineares é pelo menos quadrático em número de amostras e fica proibitivo/instável para BC esparso de alta dimensionalidade.
- Finalistas para DF e BC: **Gradient Boosting**, **Logistic Regression**, **Random Forest**, **LinearSVC**, **Naive Bayes**.

### D.1 Algoritmos candidatos
| Algoritmo | Viés | Classe sklearn | Obs |
|---|---|---|---|
| Decision Tree | árvore | `DecisionTreeClassifier` | — |
| Random Forest | bagging | `RandomForestClassifier` | — |
| Gradient Boosting | boosting | `GradientBoostingClassifier` / `HistGradientBoostingClassifier` | `HistGB` recomendado para BC pelo custo |
| Naive Bayes | probabilístico | `MultinomialNB` (BC) / `GaussianNB` (DF) | — |
| Logistic Regression | linear paramétrico | `LogisticRegression` | `solver='lbfgs'` (DF) / `'saga'` (BC esparso) |
| LinearSVC | margem linear | `LinearSVC` | escala bem em BC esparso |
| SVM RBF | margem não-linear | `SVC(kernel='rbf')` | **somente DF**; exige `StandardScaler`; não usado em BC por custo de kernel em matriz esparsa grande |
| SVM Poly | margem não-linear | `SVC(kernel='poly')` | **somente DF**; exige `StandardScaler`; não usado em BC por custo de kernel em matriz esparsa grande |
| KNN | distância (lazy, não-paramétrico) | `KNeighborsClassifier` | em DF aplicar após `StandardScaler`; em BC esparso esperar performance modesta (curse of dimensionality), mantemos como spot-check para confirmar empiricamente |

**9 candidatos para DF** e **7 candidatos para BC**. Cobrem os vieses indutivos do backbone §13.3 (árvore, bagging, boosting, probabilístico, linear paramétrico, margem linear, margem não-linear, distância). BC testa `HistGradientBoostingClassifier` com conversão controlada para matriz densa e limite de tempo de 10x o maior tempo já observado nas runs; se a combinação excede esse limite, ela é interrompida e removida do ranking. BC não recebe `SVC` RBF/poly porque o custo de kernels não-lineares sobre matriz esparsa de alta dimensionalidade é inadequado para este projeto.

### D.2 Procedimento
Hold-out 80/20 estratificado por `y1`, para cada representação ∈ {BC, DF}. Defaults dos algoritmos. Reportar macro-F1, accuracy, tempo. Fixar `bc_min_df` do BC nessa fase (testar 1, 5, 10, 20). TF-IDF fica desligado no spot-check.

**Saída**: `documents/spot_check_results.md`. Como `bc_min_df ∈ {1,5,10,20}` foi testado para BC, a rodada executa DF uma vez por algoritmo elegível e BC uma vez por algoritmo elegível por `bc_min_df`.

### D.3 Seleção dos 5 algoritmos finalistas
O spot-checking é a etapa de filtragem. Embora o ranking tenha sido calculado por representação, a decisão final é usar o **mesmo conjunto de 5 algoritmos** em DF e BC para preservar comparabilidade direta na Fase E:

```text
A_5 = {gradient_boosting, logistic_regression, random_forest, linear_svc, naive_bayes}
```

Justificativa: `svc_rbf` teve desempenho em DF muito próximo de `linear_svc`, mas não é viável em BC dentro deste desenho; `naive_bayes` é computacionalmente barato, interpretável e natural para BC. Como a diferença entre os candidatos de borda é pequena, priorizamos simetria e clareza experimental.

Critério de desempate / diversidade: se o ranking puro concentrar muitos algoritmos do mesmo viés (ex: 3 ensembles no topo), pode-se privilegiar diversidade de vieses indutivos. A decisão final é documentada em `documents/spot_check_results.md` com justificativa explícita.

Combinações que falharem por timeout/erro no spot-check ficam fora automaticamente. Se um algoritmo falhar em um `bc_min_df`, mas completar no `bc_min_df` escolhido, ele continua elegível para aquela configuração bem-sucedida.

## Fase E — Nested CV

Alvo único: `y1`. **10 modelos** treinados: os 5 algoritmos selecionados (`A_5`) × 2 representações (`DF`, `BC`).

### E.1 Esquema
```text
outer:  StratifiedKFold(n_splits=5, shuffle=True, random_state=r)
        r ∈ {1, 2, 3}            # 15 outer evaluations por (fs, algo)
inner:  StratifiedKFold(n_splits=3, shuffle=True, random_state=r+100)
                                 # GridSearchCV otimiza hiperparâmetros
```

Métrica de seleção interna: **macro-F1**. Métricas reportadas: macro-F1, accuracy, precision_macro, recall_macro, confusion matrix.

Folds idênticos para todos os 10 modelos em cada repeat. Seeds em `experiments/seeds.json`. Biblioteca: **scikit-learn** (`GridSearchCV` com `cv=inner`).

**Predições out-of-fold salvas** para todos os 10 modelos — reutilizadas nas Fases G e K sem retreino.

### E.2 Grids de hiperparâmetros
Grids definidos apenas para os algoritmos selecionados em §D.3. Nenhum dos algoritmos candidatos tem variante `*CV` com grids embutidos no sklearn que cubra exatamente o que queremos (`LogisticRegressionCV` existe e oferece grade automática de `Cs`, mas usamos `GridSearchCV` uniformemente para padronização). Valores comuns do sklearn user guide / Géron / Hastie listados abaixo para os candidatos — só os selecionados são realmente usados:

| Algoritmo | Grid |
|---|---|
| `DecisionTreeClassifier` | `max_depth ∈ {None, 10, 20}`, `min_samples_leaf ∈ {1, 5, 20}`, `criterion ∈ {gini, entropy}` |
| `RandomForestClassifier` | `n_estimators ∈ {100, 300}`, `max_features ∈ {sqrt, log2}`, `max_depth ∈ {None, 20}` |
| `GradientBoostingClassifier` | `n_estimators ∈ {100, 300}`, `learning_rate ∈ {0.05, 0.1}`, `max_depth ∈ {3, 5}` |
| `MultinomialNB` (BC) | `alpha ∈ {0.01, 0.1, 1.0, 10.0}` |
| `GaussianNB` (DF) | `var_smoothing ∈ np.logspace(-9, -7, 3)` |
| `LogisticRegression` | `C ∈ {0.01, 0.1, 1, 10}`, `class_weight ∈ {None, balanced}`, `solver='lbfgs'` (DF) / `'saga'` (BC esparso) |
| `LinearSVC` | `C ∈ {0.01, 0.1, 1, 10}`, `class_weight ∈ {None, balanced}` |

`GridSearchCV` no inner; trocar para `RandomizedSearchCV` se algum grid se mostrar inviável, especialmente para `gradient_boosting × BC`, que exige conversão controlada para matriz densa. `random_state=42` onde aplicável.

### E.3 GroupKFold por comandante (análise auxiliar)
Uma rodada extra com `GroupKFold(n_splits=5)` por `commander_signature`, sem repeat. Roda todos os 10 modelos com defaults (sem inner CV) para custo controlado. Reportar **gap macro-F1 (Stratified − Group)** em `documents/grouped_cv_report.md` — gap pequeno indica padrões gerais; gap grande indica dependência do modelo de comandantes específicos vistos no treino (backbone §13.4). O gap em si é resultado de interesse para a discussão.

### E.4 Testes estatísticos
- Múltiplos algoritmos: Friedman + Nemenyi sobre os 15 outer scores.
- Pareado: Wilcoxon signed-rank por fold.

**Saídas**: `experiments/<fs>_<algo>/{best_hyperparams_per_fold.json, predictions_per_fold.jsonl, metrics_per_fold.json}`, `documents/statistical_tests.md`.

## Fase F — Melhor modelo por representação

Ranquear os 10 modelos por macro-F1 médio nos outer folds. Selecionar **um modelo por representação**:

```text
melhor_BC = argmax_{alg ∈ A_5} macro_F1(alg, BC, y1)
melhor_DF = argmax_{alg ∈ A_5} macro_F1(alg, DF, y1)
```

Desvio padrão como desempate (estabilidade). Decisão registrada manualmente em `documents/best_models.md`. Esses dois modelos receberão interpretabilidade (Fase H).

Comparações no relatório: BC vs DF para `y1`; tabela de macro-F1 dos 10 modelos.

## Fase G — Comparação das predições dos modelos com a calculadora

**Descritivo, sem retreino**. Reutiliza as predições out-of-fold dos 10 modelos da Fase E e compara contra `y2`:

```text
para cada um dos 10 modelos:
  ŷ1 = predição out-of-fold (treinado em y1)
  comparar ŷ1 vs y2 por: concordância exata, ±1, macro-F1 contra y2,
                          |Δ| médio, matriz de confusão ŷ1 × y2
```

**Saída**:
- Tabela completa com os 10 modelos (linha por modelo, colunas com cada métrica de concordância com `y2`).
- Discussão narra 2-3 modelos de destaque (ex: o que mais concorda com y2, o que menos concorda, e o que tem maior gap entre `macro-F1(y1)` e `concordância(y2)`).
- `documents/model_vs_calculator.md` + figuras `documents/figures/model_vs_calc/`.

Subset analysis: para cada modelo, performance no subset `y1 == y2` vs `y1 ≠ y2`.

## Fase H — Interpretabilidade

**Dois modelos**: `melhor_BC` e `melhor_DF` (definidos na Fase F).

Para **Deck Features**:
- Feature importance (importance nativo para árvores/ensembles, coeficientes para lineares, permutation importance como fallback universal).
- Top 10-15 features com direção do efeito.
- Features associadas a divergência entre `ŷ1` do modelo e `y2` (calculadora).

Para **Bag of Cards**:
- Top-20 cartas mais importantes por classe prevista.
- Cartas associadas a divergência entre `ŷ1` e `y2`.

**Saída**: `documents/interpretability.md`.

## Fase I — Artigo

Escrito imediatamente após a interpretabilidade, com o resultado principal já fechado. Se Fase J (OOD) ou Fase K (stacking) forem executadas depois, **adicionar seções extras ao artigo** descrevendo esses experimentos (insertable nas seções de Resultados e Discussão).

Template Moodle (coluna única, ≤20 pág.):
1. Introdução · 2. Trabalhos relacionados · 3. Métodos (coleta, escopo, BC/DF, nested CV, reprodutibilidade) · 4. Resultados (B, E, F, G, H) · 5. Discussão · 6. Conclusão · 7. Referências · 8. Apêndices.

Seções extras condicionais:
- 4.x **Generalização fora da distribuição** — só se Fase J rodar.
- 4.y **Stacking** — só se Fase K rodar.

Se usar IA generativa: `documents/ai_usage.md` com prompts e limitações.

## Fase J — Out-of-distribution (opcional)

Coletar decks com 500 ≤ views < 1000. Aplicar melhores modelos **sem retreinar**. Comparar macro-F1 dentro vs fora.

**Saída**: `documents/ood_report.md`. Se executada, adicionar seção 4.x no artigo (Fase I).

## Fase K — Stacking (opcional, se houver tempo)

Movida para o final do plano por ser estritamente complementar — não é exigida pelo enunciado e seu valor depende de termos os 16 modelos individuais bem caracterizados e a comparação contra `y2` já fechada. Só faz sentido depois de F, G e H.

Base learners: os 10 modelos da Fase E (todos prevendo y1).
Meta-learner: `LogisticRegression`.
Meta-target: y1.
Folds: os mesmos outer folds da Fase E (sem leakage).

Avaliar:
- macro-F1 do stacking vs macro-F1 do melhor modelo individual (ganho do ensemble);
- concordância do stacking com `y2` vs concordância média dos modelos individuais.

**Saída**: `documents/stacking_results.md`. Se executada, adicionar seção 4.y no artigo (Fase I).

## Apêndice 1 — Reprodutibilidade

```text
experiments/
├── seeds.json
├── folds/{outer_r{1,2,3}.json, inner_r{1,2,3}.json, group_kfold.json}
├── <fs>_<algo>/{best_hyperparams_per_fold.json, predictions_per_fold.jsonl, metrics_per_fold.json}
├── stacking/{predictions.jsonl, metrics.json}   # se Fase K rodar
└── manifest.json   # SHA-256 dos JSONL de entrada + versões
```

Total: 10 subpastas de modelo (5 algoritmos selecionados × 2 representações), todas alvejando `y1`.

Ambiente já é reprodutível via `pyproject.toml` + `uv.lock`.

## Apêndice 2 — Mapeamento ao enunciado

| Exigência | Fase | Observação |
|---|---|---|
| EDA | B | ✓ concluída |
| Pré-processamento | C | dentro do pipeline de fold (sem leakage) |
| ≥5 algoritmos diversos | D | DF testa 9 candidatos: DT, RF, GB, NB, LR, LinearSVC, SVC-RBF, SVC-Poly, KNN. BC testa 7 candidatos: DT, RF, GB, NB, LR, LinearSVC, KNN. |
| Spot-checking | D | ✓ concluída; hold-out 80/20 sobre `y1`; filtrou o conjunto final `A_5` usado nas duas representações. |
| Otimização sem leakage | E | nested CV (3-fold inner, 5-fold outer × 3 repeats) sobre 10 modelos (5 algoritmos × 2 representações) |
| Folds idênticos entre algoritmos | E.1 | seeds fixas, mesma divisão para os 10 modelos |
| Seeds | E + Apêndice 1 | salvas em `experiments/seeds.json` |
| Média ± desvio nos outer folds | E, F | 15 outer scores por modelo |
| Interpretação de um modelo | H | excedido: 2 modelos (melhor BC + melhor DF) |
| Artigo científico | I | template Moodle, ≤20 pág; seções extras se J/K rodarem |
| Reprodutibilidade | Apêndice 1 | código + dados + seeds + folds + predições |

## Apêndice 3 — Cronograma

Prazos: código + artigo **2026-05-28 23:59** · peer review **2026-06-02 a 2026-06-09** · apresentação **2026-06-16**.

Hoje **2026-05-18** — 10 dias.

| Fase | Dias | Status |
|---|---|---|
| ~~A~~ | — | ✓ concluída |
| ~~B~~ | — | ✓ concluída |
| ~~C~~ | — | ✓ concluída |
| ~~D~~ | — | ✓ concluída |
| E | 2-3 | 10 modelos (5 algoritmos × 2 representações) com nested CV |
| F | 0,5 | a fazer |
| G | 0,5 | descritivo, sem retreino |
| H | 1,5 | interpretabilidade (2 modelos) |
| I (artigo) | 3 | escrita do artigo (seções extras se J/K rodarem) |
| J (opcional) | 0,5 | OOD — vira seção extra do artigo se feito |
| K (opcional) | 1 | stacking — vira seção extra do artigo se feito |

Soma do caminho obrigatório (C+D+E+F+G+H+I): **9,5-10,5 dias**. Com 10 dias disponíveis, margem é apertada mas viável (spot-check em §D.3 já filtra para 5 algoritmos, reduzindo o custo da nested CV). Mitigações em ordem de prioridade: (1) não rodar Fase K (stacking, opcional); (2) não rodar Fase J (OOD, opcional); (3) cortar E.3 (GroupKFold auxiliar); (4) usar `RandomizedSearchCV` em vez de `GridSearchCV` no inner CV para acelerar Fase E; (5) reduzir grids dos algoritmos caros se algum dos 5 selecionados for KNN×BC.

Caso o cronograma comporte, J e K rodam **depois** do artigo (Fase I) e geram seções extras incluídas em revisão final.
