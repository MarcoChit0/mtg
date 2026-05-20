# Implementação — Fase A: Coleta, Processamento e Validação

> Implementation report. **Público**: colaborador novo ou agente LLM que vai mexer no scraping/processamento de dados. Os números da última coleta vivem em [../results/phase_a_data_collection.md](../results/phase_a_data_collection.md).

## Objetivo

Construir um snapshot reprodutível de decks Commander públicos do Archidekt dentro do escopo do projeto (y1 ∈ {2,3,4}, ≥1000 views, exatamente 100 cartas no mainboard, válido em Commander) e enriquecer com `y2` (EDHPowerLevel) para análise de divergência. Saídas frozen em `data/processed/archidekt/`, distribuídas via Drive para colaboradores e usuários externos.

## O que foi construído

| Componente | Arquivo | Responsabilidade |
|---|---|---|
| Coleta Archidekt | [scripts/fetch_archidekt_raw.py](../../../scripts/fetch_archidekt_raw.py) | Paginar `archidekt.com/api/decks/cards/` por bracket; baixar detalhe por deck via `/api/decks/<id>/`; grava 3 JSONL raw |
| Cliente EDHPowerLevel | [scripts/edhpowerlevel_client.py](../../../scripts/edhpowerlevel_client.py) | Cliente Playwright que cola a decklist no SPA https://edhpowerlevel.com e extrai `commander_bracket`, `power_level`, `score`, `efficiency`, `impact`, `tipping_point`, `average_playability` |
| Processamento | [scripts/process_archidekt_raw.py](../../../scripts/process_archidekt_raw.py) | Phase A.1 (ingest) + Phase A.2 (enrich y2 via cliente acima). Produz `decks.jsonl`, `cards.jsonl`, `processing_manifest.jsonl`, `rejected_decks.jsonl`, `edhpowerlevel_results.jsonl` |
| Features | [scripts/build_features.py](../../../scripts/build_features.py) | Lê `decks.jsonl` + `cards.jsonl` e materializa `deck_features.jsonl` + `bag_of_cards.jsonl` |
| Sanity check | [scripts/sanity_check_phase_a.py](../../../scripts/sanity_check_phase_a.py) | Reconsulta 30 decks ao vivo e compara cartas + features locais |
| Manutenção `y2` | [scripts/fix_default_state_y2.py](../../../scripts/fix_default_state_y2.py), [scripts/refresh_edhpowerlevel_labels.py](../../../scripts/refresh_edhpowerlevel_labels.py), [scripts/validate_edhpowerlevel_labels.py](../../../scripts/validate_edhpowerlevel_labels.py) | Detectam e corrigem rótulos suspeitos do scraping inicial |
| Restore | [scripts/download_archidekt_processed.py](../../../scripts/download_archidekt_processed.py) | Baixa o snapshot do Drive público, extrai allowlist de arquivos, gera `processed_restore_report.json` |

## Como foi construído (decisões + porquês)

### Por que dois estágios (raw → processed)?
O scrape do Archidekt é caro e pouco confiável (rate limits, latência). Salvar os payloads JSON raw permite reprocessar a base inteira sem reconsultar o site quando uma decisão de filtragem muda (ex: trocar critério de validade, adicionar nova feature). O raw é tratado como fonte verdadeira; o processed é derivado e descartável.

### Por que Playwright e não API/HTTP direto pro EDHPowerLevel?
EDHPowerLevel é um SPA: o cálculo de `power_level`/`commander_bracket` roda no navegador, não no backend (o Cloud Run só enriquece dados de cartas). Tentamos engenharia reversa do JS, mas as fórmulas mudam com atualizações do site. Solução pragmática: Chromium headless, cola a decklist, clica Analyze, lê o DOM com regexes (ver `RESULT_PATTERNS` em [edhpowerlevel_client.py:42](../../../scripts/edhpowerlevel_client.py#L42)). Mais lento mas robusto a mudanças visuais.

### Por que regex `inner_text("body")` em vez de seletores CSS?
A página usa headers com emoji (⚡ Power Level, ⚖️ Tipping Point) e estrutura DOM que muda entre updates. `inner_text` linealiza tudo e regex sobre o texto resultante sobrevive a reorganizações visuais. O único campo que **deve** estar presente é `commander_bracket`; os demais são opcionais (regex loose, deliberado).

### Filtros de inclusão (`process_archidekt_raw.py`)
| Filtro | Razão |
|---|---|
| `bracket ∈ {2,3,4}` | Backbone §8: bracket 1 é casual/temático, 5 é cEDH; ambos têm pouca densidade de sinal estrutural |
| `viewCount ≥ 1000` | Filtra decks de baixa visibilidade que podem ser experimentais/abandonados. Ajustável (backbone §8) — pode cair pra 500 se a base ficar pequena |
| Exatamente 100 cartas no mainboard | Regra do formato Commander |
| Companion permitido como 101ª carta | Mecânica oficial; companion fica fora dos 100 mas conta como slot |
| Maybeboard/Sideboard/Tokens excluídos | Backbone §8: só o mainboard de jogo entra |

### Deduplicação
Dois níveis:
1. **Por `deck_id`**: se o mesmo deck for retornado em páginas diferentes (pode acontecer com paginação volátil), só a primeira ocorrência conta. 1467 duplicados ignorados na última rodada.
2. **Por fingerprint da lista de cartas**: dois `deck_id` distintos com a mesma lista são tratados como cópia. 4 listas duplicadas rejeitadas.

### Bug do "default state" do EDHPowerLevel
Na primeira coleta de `y2`, o cliente Playwright às vezes lia o estado inicial da página antes do JS terminar de renderizar o resultado da decklist colada. Sintoma: alguns decks recebiam scores suspeitamente uniformes. Correção:
1. `fix_default_state_y2.py` identificou e limpou labels suspeitos.
2. `refresh_edhpowerlevel_labels.py` reconsultou esses decks.
3. `validate_edhpowerlevel_labels.py` confirmou estabilidade: 87/90 (96,7%) reconsultados receberam o mesmo `commander_bracket`, com as 3 divergências em decks de fronteira (Δ `power_level` ≤ 0,3).

Hoje o cliente espera explicitamente o seletor do bracket renderizado antes de extrair (ver `_wait_for_result` em [edhpowerlevel_client.py](../../../scripts/edhpowerlevel_client.py)).

### `customCmc` ignorado (decisão 2026-05-13)
O Archidekt deixa o usuário sobrescrever o CMC de uma carta por deck. 2.421 decks (18,7%) usam isso, com 10.758 linhas sobrescritas. Algumas legítimas (X-spells), outras subjetivas. Por simetria com a §11.1.F do backbone (não deixar entrada livre do usuário poluir features estruturais), `build_features.py` usa estritamente `oracleCard.cmc`. O `custom_cmc` continua preservado por linha em `decks.jsonl` para auditoria, mas não vira feature.

### Restore via Drive público
[`download_archidekt_processed.py`](../../../scripts/download_archidekt_processed.py) é o único caminho recomendado para usuários externos. O snapshot frozen no Drive (`file_id=1gXCxPeFjxgkNmizWCTU62m-s311B05R0`) preserva os labels `y2` da rodada original — recoletar daria scores um pouco diferentes por causa da variabilidade temporal (preço/popularidade na fórmula do EDHPowerLevel). O download usa o downloader robusto compartilhado com `sync_experiments_drive.py` (cookies + páginas de aviso de tamanho do Drive).

## Pontos de extensão / armadilhas

- **Adicionar novo filtro de inclusão**: editar `process_archidekt_raw.py` na função de validação; lembrar que o snapshot frozen no Drive **não vai re-aplicar o filtro** — quem baixar do Drive usa a base velha. Pra propagar, recoletar y2 (custo alto) ou refazer só o processamento se o filtro for sobre campos já presentes.
- **Adicionar nova feature derivada**: implementar em `build_features.py`, regenerar `deck_features.jsonl` e re-publicar `processed.zip` no Drive.
- **Mudar critérios de y2**: NÃO. `y2` é snapshot; a variabilidade temporal está documentada no backbone §3. Re-scrape produz números levemente diferentes.
- **Recoletar do Archidekt**: roda em horas mas é frágil (rate limit, scraper pode quebrar com mudança no site). Mantenha o `Archive.zip` raw no Drive como artefato de backup antes de qualquer recoleta.

## Problemas encontrados e correções

| Problema | Diagnóstico | Correção |
|---|---|---|
| Duplicação de decks por deck_id na paginação | API às vezes retorna o mesmo deck em páginas diferentes durante updates | Dedup por deck_id no ingest |
| Listas idênticas com deck_id diferentes | Forks/clones do mesmo deck | Dedup por fingerprint de cartas |
| Validação live falhava em decks atualizados | `updatedAt` ao vivo > `fetched_at` salvo | Sanity check pula esses casos em vez de marcar mismatch |
| `y2` default state | Cliente lia DOM antes do render | `fix_default_state_y2.py` + reespera de seletor no cliente |
| Variabilidade temporal do `y2` | Fórmula do EDHPowerLevel usa preço/popularidade | Tratamos `y2` como snapshot frozen; limitação documentada |
