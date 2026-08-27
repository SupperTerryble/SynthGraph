# Voies de synthèse extraites automatiquement

Ce document présente les voies de synthèse extraites des publications par
**Qwen3-8B** en architecture tool-calling, et les confronte au gold annoté
manuellement. Chaque valeur est accompagnée de **la citation qui la prouve** :
c'est cette citation qui démontre l'extraction, non le chiffre seul.

Aucune valeur ne peut entrer dans le graphe sans une citation du papier qui la
contienne — les valeurs marquées « déduit » proviennent d'un post-traitement
déterministe (en-tête de tableau, ordre d'énumération, citation), jamais d'une
supposition du modèle.


# Sung et al., Philosophical Magazine

**Matériau visé** : Sr2IrO4 (+ Sr3Ir2O7, intercroissances)  
**Méthode** : croissance en flux (flux method)  
**Voies extraites** : 10

## Référence annotée à la main

| Précurseur | Ratio molaire | Rôle |
|---|---|---|
| `IrO2` | 1 | reactant |
| `SrCO3` | 2 | reactant |
| `SrCl2·6H2O` | 7 | flux |

**Atmosphère** : air  
**Contenant** : creuset de platine couvert d'un couvercle  
**Traitement final** : rinçage à l'eau distillée pour séparer le flux résiduel  

## Voie extraite — Sr214#1

### Précurseurs

| Composé | Ratio | Provenance | Citation qui le prouve |
|---|---|---|---|
| `IrO2` | 1 | cité par le modèle | Sr2IrO4−d samples IrO2 : SrCO3 : SrCl2 Furnace sequence Chemical composition (EDX) Sr214#1 1 : 2 : 7 1300◦C → (8◦C/h) 900◦C → RT Sr2.08IrO3.96 |
| `SrCO3` | 2 | cité par le modèle | Powders of IrO2, SrCO3, and SrCl2 · 6H2O were thoroughly mixed and placed in a platinum crucible covered with a lid. |
| `SrCl2` | 7 | cité par le modèle | Sr2IrO4−d samples IrO2 : SrCO3 : SrCl2 Furnace sequence Chemical composition (EDX) Sr214#1 1 : 2 : 7 1300◦C → (8◦C/h) 900◦C → RT Sr2.08IrO3.96 |

### Séquence opératoire

| # | Opération | Paramètres prouvés | Citation |
|---|---|---|---|
| 1 | **mixing** | `contenant` = **platinum crucible** | Powders of IrO2,SrCO3, and SrCl2 · 6H2O were thoroughly mixed and placed in a platinum crucible covered with a lid. |
| 2 | **heating** | `target_temperature_c` = **1300**, `atmosphere` = **air**, `equipment` = **platinum crucible**, `max_temperature_c` = **1300**, `contenant` = **platinum crucible** | Sr214#1 1 : 2 : 7 1300◦C → (8◦C/h) 900◦C → RT |
| 3 | **cooling** | `target_temperature_c` = **900**, `cooling_rate_c_per_h` = **8**, `atmosphere` = **air**, `equipment` = **platinum crucible**, `max_temperature_c` = **900**, `contenant` = **platinum crucible** | Sr214#1 1 : 2 : 7 1300◦C → (8◦C/h) 900◦C → RT |
| 4 | **separation** | `solvent` = **distilled water** | After cooling, crystals were separated from the residual ﬂux by rinsing out with distilled water. |

> **Confrontation au gold** — Tous les précurseurs de la référence sont présents.

## Voie extraite — Sr214#2

### Précurseurs

| Composé | Ratio | Provenance | Citation qui le prouve |
|---|---|---|---|
| `IrO2` | 1 | déduit de l'en-tête du tableau | Powders of IrO2, SrCO3, and SrCl2 · 6H2O were thoroughly mixed and placed in a platinum crucible covered with a lid. |
| `SrCO3` | 2 | cité par le modèle | Powders of IrO2, SrCO3, and SrCl2 · 6H2O were thoroughly mixed and placed in a platinum crucible covered with a lid. |
| `SrCl2·6H2O` | 7 | déduit de l'en-tête du tableau | Powders of IrO2, SrCO3, and SrCl2 · 6H2O were thoroughly mixed and placed in a platinum crucible covered with a lid. |

### Séquence opératoire

| # | Opération | Paramètres prouvés | Citation |
|---|---|---|---|
| 1 | **mixing** | `contenant` = **platinum crucible** | Powders of IrO2,SrCO3, and SrCl2 · 6H2O were thoroughly mixed and placed in a platinum crucible covered with a lid. |
| 2 | **heating** | `target_temperature_c` = **1100**, `ramp_rate_c_per_h` = **45**, `atmosphere` = **air**, `equipment` = **platinum crucible**, `max_temperature_c` = **1100**, `contenant` = **platinum crucible** | Sr214#2 1 : 2 : 7 1100◦C → (45◦C/h) 1300◦C → (8◦C/h) 900◦C → RT |
| 3 | **heating** | `target_temperature_c` = **1300**, `ramp_rate_c_per_h` = **45**, `atmosphere` = **air**, `equipment` = **platinum crucible**, `max_temperature_c` = **1300**, `contenant` = **platinum crucible** | Sr214#2 1 : 2 : 7 1100◦C → (45◦C/h) 1300◦C → (8◦C/h) 900◦C → RT |
| 4 | **heating** | `target_temperature_c` = **900**, `ramp_rate_c_per_h` = **8**, `atmosphere` = **air**, `equipment` = **platinum crucible**, `max_temperature_c` = **900**, `contenant` = **platinum crucible** | Sr214#2 1 : 2 : 7 1100◦C → (45◦C/h) 1300◦C → (8◦C/h) 900◦C → RT |
| 5 | **separation** | `solvent` = **distilled water** | After cooling, crystals were separated from the residual ﬂux by rinsing out with distilled water. |

> **Confrontation au gold** — Tous les précurseurs de la référence sont présents.

## Voie extraite — Sr214#3

### Précurseurs

| Composé | Ratio | Provenance | Citation qui le prouve |
|---|---|---|---|
| `IrO2` | 1 | déduit de l'en-tête du tableau | Powders of IrO2, SrCO3, and SrCl2 · 6H2O were thoroughly mixed |
| `SrCO3` | 2 | cité par le modèle | Powders of IrO2, SrCO3, and SrCl2 · 6H2O were thoroughly mixed |
| `SrCl2·6H2O` | 7 | déduit de l'en-tête du tableau | Powders of IrO2, SrCO3, and SrCl2 · 6H2O were thoroughly mixed |

### Séquence opératoire

| # | Opération | Paramètres prouvés | Citation |
|---|---|---|---|
| 1 | **mixing** | `contenant` = **platinum crucible** | Powders of IrO2,SrCO3, and SrCl2 · 6H2O were thoroughly mixed and placed in a platinum crucible covered with a lid. |
| 2 | **heating** | `target_temperature_c` = **1300**, `duration_h` = **24**, `atmosphere` = **air**, `equipment` = **platinum crucible**, `max_temperature_c` = **1300**, `contenant` = **platinum crucible** | Sr214#3 1 : 2 : 7 1300◦C (24h dwell) → (8◦C/h) 1100◦C → Quench |
| 3 | **cooling** | `target_temperature_c` = **1100**, `cooling_rate_c_per_h` = **8**, `atmosphere` = **air**, `equipment` = **platinum crucible**, `max_temperature_c` = **1100**, `contenant` = **platinum crucible** | Sr214#3 1 : 2 : 7 1300◦C (24h dwell) → (8◦C/h) 1100◦C → Quench |
| 4 | **separation** | `solvent` = **distilled water** | After cooling, crystals were separated from the residual ﬂux by rinsing out with distilled water. |

> **Confrontation au gold** — Tous les précurseurs de la référence sont présents.

## Voie extraite — Sr214#4

### Précurseurs

| Composé | Ratio | Provenance | Citation qui le prouve |
|---|---|---|---|
| `IrO2` | 1 | cité par le modèle | Sr2IrO4−d samples IrO2 : SrCO3 : SrCl2 Furnace sequence Chemical composition (EDX) Sr214#1 1 : 2 : 7 1300◦C → (8◦C/h) 900◦C → RT |
| `SrCO3` | 2 | cité par le modèle | Sr2IrO4−d samples IrO2 : SrCO3 : SrCl2 Furnace sequence Chemical composition (EDX) Sr214#1 1 : 2 : 7 1300◦C → (8◦C/h) 900◦C → RT |
| `SrCl2` | 7 | cité par le modèle | Sr2IrO4−d samples IrO2 : SrCO3 : SrCl2 Furnace sequence Chemical composition (EDX) Sr214#1 1 : 2 : 7 1300◦C → (8◦C/h) 900◦C → RT |

### Séquence opératoire

| # | Opération | Paramètres prouvés | Citation |
|---|---|---|---|
| 1 | **mixing** | `contenant` = **platinum crucible** | Powders of IrO2,SrCO3, and SrCl2 · 6H2O were thoroughly mixed and placed in a platinum crucible covered with a lid. |
| 2 | **heating** | `target_temperature_c` = **1300**, `ramp_rate_c_per_h` = **8**, `duration_h` = **24**, `equipment` = **platinum crucible**, `max_temperature_c` = **1300**, `contenant` = **platinum crucible** | Sr214#4 1 : 2 : 7 1300◦C (24h dwell) → (8◦C/h) 1100◦C (100h dwell) → RT |
| 3 | **heating** | `atmosphere` = **air**, `equipment` = **platinum crucible**, `contenant` = **platinum crucible** | The crucibles were heated in a programmable box furnace in air then cooled to room temperature and removed from the furnace. |
| 4 | **cooling** | `target_temperature_c` = **1100**, `cooling_rate_c_per_h` = **8**, `atmosphere` = **air**, `equipment` = **platinum crucible**, `max_temperature_c` = **1100**, `contenant` = **platinum crucible** | Sr214#4 1 : 2 : 7 1300◦C (24h dwell) → (8◦C/h) 1100◦C (100h dwell) → RT |
| 5 | **cooling** | `atmosphere` = **air**, `equipment` = **platinum crucible**, `contenant` = **platinum crucible** | The crucibles were heated in a programmable box furnace in air then cooled to room temperature and removed from the furnace. |
| 6 | **separation** | `solvent` = **distilled water** | After cooling, crystals were separated from the residual ﬂux by rinsing out with distilled water. |

> **Confrontation au gold** — Tous les précurseurs de la référence sont présents.

## Voie extraite — Sr214−δ#1

### Précurseurs

| Composé | Ratio | Provenance | Citation qui le prouve |
|---|---|---|---|
| `IrO2` | 1 | déduit de l'en-tête du tableau | IrO2 : SrCO3 : SrCl2 |
| `SrCO3` | 2 | cité par le modèle | IrO2 : SrCO3 : SrCl2 |
| `SrCl2` | 7 | déduit de l'en-tête du tableau | IrO2 : SrCO3 : SrCl2 |

### Séquence opératoire

| # | Opération | Paramètres prouvés | Citation |
|---|---|---|---|
| 1 | **mixing** | `contenant` = **platinum crucible** | Powders of IrO2,SrCO3, and SrCl2 · 6H2O were thoroughly mixed and placed in a platinum crucible covered with a lid. |
| 2 | **heating** | `target_temperature_c` = **1300**, `duration_h` = **100**, `atmosphere` = **air**, `equipment` = **platinum crucible**, `max_temperature_c` = **1300**, `contenant` = **platinum crucible** | Sr214−δ#1 1 : 2 : 7 1300◦C (100h dwell) → RT Sr2.08IrO3.86 |
| 3 | **separation** | `solvent` = **distilled water** | After cooling, crystals were separated from the residual ﬂux by rinsing out with distilled water. |

> **Confrontation au gold** — Tous les précurseurs de la référence sont présents.

## Voie extraite — Sr214−δ#2

### Précurseurs

| Composé | Ratio | Provenance | Citation qui le prouve |
|---|---|---|---|
| `IrO2` | 1 | déduit de l'en-tête du tableau | Powders of IrO2, SrCO3, and SrCl2 · 6H2O were thoroughly mixed and placed in a platinum crucible covered with a lid. |
| `SrCO3` | 2 | déduit de l'en-tête du tableau | Powders of IrO2, SrCO3, and SrCl2 · 6H2O were thoroughly mixed and placed in a platinum crucible covered with a lid. |
| `SrCl2·6H2O` | 7 | déduit de l'en-tête du tableau | Powders of IrO2, SrCO3, and SrCl2 · 6H2O were thoroughly mixed and placed in a platinum crucible covered with a lid. |

### Séquence opératoire

| # | Opération | Paramètres prouvés | Citation |
|---|---|---|---|
| 1 | **mixing** | `contenant` = **platinum crucible** | Powders of IrO2,SrCO3, and SrCl2 · 6H2O were thoroughly mixed and placed in a platinum crucible covered with a lid. |
| 2 | **heating** | `target_temperature_c` = **1300**, `ramp_rate_c_per_h` = **8**, `atmosphere` = **air**, `equipment` = **platinum crucible**, `max_temperature_c` = **1300**, `contenant` = **platinum crucible** | Sr214−δ#2 1 : 1.8 : 7 1300◦C → (8◦C/h) 900◦C → RT Sr2.00IrO3.68 |
| 3 | **separation** | `solvent` = **distilled water** | After cooling, crystals were separated from the residual ﬂux by rinsing out with distilled water. |

> **Confrontation au gold** — Tous les précurseurs de la référence sont présents.

## Voie extraite — Sr214/Sr327#1

### Précurseurs

| Composé | Ratio | Provenance | Citation qui le prouve |
|---|---|---|---|
| `IrO2` | 1 | déduit de l'en-tête du tableau | Powders of IrO2, SrCO3, and SrCl2 · 6H2O were thoroughly mixed and placed in a platinum crucible covered with a lid. |
| `SrCO3` | 2 | cité par le modèle | Powders of IrO2, SrCO3, and SrCl2 · 6H2O were thoroughly mixed and placed in a platinum crucible covered with a lid. |
| `SrCl2·6H2O` | 7 | déduit de l'en-tête du tableau | Powders of IrO2, SrCO3, and SrCl2 · 6H2O were thoroughly mixed and placed in a platinum crucible covered with a lid. |

### Séquence opératoire

| # | Opération | Paramètres prouvés | Citation |
|---|---|---|---|
| 1 | **mixing** | `contenant` = **platinum crucible** | Powders of IrO2,SrCO3, and SrCl2 · 6H2O were thoroughly mixed and placed in a platinum crucible covered with a lid. |
| 2 | **heating** | `target_temperature_c` = **1150**, `ramp_rate_c_per_h` = **5**, `duration_h` = **12**, `atmosphere` = **air**, `equipment` = **platinum crucible**, `max_temperature_c` = **1150**, `contenant` = **platinum crucible** | Sr214/Sr327#1 1 : 2 : 7 1150◦C (12h dwell) → (5◦C/h) 880◦C → RT |
| 3 | **cooling** | `target_temperature_c` = **880**, `cooling_rate_c_per_h` = **5**, `atmosphere` = **air**, `equipment` = **platinum crucible**, `max_temperature_c` = **880**, `contenant` = **platinum crucible** | Sr214/Sr327#1 1 : 2 : 7 1150◦C (12h dwell) → (5◦C/h) 880◦C → RT |
| 4 | **separation** | `solvent` = **distilled water** | After cooling, crystals were separated from the residual ﬂux by rinsing out with distilled water. |

> **Confrontation au gold** — Tous les précurseurs de la référence sont présents.

## Voie extraite — Sr214/Sr327#2

### Précurseurs

| Composé | Ratio | Provenance | Citation qui le prouve |
|---|---|---|---|
| `IrO2` | 1 | déduit de l'en-tête du tableau | Powders of IrO2, SrCO3, and SrCl2 · 6H2O were thoroughly mixed and placed in a platinum crucible covered with a lid. |
| `SrCO3` | 2 | cité par le modèle | Powders of IrO2, SrCO3, and SrCl2 · 6H2O were thoroughly mixed and placed in a platinum crucible covered with a lid. |
| `SrCl2·6H2O` | 7 | déduit de l'en-tête du tableau | Powders of IrO2, SrCO3, and SrCl2 · 6H2O were thoroughly mixed and placed in a platinum crucible covered with a lid. |

### Séquence opératoire

| # | Opération | Paramètres prouvés | Citation |
|---|---|---|---|
| 1 | **mixing** | `contenant` = **platinum crucible** | Powders of IrO2,SrCO3, and SrCl2 · 6H2O were thoroughly mixed and placed in a platinum crucible covered with a lid. |
| 2 | **heating** | `target_temperature_c` = **1125**, `duration_h` = **12**, `atmosphere` = **air**, `equipment` = **platinum crucible**, `max_temperature_c` = **1125**, `contenant` = **platinum crucible** | Sr214/Sr327#2 1 : 2 : 7 1125◦C (12h dwell) → (5◦C/h) 880◦C → RT |
| 3 | **cooling** | `target_temperature_c` = **880**, `cooling_rate_c_per_h` = **5**, `atmosphere` = **air**, `equipment` = **platinum crucible**, `max_temperature_c` = **880**, `contenant` = **platinum crucible** | Sr214/Sr327#2 1 : 2 : 7 1125◦C (12h dwell) → (5◦C/h) 880◦C → RT |
| 4 | **separation** | `solvent` = **distilled water** | After cooling, crystals were separated from the residual ﬂux by rinsing out with distilled water. |

> **Confrontation au gold** — Tous les précurseurs de la référence sont présents.

## Voie extraite — Sr214/Sr327#3

### Précurseurs

| Composé | Ratio | Provenance | Citation qui le prouve |
|---|---|---|---|
| `IrO2` | 1 | déduit de l'en-tête du tableau | Powders of IrO2, SrCO3, and SrCl2 · 6H2O were thoroughly mixed and placed in a platinum crucible covered with a lid. |
| `SrCO3` | 2 | cité par le modèle | Powders of IrO2, SrCO3, and SrCl2 · 6H2O were thoroughly mixed and placed in a platinum crucible covered with a lid. |
| `SrCl2·6H2O` | 7 | déduit de l'en-tête du tableau | Powders of IrO2, SrCO3, and SrCl2 · 6H2O were thoroughly mixed and placed in a platinum crucible covered with a lid. |

### Séquence opératoire

| # | Opération | Paramètres prouvés | Citation |
|---|---|---|---|
| 1 | **mixing** | `contenant` = **platinum crucible** | Powders of IrO2,SrCO3, and SrCl2 · 6H2O were thoroughly mixed and placed in a platinum crucible covered with a lid. |
| 2 | **heating** | `target_temperature_c` = **1050**, `ramp_rate_c_per_h` = **5**, `duration_h` = **12**, `atmosphere` = **air**, `equipment` = **platinum crucible**, `max_temperature_c` = **1050**, `contenant` = **platinum crucible** | Sr214/Sr327#3 1 : 2 : 7 1050◦C (12h dwell) → (5◦C/h) 880◦C → RT |
| 3 | **cooling** | `target_temperature_c` = **880**, `cooling_rate_c_per_h` = **5**, `atmosphere` = **air**, `equipment` = **platinum crucible**, `max_temperature_c` = **880**, `contenant` = **platinum crucible** | Sr214/Sr327#3 1 : 2 : 7 1050◦C (12h dwell) → (5◦C/h) 880◦C → RT |
| 4 | **separation** | `solvent` = **distilled water** | After cooling, crystals were separated from the residual ﬂux by rinsing out with distilled water. |

> **Confrontation au gold** — Tous les précurseurs de la référence sont présents.

## Voie extraite — Sr327

### Précurseurs

| Composé | Ratio | Provenance | Citation qui le prouve |
|---|---|---|---|
| `IrO2` | 2 | cité par le modèle | Powders of IrO2, SrCO3, and SrCl2 · 6H2O were thoroughly mixed and placed in a platinum crucible covered with a lid. |
| `SrCO3` | 3 | cité par le modèle | Powders of IrO2, SrCO3, and SrCl2 · 6H2O were thoroughly mixed and placed in a platinum crucible covered with a lid. |
| `SrCl2·6H2O` | — | — | Powders of IrO2, SrCO3, and SrCl2 · 6H2O were thoroughly mixed and placed in a platinum crucible covered with a lid. |

### Séquence opératoire

| # | Opération | Paramètres prouvés | Citation |
|---|---|---|---|
| 1 | **mixing** | `contenant` = **platinum crucible** | Powders of IrO2,SrCO3, and SrCl2 · 6H2O were thoroughly mixed and placed in a platinum crucible covered with a lid. |
| 2 | **heating** | `target_temperature_c` = **1050**, `ramp_rate_c_per_h` = **5**, `duration_h` = **36**, `atmosphere` = **air**, `equipment` = **platinum crucible**, `max_temperature_c` = **1050**, `contenant` = **platinum crucible** | Sr327 2 : 3 : 7 1050 ◦C (36h dwell) → (5 ◦C/h) 750 ◦C → RT |
| 3 | **separation** | `solvent` = **distilled water** | After cooling, crystals were separated from the residual ﬂux by rinsing out with distilled water. |

> **Confrontation au gold** — Tous les précurseurs de la référence sont présents.


# Crawford et al., Phys. Rev. B 49, 11890 (1994)

**Matériau visé** : Sr2Ir(1-x)Ru(x)O4 (solution solide)  
**Méthode** : réaction à l'état solide (céramique)  
**Voies extraites** : 1

## Référence annotée à la main

| Précurseur | Ratio molaire | Rôle |
|---|---|---|
| `SrCO3` | — | reactant |
| `IrO2` | — | reactant |
| `RuO2` | — | reactant |

**Atmosphère** : O2 en flux (flowing O2)  

## Voie extraite — voie 1 sur 1

### Précurseurs

| Composé | Ratio | Provenance | Citation qui le prouve |
|---|---|---|---|
| `SrCO3` | — | — | Starting materials SrCO3, Ir02, and Ru02 were mixed in proportions to span the solid-solution series and heated in flowing 02. |
| `IrO2` | — | — | Starting materials SrCO3, Ir02, and Ru02 were mixed in proportions to span the solid-solution series and heated in flowing 02. |
| `RuO2` | — | — | Starting materials SrCO3, Ir02, and Ru02 were mixed in proportions to span the solid-solution series and heated in flowing 02. |

### Séquence opératoire

| # | Opération | Paramètres prouvés | Citation |
|---|---|---|---|
| 1 | **mixing** | `atmosphere` = **O2** | Starting materials SrCO3, Ir02, and Ru02 were mixed in proportions to span the solid-solution series and heated in flowing 02. |
| 2 | **heating** | `target_temperature_c` = **900**, `duration_h` = **24**, `atmosphere` = **O2**, `max_temperature_c` = **900** | Typical heating schedules were 900'C, 24 h; 1000'C, 60 h; and 1100'C, 60 h, with many intermediate grindings. |
| 3 | **grinding** | `atmosphere` = **O2** | Typical heating schedules were 900'C, 24 h; 1000'C, 60 h; and 1100'C, 60 h, with many intermediate grindings. |
| 4 | **heating** | `target_temperature_c` = **1000**, `duration_h` = **60**, `atmosphere` = **O2**, `max_temperature_c` = **1000** | Typical heating schedules were 900'C, 24 h; 1000'C, 60 h; and 1100'C, 60 h, with many intermediate grindings. |
| 6 | **heating** | `target_temperature_c` = **1100**, `duration_h` = **60**, `atmosphere` = **O2**, `max_temperature_c` = **1100** | Typical heating schedules were 900'C, 24 h; 1000'C, 60 h; and 1100'C, 60 h, with many intermediate grindings. |

> **Confrontation au gold** — Tous les précurseurs de la référence sont présents.


# Randall, Katz & Ward, JACS 79 (1957)

**Matériau visé** : Sr2IrO4  
**Méthode** : réaction à l'état solide  
**Voies extraites** : 1

## Référence annotée à la main

| Précurseur | Ratio molaire | Rôle |
|---|---|---|
| `Ir` | — | reactant |
| `SrO` | — | reactant |
| `SrCO3` | — | reactant |
| `Sr(NO3)2` | — | reactant |
| `Sr(OH)2` | — | reactant |

**Atmosphère** : air  
**Contenant** : nacelle de platine ou de silicate de zirconium  

## Voie extraite — voie 1 sur 1

### Précurseurs

| Composé | Ratio | Provenance | Citation qui le prouve |
|---|---|---|---|
| `Ir` | — | — | Strontium-iridium oxide is obtained readily by the reaction between iridium metal powder and strontium oxide, carbonate, nitrate or hydroxide at 1200° |
| `SrO` | — | — | Strontium-iridium oxide is obtained readily by the reaction between iridium metal powder and strontium oxide, carbonate, nitrate or hydroxide at 1200° |
| `SrCO3` | — | — | Strontium-iridium oxide is obtained readily by the reaction between iridium metal powder and strontium oxide, carbonate, nitrate or hydroxide at 1200° |
| `Sr(NO3)2` | — | — | Strontium-iridium oxide is obtained readily by the reaction between iridium metal powder and strontium oxide, carbonate, nitrate or hydroxide at 1200° |
| `Sr(OH)2` | — | — | Strontium-iridium oxide is obtained readily by the reaction between iridium metal powder and strontium oxide, carbonate, nitrate or hydroxide at 1200° |

### Séquence opératoire

| # | Opération | Paramètres prouvés | Citation |
|---|---|---|---|
| 1 | **mixing** | `contenant` = **platinum or zirconium silicate combustion boats** | ![image 2](<the-preparation-of-a-strontium-iridium-oxide-sr2iro41-2 (1)_images/imageFile2.png>)

atomic ratio were used, some iridium remained dispers |
| 2 | **heating** | `target_temperature_c` = **1200**, `atmosphere` = **air**, `equipment` = **platinum or zirconium silicate combustion boats**, `max_temperature_c` = **1200**, `contenant` = **platinum or zirconium silicate combustion boats** | Strontium-iridium oxide is obtained readily by the reaction between iridium metal powder and strontium oxide, carbonate, nitrate or hydroxide at 1200° |
| 3 | **grinding** | `duration_h` = **0.25**, `equipment` = **platinum or zirconium silicate combustion boats**, `atmosphere` = **air**, `contenant` = **platinum or zirconium silicate combustion boats** | The reaction occurs rapidly compared with most solid phase reactions, a pure product being obtained upon heating for 15 min., regrinding the sample an |
| 4 | **heating** | `duration_h` = **0.25**, `atmosphere` = **air**, `equipment` = **platinum or zirconium silicate combustion boats**, `contenant` = **platinum or zirconium silicate combustion boats** | The reaction occurs rapidly compared with most solid phase reactions, a pure product being obtained upon heating for 15 min., regrinding the sample an |
| 5 | **cooling** | `atmosphere` = **air**, `contenant` = **platinum or zirconium silicate combustion boats** | The furnace was then cooled, nitric oxide removed from the system, and the reaction chamber removed for extraction of the sodium nitrite with dry meth |

> **Confrontation au gold** — Tous les précurseurs de la référence sont présents.


# Xia et al., Nanoscale Res. Lett. 9 (2014) — hydrothermale, Cu2ZnSnS4

**Matériau visé** : Cu2ZnSnS4 (kesterite)  
**Méthode** : hydrothermale (eau, bombe de digestion)  
**Voies extraites** : 1

## Référence annotée à la main

| Précurseur | Ratio molaire | Rôle |
|---|---|---|
| `CuCl2·2H2O` | 2 | reactant |
| `ZnCl2` | 2 | reactant |
| `SnCl2·2H2O` | 1 | reactant |
| `C3H7NO2S` | 4 | reactant |
| `C10H16N2O8` | 2 | additive |
| `H2O` | None | solvent |

**Atmosphère** : autogene (bombe fermee) — non precisee dans le texte  
**Contenant** : bombe de digestion acide de 50 ml, etuve electrique  
**Traitement final** : filtration puis lavage a l'ethanol 30 % et 80 %  

## Voie extraite — voie 1 sur 1

### Précurseurs

| Composé | Ratio | Provenance | Citation qui le prouve |
|---|---|---|---|
| `CuCl2·2H2O` | 2 | déduit des quantités molaires citées | CuCl2 · 2H2O, ZnCl2, SnCl2 · 2H2O, L-cysteine, and EDTA were of analytical grade and used as received without further purification. |
| `ZnCl2` | 2 | déduit des quantités molaires citées | CuCl2 · 2H2O, ZnCl2, SnCl2 · 2H2O, L-cysteine, and EDTA were of analytical grade and used as received without further purification. |
| `SnCl2·2H2O` | 1 | déduit des quantités molaires citées | CuCl2 · 2H2O, ZnCl2, SnCl2 · 2H2O, L-cysteine, and EDTA were of analytical grade and used as received without further purification. |
| `L-cysteine` | 4 | déduit des quantités molaires citées | CuCl2 · 2H2O, ZnCl2, SnCl2 · 2H2O, L-cysteine, and EDTA were of analytical grade and used as received without further purification. |
| `EDTA` | — | — | CuCl2 · 2H2O, ZnCl2, SnCl2 · 2H2O, L-cysteine, and EDTA were of analytical grade and used as received without further purification. |
| `H2O` | — | — | In a typical synthesis, 2 mmol CuCl2 · 2H2O, 2 mmol of ZnCl2, 1 mmol of SnCl2 · 2H2O, 4 mmol of L-cysteine, and 0 to 3 mmol of EDTA were dispersed in  |

### Séquence opératoire

| # | Opération | Paramètres prouvés | Citation |
|---|---|---|---|
| 1 | **mixing** | `duration_h` = **0.0833**, `contenant` = **acid digestion bomb** | In a typical synthesis, 2 mmol CuCl2 · 2H2O, 2 mmol of ZnCl2, 1 mmol of SnCl2 · 2H2O, 4 mmol of L-cysteine, and 0 to 3 mmol of EDTA were dispersed in  |
| 2 | **generic** | `duration_h` = **0.0833**, `equipment` = **acid digestion bomb (50 ml)**, `contenant` = **acid digestion bomb** | In a typical synthesis, 2 mmol CuCl2 · 2H2O, 2 mmol of ZnCl2, 1 mmol of SnCl2 · 2H2O, 4 mmol of L-cysteine, and 0 to 3 mmol of EDTA were dispersed in  |
| 3 | **heating** | `target_temperature_c` = **180**, `duration_h` = **12**, `equipment` = **electric oven**, `max_temperature_c` = **190**, `min_temperature_c` = **170**, `deterministic_fills` = **[{'parameter': 'min_temperature_c/max_temperature_c', 'value': [170.0, 190.0], 'source': 'citation_range_regex'}, {'parameter': 'min_duration_h/max_duration_h', 'value': [6.0, 16.0], 'source': 'citation_range_regex'}]**, `min_duration_h` = **6**, `max_duration_h` = **16**, `condition_citation` = **Pure kesterite Cu2ZnSnS4 has been synthesized at 180°C for 12 h from the reaction system cont**, `condition_source` = **optimum_du_papier**, `contenant` = **acid digestion bomb** | The hydrothermal synthesis was conducted at 170°C to 190°C for 6 to 16 h in an electric oven |
| 4 | **cooling** | `equipment` = **acid digestion bomb**, `contenant` = **acid digestion bomb** | After synthesis, the bomb was cooled down naturally to room temperature |
| 5 | **washing** | `solvent` = **30% and 80% ethanol** | The final product was filtrated and washed with 30% and 80% ethanol |
| 6 | **drying** | `temperature_c` = **60**, `atmosphere` = **vacuum**, `equipment` = **vacuum oven** | followed by drying at 60°C in a vacuum oven |

> **Confrontation au gold** — Tous les précurseurs de la référence sont présents.


# Dorner et al., Sci. Rep. 9 (2019) — sol-gel, CuO poreux

**Matériau visé** : CuO nanoparticulaire poreux (via precurseur malachite CuCO3·Cu(OH)2)  
**Méthode** : sol-gel (co-precipitation) + calcination  
**Voies extraites** : 1

## Référence annotée à la main

| Précurseur | Ratio molaire | Rôle |
|---|---|---|
| `Cu(CH3COO)2` | 1 | reactant |
| `(NH4)2CO3` | 1.029 | reactant |

**Atmosphère** : air  
**Contenant** : four a moufle  
**Traitement final** : centrifugation puis lavage a l'ethanol et a l'eau distillee  

## Voie extraite — voie 1 sur 1

### Précurseurs

| Composé | Ratio | Provenance | Citation qui le prouve |
|---|---|---|---|
| `Cu(C2H3O2)2` | — | — | stoichiometric amounts of fresh aqueous 15 mM copper acetate (Sigma Aldrich) and 15 mM ammonia carbonate (Alfa Aesar) solutions |
| `(NH4)2CO3` | — | — | stoichiometric amounts of fresh aqueous 15 mM copper acetate (Sigma Aldrich) and 15 mM ammonia carbonate (Alfa Aesar) solutions |
| `C2H5OH` | — | — | washed with ethanol and distilled water |

### Séquence opératoire

| # | Opération | Paramètres prouvés | Citation |
|---|---|---|---|
| 1 | **mixing** | `duration_h` = **2** | mixing stoichiometric amounts of fresh aqueous 15 mM copper acetate (Sigma Aldrich) and 15 mM ammonia carbonate (Alfa Aesar) solutions at room tempera |
| 2 | **centrifugation** | _aucun paramètre prouvé_ | the gel precipitate was collected by centrifugation |
| 3 | **washing** | `solvent` = **ethanol and distilled water** | washed with ethanol and distilled water |
| 4 | **drying** | `temperature_c` = **60**, `duration_h` = **6**, `atmosphere` = **air**, `equipment` = **muffle furnace** | dried in a muffle furnace in air at a temperature of 60 °C for a fixed duration of tdrying = 6 h |
| 5 | **calcination** | `temperature_c` = **400**, `duration_h` = **4**, `atmosphere` = **air**, `equipment` = **muffle furnace**, `max_temperature_c` = **400** | annealing in a muffle furnace in air at 400 °C for a fixed duration of tcalcination = 4 h |

> **Confrontation au gold** — Tous les précurseurs de la référence sont présents.


# Batoo & Ansari, Nanoscale Res. Lett. 7 (2012) — auto-combustion, ferrite Ni-Cu-Zn

**Matériau visé** : Ni(0.7-x)ZnxCu0.3Fe2O4 (0 <= x <= 0.2, pas de 0.05)  
**Méthode** : auto-combustion (sol-gel combustion) + calcination  
**Voies extraites** : 1

## Référence annotée à la main

| Précurseur | Ratio molaire | Rôle |
|---|---|---|
| `Ni(NO3)2·6H2O` | None | reactant |
| `CuCl` | None | reactant |
| `Zn(NO3)2·6H2O` | None | reactant |
| `Fe(NO3)2·9H2O` | None | reactant |
| `H2O` | None | solvent |
| `C2H5OH` | None | additive |

**Atmosphère** : non precisee dans le texte (aucune mention d'atmosphere ; « air » etait une inference de l'annotateur a partir du caractere auto-propage de la combustion)  
**Contenant** : agitateur magnetique puis four  

## Voie extraite — v1

### Précurseurs

| Composé | Ratio | Provenance | Citation qui le prouve |
|---|---|---|---|
| `Ni(NO3)2.6H2O` | — | — | ‘AR’ grade Ni(NO3)2.6H2O, CuCl, Zn(NO3)2.6H2O, and Fe(NO3)2.9H2O as raw materials |
| `CuCl` | — | — | ‘AR’ grade Ni(NO3)2.6H2O, CuCl, Zn(NO3)2.6H2O, and Fe(NO3)2.9H2O as raw materials |
| `Zn(NO3)2.6H2O` | — | — | ‘AR’ grade Ni(NO3)2.6H2O, CuCl, Zn(NO3)2.6H2O, and Fe(NO3)2.9H2O as raw materials |
| `Fe(NO3)2.9H2O` | — | — | ‘AR’ grade Ni(NO3)2.6H2O, CuCl, Zn(NO3)2.6H2O, and Fe(NO3)2.9H2O as raw materials |
| `deionized water` | — | — | The stoichiometric mixtures of the mentioned materials were dissolved in deionized water, and few drops of ethyl alcohol were added to it |
| `ethyl alcohol` | — | — | The stoichiometric mixtures of the mentioned materials were dissolved in deionized water, and few drops of ethyl alcohol were added to it |

### Séquence opératoire

| # | Opération | Paramètres prouvés | Citation |
|---|---|---|---|
| 1 | **mixing** | `equipment` = **magnetic stirrer** | The stoichiometric mixtures of the mentioned materials were dissolved in deionized water, and few drops of ethyl alcohol were added to it |
| 2 | **generic** | `temperature_c` = **65**, `equipment` = **magnetic stirrer** | The solution was allowed for gel formation on the magnetic stirrer at 65°C with constant stirring |
| 3 | **annealing** | `temperature_c` = **200**, `duration_h` = **24**, `max_temperature_c` = **200** | annealed at 200°C for 24 h |
| 4 | **grinding** | `duration_h` = **0.5** | followed by grinding for 0.5 h |
| 5 | **generic** | _aucun paramètre prouvé_ | The dried gel was allowed to burn in a self-propagating combustion manner until the whole gel was completely burnt out to form a fluffy loose powder |
| 6 | **calcination** | `temperature_c` = **600**, `duration_h` = **4**, `ramp_rate_c_per_h` = **5**, `max_temperature_c` = **600** | heated for 4 h at 600°C to remove any organic material present while maintaining the rate of heating and cooling at 5°C/min |
| 7 | **calcination** | `temperature_c` = **600**, `duration_h` = **4**, `ramp_rate_c_per_h` = **5**, `max_temperature_c` = **600** | heated for 4 h at 600°C to remove any organic material present while maintaining the rate of heating and cooling at 5°C/min and then finally ground fo |
| 8 | **calcination** | `temperature_c` = **600**, `duration_h` = **4**, `ramp_rate_c_per_h` = **5**, `max_temperature_c` = **600** | The formed powder was heated for 4 h at 600°C to remove any organic material present while maintaining the rate of heating and cooling at 5°C/min and  |

> **Confrontation au gold** — Tous les précurseurs de la référence sont présents.


# Kariper, Materials Research (2018) — bain chimique, MnSe

**Matériau visé** : MnSe couche mince  
**Méthode** : depot par bain chimique (CBD)  
**Voies extraites** : 1

## Référence annotée à la main

| Précurseur | Ratio molaire | Rôle |
|---|---|---|
| `Mn(NO3)2` | None | reactant |
| `Se` | None | reactant |
| `KOH` | None | reactant |
| `LiAlH4` | None | reactant |
| `C4H8O2` | None | solvent |
| `C6H15NO3` | None | additive |
| `HCl` | None | additive |
| `H2O` | None | solvent |

**Atmosphère** : non precisee dans le texte (bain ouvert presume, mais aucune mention)  
**Contenant** : becher (bain chimique)  
**Traitement final** : filtration de la source Se avant ajout au bain  

## Voie extraite — voie 1 sur 1

### Précurseurs

| Composé | Ratio | Provenance | Citation qui le prouve |
|---|---|---|---|
| `Se` | 1 | cité par le modèle | Twenty milliliters concentrate 1-4 dioxane and 0.01 mol solid selenium are added to a beaker with 0.01 mol KOH. |
| `KOH` | 1 | cité par le modèle | Twenty milliliters concentrate 1-4 dioxane and 0.01 mol solid selenium are added to a beaker with 0.01 mol KOH. |
| `LiAlH4` | — | — | 0.01 mol LiAlH4 is added immediately to the beaker before the gel cools. |
| `Mn(NO3)2` | 0.001 | cité par le modèle | components of the baths were 8 % HCl, 5 mL 0.001 M manganese nitrate, 5 mL of the prepared Se source solution, and 5 mL triethanolamine (TEA). |
| `TEA` | — | — | components of the baths were 8 % HCl, 5 mL 0.001 M manganese nitrate, 5 mL of the prepared Se source solution, and 5 mL triethanolamine (TEA). |
| `HCl` | — | — | components of the baths were 8 % HCl, 5 mL 0.001 M manganese nitrate, 5 mL of the prepared Se source solution, and 5 mL triethanolamine (TEA). |
| `C4H8O2` | — | — | Twenty milliliters concentrate 1-4 dioxane and 0.01 mol solid selenium are added to a beaker with 0.01 mol KOH. |
| `H2O` | — | — | The solution is mixed at 1000 rpm and is completed with distilled water to 100 mL. |

### Séquence opératoire

| # | Opération | Paramètres prouvés | Citation |
|---|---|---|---|
| 1 | **mixing** | `contenant` = **beaker** | The solution is mixed at 1000 rpm and is completed with distilled water to 100 mL. |
| 2 | **heating** | `target_temperature_c` = **80**, `equipment` = **beaker**, `max_temperature_c` = **80**, `contenant` = **beaker** | Twenty milliliters concentrate 1-4 dioxane and 0.01 mol solid selenium are added to a beaker with 0.01 mol KOH. The mixture is heated at 80 ºC until t |
| 3 | **generic** | `equipment` = **beaker**, `contenant` = **beaker** | 0.01 mol LiAlH4 is added immediately to the beaker before the gel cools. |
| 4 | **generic** | `equipment` = **beaker**, `contenant` = **beaker** | Distilled water is added then slowly to the beaker. The solution is mixed at 1000 rpm and is completed with distilled water to 100 mL. |
| 5 | **soak** | `temperature_c` = **50**, `duration_h` = **3**, `equipment` = **beaker**, `max_temperature_c` = **50**, `contenant` = **beaker** | The bath remained for 3 hours at 50 ºC. |
| 6 | **separation** | _aucun paramètre prouvé_ | The mixture is filtered before being added to the chemical bath. |

> **Confrontation au gold** — Tous les précurseurs de la référence sont présents.


# Khan et al., Int. Nano Lett. 6 (2016) — reduction chimique, Cu

**Matériau visé** : nanoparticules de Cu (avec Cu2O)  
**Méthode** : reduction chimique en milieu aqueux  
**Voies extraites** : 1

## Référence annotée à la main

| Précurseur | Ratio molaire | Rôle |
|---|---|---|
| `CuSO4·5H2O` | None | reactant |
| `C6H10O5` | None | additive |
| `C6H8O6` | None | reactant |
| `NaOH` | None | additive |
| `H2O` | None | solvent |

**Atmosphère** : non precisee explicitement : les auteurs revendiquent « ambient atmospheric pressure without inert gas protection » — une pression et une NEGATION, pas une atmosphere nommee  
**Contenant** : NON PRECISE dans le texte : le recipient de reaction n'est jamais nomme. Le seul contenant cite est un « glass vial », et il sert au STOCKAGE apres sechage, pas a la synthese.  
**Traitement final** : filtration puis trois lavages a l'eau deionisee et a l'ethanol  

## Voie extraite — voie 1 sur 1

### Précurseurs

| Composé | Ratio | Provenance | Citation qui le prouve |
|---|---|---|---|
| `CuSO4·5H2O` | — | — | Copper sulphate pentahydrate CuSO4 5H2O (0.1 M) |
| `(C6H10O5)n` | 1 | cité par le modèle | Starch (C6H10O5) n (1.2 %) |
| `C6H8O6` | — | — | Ascorbic acid C6H8O6 (0.2 M) |
| `NaOH` | 1 | cité par le modèle | Sodium hydroxide NaOH (1 M) |
| `H2O` | — | — | De-ionized water was used for all the experiment. |

### Séquence opératoire

| # | Opération | Paramètres prouvés | Citation |
|---|---|---|---|
| 1 | **mixing** | `duration_h` = **0.5** | The preparation method starts with addition of 0.1 M copper (II) sulfate pentahydrate solution into 120 mL of starch (1.2 %) solution with vigorous st |
| 2 | **generic** | _aucun paramètre prouvé_ | In the second step, 50 mL of 0.2 M ascorbic acid solution is added to synthesis solution under continuous rapid stirring. |
| 3 | **heating** | `target_temperature_c` = **80**, `duration_h` = **2**, `max_temperature_c` = **80** | Subsequently, 30 mL of 1 M sodium hydroxide solution was slowly added to the prepared solution with constant stirring and heating at 80 C for 2 h. |
| 4 | **cooling** | _aucun paramètre prouvé_ | After the completion of reaction, the solution was taken from the heat and allowed to settle overnight |
| 5 | **generic** | _aucun paramètre prouvé_ | allowed to settle overnight |
| 6 | **washing** | `solvent` = **deionized water and ethanol**, `repetitions` = **3** | washed with deionized water and ethanol for three times to take out the excessive starch bound with the nanoparticles |
| 7 | **drying** | _aucun paramètre prouvé_ | dried at room temperature |

> **Confrontation au gold** — Tous les précurseurs de la référence sont présents.


# Zhu et al., npj 2D Mater. Appl. (2017) — CVD, MoS2

**Matériau visé** : MoS2 (mono- et few-layer, sur graphene)  
**Méthode** : depot chimique en phase vapeur (CVD)  
**Voies extraites** : 1

## Référence annotée à la main

| Précurseur | Ratio molaire | Rôle |
|---|---|---|
| `MoO2` | None | reactant |
| `S` | None | reactant |

**Atmosphère** : Ar 99,999 % (gaz vecteur), 200 sccm pour le few-layer et 500 sccm pour le monolayer  
**Contenant** : nacelle (boat) contenant le MoO2, dans un systeme CVD ; grilles MEB sur porte-echantillon ceramique, face vers le bas au-dessus de la nacelle  

## Voie extraite — voie 1 sur 1

### Précurseurs

| Composé | Ratio | Provenance | Citation qui le prouve |
|---|---|---|---|
| `MoO2` | — | — | MoO2 precursors (Sigma-Aldrich, 99%) |
| `S` | — | — | sulfur source (Aladdin, 99.999%) |
| `Ar` | — | — | argon (99.999%) was used as the carrier gas |

### Séquence opératoire

| # | Opération | Paramètres prouvés | Citation |
|---|---|---|---|
| 3 | **heating** | `target_temperature_c` = **750**, `duration_h` = **0.6667**, `equipment` = **furnace**, `max_temperature_c` = **750** | heated to 750 °C in 40 min |
| 4 | **soak** | `duration_h` = **0.4167**, `equipment` = **furnace** | kept for next 25 min |
| 5 | **heating** | `target_temperature_c` = **180**, `duration_h` = **0.0333**, `equipment` = **furnace**, `max_temperature_c` = **180** | heating of 300 mg of sulfur source... started, with its temperature reaching 180 °C in 2 min |
| 6 | **soak** | `duration_h` = **0.1667**, `equipment` = **furnace** | held for the next 10 min |

> **Confrontation au gold** — Tous les précurseurs de la référence sont présents.


# Xie et al., Appl. Surf. Sci. — electrodeposition en liquide ionique, Ni-Co

**Matériau visé** : alliage Ni-Co (48 at% Co) electrodepose sur verre FTO  
**Méthode** : electrodeposition en liquide ionique protique (EAN)  
**Voies extraites** : 1

## Référence annotée à la main

| Précurseur | Ratio molaire | Rôle |
|---|---|---|
| `CH3CH2NH2` | 1 | reactant |
| `HNO3` | 1 | reactant |
| `NiCl2` | None | reactant |
| `CoCl2` | None | reactant |

**Atmosphère** : argon barbote 15 min dans l'electrolyte ; electrodeposition en boite a gants, sans oxygene  
**Contenant** : cellule a trois electrodes (contre-electrode anneau de nickel 15 mm, electrode de travail FTO 0,5 x 0,5 cm, reference fil d'argent en double jonction), placee en BOITE A GANTS  
**Traitement final** : le substrat FTO est lave AVANT depot : acetone, ethanol, eau desionisee, 15 minutes chacun  

## Voie extraite — voie 1 sur 1

### Précurseurs

| Composé | Ratio | Provenance | Citation qui le prouve |
|---|---|---|---|
| `CH3CH2NH2` | 1 | cité par le modèle | Ethylamine (CH3CH2NH2, 70 wt.% in water, Acros Organics) |
| `HNO3` | 1 | cité par le modèle | Nitric acid (HNO3, 68 wt.% in water, AnalaR NORMAPUR) |
| `CoCl2` | — | — | cobalt chloride (CoCl2, 98% purity, Sigma-Aldrich) |
| `NiCl2` | — | — | nickel chloride (NiCl2, 98%, Sigma-Aldrich) |

### Séquence opératoire

| # | Opération | Paramètres prouvés | Citation |
|---|---|---|---|
| 1 | **mixing** | `temperature_c` = **-10** | Ethylammonium nitrate (EAN) was prepared by mixing ethylamine and nitric acid with a molar ratio of 1:1. During this process, the nitric acid was adde |
| 2 | **generic** | `temperature_c` = **-86** | The purification of EAN was performed by lyophilization (Freeze Dryer -86℃, OPERON CO., LTD.) in order to get EAN with a low water content (below 100  |
| 3 | **drying** | _aucun paramètre prouvé_ | The salts used for electrochemistry were dried by heating and lyophilization in order to reduce the amount of water in the electrolytes. |
| 4 | **generic** | `temperature_c` = **70**, `duration_h` = **24** | Solutions of 0.5 M NiCl2, 0.5 M CoCl2, - 0.25 M NiCl2 + 0.25 M CoCl2 and 0.375 M CoCl2 + 0.125 M NiCl2 in EAN were prepared by mixing the different co |
| 5 | **separation** | `solvent` = **acetone** | Fluorine-doped Tin Oxide glasses (FTO glass, from Solems, 80 nm thickness) (1.5 ×

0.5 × 0.1 cm3) were used as working electrode after washing in acet |

> **Confrontation au gold** — Tous les précurseurs de la référence sont présents.


# Nature Communications — mecanosynthese, Na3P

**Matériau visé** : Na3P (particules)  
**Méthode** : mecanosynthese (broyage a billes), a temperature ambiante  
**Voies extraites** : 1

## Référence annotée à la main

| Précurseur | Ratio molaire | Rôle |
|---|---|---|
| `Na` | 3 | reactant |
| `P` | 1 | reactant |

**Atmosphère** : boite a gants sous argon (chargement et broyage)  
**Contenant** : jarre en acier dur de 30 cm3 d'un broyeur Spex 8000M, chargee de sept billes d'acier dur de 7 g et 12 mm de diametre  

## Voie extraite — voie 1 sur 1

### Précurseurs

| Composé | Ratio | Provenance | Citation qui le prouve |
|---|---|---|---|
| `Na` | 3 | déduit de la formule cible énoncée | Stoichiometric amounts of metallic sodium as bulk (Sigma) and red phosphorus (Alfa, 325 mesh) were filled into a hard steel ball-milled jar (30 cm3) o |
| `P` | 1 | déduit de la formule cible énoncée | Stoichiometric amounts of metallic sodium as bulk (Sigma) and red phosphorus (Alfa, 325 mesh) were filled into a hard steel ball-milled jar (30 cm3) o |

### Séquence opératoire

| # | Opération | Paramètres prouvés | Citation |
|---|---|---|---|
| 1 | **grinding** | `duration_h` = **2**, `atmosphere` = **Ar** | These solid materials were ball-milled for 2 h to obtain Na3P particles. The mass ratio of balls to Na3P was maintained at 35. |

> **Confrontation au gold** — Tous les précurseurs de la référence sont présents.


# JACS — sels fondus LiI-KI, CoSi

**Matériau visé** : nanoparticules de CoSi (coeur-coquille a 300 °C, homogenes a 400 °C)  
**Méthode** : synthese en sels fondus, precedee d'un broyage a billes  
**Voies extraites** : 1

## Référence annotée à la main

| Précurseur | Ratio molaire | Rôle |
|---|---|---|
| `Si` | 2.3 | reactant |
| `CoCl2` | 1.5 | reactant |
| `LiI` | 0.63 | solvent |
| `KI` | 0.37 | solvent |
| `CH3OH` | None | solvent |

**Atmosphère** : vide dynamique 10-3 mbar pendant le traitement thermique et le refroidissement ; manipulation et stockage en boite a gants sous argon (H2O et O2 < 0,5 ppm)  
**Contenant** : broyage : jarre etanche de 50 mL d'un broyeur Retsch MM400, une bille d'acier de 62,3 g et 23 mm ; traitement thermique : tube de quartz (28 mm x 345 mm) sur rampe de Schlenk ; sechage : tube de Schlenk  
**Traitement final** : methanol, SEPT cycles de centrifugation/redispersion, puis sechage sous vide une nuit  

## Voie extraite — voie 1 sur 1

### Précurseurs

| Composé | Ratio | Provenance | Citation qui le prouve |
|---|---|---|---|
| `Si` | — | — | Silicon nanoparticles (99%, Nanomakers©, France) |
| `CoCl2` | 1 | cité par le modèle | 194.8 mg CoCl2 (1.5 mmol) |
| `LiI` | 0.63 | cité par le modèle | 2.9 g LiI (21.7 mmol) (molar ratio LiI:KI 0.63:0.37) |
| `KI` | 0.37 | cité par le modèle | 2.1 g KI (12.7 mmol) (molar ratio LiI:KI 0.63:0.37) |

### Séquence opératoire

| # | Opération | Paramètres prouvés | Citation |
|---|---|---|---|
| 1 | **grinding** | `duration_h` = **0.0333**, `equipment` = **airtight vial of 50 mL**, `frequency_hz` = **20**, `contenant` = **quartz tube** | 63.2 mg Si nanoparticles (2.3 mmol), 194.8 mg CoCl2 (1.5 mmol), 2.9 g LiI (21.7 mmol) and 2.1 g KI (12.7 mmol) (molar ratio LiI:KI 0.63:0.37) were bal |
| 2 | **generic** | `equipment` = **quartz tube (Ø28×H345mm)**, `contenant` = **quartz tube** | The mixture was loaded in a quartz tube (Ø28×H345mm) |
| 3 | **generic** | `duration_h` = **6**, `atmosphere` = **dynamic vacuum**, `equipment` = **vertical furnace from Eraly®**, `contenant` = **quartz tube** | Then, the quartz tube was put in the furnace, followed by 6 hours of thermal treatment under dynamic vacuum (10-3 mbar). |
| 4 | **cooling** | `atmosphere` = **vacuum**, `equipment` = **quartz tube**, `contenant` = **quartz tube** | Later, the hot quartz tube was taken out and cooled down to room temperature under vacuum. |
| 5 | **washing** | `solvent` = **methanol**, `repetitions` = **7** | The as-prepared mixture was washed in methanol by seven cycles of centrifugation/redispersion |
| 6 | **drying** | `atmosphere` = **vacuum**, `equipment` = **Schlenk tube** | and was later dried in a Schlenk tube under vacuum during the night |

> **Confrontation au gold** — **Manquant(s)** : `CH3OH`
