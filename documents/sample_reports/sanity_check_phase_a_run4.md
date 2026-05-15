# Sanity Check — Fase A

- Amostra: **30 decks** (estratificado por y1, seed 20260517).
- A.1: compara estado salvo vs Archidekt ao vivo, filtrando decks alterados após o scrap.
- A.3: re-roda `build_deck_features` sobre o registro salvo e diffa contra `deck_features.jsonl`.
- A.2 (calculadora) é coberta por `validate_edhpowerlevel_labels.py` separadamente.

## Resumo

| Métrica | Valor |
|---|---|
| Falhas de fetch | 0 |
| A.1 OK (todos campos) | 26 |
| A.1 mismatch | 0 |
| A.1 pulado (deck mudou após scrap) | 4 |
| A.3 features idênticas | 30 |
| A.3 features divergem | 0 |
| A.3 erro de execução | 0 |

## Detalhe por deck

| # | deck_id | y1 | A.1 | Δ a.3 | obs |
|---:|---|---:|---|---:|---|
| 1 | [9106170](https://archidekt.com/decks/9106170) | 2 | OK | 0 |  |
| 2 | [14216763](https://archidekt.com/decks/14216763) | 2 | OK | 0 |  |
| 3 | [1099418](https://archidekt.com/decks/1099418) | 2 | OK | 0 |  |
| 4 | [6336293](https://archidekt.com/decks/6336293) | 2 | OK | 0 |  |
| 5 | [13021514](https://archidekt.com/decks/13021514) | 2 | OK | 0 |  |
| 6 | [10844137](https://archidekt.com/decks/10844137) | 2 | OK | 0 |  |
| 7 | [17924666](https://archidekt.com/decks/17924666) | 2 | skip | 0 | live updatedAt > fetched_at |
| 8 | [11672936](https://archidekt.com/decks/11672936) | 2 | OK | 0 |  |
| 9 | [17585113](https://archidekt.com/decks/17585113) | 2 | skip | 0 | live updatedAt > fetched_at |
| 10 | [8530736](https://archidekt.com/decks/8530736) | 2 | OK | 0 |  |
| 11 | [4280006](https://archidekt.com/decks/4280006) | 3 | skip | 0 | live updatedAt > fetched_at |
| 12 | [7292436](https://archidekt.com/decks/7292436) | 3 | OK | 0 |  |
| 13 | [13392446](https://archidekt.com/decks/13392446) | 3 | OK | 0 |  |
| 14 | [749684](https://archidekt.com/decks/749684) | 3 | OK | 0 |  |
| 15 | [1670156](https://archidekt.com/decks/1670156) | 3 | OK | 0 |  |
| 16 | [3993777](https://archidekt.com/decks/3993777) | 3 | OK | 0 |  |
| 17 | [12384474](https://archidekt.com/decks/12384474) | 3 | OK | 0 |  |
| 18 | [7640013](https://archidekt.com/decks/7640013) | 3 | OK | 0 |  |
| 19 | [216212](https://archidekt.com/decks/216212) | 3 | OK | 0 |  |
| 20 | [4370132](https://archidekt.com/decks/4370132) | 3 | OK | 0 |  |
| 21 | [16490045](https://archidekt.com/decks/16490045) | 4 | OK | 0 |  |
| 22 | [10959006](https://archidekt.com/decks/10959006) | 4 | OK | 0 |  |
| 23 | [7877967](https://archidekt.com/decks/7877967) | 4 | OK | 0 |  |
| 24 | [4448222](https://archidekt.com/decks/4448222) | 4 | OK | 0 |  |
| 25 | [10716417](https://archidekt.com/decks/10716417) | 4 | OK | 0 |  |
| 26 | [14587267](https://archidekt.com/decks/14587267) | 4 | OK | 0 |  |
| 27 | [10216307](https://archidekt.com/decks/10216307) | 4 | OK | 0 |  |
| 28 | [7504129](https://archidekt.com/decks/7504129) | 4 | skip | 0 | live updatedAt > fetched_at |
| 29 | [2086869](https://archidekt.com/decks/2086869) | 4 | OK | 0 |  |
| 30 | [5988003](https://archidekt.com/decks/5988003) | 4 | OK | 0 |  |

## Decks com divergência (detalhes)

_Nenhum deck divergente entre os comparados._
