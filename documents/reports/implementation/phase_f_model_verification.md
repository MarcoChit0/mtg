# Implementação — Fase F: Verificação dos Modelos Individuais

> Implementation report. Público: colaborador novo ou LLM. Resultados automáticos em [../results/phase_f_model_verification.md] e [../results/phase_f_statistical_tests.md].

## Objetivo

Portão de qualidade entre a Fase E (nested CV) e as fases seguintes (G: voting, H: melhor modelo, I: comparação com calculadora). Verifica que os modelos gerados estão completos, consistentes e robustos o suficiente antes de qualquer conclusão ser tirada.

Três sub-fases:
- **F.1** — completude e consistência dos artefatos da Fase E
- **F.2** — robustez por GroupKFold agrupado por comandante (opcional, mais lento)
- **F.3** — testes estatísticos (Friedman + Nemenyi + Wilcoxon) sobre os 15 outer scores

## O que foi construído

| Componente | Arquivo | Responsabilidade |
|---|---|---|
| Script principal | `scripts/phase_f_model_verification.py` | F.1 + F.2 + F.3 + geração dos reports |
| Entrypoint CLI | `pyproject.toml` → `phase-f-model-verification` | `uv run phase-f-model-verification` |
| Results report (verificação) | `documents/reports/results/phase_f_model_verification.md` | Auto-gerado a cada execução |
| Results report (testes) | `documents/reports/results/phase_f_statistical_tests.md` | Auto-gerado a cada execução |
| Artefato GroupKFold | `experiments/model_verification/group_kfold_results.json` | Gerado só com `--group-kfold` |

## Como foi construído

### F.1 — Completude e consistência

**Descoberta de modelos**: lê `experiments/spot_check/summary.json` → `selection.union` para obter `A_union`, depois cruza com `{df, bc}` para montar a lista de 12 modelos esperados. Fallback: escaneia `experiments/` diretamente se o summary não existir.

**Arquivos obrigatórios**: `metrics_per_fold.json`, `best_hyperparams_per_fold.json`, `predictions_per_fold.jsonl`. Ausência de qualquer um desses exclui o modelo da análise.

**Arquivos opcionais**: `cv_results_per_fold.jsonl`, `checkpoint_state.json`. Ausência gera aviso mas não exclui o modelo — alguns modelos rodados em máquinas diferentes ou versões mais antigas do script não os geram.

**Flag `--all`**: aborta se qualquer modelo esperado estiver ausente ou com menos de 15 folds. Usar apenas depois que a Fase E estiver completamente concluída.

**Flag `--min-folds`** (default=5): limiar mínimo de folds para incluir um modelo. Permite operar com a Fase E parcialmente concluída (pelo menos um repeat completo).

**Consistência de fold IDs**: verifica que todos os modelos compartilham exatamente os mesmos `fold_id`s (ex: `r1_f1` ... `r3_f5`). Divergência indica mistura de rodadas ou seeds diferentes, o que invalida comparações pareadas (Wilcoxon/Nemenyi).

### F.2 — GroupKFold por comandante

**Motivação**: na Fase E, folds estratificados por `y1` permitem que decks do mesmo comandante apareçam nos dois lados do split. O modelo pode memorizar associações por comandante em vez de padrões estruturais gerais. O GroupKFold mede o quanto o desempenho cai quando comandantes vistos no treino não aparecem no teste.

**Implementação**: usa `commander_oracle_uids` do `deck_features.jsonl` como chave de grupo (lista de UIDs ordenada → string separada por `|`). `GroupKFold(n_splits=5)`, sem repeat, sem nova busca de hiperparâmetros.

**Hiperparâmetros**: usa o config mais frequente entre os 15 outer folds de `best_hyperparams_per_fold.json` da Fase E. Não faz nova busca — o objetivo é medir o gap de generalização, não otimizar.

**Pipeline**: reutiliza `pipeline_for()` de `phase_e_nested_cv.py` (mesmos preprocessadores, mesma lógica de scaling/densificação). Hiperparâmetros `clf__*` são aplicados via `pipeline.set_params()` após construção.

**Gap reportado**: `gap = macro_F1_estratificado_mean − macro_F1_grupo_mean`. Gap positivo = modelo beneficia de comandantes já vistos. Gap grande (>0.05) é sinal de atenção para a discussão do artigo.

**Por que é opcional**: re-treina cada modelo 5 vezes. Para modelos BC com HistGradientBoosting (que requer conversão densa) isso pode levar vários minutos por modelo.

### F.3 — Testes estatísticos

Mesma metodologia da Fase E (Demšar 2006):

- **Friedman**: testa se há diferença significativa entre os modelos. Rejeitar H₀ habilita post-hoc.
- **Nemenyi**: CD = q_α × √(k(k+1)/(6N)), onde k = número de modelos, N = folds usados. Usa `scipy.stats.studentized_range` com fallback para tabela hard-coded se a versão do scipy não suportar.
- **Wilcoxon signed-rank**: todos os pares, two-sided, `zero_method='wilcox'`.
- **Ranking**: descendente (maior F1 = rank 1).

Diferença em relação à Fase E: os testes aqui operam sobre o conjunto final de modelos disponíveis no momento da execução, e são sempre regerados. A Fase E gerava os testes embutidos na execução de treino; a Fase F os regera de forma independente sobre os artefatos salvos.

## Comandos de execução

```bash
# Modo padrão — opera com modelos disponíveis (Fase E parcial OK)
uv run phase-f-model-verification

# Com GroupKFold (lento — re-treina cada modelo 5 vezes)
uv run phase-f-model-verification --group-kfold

# Depois que Fase E terminar — exige 12/12 modelos com 15/15 folds
uv run phase-f-model-verification --all

# Combinado
uv run phase-f-model-verification --all --group-kfold
```

## Pontos de extensão / armadilhas

- **Adicionar um modelo novo**: basta rodar a Fase E para ele. A Fase F descobre automaticamente via `A_union` do summary ou scan do diretório.
- **Incrementalidade**: cada execução regera tudo do zero. Não há checkpoint entre execuções da Fase F. O GroupKFold é o único passo caro — se necessário, adicionar cache por `model_id` em `group_kfold_results.json` (verificar hash do `best_hyperparams_per_fold.json`).
- **`pipeline_for()` como contrato**: a Fase F depende que `pipeline_for(algo, rep, ...)` de `phase_e_nested_cv.py` continue existindo e com a mesma assinatura. Se refatorar a Fase E, atualizar o import aqui.
- **Artefatos opcionais ausentes**: `cv_results_per_fold.jsonl` e `checkpoint_state.json` não são consumidos pela Fase F — são listados como opcionais apenas para auditoria. Não adicione lógica que dependa deles aqui.
- **Não gera voting**: a Fase F é estritamente verificação. Voting fica na Fase G, conforme decisão metodológica do projeto.

## Problemas encontrados e correções

- **Chave errada no spot-check summary**: a chave esperada era `a_union` mas o arquivo real usa `selection.union`. Corrigido no script.
- **Arquivos opcionais bloqueando modelos**: `cv_results_per_fold.jsonl` e `checkpoint_state.json` estavam na lista de obrigatórios, o que excluía 5 dos 12 modelos (gerados por versão anterior do pipeline). Movidos para `OPTIONAL_FILES`.
- **Import inexistente**: tentativa de importar `build_pipeline` e `ALGORITHM_REGISTRY` de `phase_e_nested_cv` — essas funções não existem lá. Corrigido para usar `pipeline_for` e `jsonable`.
