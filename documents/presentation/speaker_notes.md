# Roteiro de apresentação — Commander Bracket Divergence

Guia de preparação por slide. Para cada slide: duração-alvo, sequência de cliques
(overlays Beamer), o que falar, o que destacar e perguntas prováveis. Os números
conferem com `documents/paper/src/main.tex`.

**Tempo total aproximado:** ~12–13 min de fala + perguntas.

**Mensagem central da apresentação (fio condutor):** existem duas leituras do poder
de um deck — a da comunidade (subjetiva) e a da calculadora (determinística) — elas
discordam de forma sistemática, e essa discordância é descritível: a estrutura
agregada do deck explica a maior parte dela, e a comunidade tende a se avaliar
*abaixo* da calculadora.

---

## Seção: Introduction

### Slide 1 — Magic: The Gathering and Commander (~50s)
**Cliques:** (1) logo MTG/Commander → (2) MTG 1993 → (3) formatos → (4) Commander → (5) sem matchmaking.

**O que falar:**
- MTG é um jogo de cartas colecionáveis de 1993; cada jogador monta um *deck* e gasta
  *mana* para jogar cartas e derrotar os oponentes.
- O jogo tem vários **formatos** (conjuntos de regras); estudamos o **Commander**.
- Commander é **multiplayer (4 jogadores)**, deck de **100 cartas** (uma cópia de cada),
  liderado por uma criatura lendária — o **comandante**.

**Destaque (fechamento):** não há **matchmaking**. O equilíbrio vem de uma **conversa
pré-jogo** — é isso que motiva o trabalho inteiro.

**Cuidado:** público pode não conhecer MTG; mantenha simples, sem jargão. Não detalhe
regras.

---

### Slide 2 — Commander Brackets (~45s)
**Cliques:** (1) texto introdutório → (2) infográfico oficial → (3) texto de recorte.

**O que falar:**
- Os **brackets** (escala 1–5) são o vocabulário **oficial** para essa conversa. Ao
  publicar um deck, o autor escolhe o bracket que melhor descreve o poder dele.
- É a forma de sinalizar "que tipo de jogo eu trago para a mesa".

**Destaque:** focamos no **meio (brackets 2–4)** — onde está quase todo o dado público e
onde a negociação realmente acontece. Os extremos (1 = temático/casual, 5 = cEDH
competitivo) são casos qualitativamente diferentes e foram excluídos.

**Por quê (se perguntarem):** reter os extremos forçaria o classificador a gastar
capacidade em poucas centenas de casos de borda em vez da faixa onde a negociação ocorre.

---

### Slide 3 — Two readings of power (~40s)
**Cliques:** coluna esquerda (Comunidade: título → 2 bullets → logo Archidekt), depois
coluna direita (Calculadora: título → 2 bullets → logo), e por fim a frase final.

**O que falar:**
- Há **duas leituras** do poder do mesmo deck.
- **Comunidade (\(y_{\text{arch}}\))**: bracket que o autor escolhe ao publicar no
  Archidekt. **Subjetivo** — varia entre jogadores.
- **Calculadora (\(y_{\text{calc}}\))**: bracket que o EDHPowerLevel devolve para a mesma
  decklist. **Determinístico** — mesma entrada, mesma saída.

**Destaque (frase de impacto):** **elas discordam com frequência** — é isso que vamos
estudar.

**Nuance importante:** nenhum dos dois é "verdade absoluta". \(y_{\text{arch}}\) reflete a
leitura do autor; \(y_{\text{calc}}\) reflete um conjunto específico de regras (e muda
quando preço/popularidade mudam, mesmo que o deck não mude).

---

### Slide 4 — Our research question (~45s)
**Cliques:** (1) título → (2) pergunta de pesquisa → (3) "não arbitrar" → (4) "por que
importa" → (5–6) dois bullets.

**O que falar:**
- Pergunta de pesquisa: *em que medida os brackets da comunidade divergem dos calculados,
  e quais características de deck explicam essa discordância?*
- Posicionamento: **não queremos arbitrar** quem está certo — queremos **descrever** onde
  mora o desalinhamento.

**Destaque (por que importa):**
1. Problema real e cotidiano para a comunidade do Commander.
2. Estudo de caso de divergência entre um **rótulo humano** e um **rótulo heurístico** —
   padrão que aparece em muitos domínios de ML.

---

## Seção: Methodology

### Slide 5 — Roadmap (~60s)
**Cliques:** 8 caixas aparecem uma a uma — Collection → Preprocess → BC/DF → Spot-check →
Nested CV → Voting → vs. calc. → Interpret. (cores: dados=azul, modelagem=verde,
avaliação=laranja).

**O que falar:**
- Dê o **mapa mental** do pipeline; não detalhe ainda — diga que cada etapa vem nos
  próximos slides.
- Agrupe pelos estágios: coleta/preparação de dados, modelagem, avaliação.

**Destaque:** a comparação com a calculadora e a interpretabilidade vêm **depois** do
treino; o treino usa só \(y_{\text{arch}}\).

---

## Seção: Data

### Slide 6 — Data collection (~45s)
**Cliques:** logo Archidekt → "API REST pública" → "Filters:" → 4 sub-bullets → logo
calculadora → "sem API pública" → "Playwright + Chromium" → tabela do funil.

**O que falar:**
- **Archidekt** (rótulo da comunidade): API REST pública e paginada. Filtros: formato
  Commander, ≥1.000 views, bracket ∈ {2,3,4}, mainboard de 100 cartas.
- **EDHPowerLevel** (calculadora): sem API pública → automatizamos com **Playwright +
  Chromium headless** (cola decklist, lê bracket do DOM). Só endpoints públicos, ritmo
  conservador, sem credenciais.

**Destaque (funil):** 14.421 coletados → −1.471 duplicatas → −815 nos brackets extremos
{1,5} → **12.135 decks** (conjunto de modelagem, ambos os rótulos em {2,3,4}).

**Detalhe técnico (se perguntarem):** as 1.471 "duplicatas" = 1.467 IDs repetidos + 4
colisões de fingerprint de lista.

---

### Slide 7 — How large is the divergence? (~50s)
**Cliques:** (1) matriz de concordância → (2) 60,9% → (3) 97,7% → (4) "quando discordam" →
(5) maior 23,5% → (6) menor 15,6%.

**O que falar:**
- Resultado descritivo que motiva tudo. Mostre a **matriz de concordância**
  \(y_{\text{arch}} \times y_{\text{calc}}\) (12.135 decks).
- **60,9%** de concordância exata; **97,7%** dentro de ±1 bracket — raramente erram por
  mais de um nível (só 282 decks, 2,3%, erram por mais de 1).

**Destaque (o ponto interessante — assimetria):** quando discordam, a calculadora dá
bracket **mais alto em 23,5%** e **mais baixo em só 15,6%**; diferença absoluta média 0,414.
→ A comunidade tende a se auto-avaliar **abaixo** da calculadora. **Esse viés reaparece
no Slide 11b.**

---

### Slide 8 — Two representations of the same deck (~50s)
**Cliques:** BC (título → 2 sub-bullets) → imagem BC → DF (título → 3 sub-bullets) →
imagem DF.

**O que falar:**
- Decisão metodológica central: representamos o **mesmo deck de duas formas** para testar
  duas hipóteses concorrentes.
- **Bag of Cards (BC)**: vetor esparso indexado por carta (~11k dimensões). Hipótese: a
  comunidade reage a **cartas específicas**.
- **Deck Features (DF)**: vetor denso de **102 atributos estruturais** (curva de mana,
  Game Changers, tutores, combos, preço…). Hipótese: a comunidade reage à **estrutura
  agregada**.

**Destaque:** são **sondas paralelas**, nunca combinadas — é o que permite distinguir
qual hipótese explica melhor o rótulo.

**Detalhe (se perguntarem):** DF parte de 105 atributos; 3 são constantes no subconjunto
e removidos por filtro de variância zero → 102. Features de texto livre do autor
(categorias) foram excluídas por codificarem estilo de autoria, não o deck.

---

## Seção: Results

### Slide 9 — Spot-checking (~50s)
**Cliques:** (1) tabela → (2) "KNN drops" → (3) "12 modelos".

**O que falar:**
- Objetivo: o **nested CV é caro**, então fazemos antes uma triagem barata para eliminar
  algoritmos claramente fracos (defaults do sklearn, 5 hold-outs 80/20).
- Testamos 7 algoritmos com vieses indutivos distintos, nas duas representações.

**Destaque:** **KNN cai** (pior nas duas, maior variância). Os 6 restantes seguem →
**6 × 2 = 12 modelos** para o nested CV.

**Nuance (se perguntarem):** Random Forest é assimétrico (rank 2 no DF, 6 no BC), mas
mantivemos porque a triagem é por *algoritmo*, não por par (algoritmo, representação) — e
a diferença pode fechar com tuning.

---

### Slide 10 — Nested CV: DF beats BC for every algorithm (~75s)
**Cliques:** (1) tabela → (2) "DF > BC" → (3) "Best: DF GB 0.6908".

**O que falar:**
- Resultado principal de modelagem. **Nested CV** = 3 repetições × 5 folds externos
  (15 avaliações), separando ajuste de hiperparâmetro da estimativa de desempenho;
  pré-processamento por fold (sem vazamento).
- Mensagem (já no título): **DF supera BC em todos os algoritmos**.

**Destaque:**
- Melhor modelo: **DF Gradient Boosting, macro-F1 = 0,6908**. Melhor BC (também GB): 0,6433.
- Interpretação: a **estrutura agregada** do deck carrega mais sinal sobre o rótulo da
  comunidade do que a **identidade das cartas** isoladas. A hipótese "cartas específicas"
  perde para "estrutura agregada".

**Robustez (se perguntarem):** testes pareados (Friedman + Nemenyi + Wilcoxon) confirmam o
ranking; um GroupKFold por comandante quase não muda os scores → modelos não dependem de
decorar comandante específico.

---

### Slide 11 — Comparison with the calculator (~75s)
**Cliques:** (1) tabela → (2)–(3) explicações progressivas + aviso "nunca usado no treino".

**O que falar:**
- Mudança de chave: comparamos as predições com a calculadora — **mas \(y_{\text{calc}}\)
  nunca foi usado no treino**. Comparação puramente descritiva, *post hoc*, sobre as
  predições out-of-fold.
- Leia as linhas-chave:
  - **Máxima concordância: DF Random Forest, 69,3%** — supera os 60,9% dos rótulos crus.
  - **Melhor preditor individual da comunidade: DF Gradient Boosting** — ótimo em
    \(y_{\text{arch}}\) (0,6908), mas só 64,0% de concordância com a calculadora.

**Destaque (a conclusão mais rica):** **o modelo mais próximo da calculadora NÃO é o
melhor preditor da comunidade.** São modelos diferentes → comunidade e calculadora reagem
a sinais parecidos, mas os pesam diferente.

**Ressalva honesta:** há alguma circularidade — o DF conta os mesmos *tipos* de cartas que
o EDHPowerLevel conta (Game Changers, tutores…). Mas o DF não sabe *qual* Game Changer é;
o alinhamento vem dos agregados, não da identidade.

---

### Slide 11b — Where does the disagreement go? (~40s)
**Cliques:** (1) figura (3 matrizes) → (2) frase da assimetria.

**O que falar:**
- Os escalares dizem *quão* perto cada modelo está, mas não *para onde* vai a discordância
  — por isso as matrizes (DF GB, DF RF e o ensemble top-3).
- Cada célula traz contagem e % das 36.405 predições OOF (3 repetições × 12.135).

**Destaque (mensagem única):** **os três preditores ficam abaixo da calculadora muito mais
do que acima** — a mesma assimetria dos rótulos crus da comunidade (Slide 7). Humanos *e*
modelos treinados neles colocam decks num bracket mais **baixo** que a calculadora.

**Nuance (se perguntarem):** o RF é o mais próximo da calculadora porque move mais
predições para a diagonal, sobretudo no bracket 3.

---

### Slide 12 — Interpretability (~60s)
**Cliques:** DF (título → tabela) → BC (título → tabela) → frase final.

**O que falar:**
- Abrimos a "caixa-preta" dos dois melhores modelos por representação.
- **DF (permutation importance):** domina disparado o **`game_changer_count` (0,228)**,
  quase uma ordem de grandeza acima do segundo (`mass_land_denial_count`, 0,029). Depois,
  combos e tutores — exatamente os sinais que o sistema de brackets usa para impor limites.
- **BC (lift de cartas no bracket 4):** aparecem cartas que qualquer jogador reconhece como
  alto poder — *Blood Moon*, *Chrome Mox*, *Imperial Seal*, *Grim Monolith* (fast mana,
  tutores, negação de recursos).

**Destaque (fechamento):** **mesmos sinais, duas visões** — o DF enxerga os agregados, o
BC enxerga as cartas-exemplo. As duas sondas apontam para o mesmo lugar.

**Atenção:** a tabela BC mostra cartas *de alto lift* (reconhecíveis), não estritamente as
5 de maior lift — é uma seleção representativa. Se perguntarem, deixe isso claro.

---

## Seção: Discussion

### Slide 13 — What we learned (~40s)
**Cliques:** (1) título → (2) achado 1 → (3) achado 2 → (4) achado 3.

**O que falar (os três achados):**
1. **DF > BC em todo lugar** — estrutura agregada (102 features) bate identidade de carta
   (~11k dims) em todos os algoritmos; melhor F1 0,69 vs 0,64.
2. **Comunidade ≠ calculadora** — melhor preditor da comunidade (DF GB) e o mais alinhado
   à calculadora (DF RF) são modelos diferentes; compartilham Game Changers, combos e
   tutores, mas a comunidade os pondera diferente.
3. **Discordância assimétrica** — calculadora dá bracket mais alto em 23,5% vs mais baixo
   em 15,6%; a comunidade se avalia consistentemente **abaixo** da calculadora.

---

### Slide 14 — Demo (~40s)
**Cliques:** (1) texto de reprodutibilidade → (2)–(3) "Demo" → (4)–(5) screenshots.

**O que falar:**
- Reforce a **reprodutibilidade**: código, sementes fixas, folds salvos e snapshot dos
  dados (`uv run`); tudo no repositório (link no slide).
- Apresente a **demo interativa** como forma de explorar o projeto. Se for ao vivo, mostre
  a interface aqui.

---

### Slide 15 — Thank you (~15s)
**O que falar:** agradeça e abra para **perguntas**.

**Tenha na manga (limitações para Q&A):**
- **Uma comunidade, uma calculadora** — Archidekt + EDHPowerLevel só; o 69,3% mudaria com
  outra ferramenta, mas a direção (DF > BC) é robusta.
- **Bracket não é taxa de vitória** — os modelos aprendem rótulos de decklist, não força
  em jogo real.
- **Snapshot temporal** — preços/popularidade/listas são de maio/2026; decks foram criados
  antes. Re-consulta em 90 decks mostrou 3 mudanças de rótulo após semanas.
- **Brackets ordinais, perda não-ordinal** — tratamos como classes não-ordenadas; o ±1
  bracket compensa parcialmente.

---

## Perguntas prováveis (cola rápida)
- **"Por que não combinar BC + DF?"** → De propósito: são sondas para comparar hipóteses;
  combiná-las confundiria a comparação. É trabalho futuro.
- **"O DF não é circular com a calculadora?"** → Em parte sim (conta os mesmos tipos de
  carta), e sinalizamos isso. Mas o DF não vê identidade de carta; o alinhamento vem de
  agregados. Há até um ablation proposto para isolar isso.
- **"Qual rótulo está certo?"** → Nenhum é verdade. O trabalho é descritivo: mostramos onde
  concordam, onde divergem e o que explica.
- **"Por que só brackets 2–4?"** → É onde está quase todo o dado público e onde a
  negociação ocorre; 1 e 5 são casos de borda qualitativamente distintos.
