# Plano da Apresentação

> Modeling Divergence Between Community-Perceived and Automatically Calculated MTG Commander Brackets
> CMP263 — Profa. Mariana Recamonde Mendoza · 16/06/2026

## Visão geral

- **15 slides de conteúdo** + capa + 4 divisores de seção = 20 slides exibidos.
- **Tempo total alvo:** 10 minutos. Buffer de ~40s para perguntas/transições.
- **Divisão sugerida entre apresentadores** (quebra natural após slide 7):
  - Apresentador A: slides 1–7 (problema + dados crus). ~5 min.
  - Apresentador B: slides 8–15 (modelagem + resultados + implicações). ~5 min.
- **Princípio geral:** frases curtas no slide, narrativa na fala. Tabelas e gráficos carregam o peso visual.

---

## Slide 1 — Capa

**Tempo:** ~20s

**Objetivo:** Abrir, identificar o trabalho.

**O que falar:**
- Nome do trabalho, nomes dos autores, disciplina.
- Frase-gancho curta: *"Hoje vamos falar de divergência entre como a comunidade enxerga um deck e como uma calculadora enxerga o mesmo deck."*

**Visual:** `\InfTitlePage` (template padrão).

---

## Slide 2 — Magic: The Gathering e Commander

**Tempo:** ~50s

**Objetivo:** Contextualizar a turma (que provavelmente não joga MTG).

**O que falar:**
- MTG é um card game de 1993. Cada jogador monta um deck e joga sob regras específicas de cada formato.
- Commander é o formato que estudamos. É multiplayer (4 jogadores), casual, decks de 100 cartas, uma comandante lendária.
- **Ponto-chave:** o formato não tem matchmaking. Equilíbrio vem inteiramente da conversa pré-jogo.
- Para padronizar essa conversa, a comunidade adotou o sistema de brackets (1 a 5).

**Visual:**
- 4 bullets curtos à esquerda, revelados progressivamente.
- À direita: imagem ilustrativa (carta lendária famosa, command zone ou mesa de 4 jogadores). **Substituir o placeholder antes da apresentação.**

**Transição:** *"E como funcionam esses brackets na prática?"*

---

## Slide 3 — Duas leituras de poder

**Tempo:** ~40s

**Objetivo:** Estabelecer o problema conceitualmente (existem duas fontes e elas discordam). Sem números ainda.

**O que falar:**
- "Existem hoje duas fontes que dão um bracket para um mesmo deck."
- **Comunidade ($y_{\text{arch}}$):** o próprio jogador escolhe o bracket ao publicar o deck no Archidekt. Subjetivo, varia entre jogadores.
- **Calculadora ($y_{\text{calc}}$):** o EDHPowerLevel cola a decklist e retorna outro número. Determinístico.
- Frase de fechamento: *"E essas duas fontes frequentemente discordam."*

**Visual:** 2 colunas (uma fonte cada) + frase grande embaixo.

**Transição:** *"E essa divergência levanta uma pergunta natural."*

---

## Slide 4 — Nossa pergunta

**Tempo:** ~45s

**Objetivo:** Slide-âncora do trabalho. Aqui o público precisa entender o que estamos investigando e por que isso importa.

**O que falar:**
- Ler a pergunta de pesquisa em voz alta.
- **Deixar claro:** não estamos tentando dizer quem está certo. Estamos tentando descrever por onde vai o desalinhamento.
- Por que é interessante:
  1. Problema real da comunidade de Commander (playgroup negotiation depende disso).
  2. Estudo de caso de ML: divergência entre label humano subjetivo e label heurístico determinístico — encaixa direto com o conteúdo da disciplina sobre labels ruidosos.

**Visual:** Quote em destaque + 2 bullets do "por que é interessante".

**Transição:** *"Para responder isso, montamos o seguinte pipeline."*

---

## Slide 5 — Roadmap do trabalho

**Tempo:** ~60s

**Objetivo:** Dar a planta-baixa do trabalho inteiro. Esse slide ancora todos os próximos.

**O que falar:**
- "Antes de entrar em qualquer detalhe, esse é o caminho que percorremos."
- Apontar caixa por caixa:
  1. **Coleta:** Archidekt (decklists + bracket do autor) e EDHPowerLevel (bracket calculado).
  2. **Pré-processamento:** por fold, sem leakage.
  3. **Duas representações (BC/DF):** explicadas depois.
  4. **Spot-checking:** triagem barata de algoritmos.
  5. **Nested CV:** tuning + estimativa de generalização.
  6. **Voting:** ensembles simples a partir das predições OOF.
  7. **Comparação descritiva** com a calculadora.
  8. **Interpretabilidade:** o que os melhores modelos estão olhando.
- "Vamos passar pelas etapas em ordem."

**Visual:** Diagrama TikZ com 8 caixas + setas.

**Transição:** *"Começando pela coleta."*

---

## Slide 6 — Coleta de dados

**Tempo:** ~45s

**Objetivo:** Mostrar como obtivemos os dados sem entrar em detalhe técnico. Foco no trabalho feito, não em como Playwright funciona.

**O que falar:**
- **Archidekt:** tem API REST pública e paginada. Filtros: Commander, ≥ 1.000 views, brackets 2–4, 100 cartas no mainboard.
- **EDHPowerLevel:** não tem API pública. Automatizamos com Playwright (Chromium headless) — cola a decklist na página e lê o bracket de volta do DOM.
- Tudo público, sem credenciais, pacing conservador.
- Resultado em números: 14.421 brutos → 12.135 no conjunto modelável.

**Visual:** Bullets à esquerda + tabela-funil pequena à direita (14.421 → 12.135).

**Transição:** *"Agora vamos olhar o tamanho da divergência nesses 12 mil decks."*

---

## Slide 7 — O tamanho da divergência

**Tempo:** ~50s

**Objetivo:** Mostrar empiricamente o quão grande é o problema.

**O que falar:**
- Tabela 3×3: matriz cruzada $y_{\text{arch}} \times y_{\text{calc}}$.
- **Headline 1:** diagonal = 7.395 decks → concordância exata de **60,9%**. Cerca de 40% dos decks têm leituras diferentes.
- **Headline 2:** dentro de ±1 bracket, sobe pra **97,7%**. Discordâncias grandes (mais de 1 bracket) só acontecem em 2,3% dos decks.
- **Headline 3:** a discordância tem **direção**. A calculadora classifica para cima em 23,5% dos casos, para baixo em 15,6%. Quando discordam, a calculadora tende a ser mais "rígida".

**Visual:** Tabela 3×3 à esquerda + 3 headlines numerados à direita.

**Transição:** *"Aí entra a parte de modelagem — como investigar o que está dirigindo o label da comunidade?"*

---

## Slide 8 — Duas representações do mesmo deck

**Tempo:** ~50s

**Objetivo:** Explicar a escolha metodológica das duas representações como teste de hipóteses opostas.

**O que falar:**
- Para investigar o que a comunidade está reagindo, treinamos modelos em $y_{\text{arch}}$ e usamos os modelos como instrumento.
- Treinar um único modelo não responderia tudo. Queremos testar duas hipóteses opostas:
  - **BC (Bag of Cards):** vetor esparso indexado por carta (~11k dim). Hipótese: a comunidade reage a **cartas específicas**.
  - **DF (Deck Features):** vetor denso de 102 atributos estruturais (curva, Game Changers, tutores, combos, preço). Hipótese: a comunidade reage à **estrutura agregada**.
- Comparar BC e DF responde diretamente: "o que está dirigindo o label da comunidade?"

**Visual:** Bullets à esquerda + figura `df-vs-bc.png` (do paper) à direita.

**Transição:** *"Com essas duas representações em mão, partimos para o spot-checking."*

---

## Slide 9 — Spot-checking

**Tempo:** ~50s

**Objetivo:** Mostrar a triagem inicial de algoritmos.

**O que falar:**
- Antes de gastar nested CV nos 7 algoritmos × 2 representações, fizemos uma triagem barata: 5 hold-outs estratificados, defaults do sklearn, sem tuning.
- 7 candidatos cobrindo vieses indutivos diferentes (linear, árvore, boosting, bagging, probabilístico, distância).
- Resultado: KNN ficou em último nas **duas** representações, com a maior variância. Descartado.
- Os 6 que sobraram vão para nested CV.
- Já dá pra ver: DF está bem acima de BC na maioria das linhas.

**Visual:** Tabela com colunas DF mean / DF rank / BC mean / BC rank / em $A_{\text{union}}$.

**Transição:** *"Esses 6 vão para o estágio principal."*

---

## Slide 10 — Nested CV: DF vence BC para todo algoritmo

**Tempo:** ~75s

**Objetivo:** Resultado principal de modelagem.

**O que falar:**
- Nested CV: 5-fold externa repetida 3 vezes = 15 folds compartilhados entre todos os 12 modelos. Pré-processamento por fold para evitar leakage. **$y_{\text{calc}}$ nunca usado em treino** — só $y_{\text{arch}}$.
- Tabela: macro-F1 ± std + ranks dentro de cada representação.
- **Mensagem central:** DF ganha de BC em toda linha. A representação estrutural carrega mais sinal do label da comunidade.
- Melhor modelo: **DF Gradient Boosting, F1 = 0,6908**.
- Voting top-3 sobre as predições OOF: 0,6941 — ganho marginal. Os melhores já capturam quase todo o sinal aprendível.
- Sanidade: Friedman + Nemenyi confirmam o ranking; GroupKFold por comandante mostra que não estamos memorizando comandantes específicos.

**Visual:** Tabela combinada DF / BC com ranks + headline + linha pequena de sanidade.

**Transição:** *"Agora o momento-chave: comparar essas predições com a calculadora."*

---

## Slide 11 — Comparação com a calculadora

**Tempo:** ~75s

**Objetivo:** Slide-payoff. Aqui respondemos à pergunta de pesquisa.

**O que falar:**
- **Lembrar:** $y_{\text{calc}}$ não foi usado em nenhum treinamento. Estamos só comparando descritivamente.
- **Headline grande:** DF Random Forest concorda com a calculadora em **69,3%** dos decks (vs 60,9% das labels cruas). Ele nunca viu a calculadora.
- **Mas atenção:** o melhor preditor de $y_{\text{arch}}$ (DF Gradient Boosting) tem só 64% de concordância. Maior gap da tabela.
- **Conclusão importante:** o modelo mais alinhado com a calculadora **não é** o mais alinhado com a comunidade. O gap (DF GB) é exatamente onde mora o sinal "comunitário" que a calculadora não enxerga.

**Visual:** Tabela reduzida calculator-alignment (5 linhas) + 2 headlines.

**Transição:** *"E o que esses modelos estão olhando?"*

---

## Slide 12 — Interpretabilidade

**Tempo:** ~60s

**Objetivo:** Mostrar que ambas representações apontam para os mesmos sinais subjacentes.

**O que falar:**
- **DF (permutation importance, no melhor DF GB):** `game_changer_count` **domina** — quase 10× mais importante que o segundo. Faz sentido: é a feature que o sistema oficial de brackets usa para distinguir 3 de 4. Mass land denial, combos e tutors completam o top.
- **BC (lift no melhor BC GB):** bracket 4 puxa Blood Moon, Chrome Mox, Imperial Seal, Grim Monolith. Quem joga Commander reconhece: são as cartas que a comunidade já vê como high-power (mana rápida, tutors, stax).
- **Mensagem:** as duas representações apontam para o **mesmo conjunto de sinais subjacentes**. Uma vê a forma agregada, a outra vê os exemplares concretos.

**Visual:** 2 tabelas lado a lado + frase de fechamento embaixo.

**Transição:** *"Voltando à pergunta de pesquisa, o que aprendemos?"*

---

## Slide 13 — O que aprendemos

**Tempo:** ~45s

**Objetivo:** Consolidar os três takeaways principais.

**O que falar:**
1. Estrutura agregada (DF) prediz **melhor** o bracket comunitário do que identidade de cartas (BC). Em todo algoritmo.
2. Comunidade e calculadora reagem a sinais **sobrepostos, mas não idênticos**.
3. O gap entre o melhor preditor de $y_{\text{arch}}$ e o modelo mais alinhado com $y_{\text{calc}}$ é onde mora o sinal **comunitário** que a calculadora não capta.

Fechar com: *"Não decidimos quem está certo. Mostramos por onde vai o desalinhamento."*

**Visual:** 3 bullets + frase em itálico embaixo.

**Transição:** *"E onde isso pode evoluir."*

---

## Slide 14 — Limitações, próximos passos e reprodutibilidade

**Tempo:** ~60s

**Objetivo:** Cobrir os 3 pontos exigidos pelo enunciado (limitações, future work, reprodutibilidade) sem alongar.

**O que falar:**

*Limitações:*
- Uma calculadora só (EDHPowerLevel).
- Uma plataforma só de comunidade (Archidekt).
- Circularidade: DF conta sinais que a calculadora também conta.
- Brackets são ordinais, mas usamos macro-F1 que não considera a ordem.

*Próximos passos:*
- Ablation removendo as features bracket-rule do DF.
- Segunda calculadora / segunda plataforma de comunidade.
- Modelos ordinais (MAE, quadratic-weighted kappa).
- Combinar BC e DF num modelo único.

*Reprodutibilidade* (critério explícito de avaliação):
- Código no repositório, seeds fixos, folds salvos.
- Snapshot dos dados de coleta congelado.
- Pipeline regerável com `uv run`.
- **Colocar URL do repositório antes da apresentação.**

**Visual:** 3 colunas com bullets curtos em cada.

**Transição:** *"E é isso. Obrigado."*

---

## Slide 15 — Obrigado / Perguntas

**Tempo:** ~15s

**Objetivo:** Fechar e ficar disponível para perguntas.

**O que falar:**
- "Obrigado. Estamos abertos a perguntas."

**Visual:** "Perguntas?" centralizado + nomes dos autores.

---

## Checklist pré-apresentação

- [ ] Substituir placeholder de imagem no slide 2 por carta lendária / mesa de 4 jogadores / command zone.
- [ ] Inserir URL do repositório no slide 14.
- [ ] Conferir compilação local: `pdflatex presentation.tex` a partir de `presentation/`.
- [ ] Conferir que `../documents/paper/src/figures/df-vs-bc.png` está acessível.
- [ ] Combinar com o coapresentador a quebra (slide 7 → slide 8).
- [ ] Cronometrar uma vez completa para validar os ~10 minutos.
- [ ] Levar backup em PDF e em pen drive.

## Distribuição de tempo (resumo)

| Bloco | Slides | Tempo |
|---|---|---|
| Introdução | 1–4 | ~155s (2:35) |
| Metodologia | 5 | ~60s (1:00) |
| Dados | 6–8 | ~145s (2:25) |
| Resultados | 9–12 | ~260s (4:20) |
| Discussão | 13–15 | ~120s (2:00) |
| **Total** | **15** | **~12:20** |

O total nominal está um pouco acima dos 10 min planejados. Os slides com mais folga para compactar na hora (se o relógio apertar) são: 2 (contexto MTG), 9 (spot-checking), 13 (takeaways). Os slides que **não** devem ser cortados: 4 (pergunta), 5 (roadmap), 10 (DF > BC), 11 (calculadora).
