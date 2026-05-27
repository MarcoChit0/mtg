# Fase J — Interpretabilidade dos Melhores Modelos

> Gerado automaticamente por `scripts/phase_j_interpretability.py`.
> Estimativas de generalização vêm da **Fase E** (nested CV).
> Este modelo final é treinado em todos os dados **exclusivamente para interpretação**.
> `y2` aparece apenas como label de comparação — nunca como alvo de treino (backbone §5).

## 0. Configuração

| Parâmetro | Valor |
|---|---|
| Modelo DF | `df_gradient_boosting` |
| Modelo BC | `bc_gradient_boosting` |
| Hiperparâmetros DF | modal dos 15 outer folds: {'class_weight': 'balanced', 'learning_rate': 0.05, 'max_iter': 200, 'max_leaf_nodes': 31} |
| Hiperparâmetros BC | modal dos 15 outer folds: {'class_weight': 'balanced', 'learning_rate': 0.05, 'max_iter': 200, 'max_leaf_nodes': 31} |
| Split treino/val (DF) | 80/20 — n_train=9708, n_val=2427 |
| PI n_repeats (DF) | 10 |
| Features DF (após pré-proc.) | 102 |
| Vocabulário BC (min_df=10) | 11114 cartas |
| OOF entries BC | 36405 (12.135 decks × 3 repeats) |

## 1. `df_gradient_boosting` — Deck Features

> **Método**: permutation importance sobre hold-out estratificado (20%).
> HistGradientBoostingClassifier não expõe `feature_importances_` MDI diretamente;
> permutation importance é o método recomendado pelo sklearn para este estimador.

### 1.1 Importância de features (permutation importance, macro-F1)

| # | Feature | PI médio | PI dp |
|---|---|---:|---:|
| 1 | `game_changer_count` | 0.2325 | 0.0094 |
| 2 | `mass_land_denial_count` | 0.0272 | 0.0028 |
| 3 | `unique_atomic_combo_refs_count` | 0.0083 | 0.0055 |
| 4 | `tutor_count` | 0.0042 | 0.0028 |
| 5 | `land_mana_production_U` | 0.0035 | 0.0015 |
| 6 | `cmc_4_count` | 0.0028 | 0.0021 |
| 7 | `nonland_cmc_mean` | 0.0020 | 0.0022 |
| 8 | `cmc_2_count` | 0.0014 | 0.0018 |
| 9 | `unique_card_count` | 0.0014 | 0.0013 |
| 10 | `land_mana_production_W` | 0.0014 | 0.0009 |
| 11 | `ward_count` | 0.0007 | 0.0006 |
| 12 | `vehicle_subtype_count` | 0.0006 | 0.0010 |
| 13 | `cards_with_atomic_combos_count` | 0.0006 | 0.0031 |
| 14 | `layout_modal_dfc_count` | 0.0006 | 0.0022 |
| 15 | `enchantment_count` | 0.0006 | 0.0015 |

### 1.2 Direção do efeito por bracket previsto

> Médias do valor da feature condicionadas ao bracket previsto pelo modelo no val set.
> Interpretação como hipótese analítica — não implica causalidade.

| Feature | Geral | Bracket 2 (pred) | Bracket 3 (pred) | Bracket 4 (pred) |
|---|---:|---:|---:|---:|
| `game_changer_count` | 1.737 | 0.003 | 1.475 | 4.233 |
| `mass_land_denial_count` | 0.052 | 0.000 | 0.000 | 0.211 |
| `unique_atomic_combo_refs_count` | 17.252 | 10.231 | 16.216 | 27.313 |
| `tutor_count` | 2.315 | 1.095 | 2.357 | 3.638 |
| `land_mana_production_U` | 10.136 | 9.649 | 10.066 | 10.832 |
| `cmc_4_count` | 9.859 | 10.242 | 9.736 | 9.657 |
| `nonland_cmc_mean` | 3.238 | 3.207 | 3.263 | 3.226 |
| `cmc_2_count` | 16.713 | 17.268 | 16.685 | 16.127 |
| `unique_card_count` | 87.404 | 85.632 | 88.073 | 88.161 |
| `land_mana_production_W` | 9.448 | 9.690 | 9.751 | 8.590 |
| `ward_count` | 0.570 | 0.547 | 0.570 | 0.598 |
| `vehicle_subtype_count` | 0.256 | 0.418 | 0.231 | 0.117 |
| `cards_with_atomic_combos_count` | 7.019 | 5.221 | 6.815 | 9.477 |
| `layout_modal_dfc_count` | 1.602 | 1.437 | 1.850 | 1.317 |
| `enchantment_count` | 8.732 | 8.900 | 8.522 | 8.941 |

### 1.3 Features associadas à divergência ŷ1 vs y2

> OOF entries: 23297 concordantes (ŷ1=y2), 13108 divergentes (ŷ1≠y2).
> `delta` = mean(divergente) − mean(concordante). `norm_delta` = delta / dp_geral.

| Feature | Conc. média | Div. média | Δ | Δ normalizado |
|---|---:|---:|---:|---:|
| `game_changer_count` | 2.165 | 0.939 | -1.226 | -0.558 |
| `salt_std` | 0.375 | 0.341 | -0.034 | -0.341 |
| `edhrec_rank_mean` | 2707.804 | 2410.914 | -296.890 | -0.253 |
| `salt_mean` | 0.446 | 0.422 | -0.024 | -0.241 |
| `edhrec_rank_median` | 1360.352 | 1146.467 | -213.885 | -0.235 |
| `mass_land_denial_count` | 0.099 | 0.004 | -0.095 | -0.235 |
| `rare_count` | 43.328 | 45.707 | 2.379 | 0.221 |
| `basic_land_count` | 15.679 | 14.023 | -1.656 | -0.219 |
| `edhrec_rank_std` | 3386.418 | 3132.850 | -253.568 | -0.214 |
| `nonbasic_land_count` | 19.324 | 20.921 | 1.597 | 0.210 |

## 2. `bc_gradient_boosting` — Bag of Cards

> **Método**: lift analysis sobre as 36.405 predições OOF existentes.
> `lift[k][carta] = P(carta presente | ŷ1=k) / P(carta presente)`.
> Permutation importance omitida: conversão densa de ~10k features × HistGB seria inviável.
> Cartas com menos de 10 decks únicos são filtradas.

### 2.1. Top-20 cartas — Bracket 2 (casual)

| # | Carta | Lift | Freq. no bracket | Freq. geral |
|---|---|---:|---:|---:|
| 1 | Owlbear | 3.467 | 0.3% | 0.1% |
| 2 | Bear Cub | 3.251 | 0.4% | 0.1% |
| 3 | Miscalculation | 3.236 | 0.3% | 0.1% |
| 4 | Zodiac Monkey | 3.179 | 0.3% | 0.1% |
| 5 | Tree Monkey | 3.179 | 0.3% | 0.1% |
| 6 | Striped Bears | 3.152 | 0.3% | 0.1% |
| 7 | Ulvenwald Bear | 3.152 | 0.3% | 0.1% |
| 8 | Wily Bandar | 3.121 | 0.3% | 0.1% |
| 9 | Burnout Bashtronaut | 3.121 | 0.3% | 0.1% |
| 10 | Goliath Paladin | 3.082 | 0.3% | 0.1% |
| 11 | Chariot of Victory | 3.055 | 0.4% | 0.1% |
| 12 | At Knifepoint | 3.047 | 0.3% | 0.1% |
| 13 | Compleated Huntmaster | 3.005 | 0.2% | 0.1% |
| 14 | Start the TARDIS | 2.986 | 0.3% | 0.1% |
| 15 | Valiant Changeling | 2.986 | 0.3% | 0.1% |
| 16 | Scrounging Bandar | 2.972 | 0.3% | 0.1% |
| 17 | Aryel, Knight of Windgrace | 2.972 | 0.3% | 0.1% |
| 18 | Pale Bears | 2.934 | 0.3% | 0.1% |
| 19 | Mother Bear | 2.920 | 0.5% | 0.2% |
| 20 | Balduvian Bears | 2.890 | 0.4% | 0.1% |

### 2.2. Top-20 cartas — Bracket 3 (médio)

| # | Carta | Lift | Freq. no bracket | Freq. geral |
|---|---|---:|---:|---:|
| 1 | Ongoing Investigation | 2.191 | 0.2% | 0.1% |
| 2 | Asmoranomardicadaistinaculdacar | 2.028 | 0.2% | 0.1% |
| 3 | Rustler Rampage | 1.927 | 0.3% | 0.1% |
| 4 | Detective of the Month | 1.922 | 0.6% | 0.3% |
| 5 | Book of Mazarbul | 1.918 | 0.2% | 0.1% |
| 6 | Lamentation | 1.909 | 0.3% | 0.1% |
| 7 | Braulios of Pheres Band | 1.893 | 0.2% | 0.1% |
| 8 | Waterbender's Restoration | 1.884 | 0.5% | 0.3% |
| 9 | Dance of the Tumbleweeds | 1.872 | 0.2% | 0.1% |
| 10 | Foundation Breaker | 1.867 | 1.1% | 0.6% |
| 11 | Tanufel Rimespeaker | 1.866 | 0.2% | 0.1% |
| 12 | Saproling Cluster | 1.866 | 0.2% | 0.1% |
| 13 | Canyon Jerboa | 1.866 | 0.2% | 0.1% |
| 14 | Emergency Weld | 1.866 | 0.2% | 0.1% |
| 15 | Nikya of the Old Ways | 1.861 | 0.3% | 0.1% |
| 16 | Five Hundred Year Diary | 1.850 | 0.4% | 0.2% |
| 17 | Wren's Run Packmaster | 1.844 | 0.2% | 0.1% |
| 18 | The Boulder, Ready to Rumble | 1.844 | 0.2% | 0.1% |
| 19 | Flamebraider | 1.844 | 0.2% | 0.1% |
| 20 | Thorn Mammoth | 1.839 | 0.5% | 0.2% |

### 2.3. Top-20 cartas — Bracket 4 (competitivo)

| # | Carta | Lift | Freq. no bracket | Freq. geral |
|---|---|---:|---:|---:|
| 1 | Blood Moon | 3.325 | 3.5% | 1.0% |
| 2 | Winter Moon | 3.325 | 2.1% | 0.6% |
| 3 | Ruination | 3.325 | 0.5% | 0.2% |
| 4 | Harbinger of the Seas | 3.278 | 1.3% | 0.4% |
| 5 | Back to Basics | 3.186 | 0.8% | 0.3% |
| 6 | Chrome Mox | 3.185 | 6.7% | 2.1% |
| 7 | Imperial Seal | 3.160 | 2.1% | 0.7% |
| 8 | Grim Monolith | 3.138 | 2.1% | 0.7% |
| 9 | Mox Diamond | 3.114 | 2.0% | 0.7% |
| 10 | Chain of Smog | 3.090 | 1.3% | 0.4% |
| 11 | Armageddon | 3.060 | 1.2% | 0.4% |
| 12 | Trinisphere | 3.048 | 0.3% | 0.1% |
| 13 | Winter Orb | 3.042 | 1.2% | 0.4% |
| 14 | Mana Vault | 3.009 | 8.5% | 2.8% |
| 15 | Pithing Needle | 2.984 | 0.3% | 0.1% |
| 16 | Tainted Pact | 2.972 | 0.5% | 0.2% |
| 17 | Food Chain | 2.955 | 1.5% | 0.5% |
| 18 | Spelltithe Enforcer | 2.922 | 0.3% | 0.1% |
| 19 | Temporal Manipulation | 2.896 | 1.8% | 0.6% |
| 20 | Static Orb | 2.891 | 0.5% | 0.2% |

### 2.4 Cartas associadas à divergência ŷ1 vs y2
> OOF: 21955 concordantes, 14450 divergentes
> (4373 super-previstos ŷ1>y2, 10077 sub-previstos ŷ1<y2).

#### Cartas enriquecidas em decks divergentes (lift vs concordantes)

| # | Carta | Lift | Freq. div. | Freq. conc. |
|---|---|---:|---:|---:|
| 1 | Infesting Radroach | 3.466 | 0.5% | 0.1% |
| 2 | Seifer, Balamb Rival | 3.063 | 0.2% | 0.0% |
| 3 | Arahbo, Roar of the World | 2.896 | 0.3% | 0.1% |
| 4 | Marshland Bloodcaster | 2.820 | 0.2% | 0.0% |
| 5 | Akal Pakal, First Among Equals | 2.794 | 0.2% | 0.0% |
| 6 | Transdimensional Bovine | 2.794 | 0.2% | 0.0% |
| 7 | Disruption Protocol | 2.716 | 0.3% | 0.1% |
| 8 | Arcbound Worker | 2.690 | 0.3% | 0.1% |
| 9 | Bloatfly Swarm | 2.680 | 0.4% | 0.1% |
| 10 | Vexing Radgull | 2.675 | 0.5% | 0.2% |

#### Cartas enriquecidas em decks concordantes (lift vs divergentes)

| # | Carta | Lift | Freq. conc. | Freq. div. |
|---|---|---:|---:|---:|
| 1 | Blood Moon | 35.707 | 1.7% | 0.0% |
| 2 | Winter Moon | 21.770 | 1.0% | 0.0% |
| 3 | Harbinger of the Seas | 10.914 | 0.6% | 0.0% |
| 4 | Ruination | 6.466 | 0.3% | 0.0% |
| 5 | Back to Basics | 6.038 | 0.4% | 0.0% |
| 6 | Imperial Seal | 5.897 | 1.0% | 0.1% |
| 7 | Gandalf the Grey | 5.646 | 0.2% | 0.0% |
| 8 | Chrome Mox | 5.297 | 3.1% | 0.5% |
| 9 | Force of Will | 5.019 | 4.0% | 0.8% |
| 10 | Armageddon | 4.983 | 0.6% | 0.1% |

#### Cartas enriquecidas em decks super-previstos (ŷ1 > y2)

| # | Carta | Lift | Freq. ŷ1>y2 | Freq. ŷ1<y2 |
|---|---|---:|---:|---:|
| 1 | Titan's Presence | 32.100 | 1.6% | 0.0% |
| 2 | Desecrate Reality | 25.280 | 2.0% | 0.0% |
| 3 | Zhulodok, Void Gorger | 24.464 | 2.6% | 0.1% |
| 4 | It That Heralds the End | 22.049 | 2.6% | 0.1% |
| 5 | Conduit of Ruin | 21.328 | 3.1% | 0.1% |
| 6 | Eye of Ugin | 20.534 | 2.6% | 0.1% |
| 7 | Skittering Cicada | 20.134 | 2.4% | 0.1% |
| 8 | Abstruse Archaic | 19.751 | 0.9% | 0.0% |
| 9 | Breaker of Creation | 19.424 | 1.7% | 0.0% |
| 10 | Devourer of Destiny | 17.625 | 1.0% | 0.0% |

#### Cartas enriquecidas em decks sub-previstos (ŷ1 < y2)

| # | Carta | Lift | Freq. ŷ1<y2 | Freq. ŷ1>y2 |
|---|---|---:|---:|---:|
| 1 | Vorinclex, Voice of Hunger | 42.282 | 2.1% | 0.0% |
| 2 | Caesar, Legion's Emperor | 27.794 | 1.3% | 0.0% |
| 3 | Champions from Beyond | 23.626 | 1.1% | 0.0% |
| 4 | Timestream Navigator | 22.832 | 1.1% | 0.0% |
| 5 | Ajani, Nacatl Pariah // Ajani, Nacatl Avenger | 22.038 | 1.1% | 0.0% |
| 6 | Wrecking Ball Arm | 20.450 | 1.0% | 0.0% |
| 7 | Expropriate | 18.267 | 0.9% | 0.0% |
| 8 | Ms. Bumbleflower | 15.939 | 1.1% | 0.0% |
| 9 | Time Stretch | 15.885 | 0.7% | 0.0% |
| 10 | Time Sieve | 15.290 | 0.7% | 0.0% |

## 3. Artefatos

| Artefato | Caminho |
|---|---|
| Hiperparâmetros finais usados | `experiments/phase_j_interpretability/final_model_params.json` |
| PI DF (raw) | `experiments/phase_j_interpretability/df_permutation_importance.json` |
| Lift BC por classe (raw) | `experiments/phase_j_interpretability/bc_card_lift_per_class.json` |
| Análise divergência DF (raw) | `experiments/phase_j_interpretability/df_divergence_features.json` |
| Análise divergência BC (raw) | `experiments/phase_j_interpretability/bc_divergence_cards.json` |
| Este relatório | `documents/reports/results/phase_j_interpretability.md` |

