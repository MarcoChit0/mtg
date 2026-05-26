# MTG Archidekt Pipeline

Interface reprodutível para o projeto de ML com decks Commander do Archidekt.

## Setup

Requisitos:

- Python gerenciado pelo `uv`
- acesso à internet na primeira execução

Na raiz do projeto:

```bash
uv sync
uv run run-mtg-pipeline init
```

`init` baixa o snapshot processado, roda os relatórios/preprocessamento das Fases B/C e baixa os experimentos públicos já publicados da Fase E. O comando sem subcomando continua funcionando como atalho para `init`:

```bash
uv run run-mtg-pipeline
```

## Interface Principal

Inicializar dados e experimentos publicados:

```bash
uv run run-mtg-pipeline init
```

Rodar spot-checking da Fase D depois do init:

```bash
uv run run-mtg-pipeline spot-checking
```

Treinar um modelo da Fase E:

```bash
uv run run-mtg-pipeline train --model random_forest --feature df
uv run run-mtg-pipeline train --model random_forest --feature bc
```

Quando o treino não usa `--run-local`, o comando verifica escrita no Drive antes de começar, sobe o zip do modelo ao terminar e atualiza o manifest público.

Treinar sem enviar resultados ao Drive:

```bash
uv run run-mtg-pipeline train --model random_forest --feature df --run-local
```

Simular qualquer comando:

```bash
uv run run-mtg-pipeline init --dry-run
uv run run-mtg-pipeline spot-checking --dry-run
uv run run-mtg-pipeline train --model random_forest --feature df --dry-run
```

O manifest de execução é salvo em:

```text
experiments/pipeline_run_manifest.json
```

## Drive Do Projeto

Leitura dos experimentos publicados não exige `rclone`. O `init` usa por padrão o manifest público:

```text
1MU0AilsDnG11M9pySkDUebLKkJ4a_5kR
```

Para baixar manualmente os experimentos publicados:

```bash
uv run sync-experiments-drive download-public
```

Para colaboradores com permissão de escrita, configure uma vez o remote `mtg-experiments`:

```bash
rclone version

# macOS, se precisar instalar
brew install rclone

# Windows PowerShell, se precisar instalar
winget install Rclone.Rclone

rclone config create mtg-experiments drive scope drive root_folder_id 183wMYdR0EzGJ3Dghq-JH7iZ8fL2G-Nfm
rclone lsf mtg-experiments:
uv run sync-experiments-drive check-write
```

Durante a configuração, autentique com uma conta Google que tenha permissão de escrita em `MTG/Experiments`. Se a conta não tiver escrita, `train` para antes do treino pesado e pede para usar `--run-local`.

Guia completo para instalar/configurar `rclone` em máquina local ou servidor remoto: [documents/rclone_drive_setup.md](documents/rclone_drive_setup.md).

Se a máquina já tiver `gdrive:` apontando para a conta correta:

```bash
rclone config create mtg-experiments alias remote gdrive:MTG/Experiments
```

Publicar/atualizar o manifest depois de subir zips:

```bash
uv run sync-experiments-drive publish-manifest
```

## Dados

Snapshot processado padrão:

```text
https://drive.google.com/file/d/1gXCxPeFjxgkNmizWCTU62m-s311B05R0/view?usp=sharing
```

Usar outro snapshot processado:

```bash
uv run run-mtg-pipeline init --processed-drive-url "https://drive.google.com/file/d/<FILE_ID>/view?usp=sharing"
```

Usar um arquivo local:

```bash
uv run run-mtg-pipeline init --processed-archive processed.zip
```

O diretório `data/` não é versionado.

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
  action_plan.md
  backbone.md
  archidekt_pipeline.md
  reports/
    results/                     # auto-generated each run; descartável
      phase_a_data_collection.md
      phase_b_eda.md
      phase_b_divergence.md
      phase_c_preprocessing.md
      phase_d_spot_checking.md
      phase_e_nested_cv.md
      figures/{eda,divergence}/
      sample_reports/
    implementation/              # hand-written; narrativa de decisões para colaboradores/LLMs
      phase_a_data_collection.md
      phase_b_eda_divergence.md
      phase_c_preprocessing.md
      phase_d_spot_checking.md
      phase_e_nested_cv.md

experiments/
  pipeline_run_manifest.json
  archives/
  spot_check/
  <feature>_<algorithm>/
```

O plano completo do projeto está em `documents/action_plan.md`.

## Demo Local no Navegador

Para apresentar o projeto de forma interativa:

```bash
uv run --no-sync python -m scripts.demo serve --port 8000
```

Abra `http://127.0.0.1:8000/`.

A demo gera assets em `demo/assets/` a partir dos dados processados e das predições
OOF dos modelos. Ela mostra cenários prontos, decks reais e as predições dos três
modelos principais em uma interface simples. Mais detalhes em [documents/demo.md](documents/demo.md).
