# Project Brief — Divergência entre Brackets de Commander

## Título provisório

**Divergence Between Community-Perceived and Automatically Calculated Commander Brackets**

Uma alternativa em inglês, mais acadêmica:

**Modeling Divergence Between Community-Perceived and Automatically Calculated MTG Commander Brackets**

## 1. Contexto

No formato **MTG Commander**, a experiência de jogo depende muito do alinhamento de poder entre os decks sentados à mesma mesa. Quando um deck é significativamente mais forte, mais consistente ou mais otimizado que os demais, a partida pode se tornar frustrante, mesmo que todos os jogadores acreditem estar jogando dentro de uma faixa parecida de poder.

Os **Commander Brackets** existem para ajudar nessa conversa. Eles funcionam como uma linguagem comum para comunicar expectativa de jogo, nível de otimização e presença de elementos considerados mais fortes ou competitivos.

No entanto, brackets não são uma medida objetiva e perfeita de força. Eles envolvem percepção, intenção, contexto social e interpretação. Um mesmo deck pode ser visto como casual por seu criador, mas como mais forte por uma calculadora automatizada. O inverso também pode acontecer: um deck pode parecer forte para o jogador, mas não apresentar sinais estruturais que uma calculadora considere suficientes para classificá-lo em um bracket mais alto.

Este projeto nasce dessa diferença entre duas formas de avaliar poder em Commander:

1. **Percepção comunitária ou do usuário**, representada pelo bracket informado no Archidekt.
2. **Avaliação automatizada**, representada pelo bracket calculado por uma ferramenta externa, inicialmente o EDHPowerLevel.

O ponto central não é descobrir qual dessas fontes está correta. O ponto central é medir e explicar a **divergência** entre elas.

## 2. Problema

Commander não possui um *ground truth* universal de poder de deck.

Não há uma medida definitiva que diga, de forma objetiva, que um deck é bracket 2, 3 ou 4. O poder percebido depende de vários fatores:

* composição do deck;
* intenção do jogador;
* experiência local de mesa;
* familiaridade com o comandante;
* presença de combos;
* velocidade do deck;
* consistência;
* interação;
* preço e disponibilidade das cartas;
* reputação de certas cartas ou estratégias;
* expectativas sociais do grupo.

Por isso, duas fontes diferentes podem classificar o mesmo deck de maneira distinta.

A questão-chave do projeto é entender **o quão longe a percepção da comunidade está da avaliação automatizada**, e quais características dos decks parecem estar associadas a essa distância.

## 3. Pergunta principal

A pergunta principal do projeto é:

> **Em que medida o bracket atribuído no Archidekt diverge do bracket calculado automaticamente, e quais características dos decks ajudam a explicar essa divergência?**

Em inglês:

> **To what extent do Archidekt-assigned Commander brackets diverge from automatically calculated bracket estimates, and which deck characteristics help explain this disagreement?**

Essa pergunta evita tratar qualquer fonte como verdade absoluta. O projeto não busca decidir quem está certo. Ele busca entender o desalinhamento entre duas percepções de poder.

Uma premissa importante é que a percepção comunitária pode variar bastante. Dois usuários diferentes podem montar listas muito parecidas, ou até o mesmo deck, e atribuir brackets diferentes, porque cada um interpreta poder, intenção e experiência de mesa de forma própria.

Já a calculadora automatizada é **parcialmente** determinística: para o mesmo deck no mesmo instante de consulta, ela tende a retornar o mesmo label. Porém, suas regras incorporam sinais temporais — preço médio das cartas e popularidade — que evoluem ao longo do tempo. Por isso, o mesmo deck pode receber brackets diferentes em consultas feitas em momentos distintos (especialmente decks de fronteira entre brackets). Empiricamente, validamos isso na Fase A: 87/90 (96,7%) dos decks reconsultados receberam o mesmo `commander_bracket`, com as discrepâncias concentradas em decks cujo `power_level` está próximo do limite entre dois brackets.

Essa diferença é central para o projeto: o Archidekt representa uma percepção humana/comunitária com variação subjetiva; a calculadora representa uma avaliação automatizada baseada em regras, mais estável que a humana mas ainda sujeita a flutuações por sinais temporais externos (mercado, meta).

## 4. Objetivo geral

O objetivo geral é estudar a divergência entre duas famílias de bracket para decks Commander:

* o bracket informado no Archidekt;
* o bracket calculado por uma ferramenta externa.

A partir disso, o projeto busca entender:

* com que frequência as duas fontes concordam;
* em quais situações elas discordam;
* se a calculadora tende a classificar decks acima ou abaixo do Archidekt;
* se a discordância costuma ser pequena ou grande;
* quais características dos decks estão associadas a maior divergência;
* se a divergência é melhor explicada por cartas específicas ou por propriedades agregadas do deck.

## 5. Objetivos específicos

O projeto pretende:

1. Coletar decks públicos de Commander do Archidekt.
2. Filtrar decks válidos dentro do escopo definido.
3. Obter dois rótulos para cada deck:

   * bracket do Archidekt (`y1`, percepção comunitária — usado como **alvo de treino**);
   * bracket calculado pela calculadora externa (`y2`, avaliação automatizada — usado como **benchmark de comparação**, não como alvo de modelo).
4. Representar cada deck de duas formas:

   * **Bag of Cards (BC)**;
   * **Deck Features (DF)**.
5. Fazer **spot-checking** com 7 algoritmos candidatos (DT, RF, GB, NB, LR, LinearSVC, KNN), todos viáveis nas duas representações, com **N=5 repetições** (seeds `{1, 2, 3, 4, 5}`) para reportar média ± desvio padrão. Selecionar os **top-5 por representação** (BC e DF independentes). A união `A_uniao = A_BC ∪ A_DF` (5 a 7 algoritmos distintos) é o conjunto da Fase E, no qual **cada algoritmo da união é treinado em ambas as representações**, gerando `|A_uniao| × 2` modelos (10 a 14). A otimização de hiperparâmetros é feita modelo a modelo via nested CV, com grids limitados a até 192 configurações por algoritmo para evitar explosão combinatorial.
6. Avaliar o quanto a percepção comunitária pode ser aprendida a partir dos dados observáveis do deck.
7. Comparar as predições dos modelos com `y2` da calculadora — identificar quais modelos têm comportamento mais próximo do da calculadora.
8. Analisar diretamente a divergência entre `y1` e `y2`, independente de modelos.
9. Interpretar os **dois melhores modelos** (melhor BC + melhor DF) para entender quais cartas e quais features explicam o bracket comunitário.
10. **Ensemble por votação** (hard voting) dos top-3/top-5 BC, top-3/top-5 DF, top-3 BC + top-3 DF e de todos os modelos individuais (`voting_all`), a partir das predições out-of-fold (sem retreino).
11. (Opcional, se o cronograma permitir) realizar **stacking** dos modelos individuais para prever `y1` e comparar o stacking final com `y2`.

**Decisão metodológica**: a calculadora não é alvo de modelo. Treinar um modelo para prever a saída de outra ferramenta determinística (a calculadora produz o mesmo `y2` para o mesmo input) seria redundante e não responde à pergunta central. Tratamos `y2` como **fonte alternativa de avaliação** contra a qual comparamos os modelos treinados em `y1`.

## 6. O que o projeto não pretende afirmar

O projeto não pretende afirmar que:

* o bracket do Archidekt é o bracket verdadeiro;
* o bracket da calculadora é o bracket verdadeiro;
* uma fonte é universalmente melhor que a outra;
* o modelo mede a força real de um deck;
* o modelo prediz taxa de vitória;
* o modelo prediz diversão da mesa.

A formulação correta é mais cuidadosa:

> O projeto compara duas leituras imperfeitas de poder e busca explicar onde elas se alinham ou divergem.

## 7. Fonte de dados

A base de dados virá do **Archidekt**.

O Archidekt será usado como fonte de:

* decklists;
* metadados de decks;
* bracket informado no deck;
* categorias do deck;
* categorias por carta;
* metadados das cartas;
* flags específicas de bracket;
* dados de combos;
* preços;
* EDHREC rank;
* salt score;
* raridade;
* tipos, cores, CMC, keywords e layout das cartas.

Para o escopo atual, a API/raw JSON do Archidekt é considerada suficiente. A API do Scryfall não será necessária como fonte obrigatória nesta etapa, pois o raw do Archidekt já traz metadados ricos das cartas.

O Scryfall pode continuar sendo uma extensão futura para validação canônica, mas não faz parte do escopo atual.

## 8. Decks considerados

Serão considerados apenas decks que satisfaçam os seguintes critérios:

* decks públicos do Archidekt;
* formato Commander;
* decks legais e válidos para o formato;
* pelo menos 1000 visualizações no Archidekt, inicialmente;
* bracket informado no Archidekt;
* bracket entre 2 e 4;
* exatamente 100 cartas no mainboard;
* considerar apenas as 100 cartas do mainboard;
* excluir Maybeboard, Sideboard, Tokens/Extras e qualquer item fora do deck principal.

A restrição aos brackets 2–4 reduz o ruído dos extremos. Bracket 1 pode representar decks muito casuais, temáticos ou pouco otimizados. Bracket 5 pode envolver intenção competitiva e contexto cEDH. O foco em 2–4 torna o problema mais tratável e mais alinhado ao escopo do trabalho.

O projeto precisa de uma quantidade grande de decks para treinar e testar modelos com alguma confiabilidade. Por isso, o filtro de visualizações será tratado como um parâmetro ajustável. O valor inicial será 1000 visualizações, mas, se esse critério gerar poucos decks, o limite poderá ser reduzido para 500 visualizações.

Essa redução não muda a pergunta do projeto; ela apenas amplia a base amostral caso o filtro inicial seja restritivo demais.

## 9. Labels

O projeto terá duas famílias de rótulos:

```text
y1 = bracket do Archidekt
y2 = bracket calculado pela calculadora externa
```

Esses rótulos não serão tratados como verdadeiro e falso. Eles representam duas leituras diferentes do mesmo deck.

O objetivo é comparar essas leituras e estudar a divergência entre elas.

## 10. Representações de entrada

Cada deck será representado de duas formas principais:

```text
BC = Bag of Cards
DF = Deck Features
```

Essas representações são necessárias para que os modelos possam ser treinados, mas elas não são o objetivo final do projeto.

A comparação entre **BC** e **DF** é uma comparação instrumental: ela ajuda a entender se a percepção comunitária (`y1`) é melhor capturada pela identidade exata das cartas ou por propriedades agregadas do deck.

A comparação mais importante ocorre na §13.7: depois de treinar os modelos individuais (10 a 14) em `y1`, as predições out-of-fold de cada modelo são comparadas descritivamente com `y2` (calculadora), sem retreino. É nessa comparação que o projeto identifica quais modelos convergem para a lógica da calculadora e quais capturam particularidades da percepção comunitária.

Em outras palavras:

* **BC** e **DF** são formas de representar o deck;
* **y1** e **y2** são duas percepções de poder;
* o núcleo do projeto é entender o desalinhamento entre **y1** e **y2**, usando os modelos treinados em `y1` como sondas comparáveis a `y2`.

### 10.1 Bag of Cards

Na abordagem **Bag of Cards**, cada deck é representado pela identidade das cartas presentes.

Cada carta distinta no dataset vira uma feature. O valor da feature é a quantidade daquela carta no deck.

Como Commander é majoritariamente singleton:

* cartas não-básicas tendem a aparecer como 0 ou 1;
* basic lands podem aparecer com valores maiores.

Exemplo conceitual:

```text
Sol Ring = 1
Command Tower = 1
Island = 8
Forest = 5
Cyclonic Rift = 0
Demonic Tutor = 1
```

Essa abordagem captura diretamente:

* staples;
* cartas específicas de alto impacto;
* cartas de combo;
* cartas caras;
* cartas populares;
* pacotes recorrentes de construção de deck.

Ela ajuda a responder:

> A divergência entre percepção comunitária e calculadora está associada à presença de cartas específicas?

**Variante TF-IDF**: além da contagem bruta de cartas, será testada uma representação Bag of Cards transformada por TF-IDF (Term Frequency-Inverse Document Frequency). Como Commander é majoritariamente singleton, o TF tende ao binário; a contribuição relevante do TF-IDF vem do IDF, que pondera cartas raras (presentes em poucos decks) com mais peso do que staples ubíquos (Sol Ring, Command Tower etc.). Essa variante será avaliada como hiperparâmetro de pipeline para algoritmos que se beneficiam de features ponderadas (ex: LinearSVC), e descartada para algoritmos cuja suposição é incompatível (ex: `MultinomialNB`, que assume contagens inteiras).

### 10.2 Deck Features

Na abordagem **Deck Features**, cada deck é representado por estatísticas agregadas extraídas do Archidekt.

O modelo não vê diretamente a identidade de cada carta. Ele vê propriedades resumidas do deck, como:

* curva de mana;
* número de lands;
* número de criaturas;
* categorias funcionais;
* número de Game Changers;
* número de tutores;
* número de combos;
* EDHREC rank médio;
* salt score médio;
* preço médio;
* raridade;
* keywords;
* layout/multiface.

Ela ajuda a responder:

> A divergência entre percepção comunitária e calculadora está associada a propriedades estruturais do deck?

## 11. Features de Deck Features

Todas as features abaixo devem ser extraídas ou derivadas diretamente do raw JSON do Archidekt. Não entram features que dependam de inferência incerta, modelos auxiliares ou regras frágeis de texto.

### 11.1 Núcleo principal

#### A. Estrutura básica

```text
unique_card_count
non_commander_card_count
commander_card_count
has_companion
```

#### B. Cores

```text
deck_color_count
has_W
has_U
has_B
has_R
has_G
```

#### C. Mana base

```text
land_count
nonland_count
basic_land_count
nonbasic_land_count
land_mana_production_W
land_mana_production_U
land_mana_production_B
land_mana_production_R
land_mana_production_G
land_mana_production_C
lands_that_produce_multiple_colors_count
lands_that_produce_colorless_count
```

#### D. Curva de mana

```text
cmc_mean
cmc_median
cmc_std
cmc_min
cmc_max
nonland_cmc_mean
nonland_cmc_median
nonland_cmc_std
cmc_0_count
cmc_1_count
cmc_2_count
cmc_3_count
cmc_4_count
cmc_5_count
cmc_6_plus_count
```

**Observação (decisão de implementação, 2026-05-13):** o CMC usado para calcular todas as features desta seção vem **estritamente de `card.oracleCard.cmc`** (canônico do Archidekt/Scryfall). O Archidekt permite que o usuário sobrescreva o CMC de uma carta por deck via o campo `customCmc` da linha do deck — auditoria mostrou que 2.421 decks (18,7%) usam esse override em pelo menos uma carta, totalizando 10.758 linhas com valores arbitrários (alguns legítimos, como interpretações de X-spells; outros refletindo preferência subjetiva do construtor). Pela mesma razão de §11.1.F (não deixar entrada livre do usuário poluir features estruturais), o pipeline ignora `customCmc` e usa só o oracle canônico. O campo `custom_cmc` continua preservado em cada linha de `mainboard` em `decks.jsonl` para auditoria, mas não vira feature de modelo.

**Observação (poda, 2026-05-13):** `cmc_min` e `cmc_max` foram removidos por baixo sinal — `cmc_min` é 0 em ~todo deck por causa dos basics, e `cmc_max` reflete uma única carta atípica em vez da forma da curva. Os buckets `cmc_0_count` … `cmc_6_plus_count` já capturam os extremos com mais utilidade.

#### E. Tipos de carta

```text
creature_count
instant_count
sorcery_count
artifact_count
enchantment_count
planeswalker_count
land_count
noncreature_spell_count
permanent_count
nonland_permanent_count
```

**Observação (correção de bug, 2026-05-13):** `permanent_count` foi **removido**. A definição original na implementação excluía terrenos da contagem (`not is_land`), produzindo o mesmo valor que `nonland_permanent_count`. Em MTG, terrenos *são* permanentes — a definição correta seria "tudo que não é instant nem sorcery". Em vez de corrigir, a feature foi removida por redundância parcial com as outras contagens de tipo já presentes (terrenos têm `land_count`, não-terrenos permanentes têm `nonland_permanent_count`).

#### F. Categorias do Archidekt

```text
category_ramp_total
category_draw_total
category_removal_count
category_mass_removal_count
category_protection_count
category_recursion_count
category_finisher_count
category_tokens_count
category_blink_count
category_copy_count
category_untap_count
category_counters_count
category_evasion_count
category_lifegain_count
category_pump_count
category_auras_equipment_count
```

**Observação (decisão de implementação, 2026-05-13):** as features desta seção foram **removidas** do pipeline após auditoria empírica sobre 12.950 decks.

As categorias por carta no Archidekt são strings livres definidas pelo próprio usuário. Diferente de campos canônicos do `oracleCard` (tipos, cores, CMC, salt, EDHREC rank, flags de bracket), elas não passam por nenhuma normalização do site. Isso gera dois problemas que invalidam a feature como sinal:

- **Cobertura zero em ~23% da base**: 2.949 dos 12.950 decks (22,8%) não usam nenhum nome de categoria que bata com o vocabulário funcional padrão (Ramp / Draw / Removal / …). 16,9% dos decks usam apenas buckets de tipo de carta ("Creature", "Artifact", "Land"). Exemplo concreto: o deck `archidekt.com/decks/315586` ("PwLvL 8.0 Braids") tem rampa, draw e wipes, mas o usuário organizou tudo dentro de "Artifact" e "Creature" — todas as `category_*` saíam zero apesar das cartas existirem.

- **Confound de estilo de catalogação**: mesmo entre decks "bem categorizados", convenções variam (`Card Draw` vs `Draw` vs `Advantage` vs `cardadvantage`). Expandir aliases é Sísifo — a auditoria encontrou pelo menos `interaction` (13k usos), `cardadvantage` (12.6k), `burn`, `drain`, `mill`, `stax`, `discard`, `landfall` como funcionais não cobertos. Manter a feature treina o modelo a aprender **estilo do criador**, não composição do deck.

Como as outras seções (D curva, E tipos, G flags de bracket, H combos, K keywords) já capturam composição estrutural do oracle canônico, a perda de informação é limitada. O campo `categories` continua preservado em cada linha de `mainboard` em `decks.jsonl` para análises descritivas que queiram olhar convenções de catalogação diretamente — só não vira feature de modelo.

#### G. Flags específicas de bracket

```text
game_changer_count
extra_turns_count
tutor_count
mass_land_denial_count
two_card_combo_singleton_count
```

#### H. Combos

```text
cards_with_atomic_combos_count
cards_with_potential_combos_count
atomic_combo_refs_total
potential_combo_refs_total
unique_atomic_combo_refs_count
unique_potential_combo_refs_count
two_card_combo_ids_total
unique_two_card_combo_ids_count
```

#### I. Popularidade, preço e salt

```text
edhrec_rank_mean
edhrec_rank_median
edhrec_rank_std
edhrec_rank_min
salt_mean
salt_median
salt_std
salt_max
high_salt_card_count
price_total
price_mean
price_median
price_std
price_max
```

Para preço, a ideia é calcular um preço médio por carta usando os preços disponíveis no raw do Archidekt, preferencialmente considerando preços de papel e não-foil.

**Observação (poda, 2026-05-13):** `price_max`, `edhrec_rank_min`, `salt_max` e `high_salt_card_count` foram removidos. Todos refletem uma única carta dominante: `price_max` é o terreno dual/staple mais caro; `edhrec_rank_min` é praticamente sempre top-100 (Sol Ring, Command Tower); `salt_max` é tipicamente uma única carta salgada. Eles não caracterizam o perfil do deck — só sinalizam a presença de uma carta no extremo. `high_salt_card_count` usava um threshold arbitrário (`salt >= 1.0`); `salt_mean`/`salt_median`/`salt_std` já descrevem o perfil de salt com mais robustez. As features mantidas (`price_total`, `price_mean`, `price_median`, `price_std`, `edhrec_rank_mean`/`median`/`std`, `salt_mean`/`median`/`std`) cobrem popularidade, preço e salt como propriedades do deck inteiro.

#### J. Raridade

```text
common_count
uncommon_count
rare_count
mythic_count
rare_mythic_count
```

**Observação (poda, 2026-05-13):** `rare_mythic_count` foi removido — é literalmente `rare_count + mythic_count`. Combinações lineares de outras features já existentes são redundantes e podem prejudicar modelos lineares.

### 11.2 Features secundárias

#### K. Keywords

```text
keyword_total_count
distinct_keyword_count
keyword_count_mean
keyword_count_std
flying_count
trample_count
haste_count
hexproof_count
ward_count
indestructible_count
lifelink_count
menace_count
vigilance_count
deathtouch_count
flash_count
equip_count
annihilator_count
cascade_count
protection_keyword_count
```

**Observação (poda, 2026-05-13):** `keyword_count_mean` e `keyword_count_std` foram removidos. O campo `oracleCard.keywords` do Archidekt mistura keywords evergreen (Flying, Trample, …) com keywords flavor/set-específicas ("Allons-y!", "Animal May-Ham", "Aberrant Tinkering" — 583 distintas na base). Médias e desvios sobre essa cardinalidade ruidosa não capturam densidade real de mecânicas evergreen; as contagens absolutas por keyword evergreen (`flying_count`, `trample_count`, …) e `keyword_total_count`/`distinct_keyword_count` permanecem.

#### L. Supertipos e subtipos

```text
legendary_count
snow_count
distinct_subtype_count
most_common_subtype_count
equipment_subtype_count
aura_subtype_count
vehicle_subtype_count
```

#### M. Multiface e layout

```text
multiface_card_count
layout_normal_count
layout_transform_count
layout_modal_dfc_count
layout_split_count
layout_adventure_count
cards_with_faces_count
total_face_count
max_faces_on_card
```

## 12. Tratamento de cartas com duas ou mais faces

As duas representações devem lidar corretamente com cartas multiface.

Na abordagem **Bag of Cards**, uma carta multiface conta como uma única carta. Ela não deve ser duplicada por número de faces.

Na abordagem **Deck Features**, a carta também conta como um único slot do deck, mas suas faces podem contribuir para features secundárias, como:

* `multiface_card_count`;
* `layout_modal_dfc_count`;
* `cards_with_faces_count`;
* `total_face_count`;
* `max_faces_on_card`.

A regra conceitual é:

> O slot do deck é a unidade de contagem; as faces são metadados auxiliares.

Isso evita o erro de transformar uma carta de duas faces em duas cartas diferentes dentro do deck.

## 13. Estratégia experimental

A estratégia experimental deve sustentar o projeto inteiro e cumprir as exigências do trabalho prático: comparação de algoritmos, validação robusta, ajuste de hiperparâmetros, prevenção de data leakage, interpretação, análise crítica e reprodutibilidade.

O projeto será formulado como uma tarefa supervisionada de **classificação multiclasse**, com classes 2, 3 e 4. A pergunta científica principal continua sendo a divergência entre percepções de poder, mas essa pergunta será estudada por meio de modelos preditivos treinados sobre duas famílias de labels.

A estratégia experimental tem seis camadas:

1. análise exploratória e preparação dos dados;
2. spot-checking N=5 sobre 7 algoritmos candidatos (todos viáveis em BC e DF) e seleção dos top-5 por representação;
3. predição de `y1` com `|A_uniao| × 2` modelos (cada algoritmo da união treinado em ambas as representações, totalizando 10 a 14) via nested CV com grids ≤192 configs, e comparação entre representações;
4. votação majoritária (hard voting) de subconjuntos dos modelos individuais a partir das predições OOF, sem retreino;
5. comparação descritiva das predições dos modelos individuais (e dos ensembles de votação) contra `y2` (calculadora);
6. (opcional) stacking dos modelos individuais para prever `y1`.

A quarta camada é a que conecta a modelagem à pergunta central do projeto: ela revela quais modelos, treinados apenas em `y1`, terminam reproduzindo o comportamento da calculadora — e quais divergem dela.

As camadas 2 e 3 garantem que os modelos existem, que conseguem aprender `y1` e que as representações **BC** e **DF** carregam sinal.

### 13.1 Análise exploratória dos dados

Antes do treinamento, o projeto deve realizar uma análise exploratória dos dados para entender a base coletada, identificar problemas e orientar o pré-processamento.

A EDA deve incluir, no mínimo:

```text
distribuição do bracket do Archidekt, y1
distribuição do bracket da calculadora, y2
distribuição de delta = y2 - y1
distribuição de abs_delta
quantidade de decks por bracket
balanceamento das classes
número de decks por comandante
distribuição de cores
distribuição de categorias do Archidekt
distribuição de número de lands
curva de mana média
valores ausentes por atributo
outliers de preço, salt e EDHREC rank
quantidade de decks removidos por cada filtro
```

A EDA também deve indicar se será necessário aplicar normalização, imputação, tratamento de outliers, remoção de atributos problemáticos ou balanceamento de classes.

### 13.2 Pré-processamento

O pré-processamento deve ser feito dentro do pipeline de validação, sem usar informação dos folds de teste.

Para **Bag of Cards**, o pré-processamento deve considerar:

```text
construção de matriz esparsa
representação por contagem de cartas
basic lands representadas por quantidade
cartas não-básicas geralmente representadas por 0 ou 1
remoção opcional de cartas extremamente raras, se necessário
garantia de que apenas mainboard entra na matriz
```

Para **Deck Features**, o pré-processamento deve considerar:

```text
tratamento de valores ausentes
padronização para algoritmos sensíveis à escala
codificação de atributos booleanos
tratamento ou winsorização de outliers de preço, se necessário
imputação de EDHREC rank, salt e preço, se necessário
remoção de atributos constantes
remoção ou análise de atributos altamente redundantes, se necessário
```

Regras importantes contra vazamento de dados:

```text
não usar y1 como feature para prever y2
não usar y2 como feature para prever y1
não usar delta ou abs_delta como feature
não usar resultados da calculadora dentro de X
calcular imputação, escala, seleção de atributos e qualquer transformação apenas no treino de cada fold
usar os mesmos folds para comparar algoritmos e representações
```

### 13.3 Algoritmos e spot-checking

Será definido um conjunto inicial diversificado de algoritmos candidatos, respeitando a recomendação do trabalho de testar ao menos 5 algoritmos com diferentes vieses indutivos. O projeto considera **7 algoritmos candidatos**, todos viáveis tanto em BC quanto em DF:

```text
A_candidatos = {
  Decision Tree,                # árvore
  Random Forest,                # bagging
  Gradient Boosting,            # boosting
  Naive Bayes,                  # probabilístico (MultinomialNB em BC, GaussianNB em DF)
  Logistic Regression,          # linear paramétrico
  LinearSVC,                    # margem linear
  KNN                           # distância
}
```

Kernels não-lineares de SVM (RBF, polinomial) foram **excluídos** do conjunto: seu custo computacional em BC esparso de alta dimensão (~15k features × 12k decks) é proibitivo, o que quebraria a simetria de aplicar exatamente o mesmo conjunto de algoritmos às duas representações. A regra do projeto, fixada com a professora em 2026-05-19, é manter no pool só algoritmos que rodam em ambas as representações. Mantemos margem linear via `LinearSVC` e não-linearidade via `GradientBoosting` e `KNN`.

A primeira etapa será tratada como **spot-checking**: rodar todos os 7 algoritmos × 2 representações = **14 combinações** com defaults em hold-out 80/20. Cada combinação é avaliada com **N=5 repetições** usando seeds `{1, 2, 3, 4, 5}` para gerar 5 hold-outs estratificados distintos. Reportamos média e desvio padrão de macro-F1 (e demais métricas) por combinação.

**Resultado do spot-checking**: selecionar os **top-5 algoritmos por representação** (BC e DF independentes) por macro-F1 média. A união `A_uniao = A_DF ∪ A_BC` (5 a 7 algoritmos distintos) define o conjunto de algoritmos que vai para a Fase E. Em Fase E, **cada algoritmo da união é treinado em ambas as representações** — não apenas naquela em que entrou no top-5. Isso gera `|A_uniao| × 2` modelos (10 a 14) e mantém a comparação BC vs DF justa para cada algoritmo selecionado.

A seleção é primariamente por desempenho médio; desvio padrão (estabilidade) e diversidade de vieses indutivos servem de desempate quando o ranking concentrar muitos algoritmos da mesma família (ex: três ensembles no topo). A decisão é documentada no relatório.

### 13.4 Nested cross-validation

Todos os algoritmos devem usar os mesmos folds de **nested cross-validation**.

A avaliação será organizada em dois níveis:

```text
outer folds = avaliação final de generalização
inner folds = seleção de hiperparâmetros
```

O loop externo estima o desempenho final dos modelos. O loop interno escolhe os melhores hiperparâmetros para cada algoritmo, representação e label.

Todos os algoritmos devem usar exatamente as mesmas divisões externas e internas em cada configuração experimental. Isso garante comparação justa entre algoritmos, representações e famílias de label.

Regras:

```text
usar os mesmos outer folds para todos os algoritmos
usar os mesmos inner folds dentro de cada outer fold para todos os algoritmos
fixar random seeds
salvar os índices dos folds
não ajustar hiperparâmetros usando dados do outer test fold
reportar média e desvio padrão das métricas nos outer folds
```

Sempre que possível, os folds devem ser estratificados por classe.

Como controle adicional, deve-se rodar uma análise auxiliar com **GroupKFold por comandante**, garantindo que decks com o mesmo comandante (ou combinação de comandantes em decks partner/background) não apareçam simultaneamente no treino e no teste. A motivação é que decks que compartilham comandante também compartilham a própria carta do comandante, identidade de cores e staples canônicos do arquétipo; sem o controle por grupo, o modelo pode aprender "padrões de comandante" em vez de padrões gerais de poder, superestimando sua capacidade de generalizar para comandantes novos.

A estimativa com `StratifiedKFold` representa o cenário **otimista** (comandantes do treino podem aparecer no teste); a estimativa com `GroupKFold` representa o cenário **conservador** (comandantes do treino são disjuntos dos do teste). O **gap entre as duas** é em si um resultado: gap pequeno indica padrões gerais; gap grande indica dependência de comandante específico.

`GroupKFold` não garante estratificação perfeita por classe, por isso permanece como **análise auxiliar** (relatada para mostrar robustez), não como a métrica principal de seleção.

### 13.5 Predição de `y1` (percepção comunitária)

A Fase D entrega duas listas `A_DF` e `A_BC` (top-5 de cada representação). A união `A_uniao = A_DF ∪ A_BC` é o conjunto de algoritmos da Fase E. Para cada par `(alg, est)` com `alg ∈ A_uniao` e `est ∈ {BC, DF}`, treina-se um modelo prevendo **somente** `y1`:

```text
m = alg(est(X), y1)   para todo (alg, est) ∈ A_uniao × {BC, DF}
```

Total: `|A_uniao| × 2` modelos (10 a 14 dependendo do tamanho da união). Treinamos cada algoritmo selecionado em ambas as representações para preservar a comparação BC vs DF necessária à Fase F.

Para conter o custo computacional, cada algoritmo recebe um grid de hiperparâmetros com no máximo **192 configurações** (guarda-corpo de ordem de grandeza atualizado em 2026-05-20). Random Forest, por exemplo, sai de 864 configurações no desenho original para 192.

A calculadora (`y2`) **não é alvo de modelo**. Treinar para prever a saída de outra ferramenta determinística não responde à pergunta central. `y2` aparece como benchmark de comparação em §13.7.

Essa etapa mede se a percepção comunitária pode ser aprendida a partir dos dados observáveis do deck e qual representação carrega mais sinal preditivo.

### 13.5.1 Ensembles por votação (hard voting, sem retreino)

A pedido da professora (2026-05-19), avaliamos seis ensembles construídos por **votação majoritária** das predições out-of-fold dos modelos da §13.5. Como todas as predições OOF compartilham o mesmo conjunto de folds e seeds, a votação é exata por linha e por fold — não há novo treinamento.

```text
voting_top3_BC        top-3 modelos BC por macro-F1 média da §13.5
voting_top5_BC        top-5 modelos BC
voting_top3_DF        top-3 modelos DF
voting_top5_DF        top-5 modelos DF
voting_top3_BC_DF     top-3 BC + top-3 DF (6 modelos)
voting_all            todos os modelos individuais da §13.5 (10 a 14)
```

Para cada ensemble e cada outer fold, agregamos as predições dos membros, computamos a moda por linha (empates resolvidos pela classe com maior macro-F1 médio entre os membros que a previram), e reportamos macro-F1, accuracy, precision_macro, recall_macro e a matriz de confusão. Reportamos média e desvio padrão sobre os 15 outer folds, do mesmo jeito que para os modelos individuais.

As predições OOF dos 6 ensembles também são preservadas e entram no leque de comparações da §13.7 (vs `y2`) e no relatório da §17 (interpretação).

### 13.6 Comparação entre representações

Para `y1`, compara-se:

```text
BC -> y1
DF -> y1
```

Essa comparação ajuda a entender se a percepção comunitária é melhor explicada por:

* identidade específica das cartas (BC);
* propriedades agregadas do deck (DF).

Se **Bag of Cards** performar melhor, cartas específicas carregam mais sinal sobre o bracket comunitário do que estatísticas agregadas.

Se **Deck Features** performar perto ou melhor, a percepção comunitária é capturável por propriedades estruturais — o que pode aproximá-la da lógica que a calculadora usa.

Essa etapa é instrumental: alimenta a seleção dos dois melhores modelos (um por representação) que receberão interpretabilidade em §17.

### 13.7 Comparação das predições dos modelos com a calculadora

Esta é a camada central que conecta a modelagem à pergunta de pesquisa. Não envolve novo treinamento: reutiliza as **predições out-of-fold** já produzidas em §13.5 (modelos individuais) e §13.5.1 (ensembles de votação) e as compara contra `y2`.

Para cada modelo individual (10 a 14 dependendo de `|A_uniao|`) e cada um dos 6 ensembles de votação, avaliados em todos os folds externos:

```text
ŷ1 = predição out-of-fold do modelo (alvo de treino: y1)
y2 = bracket da calculadora (não usado no treino)
```

Métricas computadas para cada modelo:

```text
concordância exata entre ŷ1 e y2
concordância dentro de ±1
macro-F1 tratando y2 como rótulo de referência
matriz de confusão ŷ1 × y2
|Δ| médio entre ŷ1 e y2
distribuição de ŷ1 - y2
```

Interpretação:

* modelos cujas predições têm **alta concordância com y2** capturam padrões estruturais similares aos que a calculadora usa, mesmo sem terem sido treinados nela — sugerem que parte do sinal comunitário é "explicável" pelos mesmos critérios objetivos da calculadora;
* modelos com **alta performance contra y1 mas baixa concordância com y2** estão aprendendo particularidades da percepção comunitária que a calculadora não capta;
* a comparação BC vs DF informa quais sinais (cartas específicas vs propriedades agregadas) cada modelo aproveita para "imitar" a calculadora indiretamente.

Essa análise é **descritiva**: não há retreino, não há novos folds, não há novo target de treinamento. O custo computacional é desprezível.

### 13.8 Seleção final dos melhores modelos

A seleção usa a métrica principal (macro-F1, ver §15) calculada nos outer folds da nested CV. Para cada representação:

```text
melhor modelo BC = argmax_{alg ∈ A_uniao} macro_F1(alg, BC, y1)
melhor modelo DF = argmax_{alg ∈ A_uniao} macro_F1(alg, DF, y1)
```

Esses dois modelos recebem interpretabilidade aprofundada (§17). Em caso de empate por macro-F1, o desempate considera desvio padrão (estabilidade) e custo de interpretação. Os ensembles de votação (§13.5.1) também são ranqueados e comparados, mas a interpretabilidade segue sendo feita sobre dois modelos individuais por simplicidade.

O artigo deve reportar:

```text
média e desvio padrão das métricas por (algoritmo, representação) nos outer folds
métricas complementares
matrizes de confusão (por fold e agregada) contra y1
melhores hiperparâmetros selecionados por fold
comparação entre BC e DF para y1
métricas dos 6 ensembles de votação (§13.5.1) lado a lado com os 10 individuais
comparação descritiva entre as predições dos modelos e y2 (§13.7)
```

### 13.9 Stacking (opcional, se houver tempo até a entrega)

Caso o cronograma permita, treinar um **meta-modelo** que combina as predições dos modelos individuais da §13.5:

```text
base learners: |A_uniao| × 2 modelos individuais (algoritmos da união × {BC, DF}), todos prevendo y1
features do meta: predições out-of-fold de cada base learner
meta-learner: LogisticRegression
meta-target: y1
folds: os mesmos outer folds da §13.5 (sem leakage)
```

Comparações de interesse:

* macro-F1 do stacking vs macro-F1 do melhor modelo individual (ganho do ensemble);
* concordância do stacking com `y2` vs concordância dos modelos individuais (o stacking se aproxima mais ou menos da calculadora?).

Critério de inclusão no artigo final: ganho consistente em macro-F1 vs o melhor modelo individual, ou insight relevante na comparação com `y2`.

## 14. Análise direta da divergência

Além de treinar modelos, o projeto deve analisar diretamente a diferença entre os dois rótulos:

```text
delta = y2 - y1
```

Interpretação:

```text
delta = 0  -> Archidekt e calculadora concordam
delta > 0  -> calculadora classifica acima do Archidekt
delta < 0  -> calculadora classifica abaixo do Archidekt
```

Também será analisado:

```text
abs_delta = |y2 - y1|
```

Esse valor representa o tamanho da discordância.

Essa análise é central para o projeto, pois conecta diretamente o experimento à motivação inicial: medir quão longe a percepção comunitária está da avaliação automatizada.

O projeto deve observar:

* frequência de concordância;
* frequência de discordância por 1 bracket;
* frequência de discordância por 2 ou mais brackets;
* direção da discordância;
* características dos decks com `delta > 0`;
* características dos decks com `delta < 0`;
* características dos decks com `abs_delta` alto.

## 15. Métricas

As métricas de desempenho dos modelos devem seguir as métricas vistas na disciplina para problemas de classificação.

Como a tarefa preditiva principal é multiclasse, com classes 2, 3 e 4, a avaliação dos modelos deve usar métricas derivadas da matriz de confusão e suas generalizações para multiclasse.

### 15.1 Métrica principal de seleção

A métrica principal de seleção de modelos será:

```text
macro-F1
```

A escolha de macro-F1 é adequada porque cada classe recebe o mesmo peso na média. Isso é importante caso os brackets estejam desbalanceados.

A acurácia será reportada, mas não será usada como critério principal, pois pode mascarar desempenho ruim em classes minoritárias.

### 15.2 Métricas complementares de classificação

As métricas complementares serão:

```text
accuracy
precision_macro
recall_macro
f1_macro
precision_micro
recall_micro
f1_micro
confusion_matrix
```

A matriz de confusão será essencial para analisar quais brackets são confundidos entre si.

Se o desbalanceamento entre classes for relevante, a discussão deve enfatizar precision, recall e F1 macro.

Métricas como AUC-ROC e AUPRC não serão usadas como métricas principais, pois o problema central é multiclasse. Elas podem ser consideradas apenas se houver uma análise binária auxiliar, como “concorda vs discorda” ou “delta positivo vs não positivo”.

### 15.3 Medidas descritivas para divergência entre labels

Além das métricas de desempenho dos modelos, o projeto usará medidas descritivas para estudar a divergência entre as duas famílias de rótulo.

Essas medidas não substituem as métricas de classificação. Elas servem para responder à pergunta central do projeto.

```text
exact_agreement
agreement_within_one_bracket
delta_distribution
abs_delta_distribution
mean_abs_delta
median_abs_delta
y1_by_y2_matrix
proportion_y2_greater_than_y1
proportion_y2_less_than_y1
```

Onde:

```text
delta = y2 - y1
abs_delta = |y2 - y1|
```

Essas medidas descrevem a distância entre a percepção comunitária e a avaliação automatizada.

## 16. Interpretação esperada

O foco interpretativo não é declarar um vencedor entre Archidekt e calculadora.

O foco é explicar o desalinhamento.

Possíveis interpretações:

* Se a calculadora frequentemente classifica acima do Archidekt, usuários podem estar subestimando decks com sinais objetivos de força.
* Se a calculadora classifica abaixo do Archidekt, usuários podem estar percebendo força em sinergias, reputações ou contextos que a calculadora não captura.
* Se decks com muitos combos têm `delta` alto, a calculadora pode ser mais sensível a combos do que a percepção comunitária.
* Se decks com alto preço, baixo CMC ou muitos Game Changers têm `delta` alto, pode haver diferença entre otimização estrutural e autoavaliação humana.
* Se as predições dos modelos (treinados em `y1`) têm **baixa concordância com `y2`**, isso sugere que a percepção comunitária aprendível pelos dados estruturais está descolada da lógica da calculadora.
* Se as predições têm **alta concordância com `y2`**, parte do sinal comunitário capturado pelos modelos coincide com critérios objetivos que a calculadora também usa — apontando para uma estrutura compartilhada apesar da fonte distinta.

## 17. Interpretação dos modelos

O projeto inclui interpretação dos modelos, como exigido no trabalho prático. A interpretação é feita sobre **dois modelos**:

* o melhor modelo de **Bag of Cards** prevendo `y1`;
* o melhor modelo de **Deck Features** prevendo `y1`.

O enunciado pede interpretação de **um** modelo; analisamos dois (um por representação) para responder simetricamente "**quais cartas** explicam o bracket comunitário?" e "**quais propriedades estruturais** explicam o bracket comunitário?".

Para **Deck Features**, analisa-se:

```text
importância de atributos em árvores ou ensembles
coeficientes de modelos lineares, quando aplicável
permutation importance
features mais associadas a cada bracket previsto
features associadas a divergência entre ŷ1 do modelo e y2 (calculadora)
```

Para **Bag of Cards**, analisa-se:

```text
cartas com maior peso/importância
cartas associadas a brackets mais altos vs mais baixos
cartas associadas a divergência entre ŷ1 do modelo e y2 (calculadora)
```

A interpretação é apresentada como hipótese analítica, não como prova causal.

## 18. Plano de reporte dos resultados

O artigo deve reportar os resultados de forma clara e reprodutível.

Devem ser incluídos:

```text
tabelas com média e desvio padrão das métricas nos outer folds (10 a 14 modelos individuais, conforme |A_uniao|)
tabela do spot-checking (7 algoritmos candidatos, N=5 repetições, média ± dp) com justificativa do top-5 por representação e da união
comparação entre algoritmos para y1
comparação entre BC e DF para y1
matrizes de confusão contra y1
métricas dos 6 ensembles de votação (top-3/top-5 BC, top-3/top-5 DF, top-3 BC + top-3 DF, voting_all)
ganho/perda dos ensembles vs melhores modelos individuais por representação
análise direta de divergência entre y1 e y2 (descritiva, §14)
comparação descritiva entre as predições dos modelos (individuais + ensembles) e y2 (§13.7)
gráficos de distribuição de delta e abs_delta
análise dos dois melhores modelos (BC + DF)
interpretação das features e cartas mais relevantes
(opcional) resultados do stacking, se incluído
```

A discussão deve conectar os resultados à pergunta central: a distância entre percepção comunitária e avaliação automatizada.

## 19. Reprodutibilidade

O projeto deve registrar todos os elementos necessários para reprodução dos resultados.

Devem ser preservados:

```text
código usado nos experimentos
configurações de coleta
filtros aplicados aos decks
versão ou data da coleta
seeds aleatórias
índices dos outer folds
índices dos inner folds
hiperparâmetros testados
melhores hiperparâmetros selecionados por fold
métricas por fold
predições por fold
```

O artigo deve descrever a metodologia com detalhes suficientes para que outra pessoa possa reproduzir o fluxo experimental.

## 20. Alinhamento com o trabalho prático

O projeto está alinhado às diretrizes do trabalho prático porque:

* define uma tarefa preditiva supervisionada de classificação;
* usa um conjunto de dados de interesse próprio;
* inclui coleta e descrição dos dados;
* prevê análise exploratória dos dados;
* prevê pré-processamento adequado para cada representação;
* compara ao menos 5 algoritmos com diferentes vieses indutivos;
* usa spot-checking N=5 (seeds 1..5, média ± dp) como etapa inicial de seleção de algoritmos;
* usa nested cross-validation para seleção de hiperparâmetros e estimativa final de desempenho, com grids limitados a ≤192 configs por algoritmo para evitar explosão combinatorial;
* reporta média e desvio padrão das métricas nos outer folds, tanto para os modelos individuais (10 a 14) quanto para os 6 ensembles de votação;
* usa as mesmas divisões internas e externas para comparar algoritmos e ensembles de forma justa;
* define seeds e procedimentos reprodutíveis;
* inclui interpretação de modelos para ambas as representações (melhor BC e melhor DF), excedendo o requisito de "um modelo" do enunciado;
* inclui ensembles por votação majoritária a partir das predições OOF, sem retreino;
* discute limitações e riscos de vazamento ou viés.

## 21. Limitações conceituais

O projeto possui limitações importantes:

* não existe ground truth universal de força;
* bracket envolve percepção, intenção e contexto social;
* Archidekt pode refletir autoavaliação subjetiva;
* calculadoras podem refletir regras rígidas e incompletas;
* decks públicos com 1000+ views não representam todos os decks Commander;
* o modelo aprende padrões de rótulo, não força verdadeira;
* comandantes e arquétipos populares podem influenciar resultados;
* o filtro de views pode introduzir viés de popularidade;
* os resultados não equivalem a win rate;
* os resultados não medem diversão real de uma mesa.

## 22. Formulação final

A formulação atual do projeto é:

> Este projeto estuda a divergência entre duas percepções de poder em decks Commander: o bracket atribuído no Archidekt (`y1`, percepção comunitária) e o bracket calculado por uma ferramenta externa (`y2`, avaliação automatizada). Usando dados extraídos do Archidekt, o projeto representa decks de duas formas — Bag of Cards e Deck Features. Após um spot-checking de 7 algoritmos candidatos (todos viáveis em BC e DF) com N=5 repetições (seeds 1..5) e média ± desvio padrão, selecionamos o top-5 de cada representação. A união `A_uniao = A_DF ∪ A_BC` (5 a 7 algoritmos) alimenta a nested CV: cada algoritmo da união é treinado nas duas representações, gerando **10 a 14 modelos individuais treinados apenas para prever `y1`**, com grids ≤192 configurações por algoritmo. A partir das predições out-of-fold construímos seis ensembles por votação majoritária (top-3/top-5 por representação, top-3 BC + top-3 DF e `voting_all` com todos os individuais) sem retreino. As predições dos modelos individuais e dos ensembles são comparadas descritivamente com `y2`, para identificar quais convergem para a lógica da calculadora e quais capturam particularidades da percepção comunitária. O objetivo não é descobrir o bracket verdadeiro, nem treinar modelos que imitem a calculadora, mas medir e explicar o desalinhamento entre as duas leituras de poder.
