# Implementação — Fase I: Comparação das Predições dos Modelos com a Calculadora

> Implementation report. Público: colaborador novo ou LLM. Resultados automáticos em [../results/phase_i_model_vs_calculator.md].

## Objetivo

Comparar, na mesma base OOF, o rótulo real `y1` (Archidekt) contra `y2` (calculadora EDHPowerLevel) e as predições OOF `ŷ1` (modelos treinados em `y1`) contra `y2`. A fase é **descritiva** — sem retreino, sem novos folds, sem uso de `y2` como alvo de treinamento (backbone §5). O objetivo é medir o grau de alinhamento entre percepção comunitária, percepção aprendida pelos modelos e avaliação automática da calculadora.

As predições usadas aqui já foram feitas e persistidas antes:

- Fase E: `experiments/<modelo>/predictions_per_fold.jsonl`, com as predições out-of-fold dos modelos individuais.
- Fase G: `experiments/voting/<ensemble>/predictions_per_fold.jsonl`, com as predições dos ensembles por votação.

A Fase I apenas lê esses arquivos, computa métricas e monta matrizes de confusão comparando `ŷ1` com `y2`. As 36.405 entradas aparecem porque cada um dos 12.135 decks possui uma predição OOF em cada um dos 3 repeats da Fase E.

## O que foi construído

| Componente | Arquivo | Responsabilidade |
|---|---|---|
| Script principal | `scripts/phase_i_model_vs_calculator.py` | Métricas de concordância, subset analysis, matrizes de confusão, relatório |
| Entrypoint CLI | `pyproject.toml` → `phase-i-model-vs-calculator` | `uv run --no-sync python -m scripts.phase_i_model_vs_calculator` |
| Results report | `documents/reports/results/phase_i_model_vs_calculator.md` | Auto-gerado a cada execução |

Nenhum artefato gerado em `experiments/` — análise puramente descritiva sobre o que já existe.

## Como foi construído

### Fonte de dados

As predições OOF (`predictions_per_fold.jsonl`) já contêm o campo `y2` por linha, gravado na Fase E a partir de `deck_features.jsonl`. `y2` é estável por deck (verificado: 0 inconsistências entre os 3 repeats). Total: 36.405 entradas = 12.135 decks × 3 repeats. Isso não significa retreino na Fase I: os três repeats já foram treinados e preditos na Fase E; aqui eles são apenas lidos do disco.

### Métricas calculadas para a referência direta `y1` vs `y2`

Antes da análise de modelos, o relatório calcula na mesma base OOF:

- **Concordância exata**: `mean(y1 == y2)`
- **Concordância ±1**: `mean(|y1 − y2| ≤ 1)`
- **|Δ| médio**: `mean(|y1 − y2|)`
- **Macro-F1 vs y2**: macro-F1 com `y2` como referência descritiva
- **Matriz de confusão y1 × y2**: linhas = `y1`, colunas = `y2`

### Métricas calculadas por modelo (backbone §13.7 + action plan §I)

Para cada um dos 12 modelos individuais + 3 ensembles (15 total):

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

### Contingência triádica y1 × y2 × ŷ1

A análise triádica cruza três rótulos: `y1` (comunidade), `y2` (calculadora) e `ŷ1` (predição do modelo treinado em `y1`). Dentro de cada célula em que `y1 != y2`, o relatório conta se `ŷ1` segue a comunidade, segue a calculadora ou escolhe outro bracket.

**Atualização metodológica (2026-06-15):** a análise por gap absoluto foi substituída pela contingência triádica. A definição anterior tentava resumir a separação entre comunidade e calculadora em um único escalar; a nova leitura é mais direta, pois mostra para onde a predição vai em cada célula de discordância.

### Destaques automáticos globais

Considerando todos os modelos e ensembles juntos, o relatório identifica:

1. **Maior concordância com y2** — modelo mais alinhado à calculadora.
2. **Menor concordância com y2** — modelo mais distante da calculadora.
3. **Melhor preditor comunitário individual** — modelo individual com maior macro-F1 em `y1`, usado como caso principal para a contingência triádica.
4. **Melhor BC / melhor ensemble** — referências adicionais para o texto do artigo.

Cada escolha aparece com justificativa explícita e, quando o modelo ainda não apareceu no bloco, com matriz `ŷ1 × y2`. Os destaques são globais, isto é, independem de a origem ser `BC`, `DF` ou `BC+DF`.

### Referência cruzada com Fase B

O relatório agora recalcula a concordância direta `y1` vs `y2` na mesma base OOF usada para os modelos, em vez de apenas citar a Fase B. Essa referência serve como linha de base natural.

## Resultados principais (2026-05-24; análise triádica adicionada em 2026-06-15)

| Destaque | Modelo | Métrica |
|---|---|---|
| Maior concordância global | `df_random_forest` | 69,3% exata |
| Menor concordância global | `bc_decision_tree` | 54,2% exata |
| Melhor preditor comunitário individual | `df_gradient_boosting` | macro-F1(y1) = 0,6908 |
| Contingência triádica (`df_gradient_boosting`, discordantes) | — | segue y1: 53,8%; segue y2: 39,0%; outro: 7,2% |

Os destaques são escolhidos em um ranking único global.

## Comandos de execução

```bash
uv run --no-sync python -m scripts.phase_i_model_vs_calculator
```

## Pontos de extensão / armadilhas

- **Re-execução**: sempre regera tudo do zero. Idempotente.
- **Nunca usar y2 como target**: o campo `y2` está disponível nas predições OOF apenas para esta análise descritiva. Não adicionar lógica que treine ou otimize para `y2`.
- **Subset analysis usa y_true (=y1) como filtro**: os grupos concordante/discordante são definidos por `y_true == y2`, não por `y_pred == y2`. Isso preserva a integridade da análise — estamos vendo como o modelo se comporta em decks com diferentes graus de divergência entre as fontes de rótulo.
- **Macro-F1 vs y2**: interpretado apenas como medida de alinhamento, não como avaliação do modelo. O modelo não foi otimizado para y2.
