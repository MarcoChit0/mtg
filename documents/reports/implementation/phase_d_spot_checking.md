# Implementação — Fase D: Spot-checking

> Implementation report. **Público**: colaborador novo ou agente LLM que vai mexer no pool de algoritmos, seeds, hold-out, agregação ou regra de top-5. Resultados (média±dp de cada combinação, top-5 selecionado) vivem em [../results/phase_d_spot_checking.md](../results/phase_d_spot_checking.md).

## Objetivo

Filtrar empiricamente o pool de algoritmos candidatos antes da Fase E (otimização cara). A entrega da Fase D é uma seleção `top5_DF` + `top5_BC` (lidos pelo Phase E via `--from-spot-check`); a união `A_DF ∪ A_BC` define quais algoritmos treinam em Phase E.

## O que foi construído

Um único script, `scripts/phase_d_spot_check.py` (~500 linhas):

| Saída | Conteúdo |
|---|---|
| `documents/reports/results/phase_d_spot_checking.md` | Auto-gerado: tabela média±dp por combinação, ranking por representação, top-5 selecionado, problemas |
| `experiments/spot_check/results.jsonl` | Uma linha por `(algoritmo, representação, bc_min_df, seed)` |
| `experiments/spot_check/combinations.jsonl` | Uma linha por `(algoritmo, representação, bc_min_df)` com agregado (média/dp das 5 seeds) |
| `experiments/spot_check/summary.json` | Parâmetros + `best_bc_min_df` + rankings + chave `selection` com `top5_DF`/`top5_BC`/`union` (consumido pelo Phase E) |

## Como foi construído (decisões + porquês)

### Pool de 7 candidatos — por que esses e não outros

Backbone §13.3 + redesign de 2026-05-19 (orientação direta da professora):

```
ALGORITHMS = (
    "decision_tree", "random_forest", "gradient_boosting",
    "naive_bayes", "logistic_regression", "linear_svc", "knn",
)
```

| Algoritmo | Viés indutivo |
|---|---|
| Decision Tree | Árvore |
| Random Forest | Bagging |
| Gradient Boosting | Boosting |
| Naive Bayes (Multinomial em BC, Gaussian em DF) | Probabilístico |
| Logistic Regression | Linear paramétrico |
| LinearSVC | Margem linear |
| KNN | Distância (lazy) |

Cobre os 7 vieses distintos do backbone. **SVC RBF e SVC Poly foram explicitamente removidos** em 2026-05-19 porque:

1. Não escalam para BC esparso de alta dim (~15k features × 12k decks). O kernel é pelo menos O(n²) em amostras.
2. A regra do projeto pós-redesign é: **só algoritmos viáveis em ambas as representações**. RBF/Poly só roda em DF → fora.

Margem não-linear continua representada via `GradientBoosting` e `KNN`.

### N=5 repetições com seeds {1,2,3,4,5}

Antes era N=1 (uma única hold-out 80/20 com seed=42). A professora pediu N=5 com seeds determinísticas {1..5} para reportar **média ± desvio padrão**, não um número único que pode ser sortudo. Cada seed:

- Faz `train_test_split(stratify=y, random_state=seed)`.
- Instancia o estimador com `random_state=seed` (quando aceita).
- Treina, prediz, computa macro-F1, accuracy, precision_macro, recall_macro.

Agregação: 5 valores por combinação → `mean(ddof=1)` + `std(ddof=1)`.

### Por que hold-out 80/20 e não CV aqui

Phase D é **filtro**, não otimização. O custo de rodar 7 × 2 × 3 × 5 = 210 combinações com defaults é ~30 min; com CV de 5 folds seria ~2,5h. Para a decisão de top-5, hold-out estratificado com 5 repetições já entrega média±dp suficientemente estável.

### `bc_min_df ∈ {5, 10, 20}` como hiperparâmetro da fase

BC tem ~15k cartas distintas. Cartas raras viram colunas zero quase em todo lugar e só inflam dimensão. Testamos três thresholds porque o valor ótimo depende do dataset. A escolha (`best_bc_min_df`) é feita aqui e propagada pra Fase E:

```python
def select_best_bc_min_df(combinations):
    # Para cada bc_min_df, média do macro-F1 sobre (algoritmo × seeds) em BC
    # Empate vence o primeiro (5 antes de 10 antes de 20)
```

### Ranking por representação INDEPENDENTE

Antes (design pré-redesign): um único ranking conjunto produzia `A_5` simétrico (mesmos 5 em BC e DF). Agora:

```python
rankings = {
    "DF": ranking_for_representation(combinations, "DF", bc_min_df_filter=None),
    "BC": ranking_for_representation(combinations, "BC", bc_min_df_filter=best_bc_min_df),
}
top5_DF = selected_algorithms(rankings["DF"])
top5_BC = selected_algorithms(rankings["BC"])
union = sorted(set(top5_DF) | set(top5_BC))
```

A união pode ter 5 a 7 algoritmos. Phase E treina **cada algoritmo da união em ambas as representações** (`|union| × 2` modelos: 10 a 14).

### Tie-break determinístico

`sorted(rows, key=lambda r: (r["eligible"], r["macro_f1_mean"] or -inf), reverse=True)` — Python sort é estável. Quando dois algoritmos têm o mesmo macro_f1_mean, a ordem original (que é `tuple ALGORITHMS` fixa) decide. Isso garante que rodar o mesmo dataset em duas máquinas produz o mesmo top-5.

### Logística de execução

- `n_jobs=-1` é passado para `RandomForestClassifier` e similares. RF com `random_state` fixo é determinístico mesmo paralelo (sklearn semeia cada árvore com derivação determinística do `random_state` principal).
- `HistGradientBoostingClassifier` em BC: matriz esparsa CSR → não suporta `HistGB` diretamente. Conversão controlada para `dense` antes do `fit` (ver `if algorithm == "gradient_boosting": x_train = x_train.toarray()`).
- Erros isolados: se uma combinação quebra (`LinearSVC` não converge, etc.), só essa combinação fica fora; as outras continuam. O report lista todos os erros.

### Bundle `spot_check` no Drive

Após a Fase D rodar, [`run_pipeline.py`](../../../scripts/run_pipeline.py) (no modo não-`--run-local`) chama `sync_experiments_drive.py upload-bundle spot_check`, que zipa `experiments/spot_check/` e sobe pra `mtg-experiments:spot_check.zip`. Colaboradores rodando Phase E com `--from-spot-check` consomem essa seleção via Drive público — ver `documents/reports/implementation/phase_e_nested_cv.md`.

## Pontos de extensão / armadilhas

- **Adicionar algoritmo ao pool**: editar `ALGORITHMS` em `phase_d_spot_check.py` E também `SELECTED_ALGORITHMS` em `phase_e_nested_cv.py` + adicionar entrada em `full_param_grid()` da Fase E. Sem isso, a união no spot-check vai conter um algoritmo que Phase E não sabe treinar.
- **Mudar seeds**: vai quebrar a reprodutibilidade cross-machine se o colaborador publicou bundle com seeds antigas. Pra propagar, todo mundo precisa rodar de novo.
- **Adicionar mais valores de `bc_min_df`**: o custo escala linearmente em BC. Adicionar `30, 50` aumenta runtime mas não quebra nada — só ajusta o ranking.
- **Trocar hold-out por CV**: mudaria o significado de "média±dp" — passa a ser média sobre folds CV, não sobre seeds de hold-out. Discutir com a professora antes.
- **NÃO usar `y2` aqui**: o filtro C.1 já garante que só decks com y1, y2 ∈ {2,3,4} entram, mas `target_vector(features)` usa `y1` exclusivamente. Adicionar `y2` quebraria a linha base do projeto inteiro.
- **NÃO publicar resultados parciais do Phase D no Drive**: o bundle é publicado pelo `run_pipeline` no fim do `spot-checking`. Subir intermediário confunde colaboradores que veem `summary.json` incompleto.

## Problemas encontrados e correções

| Problema | Diagnóstico | Correção |
|---|---|---|
| Design original com SVC RBF/Poly (só DF) | Quebrava simetria; pool em BC e DF eram diferentes (7 vs 9) | Pool reduzido para 7 viáveis em ambas; SVC RBF/Poly removidos completamente em 2026-05-19 |
| Design original com `A_5` único | Ranking conjunto poderia ocultar algoritmos bons em só uma representação | Ranking separado por representação; união ∪ alimenta Fase E |
| Design original com N=1 | Macro-F1 num único hold-out é alto-variância | N=5 com seeds determinísticas + média±dp |
| `HistGradientBoosting` em BC esparso | API não aceita CSR diretamente | Conversão controlada para `dense` antes do `fit` (custo de memória aceitável a 12k×11k decks×cartas) |
| `MultinomialNB(alpha)` em valores muito pequenos | Estabilidade numérica | Phase D usa defaults; o sweep de alpha acontece só em Phase E (`{1e-3, ..., 100}`) |
