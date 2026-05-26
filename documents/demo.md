# Demo local no navegador

Interface interativa para apresentacao do projeto. A demo usa os artefatos das Fases
A-J e nao faz parte do artigo. A interface foi mantida simples para uma leitora leiga:
ela mostra cenarios prontos, um deck por vez, imagem do comandante, explicacoes
textuais e elementos visuais para comparar comunidade, calculadora e modelos.

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
2. Clicar em um cenario e escolher um deck.
3. Observar a imagem do comandante, y1, y2 e os sinais do deck.
4. Comparar as predicoes dos modelos selecionados.
5. Usar o seletor ordenado por macro-F1 para alternar entre Top 3, DF, BC,
   ensembles ou todos os modelos.

## Referencia visual

O EDHPowerLevel apresenta a leitura de um deck colocando primeiro numeros de alto
nivel ao lado da imagem do comandante e depois graficos de composicao. A demo segue
essa logica de apresentacao, mas nao destaca power level porque ele nao e o alvo do
estudo. O foco fica em `y1`, `y2`, divergencia entre fontes e sinais disponiveis no
projeto. O preco tambem nao aparece na demo porque `price_total` esta nulo nos
artefatos processados atuais.
