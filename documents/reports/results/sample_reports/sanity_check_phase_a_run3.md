# Sanity Check — Fase A

- Amostra: **30 decks** (estratificado por y1, seed 20260516).
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
| 1 | [1488344](https://archidekt.com/decks/1488344) | 2 | OK | 0 |  |
| 2 | [9360873](https://archidekt.com/decks/9360873) | 2 | skip | 0 | live updatedAt > fetched_at |
| 3 | [1939210](https://archidekt.com/decks/1939210) | 2 | OK | 0 |  |
| 4 | [6314848](https://archidekt.com/decks/6314848) | 2 | OK | 0 |  |
| 5 | [3954378](https://archidekt.com/decks/3954378) | 2 | OK | 0 |  |
| 6 | [7695030](https://archidekt.com/decks/7695030) | 2 | OK | 0 |  |
| 7 | [6385783](https://archidekt.com/decks/6385783) | 2 | OK | 0 |  |
| 8 | [3617970](https://archidekt.com/decks/3617970) | 2 | OK | 0 |  |
| 9 | [7204282](https://archidekt.com/decks/7204282) | 2 | OK | 0 |  |
| 10 | [8197117](https://archidekt.com/decks/8197117) | 2 | OK | 0 |  |
| 11 | [284047](https://archidekt.com/decks/284047) | 3 | OK | 0 |  |
| 12 | [9891842](https://archidekt.com/decks/9891842) | 3 | skip | 0 | live updatedAt > fetched_at |
| 13 | [5842284](https://archidekt.com/decks/5842284) | 3 | OK | 0 |  |
| 14 | [10309175](https://archidekt.com/decks/10309175) | 3 | OK | 0 |  |
| 15 | [5754391](https://archidekt.com/decks/5754391) | 3 | OK | 0 |  |
| 16 | [3370911](https://archidekt.com/decks/3370911) | 3 | OK | 0 |  |
| 17 | [12288422](https://archidekt.com/decks/12288422) | 3 | OK | 0 |  |
| 18 | [7731751](https://archidekt.com/decks/7731751) | 3 | OK | 0 |  |
| 19 | [9794856](https://archidekt.com/decks/9794856) | 3 | OK | 0 |  |
| 20 | [1959196](https://archidekt.com/decks/1959196) | 3 | OK | 0 |  |
| 21 | [6129174](https://archidekt.com/decks/6129174) | 4 | OK | 0 |  |
| 22 | [1032812](https://archidekt.com/decks/1032812) | 4 | OK | 0 |  |
| 23 | [5427561](https://archidekt.com/decks/5427561) | 4 | skip | 0 | live updatedAt > fetched_at |
| 24 | [2627131](https://archidekt.com/decks/2627131) | 4 | OK | 0 |  |
| 25 | [17037622](https://archidekt.com/decks/17037622) | 4 | skip | 0 | live updatedAt > fetched_at |
| 26 | [13247668](https://archidekt.com/decks/13247668) | 4 | OK | 0 |  |
| 27 | [5168601](https://archidekt.com/decks/5168601) | 4 | OK | 0 |  |
| 28 | [18494260](https://archidekt.com/decks/18494260) | 4 | OK | 0 |  |
| 29 | [13042670](https://archidekt.com/decks/13042670) | 4 | OK | 0 |  |
| 30 | [9406813](https://archidekt.com/decks/9406813) | 4 | OK | 0 |  |

## Decks com divergência (detalhes)

_Nenhum deck divergente entre os comparados._
