# Spot-checking — Fase D

## Objetivo

Avaliar rapidamente os algoritmos candidatos em hold-out 80/20 estratificado por `y1`, usando as duas representações do projeto: Deck Features (`DF`) e Bag of Cards (`BC`). Esta fase escolhe os algoritmos finalistas que avançam para a nested CV.

## Configuração

- `processed_dir`: `data/processed/archidekt`
- `random_state`: `42`
- `test_size`: `0.2`
- `bc_min_df_values`: `5, 10, 20`
- `best_bc_min_df`: `10`
- `use_tfidf`: `False` nesta etapa
- Combinações com sucesso: 30
- Combinações puladas: 0
- Combinações com erro: 0

## Resultados por combinação

| Representação | Algoritmo | bc_min_df | TF-IDF | Status | Macro-F1 | Accuracy | Precision macro | Recall macro | Features | Tempo total (s) |
|---|---|---:|---|---|---:|---:|---:|---:|---:|---:|
| BC | `decision_tree` | 5 | não | ok | 0.5202 | 0.5426 | 0.5199 | 0.5206 | 13355 | 1.5500 |
| BC | `decision_tree` | 10 | não | ok | 0.5297 | 0.5546 | 0.5320 | 0.5276 | 10069 | 1.4170 |
| BC | `decision_tree` | 20 | não | ok | 0.5412 | 0.5628 | 0.5439 | 0.5388 | 6856 | 1.3840 |
| BC | `gradient_boosting` | 5 | não | ok | 0.6276 | 0.6539 | 0.6457 | 0.6168 | 13355 | 60.5670 |
| BC | `gradient_boosting` | 10 | não | ok | 0.6276 | 0.6539 | 0.6457 | 0.6168 | 10069 | 46.9320 |
| BC | `gradient_boosting` | 20 | não | ok | 0.6276 | 0.6539 | 0.6457 | 0.6168 | 6856 | 33.2520 |
| BC | `knn` | 5 | não | ok | 0.4532 | 0.5043 | 0.4666 | 0.4473 | 13355 | 0.5870 |
| BC | `knn` | 10 | não | ok | 0.4415 | 0.4895 | 0.4590 | 0.4375 | 10069 | 0.5840 |
| BC | `knn` | 20 | não | ok | 0.4384 | 0.4850 | 0.4617 | 0.4396 | 6856 | 0.5260 |
| BC | `linear_svc` | 5 | não | ok | 0.5558 | 0.5822 | 0.5561 | 0.5558 | 13355 | 8.7900 |
| BC | `linear_svc` | 10 | não | ok | 0.5465 | 0.5731 | 0.5460 | 0.5473 | 10069 | 8.8160 |
| BC | `linear_svc` | 20 | não | ok | 0.5225 | 0.5517 | 0.5221 | 0.5238 | 6856 | 1.8190 |
| BC | `logistic_regression` | 5 | não | ok | 0.5900 | 0.6193 | 0.5970 | 0.5844 | 13355 | 5.9940 |
| BC | `logistic_regression` | 10 | não | ok | 0.5891 | 0.6172 | 0.5947 | 0.5844 | 10069 | 5.6670 |
| BC | `logistic_regression` | 20 | não | ok | 0.5873 | 0.6160 | 0.5928 | 0.5827 | 6856 | 5.0790 |
| BC | `naive_bayes` | 5 | não | ok | 0.5491 | 0.5583 | 0.5410 | 0.5679 | 13355 | 0.4120 |
| BC | `naive_bayes` | 10 | não | ok | 0.5536 | 0.5595 | 0.5453 | 0.5781 | 10069 | 0.3910 |
| BC | `naive_bayes` | 20 | não | ok | 0.5594 | 0.5641 | 0.5513 | 0.5875 | 6856 | 0.3780 |
| BC | `random_forest` | 5 | não | ok | 0.5200 | 0.6337 | 0.6697 | 0.5104 | 13355 | 0.7770 |
| BC | `random_forest` | 10 | não | ok | 0.5380 | 0.6436 | 0.6859 | 0.5239 | 10069 | 0.7490 |
| BC | `random_forest` | 20 | não | ok | 0.5321 | 0.6292 | 0.6471 | 0.5171 | 6856 | 0.7400 |
| DF | `decision_tree` |  | não | ok | 0.5959 | 0.6172 | 0.5934 | 0.5993 | 102 | 0.6990 |
| DF | `gradient_boosting` |  | não | ok | 0.6755 | 0.6996 | 0.7028 | 0.6636 | 102 | 2.5520 |
| DF | `knn` |  | não | ok | 0.5099 | 0.5558 | 0.5383 | 0.4991 | 102 | 0.4200 |
| DF | `linear_svc` |  | não | ok | 0.6285 | 0.6836 | 0.6912 | 0.6055 | 102 | 1.1520 |
| DF | `logistic_regression` |  | não | ok | 0.6736 | 0.6976 | 0.6996 | 0.6601 | 102 | 0.4820 |
| DF | `naive_bayes` |  | não | ok | 0.5654 | 0.5608 | 0.5777 | 0.6201 | 102 | 0.4180 |
| DF | `random_forest` |  | não | ok | 0.6651 | 0.7046 | 0.7163 | 0.6415 | 102 | 0.7230 |
| DF | `svc_poly` |  | não | ok | 0.5396 | 0.6333 | 0.6561 | 0.5222 | 102 | 2.3780 |
| DF | `svc_rbf` |  | não | ok | 0.6280 | 0.6774 | 0.6887 | 0.6039 | 102 | 2.7490 |

## Ranking dos algoritmos por representação

O ranking é separado por representação. Para BC, usa apenas o `bc_min_df` escolhido. Os kernels não-lineares de SVM (`svc_rbf`, `svc_poly`) são avaliados só em DF; em BC, o custo de kernel não-linear sobre matriz esparsa de alta dimensionalidade não é adequado para este projeto.

### DF

| Rank | Algoritmo | Macro-F1 | Elegível | Top-5 automático | Observação |
|---:|---|---:|---|---|---|
| 1 | `gradient_boosting` | 0.6755 | sim | sim |  |
| 2 | `logistic_regression` | 0.6736 | sim | sim |  |
| 3 | `random_forest` | 0.6651 | sim | sim |  |
| 4 | `linear_svc` | 0.6285 | sim | sim |  |
| 5 | `svc_rbf` | 0.6280 | sim | sim |  |
| 6 | `decision_tree` | 0.5959 | sim | não |  |
| 7 | `naive_bayes` | 0.5654 | sim | não |  |
| 8 | `svc_poly` | 0.5396 | sim | não |  |
| 9 | `knn` | 0.5099 | sim | não |  |

### BC

| Rank | Algoritmo | Macro-F1 | Elegível | Top-5 automático | Observação |
|---:|---|---:|---|---|---|
| 1 | `gradient_boosting` | 0.6276 | sim | sim |  |
| 2 | `logistic_regression` | 0.5891 | sim | sim |  |
| 3 | `naive_bayes` | 0.5536 | sim | sim |  |
| 4 | `linear_svc` | 0.5465 | sim | sim |  |
| 5 | `random_forest` | 0.5380 | sim | sim |  |
| 6 | `decision_tree` | 0.5297 | sim | não |  |
| 7 | `knn` | 0.4415 | sim | não |  |


## Top-5 automático por representação

- DF: `gradient_boosting`, `logistic_regression`, `random_forest`, `linear_svc`, `svc_rbf`
- BC: `gradient_boosting`, `logistic_regression`, `naive_bayes`, `linear_svc`, `random_forest`

## Decisão final

Após revisão do spot-check, o projeto usará o mesmo conjunto de algoritmos para DF e BC:

```text
A_5 = {gradient_boosting, logistic_regression, random_forest, linear_svc, naive_bayes}
```

Justificativa: a performance dos candidatos de borda não muda o suficiente para compensar a perda de comparabilidade entre representações. `svc_rbf` teve bom resultado em DF, mas não é viável em BC neste desenho; `naive_bayes` é barato, interpretável e adequado para Bag of Cards.

## Problemas encontrados

- Nenhum problema operacional encontrado.

## Próximo passo

Rodar a nested CV da Fase E com os 5 algoritmos selecionados em `A_5` nas duas representações.
