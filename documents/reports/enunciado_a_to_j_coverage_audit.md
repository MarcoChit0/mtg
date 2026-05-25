# Auditoria de Cobertura do Enunciado — Fases A-J

Data: 2026-05-25

## Veredito

**Correto para o escopo técnico do projeto**: as fases A-J cobrem as exigências metodológicas e de pipeline do `documents/enunciado.pdf` antes da escrita do artigo.

**Ressalva importante**: o enunciado também exige entregáveis que não são "artigo" nem "pipeline técnico": apresentação oral, etapa de peer review e, se IA generativa foi usada, material suplementar com prompts/limitações. Esses itens não pertencem às fases A-J e devem ser tratados fora delas. Portanto, a formulação estrita "A-J cobre tudo menos o artigo" só é verdadeira se "tudo" significar **fluxo técnico de ML + reprodutibilidade do código/modelos/dados**.

## Fonte revisada

- `documents/enunciado.pdf` — 8 páginas.
- `documents/backbone.md`.
- `documents/action_plan.md`.
- Reports de implementação e resultados das fases A-J.
- Artefatos em `experiments/`.

## Cobertura requisito a requisito

| Requisito do enunciado | Cobertura A-J | Veredito |
|---|---|---|
| Definir problema preditivo de classificação/regressão e pergunta de pesquisa | `backbone.md` define classificação multiclasse de brackets Commander e pergunta sobre divergência `y1` vs `y2`; A/B materializam dados e labels | Coberto |
| Coletar/descrever dados e, quando públicos, oferecer caminho de download | A coleta Archidekt/EDHPowerLevel está em Fase A; snapshot processado e experimentos têm restauração/Drive público documentados | Coberto tecnicamente; link final precisa aparecer no artigo |
| Realizar EDA com distribuição do alvo, atributos, padrões, anomalias, gráficos e estatísticas | Fase B tem EDA, figuras, distribuição `y1`/`y2`, outliers, faltantes, comandantes, correlações e divergência direta | Coberto |
| Pré-processar conforme problemas encontrados na EDA | Fase C filtra base modelável, define DF/BC, imputação, winsorização, scaling, pruning BC e exclusão de `y2` de X | Coberto |
| Evitar data leakage no pré-processamento | Fase C/E documentam fit de transformações somente dentro do treino do fold; `y2`, `delta`, `abs_delta` e campos EDHPowerLevel não entram em X | Coberto |
| Escolher abordagem, algoritmos e estratégia de avaliação | Fase D define 7 algoritmos candidatos, duas representações, spot-check N=5, métrica principal macro-F1 e diversidade de vieses | Coberto |
| Testar pelo menos 5 algoritmos | Fase D testa 7 candidatos em BC e DF | Coberto |
| Usar mais de uma métrica e escolher métrica principal | Fases D/E/F/G/H usam macro-F1 como critério principal e reportam accuracy, precision, recall, matrizes e desvio | Coberto |
| Realizar treinamento, validação e otimização de hiperparâmetros corretamente | Fase E usa nested CV 5 folds x 3 repeats, inner 3-fold, grids por algoritmo, 12 modelos esperados completos | Coberto |
| Usar múltiplas repetições, seeds e folds consistentes entre algoritmos | D usa seeds 1-5; E usa 3 repeats x 5 folds, `experiments/seeds.json` e `experiments/folds.json`; F/G conferem consistência | Coberto |
| Evitar leakage na avaliação final | Fase E separa inner/outer CV; F verifica completude e GroupKFold por comandante; G usa só OOF sem retreino | Coberto |
| Sumarizar resultados e comparar modelos com suporte estatístico | Fases E/F/H/G reportam métricas agregadas; F inclui Friedman, Nemenyi e Wilcoxon | Coberto |
| Interpretar modelo(s) com gráficos/tabelas e discutir relações relevantes | Fase J interpreta dois modelos, excedendo o mínimo de um: melhor DF por permutation importance/features e melhor BC por lift/cartas, incluindo divergência `ŷ1` vs `y2` | Coberto |
| Reprodutibilidade: código, dados, modelos, seeds, metodologia e download | README, A, E, auditorias E-J, Drive/manifest público, arquivos `seeds.json`, `folds.json`, zips de modelos e reports de implementação cobrem o fluxo | Coberto tecnicamente |
| Pipeline implementado | Scripts A-J existem e compilam; reports e artefatos obrigatórios A-J existem | Coberto |
| Artigo científico | Planejado na Fase K | Fora de A-J |
| Apresentação oral | Não há fase técnica dedicada | Fora de A-J; precisa preparar slides posteriormente |
| Peer review dos artigos de outros grupos | Não há fase técnica dedicada | Fora de A-J; atividade individual posterior |
| Material suplementar sobre uso de IA generativa, se aplicável | Planejado em K como `ai_usage.md` | Fora de A-J; precisa ser produzido junto do artigo |

## Checagens práticas executadas

```bash
uv run --no-sync python -m py_compile \
  scripts/sanity_check_phase_a.py \
  scripts/phase_b_eda_divergence.py \
  scripts/phase_c_filter_dataset.py \
  scripts/phase_d_spot_check.py \
  scripts/phase_e_nested_cv.py \
  scripts/phase_f_model_verification.py \
  scripts/phase_g_voting.py \
  scripts/phase_h_best_models.py \
  scripts/phase_i_model_vs_calculator.py \
  scripts/phase_j_interpretability.py
```

Resultado: passou.

Também foi verificada a existência não vazia dos results reports, implementation reports e artefatos centrais das fases A-J, incluindo `experiments/spot_check/summary.json`, `experiments/seeds.json`, `experiments/folds.json`, `experiments/nested_cv_summary.json`, `experiments/model_verification/group_kfold_results.json`, `experiments/voting/voting_summary.json`, `experiments/best_models.json` e `experiments/phase_j_interpretability/final_model_params.json`.

Resultado: passou.

## Conclusão

Não encontrei lacuna técnica no fluxo A-J em relação ao que o enunciado exige para desenvolvimento, avaliação, validação, interpretação e reprodutibilidade de modelos de AM.

O que ainda não está coberto por A-J não é pipeline técnico: artigo científico, apresentação oral, peer review e material de uso de IA. Esses itens devem ser tratados na fase K e no cronograma de entrega/apresentação.
