# Demo local no navegador

Interface interativa para apresentacao do projeto. A demo usa os artefatos das Fases
A-J e nao faz parte do artigo. A interface foi mantida simples para uma leitora leiga:
ela mostra cenarios prontos, um deck por vez e apenas os tres modelos principais.

## Comandos

```bash
uv run --no-sync python -m scripts.demo build
uv run --no-sync python -m scripts.demo serve --port 8000
```

Abrir `http://127.0.0.1:8000/`.

O comando `serve` recompila os assets antes de iniciar o servidor, salvo se receber
`--no-build`.

Tambem existe o entrypoint `uv run mtg-demo serve --port 8000`, mas o comando
acima evita que `uv` tente reinstalar o pacote quando a maquina estiver sem rede.

## Entradas

- `data/processed/archidekt/modeling_snapshot_ids.json`
- `data/processed/archidekt/deck_features.jsonl`
- `data/processed/archidekt/decks.jsonl`
- `experiments/<modelo>/predictions_per_fold.jsonl`
- `experiments/<modelo>/metrics_per_fold.json`

## Saidas

- `demo/assets/manifest.json`
- `demo/assets/decks.json`
- `demo/assets/predictions.json`

## Escopo

A demo opera sobre decks ja presentes na base modelavel. "Rodar um deck em um modelo"
significa consultar as predicoes out-of-fold existentes para aquele deck e agrega-las
por maioria entre os 3 repeats. Para ensembles, o script reconstroi hard voting usando
as predicoes OOF alinhadas dos modelos membros.

## Fluxo sugerido para a professora

1. Abrir a demo.
2. Clicar em "Comunidade = calculadora" para ver um caso em que as fontes concordam.
3. Clicar em "Calculadora acima" e depois em "Calculadora abaixo" para ver a divergencia.
4. Em cada deck, comparar as tres predicoes: melhor DF, melhor BC e ensemble.
