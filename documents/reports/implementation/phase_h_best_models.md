# Implementação — Fase H: Seleção do Melhor Modelo por Representação

> Implementation report. Público: colaborador novo ou LLM. Resultados automáticos em [../results/phase_h_best_models.md].

## Objetivo

Selecionar `melhor_BC` e `melhor_DF` — um modelo individual por representação — com base no macro-F1 médio nos outer folds da Fase E. Esses dois modelos são o insumo direto da Fase J (interpretabilidade) e devem ser citados explicitamente no artigo como os melhores modelos por representação (backbone §13.8).

A fase também produz o ranking completo (individuais + 6 ensembles) e as matrizes de confusão agregadas dos dois selecionados.

## O que foi construído

| Componente | Arquivo | Responsabilidade |
|---|---|---|
| Script principal | `scripts/phase_h_best_models.py` | Ranking, seleção, confusão, relatório |
| Entrypoint CLI | `pyproject.toml` → `phase-h-best-models` | `uv run --no-sync python -m scripts.phase_h_best_models` |
| Results report | `documents/reports/results/phase_h_best_models.md` | Auto-gerado a cada execução |
| Artefato de seleção | `experiments/best_models.json` | Consumido pela Fase J |

## Como foi construído

### Descoberta de modelos

Mesma lógica da Fase F: lê `experiments/spot_check/summary.json` → `selection.union` para obter `A_union`, cruza com `{df, bc}`. Fallback: escaneia `experiments/` diretamente.

Para ensembles: escaneia `experiments/voting/*/metrics_per_fold.json`.

### Critério de seleção (backbone §13.8)

```
melhor_BC = argmax_{alg ∈ A_union} macro_F1(alg, BC, y1)
melhor_DF = argmax_{alg ∈ A_union} macro_F1(alg, DF, y1)
```

Desempate: menor desvio padrão (estabilidade). Implementado como sort primário por `-macro_f1_mean`, secundário por `macro_f1_std`.

**Resultado (2026-05-24):**
- `melhor_BC` = `bc_gradient_boosting` — macro-F1 = 0.6433 ± 0.0121
- `melhor_DF` = `df_gradient_boosting` — macro-F1 = 0.6908 ± 0.0093

Ambos são Gradient Boosting, o algoritmo dominante em ambas as representações no spot-checking e na nested CV. Não houve empate — gradient boosting liderou com margem clara em BC e DF.

### Matrizes de confusão

Carrega `predictions_per_fold.jsonl` dos dois modelos selecionados. Cada deck aparece 3× nas predições OOF (uma vez por repeat). Total: 12.135 × 3 = 36.405 entradas. A matriz é agregada sobre todos os folds e usada para calcular precisão/recall por classe.

### Artefato `best_models.json`

Salvo em `experiments/best_models.json` com campos suficientes para a Fase J: `model_id`, `representation`, `algorithm`, `macro_f1_mean`, `macro_f1_std`, `n_folds`, `predictions_path`, `hyperparams_path`. Paths relativos ao diretório do projeto.

## Comandos de execução

```bash
uv run --no-sync python -m scripts.phase_h_best_models
```

## Pontos de extensão / armadilhas

- **Re-execução**: sempre regera tudo do zero. Idempotente — resultado é determinístico dado os mesmos artefatos da Fase E.
- **Novos modelos na Fase E**: basta rodar novamente. Se um novo modelo superar o atual líder, a seleção muda automaticamente e `best_models.json` é atualizado.
- **Fase J depende de `best_models.json`**: não editar manualmente. Rodar a Fase H gera o artefato correto.
- **Ensembles não são selecionados para interpretabilidade**: o ranking inclui os 6 ensembles para comparação, mas a seleção de `melhor_BC`/`melhor_DF` é restrita a modelos individuais (backbone §13.8 e enunciado — interpretabilidade sobre modelos simples).

## Problemas encontrados e correções

- **UnicodeEncodeError no Windows**: `→` e outros caracteres UTF-8 nos logs causavam erro no console cp1252. Resolvido com `PYTHONIOENCODING=utf-8` ao executar.
