# HANDOFF — SynthGraph V5_TC (architecture tool-calling)

> **À lire en premier par toute session reprenant ce chantier.**
> Version bis de SynthGraph explorant l'architecture voulue par Terry :
> l'extracteur construit le graphe **appel d'outil par appel d'outil**, au lieu
> de produire un JSON d'un bloc. Copie de V4.4 du 17/08/2026, code + outils +
> 3 papiers + gold + Bible RAG (138 Mo, sans .git ni corpus complet).

---

## 1. L'idée et pourquoi elle tient

En single-shot, le modèle produit une recette dont les valeurs sont souvent
détachées de leur preuve : **22,6 %** seulement des valeurs figuraient dans la
citation censée les justifier. Ici, chaque valeur entre par un appel d'outil qui
la **refuse si sa citation ne la contient pas**, et le refus est renvoyé au
modèle en langage clair pour qu'il se corrige au tour suivant.

Mesuré : la traçabilité passe à **95-98 %**. Le mécanisme fait ce qu'on attend.

## 2. Fichiers du chantier

| Fichier | Rôle |
|---|---|
| `synthgraph/extraction/graph_tools.py` | `RouteBuilder` + 3 outils (`add_precursor`, `add_operation`, `finalize_route`) et leurs schémas. Toute la validation est là. |
| `synthgraph/extraction/sample_detect.py` | Détection déterministe des échantillons (9/10 sur le papier 1) + `table_rows_block()` (bloc tableaux, **non encore essayé**) |
| `synthgraph/agents/extractor_toolcalling.py` | Boucle agentique + garde-fous ; `extract_all_samples()` = une extraction par échantillon |
| `tools/test_faisabilite_tc.py` | Filtre rapide : le modèle sait-il enchaîner des outils ? (1 papier, 1 échantillon) |
| `tools/compare_tc_gold.py` | **La vraie mesure** : 3 papiers, ~10 extractions/papier, confronté au gold |
| `tools/build_text_cache.py` | Pré-extraction ODL en cache (`logs/odl_*.txt`) — indispensable, l'extraction est lente |

Tests offline (aucun GPU) dans le scratchpad : outils **29/29**, boucle **19/19**.

## 3. Résultats mesurés (17-18/08/2026)

### ⚠️ AVERTISSEMENT sur les premières mesures (18/08/2026)

Une première série concluait que **Qwen3 était incapable de tool-calling** et que
**le tool-calling s'effondrait sur les papiers non tabulés**. **CES DEUX
CONCLUSIONS ÉTAIENT FAUSSES.** Elles mesuraient CINQ défauts d'intégration
(section 4), pas les capacités des modèles. Ne pas s'y fier — seuls les chiffres
ci-dessous, obtenus après correction, sont valides.

### Qualité vs gold — Qwen3-8B après correction des 5 défauts
| Papier | Structure | Départ | **Final** | Single-shot V4.20 |
|---|---|---|---|---|
| crystal | tableaux | 0 % | **prec 100 %, temp 87,5 %, tracé 92,4 % (79 val), 8/9 voies** | prec 100 %, temp 37,5 %, tracé 22,6 %, 1 voie |
| physrev | prose, 2 colonnes | 0 % | **prec 100 %, temp 100 %, tracé 100 %** | prec 100 %, temp 100 % |
| prepara | OCR 1957 | 0 % | **prec 40 %, temp 100 %, tracé 100 %** | prec 100 %, temp 100 % |

**Le tool-calling égale ou dépasse le single-shot sur 2 papiers sur 3**, et
apporte partout ce que le single-shot ne donnait pas : **92-100 % des valeurs
adossées à une citation qui les prouve**, contre 22,6 %.

Sur `prepara`, il plafonne à 40 % : les précurseurs y sont énumérés par suffixe
(« strontium oxide, carbonate, nitrate or hydroxide ») — `SrCO3`, `Sr(NO3)2` et
`Sr(OH)2` n'apparaissent JAMAIS sous forme complète. Exiger une citation qui
nomme le composé devient impossible. Le single-shot y arrive parce qu'il n'a pas
cette contrainte : c'est le prix de la rigueur, ici 60 points.

### Faisabilité mécanique (mesures AVANT correction — à refaire)
| Modèle | Verdict | Remarque |
|---|---|---|
| qwen25-7b | ✅ | 7/7 appels acceptés |
| llama31-8b | ✅ | 6/6 — seul modèle SANS support natif, l'adaptateur lui est nécessaire |
| qwen25-14b | ✅ | 6/6, **5× plus lent** que le 7B pour le même résultat |
| qwen3-8b | ❌→✅ | déclaré en échec À TORT ; après correction, meilleur résultat mesuré |
| qwen3-14b | ❌ | **à refaire** — testé avec les défauts d'intégration |
| qwen35-9b | ✅ | 87,5 % temp sur crystal, mais testé AVANT les correctifs 3-5 |

Sur la question initiale (« faut-il un plus gros modèle ? ») : **non**. Vérifié en
single-shot (Qwen2.5-14B = 7B pour 5× le temps ; Qwen3-14B < 8B). En
tool-calling, les comparaisons de taille restent **à refaire** proprement.

## 4. Les CINQ défauts d'intégration (le cœur du sujet)

Chacun donnait l'apparence d'un **échec du modèle**. Aucun n'en était un. Ils se
sont révélés l'un après l'autre, chaque correction dévoilant le suivant.

| # | Défaut | Symptôme trompeur | Correction |
|---|---|---|---|
| 1 | `chat_format` écrasant le template natif | appel tronqué en `functions.add_precursor:` | ne forcer l'adaptateur QUE si le template n'a pas `tool_call` |
| 2 | Parser aveugle aux balises natives | appels parfaits mais `tool_calls` vide → « le modèle ne répond plus » | `_extract_native_tool_calls()` en repli |
| 3 | Contexte 8192 saturé | `Requested tokens (8715) exceed context window` au 3e tour → extraction amputée | `n_ctx` 16384 + élagage de l'historique |
| 4 | Citation scindée par la MISE EN PAGE | 13 refus sur 17, le modèle boucle | couverture gloutonne par fragments ordonnés |
| 5 | **Césure typographique** | `reac-\n\ntion` ≠ `reaction` → AUCUNE citation possible | recollage `-\s+` des DEUX côtés |
| 6 | **Élagage d'historique SYSTÉMATIQUE** | Qwen2.5-7B chute de 62,5 % à 25 % de températures (55 → 27 valeurs) | élagage CONDITIONNEL (`_TRIM_ABOVE_TOKENS`) — ⚠️ **corrigé mais NON MESURÉ** |

> Le défaut 6 est né du correctif 3 : écrit pour empêcher Qwen3 de saturer le
> contexte, l'élagage privait de contexte les modèles SANS raisonnement, qui ne
> saturaient jamais. **Un correctif validé sur une famille de modèles doit être
> re-mesuré sur les autres avant d'être considéré comme acquis.**

**Leçon de méthode.** Face à un modèle qui échoue totalement là où d'autres
réussissent, l'hypothèse « ce modèle en est incapable » doit venir APRÈS
l'inspection des logs d'erreur. Les défauts 3 à 5 étaient tous visibles dans
stderr (`ValueError: exceed context window`, `[citation absente] '...'`) — trois
conclusions publiées à tort auraient été évitées en les lisant d'abord.

Corollaire : les défauts 4 et 5 sont des problèmes de **document**, pas de LLM.
Les articles scientifiques sont en deux colonnes et césurés ; toute validation
par citation littérale doit en tenir compte, sinon elle rejette du vrai.

## 4 bis. Autres pièges

- **`chat_format="chatml-function-calling"`** reste nécessaire pour les modèles
  SANS support natif (Llama-3.1). Sans lui, ils répondent en texte libre.
- **Normalisation des citations** : comparer littéralement rejette tout
  (`1300◦C` vs `1300 °C`, `SrCl2 · 6H2O`). On réduit au squelette alphanumérique.
- **Citations abrégées par `…`** : le modèle coupe ses citations. L'ellipse est
  une coupure, pas une invention → chaque fragment doit être présent ET dans
  l'ordre (les fragments recombinés dans le désordre restent refusés).
- **Tout-ou-rien = blocage** : refuser l'opération entière dès qu'un paramètre
  manque de preuve fige le modèle, qui boucle sur `finalize_route`. L'acceptation
  partielle (garder le prouvé, écarter le reste en trou déclaré) débloque tout.
- **Processus longs** : TOUJOURS `Start-Process` (PowerShell). Un `nohup … &`
  depuis Bash meurt avec la session — un téléchargement de 9 Go s'est interrompu
  silencieusement à 5 Go, et un bench a été tué de la même façon.

## 5. PREMIÈRE CHOSE À FAIRE À LA REPRISE

Re-mesurer **Qwen2.5-7B** avec l'élagage conditionnel (défaut 6, corrigé sans
avoir été vérifié) :
```bash
python tools/compare_tc_gold.py --model Qwen2.5-7B-Instruct-Q4_K_M.gguf --n-ctx 16384
```
Enjeu réel : Qwen2.5-7B est **12× plus rapide** que Qwen3-8B (1,9 min contre
22 min sur `crystal`) et extrait 9 voies sur 9 contre 8. Si sa mesure remonte une
fois l'élagage neutralisé, c'est lui le candidat de production, pas Qwen3-8B.

### État comparatif au 18/08/2026 03:55 (à consolider)
| Modèle | crystal temp | physrev | prepara | crystal durée |
|---|---|---|---|---|
| Qwen3-8B (6 correctifs) | **87,5 %** | 100 % / 100 % | 40 % / 100 % | 22 min |
| Qwen2.5-7B (élagage SUBI) | 25 % ⚠️ | 100 % / 33 % | 20 % / 0 % | **1,9 min** |

## 5 bis. À REFAIRE ensuite (mesures invalidées)

Tous les modèles sauf Qwen3-8B ont été évalués AVANT tout ou partie des cinq
correctifs. Leurs chiffres sous-estiment donc leurs capacités :
- **qwen25-7b, qwen35-9b** : testés avant les correctifs 3, 4 et 5 ;
- **qwen3-14b, qwen25-14b, llama31-8b** : testés avant les correctifs 2 à 5.

Commande de référence (3 papiers, ~10 extractions/papier) :
```bash
python tools/compare_tc_gold.py --model <x>.gguf --n-ctx 16384
```

## 5 bis. À corriger en priorité

1. **La métrique « appels acceptés » est trompeuse.** Depuis l'acceptation
   partielle, une opération dont TOUS les paramètres sont écartés compte comme
   acceptée : sur `physrev`, 23 « acceptés » n'ont produit aucune donnée.
   Compter séparément : pleinement accepté / partiel / refusé.
2. **L'atmosphère disparaît** en tool-calling sur le papier tabulé : les lignes
   de tableau ne la mentionnent pas (elle est dans la prose). Elle devrait être
   un attribut du PROTOCOLE, pas de l'étape, ou faire l'objet d'un appel dédié.
3. **`Sr327` non détecté** (10e échantillon) : sa ligne est fusionnée avec la
   précédente par l'extraction ODL → 750 °C reste introuvable.
4. **Comparateur** : vérifier qu'il reconnaît les précurseurs nommés en toutes
   lettres (« strontium carbonate ») et pas seulement en formule.

## 6. Suite proposée (à décider à froid)

**Routage hybride** — la détection d'échantillons fonctionne déjà et discrimine
correctement (9 sur le papier tabulé, 0 sur les deux autres) :
- échantillons tabulés détectés → tool-calling ;
- sinon → single-shot V4.20 avec ses garde-fous.

Sur ces 3 papiers, cela donnerait 100 % de précurseurs partout ET la traçabilité
du tool-calling là où elle est atteignable. **Non validé par la mesure** — c'est
une hypothèse, à tester comme le reste.

Reste aussi en réserve le **bloc tableaux** (`table_rows_block()`, écrit mais
jamais essayé) : présenter les lignes sous un intitulé explicite pourrait aider
sur les papiers en prose. Terry l'avait conditionné à « si ça marche pas ».

## 7. Commandes

```bash
# Toujours : PYTHONIOENCODING=utf-8, interpréteur C:/Python314/python
python tools/build_text_cache.py                       # cache ODL (à faire une fois)
python tools/test_faisabilite_tc.py --all --max-no-tool 5
python tools/compare_tc_gold.py --model Qwen3.5-9B-Q4_K_M.gguf
python tools/compare_tc_gold.py --model <x>.gguf --table-block   # repli non testé
```
