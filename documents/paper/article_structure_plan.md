# Plano editorial do artigo

Este documento define a estrutura, a linguagem, o formato e o conteúdo esperado do artigo em `documents/paper/src/main.tex`. Ele não é uma versão do artigo. A função dele é orientar a escrita e servir como checklist antes de reescrever o texto.

## Fontes relidas

- `documents/backbone.md`
- `documents/action_plan.md`
- `documents/enunciado.pdf`
- `documents/paper/src/main.tex`
- Reports de implementação das fases A-J em `documents/reports/implementation/`
- Reports de resultados das fases A-J em `documents/reports/results/`
- Auditorias em `documents/reports/phase_e_reaudit.md`, `documents/reports/phase_e_to_j_audit.md` e `documents/reports/enunciado_a_to_j_coverage_audit.md`
- Reports de validação amostral em `documents/reports/results/sample_reports/`
- Exemplos e instruções oficiais recentes da NeurIPS:
  - [Proceedings 2024](https://proceedings.neurips.cc/paper_files/paper/2024)
  - [Proceedings 2023](https://proceedings.neurips.cc/paper_files/paper/2023)
  - [Proceedings 2022](https://proceedings.neurips.cc/paper_files/paper/2022)
  - [NeurIPS 2024 FAQ for Authors](https://neurips.cc/Conferences/2024/PaperInformation/NeurIPS-FAQ)
  - [NeurIPS 2024 Call for Papers](https://neurips.cc/Conferences/2024/CallForPapers)
  - [NeurIPS Paper Checklist guidance](https://neurips.cc/public/guides/PaperChecklist)

## Objetivo do artigo

O artigo deve responder a uma pergunta científica simples:

> Em que medida é possível predizer o nível de poder declarado por jogadores de Commander a partir de informações de decklist, e como essas predições se relacionam com uma calculadora automática de poder?

A contribuição principal não é propor um novo algoritmo. A contribuição é construir um pipeline reprodutível para um domínio real, comparar representações de deck, avaliar modelos sob validação cruzada repetida, contrastar rótulos humanos com uma calculadora externa e interpretar os sinais usados pelos melhores modelos.

## Estilo

O texto final será em inglês. O enunciado recomenda inglês e o `main.tex` atual já está em inglês.

Use um estilo próximo ao de artigos de machine learning da NeurIPS:

- Começar pelo problema, depois dados, método, resultado e implicação.
- Fazer afirmações apenas quando houver evidência em tabela, métrica, experimento ou apêndice.
- Usar linguagem simples e direta.
- Evitar adjetivos, advérbios e variação desnecessária de termos.
- Usar o mesmo termo para o mesmo conceito em todo o texto.
- Colocar detalhes longos em apêndice: grids completos, verificações de Drive, logs, comandos, matrizes completas e listas extensas.
- Não explicar teoria básica de algoritmos. O artigo deve explicar por que os algoritmos foram escolhidos e como foram avaliados.
- Não usar figuras no corpo principal por enquanto. Usar tabelas compactas e texto.
- Não fazer alegações causais. Usar linguagem como "is associated with", "the model assigns higher importance to" e "the results suggest".

O artigo não precisa obedecer ao template da NeurIPS. A referência é de estilo: texto denso, evidência perto das afirmações, resultados com incerteza, apêndices para detalhes técnicos e checklist de reprodutibilidade. O limite formal do trabalho continua sendo o do enunciado: até 20 páginas, incluindo referências.

## Terminologia fixa

| Conceito | Termo recomendado no artigo |
|---|---|
| Magic: The Gathering | Magic: The Gathering (MTG) na primeira ocorrência; depois MTG |
| Commander | Commander |
| Rótulo do Archidekt | `y_arch` |
| Rótulo da calculadora EDHPowerLevel | `y_calc` |
| Predição do modelo treinado para `y_arch` | `\hat{y}_{arch}` |
| Bag of Cards | BC |
| Deck Features | DF |
| Métrica principal | macro-F1 |
| Predições fora da amostra | out-of-fold predictions ou OOF predictions |
| Concordância exata | exact agreement |
| Concordância com tolerância de um bracket | ±1 agreement |

Evitar alternar entre "power level", "bracket", "rank" e "class" sem necessidade. Quando falar do target, usar "bracket".

## Mensagem central

O corpo principal deve sustentar cinco conclusões:

1. O dataset contém decks públicos de Commander do Archidekt, filtrados para um problema de classificação em três brackets (`2`, `3`, `4`).
2. Modelos treinados com DF superam os modelos treinados com BC para todos os algoritmos avaliados.
3. O melhor modelo individual é `df_gradient_boosting`, com macro-F1 médio de `0.6908 ± 0.0093`; o melhor ensemble é `voting_top3`, com `0.6941 ± 0.0096`.
4. A calculadora não mede exatamente o mesmo sinal que o rótulo do Archidekt: `y_arch` e `y_calc` têm `60.9%` de concordância exata, enquanto alguns modelos chegam a maior concordância com `y_calc` do que o próprio melhor modelo para `y_arch`.
5. A interpretabilidade aponta sinais coerentes com a noção de poder em Commander, sobretudo `game_changer_count`, efeitos de negação de recursos, tutors, combos e cartas associadas a brackets altos.

## Estrutura recomendada do corpo principal

Meta: 8-10 páginas de conteúdo antes de referências e apêndices. O alvo prático é 9 páginas.

### 1. Abstract

Tamanho: 150-200 palavras.

Função: resumir o problema, os dados, a avaliação, os resultados e a conclusão principal.

Conteúdo:

- Definir MTG em uma frase curta antes de mencionar Commander.
- Dizer que Commander decks são avaliados por brackets de poder.
- Dizer que o trabalho modela `y_arch` a partir de duas representações: BC e DF.
- Informar o protocolo principal: nested cross-validation com 3 repeats x 5 folds.
- Reportar o melhor individual, o melhor ensemble e a relação com `y_calc`.
- Fechar com a utilidade: análise de divergência entre julgamento humano e calculadora automática.

Não incluir:

- Detalhes de scraping.
- Lista de algoritmos.
- Teoria sobre Commander.
- Hiperparâmetros.

### 2. Introduction

Tamanho: 0.9-1.1 página.

Função: motivar o problema e declarar as contribuições.

Conteúdo:

- Começar com uma definição breve de MTG.
- Explicar Commander como formato social em que equilíbrio de poder importa.
- Introduzir o problema: power brackets são usados para alinhar expectativas, mas podem ser ruidosos e difíceis de estimar.
- Formular a pergunta de pesquisa.
- Explicar que o trabalho usa decks públicos do Archidekt e compara o rótulo humano com `y_calc`.
- Resumir método e resultados em um parágrafo.
- Fechar com contribuições em 3-4 bullets curtos.

Contribuições sugeridas:

- Um dataset processado de Commander decks com `y_arch`, `y_calc`, BC e DF.
- Uma avaliação de sete algoritmos no spot-checking e doze modelos finais em nested CV.
- Uma comparação entre `y_arch`, `\hat{y}_{arch}` e `y_calc`.
- Uma análise de interpretabilidade dos melhores modelos DF e BC.

Não incluir:

- Regras detalhadas de MTG.
- Discussão longa sobre todos os filtros.
- Resultados completos.

### 3. Background

Tamanho: 0.7-0.9 página.

Função: dar apenas o contexto necessário para entender dados, labels e features.

Subseções recomendadas:

- `Magic: The Gathering and Commander`
- `Commander brackets and automated power estimates`

Conteúdo:

- Explicar MTG como jogo de cartas colecionáveis.
- Explicar Commander: deck de 100 cartas, singleton, comandante, identidade de cores.
- Explicar por que poder do deck importa em partidas casuais.
- Explicar Commander Brackets e por que `b1` e `b5` foram removidos: `b1` e `b5` representam extremos com baixa comparabilidade para o problema central e, no dataset modelável, `y_calc` fora de `{2,3,4}` foi excluído para manter classes comparáveis entre `y_arch` e `y_calc`.
- Explicar a calculadora EDHPowerLevel como referência externa, não como verdade absoluta.
- Incluir um parágrafo curto de contexto relacionado: classificação tabular, representações bag-of-items e interpretabilidade em modelos supervisionados.

Não incluir:

- Tutorial de regras.
- Lista longa de tipos de carta.
- Discussão de algoritmos de ML.

Mover para apêndice:

- Regras detalhadas de turno, zonas, multiplayer e vocabulário.

### 4. Dataset

Tamanho: 1.2-1.5 páginas.

Função: explicar A-C e preparar o leitor para os experimentos.

Conteúdo:

- Fontes: Archidekt, decklists públicas, metadados e EDHPowerLevel.
- Pipeline A: coleta, validação, deduplicação e snapshot processado.
- Pipeline B: EDA e divergência inicial entre `y_arch` e `y_calc`.
- Pipeline C: definição do conjunto modelável e das representações BC/DF.
- Explicar por que os filtros foram aplicados:
  - Commander decks.
  - 100 cartas no mainboard.
  - mínimo de 1000 views.
  - `y_arch` em `{2,3,4}`.
  - `y_calc` em `{2,3,4}` para experimentos comparáveis.
- Explicar que `y_calc` é temporal e foi congelado em snapshot.
- Explicar leakage control: transformações aprendidas apenas no treino de cada fold.

Tabelas principais:

- Tabela de fluxo do dataset:
  - raw records: `14,421`
  - processed decks: `12,950`
  - modeling decks: `12,135`
  - excluded because `y_calc` outside `{2,3,4}`: `815`
- Tabela curta de distribuição de `y_arch` e `y_calc` no conjunto modelável.
- Matriz `y_arch` x `y_calc`. Esta matriz deve ficar na seção Dataset para definir a relação inicial entre o rótulo humano e a calculadora antes dos modelos.

Não incluir:

- Todos os reports de validação amostral.
- Todas as features DF.
- Todas as cartas únicas.

Mover para apêndice:

- Validação amostral da Fase A.
- Catálogo completo de features DF.
- Mais estatísticas EDA.

### 5. Spot-Checking

Tamanho: 0.5-0.7 página.

Função: explicar D como triagem de algoritmos antes do treino principal.

Conteúdo:

- Declarar que o spot-checking não é o treino final.
- Explicar o hold-out repetido: 5 seeds, split estratificado 80/20.
- Listar os sete algoritmos avaliados:
  - Decision Tree
  - Random Forest
  - HistGradientBoosting
  - Naive Bayes
  - Logistic Regression
  - Linear SVC
  - KNN
- Explicar a seleção: top 5 por representação, união dos selecionados.
- Dizer que KNN foi removido e que os seis algoritmos restantes foram treinados em BC e DF na Fase E.

Tabela principal:

- Tabela curta com macro-F1 de spot-checking por representação e status: selected ou dropped.

Não incluir:

- Boxplots.
- Todos os valores por seed.
- Discussão extensa de cada algoritmo.

Mover para apêndice:

- Resultados completos por seed.
- Figuras de spot-checking, se forem usadas.

### 6. Training and Model Selection

Tamanho: 2.2-2.6 páginas.

Função: ser a seção principal do artigo. Deve cobrir E, G e H; F entra como validação resumida e depois vai para apêndice.

Subseções recomendadas:

- `Nested cross-validation`
- `Model grids and preprocessing`
- `Individual model results`
- `Voting ensembles`
- `Selected models`

Conteúdo E:

- Explicar o protocolo:
  - 3 repeats.
  - 5 outer folds por repeat.
  - 15 avaliações externas por modelo.
  - 3-fold inner CV para hiperparâmetros.
  - mesmos folds para todos os modelos.
  - target sempre `y_arch`.
- Explicar que BC e DF usam preprocessamento por fold.
- Explicar que cada algoritmo teve 24 configurações no grid.
- Reportar resultados dos 12 modelos individuais.
- Incluir tempo de treino como estatística auxiliar, com cuidado: reportar como wall-clock observado por modelo/fold, dependente de hardware e checkpoints, não como métrica científica principal.

Conteúdo F resumido:

- Um parágrafo dizendo que a verificação confirmou completude dos modelos/folds, consistência das linhas e folds compartilhados.
- Mencionar GroupKFold por comandante como teste de robustez contra memorização de comandante.
- Mencionar Friedman/Nemenyi/Wilcoxon como análise pareada dos outer scores.
- Detalhes no apêndice.

Conteúdo G:

- Explicar voting simples sem retreino, baseado em OOF predictions.
- Explicar os ensembles atuais:
  - `voting_top3`
  - `voting_top5`
  - `voting_top7`
- Dizer que os modelos foram escolhidos por macro-F1.
- Reportar se voting melhora ou não:
  - melhor individual: `df_gradient_boosting`, `0.6908 ± 0.0093`
  - melhor ensemble: `voting_top3`, `0.6941 ± 0.0096`
  - ganho absoluto: `0.0033`

Conteúdo H:

- Declarar três seleções:
  - melhor individual geral: `df_gradient_boosting`
  - melhor DF: `df_gradient_boosting`
  - melhor BC: `bc_gradient_boosting`
  - melhor geral incluindo ensembles: `voting_top3`
- Deixar claro que a Fase J usa os melhores modelos individuais por representação, não o ensemble.

Tabelas principais:

- Tabela de resultados dos 12 modelos individuais: representation, algorithm, macro-F1 mean, std, accuracy mean.
- Tabela curta de voting: ensemble, members, macro-F1 mean, std, delta vs best individual.
- Tabela curta de modelos selecionados para H/J.

Não incluir:

- Grid completo.
- Best hyperparameters de todos os folds.
- Todas as matrizes de modelo; a exceção planejada é a matriz `y_arch` x `y_calc` na seção Dataset.
- Todos os testes estatísticos.

Mover para apêndice:

- Grids completos.
- Best hyperparameters por fold.
- Métricas por fold.
- GroupKFold completo.
- Friedman/Nemenyi/Wilcoxon completo.
- Drive/model artifact audit.

### 7. Model-Calculator Comparison

Tamanho: 1.0-1.2 página.

Função: explicar I e separar três conceitos: `y_arch`, `\hat{y}_{arch}` e `y_calc`.

Conteúdo:

- Abrir dizendo que a Fase I não treina modelos.
- Explicar que a análise usa OOF predictions já salvas na Fase E/G.
- Explicar por que há `36,405` linhas nas matrizes: `12,135` decks avaliados em `3` repeats.
- Comparar:
  - `y_arch` vs `y_calc`
  - `\hat{y}_{arch}` vs `y_calc`
- Reportar para ambos:
  - exact agreement
  - ±1 agreement
  - macro-F1 against `y_calc`
  - mean absolute delta
- Para `y_arch` vs `y_calc`, referenciar a matriz já apresentada na seção Dataset.
- Para `\hat{y}_{arch}` vs `y_calc`, deixar as matrizes de confusão completas no apêndice, salvo se houver espaço para uma matriz exemplar.
- Explicar a leitura científica: alta concordância com `y_calc` não significa melhor predição de `y_arch`; significa que o modelo se aproxima mais da calculadora.

Tabelas principais:

- Tabela de baseline `y_arch` vs `y_calc` com métricas agregadas, sem repetir a matriz da seção Dataset.
- Tabela de modelos relevantes:
  - maior concordância: `df_random_forest`
  - menor concordância: `bc_decision_tree`
  - maior gap absoluto: `df_gradient_boosting`
  - menor gap absoluto: `bc_naive_bayes`
  - melhor DF para `y_arch`: `df_gradient_boosting`
  - melhor BC para `y_arch`: `bc_gradient_boosting`
  - melhor ensemble: `voting_top3`
- Uma matriz de confusão exemplar de modelo apenas se houver espaço. Caso contrário, mover todas para o apêndice.

Não incluir:

- Matrizes de modelo no corpo principal, exceto uma matriz exemplar se houver espaço.
- Interpretação causal sobre a calculadora.
- Linguagem dizendo que `y_calc` é ground truth.

Mover para apêndice:

- Todas as matrizes de confusão.
- Tabelas completas ordenadas por concordância, gap e macro-F1.

### 8. Interpretability

Tamanho: 1.0-1.2 página.

Função: explicar J usando os melhores modelos individuais por representação.

Conteúdo:

- Reafirmar que os modelos interpretados são:
  - DF: `df_gradient_boosting`
  - BC: `bc_gradient_boosting`
- Explicar que o modelo final para interpretação é ajustado no conjunto completo apenas para análise interpretável; a evidência de generalização vem da nested CV.
- DF:
  - permutation importance.
  - direção das features por bracket predito.
  - associação com divergência `\hat{y}_{arch}` vs `y_calc`.
- BC:
  - análise de lift de cartas.
  - cartas associadas ao bracket 4.
  - cartas associadas a divergências.
- Conectar os achados a Commander:
  - game changers.
  - tutors.
  - combos.
  - negação de recursos.
  - aceleração de mana.

Tabelas principais:

- Tabela com top DF features por permutation importance.
- Tabela curta com top BC cards associadas ao bracket 4 e/ou divergência.

Não incluir:

- Listas longas de cartas.
- Todas as classes.
- Afirmações de que uma carta causa um bracket.

Mover para apêndice:

- Tabelas completas de permutation importance.
- Lift por bracket.
- Lift por tipo de divergência.

### 9. Conclusion

Tamanho: 0.4-0.6 página.

Função: responder à pergunta de pesquisa e declarar limites.

Conteúdo:

- Retomar a pergunta.
- Resumir os três resultados:
  - DF > BC.
  - voting melhora pouco.
  - `y_calc` captura sinal relacionado, mas não idêntico a `y_arch`.
- Incluir uma subseção curta chamada `Discussion, Limitations, and Future Work`.
- Na subseção, declarar limitações:
  - `y_arch` é autorreportado.
  - `y_calc` é snapshot temporal.
  - dados vêm de decks públicos do Archidekt com filtros.
  - não há resultado de partidas reais.
- Na mesma subseção, fechar com próximos passos:
  - ampliar fontes.
  - incluir brackets extremos com outro desenho experimental.
  - testar modelos calibrados ou ordinal classification.
  - analisar estabilidade temporal da calculadora.

Não incluir:

- Novos resultados.
- Tabelas.
- Promessas não suportadas.

## Apêndices recomendados

O artigo completo pode ter até 20 páginas, incluindo referências, segundo o enunciado. Se o corpo tiver 9 páginas, reservar cerca de 8-10 páginas para apêndices e referências.

### Appendix A. MTG and Commander Details

- Regras básicas de MTG.
- Regras de Commander.
- Identidade de cores.
- Singleton.
- Zonas e tipos de carta.
- Vocabulário usado em features.

### Appendix B. Dataset Construction and Validation

- Detalhes completos de A.
- Validação amostral.
- Snapshot do Drive.
- Critérios de exclusão.
- Limitações de scraping e temporalidade de `y_calc`.

### Appendix C. Preprocessing and Representations

- Fase C completa.
- Lista de feature groups DF.
- Construção de BC.
- Imputação, winsorization, scaling e pruning.
- Leakage controls.

### Appendix D. Spot-Checking Details

- Resultados completos de D.
- Valores por seed.
- Escolha da união de modelos.
- Justificativa para remover KNN.

### Appendix E. Training Details and Verification

- Fase E completa.
- Grids de hiperparâmetros.
- Fase F completa.
- Completeness checks.
- GroupKFold por comandante.
- Friedman, Nemenyi e Wilcoxon.
- Métricas por fold.
- Auditoria de artefatos e download.

### Appendix F. Voting and Best Models

- Fase G completa.
- Tie-break de voting.
- Membros de cada ensemble.
- Fase H completa.
- Rankings completos individuais e ensembles.

### Appendix G. Calculator Comparison

- Fase I completa.
- Tabelas completas de `y_arch` vs `y_calc`.
- Tabelas completas de `\hat{y}_{arch}` vs `y_calc`.
- Todas as matrizes de confusão.
- Explicação das 36,405 linhas OOF.

### Appendix H. Interpretability

- Fase J completa.
- Permutation importance completa.
- Lift completo de cartas.
- Análises de divergência.

### Appendix I. AI Use and Reproducibility Statement

- Declaração de uso de IA, se aplicável.
- Link ou referência para código, dados, modelos e comandos de reprodução.
- Seeds e splits.

## Inventário de tabelas do corpo principal

| Ordem | Tabela | Seção | Observação |
|---|---|---|---|
| 1 | Dataset flow and label distributions | Dataset | Compactar fluxo e distribuição se possível |
| 2 | `y_arch` x `y_calc` matrix | Dataset | Define a divergência inicial antes dos modelos |
| 3 | Spot-checking selection | Spot-Checking | Mostrar selected/dropped |
| 4 | Individual nested-CV results | Training | 12 linhas; ordenar por macro-F1 |
| 5 | Voting ensembles | Training | 3 linhas; incluir delta vs best individual |
| 6 | Model selection summary | Training | best overall, best DF, best BC, best ensemble |
| 7 | Calculator comparison highlights | Model-Calculator Comparison | Apenas casos interpretáveis |
| 8 | Interpretability summary | Interpretability | DF features e BC cards; pode virar duas tabelas pequenas |

Se passar de 10 páginas, remover a tabela 6 e integrar sua informação no texto.

## Conteúdo que não deve entrar no corpo principal

- Código.
- Comandos de terminal.
- Manifest completo do Drive.
- Checkpoints por fold.
- Grids completos.
- Todas as predições OOF.
- Todas as matrizes de confusão.
- Todas as listas de cartas.
- Longas descrições de regras de MTG.
- Teoria introdutória de Decision Tree, Random Forest, SVM, Logistic Regression, Naive Bayes ou Gradient Boosting.

## Relação entre fases e seções

| Fase | Onde entra no artigo |
|---|---|
| A | Dataset; Appendix B |
| B | Dataset; Model-Calculator Comparison; Appendix B/G |
| C | Dataset; Training; Appendix C |
| D | Spot-Checking; Appendix D |
| E | Training and Model Selection; Appendix E |
| F | Um parágrafo em Training; Appendix E |
| G | Training and Model Selection; Appendix F |
| H | Training and Model Selection; Appendix F |
| I | Model-Calculator Comparison; Appendix G |
| J | Interpretability; Appendix H |

## Decisões confirmadas

Todas as decisões abaixo foram confirmadas antes da reescrita do artigo:

1. O artigo final será em inglês.
2. O corpo principal ficará sem figuras por enquanto.
3. A matriz `y_arch` x `y_calc` ficará na seção Dataset.
4. A tabela principal de nested CV mostrará os 12 modelos, porque a comparação BC vs DF é uma conclusão central.
5. As limitações não terão seção própria no corpo. Elas ficarão como subseção da conclusão, junto com discussão e trabalhos futuros.
6. A declaração de uso de IA ficará no apêndice.

## Checklist para a próxima edição do `main.tex`

- Abstract define MTG antes de Commander.
- Introduction define MTG antes de Commander.
- Background explica por que `b1` e `b5` ficam fora do problema principal.
- Estrutura do corpo segue as 9 seções deste plano.
- Figuras continuam removidas do corpo principal.
- E, G, H, I e J aparecem no corpo principal.
- F aparece de forma resumida no corpo e completa no apêndice.
- O texto diferencia `y_arch`, `y_calc` e `\hat{y}_{arch}`.
- O texto declara que I usa predições OOF salvas e não retreina modelos.
- O texto declara que J interpreta os melhores modelos individuais DF e BC escolhidos separadamente.
- Apêndices contêm o material de auditoria e reprodução que não cabe no corpo.
