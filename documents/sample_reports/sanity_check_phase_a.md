# Sanity Check — Fase A

- Amostra: **30 decks** (estratificado por y1, seed 20260515).
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
| 1 | [3092335](https://archidekt.com/decks/3092335) | 2 | skip | 0 | live updatedAt > fetched_at |
| 2 | [1506379](https://archidekt.com/decks/1506379) | 2 | OK | 0 |  |
| 3 | [1310924](https://archidekt.com/decks/1310924) | 2 | OK | 0 |  |
| 4 | [3256906](https://archidekt.com/decks/3256906) | 2 | OK | 0 |  |
| 5 | [6167504](https://archidekt.com/decks/6167504) | 2 | skip | 0 | live updatedAt > fetched_at |
| 6 | [8427506](https://archidekt.com/decks/8427506) | 2 | OK | 0 |  |
| 7 | [7073837](https://archidekt.com/decks/7073837) | 2 | OK | 0 |  |
| 8 | [5289584](https://archidekt.com/decks/5289584) | 2 | OK | 0 |  |
| 9 | [7115866](https://archidekt.com/decks/7115866) | 2 | OK | 0 |  |
| 10 | [15125259](https://archidekt.com/decks/15125259) | 2 | OK | 0 |  |
| 11 | [6032215](https://archidekt.com/decks/6032215) | 3 | OK | 0 |  |
| 12 | [7496766](https://archidekt.com/decks/7496766) | 3 | OK | 0 |  |
| 13 | [14350390](https://archidekt.com/decks/14350390) | 3 | OK | 0 |  |
| 14 | [1104209](https://archidekt.com/decks/1104209) | 3 | OK | 0 |  |
| 15 | [193411](https://archidekt.com/decks/193411) | 3 | OK | 0 |  |
| 16 | [5400011](https://archidekt.com/decks/5400011) | 3 | skip | 0 | live updatedAt > fetched_at |
| 17 | [11118273](https://archidekt.com/decks/11118273) | 3 | skip | 0 | live updatedAt > fetched_at |
| 18 | [9649014](https://archidekt.com/decks/9649014) | 3 | OK | 0 |  |
| 19 | [5955697](https://archidekt.com/decks/5955697) | 3 | OK | 0 |  |
| 20 | [5569847](https://archidekt.com/decks/5569847) | 3 | OK | 0 |  |
| 21 | [5570045](https://archidekt.com/decks/5570045) | 4 | OK | 0 |  |
| 22 | [4921408](https://archidekt.com/decks/4921408) | 4 | OK | 0 |  |
| 23 | [4194399](https://archidekt.com/decks/4194399) | 4 | OK | 0 |  |
| 24 | [7572930](https://archidekt.com/decks/7572930) | 4 | OK | 0 |  |
| 25 | [12453674](https://archidekt.com/decks/12453674) | 4 | OK | 0 |  |
| 26 | [2261045](https://archidekt.com/decks/2261045) | 4 | OK | 0 |  |
| 27 | [4962219](https://archidekt.com/decks/4962219) | 4 | OK | 0 |  |
| 28 | [1631187](https://archidekt.com/decks/1631187) | 4 | OK | 0 |  |
| 29 | [9913916](https://archidekt.com/decks/9913916) | 4 | OK | 0 |  |
| 30 | [4238839](https://archidekt.com/decks/4238839) | 4 | OK | 0 |  |

## Decks com divergência (detalhes)

_Nenhum deck divergente entre os comparados._
