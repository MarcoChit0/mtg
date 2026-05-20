# Report da Fase A — Coleta, Processamento e Validação dos Dados

## Objetivo

A Fase A teve como objetivo construir um snapshot confiável de decks Commander públicos do Archidekt para o escopo do projeto: `y1 ∈ {2,3,4}`, pelo menos 1.000 visualizações, 100 cartas no mainboard e validade básica em Commander. Também incluiu a coleta do rótulo `y2` via EDHPowerLevel, necessário para a análise de divergência posterior.

## O que foi feito

1. Coleta raw dos decks do Archidekt por bracket.
2. Processamento dos payloads raw em registros normalizados:
   - `data/processed/archidekt/decks.jsonl`
   - `data/processed/archidekt/cards.jsonl`
   - `data/processed/archidekt/rejected_decks.jsonl`
   - `data/processed/archidekt/processing_manifest.jsonl`
3. Enriquecimento dos decks com `edhpowerlevel`, contendo `commander_bracket`, `power_level`, `score`, `efficiency`, `impact`, `tipping_point` e `average_playability`.
4. Construção das duas representações base:
   - `deck_features.jsonl`
   - `bag_of_cards.jsonl`
5. Validações de sanidade contra o Archidekt ao vivo e contra recomputação local das features.

## Como foi feito

O processamento raw foi executado por `scripts/process_archidekt_raw.py`, com filtros de escopo e deduplicação. O manifest registra:

| Métrica | Valor |
|---|---:|
| Raw records lidos | 14.421 |
| Decks aceitos | 12.950 |
| Decks rejeitados | 4 |
| Deck IDs duplicados ignorados | 1.467 |
| Cartas únicas indexadas | 22.532 |
| Erros de processamento | 0 |

As features foram geradas por `scripts/build_features.py`:

| Métrica | Valor |
|---|---:|
| Decks processados para features | 12.950 |
| Decks com falha de features | 0 |
| Cartas indexadas | 22.532 |
| Linhas de impressão indexadas para preço/raridade | 1.411.912 |
| Printing features incluídas | Sim |

A validação final da restauração/processamento (`processed_restore_report.json`) confirmou:

| Checagem | Resultado |
|---|---|
| Arquivos obrigatórios presentes | OK |
| `deck_features.jsonl` alinhado com `decks.jsonl` | OK |
| `bag_of_cards.jsonl` alinhado com `decks.jsonl` | OK |
| Referências de cartas cobertas por `cards.jsonl` | OK |
| Todos os mainboards com 100 cartas | OK |
| Decks com `edhpowerlevel` | 12.950/12.950 |

Distribuição final dos rótulos:

| Label | Distribuição |
|---|---|
| `y1` Archidekt | 2: 2.601 · 3: 6.347 · 4: 4.002 |
| `y2` EDHPowerLevel | 1: 393 · 2: 1.911 · 3: 6.059 · 4: 4.165 · 5: 422 |

## Validação amostral

O sanity check de Fase A (`documents/reports/sample_reports/sanity_check_phase_a_run4.md`) avaliou 30 decks estratificados por `y1`.

| Métrica | Valor |
|---|---:|
| Falhas de fetch | 0 |
| A.1 OK contra Archidekt ao vivo | 26 |
| A.1 pulado porque o deck mudou depois do scrape | 4 |
| A.1 mismatch real | 0 |
| A.3 features idênticas ao recomputar | 30 |
| A.3 divergências de features | 0 |

Interpretação: quando o deck ao vivo ainda correspondia ao snapshot salvo, os campos centrais bateram. Os quatro casos pulados não foram tratados como erro porque o `updatedAt` ao vivo era posterior ao momento da coleta.

## Problemas encontrados e correções

| Problema | Impacto | Correção |
|---|---|---|
| Decks duplicados por `deck_id` ou lista de cartas | Poderiam enviesar a base com cópias do mesmo conteúdo | Deduplicação no processamento raw; 1.467 duplicados por deck ID ignorados e 4 listas duplicadas rejeitadas |
| Decks alterados após coleta | Validação ao vivo poderia acusar falso mismatch | Sanity check passou a pular decks cujo `updatedAt` ao vivo é posterior ao `fetched_at` salvo |
| Bug de estado padrão no scraping do EDHPowerLevel | Risco de labels `y2` incorretos por leitura de estado inicial da página | `scripts/fix_default_state_y2.py` limpou labels suspeitos; `refresh_edhpowerlevel_labels.py` reconsultou; validações posteriores confirmaram estabilidade do `commander_bracket` em 29/30 por rodada |
| Variabilidade temporal do EDHPowerLevel | Scores numéricos mudam levemente entre consultas | O projeto trata `y2` como snapshot congelado; a limitação é documentada e o ZIP processado preserva os labels usados |

## Estado final da Fase A

A Fase A está concluída para fins de modelagem: há um snapshot processado, validado, restaurável via Google Drive e com todos os `y2` preenchidos. O artefato recomendado para reprodutibilidade é o `processed.zip`, pois ele preserva os rótulos temporais do EDHPowerLevel.
