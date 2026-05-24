# Implementação — Fase I: Comparação das Predições dos Modelos com a Calculadora

> Implementation report. Público: colaborador novo ou LLM. Resultados automáticos em [../results/phase_i_model_vs_calculator.md].

## Objetivo

Comparar as predições OOF `ŷ1` (modelos treinados em `y1`) contra `y2` (calculadora EDHPowerLevel) de forma **descritiva** — sem retreino, sem novos folds, sem uso de `y2` como alvo de treinamento (backbone §5). O objetivo é medir o grau de alinhamento entre percepção comunitária aprendida pelos modelos e avaliação automática da calculadora, e identificar quais modelos capturam sinais mais próximos ou mais distantes da lógica objetiva da calculadora.

## O que foi construído

| Componente | Arquivo | Responsabilidade |
|---|---|---|
| Script principal | `scripts/phase_i_model_vs_calculator.py` | Métricas de concordância, subset analysis, matrizes de confusão, relatório |
| Entrypoint CLI | `pyproject.toml` → `phase-i-model-vs-calculator` | `uv run --no-sync python -m scripts.phase_i_model_vs_calculator` |
| Results report | `documents/reports/results/phase_i_model_vs_calculator.md` | Auto-gerado a cada execução |

Nenhum artefato gerado em `experiments/` — análise puramente descritiva sobre o que já existe.

## Como foi construído

### Fonte de dados

As predições OOF (`predictions_per_fold.jsonl`) já contêm o campo `y2` por linha, gravado na Fase E a partir de `deck_features.jsonl`. `y2` é estável por deck (verificado: 0 inconsistências entre os 3 repeats). Total: 36.405 entradas = 12.135 decks × 3 repeats.

### Métricas calculadas por modelo (backbone §13.7 + action plan §I)

Para cada um dos 12 modelos individuais + 6 ensembles (18 total):

- **Concordância exata**: `mean(ŷ1 == y2)`
- **Concordância ±1**: `mean(|ŷ1 − y2| ≤ 1)`
- **|Δ| médio**: `mean(|ŷ1 − y2|)`
- **Macro-F1 vs y2**: macro-F1 com `y2` como "verdade" (descritivo — não implica que y2 é ground truth)
- **Matriz de confusão ŷ1 × y2**: linhas = ŷ1, colunas = y2

### Análise por subconjunto (action plan §I)

Filtra as predições em dois grupos:
- **Concordante** (`y_true == y2`): decks onde comunidade e calculadora atribuíram o mesmo bracket
- **Discordante** (`y_true != y2`): decks onde as fontes divergem

Para cada grupo, calcula a concordância exata entre `ŷ1` e `y2`. Isso permite ver: nos decks onde a comunidade já concordava com a calculadora, o modelo acerta mais? E nos discordantes, qual fonte o modelo "prefere" imitar?

### Gap desempenho(y1) vs concordância(y2)

Métrica derivada: `gap = macro_f1_y1 − exact_agreement_y2`. Gap positivo grande = modelo aprendeu particularidades de `y1` que não se traduzem em alinhamento com a calculadora. Gap negativo = modelo acerta mais com a calculadora do que seu F1 em `y1` sugeriria.

### Narrativa automática

O relatório identifica automaticamente 3 modelos de destaque:
1. **Maior concordância com y2** — modelo mais alinhado à calculadora
2. **Menor concordância com y2** — modelo mais distante
3. **Maior gap F1(y1) − concordância(y2)** — aprendeu bem y1 mas diverge da calculadora

### Referência cruzada com Fase B

O relatório contextualiza os números com a concordância direta `y1` vs `y2` reportada na Fase B (60,9% exata, 97,7% dentro de ±1), que serve como linha de base natural.

## Resultados principais (2026-05-24)

| Destaque | Modelo | Métrica |
|---|---|---|
| Maior concordância com y2 | `df_random_forest` | 69,3% exata |
| Menor concordância com y2 | `bc_decision_tree` | 54,2% exata |
| Maior gap F1−concord. | `df_gradient_boosting` | gap = +0.051 |

Todos os modelos ficam acima da concordância base `y1==y2` (60,9%) na representação DF, e abaixo em BC — indicando que DF captura sinais mais próximos dos critérios da calculadora.

## Comandos de execução

```bash
uv run --no-sync python -m scripts.phase_i_model_vs_calculator
```

## Pontos de extensão / armadilhas

- **Re-execução**: sempre regera tudo do zero. Idempotente.
- **Nunca usar y2 como target**: o campo `y2` está disponível nas predições OOF apenas para esta análise descritiva. Não adicionar lógica que treine ou otimize para `y2`.
- **Subset analysis usa y_true (=y1) como filtro**: os grupos concordante/discordante são definidos por `y_true == y2`, não por `y_pred == y2`. Isso preserva a integridade da análise — estamos vendo como o modelo se comporta em decks com diferentes graus de divergência entre as fontes de rótulo.
- **Macro-F1 vs y2**: interpretado apenas como medida de alinhamento, não como avaliação do modelo. O modelo não foi otimizado para y2.
