# Onboarding para LLMs / Colaboradores

> Leia este arquivo **inteiro** antes de propor mudanças. Ele comprime as convenções e decisões acumuladas — economiza idas e voltas com o usuário.

## Em uma frase

Pipeline de ML para estudar divergência entre dois rótulos de bracket de decks Commander (y1 = Archidekt comunitário, y2 = EDHPowerLevel calculadora). Tarefa: classificação multiclasse {2,3,4} sobre y1, com y2 servindo só como benchmark de comparação descritiva. **Nunca treine prevendo y2** — é decisão metodológica firmada em [documents/backbone.md](documents/backbone.md) §5.

## Mapa rápido do repo

```
scripts/
  run_pipeline.py            ← CLI principal (`init`, `spot-checking`, `train`)
  preprocessing.py           ← DeckFeaturePreprocessor + BagOfCardsPreprocessor (leakage-safe, fold-by-fold)
  phase_b_eda_divergence.py  ← Fase B
  phase_c_filter_dataset.py  ← Fase C
  phase_d_spot_check.py      ← Fase D
  phase_e_nested_cv.py           ← Fase E (núcleo, ~1900 linhas)
  phase_f_model_verification.py  ← Fase F (verificação: completude, GroupKFold, testes estatísticos)
  phase_g_voting.py              ← Fase G (voting ensembles a partir de OOF predictions)
  phase_h_best_models.py         ← Fase H (seleção melhor_BC e melhor_DF, ranking, confusão)
  phase_i_model_vs_calculator.py ← Fase I (concordância ŷ1 vs y2 — descritivo, sem retreino)
  phase_j_interpretability.py    ← Fase J (interpretabilidade: PI para DF, lift analysis para BC)
  sync_experiments_drive.py      ← Drive (uploads colaborador, downloads público)

documents/
  action_plan.md             ← Roadmap fase por fase (LEIA ISSO PRIMEIRO)
  backbone.md                ← Spec metodológica completa
  reports/
    results/                 ← AUTO-GERADO a cada rodada; não editar manualmente
    implementation/          ← À MÃO; sua doc de decisões + porquês

tests/                       ← unittest discover -s tests
experiments/                 ← Artefatos de execução (não versionados além do manifest)
```

## Convenção crítica: DOIS reports por fase

Toda fase implementada gera **dois** documentos em pastas separadas:

| Pasta | Quem escreve | Quando atualiza | Conteúdo |
|---|---|---|---|
| `documents/reports/results/phase_<X>_<nome>.md` | O script da fase, automaticamente | A cada execução | Tabelas, métricas, distribuições da rodada atual. Descartável. |
| `documents/reports/implementation/phase_<X>_<nome>.md` | Você, à mão | Quando decisões de design mudam | Objetivo / O que foi construído / Como (decisões+porquês) / Pontos de extensão / Problemas encontrados |

**Quando você implementar ou modificar uma fase, atualize OS DOIS.** O results é regenerado pelo próprio script; o implementation precisa ser editado por você refletindo a mudança.

Estrutura mínima de um implementation report:

```markdown
# Implementação — Fase X: <nome>
> Implementation report. Público: colaborador novo ou LLM. Resultados em [../results/phase_X_<nome>.md].

## Objetivo
## O que foi construído (tabela: componente → arquivo → responsabilidade)
## Como foi construído (decisões + porquês — com referência da literatura quando aplicável)
## Pontos de extensão / armadilhas
## Problemas encontrados e correções
```

## Estado das fases

| Fase | O que é | Status | Script |
|---|---|---|---|
| A | Coleta Archidekt + scraping EDHPowerLevel (Playwright) | ✓ concluída | `fetch_archidekt_raw.py`, `process_archidekt_raw.py`, `edhpowerlevel_client.py` |
| B | EDA + análise direta de divergência y1↔y2 | ✓ concluída | `phase_b_eda_divergence.py` |
| C | Filtro (y1,y2 ∈ {2,3,4}) + transformers leakage-safe | ✓ concluída | `phase_c_filter_dataset.py` + `preprocessing.py` |
| D | Spot-check N=5 seeds, 7 algos, top-5 por representação | ✓ concluída | `phase_d_spot_check.py` |
| E | Nested CV dos modelos individuais (5 folds × 3 repeats), grids tunados | ✓ concluída — 12/12 modelos, 15/15 folds | `phase_e_nested_cv.py` |
| F | Verificação dos modelos individuais: completude, consistência, GroupKFold por comandante, testes estatísticos | ✓ concluída (2026-05-24) — 12/12 modelos, F.1+F.2+F.3 com --all --group-kfold | `phase_f_model_verification.py` |
| G | Voting ensembles a partir de OOF predictions, só depois da F | ✓ concluída (2026-05-24) — 6 ensembles, melhor: voting_top3_BC_DF F1=0.6944 | `phase_g_voting.py` |
| H | Melhor modelo por representação | ✓ implementada e executada | `phase_h_best_models.py` |
| I | Comparar predições dos modelos vs y2 (descritivo) | ✓ implementada e executada | `phase_i_model_vs_calculator.py` |
| J | Interpretabilidade dos 2 melhores (BC + DF) | ✓ implementada e executada | `phase_j_interpretability.py` |
| K | Artigo (template Moodle) | a fazer | — |
| L | OOD (opcional): decks 500-1000 views | a fazer | — |
| M | Stacking (opcional) | a fazer | — |

## Decisões metodológicas-chave (não viole sem discussão)

1. **Alvo único `y1`**. `y2` nunca entra em X (bloqueio por nome em `preprocessing.py::is_leakage_column`).
2. **Base modelável**: 12.135 decks com y1 e y2 em {2,3,4}. Os 815 com y2 ∈ {1,5} ficam preservados em `decks.jsonl`/`deck_features.jsonl` mas excluídos via `modeling_snapshot_ids.json` (gerado por Phase C).
3. **Duas representações**: BC (bag-of-cards esparso ~10k features) e DF (deck features denso ~102 features). Cada algoritmo selecionado treina em **ambas**.
4. **Phase D**: hold-out 80/20 estratificado por y1, N=5 seeds (`{1,2,3,4,5}`), defaults sklearn (com ajustes mínimos de convergência). Pool de 7 algoritmos viáveis em BC e DF. SVC RBF/Poly **excluídos** porque não escalam em BC.
5. **Phase E nested CV**: `StratifiedKFold(5) × 3 repeats = 15 outer evals`; inner `StratifiedKFold(3)`. **Mesmos folds para todos os modelos** — comparações pareadas (Friedman/Nemenyi/Wilcoxon) válidas. Folds derivados de y + seeds, não lidos de arquivo.
6. **Grids ~24 configs por algoritmo** (corte operacional fixado pelo usuário em 2026-05-21 porque BC estava demorando demais). `MAX_GRID_CONFIGS = 24` é constante exportada; teste no CI garante.
7. **Métrica principal**: macro-F1 (imbalanced: y1=3 é 52%, y1=2 é 21%, y1=4 é 27%). `class_weight='balanced'` está nos grids de DT/RF/HistGB/LR/LinearSVC por causa disso.
8. **Fase E não faz voting**. E treina modelos individuais e gera métricas/checkpoints/predições OOF. Voting foi deliberadamente movido para depois da verificação.
9. **Fase F será portão de qualidade**: antes de voting, verificar todos os modelos esperados (`A_uniao × {DF,BC}`), completude 15/15 folds, artefatos, consistência de seeds/folds/rótulos, GroupKFold por comandante e testes estatísticos.
10. **Voting (Fase G ✓ concluída)**: hard voting majoritário sobre predições OOF, sem retreino. Tie-break: maior macro-F1 médio dos membros que votaram na classe; empate residual = menor rótulo numérico. 6 ensembles computados, melhor: `voting_top3_BC_DF` F1=0.6944.
11. **Determinismo**: dado mesmo `deck_features.jsonl` + seeds + versões pinadas (`uv.lock`), duas máquinas devem produzir resultados equivalentes (caveat: diferenças BLAS/versão sklearn podem causar epsilons).

## Antes de mexer em qualquer fase

1. Leia `documents/reports/implementation/phase_<X>_*.md` da fase.
2. Leia a seção correspondente em `documents/action_plan.md`.
3. Se for decisão metodológica, consulte `documents/backbone.md` §13 (Estratégia experimental).
4. Verifique se há testes em `tests/test_phase_<X>*.py` — eles documentam contratos implícitos.

## Armadilhas conhecidas (aprendidas no caminho)

- **LogisticRegression / sklearn 1.8+**: `penalty` foi depreciado. O código atual usa `l1_ratio` diretamente em sklearn >=1.8 e só seta `penalty='elasticnet'` em versões antigas. Não reintroduza `penalty` fixo sem checar o warning.
- **LogisticRegression / sklearn antigo**: `l1_ratio` só funciona com `penalty='elasticnet'`. Se você setar l1_ratio sem penalty='elasticnet' em versões antigas, sklearn ignora silenciosamente.
- **HistGradientBoosting**: use `max_leaf_nodes`, não `max_depth` (sklearn user guide é explícito; LightGBM paper idem).
- **DecisionTree**: use `ccp_alpha` em vez de `min_samples_split` (Breiman/Hastie ESL §9.2).
- **LR/LinearSVC**: `fit_intercept=True` sempre. Não inclua no grid.
- **`solver='saga'`** para LR é o único que suporta L1+L2+elasticnet em multinomial. Use saga em BC E DF se quiser grid simétrico.
- **HistGB em BC esparso**: precisa `SparseToDenseTransformer` no pipeline.
- **Nunca adicionar feature derivada de y2** (`epl_*`, `edhpowerlevel.*`) — bloqueio automático em `is_leakage_column`, mas confirme nome novo.
- **Adicionar algoritmo**: atualize TANTO `phase_d_spot_check.py::ALGORITHMS` quanto `phase_e_nested_cv.py::SELECTED_ALGORITHMS` + `estimator_for` + `pipeline_for` + `full_param_grid`. Sem isso, o spot-check pode selecionar algo que a Fase E não sabe treinar.
- **Reports auto-gerados** (`documents/reports/results/`): **não edite à mão**, são sobrescritos a cada rodada.
- **Fase E sem voting**: não recrie `phase_f_voting.py`, não adicione `run-mtg-pipeline voting` e não faça `phase_e_nested_cv.py` escrever `phase_e_voting.md`. Voting só deve voltar quando a Fase G for autorizada e depois da Fase F.
- **`experiments/` pode estar sujo por runs reais**: não apague zips, checkpoints, predições ou pastas antigas sem confirmação explícita. Pode haver artefatos legados de voting mesmo que o código atual não os gere.
- **`grid-n-jobs`** em Phase E é reservado: a busca manual roda sequencial por configuração para preservar progresso/checkpoint. Paralelismo real vem de `estimator_n_jobs` quando o estimador suporta (`RandomForest`, KNN etc.).
- **GPU**: pipeline atual é scikit-learn CPU. Não prometa aceleração por GPU sem trocar bibliotecas e discutir impacto metodológico/reprodutibilidade.

## Drive (integração compartilhada)

- **Usuário externo**: `uv run run-mtg-pipeline init` — baixa snapshot processado + manifest público + zips de modelos/bundles. Sem rclone.
- **Colaborador**: configura `rclone config create mtg-experiments drive scope drive root_folder_id 183wMYdR0EzGJ3Dghq-JH7iZ8fL2G-Nfm`. `train` (sem `--run-local`) checa escrita antes, sobe modelo a modelo + bundle `shared` (= seeds+folds) + republica manifest schema v2. Voting não é gerado pela Fase E atual.
- **Servidor remoto só terminal**: use `rclone config reconnect mtg-experiments:` se o remote existir mas estiver com token vazio. `rclone lsf mtg-experiments:` deve funcionar antes de treinos sem `--run-local`.
- **Reprodutibilidade**: o snapshot `processed.zip` no Drive **preserva os labels y2** da rodada original (y2 tem flutuação temporal — re-scraping não dá mesmos números).

## Reprodutibilidade cross-machine

Determinismo é seed-driven. Se você muda algo que afeta resultados (grid, seeds, fold split, voting tie-break), considere:

- `signature_id = sha256(grid + folds + params)[:16]` invalida checkpoints antigos automaticamente. Bom.
- Mas resultados já publicados no manifest do Drive **não** são invalidados — colaboradores que baixaram via `init` ficam com resultados velhos até alguém republicar.
- Se a mudança afeta seleção (top-5 do spot-check), informe no implementation report e considere republicar o bundle `spot_check`.

## Como propor uma mudança não-trivial

1. Não edite código antes de discutir. Apresente:
   - Qual fase / arquivo
   - Que problema resolve / qual decisão metodológica está em jogo
   - Trade-off (custo computacional, risco metodológico, etc.)
   - Como atualiza o implementation report e o action_plan
2. Espere confirmação. Métricas/grids/algoritmos têm impacto que cascateia em comparações pareadas — não mude unilateralmente.

## Experiências recentes com o projeto (Claude + Codex)

Estas são decisões aprendidas em conversa e auditoria prática. Trate como contexto operacional do usuário.

- O usuário primeiro aceitou grids maiores como ordem de grandeza, mas a execução real em BC ficou lenta demais. A regra atual da Fase E virou **~24 configs por algoritmo**, preservando os principais knobs.
- Na Fase E, `--model random_forest` roda RF em **DF e BC**; `--model random_forest --feature df` roda só DF. Isso foi importante para enviar modelo a modelo ao servidor.
- Sem `--run-local`, `run-mtg-pipeline train` faz `check-write` no Drive antes do treino, treina, sobe o zip do modelo e publica manifest. Com `--run-local`, não sobe nada.
- Se rodar um algoritmo que já tem checkpoints compatíveis, a Fase E retoma/pula folds concluídos. Use `--force-rerun` só quando quiser recalcular de verdade.
- `--skip-experiment-restore` no `init` só pula download de experimentos públicos; não afeta download dos dados processados nem B/C. Útil quando o servidor vai treinar novos modelos e não precisa restaurar resultados antigos.
- A Fase E já passou por auditoria de literatura: DT usa `ccp_alpha`; HistGB usa `max_leaf_nodes`; LR usa `l1_ratio` para L2/ElasticNet/L1; lineares não tunam `fit_intercept`.
- `bc_gradient_boosting` ficou muito mais lento que o esperado porque exige `dense_conversion=True`. O grid de HistGB foi reduzido para 24 configs, removendo `max_iter=500`, `learning_rate=0.01`, `max_leaf_nodes=63` e `l2_regularization`, mas mantendo `max_leaf_nodes ∈ {15,31}`.
- O usuário corrigiu uma implementação indevida de voting como Fase F. Estado correto: Fase F é verificação (✓ concluída 2026-05-24), Fase G é voting (✓ concluída 2026-05-24), Fase H é seleção do melhor modelo (✓ concluída 2026-05-24).
- Ao implementar uma etapa futura, primeiro alinhe o plano: qual fase é, quais artefatos produz, quais reports serão criados e quais comandos validam. Depois codifique.
- O usuário valoriza comandos exatos para servidor, mas também quer que o código/documentação não confunda quem continuar o projeto. Se um comando antigo deixar de existir, remova do README/tests/docs.
- Worktree local pode conter artefatos de treinos reais de NB/experimentos no Drive. Não use `git reset --hard`, não limpe `experiments/` por iniciativa própria.

## Comandos úteis

```bash
uv sync                                          # instala deps
uv run run-mtg-pipeline init                     # baixa tudo + Phase B/C
uv run run-mtg-pipeline spot-checking            # Phase D
uv run run-mtg-pipeline train --run-local        # Phase E sem Drive
uv run run-mtg-pipeline analyze                  # Fases F+G+H+I+J pós-treino
uv run run-mtg-pipeline full --skip-training     # Pipeline B->J sem retreino
uv run python -m unittest discover -s tests      # testes (61+ atualmente passando)

uv run sync-experiments-drive download-public    # só baixar modelos públicos
uv run sync-experiments-drive check-write        # testar permissão de escrita
```

## Referências da literatura citadas em decisões

Quando justificar escolhas no implementation report, use estas (já citadas em decisões existentes):

- Cawley & Talbot 2010, *J. Machine Learning Research* — nested CV vs holdout extra
- Breiman 2001 — Random Forest, `max_features=sqrt`
- Probst et al. 2018 "Tunability" — ranking de hyperparams importantes
- Hastie/Tibshirani/Friedman *Elements of Statistical Learning* §4.4, §9.2 — LR `fit_intercept=True`, CART pruning
- Ke et al. 2017 (LightGBM) — `max_leaf_nodes` como complexidade principal
- Fan et al. 2008 (LIBLINEAR) — LinearSVC `dual` selection
- Zou & Hastie 2005 — ElasticNet vs L1 puro
- Demšar 2006 — Statistical Comparisons of Classifiers (Friedman/Nemenyi/Wilcoxon)
- McCallum & Nigam 1998 — Multinomial NB tuning

---

**Resumo em uma frase**: leia action_plan.md → leia o implementation report da fase → respeite os contratos (folds, seeds, leakage, grids ~24) → atualize ambos os reports ao mexer → discuta antes de mudanças metodológicas.
