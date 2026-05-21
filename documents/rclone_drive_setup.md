# Configuração do Google Drive com rclone

Este guia serve para configurar uma máquina local ou um servidor remoto para ler/escrever os artefatos do projeto no Google Drive.

Remote esperado pelo projeto:

```text
mtg-experiments:
```

Pasta do Drive usada pelo projeto:

```text
MTG/Experiments
root_folder_id = 183wMYdR0EzGJ3Dghq-JH7iZ8fL2G-Nfm
```

## 1. Instalar rclone

### macOS local

Com Homebrew:

```bash
brew install rclone
rclone version
```

### Linux/servidor remoto

Opção recomendada pelo instalador oficial:

```bash
curl https://rclone.org/install.sh | sudo bash
rclone version
```

Se não tiver `sudo`, instale localmente no usuário:

```bash
mkdir -p ~/bin ~/tmp/rclone-install
cd ~/tmp/rclone-install
curl -O https://downloads.rclone.org/rclone-current-linux-amd64.zip
unzip rclone-current-linux-amd64.zip
cp rclone-*-linux-amd64/rclone ~/bin/
chmod +x ~/bin/rclone
echo 'export PATH="$HOME/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
rclone version
```

### Windows local

Com Winget:

```powershell
winget install Rclone.Rclone
rclone version
```

## 2. Verificar remotes existentes

```bash
rclone config file
rclone config
```

O remote precisa se chamar exatamente:

```text
mtg-experiments
```

Se aparecer algo como `met-experiments`, renomeie:

```bash
rclone config rename met-experiments mtg-experiments
```

## 3. Criar o remote do Drive

Se `mtg-experiments` ainda não existir:

```bash
rclone config create mtg-experiments drive scope drive root_folder_id 183wMYdR0EzGJ3Dghq-JH7iZ8fL2G-Nfm
```

## 4. Autenticar em máquina local

Em máquina com navegador disponível:

```bash
rclone config reconnect mtg-experiments:
```

Siga o fluxo no navegador, faça login na conta Google com acesso à pasta do projeto e autorize.

Teste:

```bash
rclone lsf mtg-experiments:
```

## 5. Autenticar em servidor remoto

Em servidor remoto sem navegador:

```bash
rclone config reconnect mtg-experiments:
```

Quando perguntar:

```text
Use auto config?
```

responda:

```text
n
```

O rclone vai imprimir uma URL. Abra essa URL no navegador da sua máquina local, faça login na conta Google com acesso à pasta do projeto, autorize e cole o código/token de volta no terminal remoto.

Teste no servidor:

```bash
rclone lsf mtg-experiments:
```

Se listar arquivos, o remote está autenticado.

## 6. Preparar o projeto na máquina

Do zero:

```bash
git clone https://github.com/MarcoChit0/mtg.git
cd mtg
uv sync
```

Se o repositório já existe:

```bash
cd ~/mtg
git pull
uv sync
```

## 7. Baixar dados processados dos decks

Para baixar o snapshot processado e rodar as Fases B/C:

```bash
uv run run-mtg-pipeline init --skip-experiment-restore
```

Esse comando baixa os dados processados do Drive público e não precisa de `rclone`.

## 8. Testar se o projeto está ok

```bash
uv run python -m unittest discover -s tests -v
```

## 9. Testar escrita no Drive

Antes de rodar treino sem `--run-local`, teste escrita:

```bash
uv run sync-experiments-drive check-write
```

Resultado esperado:

```json
{
  "status": "ok"
}
```

Se aparecer:

```text
didn't find section in config file
```

o remote `mtg-experiments` não existe nesse servidor/usuário, ou está com nome errado.

Se aparecer:

```text
empty token found
```

rode:

```bash
rclone config reconnect mtg-experiments:
```

## 10. Rodar treino de um modelo específico

Rodar um algoritmo em DF e BC:

```bash
uv run run-mtg-pipeline train --model random_forest --estimator-n-jobs 8
```

Rodar só uma representação:

```bash
uv run run-mtg-pipeline train --model gradient_boosting --feature bc --estimator-n-jobs 8 --force-rerun
```

Testar o comando sem executar:

```bash
uv run run-mtg-pipeline train --model random_forest --feature df --dry-run
```

## 11. Modelos e features válidos

Modelos:

```text
decision_tree
random_forest
gradient_boosting
naive_bayes
logistic_regression
linear_svc
knn
```

Features:

```text
df
bc
```

## 12. Notas importantes

- Sem `--run-local`, o treino checa escrita no Drive antes de começar, sobe o zip do modelo ao terminar e publica o manifest.
- Com `--run-local`, nada é enviado ao Drive.
- Cada servidor tem seu próprio arquivo de configuração do rclone, normalmente em `~/.config/rclone/rclone.conf`.
- Configurar `mtg-experiments` em um servidor não configura automaticamente nos outros.
- Não use nomes alternativos para o remote; o projeto espera `mtg-experiments:`.
