# Demo local do projeto MTG

Esta pasta contem uma interface de navegador para explorar o projeto sem mexer no artigo.

## Rodar

Na raiz do projeto:

```bash
uv run --no-sync python -m scripts.demo build
uv run --no-sync python -m scripts.demo serve --port 8000
```

Depois abra:

```text
http://127.0.0.1:8000/
```

`serve` tambem recompila os assets por padrao, entao o caminho curto e:

```bash
uv run --no-sync python -m scripts.demo serve --port 8000
```

## O que a demo mostra

- quatro cenarios prontos para apresentacao;
- uma lista curta de decks reais da base modelavel;
- labels `y1` do Archidekt e `y2` da EDHPowerLevel;
- os tres modelos principais: melhor DF, melhor BC e melhor ensemble;
- uma explicacao textual de cada predicao;
- resumo simples das metricas dos decks mostrados.

## Observacao metodologica

A demo nao treina modelos no navegador. Ela usa as predicoes out-of-fold ja produzidas
pela nested CV da Fase E e as agrega por deck. Isso preserva o protocolo do projeto:
os modelos continuam treinados apenas em `y1`, e `y2` aparece somente como benchmark
descritivo.

Os JSONs em `demo/assets/` sao gerados localmente e ignorados pelo Git.
