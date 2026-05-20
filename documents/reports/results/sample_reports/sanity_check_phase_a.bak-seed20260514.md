# Sanity Check — Fase A

- Amostra: **30 decks** (estratificado por y1, seed 20260514).
- A.1: compara estado salvo vs Archidekt ao vivo, filtrando decks alterados após o scrap.
- A.3: re-roda `build_deck_features` sobre o registro salvo e diffa contra `deck_features.jsonl`.
- A.2 (calculadora) é coberta por `validate_edhpowerlevel_labels.py` separadamente.

## Resumo

| Métrica | Valor |
|---|---|
| Falhas de fetch | 0 |
| A.1 OK (todos campos) | 26 |
| A.1 mismatch | 1 |
| A.1 pulado (deck mudou após scrap) | 3 |
| A.3 features idênticas | 30 |
| A.3 features divergem | 0 |
| A.3 erro de execução | 0 |

## Detalhe por deck

| # | deck_id | y1 | A.1 | Δ a.3 | obs |
|---:|---|---:|---|---:|---|
| 1 | [761546](https://archidekt.com/decks/761546) | 2 | OK | 0 |  |
| 2 | [9110056](https://archidekt.com/decks/9110056) | 2 | OK | 0 |  |
| 3 | [12399151](https://archidekt.com/decks/12399151) | 2 | OK | 0 |  |
| 4 | [2860467](https://archidekt.com/decks/2860467) | 2 | OK | 0 |  |
| 5 | [3913802](https://archidekt.com/decks/3913802) | 2 | OK | 0 |  |
| 6 | [5430689](https://archidekt.com/decks/5430689) | 2 | OK | 0 |  |
| 7 | [6729770](https://archidekt.com/decks/6729770) | 2 | OK | 0 |  |
| 8 | [11314621](https://archidekt.com/decks/11314621) | 2 | OK | 0 |  |
| 9 | [4479702](https://archidekt.com/decks/4479702) | 2 | OK | 0 |  |
| 10 | [12357235](https://archidekt.com/decks/12357235) | 2 | OK | 0 |  |
| 11 | [4039182](https://archidekt.com/decks/4039182) | 3 | OK | 0 |  |
| 12 | [1084504](https://archidekt.com/decks/1084504) | 3 | OK | 0 |  |
| 13 | [13059590](https://archidekt.com/decks/13059590) | 3 | skip | 0 | live updatedAt > fetched_at |
| 14 | [12828671](https://archidekt.com/decks/12828671) | 3 | OK | 0 |  |
| 15 | [8963436](https://archidekt.com/decks/8963436) | 3 | OK | 0 |  |
| 16 | [3307137](https://archidekt.com/decks/3307137) | 3 | cmdr | 0 |  |
| 17 | [14595502](https://archidekt.com/decks/14595502) | 3 | OK | 0 |  |
| 18 | [2898736](https://archidekt.com/decks/2898736) | 3 | OK | 0 |  |
| 19 | [21413043](https://archidekt.com/decks/21413043) | 3 | skip | 0 | live updatedAt > fetched_at |
| 20 | [3196370](https://archidekt.com/decks/3196370) | 3 | OK | 0 |  |
| 21 | [7134653](https://archidekt.com/decks/7134653) | 4 | OK | 0 |  |
| 22 | [16207706](https://archidekt.com/decks/16207706) | 4 | OK | 0 |  |
| 23 | [8088989](https://archidekt.com/decks/8088989) | 4 | OK | 0 |  |
| 24 | [5077019](https://archidekt.com/decks/5077019) | 4 | OK | 0 |  |
| 25 | [18214114](https://archidekt.com/decks/18214114) | 4 | OK | 0 |  |
| 26 | [3422012](https://archidekt.com/decks/3422012) | 4 | OK | 0 |  |
| 27 | [12550748](https://archidekt.com/decks/12550748) | 4 | OK | 0 |  |
| 28 | [4044130](https://archidekt.com/decks/4044130) | 4 | skip | 0 | live updatedAt > fetched_at |
| 29 | [7250376](https://archidekt.com/decks/7250376) | 4 | OK | 0 |  |
| 30 | [734103](https://archidekt.com/decks/734103) | 4 | OK | 0 |  |

## Decks com divergência (detalhes)

### Deck 3307137  (y1=3)
- **A.1**:
  - commanders salvos: ['Braids, Arisen Nightmare']
  - commanders live: ['Black Market', 'Bonecaller Cleric', 'Braids, Arisen Nightmare', 'Burning-Rune Demon', 'Plaguecrafter']
