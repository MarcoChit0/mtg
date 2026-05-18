# MTG Archidekt Pipeline

Pipeline reprodutível para o projeto de ML com decks Commander do Archidekt.

O comando principal é:

```bash
uv run run-mtg-pipeline
```

Em uma máquina limpa, esse comando restaura automaticamente o snapshot processado salvo no Google Drive, gera os relatórios implementados até a Fase C e escreve o manifest em:

```text
experiments/pipeline_run_manifest.json
```

Se os dados já existirem em `data/processed/archidekt`, o mesmo comando reutiliza os arquivos locais.

## Setup

Requisitos:

- Python gerenciado pelo `uv`
- acesso à internet na primeira execução

Na raiz do projeto:

```bash
uv sync
uv run run-mtg-pipeline
```

No Windows PowerShell, os comandos são os mesmos.

## Dados

Por padrão, o runner usa o snapshot processado do projeto:

```text
https://drive.google.com/file/d/1gXCxPeFjxgkNmizWCTU62m-s311B05R0/view?usp=sharing
```

Também é possível passar outro arquivo processado:

```bash
uv run run-mtg-pipeline --data-source processed-drive --processed-drive-url "https://drive.google.com/file/d/<FILE_ID>/view?usp=sharing"
```

Ou usar um arquivo local `processed.zip`:

```bash
uv run run-mtg-pipeline --data-source processed-drive --processed-archive processed.zip
```

O diretório `data/` não é versionado.

## Comandos Úteis

Listar as etapas:

```bash
uv run run-mtg-pipeline --list-stages
```

Simular sem executar:

```bash
uv run run-mtg-pipeline --dry-run
```

Rodar testes:

```bash
uv run run-mtg-pipeline --run-tests
```

Rodar também o spot-check da Fase D:

```bash
uv run run-mtg-pipeline --run-spot-check
```

Rodar também a nested CV da Fase E:

```bash
uv run run-mtg-pipeline --run-nested-cv
```

Rodar somente a Fase D:

```bash
uv run phase-d-spot-check
```

Rodar somente a Fase E:

```bash
uv run phase-e-nested-cv
```

## Estado Atual

- Fase A: concluída, report em `documents/phase_a_report.md`
- Fase B: concluída, reports em `documents/eda_report.md` e `documents/divergence_report.md`
- Fase C: concluída, report em `documents/preprocessing_report.md`
- Fase D: concluída, report em `documents/spot_check_results.md`
- Fase E: implementada, roda sob demanda com `phase-e-nested-cv`

O plano completo do projeto está em `documents/action_plan.md`.

## Saídas Principais

```text
data/processed/archidekt/
  decks.jsonl
  cards.jsonl
  deck_features.jsonl
  bag_of_cards.jsonl
  modeling_snapshot_ids.json
  modeling_excluded.jsonl

documents/
  phase_a_report.md
  eda_report.md
  divergence_report.md
  preprocessing_report.md
  spot_check_results.md

experiments/
  pipeline_run_manifest.json
  spot_check/
```
