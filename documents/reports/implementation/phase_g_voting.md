# Implementação — Fase G: Voting Ensembles

> Implementation report. Público: colaborador novo ou LLM. Resultados automáticos em [../results/phase_g_voting.md].

## Objetivo

Combinar as predições OOF (out-of-fold) dos modelos individuais da Fase E em voting ensembles, sem retreino. O objetivo é verificar se a combinação de modelos complementares supera os melhores individuais em macro-F1, e produzir o ranking final de conjuntos candidatos para as fases H e I.

A Fase G opera **exclusivamente sobre artefatos já gerados** — não re-treina nenhum modelo.

## O que foi construído

| Componente | Arquivo | Responsabilidade |
|---|---|---|
| Script principal | `scripts/phase_g_voting.py` | Descoberta de modelos, voting, relatório |
| Entrypoint CLI | `pyproject.toml` → `phase-g-voting` | `uv run phase-g-voting` |
| Results report | `documents/reports/results/phase_g_voting.md` | Auto-gerado a cada execução |
| Sumário JSON | `experiments/voting/voting_summary.json` | Metadados de todos os ensembles computados |
| Artefatos por ensemble | `experiments/voting/<voting_id>/metrics_per_fold.json` | Métricas por fold salvas para reuso |
| Predições por ensemble | `experiments/voting/<voting_id>/predictions_per_fold.jsonl` | OOF predictions combinadas (para Fases I/J) |

## Ensemble specs implementadas

| voting_id | Membros |
|---|---|
| `voting_top3_BC` | Top-3 modelos BC por macro-F1 |
| `voting_top5_BC` | Top-5 modelos BC |
| `voting_top3_DF` | Top-3 modelos DF |
| `voting_top5_DF` | Top-5 modelos DF |
| `voting_top3_BC_DF` | Top-3 BC + Top-3 DF (6 membros, representações mistas) |
| `voting_all` | Todos os 12 modelos disponíveis |

## Como foi construído

### Descoberta de modelos individuais

`discover_individual_models()` lê `experiments/spot_check/summary.json` → `selection.union` para obter `A_union`, depois verifica `experiments/<rep>_<algo>/` buscando `predictions_per_fold.jsonl` e `metrics_per_fold.json`. Modelos com artefatos ausentes são ignorados com aviso.

Fallback: se o summary do spot-check não existir, escaneia `experiments/` diretamente por padrão `<rep>_<algo>`.

### Ranking por representação

`rank_models()` ordena por `macro_f1_mean` descendente dentro de cada representação (`bc`, `df`). O ranking define quem entra em top-3, top-5 etc.

### Hard voting com tie-break

Por decisão metodológica do `action_plan.md` §G:
1. Para cada amostra e fold, coleta os votos dos membros.
2. Classe com mais votos vence (pluralidade).
3. Empate → classe cujos votantes têm maior macro-F1 médio entre os membros que votaram nela.
4. Empate residual → menor rótulo numérico (2 antes de 3 antes de 4).

Implementado em `hard_vote()`: recebe lista de `(voto, macro_f1_mean_do_membro)` por amostra.

### Folds compartilhados

Ao combinar modelos com potencialmente diferentes folds disponíveis (Fase E parcial), `compute_voting_results()` usa apenas a interseção de `fold_id`s comuns a todos os membros do ensemble. Isso garante que a comparação é válida mesmo antes da Fase E estar completa.

### Reuso de artefatos

`load_existing_ensemble()` verifica se o diretório `experiments/voting/<voting_id>/` já tem `metrics_per_fold.json`. Se sim, compara os membros registrados com os membros atuais:
- Iguais → reutiliza (economiza tempo).
- Divergentes (novo modelo adicionado, ranking mudou) → recomputa.

`--force-recompute` ignora qualquer artefato existente.

### Métricas reportadas

Por fold: `macro_f1`, `accuracy`, `precision_per_class`, `recall_per_class`, `confusion_matrix`.  
Agregado: média e desvio padrão sobre os folds disponíveis.

## Comandos de execução

```bash
# Modo padrão — opera com modelos disponíveis (Fase E parcial OK)
uv run phase-g-voting

# Forçar recomputação mesmo com artefatos existentes
uv run phase-g-voting --force-recompute

# Depois que Fase E terminar — exige todos os modelos esperados
uv run phase-g-voting --all

# Combinado
uv run phase-g-voting --all --force-recompute
```

## Pontos de extensão / armadilhas

- **Adicionar novo modelo**: basta rodar a Fase E para ele. Na próxima execução da Fase G, os specs top-N incluirão o novo candidato automaticamente se ele entrar no top-N. `voting_all` sempre inclui todos.
- **Novos specs de voting**: adicionar em `VOTING_SPECS` como `VotingSpec(voting_id, description, bc_top_n, df_top_n)`. `bc_top_n=None` inclui todos BC; `df_top_n=None` inclui todos DF.
- **Membros ímpares vs pares**: ensembles com número par de membros têm maior chance de empate. O tie-break por F1 resolve, mas é algo a mencionar no artigo.
- **Fase E incompleta**: folds compartilhados determinam o N efetivo. O relatório exibe `N_folds/15` para rastreabilidade.
- **Fase I/J**: as predições OOF combinadas em `experiments/voting/<id>/predictions_per_fold.jsonl` ficam prontas para comparação com y2 (Fase I) e interpretabilidade (Fase J) sem retreino adicional.

## Problemas encontrados e correções

- **KeyError `n_folds`**: artefatos recarregados via `load_existing_ensemble()` não tinham a chave `n_folds` em runs antigas. Corrigido com fallback `r.get('n_folds', len(r.get('folds', [])))` no render.
