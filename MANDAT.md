# MANDAT — SynthGraph (Terry, 2026-08-18)

> **À lire au début de CHAQUE session.** Ce fichier fixe le but et les règles du
> jeu. Il prime sur toute habitude prise dans une session précédente.

## But

**Extraire les voies de synthèse de matériaux depuis des publications
scientifiques vers un graphe de connaissances**, avec une fiabilité suffisante
pour que la sortie serve elle-même de **référence (gold)** — sans annotation
humaine.

C'est un changement de nature : jusqu'ici le gold était annoté à la main et le
pipeline s'y comparait. L'objectif est désormais que **le pipeline PRODUISE ce
que le gold contient**.

## Règles de conduite

1. **Autonomie.** Décider et agir sans demander à chaque étape. Ne poser une
   question que si la décision engage Terry (suppression de données, changement
   de schéma du graphe, arbitrage de priorité) — et alors via `AskUserQuestion`.
2. **La QUALITÉ prime sur la vitesse.** Un modèle gros et lent est acceptable ;
   plusieurs minutes par appel d'outil ne sont pas un motif de rejet. Ne jamais
   écarter un modèle sur sa latence seule.
3. **Modèles les plus récents possible.** Privilégier les dernières générations
   (Qwen3.5 / 3.6 / 3.8 et suivantes) sur les modèles éprouvés mais anciens.
4. **Tester modèles ET architectures.** Le tool-calling d'abord (l'agent remplit
   le graphe appel par appel) ; ensuite toute autre architecture jugée pertinente.
5. **Corpus de test : les papiers les plus anciennement téléchargés** — les trois
   articles sur les iridates (Sr₂IrO₄), dans `data/bench_night/`.

## Définition d'un document GOLD (Terry, 18/08/2026)

> Un document est **gold** quand son analyse est **complète et réussie**, et que
> les valeurs de protocole extraites sont **les mêmes que celles annotées à la
> main** dans `data/gold/gold_sr2iro4.json`.

Concrètement, sur un papier donné :
- **100 % des précurseurs** du gold (le flux compris — son omission rend la
  recette irréalisable) ;
- **100 % des valeurs de protocole** : températures, durées, rampes, atmosphère,
  ratios — identiques au gold manuel ;
- **aucune valeur hors gold** (rien d'inventé) ;
- **100 % de traçabilité** : chaque valeur adossée à une citation qui la prouve ;
- **toutes les voies** : un protocole par échantillon décrit (10 pour `crystal`).

Un trou déclaré n'est PAS un gold : il est honnête, mais l'analyse est
incomplète. Le seuil est l'égalité avec l'annotation manuelle, pas « assez bon ».

### Où en est-on de ce seuil (Qwen3-8B, 18/08)
| Papier | Précurseurs | Valeurs | Traçabilité | **Gold ?** |
|---|---|---|---|---|
| physrev | 100 % | 100 % | 100 % | **OUI** |
| crystal | 100 % | 87,5 % (750 °C manquant) | 97,6 % | non |
| prepara | 20 % | 100 % | 100 % | non |

## Règle d'or (inchangée, non négociable)

Le système **n'invente RIEN**. Une donnée absente du papier devient un trou
déclaré, jamais une valeur devinée. C'est ce qui rend une sortie utilisable comme
gold : chaque valeur est adossée à une citation qui la prouve.

## DÉCISIONS DÉJÀ PRISES PAR TERRY — ne plus les reposer

| Sujet | Décision | Date |
|---|---|---|
| Schéma du graphe | **Champs enrichis sur `Operation`**, PAS de nouveau nœud — aucune migration Neo4j | 17/08 |
| Atmosphère non justifiée | **Purger → `MissingParameter`** (application stricte de la règle d'or) | 17/08 |
| Valeur introuvable partout | **Purger → `MissingParameter`** | 17/08 |
| Valeur dans PLUSIEURS lignes de tableau | **Ne rien faire** : conserver + marquer ambiguë, ne jamais ré-ancrer | 17/08 |
| Séquences multiples | **UN protocole PAR ÉCHANTILLON** (Sr214#1, Sr327…) | 17/08 |
| Ordre des correctifs | **A1 (tableaux) AVANT A2 (flux)** | 17/08 |
| Mode raisonnement (`<think>`) | **Le GARDER actif** | 18/08 |
| Régénération du corpus | Par **lots de 5 papiers**, avec création d'un gold à chaque lot, après validation sur les 3 iridates | 17/08 |
| Base des 38 graphes | **Archivée** (`logs/archive_corpus_38_pre_V4.20_*`), ne pas réinjecter dans Neo4j | 17/08 |
| Modèles Gemma / DeepSeek / 14B | **Supprimés** — ne pas les retélécharger sans raison | 17-18/08 |
| Bloc « lignes de tableau » | **En réserve**, à activer si les tableaux ne sont pas cités spontanément | 17/08 |

## Où en est le pipeline (18/08/2026)

Architecture tool-calling opérationnelle (`SynthGraph_V5_TC`), mesurée sur les
3 papiers avec Qwen3-8B :

| Papier | Précurseurs | Températures | Valeurs prouvées | Voies |
|---|---|---|---|---|
| crystal (tableaux) | 100 % | 87,5 % | 92,4 % | 8/9 |
| physrev (prose) | 100 % | 100 % | 100 % | 1 |
| prepara (OCR 1957) | 40 % | 100 % | 100 % | 1 |

Contre 22,6 % de valeurs prouvées et 1 seule voie en single-shot.

## Choix du modèle — TRANCHÉ (19/08/2026)

**Qwen3-8B** (`Qwen3-8B-Q4_K_M.gguf`), avec mode raisonnement actif, `n_ctx=16384`,
`max_tokens=4096`, format natif conservé.

La taille n'améliore JAMAIS la qualité — quatre mesures indépendantes :

| Comparaison | Résultat |
|---|---|
| Qwen2.5 7B → 14B (single-shot) | identique, ×5 le temps |
| Qwen3 8B → 14B (single-shot) | le 14B est **pire** |
| Qwen3-8B → MoE 35B-A3B | le MoE est **pire** (33 % précurseurs) |
| Qwen3-8B → Qwen3.8-27B (Q4) | **identique**, ×4,8 le temps (48 min vs 10) |

Ce qui a produit la qualité, ce sont les **correctifs d'intégration et de
validation** — pas le modèle. Avec le MÊME 8B, crystal est passé de 37,5 % à
100 % de températures.

→ Ne pas relancer de campagne « gros modèle » sans raison nouvelle.
   Qwen3.6-27B non testé : résultat prévisible au vu des quatre mesures.

## Résultats atteints (19/08/2026, Qwen3-8B)

| Papier | Précurseurs | Températures | Traçabilité | Gold ? |
|---|---|---|---|---|
| crystal | 100 % | **100 %** | 95,4 % (108 val.) | presque (5 val. non tracées) |
| physrev | 100 % | 100 % | 100 % | **OUI** |
| prepara | **100 %** | 100 % | 100 % | **OUI** |

Départ (single-shot) : crystal 37,5 % de températures, 22,6 % de traçabilité,
**1 voie sur 10**.

## Ce qui bloque encore la génération d'un gold

| # | Erreur | Cause |
|---|---|---|
| 1 | **Atmosphère perdue** sur crystal | elle est dans la prose, la température dans le tableau — l'outil n'accepte qu'UNE citation par appel |
| 2 | **Précurseurs énumérés par suffixe** (prepara, 40 %) | « strontium oxide, carbonate, nitrate or hydroxide » : `SrCO3` n'est jamais écrit en entier |
| 3 | **750 °C manquant** | ligne `Sr327` fusionnée avec la précédente par opendataloader — défaut d'extraction PDF, pas de LLM |
| 4 | **Ratios molaires** | jamais mesurés en tool-calling |
| 5 | **Rendements** | aucun des 3 papiers n'en rapporte — non validé |

Cause commune aux trois premières : une information VRAIE existe dans le papier
sous une forme que la règle « une citation contient la valeur ET nomme le
composé » ne sait pas accepter. La rigueur qui interdit l'invention rejette aussi
du vrai. Les lever **sans rouvrir la porte à l'invention** est le chantier
central.

## Leçon de méthode (payée six fois)

Quand un modèle échoue totalement là où d'autres réussissent, l'hypothèse
« ce modèle en est incapable » vient APRÈS l'inspection des tokens bruts et des
logs d'erreur. Six défauts d'intégration successifs ont été pris pour des limites
de modèles (cf. `HANDOFF_V5_TOOLCALLING.md` §4). Il n'existe **aucun format
standard d'appel d'outil** : chaque famille impose le sien.
