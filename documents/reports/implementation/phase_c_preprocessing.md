# Implementação — Fase C: Pré-processamento

> Implementation report. **Público**: colaborador novo ou agente LLM que vai mexer em filtros, imputação, scaling, pruning de cartas ou antivazamento. Resultados (totais incluídos/excluídos por rodada) vivem em [../results/phase_c_preprocessing.md](../results/phase_c_preprocessing.md).

## Objetivo

Congelar a base modelável (y1, y2 ∈ {2,3,4}) e expor transformadores sklearn-compatíveis (`fit`/`transform`) que as Fases D e E aplicam **fold a fold**, sem vazamento de teste pro treino. O alvo único de treino é `y1` (Archidekt). `y2` é preservado para comparação descritiva (Fase G), nunca como feature.

## O que foi construído

| Componente | Arquivo | Responsabilidade |
|---|---|---|
| Filtro C.1 | [scripts/phase_c_filter_dataset.py](../../../scripts/phase_c_filter_dataset.py) | Lê `deck_features.jsonl`, separa incluídos/excluídos por reason (`y1_out_of_range`/`y2_out_of_range`), grava `modeling_snapshot_ids.json` (incluídos) + `modeling_excluded.jsonl` (audit) + `modeling_dataset_manifest.json` (totais) + auto-gera o results report |
| Helpers | [scripts/preprocessing.py](../../../scripts/preprocessing.py) | `iter_jsonl`, `write_jsonl`, `y1_value`, `y2_value`, `modeling_filter_reason`, `split_modeling_records`, `is_leakage_column`, `target_vector` |
| Transformador DF | `DeckFeaturePreprocessor` em `preprocessing.py` | Imputação por mediana (edhrec_rank_*, salt_*), winsorização p99 (price_total), drop variance-zero, StandardScaler opcional |
| Transformador BC | `BagOfCardsPreprocessor` em `preprocessing.py` | Vocabulário aprendido só no treino, pruning por `min_df`, matriz CSR, TF-IDF opcional |

## Como foi construído (decisões + porquês)

### Separação em DOIS pontos: filtro vs transformações

A Fase C tem duas naturezas distintas:

1. **C.1 — filtro estático**: roda uma vez por snapshot, produz `modeling_snapshot_ids.json`. Vive em `phase_c_filter_dataset.py`.
2. **C.2/C.3/C.4 — transformações por fold**: rodam **dentro** de Phase D e Phase E, dentro de cada outer/inner fold. Vivem em `preprocessing.py` como classes sklearn-compatíveis.

Por que separar? Porque tentar pré-computar imputação/scaling/pruning aqui produziria **vazamento**: a mediana da base inteira contamina folds de teste. Os transformadores precisam ver só o treino do fold quando fazem `.fit()`. Empacotá-los em classes com API `fit`/`transform` permite que sklearn `Pipeline` faça a coisa certa automaticamente.

### Por que descobrir colunas dinamicamente em `DeckFeaturePreprocessor.fit`?

`deck_features.jsonl` tem ~114 colunas potenciais, mas algumas (game_changer_count, mass_land_denial_count, etc.) podem virar zero-variance dependendo do filtro. Ao invés de hardcodar a lista, `infer_deck_feature_columns()` percorre os records procurando colunas numéricas, **excluindo explicitamente** o que está em `is_leakage_column()`:

```python
TARGET_COLUMNS  = {"archidekt_edh_bracket", "y1"}            # y1 não é feature
LEAKAGE_COLUMNS = {"edhpowerlevel", "edhpowerlevel_bracket", # y2 e derivados
                   "y2", "delta", "abs_delta"}
METADATA_COLUMNS = {"snapshot_id", "deck_id", ...}
# Bloqueio por prefixo:
name.startswith("edhpowerlevel.") or name.startswith("epl_")
```

Esse bloqueio é **defesa em profundidade**. Se alguém adicionar uma nova feature derivada do EDHPowerLevel (`epl_score_diff` etc), ela é bloqueada automaticamente sem precisar atualizar o filtro.

### Imputação só pra `edhrec_rank_*` e `salt_*` — por quê

Outras features são contagens (creature_count, land_count, ...) que **não podem ser NaN** — se uma carta não aparece, a contagem é 0. Já EDHREC rank e salt vêm do oracle e podem faltar para cartas raras/novas. Imputar pela mediana do **treino** é leakage-safe e preserva a forma da distribuição.

### Winsorização p99 do `price_total`

`price_total` tem cauda longa: deck mediano custa ~150-300 USD, mas alguns chegam a 50k USD. Sem winsorização, modelos lineares e KNN sofrem; árvores se viraram bem mas ainda assim a feature fica menos informativa que o necessário. Cap no p99 do treino: a maioria dos decks fica intacta, só o tail extremo é cortado.

### `StandardScaler` opcional

Modelos sensíveis à escala (logistic_regression, linear_svc, knn) precisam de scaling. Árvores (decision_tree, random_forest, gradient_boosting) e NB (gaussian) **não** — scaling em árvores pode até prejudicar a interpretabilidade dos splits. A Fase D/E decide o flag `scale=True/False` por algoritmo via `needs_df_scaling()`.

### `BagOfCardsPreprocessor` — por que vocabulário no treino?

Se aprendêssemos o vocabulário no dataset inteiro, cartas que só aparecem em decks de teste contaminariam o espaço de features. `BagOfCardsPreprocessor.fit()` constrói o vocabulário só dos records passados (treino do fold). No `transform()` de teste, cartas fora do vocabulário são **silenciosamente ignoradas** — que é o comportamento correto (modelo nunca viu essa carta no treino).

### `min_df` pruning

Cartas raríssimas (presença < `min_df` decks no treino do fold) viram colunas constantes-zero que só inflam dimensão sem aprender nada. Phase D testa `bc_min_df ∈ {5, 10, 20}` e escolhe pelo macro-F1 médio. Phase E usa o vencedor.

### TF-IDF como hiperparâmetro, não default

Commander é majoritariamente singleton (`Sol Ring = 1`, `Demonic Tutor = 1`). A componente TF do TF-IDF tende ao binário; o ganho real vem do IDF que pondera cartas raras. Faz sentido pra `LinearSVC` (margem linear se beneficia de ponderação). **Não faz** sentido pra `MultinomialNB` (assume contagens inteiras). Por isso TF-IDF é **opt-in** via `use_tfidf=True`, e a Fase D mantém desligado pra isolar o efeito de algoritmo vs vocabulário.

### Antivazamento (C.4) — três camadas

1. **Filtro de coluna** (`is_leakage_column`): qualquer coluna que comece com `edhpowerlevel.`, `epl_`, ou esteja nas constantes LEAKAGE/TARGET/METADATA, é dropada na inferência.
2. **`fit`-only no treino**: median, p99, scaler params e vocabulário BC são aprendidos somente no treino do fold.
3. **Mesmos folds entre algoritmos**: Phase E usa `experiments/folds.json` global, e cada algoritmo na nested CV vê exatamente as mesmas divisões inner/outer.

### Re-execução determinística

Phase C não tem aleatoriedade: `iter_jsonl(features_path)` percorre em ordem do arquivo. Se `deck_features.jsonl` é byte-idêntico (vem do snapshot do Drive), `modeling_snapshot_ids.json` é byte-idêntico → Phase D/E reproduz exatamente o mesmo conjunto modelável.

## Pontos de extensão / armadilhas

- **NÃO mover transformações pra Phase C runtime**: imputar uma vez antes da Fase D quebra a separação treino/teste em todos os folds. Os transformadores **têm** que ser executados por fold.
- **Adicionar nova feature derivada de y2**: vai dar errado silenciosamente se o nome não for capturado por `is_leakage_column`. Se for derivada, prefira nomeá-la com prefixo `epl_` para ser auto-bloqueada.
- **Mudar mediana → média para imputação**: mediana é robusta a outliers; média não. Para `edhrec_rank_*` (que vai até 10000+) e `salt_*` (até ~4) isso importa.
- **Reduzir o p99**: p95 cortaria preço médio também — mantenha p99 a menos que tenha justificativa empírica.
- **Trocar `use_tfidf=True` como default**: vai quebrar `MultinomialNB`. Mantenha como hiperparâmetro de pipeline.
- **Auto-regeneração do report**: o results report é regerado a cada `init`. Decisões de método (este arquivo) NÃO são regerada — é hand-written. Se você muda imputação/scaling/pruning, vem aqui e atualize a seção correspondente.

## Problemas encontrados e correções

| Problema | Diagnóstico | Correção |
|---|---|---|
| `preprocessing.py` não existia inicialmente | Console script `phase-c-filter-dataset` apontava pra arquivo inexistente | Criado com transformadores sklearn-compatíveis reutilizáveis |
| Risco de vazamento de y2 ou campos da calculadora | `infer_deck_feature_columns` pegaria qualquer coluna numérica | `is_leakage_column` bloqueia por nome exato + prefixo (`edhpowerlevel.`, `epl_`) |
| Mediana/p99/vocabulário fitados no dataset inteiro | Vazamento treino → teste em CV | Transformadores seguem API `fit/transform`; toda estatística é aprendida no `fit` |
| `categories` (§11.1.F do backbone) gerava feature ruim | 22,8% dos decks não usavam vocabulário funcional padrão; convenções inconsistentes | Seção F removida do feature builder; campo continua em `decks.jsonl` para análise descritiva |
| `customCmc` poluindo curva | 18,7% dos decks override CMC subjetivamente | Pipeline usa só `oracleCard.cmc`; `customCmc` preservado para auditoria |
