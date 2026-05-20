# Implementação — Fase B: EDA + Análise de Divergência

> Implementation report. **Público**: colaborador novo ou agente LLM que precisa entender o que a EDA cobre e por quê. Resultados numéricos vivem em [../results/phase_b_eda.md](../results/phase_b_eda.md) e [../results/phase_b_divergence.md](../results/phase_b_divergence.md).

## Objetivo

Descrever a base modelável (12.135 decks com y1, y2 ∈ {2,3,4}) e medir diretamente, sem treinar modelo nenhum, **quão longe** y1 está de y2 e **com quais características de deck** a divergência se correlaciona. Essa é a primeira resposta concreta à pergunta de pesquisa antes mesmo da modelagem.

## O que foi construído

Um único script, `scripts/phase_b_eda_divergence.py` (~700 linhas), gera dois reports independentes + figuras:

| Saída | Conteúdo |
|---|---|
| `results/phase_b_eda.md` | Distribuições de y1/y2, balanceamento, cores, mana base, curva, tipos, flags de bracket, popularidade/preço/salt, combos, raridade, missing values, comandantes top, correlação top-30 features |
| `results/phase_b_divergence.md` | Concordância exata/±1, matriz y1×y2, distribuição de Δ e \|Δ\|, direção da divergência, \|Δ\| segmentado por características (cores, game changers, tutores, combos, preço, EDHREC, salt) |
| `results/figures/eda/*.png` | Histogramas e barras das seções da EDA |
| `results/figures/divergence/*.png` | Histogramas/heatmaps da divergência |

## Como foi construído (decisões + porquês)

### Por que UM script com DOIS reports?
EDA e divergência compartilham o pipeline de carregamento (`deck_features.jsonl` + `decks.jsonl` → pandas DataFrame), os helpers de formatação (`fmt_pct`, `save_fig`) e o backend matplotlib. Separar em dois scripts duplicaria isso. Manter um arquivo com `eda()` e `divergence()` retornando markdown é mais simples.

### `matplotlib.use("Agg")` no topo
Antes de qualquer import de `pyplot`. Backend Agg é headless (sem GUI), funciona em CI/Drive/colaborador sem display. Crítico para reprodutibilidade — sem isso, em algumas máquinas o matplotlib tenta abrir uma janela e trava o batch.

### Linha única de carga: `load_features()` + `load_decks_minimal()`
`deck_features.jsonl` traz tudo numérico (mais features prontas) **mas** não tem o nome do comandante. `decks.jsonl` é grande (cartas inline) — carregar inteiro custa memória. Solução: `load_decks_minimal()` pega só `snapshot_id` + `commander_oracle_uids` + commander names. Join em pandas por `snapshot_id`.

### Por que separar a base em dois conjuntos visíveis?
A EDA mostra a **base modelável** (y1, y2 ∈ {2,3,4} = 12.135 decks) — é o que entra na Fase D/E. Mas também documenta o **conjunto completo** (12.950 decks, incluindo os 815 com y2 ∈ {1,5}) na subseção da divergência. Os 815 são preservados como análise qualitativa (backbone §8): "calculadora classificou abaixo/acima dos extremos do nosso escopo".

### Por que figuras separadas em `figures/eda/` e `figures/divergence/`?
Cada report referencia apenas suas figuras (`![](figures/eda/y1_distribution.png)` vs `![](figures/divergence/delta_hist.png)`). Subpastas evitam colisão de nomes e tornam a limpeza/re-execução previsível.

### Métricas de divergência escolhidas
A pergunta do projeto é "quão longe y1 está de y2". As métricas refletem isso direto:

| Métrica | Por que |
|---|---|
| `exact_agreement` (% com y1 = y2) | Linha de base trivial: quantas vezes os dois concordam? |
| `agreement_within_one_bracket` (% com \|Δ\| ≤ 1) | Critério "social" — bracket adjacente raramente quebra mesa |
| `delta = y2 - y1` (distribuição) | Direção da divergência: calculadora puxa pra cima ou pra baixo? |
| `|Δ|` médio | Magnitude global do desalinhamento |
| Matriz y1 × y2 | Mostra onde a confusão concentra (ex: y1=2 → y2=3 mais comum?) |

Não usamos AUC/ROC porque a tarefa não é binária. Não usamos macro-F1 aqui porque a EDA é descritiva — sem modelo, não há "predição vs verdadeiro".

### Segmentação de `|Δ|` por característica
Para cada feature de bracket-relevante (game_changers, tutors, mass_land_denial, combos, preço, EDHREC rank, salt), calculamos `|Δ|` médio por bucket. Isso entrega a hipótese: "decks com muitos game_changers divergem mais entre archidekt e calculadora?" — resposta direta sem modelo. Esses insights alimentam a discussão do artigo final (Fase I).

### `print()` durante a execução
EDA é demorada (carrega 12k linhas + matplotlib). O script imprime progresso ("Loading...", "Generating EDA report + figures...") para evitar a impressão de travar quando rodado interativamente. Output vai pra stdout; logs estruturados ficariam exagerados pra um one-shot.

## Pontos de extensão / armadilhas

- **Adicionar nova seção na EDA**: criar uma função `seção_x(df, decks) -> str` que retorna markdown, e concatenar dentro de `eda()`. Salvar figuras via `save_fig(FIG_EDA / "x.png", fig)` para manter coerência de path.
- **Modificar bin edges/buckets**: cuidado para não mudar o significado das comparações entre rodadas. O artigo cita números específicos — re-bucketing força revisão narrativa.
- **NÃO acrescentar predições aqui**: a Fase B é estritamente descritiva. Predições out-of-fold pertencem à Fase E.5 → G. Misturar atrasa entendimento.
- **Memória**: o DataFrame de 12k decks × 114 features cabe em ~100 MB. Se a base crescer ordens de magnitude, mudar para `pd.read_json(..., lines=True, chunksize=...)`.

## Problemas encontrados

- **Comandantes top precisavam de nome legível**: `decks.jsonl` carrega `commander_oracle_uids` como UID. `load_decks_minimal()` resolve UID → nome usando `cards.jsonl`.
- **Matplotlib bleed entre figuras**: sem `plt.close(fig)` o backend acumulava memória. `save_fig()` fecha explicitamente cada figura após salvar.
- **Truncamento de tabelas markdown**: pandas DataFrame com 30+ colunas estourava a largura. Usamos `df.head(30).to_markdown(index=False)` e mencionamos no texto que é top-30.
