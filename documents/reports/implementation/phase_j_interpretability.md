# Implementação — Fase J: Interpretabilidade dos Melhores Modelos

> Implementation report. Público: colaborador novo ou LLM. Resultados automáticos em [../results/phase_j_interpretability.md].

## Objetivo

Interpretar os dois melhores modelos selecionados na Fase H (`bc_gradient_boosting` e `df_gradient_boosting`) para responder:

1. **DF**: quais propriedades estruturais do deck (features agregadas) o modelo usa para prever o bracket comunitário? Com que direção?
2. **BC**: quais cartas o modelo associa a cada bracket previsto? Quais cartas estão ligadas à concordância ou divergência entre ŷ1 e y2?

A interpretação é apresentada como **hipótese analítica**, não como prova causal (backbone §17).

## O que foi construído

| Componente | Arquivo | Responsabilidade |
|---|---|---|
| Script principal | `scripts/phase_j_interpretability.py` | Treino final, PI, lift, divergência, relatório |
| Entrypoint CLI | `pyproject.toml` → `phase-j-interpretability` | `uv run --no-sync python -m scripts.phase_j_interpretability` |
| Results report | `documents/reports/results/phase_j_interpretability.md` | Auto-gerado a cada execução |
| Artefatos intermediários | `experiments/phase_j_interpretability/` | PI raw, lift por classe, divergência DF e BC |

## Como foi construído

### Decisão 1: Modelo final treinado em todos os dados

A Fase E **não serializa modelos** — salva apenas predições e hiperparâmetros. Para extrair importância de features é necessário um modelo ajustado ao dataset. A prática padrão é:

> Fase E (nested CV) → **estimativas de generalização** (irrelevante para interpretação)
> Fase J (treino final em todos os dados) → **interpretação** (não reporta métricas de generalização)

Hiperparâmetros usados: **configuração modal** dos 15 outer folds de cada modelo. Para ambos os modelos a configuração modal foi idêntica: `{class_weight: balanced, learning_rate: 0.05, max_iter: 200, max_leaf_nodes: 31}`.

### Decisão 2: Permutation importance para o DF

`HistGradientBoostingClassifier` **não expõe `feature_importances_`** MDI diretamente (diferente de `RandomForestClassifier` ou `DecisionTreeClassifier`). A alternativa recomendada pelo sklearn é `sklearn.inspection.permutation_importance`.

Para evitar inflação por overfitting, o PI é calculado sobre um **hold-out estratificado 80/20** (n_val=2.427 decks), não sobre os próprios dados de treino.

O PI é computado sobre a matriz X já transformada pelo preprocessor (após imputação, winsorização e remoção de variância zero), e depois mapeado de volta aos nomes de features via `DeckFeaturePreprocessor.output_feature_names_`.

`game_changer_count` emergiu com PI muito superior aos demais (0.228 vs 0.029 do segundo), confirmando que a flag de "Game Changer" do Archidekt é o preditor dominante do bracket comunitário.

### Decisão 3: Lift analysis para BC (em vez de permutation importance)

`HistGradientBoostingClassifier` em BC exige conversão densa do esparso (~11k features). Permutation importance seria `11k features × 10 repeats × 12k decks × predict()` = inviável em horas.

A alternativa: **lift analysis sobre as 36.405 predições OOF existentes** (sem retreino adicional para BC):

```
lift[k][carta] = P(carta presente | ŷ1 = k) / P(carta presente)
```

Um lift de 3.0 significa que a carta é 3x mais frequente em decks previstos como bracket k do que na base geral.

Filtros aplicados:
- Cartas com menos de `min_deck_count=10` decks únicos são excluídas (alinhado com `bc_min_df=10` do treino)
- Frequências são calculadas sobre todas as 36.405 entradas OOF (3 repeats × 12.135 decks), não deduplicated — mais estabilidade estatística

### Decisão 4: Suavização Laplace para lifts de divergência

Na análise de divergência (concordante vs divergente, super vs sub-previstos), cartas que aparecem em um grupo mas não no outro geravam lifts astronomicamente grandes (e.g., 17 milhões). Adicionamos **suavização Laplace** com `smooth = 5e-4`:

```
lift = (freq_base + smooth) / (freq_ref + smooth)
```

Isso mantém os lifts em escala interpretável (máx ~42x observado) enquanto cards com frequência zero no grupo de referência ainda emergem no topo — só com lift limitado.

### Decisão 5: Identificadores de carta

`bag_of_cards.jsonl` usa **oracle_uids** (UUIDs) como identificadores, não nomes de cartas. O script carrega `cards.jsonl` (`oracle_uid → oracle_name`) para converter UUIDs em nomes legíveis no relatório.

### Direção do efeito (DF)

Para cada feature do top-15, calculamos `mean(feature | y_pred = k)` para k ∈ {2, 3, 4} usando o val set. Isso permite ver, por exemplo:

- `game_changer_count`: 0.001 (bracket 2) → 1.499 (bracket 3) → 4.146 (bracket 4) — direção clara e monótona
- `land_count`: 35.4 → 35.0 → 34.2 — direção tênue, mais terras = ligeiramente menos competitivo

### Divergência ŷ1 vs y2 (DF)

Usando as 36.405 predições OOF do `df_gradient_boosting`, dividimos em grupos:
- **Concordante** (ŷ1 == y2): 23.297 entradas
- **Divergente** (ŷ1 ≠ y2): 13.108 entradas

Para cada feature, calculamos `mean(feature | concordante)` vs `mean(feature | divergente)` e o delta normalizado pelo desvio padrão geral. As 10 features com maior `|Δ normalizado|` são mostradas.

Achado principal: `game_changer_count` é muito mais alto em decks concordantes (2.165 vs 0.939) — quando há muitos Game Changers, modelo e calculadora tendem a concordar no bracket alto. A divergência ocorre em decks sem esse sinal claro.

## Resultados principais (2026-05-24)

### df_gradient_boosting

| Destaque | Feature | Valor |
|---|---|---|
| Mais importante (PI) | `game_changer_count` | 0.2281 |
| 2ª mais importante | `mass_land_denial_count` | 0.0288 |
| 3ª mais importante | `unique_atomic_combo_refs_count` | 0.0143 |
| Maior Δ normalizado (divergência) | `game_changer_count` | −0.558 |

### bc_gradient_boosting

| Destaque | Cartas (exemplos) |
|---|---|
| Bracket 2 top lift | Owlbear, Bear Cub — tema tribal/casual |
| Bracket 4 top lift | Blood Moon, Chrome Mox, Mana Vault, Imperial Seal |
| Concordante top lift | Blood Moon, Imperial Seal, Force of Will — stax/cEDH |
| Sub-previsto (ŷ1 < y2) | Vorinclex, Expropriate, Time Stretch — turno extra/power |

## Comandos de execução

```bash
uv run --no-sync python -m scripts.phase_j_interpretability
# Com mais PI repeats (mais estável, mais lento):
uv run --no-sync python -m scripts.phase_j_interpretability --n-pi-repeats 20
```

## Pontos de extensão / armadilhas

- **Não usar para generalização**: o modelo final treinado aqui é para interpretação. Métricas de generalização vêm exclusivamente da Fase E.
- **Re-execução**: sempre regera tudo do zero. Idempotente.
- **BC permutation importance**: não implementado por inviabilidade computacional. Se sklearn adicionar suporte nativo a importâncias para HistGB (ex: via `feature_importances_` MDI), avaliar a inclusão no futuro.
- **Lift vs frequência absoluta**: o lift captura quão "específica" uma carta é para o bracket k, mas não quão comum ela é. `game_changer_count` tem tanto lift quanto frequência relevante — a combinação é o que importa para a narrativa do artigo.
- **Suavização Laplace**: o valor `smooth=5e-4` é um compromisso entre evitar lifts infinitos e preservar a ordenação das cartas. Se mudado, verificar se os tops se alteram significativamente.
- **Nunca usar y2 como target**: o campo `y2` das OOF predictions é usado apenas para classificar entradas em concordante/divergente. Nenhuma `.fit()` é chamada com y2.
