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

Já a calculadora automatizada tende a ser determinística: se receber exatamente o mesmo deck e os mesmos parâmetros, deve retornar o mesmo label. Isso não significa que ela está correta, apenas que sua percepção é estável e baseada em regras ou heurísticas fixas.

Essa diferença é central para o projeto: o Archidekt representa uma percepção humana/comunitária potencialmente ruidosa; a calculadora representa uma percepção automatizada e consistente, mas também limitada.

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

   * bracket do Archidekt;
   * bracket calculado por ferramenta externa.
4. Representar cada deck de duas formas:

   * **Bag of Cards**;
   * **Deck Features**.
5. Treinar modelos de aprendizado de máquina para cada combinação de representação e fonte de rótulo.
6. Avaliar o quanto cada rótulo pode ser aprendido a partir dos dados observáveis do deck.
7. Estudar a transferência entre famílias de rótulo.
8. Analisar diretamente a divergência entre os dois brackets.
9. Interpretar quais características estão associadas a concordância e discordância.

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

A comparação entre **BC** e **DF** é uma comparação instrumental: ela ajuda a entender se os modelos conseguem aprender melhor a partir da identidade exata das cartas ou a partir de propriedades agregadas do deck.

A comparação mais importante ocorre depois: quando um modelo é treinado em uma família de rótulo e avaliado contra a outra. É nessa transferência entre famílias de labels que o projeto mede a distância entre duas percepções de poder.

Em outras palavras:

* **BC** e **DF** são formas de representar o deck;
* **y1** e **y2** são duas percepções de poder;
* o núcleo do projeto é entender o desalinhamento entre **y1** e **y2**.

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

#### J. Raridade

```text
common_count
uncommon_count
rare_count
mythic_count
rare_mythic_count
```

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

A estratégia experimental tem quatro camadas:

1. análise exploratória e preparação dos dados;
2. predição interna de cada família de label;
3. comparação entre representações;
4. transferência entre famílias de label.

A quarta camada é a mais importante para a pergunta central do projeto.

As camadas 2 e 3 garantem que os modelos existem, que conseguem aprender padrões de cada rótulo e que as representações **BC** e **DF** são úteis. A camada de transferência é onde o projeto mede a distância entre a percepção comunitária e a avaliação automatizada.

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

Será definido um conjunto diversificado de algoritmos, respeitando a recomendação do trabalho de testar ao menos 5 algoritmos com diferentes vieses indutivos.

```text
A = {
  Decision Tree,
  Random Forest,
  Gradient Boosting,
  Naive Bayes,
  Logistic Regression,
  KNN,
  SVM
}
```

A primeira etapa será tratada como **spot-checking**: testar um conjunto diverso de algoritmos para identificar quais merecem análise mais aprofundada.

O conjunto deve incluir modelos com diferentes vieses indutivos:

* árvores;
* ensembles;
* modelos probabilísticos;
* modelos lineares;
* modelos baseados em distância;
* modelos de margem.

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

Sempre que possível, os folds devem ser estratificados por classe. Se for necessário controlar vazamento por comandante, deve-se considerar uma variação agrupada por comandante, garantindo que decks com o mesmo comandante não apareçam simultaneamente no treino e no teste externo.

### 13.5 Predição interna de cada família de label

Para cada algoritmo `alg` em `A`, para cada label `y` em `{y1, y2}`, e para cada representação `est` em `{BC, DF}`, treina-se um modelo:

```text
m = alg(est(X), y)
```

As combinações principais são:

```text
BC -> y1
DF -> y1
BC -> y2
DF -> y2
```

Essa etapa mede se cada percepção de bracket pode ser aprendida a partir dos dados observáveis do deck.

Ela é necessária para validar a viabilidade dos modelos, mas não é a pergunta principal.

### 13.6 Comparação entre representações

Para cada família de rótulo, o projeto compara:

```text
BC -> y
DF -> y
```

Essa comparação ajuda a entender se cada percepção de poder é melhor explicada por:

* identidade específica das cartas;
* propriedades agregadas do deck.

Se **Bag of Cards** performar melhor, isso sugere que cartas específicas carregam muito sinal.

Se **Deck Features** performar perto ou melhor, isso sugere que propriedades estruturais do deck explicam bem os brackets.

Essa etapa é útil, mas continua sendo instrumental. Ela não substitui a análise de divergência entre **y1** e **y2**.

### 13.7 Transferência entre famílias de label

Depois da avaliação interna, serão escolhidos 1 ou 2 algoritmos interessantes para estudar transferência entre rótulos.

As comparações são:

```text
treina em y1, avalia em y2
treina em y2, avalia em y1
```

Para cada representação:

```text
BC/y1 -> y2
DF/y1 -> y2
BC/y2 -> y1
DF/y2 -> y1
```

Essa é a camada central da estratégia experimental.

Ela testa se um modelo que aprendeu uma percepção consegue aproximar a outra. Se a transferência falha, isso indica desalinhamento entre percepção comunitária e avaliação automatizada. Se a transferência funciona, isso indica que as duas famílias compartilham uma estrutura comum de avaliação.

A assimetria também é importante:

* se modelos treinados em **y2** predizem mal **y1**, isso pode indicar que a percepção comunitária contém mais variação subjetiva;
* se modelos treinados em **y1** predizem mal **y2**, isso pode indicar que a calculadora segue uma lógica diferente da percepção média dos usuários;
* se uma direção funciona melhor que a outra, isso ajuda a caracterizar a distância entre as duas percepções.

### 13.8 Seleção final de modelos

A seleção do melhor modelo deve usar a métrica principal definida na seção de métricas, calculada nos outer folds da nested cross-validation.

O artigo deve reportar:

```text
média da métrica principal
desvio padrão da métrica principal
métricas complementares
matrizes de confusão agregadas ou por fold
melhores hiperparâmetros selecionados
comparação entre BC e DF
comparação entre y1 e y2
```

A escolha de 1 ou 2 modelos para análise de transferência e interpretação deve considerar desempenho, estabilidade e interpretabilidade.

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
* Se a transferência entre labels é fraca, as duas famílias de rótulo representam percepções distintas.
* Se a transferência é forte, elas compartilham uma estrutura comum de avaliação.

## 17. Interpretação dos modelos

O projeto deve incluir interpretação dos modelos, como exigido no trabalho prático.

A interpretação deve ser feita preferencialmente sobre os modelos escolhidos após a avaliação com nested cross-validation.

Para **Deck Features**, a interpretação pode analisar:

```text
importância de atributos em árvores ou ensembles
coeficientes de modelos lineares, quando aplicável
permutation importance
features associadas a y1
features associadas a y2
features associadas a erros de transferência
features associadas a delta positivo ou negativo
```

Para **Bag of Cards**, a interpretação pode analisar:

```text
cartas com maior peso/importância
cartas associadas a brackets mais altos
cartas associadas a divergência entre y1 e y2
pacotes de cartas recorrentes em erros de transferência
```

A interpretação deve ser apresentada como hipótese analítica, não como prova causal.

## 18. Plano de reporte dos resultados

O artigo deve reportar os resultados de forma clara e reprodutível.

Devem ser incluídos:

```text
tabelas com média e desvio padrão das métricas nos outer folds
comparação entre algoritmos
comparação entre BC e DF
comparação entre y1 e y2
matrizes de confusão
gráficos de distribuição de delta e abs_delta
análise de concordância entre y1 e y2
análise dos melhores modelos
interpretação das features ou cartas mais relevantes
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
* usa spot-checking como etapa inicial de seleção de algoritmos;
* usa nested cross-validation para seleção de hiperparâmetros e estimativa final de desempenho;
* reporta média e desvio padrão das métricas nos outer folds;
* usa as mesmas divisões internas e externas para comparar algoritmos de forma justa;
* define seeds e procedimentos reprodutíveis;
* inclui interpretação de modelos, especialmente na representação Deck Features;
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

> Este projeto estuda a divergência entre duas percepções de poder em decks Commander: o bracket atribuído no Archidekt e o bracket calculado por uma ferramenta externa. Usando dados extraídos do Archidekt, o projeto representa decks de duas formas — Bag of Cards e Deck Features — e treina modelos para entender como cada percepção pode ser aprendida, transferida e comparada. O objetivo não é descobrir o bracket verdadeiro, mas medir e explicar o desalinhamento entre percepção comunitária e avaliação automatizada, ajudando a entender onde expectativas de poder podem divergir antes de uma mesa de Commander.
