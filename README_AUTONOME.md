# README_AUTONOME — Journal de bord Claude × SynthGraph

> **À LIRE EN DÉBUT DE CHAQUE SESSION.** Ce fichier est l'historique continu des
> modifications et l'état du protocole de montée en charge du corpus. Il est mis à
> jour après chaque batch et chaque correctif. Ne pas supprimer.

---

## Mission (mandat de Terry, 2026-07-12)

Construire la base de données Neo4j de voies de synthèse **la plus complète possible**
à partir d'un corpus de publications scientifiques, en autonomie, avec la règle d'or :

> **Ne JAMAIS rien inventer. Un trou dans le protocole est déclaré dans le graphe
> (MissingParameter/REQUIRES_CLARIFICATION), jamais comblé par une supposition.**

## Protocole de montée en charge (batchs)

1. Batch initial : **5 papiers** en `--no-debate` → triage (`tools/triage_corpus.py`).
2. Analyser les erreurs → re-run **avec débat** (sans `--no-debate`).
3. S'il reste des erreurs : **corriger le code** (tests offline d'abord), re-run les
   papiers affectés + golden set, puis passer au batch suivant.
4. **Zéro erreur sur un batch → la taille double** (5 → 10 → 20 → 40…).
5. Objectif de sortie de phase 1 : **zéro erreur sur 10 papiers successifs**.
6. Après chaque batch : mettre à jour ce README (section Historique + État).
7. Golden set : les papiers validés sont archivés (`logs/baseline_*`) ; tout correctif
   est re-testé dessus — un correctif qui casse un golden est rejeté.

**Définition d'« erreur »** (classes du triage, par gravité) : `CRASH`, `NO_DATA`,
`ALL_REJECTED`, `EXTRACTION_LOSSY` (majorité des variantes supprimées),
`STOICH_FAIL` non résolu, `SLOW` (>45 min/papier ou appel >350 s — Terry, 2026-07-13 : « c'est ok 45 minutes si les résultats sont corrects », la qualité prime).
`STOICH_UNKNOWN` et `GAPS_REQUIRED` = signaux à surveiller, pas des échecs bloquants
(ils reflètent souvent le papier lui-même).

## Commandes de référence

```bash
# Triage rapide d'un batch
python run.py --input data/corpus_batch_N/ --no-debate > logs/run_batchN.log 2>&1
python tools/triage_corpus.py --run-log logs/run_batchN.log

# Run complet (QA débat)
python run.py --input data/corpus_batch_N/ > logs/run_batchN_debate.log 2>&1

# Tests de non-régression (offline, sans LLM, ~2 min)
# suites scratchpad : etape1/2/3/4, antihallucination, fusion — voir section Tests
```

- Python : `C:/Python314/python` (llama-cpp-python 0.3.31, CUDA).
- Modèle : Llama-3.1-8B-Instruct Q4_K_M in-process (`config/settings.yaml`), RTX 3070 8 Go.
- `PYTHONIOENCODING=utf-8` obligatoire (logs accentués).
- Ne jamais toucher `logs/chroma_db_bible/` ni `data/`.

---

## Architecture des garde-fous (état actuel V4.7.3)

Chaîne : `PDF → Stratège (routes) → Orchestrateur (directives, dédupliquées) →
Extracteur single-shot (+ rattrapages) → validation déterministe → QA débat (veto) →
Cypher paramétré → Neo4j`.

| Garde-fou | Fichier | Principe (toujours : preuve textuelle, sinon ne rien faire) |
|---|---|---|
| Grounding citations | `pipeline/runner.py` `_validate_extraction_against_text` | Chaque citation doit exister dans la source (match nettoyé, tolérant OCR). Majorité STRICTE non ancrée → variante SUPPRIMÉE (`dropped_pathways`) ; sinon flag `citation_grounded=false` dans le graphe |
| Grounding précurseurs | idem (`_name_in_source`) | La formule doit exister dans la source (mots ≥4 chars pour les noms en prose). Précurseur inventé = non-ancré |
| Bilan élémentaire | `validation/deterministic.py` `element_balance_report` | Parseur maison (hydrates, dopage 1-x). Verdicts OK/ÉCHEC/INDÉTERMINÉ — jamais de veto sur formule illisible |
| Veto déterministe | `runner.py` `_apply_deterministic_veto` | Stoich ÉCHEC → REJECT forcé quel que soit l'avis LLM. Ancre l'audit_checklist |
| Rattrapage précurseurs | `runner.py` (step3) | ≤2 précurseurs + éléments manquants → 1 retry avec l'indice des éléments absents ; retenu si mesurablement meilleur |
| Fusion/insertion grindings | `runner.py` `_merge_sequential_variants` | 'intermediate grindings' mentionné + cycles palier→réchauffe → fusion des fausses variantes OU insertion déterministe (zéro LLM, citation = phrase réelle) |
| Dédup directives | `runner.py` `_dedupe_directives` | (cible, méthode) uniques — l'Orchestrateur duplique parfois ×3 |
| Recommendation canonique | `runner.py` `_normalize_recommendation` | Phrase libre LLM → REVISE (jamais promue ACCEPT) ; brut gardé en `recommendation_raw` |
| Fail-closed | `runner.py` steps 4/5 | Agent en échec → QA_FAILED, conf 0.0, débat interrompu. AUCUN fallback à données fictives |
| qa_status → graphe | `runner.py` step6 | ACCEPT/REJECT/REVISE/NEEDS_DATA/QA_FAILED/QA_SKIPPED + qa_confidence (null si QA absente) sur SynthesisProtocol |
| IDs anti-collision | `runner.py` `_paper_id_from_reference` | SHA1[:10] du DOI (sinon fichier) préfixe tous les IDs ; Reference MERGE sur paper_id |
| Cypher paramétré | `runner.py` step6 + `utils/tools.py` | `$params` natifs driver, clés assainies, échecs comptés ; `.cypher` rendu pour relecture |
| Trous explicites | `schemas/step_schema.py` + step6 | required + RECOMMENDED_PARAMETERS → nœud MissingParameter (severity, unit) lié au protocole ET à l'Operation |
| Plafond QA | `runner.py` `QA_MAX_TOKENS=2048` | Anti-génération dégénérée (590 s constatés au plafond 8192) |

## Historique des modifications

### 2026-08-22 — la CONVERSION admise, et le rapport ENONCE lu

**Correctif 35 — le modele n'est plus puni d'avoir bien converti.** La citation
dit « heated to 750 °C IN 40 MIN », le modele declare `duration_h = 0.6667` — la
valeur EXACTE — et le garde-fou la refusait faute de trouver « 0.6667 » ecrit.
Une ligne plus bas, `_DUREE_RE` lit « 40 min » et ecrit 0.6667 : le pipeline
refusait au modele ce qu'il calcule lui-meme. 9 refus sur 5 papiers.

`_num_in` compare desormais DANS L'UNITE CANONIQUE pour la famille temps, avec
une tolerance d'ARRONDI et non d'a-peu-pres : 0,67 vaut 40 min, 0,7 ne les vaut
plus. La regle d'or tient — accepter une conversion n'est pas accepter une
valeur absente, la duree source doit etre ECRITE.

Verifie en production : sur `cvd_mos2` les cinq durees portent maintenant
`duration_h_source = None`, elles viennent DU MODELE. Avant, elles etaient
refusees puis re-fournies par le post-traitement. **Le rattrapage redevient un
filet, pas une bequille.** Metrique inchangee — c'etait attendu.

**Correctif 36 — un rapport ECRIT EN TOUTES LETTRES doit etre lu.**
`electro_nico` restait a 0 % de ratios, le plus faible du corpus. Le modele
declarait pourtant `ratio = 1` pour l'ethylamine ET l'acide nitrique — les
BONNES valeurs — en attachant la phrase des REACTIFS, qui ne porte aucun
rapport. Celui-ci est dans la phrase voisine : « ... with a MOLAR RATIO OF 1:1 ».

Aucun des trois mecanismes existants ne lisait un rapport ENONCE : l'un lit une
enumeration, l'autre des quantites pesees, le troisieme deduit d'une formule.
Le cas le plus simple etait le seul non couvert.

**HUITIEME mecanisme inerte de la nuit, et ma regle etait fausse dans sa
CONCEPTION.** J'exigeais que le nombre de termes egale le nombre de precurseurs
SANS RAPPORT. Or `electro_nico` en a quatre et l'enonce n'a que deux termes,
parce que la phrase ne concerne que deux composes — les chlorures n'y sont pour
rien. Un rapport s'apparie aux composes QUE LA PHRASE NOMME.

Corriger la regle a invalide DEUX de mes propres assertions. Je les ai
reecrites plutot que d'affaiblir la regle : l'ancienne garde etait precisement
ce qui sterilisait le mecanisme.

`electro_nico` : ratios **0 % -> 100 %**, confirme par
`[ratios] 2 ratio(s) lus d'un ENONCE : 1:1`. Aucune regression.

**Etat : 8 papiers sur 12 a l'egalite stricte complete, tracabilite 100 %
partout. 58 suites, 1322 assertions, 0 echec.**

**FAUSSE ALERTE A CONSIGNER.** Trois commandes consecutives ont omis le `cd`
initial et listaient `D:\projet\logs\` au lieu du repertoire du projet. J'y ai
vu un repertoire vide et l'absence de `chroma_db_bible`, que le CLAUDE.md
protege — j'etais a une phrase d'annoncer une PERTE DE DONNEES catastrophique.
Verification au bon endroit : 12 fichiers de voies, 12 textes, 15 fichiers de
baseline, la bible presente. RIEN n'avait disparu. Le repertoire de travail par
defaut est `D:\projet`, PAS le projet : chaque commande a besoin de son `cd`.

### 2026-08-22 (fin) — la BOUSSOLE mentait, et le corpus devient la limite

**Aucun correctif du pipeline dans cette phase, et c'est le resultat.** Trois
pistes ouvertes par l'audit ont ete ECARTEES SUR MESURE, et l'audit lui-meme a
du etre repare trois fois.

**L'instrument mentait, en trois couches.** En voulant traiter les « 5
parametres directement actionnables » de `crystal`, je n'ai pu en REJOUER aucun.

| Defaut | Effet |
|---|---|
| jugement sur TOUT le papier | « 24h dwell » present pour CERTAINS echantillons rendait rattrapables les durees de voies qui n'en portent aucune |
| table des citations indexee par `order` seul | sur DIX voies renumerotees a partir de 1, les citations se melangeaient entre voies — **defaut que j'avais introduit la veille** |
| AUCUN motif pour `target_temperature_c` | l'audit tombait dans « je ne sais pas juger » et comptait le parametre comme PRESENT dans le papier |

Le troisieme est le plus insidieux : **un defaut par defaut se faisait passer
pour un constat**. Il a desormais sa categorie propre, qui dit « l'audit ne sait
pas juger » au lieu de se ranger du cote flatteur.

L'audit distingue maintenant QUATRE etats : present dans la citation de l'etape
(actionnable), present AILLEURS dans le papier (mecanisme inter-phrases),
absent de la source (incomblable), non jugeable (limite de l'audit).

**Trois pistes ecartees sur mesure**, par la meme regle qui a servi toute la
nuit — ne pas construire pour un cas isole :

| Piste | Mesure | Decision |
|---|---|---|
| apparier chaque palier a sa duree (ligne multi-paliers) | **1** cas sur 12 papiers | non |
| etapes sans aucun parametre | 7 % et non 20 % (mon instrument excluait `other_parameters`), 6 sur 7 legitimement vides | non |
| un MAINTIEN herite du palier precedent | **2** etapes, et gain NUL sur la mesure (750 et 180 °C figurent deja ailleurs) | non |

**CE QUE L'AUDIT DIT MAINTENANT**, une fois honnete :
- `physrev` et `electro_nico` : UNIQUEMENT des limites de la source ;
- `broyage_na` et `selfondu_cosi` : une `method` chacun, seul vrai manque ;
- `crystal` et `cvd_mos2` : des valeurs presentes AILLEURS, dont la
  recuperation buterait sur l'interdit du projet (ne jamais propager une
  temperature — chaque palier a la sienne).

**LE CORPUS EST DEVENU LA LIMITE.** Les 12 PDF disponibles sont tous exploites,
8 papiers sur 12 sont a l'egalite stricte complete avec 100 % de tracabilite, et
les ecarts restants sont soit incomblables, soit marginaux. Le pipeline a
plafonne sur CE corpus : chaque famille nouvelle avait revele des defauts que
les precedentes ne pouvaient pas montrer, et il n'y a plus de famille nouvelle.

**Etat verifie : 56 suites / 1289 assertions / 0 echec. Golds : 310 controles /
0 erreur. Document des 12 voies regenere.**

### 2026-08-22 — l'UNITE, et la REFAISABILITE comme nouvelle boussole

**Correctif 32 — GRAVE : le controle anti-invention ignorait les UNITES.** Il
n'examinait que le nombre. Sur une citation reelle de `selfondu_cosi` :

    temperature_c = 20    ACCEPTE, prouve par « 20 Hz »
    temperature_c = 23    ACCEPTE, prouve par « 23 mm » (diametre de bille)
    temperature_c = 62.3  ACCEPTE, prouve par « 62.3 g » (masse de bille)

Le run du 21/08 avait REELLEMENT pose « 20 °C » sur un broyage a partir de
« 20 Hz ». Une valeur fabriquee franchissait la regle d'or.

Mesure AVANT d'ecrire : 60 des 74 valeurs du corpus portaient deja une unite
compatible ; les 14 autres relevaient d'ECRITURES OCR que mon motif ignorait —
« 24h » colle, « 900'C » a l'apostrophe, « 1200° » sans le C, « 180 ℃ »,
« 50 ºC », « 900 C ». Toutes sont desormais testees.

L'UNITE PARTAGEE m'a rattrape une seconde fois : « 170 to 190 C », « 300 and
400 °C ». Trois suites sont tombees des le durcissement. Je l'avais traite dans
`_temperatures_citees` sans le porter ici — la dette des mecanismes dupliques,
que je combattais par ailleurs toute la nuit.

Verification : 12 papiers sans regression, la temperature fabriquee a disparu,
et un audit d'unite sur tout le corpus rend 71 valeurs prouvees / 3 signalees,
les 3 legitimes apres examen.

**LA REFAISABILITE DEVIENT LA BOUSSOLE.** Le mandat ne demande pas la fidelite a
un gold mais des golds SANS annotation humaine : la question utile est « cette
recette est-elle refaisable ? ». L'audit, qui n'avait pas tourne depuis vingt
correctifs, a livre deux defauts INVISIBLES a la comparaison au gold — sur
`crystal`, qui obtient pourtant 100 % en precurseurs, ratios et durees.

**Correctif 33 — une recette ne commence pas par le four.** Les DIX voies de
`crystal` demarraient par `heating` et placaient en DERNIER « Powders of IrO2,
SrCO3 and SrCl2 · 6H2O were thoroughly mixed and placed in a platinum
crucible ». On melange AVANT d'enfourner. Cause : l'ordre suivait la lecture du
papier, et le modele a cite la ligne du TABLEAU avant la phrase des Methods.
Mesure : 12 voies sur 3 papiers. PIEGE evite — `physrev` decrit « with many
INTERMEDIATE grindings » : la regle ne deplace QU'UNE etape, et seulement quand
aucune preparation n'ouvre la voie. Sur `prepara`, le broyage intermediaire ne
bouge pas.

**Correctif 34 — une LIGNE DE TABLEAU n'a pas de position dans le protocole.**
Ma prediction que le correctif 33 debloquerait les atmospheres etait FAUSSE :
`crystal` restait a 17 manquants. Le diagnostic a montre la vraie cause — la
mention « heated ... IN AIR » est en position 10479, les lignes de tableau
portant les programmes thermiques en 9200, donc « avant ». La contrainte de
position excluait les huit chauffages. Or un tableau est IMPRIME ailleurs : son
rang dans le document ne dit rien de son rang dans la recette. Meme principe que
le re-ancrage des citations, deja arbitre : le tableau est source de PREMIER
RANG.

| `crystal` | avant | apres |
|---|---|---|
| parametres requis manquants mais PRESENTS dans le papier | 17 | **10** |
| dont atmospheres | 8 | **1** |

**Etat : 8 papiers sur 12 a l'egalite stricte complete, tracabilite 100 %
partout. 56 suites, 1289 assertions, 0 echec.**

Trois fois cette nuit un papier a 100 % cachait un defaut de structure : deux
etapes pour un seul geste, une recette partielle donnee pour complete, et une
sequence inexecutable. **La comparaison au gold ne voit pas la chimie.**

### 2026-08-21 (fin) — le DIALOGUE, et un defaut que seule la RELECTURE montre

**Correctif 29 — le message d'outil n'etait pas neutre.** Trois runs strictement
identiques donnent des resultats IDENTIQUES : le moteur est DETERMINISTE
(`temperature=0.0`). Pourtant `solgel_cuo` divergeait entre deux runs a texte
focalise identique. La seule variable restante etait le DIALOGUE — et en effet :

| Ce que le modele fournit | Ce que le message lui annoncait |
|---|---|
| rien | « **4** parametre(s) valide(s) » |
| la temperature, correctement | « **3** parametre(s) valide(s) » |

Le compte incluait les valeurs recuperees APRES COUP par les post-traitements.
Message inversement informatif : fournir une valeur faisait BAISSER le compte.
La propriete sur laquelle repose toute la strategie du projet — « le
post-traitement deterministe ne se paie pas » — etait donc FAUSSE en pratique :
il deplacait la trajectoire du modele au tour suivant, et rendait les correctifs
inattribuables d'un run a l'autre.

Le compte ne porte plus que sur ce que le MODELE a fourni. Marqueurs renommes en
`<champ>_source` pour que la regle d'exclusion soit GENERALE, plutot qu'une table
d'exceptions qui deriverait — meme lecon que les trois listes de colonnes.

**Correctif 30 — un solvant porte par l'ETAPE compte comme extrait.** Le gold de
`selfondu_cosi` attend CH3OH et la mesure le declarait MANQUANT (precurseurs
80 %). Or l'etape de lavage portait bien `solvent='methanol'`, 7 repetitions.
L'information etait la ; la mesure ne regardait qu'un endroit. TROISIEME angle
mort de mesure de la nuit, apres l'asymetrie `SrCl2` et le compte gonfle.
Garde : seul un precurseur de role « solvent » peut etre satisfait ainsi.

**Correctif 31 — DEUX etapes pour un seul geste.** Trouve en RELISANT le document
des voies (#21), pas dans les chiffres. Sur `broyage_na` :

    1. grinding      duration_h = 2     meme phrase
    2. ball_milling  atmosphere = Ar    meme phrase

Un chimiste y lisait deux broyages successifs. Le papier etait pourtant a
l'EGALITE STRICTE COMPLETE : les durees se dedoublonnent, l'atmosphere est
juste, la mesure ne voyait RIEN. Un defaut de STRUCTURE, que la comparaison de
valeurs ne peut pas montrer.

Le diagnostic a traverse TROIS couches, meme cause racine — comparer des types
BRUTS plutot que canoniques :
- la deduplication (`grinding` != `ball_milling`) ;
- `_recover_workup_steps`, qui ne reconnaissait pas « ball-milling » comme un
  broyage deja declare et EN AJOUTAIT un ;
- le REGISTRE, ou `atmosphere` existait sur `ball_milling` et `mixing` mais PAS
  sur `grinding` — alors que `ball_milling` s'y canonicalise.

Ce troisieme point etait un piege : supprimer l'etape en double supprimait
justement celle qui portait l'atmosphere. Sans le verifier, j'aurais corrige la
structure en perdant une valeur.

**Le document des voies etendu aux 12 papiers** (#21) est desormais l'outil qui
manquait. Il montre ce que la metrique tait : l'ordre des etapes, leur sens
chimique, et la citation qui prouve chaque valeur. Il a livre son premier defaut
a la premiere relecture.

**Etat : 8 papiers sur 12 a l'EGALITE STRICTE COMPLETE, tracabilite 100 %
partout. 52 suites, 1241 assertions, 0 echec.**

`selfondu_cosi` passe de 0 a 50 % de temperatures — mais la relecture montre que
le modele a retenu UNE des deux variantes (« 300 and 400 °C ... respectively »)
et la presente comme LA recette. Ce n'est pas une invention, c'est une recette
partielle. Consigne en tache dediee.

### 2026-08-21 — parametres de procede, tracabilite, et le PROMPT disculpe

**Correctif 27 — frequence de broyage et potentiel de depot.** Les colonnes
ajoutees au registre restaient inatteignables : rien ne les remplissait. Une
colonne qu'aucun mecanisme n'alimente ne vaut pas mieux qu'une colonne absente.

Avant d'ecrire, j'ai verifie qu'il y avait une CIBLE — la lecon de la nuit.
`selfondu_cosi` a deux etapes portant « 20 Hz » ; `electro_nico` n'a AUCUNE
etape portant un potentiel. Le mecanisme du potentiel est ecrit et teste pour le
jour ou l'etape de depot apparaitra, mais il ne compte pas comme un gain.

Chaque grandeur est bornee a l'operation ou elle a un SENS : sans cela les
potentiels de pic releves en voltammetrie cyclique (-0,50 / -0,59 / -0,94 V),
qui sont de la CARACTERISATION, passeraient pour des consignes de depot.

**Cinquieme mecanisme inerte, et le plus instructif.** Zero declenchement au
premier run. Cause : le post-traitement s'execute AVANT la normalisation, donc
il voit le type BRUT ecrit par le modele — qui suit le papier, « were
ball-MILLED », donc `ball-milling` avec un TRAIT D'UNION. Ma liste ne connaissait
que « ball milling » avec une espace, et mes tests etaient ecrits sur les types
DEJA normalises : ils passaient tous les six.

Corrige non pas en allongeant ma liste, mais en s'adossant a la table `SYNONYMS`
du registre — meme principe que pour la couverture du grounding : UNE SEULE
SOURCE DE VERITE, pas une copie qui derive. Confirme en production :
`[procede] 20 Hz deduit de la citation`.

**Correctif 28 — la tracabilite des etapes etait perdue.** Terry avait exige
qu'un audit puisse toujours separer ce qui a ete LU de ce qui a ete CALCULE.
C'etait tenu pour les precurseurs (`ratio_source=formule_cible` figure bien dans
la voie finale) et PERDU pour les etapes : le normaliseur ne conserve que les
colonnes du registre, donc `duration_source`, `temperature_source` et
`frequency_source` etaient effaces en silence. Ils sont desormais routes dans
`other_parameters`, qui fait partie des cles structurelles preservees — plutot
que d'ajouter une colonne `_source` a chacun des vingt-huit types d'operation.

La distinction montee/palier redevient lisible : `citation_regex_montee` pour
« in 40 min », `citation_regex` pour « kept for 25 min ».

**LE PROMPT EST DISCULPE — mesure, pas opinion.** Terry a demande s'il fallait
le modifier. La focalisation reduit `electro_nico` de 54 301 a 8 500 caracteres
(16 %), et les conditions de depot N'Y SONT PAS :

| Phrase du papier | complet | focalise |
|---|---|---|
| « at the same temperature (60℃) » | oui | **NON** |
| « of -1.1, -1.2, and -1.3 V » | oui | **NON** |
| « for a 1 hour deposit at 60°C » | oui | **NON** |

Le modele ne cloturait pas trop tot par negligence : **il n'a jamais recu ces
phrases**. 12 appels, 11 acceptes, 1 refus — il a extrait tout ce qu'on lui a
donne. Durcir le prompt n'aurait rien change au probleme et aurait ajoute du
risque sur les 8 papiers qui marchent. Le correctif est en amont, dans
`_build_focused_text` (#41), et il est DETERMINISTE.

ERREUR DE METHODE A NE PAS REFAIRE : j'avais d'abord « verifie » la presence en
cherchant la chaine « 60 », qui matche « 60 % », « 1960 »... et conclu que le
texte etait complet. **Une aiguille trop faible donne une fausse confirmation.**
Chercher la phrase, jamais le nombre seul.

**Etat : 8 papiers sur 12 a l'egalite stricte complete, tracabilite 100 %
partout. 47 suites, 1159 assertions, 0 echec.**

### 2026-08-21 — le lavage, et une DERIVE STRUCTURELLE du garde-fou

**Correctif 25 — le champ `solvent` ne contenait pas que le solvant.** Quatre
defauts, tous PREEXISTANTS :

| Citation | Avant | Apres |
|---|---|---|
| « washed with ethanol three times » | `"ethanol three times"` | `ethanol` + 3 |
| « washed with deionized water twice before drying » | `"deionized water twice be"` | `deionized water` + 2 |
| « washed IN methanol BY seven cycles » | rien | `methanol` + 7 |
| « washed out with acetone » | `"ace"` | `acetone` |

Le dernier est le plus instructif : le motif `to` de la liste de delimiteurs
correspondait au « to » d'« aceTOne ». Il manquait les FRONTIERES DE MOT, et
l'ancienne liste portait deja `to` nu — le defaut precedait ce correctif de
plusieurs semaines. C'est le test qui l'a revele.

Admettre « washed IN » ouvrait une porte : « washed in a beaker » aurait fait
passer le CONTENANT pour un solvant. Une garde rejette toute capture qui nomme
un recipient ou un appareil.

Verifie sur donnees reelles : l'etape de lavage de `selfondu_cosi`, jusqu'ici
ENTIEREMENT VIDE alors que `solvent` est REQUIS au registre, rend desormais
`methanol` et 7 repetitions. Les trois autres papiers concernes sont inchanges.

**Correctif 26 — DIX-NEUF colonnes echappaient au controle anti-invention.**
Je cherchais a brancher trois colonnes nouvelles (`voltage_v`, `frequency_hz`,
`current_ma`). La mesure en a montre dix-neuf : `gas_flow_sccm`,
`from_temperature_c`, `repetitions`, `power_w`, `pressure_torr`...

La cause n'etait pas une omission mais une RECOPIE. La liste des colonnes
soumises au controle existait en TROIS exemplaires codes en dur — un dans
`graph_tools`, deux dans le runner — pendant que le registre d'etapes vivait sa
vie. **Toute colonne ajoutee au registre echappait automatiquement au controle,
en silence.** C'est le contraire d'un garde-fou : une garde qui se decale toute
seule finit par ne plus rien garder.

Le registre est desormais la SOURCE UNIQUE (`colonnes_numeriques()`), et les
trois listes en derivent. `test_couverture_grounding.py` verrouille
l'INVARIANT plutot que trois noms : ajouter demain une colonne sans la brancher
fera echouer la suite.

Un defaut que j'ai introduit en corrigeant, rattrape par ce meme test : l'union
faisait entrer les RAMPES dans le controle par valeur, alors qu'une rampe est
DERIVEE d'un calcul (5 °C/min -> 300 °C/h) et se verifie par sa NOTATION, pas
par son nombre. Les vitesses sont soustraites explicitement.

**Non-regression : les douze papiers rendent exactement les memes chiffres.
8 sur 12 a l'egalite stricte complete. 45 suites, 1124 assertions, 0 echec.
Golds : 310 controles, 0 erreur.**

### 2026-08-21 — les RATIOS, et une lecon sur les mecanismes inertes

Trois papiers a 0 % de rapports molaires. J'allais ecrire la deduction par
formule cible (#37, approuvee par Terry) quand la mesure m'a redirige :
`hydro_czts` donne ses quantites en MILLIMOLES, et le mecanisme qui les
convertit EXISTAIT deja. Quatre rapports en jeu contre deux — diagnostiquer
avant d'ecrire du neuf.

**Correctif 23 — la quantite prouvee par le TEXTE, pas seulement la citation.**
Le modele avait bien releve « 2 mmol / 2 mmol / 1 mmol / 4 mmol ». C'est MON
garde-fou, pose la veille, qui les ecartait : la quantite devait etre prouvee
par la citation DU PRECURSEUR, or le modele y avait attache la phrase de
purete — « CuCl2 · 2H2O, ZnCl2 ... were of analytical grade » — qui ne dose
rien. Les millimoles sont dans la phrase suivante.

Le garde reste : on elargit la PREUVE, pas la credulite. Meme regle d'adjacence
que pour les concentrations — « 2 mmol CuCl2 · 2H2O » prouve le 2 du chlorure
de cuivre, un « 2 mmol » trois composes plus loin ne prouve rien, et le nombre
doit toujours porter SON UNITE, sans quoi le « 2 » de « 2H2O » suffirait.

Second defaut trouve en route : `_position_du_compose` ne rend que la PREMIERE
occurrence. Ici le compose est d'abord nomme dans la phrase de purete, en
position 0, loin de toute quantite — la recherche etait condamnee d'avance.
Toutes les occurrences sont desormais examinees.

`hydro_czts` : ratios 0 % -> **80 %** (le cinquieme, EDTA « 0 to 3 mmol », est
une PLAGE, legitimement non chiffrable).

**Correctif 24 — deduction par la formule cible** (decision de Terry). Quatre
conditions cumulatives : le mot « stoichiometric » dans la source, une cible
decomposable et ENTIERE, un element DISTINCTIF par precurseur, et au moins DEUX
precurseurs servis. L'element distinctif est la garde qui m'est venue en
ecrivant le test : pour une cible CuO, le carbonate d'ammonium partage
l'OXYGENE et serait servi a tort. O, H, C et N n'identifient personne. Un « 1 »
solitaire sans son partenaire est trompeur, d'ou le minimum de deux.

Le ratio deduit porte `ratio_source=formule_cible`, comme Terry l'a exige :
un audit doit toujours pouvoir separer ce qui a ete LU de ce qui a ete CALCULE.

**LA LECON DE LA NUIT — le mecanisme inerte.** Quatre fois de suite, un
mecanisme existait ou fonctionnait, et un detail d'integration le rendait
inerte :

| Mecanisme | Ce qui le bloquait |
|---|---|
| recuperation de temperature | le SCHEMA effacait le resultat sur 6 types d'etape |
| quantite -> ratio | la preuve cherchee dans la mauvaise phrase |
| position du compose | seule la PREMIERE occurrence etait regardee |
| deduction par formule | la cible du gold est un LIBELLE, pas une formule |

Ce dernier est le plus net : « Na3P (particules) », « nanoparticules de CoSi
(coeur-coquille) » — AUCUNE cible de gold ne se decompose telle quelle. Le
mecanisme passait ses 16 assertions et ne pouvait JAMAIS se declencher. La
formule est desormais extraite du libelle, avec deux gardes : un candidat doit
commencer par une MAJUSCULE (sinon « particules » passerait pour un compose) et
porter un chiffre ou au moins deux elements.

**Un test vert ne prouve rien tant que le mecanisme n'a pas tire sur donnees
reelles.** Je verifie desormais le journal d'execution apres chaque correctif,
pas seulement la suite.

`broyage_na` : ratios 0 % -> **100 %**, confirme par
`[ratios] 2 ratio(s) deduit(s) de la formule cible Na3P (particules)`.

**Etat : 8 papiers sur 12 a l'EGALITE STRICTE COMPLETE, tracabilite 100 %
partout. 43 suites, 1092 assertions, 0 echec.**

Seul `solgel_cuo` reste a 0 % de ratios : ses deux reactifs sont donnes en
CONCENTRATIONS egales (15 mM), et une molarite n'est un rapport que si les
volumes le sont aussi — le texte ne les donne pas. L'abstention est correcte.

### 2026-08-21 — les temperatures manquantes venaient du SCHEMA, pas du modele

Depart : la temperature etait l'axe le plus faible du corpus (0 % sur deux
papiers, 66,7 % sur deux autres). J'ai ecrit sa recuperation depuis la citation,
pendant exact de celle des durees — 21 assertions, cinq gardes nees de cas
reels, dont la plus subtile : dans « 300 and 400 °C » le premier nombre n'a pas
de degre a lui, et sans le lire on n'en voyait qu'un seul, donc aucune
ambiguite, donc on retenait 400 — alors que le papier decrit DEUX syntheses.

**Puis la mesure a montre ZERO declenchement sur 36 executions de papier.** Un
mecanisme inerte est suspect : j'ai creuse plutot que de le compter comme un
gain. Le vrai defaut etait ailleurs.

**SIX types d'operation ne pouvaient pas porter de temperature** — `mixing`,
`grinding`, `ball_milling`, `electrodeposition`, `washing` et le fourre-tout
`generic`. Le normaliseur l'effacait. Ce n'etait pas un defaut d'extraction :

| Papier | Valeur perdue | Type d'etape |
|---|---|---|
| electro_nico | -10 °C et 70 °C sous agitation | `mixing` |
| electro_nico | 60 °C du depot | `electrodeposition` |
| combu_ferrite | 65 °C, « gel formation on the magnetic stirrer » | `generic` |

Les 0 % affiches sur `electro_nico` etaient un ARTEFACT. Le modele faisait son
travail ; le schema jetait le resultat.

**Ce que le fourre-tout coutait.** `generic` ne portait QUE `description` :
toute etape que le modele n'arrive pas a classer perdait chacune de ses valeurs
numeriques, MEME prouvees par leur citation. Refuser d'INVENTER est la regle du
projet ; JETER ce qui est prouve n'en fait pas partie. Une etape mal typee vaut
mieux qu'une valeur perdue : le type se corrige, la valeur ne se retrouve pas.

J'avais pourtant ecrit noir sur blanc, dans mon propre test, que le fourre-tout
ne devait porter aucune temperature. **Deuxieme fois cette nuit qu'une prudence
que j'avais decidee est dementie par la mesure suivante** (la premiere etant
l'exclusion de `mixing` pour les durees). J'ai revise, comme la premiere fois.

**Colonnes ajoutees** (decision de Terry du 21/08) : `temperature_c` sur les
cinq operations qui la perdaient, `reference_electrode` — un potentiel de
-1,3 V ne veut rien dire sans elle —, `frequency_hz` pour le broyeur vibrant.
`voltage_v` et `ball_to_powder_ratio` EXISTAIENT deja : pas de doublon cree.

**Effet mesure, deux campagnes completes** :

| Papier | avant | apres |
|---|---|---|
| combu_ferrite | temperatures 66,7 % | **100 %, egalite stricte COMPLETE** |
| selfondu_cosi | durees 50 % | **100 %** |
| electro_nico | temperatures 0 %, tracabilite n/a | 33,3 %, tracabilite 100 % |

**8 papiers sur 12 a l'EGALITE STRICTE COMPLETE** (contre 6 en debut de nuit),
tracabilite 100 % partout.

**Ce qui reste ouvert et pourquoi.** `voltage_v` et `frequency_hz` existent au
schema mais RIEN ne les remplit : elles ne sont pas exposees au modele — donc il
ne peut pas les fabriquer, ce qui est bien — et aucun post-traitement ne les
ecrit encore. Quand il en ecrira un, il faudra les ajouter a `_CHECKED_NUM`
(graph_tools) ET aux deux listes codees en dur du runner (`_NUMERIC_STEP_KEYS`
et le controle d'ancrage), sans quoi elles echapperaient au grounding.

**Suites : 41 suites, 1051 assertions, 0 echec. Golds : 310 controles, 0 erreur.**

### 2026-08-21 — les golds passes aux QUATRE verifications

Demande de Terry : refaire proprement les golds, puis les verifier QUATRE fois
avant d'en rien conclure. Un gold faux ne se voit pas — il fausse la mesure en
silence, et le pipeline est accuse, ou absout, a tort.

`tools/verifier_golds.py` attaque chaque gold sous quatre angles INDEPENDANTS.
C'est leur independance qui fait leur valeur : aucune des sept erreurs
d'annotation commises sur ce corpus n'aurait ete prise par une seule d'entre
elles.

| Passe | Question | Erreur qu'elle prend |
|---|---|---|
| 1 SOURCAGE | tout ce que le gold affirme est-il ECRIT ? | atmosphere inferee, rampe convertie |
| 2 COMPLETUDE | le texte porte-t-il des valeurs OUBLIEES ? | duree oubliee |
| 3 ATTRIBUTION | la valeur appartient-elle a CETTE synthese ? | valeur prise a un autre compose |
| 4 COHERENCE | le gold se contredit-il lui-meme ? | millimoles dans un champ de ratio |

**Resultat : 310 controles, 0 erreur, 30 signalements** — tous relus un par un et
confirmes comme exclusions deliberees (litterature comparee, fabrication de
dispositif, caracterisation, autres syntheses du meme papier).

**SEPTIEME erreur d'annotation, prise par la passe 4.** Le gold de `reduc_cu`
portait « becher » comme contenant. Le mot « beaker » n'existe PAS dans le
papier : je l'avais DEDUIT de « vigorous stirring ». Le seul contenant nomme est
un « glass vial », et il sert au STOCKAGE apres sechage. Meme faute que les trois
atmospheres inferees. Le contenant reactionnel est un trou legitime.

**Une omission, prise par la passe 2.** Les 15 min de `cvd_mos2` — « At about 15
min AFTER the furnace temperature reached 750 °C » — manquaient au gold. Ce n'est
pas la duree d'une operation mais un DELAI entre deux evenements : sans lui, le
soufre n'arrive pas au bon moment et la synthese echoue. Le trou est desormais
visible plutot que masque : le pipeline ne sait pas exprimer un delai.

**Les golds des iridates NORMALISES.** Ils melangeaient temperatures et durees
dans `key_values`, et le comparateur les separait par un seuil de 100 —
heuristique que le code signalait lui-meme comme menteuse hors de ce corpus.
`durations_h` est maintenant declare explicitement. Les ensembles effectifs sont
INCHANGES, verifie avant ecriture : normaliser ne devait pas changer la mesure.

**Un defaut de MESURE, decouvert au passage.** Le comparateur affichait sur
`crystal` « precurseurs 100 % » ET « HORS GOLD : ['SrCl2'] ». Les deux ne peuvent
pas etre vrais. Le predicat de correspondance existait en DEUX exemplaires qui
avaient diverge : le cote « manquants » tolerait le noyau anhydre, le cote « hors
gold » comparait les compositions — et un hydrate n'a pas la composition de son
sel. L'egalite stricte sur les precurseurs etait donc inatteignable des que le
modele laisse tomber un hydrate, ce qu'il fait couramment. Il n'y a plus qu'UN
predicat, et il reste DIRECTIONNEL : on cherche le noyau du gold dans l'ecriture
du pipeline, jamais l'inverse, sans quoi un pipeline n'extrayant que « Sr » face
a « SrCO3 » cesserait d'etre pris en defaut.

Ma premiere version de cette fusion a fait tomber `solgel_cuo` de 100 % a 50 % de
precurseurs : je lui passais des ecritures deja NORMALISEES, sur lesquelles la
decomposition elementaire ne peut plus parser. Vu au recapitulatif, corrige, et
verrouille par `test_symetrie_precurseurs.py`.

**Etat du corpus — 6 papiers sur 12 a l'EGALITE STRICTE COMPLETE, tracabilite
100 % partout** : physrev, prepara, solgel_cuo, cbd_mnse, reduc_cu, broyage_na.

**Suites : 39 suites, 1002 assertions, 0 echec** — le verificateur des golds
tourne desormais A CHAQUE execution de la suite.

### 2026-08-21 — corpus etendu a 12 papiers : 4 familles NOUVELLES

Quatre papiers sans aucun rapport avec l'inorganique haute temperature du corpus
initial : CVD en phase gazeuse (`cvd_mos2`), electrodeposition en liquide
ionique (`electro_nico`), mecanosynthese (`broyage_na`), sels fondus
(`selfondu_cosi`). Golds annotes A LA MAIN (decision de Terry), chacun verifie
valeur par valeur contre sa source AVANT toute conclusion : le verificateur
couvre desormais `gold_corpus9.json`, soit 129 assertions de sourcage.

**Ce que le corpus initial ne pouvait pas reveler.** `broyage_na` est le premier
papier dont la voie complete n'a PAS UN SEUL palier thermique — et le papier
contient « 900 C for 12 h in air », qui appartient a un AUTRE compose cite par
reference. Le pipeline a refuse de le prendre : egalite stricte sur les trois
axes, temperatures comprises. La regle d'or tient sur le piege le plus direct
qu'on lui ait pose.

Mais la mesure, elle, ne le voyait pas. Un gold sans temperature donne
`temperatures_pct = None` — identique que le pipeline s'abstienne ou qu'il
fabrique. Seuls l'egalite stricte et les valeurs HORS GOLD portent le signal.
`test_gold_sans_temperature.py` verrouille ce point : sans lui, le tableau de
synthese afficherait « n/a » pour une invention comme pour une bonne reponse.

**Correctif 16 — l'atmosphere perdue sur l'ORDRE DES MOTS.** Tous les motifs
exigeaient « in/under <gaz> ». Des que la phrase enonce le gaz en SUJET, plus
rien :

| Citation | Avant | Apres |
|---|---|---|
| `argon (99.999%) was used as the carrier gas` (cvd_mos2) | — | Ar |
| `argon was bubbled in the electrolyte` (electro_nico) | — | Ar |
| `under DYNAMIC vacuum (10-3 mbar)` (selfondu_cosi) | — | vacuum |

Deux papiers sur quatre perdaient TOUTE leur atmosphere pour cette seule raison
de syntaxe — dans le cas de `cvd_mos2`, la seule mention du papier. Le vide,
lui, etait bien au vocabulaire : c'est le qualificatif entre « under » et
« vacuum » qui bloquait, sur l'etape de reaction de 6 h, la plus importante du
papier.

La boite a gants NE donne toujours rien quand aucun gaz n'est nomme : en deduire
« inerte » serait une invention. `broyage_na` ne passait que parce que
« Ar-filled » nomme l'argon.

**Correctif 17 — les durees citees mais non renseignees.** La recuperation
EXISTAIT (je l'avais crue absente) mais exigeait « for|during|pendant »
immediatement suivi du nombre. Sur `cvd_mos2` elle manquait les QUATRE durees du
gold, toutes ecrites en toutes lettres : « in 40 min », « for next 25 min »,
« for the next 10 min », « for about 10 min ». Et « followed by 6 hours » sur
`selfondu_cosi`. Prepositions elargies, deux qualificatifs admis.

« in 40 min » est un temps de MONTEE, « for 25 min » un palier : les deux
restent des durees — c'est ce qu'un chimiste releve — mais `duration_source`
garde la distinction. Aucune conversion en rampe °C/h : cette conversion
inventee a deja rendu l'egalite stricte inatteignable sur `combu_ferrite`.

L'exclusion `mixing/grinding` de cette recuperation est LAISSEE en place, sur
mesure : `broyage_na` tient sa duree de 2 h du modele lui-meme, l'exclusion n'a
donc rien coute, et la lever risquerait d'ajouter des durees parasites aux 8
papiers deja a l'egalite stricte.

**Correctif 18 — un qualificatif de FORME faisait perdre le compose.** Le
silicium, reactif PRINCIPAL de `selfondu_cosi`, refuse trois fois de suite :
« la citation fournie ne mentionne pas 'Si nanoparticles' ». Il y etait pourtant
deux fois — « silicon nanoparticles » dans la phrase des reactifs, « 63.2 mg Si
nanoparticles » dans la phrase operatoire. `_compound_named_in("Si", ...)` rend
True ; `"Si nanoparticles"` rend False, la formule ne se parsant plus, donc le
repli par composition elementaire est saute.

**Sixieme fois** dans ce projet que l'outillage accuse le modele a tort. Le
modele suivait la formulation exacte de l'article. On retire desormais les mots
de FORME (nanoparticules, poudre, feuille, monocristal...), jamais les mots de
CHIMIE — retirer « acetate » ferait passer n'importe quel sel de cuivre pour du
cuivre metal. Une formule qui n'etait QUE de la morphologie ne rend plus la
chaine d'origine : elle matcherait litteralement dans le texte et rouvrirait la
porte que la regle d'or ferme.

Deux de mes attentes de test contredisaient une borne DELIBEREE du projet — un
mot d'element NU ne prouve jamais un metal, sinon « copper » suffirait a prouver
du cuivre metal dans tout papier parlant d'oxyde de cuivre. J'ai corrige le
test, pas la borne : on n'affaiblit pas une regle anti-invention pour faire
verdir sa propre mesure. Le cas reel passe parce que « silicon nanoparticles »
fait deux mots.

**Correctif 19 — le TUBE est un contenant.** `quartz tube` et `Schlenk tube`
refuses (« ni contenant ni appareil »), alors que le tube scelle est le
contenant le plus courant de la chimie du solide et des sels fondus, et que sa
nature decide de la faisabilite au meme titre qu'un creuset. Le piege etait
immediat : « tube furnace » est un APPAREIL, et l'ajouter sans precaution ferait
passer le four pour le contenant — l'inversion exacte que la distinction
contenant/appareil existe pour empecher. Exclusion explicite des tournures
« tube + furnace/oven/reactor/mill/kiln ».

**Ce que les garde-fous ont correctement REFUSE sur `selfondu_cosi`**, et qu'il
faut lire comme un succes et non comme un manque :
- `temperature_c=25` et `duration_h=0` pour « cooled down to room temperature » ;
- `duration_h=24` pour « dried under vacuum DURING THE NIGHT » — le modele
  comblait un trou non chiffre, la garde l'a arrete ;
- `temperature_c=300` attache a une citation qui ne le contient pas (le 300 est
  dans la phrase precedente).
Le seul mecanisme qui a mal juge est celui du contenant, corrige ci-dessus.

**Une erreur de MON gold, corrigee.** Le comparateur comptait « FAUX » les
ratios `LiI 0,63` / `KI 0,37` du modele. Le papier ecrit pourtant « (molar ratio
LiI:KI 0.63:0.37) » : j'avais mis des millimoles (21,7 et 12,7) dans un champ de
rapport molaire. **Le modele avait raison, le gold avait tort.** Deux echelles
coexistent dans ce papier et ne se melangent pas — bain de sels en fractions
molaires, reactifs en millimoles.

**Correctif 20 — 16 noms usuels sur 31 manquaient a la table, dont TOUS les
acides mineraux.** `normalize_compound_name("nitric acid")` rendait `None`. Sur
`electro_nico`, « nitric acid » et « ethylamine » — les deux reactifs de la
premiere synthese du papier — etaient donc refuses a chaque tour, alors qu'ils
sont ecrits en toutes lettres dans la citation choisie par le modele. Effet
mesure :

| | avant | apres |
|---|---|---|
| appels acceptes | 6 / 14 | **13 / 13** |
| precurseurs | 50 % | **100 %** |
| ratios molaires | 0 % | **100 %** |
| duree du papier | 234 s | **87 s** |

Les huit refus faisaient boucler le modele sur les memes appels : le temps de
traitement a ete divise par pres de trois en supprimant du travail inutile, pas
en accelerant quoi que ce soit. **Septieme cas** ou l'outillage accusait le
modele.

**Correctif 21 — le message de refus rendu ACTIONNABLE.** Sur `cvd_mos2`, le
modele a cite « the furnace was FIRST heated to 300 °C » la ou le papier ecrit
« FIRSTLY » : un mot d'ecart sur quinze, l'etape refusee deux fois, le palier a
300 °C perdu. Aucun garde-fou n'est assoupli — la citation doit toujours etre
EXACTE et les valeurs restent validees contre elle. On rend simplement au modele
la phrase du texte dont il s'est le plus approche, pour qu'il la recopie. Un
seuil de recouvrement de 50 % empeche de suggerer une phrase au hasard, ce qui
l'orienterait vers une citation sans rapport avec son intention.

**Correctif 22 — et une decision que la mesure a DEMENTIE.** La recuperation de
duree excluait `mixing` et `grinding`. J'avais decide de laisser l'exclusion,
faute de cout mesure : `broyage_na` tenait sa duree du modele lui-meme. La
non-regression du corpus5 a montre le contraire — l'etape 1 de `hydro_czts` est
un `mixing` dont la citation dit « dispersed ... FOR 5 MIN », le modele n'avait
pas rempli le champ, et l'exclusion bloquait le rattrapage. C'etait la
difference entre l'egalite stricte sur les durees et son echec.

L'exclusion est levee en gardant ce qu'elle protegeait : pour un melange ou un
broyage, la citation ne doit porter qu'UNE SEULE duree distincte. « stirred for
10 min and then heated at 180 °C for 12 h » ne donne donc rien — c'est
exactement l'ambiguite que l'exclusion visait.

**Non-regression des 8 papiers acquis : aucune perte.** `solgel_cuo`,
`cbd_mnse` et `reduc_cu` restent a l'egalite stricte complete ; `combu_ferrite`
est inchange. `hydro_czts` a gagne l'egalite stricte sur les temperatures et
recupere 180 °C et 12 h.

**Decisions de Terry (21/08)** :
- *Colonnes nommees au schema* pour le potentiel electrique et les parametres de
  broyage, plutot qu'un champ libre. Changement de schema APPROUVE. Elles seront
  remplies par post-traitement deterministe d'abord : trois mesures ont etabli
  que tout ajout a l'interface du MODELE se paie ailleurs.
- *Deduction du ratio depuis la formule cible AUTORISEE*, sur preuve
  (« stoichiometric » dans la citation) et TRACEE (`origine=deduit_formule`),
  pour qu'un audit puisse toujours separer ce qui a ete lu de ce qui a ete
  calcule.

**Suites de non-regression : 37 suites, 673 assertions, 0 echec.**

**Trois trous de FAMILLE, hors de portee du schema actuel** — a arbitrer avec
Terry, un changement de schema lui revenant :
- le potentiel impose (-1,3 V/Ag/Ag+) est LA consigne d'une electrodeposition ;
- la frequence et la charge de billes sont LES consignes d'une mecanosynthese ;
- « stoichiometric amounts » sans aucun chiffre : le rapport 3:1 de Na3P se
  deduit de la formule cible, enoncee dans la phrase. Lecture ou invention ?
  Les deux inferences de ratio deja en place penchent pour la lecture.

**Suites de non-regression : 32 suites, 581 assertions, 0 echec.**

### 2026-08-20 (nuit) — concentration et pH par POST-TRAITEMENT

Suite directe du champ libre retire : capter la MEME information par la voie qui
n'a jamais rien coute. Le contraste est la demonstration la plus directe du
principe qui structure le projet.

| Voie | Resultat |
|---|---|
| interface du modele (`extra_parameters`) | **4 papiers degrades sur 7**, champ jamais utilise |
| post-traitement deterministe | **6 concentrations recuperees, 0 regression** |

`cbd_mnse`, tombe a 3 etapes avec le champ libre, reste a 100 % et gagne sa
concentration. `reduc_cu` obtient ses trois molarites (CuSO4 0,1 M, ascorbique
0,2 M, NaOH 1 M) — il avait ses reactifs et ses volumes, mais « 50 mL d'acide
ascorbique » ne permet pas de peser sans la molarite.

**Quatre pieges, tous trouves sur donnees reelles, aucun anticipe** :
- `HCl` (donne a 8 %) heritait du « 0.001 M » du nitrate voisin. La regle est
  devenue l'ADJACENCE, avec la PARENTHESE comme seul discriminant du cas ou la
  concentration SUIT le compose (« CuSO4 5H2O (0.1 M) »).
- `Mn(NO3)2` etait introuvable dans sa propre citation, qui ecrit « manganese
  nitrate » en toutes lettres. Le projet savait repondre par oui/non
  (`_compound_named_in`) mais pas donner la POSITION : `_position_du_compose`
  ajoute. Sans lui, la concentration reste introuvable sur exactement les
  papiers qui la portent — ceux de chimie en solution.
- « adjust the pH ... to 10, 9, 8 » pose TROIS bains. En retenir un attribuerait
  a une etape ce qui decrit trois experiences : abstention.
- Distinguer « 10, 9, 8 » de « 10, 2 mL of HCl » a demande un retour en arriere
  d'expression reguliere : `\s*(?![a-zA-Z])` se satisfait en ne consommant aucun
  espace, et juge alors l'espace au lieu de la lettre.

Un pH de RESULTAT (« the best crystalline at pH: 9 ») n'est jamais pris pour une
consigne : un marqueur de reglage est exige.

**Suites de non-regression : 29 suites, 492 assertions, 0 echec.**


### 2026-08-20 (soir) — champ LIBRE ouvert au modele + 2 correctifs de mesure

**Vocabulaire pilote par le corpus** (`tools/vocabulaire_parametres.py`). Ecrit
AVANT de toucher au schema — mesurer ce que les papiers portent avant de
demander quoi que ce soit au modele. Six grandeurs candidates, dont **trois
FAUX POSITIFS** ecartes en verifiant les contextes : « 5,28 nm » = tailles de
grain, « 6,72 g » = densites, « 42 Hz » = plage d'un LCR-metre. Des RESULTATS,
pas des parametres. L'outil propose, il ne decide pas.

Deux grandeurs reelles, et elles valident la decision de ne PAS predefinir la
liste :
- **concentration molaire** : 7 papiers sur 8, dans les phrases operatoires,
  sans aucune colonne au schema apres trente correctifs ;
- **pH** : 2 papiers seulement, mais il y decide la phase obtenue (« At pHs of
  11 and 10 the MnSeO4 structure was observed »). Aucune liste anticipee pour un
  projet ne sur des iridates ne l'aurait contenu.

**Choix de Terry : ouvrir un champ libre** plutot que promouvoir des colonnes
nommees. `extra_parameters` sur `add_operation`, dictionnaire PLAT (un 8B produit
mal le JSON imbrique), empreinte minimale sur l'interface. La regle d'or s'y
applique : chaque valeur doit figurer dans la citation de l'etape, sinon elle est
ecartee entree par entree.

**Impact mesure — CHAMP RETIRE, causalite ETABLIE** :

| Papier | Effet |
|---|---|
| solgel_cuo | intact, egalite stricte complete |
| hydro_czts | intact, egalite stricte complete |
| reduc_cu | perd une duree (30 min d'agitation) |
| cbd_mnse | **effondre** : 3 etapes au lieu de 6, aucune chauffe |

Mesure complete : **4 papiers degrades sur 7** (cbd_mnse, reduc_cu,
combu_ferrite, prepara), 3 intacts (solgel_cuo, hydro_czts, physrev).

**TEST CONTROLE.** Les 4 papiers degrades relances champ RETIRE, sans aucune
autre modification :

| Papier | Avec le champ | Sans |
|---|---|---|
| cbd_mnse | 3 etapes, 0 % temperatures | 100 % partout, egalite stricte |
| reduc_cu | 50 % durees | 100 % partout, egalite stricte |
| prepara | 1 valeur, 0 % temperatures | 100 % partout, egalite stricte |
| combu_ferrite | 83,3 % precurseurs | 100 % precurseurs |

**4 degrades, 4 restaures.** La causalite n'est plus une hypothese.

Le fait le plus parlant : le modele n'a utilise le champ sur AUCUN papier. Il
n'a rien gagne — il a seulement eu un parametre de plus a considerer.

> **Lecon, deuxieme mesure du meme phenomene.** Apres le durcissement du prompt
> (precurseurs 100 -> 20 %), voici le durcissement de l'INTERFACE : un seul
> parametre optionnel de plus dans un outil suffit a degrader un 8B. Ce n'est pas
> le texte de la consigne qui compte, c'est la SURFACE totale presentee au
> modele. Tout ce qui passe par lui se paie ailleurs ; le post-traitement
> deterministe, lui, ajoute sans retrancher.

**Etat retenu** : champ retire de l'interface, derriere `SYNTHGRAPH_EXTRA_PARAMS=1`.
La VALIDATION reste active — s'il revient un jour avec un modele plus capable,
il obeit deja a la regle d'or. Le test de non-regression passe dans les DEUX
etats.

**Ce qui reste acquis** : la concentration molaire manque au schema sur 7 papiers
sur 8, et le pH decide de la phase obtenue sur `cbd_mnse`. Ces deux grandeurs
sont a recuperer par POST-TRAITEMENT deterministe depuis les citations — la voie
qui n'a jamais rien coute.

**Correctif de mesure — arrondi des minutes.** « 5 min » est stocke 5/60 =
0,08333 h ; le retour en minutes donne 4,998, qui ne correspond plus a « 5 ».
La valeur etait declaree NON PROUVEE alors que sa citation dit « for 5 min under
constant stirring ». Tracabilite de `hydro_czts` : 87,5 % -> 100 %.

**QUATRIEME erreur dans mon gold** : la dispersion initiale de `hydro_czts` dure
5 minutes, le papier l'ecrit, et `durations_h` ne la listait pas. L'extraction la
trouvait et la mesure la comptait « hors gold » — donc a tort. Ajoutee.

**Suites de non-regression : 28 suites, 475 assertions, 0 echec.**


### 2026-08-20 — minimum de refaisabilite + tri des trous (decisions de Terry)

**Le constat qui a motive le durcissement.** `heating` n'exigeait que
`target_temperature_c` — ni duree, ni atmosphere — et `mixing` n'exigeait RIEN.
Un chimiste ne peut refaire ni l'un ni l'autre : les scores eleves mesuraient des
criteres trop faibles.

**`MINIMUM_REFAISABILITE`** (couche SEPAREE de `STEP_PARAMETERS`, pour que le
motif du durcissement reste lisible et reversible d'une ligne) :
heating = +duree +atmosphere ; calcination/annealing/sintering/soak = +atmosphere ;
cooling = +vitesse ; mixing/grinding = +methode ; washing = +repetitions ;
drying = +temperature +duree. Chaque trou porte `origine: minimum_refaisabilite`.

**Effet mesure** : 55 trous requis sur les 8 papiers, dont 47 dus au durcissement.
La FIDELITE AU GOLD est inchangee (precurseurs, ratios, durees, temperatures) —
le durcissement n'ajoute pas d'erreur, il declare ce qui manquait en silence.
`cbd_mnse` gagne meme son dioxane (87,5 % -> 100 %).

**Contradiction corrigee** : l'audit declarait `crystal` REFAISABLE pendant que
le graphe portait 18 trous « required » sur ce meme papier. Deux definitions de
la reproductibilite coexistaient sans se parler. L'audit lit desormais les trous
declares par le graphe — c'est cette definition qui fait foi.

**TRI DES TROUS : rattrapable vs incomblable.** Decouverte qui change la lecture
des 55 trous : **6 papiers sur 8 ne nomment AUCUNE methode de melange**. Ces
trous sont donc INCOMBLABLES — aucune amelioration du pipeline ne les fermera.
Sans cette distinction, on chasserait un bug inexistant.

L'audit separe maintenant :
  - RATTRAPABLE : le papier porte l'information, le pipeline l'a manquee ;
  - INCOMBLABLE : la source ne la donne pas (limite du papier, pas du systeme).

Sur le corpus5 : 25 rattrapables / 11 incomblables. Le plus actionnable est
`vessel` la ou le papier le nomme (detecteur de transfert a ameliorer) ;
l'atmosphere de `cbd_mnse`/`combu_ferrite` et la methode de 6 papiers ne se
fermeront jamais.

Le contenant reutilise son propre detecteur (verbe de transfert exige) plutot que
la table generique : sans cela, l'audit le classait « rattrapable » sur des
papiers ou il venait d'ecrire qu'aucun contenant n'est nomme — deux verdicts
opposes dans le meme rapport.

**Decisions de Terry ce jour** : golds toujours annotes A LA MAIN (pas de gold
automatique) ; minimum de refaisabilite tel que propose, atmosphere comprise ;
effort porte sur l'APPROFONDISSEMENT des 8 papiers plutot que sur l'elargissement.

**Suites de non-regression : 19 suites, 301 assertions, 0 echec.**


### 2026-08-20 — correctif 15 : une FORMULE prouvee par une enumeration de NOMS

**`prepara` passe de 40 % a 100 % de precurseurs.** Le papier le plus resistant
du corpus (1957, OCR degrade) est resolu.

**Le modele avait raison depuis le debut.** Il proposait `SrCO3`, `Sr(NO3)2` et
`Sr(OH)2` — refuses comme « absents du texte source ». La phrase
« the reaction between iridium metal powder and strontium oxide, carbonate,
nitrate or hydroxide » designe pourtant QUATRE sources de strontium.

Cause : `_enumerated_compound` a ete ecrit pour des NOMS, qu'il decoupe en
prefixe + suffixe (« strontium » ... « carbonate »). Le modele fournit des
FORMULES, et « SrCO3 » normalise ne fait qu'UN SEUL MOT — la fonction abandonnait
a la premiere ligne. Le projet savait traduire nom -> formule ; il manquait le
chemin INVERSE.

`_enumerated_by_name()` cherche donc, dans `COMPOUND_NAME_TO_FORMULA`, les noms
qui designent le compose (par composition elementaire) et teste l'enumeration
sur eux.

**Faux positif ferme au passage** : `IrO2` etait accepte parce que
« strontium-iridium oxide » — le nom du PRODUIT Sr2IrO4 — contient « iridium
oxide » par accident de sous-chaine. On exige desormais une VRAIE enumeration :
prefixe et suffixe separes par au moins un mot, les mentions litterales etant
deja couvertes par `_compound_named_in`.

**Etat du corpus : 7 papiers sur 8 a 100 % de precurseurs** (`cbd_mnse` 87,5 %),
**tracabilite 100 % sur les 8**.

> **Lecon, quatrieme occurrence de la nuit** : un « echec du modele » etait un
> defaut de l'OUTILLAGE. Le motif est trop constant pour etre fortuit — la
> chaine de validation a ete faconnee sur des iridates cites par FORMULE dans
> des TABLEAUX, et elle decroche des qu'un papier s'en ecarte (noms en toutes
> lettres, enumerations, prose, OCR ancien). Mesurer avant de conclure sur le
> modele.

**Suites de non-regression : 17 suites, 270 assertions, 0 echec.**


### 2026-08-20 — correctifs 13 (solvant) et 14 (hydrates au point) 

**13. Le SOLVANT etait omis.** L'eau manquait sur `reduc_cu` et `cbd_mnse` — et
le modele ne l'avait JAMAIS proposee (aucun rejet a son nom) : omission pure, pas
un refus du validateur. Sans solvant la recette n'est pas executable, et toute la
chimie en solution est concernee.

`RouteBuilder._recover_solvents()` repere les tournures reelles du corpus
(« dissolved/dispersed in X », « filled with X », « completed with X »,
« X was used for all the experiment ») et passe par `add_precursor`, donc TOUS
les garde-fous existants s'appliquent : le compose doit etre nomme par la phrase,
qui devient sa citation.

Deux exclusions propres a ce cas, toutes deux tirees d'un piege reel :
  - CARACTERISATION — `hydro_czts` ecrit « dispersed into ethanol by ultrasound »
    pour une observation TEM, pas pour la synthese ;
  - LAVAGE — « washed with ethanol » ne fait pas de l'ethanol un milieu
    reactionnel.

Resultat sur les 8 papiers : +H2O sur `cbd_mnse` et `reduc_cu` — exactement les
deux ou l'audit la signalait manquante — et **0 ajout partout ailleurs**.

Deux doublons corriges au passage, tous deux dus a une deduplication par CHAINE
au lieu de COMPOSITION : l'amidon rajoute en `C6H10O5` alors qu'il figurait en
`(C6H10O5)n` (et etiquete « solvant » alors qu'il est l'agent de coiffage), et
l'eau rajoutee sur `combu_ferrite` qui la portait deja sous « deionized water ».

**14. Hydrates notes avec un POINT — defaut GRAVE, trouve par hasard.**
`Fe(NO3)2.9H2O` etait parse **N=2,9 et O=9,7** au lieu de N=2, O=15, H=18 : le
point ASCII etait lu comme un decimal.

Ce n'est pas cosmetique. Le bilan elementaire deterministe sert de **VETO** dans
le pipeline (un bilan en echec force REJECT quoi que dise le LLM) : une
stoechiometrie corrompue pouvait donc **rejeter une extraction correcte ou en
valider une fausse**. Il alimente aussi `_composition_key`, utilise pour
l'equivalence nom<->formule dans le validateur, le comparateur, l'audit et le
document. Trois precurseurs de `combu_ferrite` sont ecrits ainsi, et la notation
est courante dans la litterature.

Correctif dans `parse_composition` : un point suivi d'un coefficient puis de H2O
est un SEPARATEUR d'hydrate, jamais un decimal. Non-regression verifiee sur les
vrais decimaux — `Sr2.5Ir1O4` garde son 2,5.

> **Lecon** : ce defaut vivait dans le validateur le plus critique du projet et
> n'a ete vu qu'en inspectant des cles de composition pour une TOUTE AUTRE
> raison. Les garde-fous doivent eux-memes etre testes sur des donnees reelles.

**Suites de non-regression : 16 suites, 254 assertions, 0 echec.**


### 2026-08-20 — correctif 12 : contenant OPERATION PAR OPERATION

**Choix de Terry.** Interroge sur un champ `vessel` au niveau de la VOIE (donc un
changement de schema du graphe), il a repondu : « il faudrait reussir a
l'extraire operation par operation ». Choix meilleur que ma proposition — il
evite le changement de schema ET rend compte des protocoles a transferts
multiples, ou le recipient change en cours de route (un champ unique l'ecraserait).

**`RouteBuilder._recover_vessel_per_step()`.** Principe chimique : un contenant
nomme lors d'un TRANSFERT vaut pour les operations suivantes jusqu'au transfert
suivant — c'est ainsi qu'on lit un protocole. Trois garde-fous :
  - VERBE DE TRANSFERT exige. Sans lui, deux fausses pistes reelles passaient :
    « VialTweeter » (sonicateur de marque, `vial` pris dans un mot) et « stored
    in glass vial for further analysis » (stockage APRES synthese).
  - propagation vers l'AVANT uniquement ;
  - un seul contenant nomme dans le papier leve l'ambiguite pour les etapes
    anterieures (`prepara` 1957 decrit ses nacelles apres coup) ; des qu'il y en
    a deux, on s'abstient.
Chaque attribution conserve la phrase BRUTE qui la prouve (`vessel_citation`),
meme dispositif que `atmosphere_citation`.

**Piege de nommage.** `vessel` est deja un ALIAS de `crucible_material` dans
`step_schema.py`, champ reserve a certains types d'etape : la valeur etait donc
SUPPRIMEE sur un `mixing` ou un `washing`, et l'audit continuait de signaler un
contenant manquant alors qu'il avait ete calcule. Renomme `vessel_name`, non
mappe, il atterrit dans `other_parameters` avec sa preuve — sans toucher au schema.

**Resultat sur les 8 papiers** : `crystal` 40/40 etapes (creuset de platine),
`hydro_czts` 6/6 (bombe de digestion), `cbd_mnse` 6/6 (becher), `prepara` 5/5
(nacelles platine/silicate de zirconium). Les 4 autres restent vides — et c'est
CORRECT, leurs papiers ne decrivent aucun recipient reactionnel.

**Deuxieme defaut ferme : `equipment` n'etait pas verifie sur sa NATURE.**
`equipment='room temperature'` etait accepte sur `hydro_czts` — la valeur figure
bien dans le texte, donc elle passait l'ancrage, sans etre un equipement. Une
valeur doit desormais designer un CONTENANT ou un APPAREIL ; les deux motifs de
refus restent distincts dans les messages.

**Audit aligne** : il exige lui aussi un verbe de transfert (il reclamait le
« glass vial » de stockage de `reduc_cu`), et ses bornes de mots evitent de
matcher « Vial » dans « VialTweeter ».

**Suites de non-regression : 14 suites, 222 assertions, 0 echec.**


### 2026-08-20 — correctif 11 : atmosphere recuperee + gold CORRIGE

**Le constat.** L'atmosphere n'etait extraite sur AUCUN des 5 papiers du corpus5,
alors qu'elle figure dans les citations que le modele utilise deja :
`solgel_cuo` porte « dried in a muffle furnace IN AIR at 60 °C » et « annealing
in a muffle furnace IN AIR at 400 °C ». Meme schema que les etapes de traitement
final : la preuve est presente, seule la declaration manque.

**`RouteBuilder._recover_atmosphere()`.** Pour chaque etape sans atmosphere, on
cherche un marqueur dans SA citation. Trois abstentions : etape deja renseignee,
marqueur precede d'une NEGATION dans la meme proposition, aucun marqueur.
Le mot NU ne suffit jamais — « air-sensitive », « air quality », « nitrogen
adsorption isotherm » ne donnent rien ; il faut la tournure qui designe un
milieu reactionnel (`in air`, `under flowing argon`, `vacuum oven`...).

Verifie sur les 8 sources REELLES : crystal +2 (air), solgel_cuo +2 (air),
prepara +1 (air), hydro_czts +1 (vacuum, etape de sechage), et **0 sur les 4
autres** — aucun faux positif. `reduc_cu` ne recupere rien malgre « in ambient »
et « inert gas » presents dans sa source : negation et specificite jouent.

**J'AI CORRIGE MON PROPRE GOLD.** Trois atmospheres y etaient des INFERENCES de
chimiste, pas des relevés du texte :

| Papier | Mon annotation | Ce que dit le papier |
|---|---|---|
| `combu_ferrite` | « air (combustion auto-propagee) » | **rien** |
| `cbd_mnse` | « air » | **rien** |
| `reduc_cu` | « air (sans gaz inerte) » | « ambient atmospheric pressure », « without inert gas » — une pression et une NEGATION |
| `solgel_cuo` | « air » | « in air » x11 (correct) |

Un gold qui contient ce que la source n'enonce pas viole la meme regle d'or que
l'extraction, et faussait la mesure DANS LE SENS DE L'INDULGENCE : le pipeline
aurait pu « reussir » en devinant. Les trois entrees portent desormais le piege
correspondant.

**Comparateur** : un gold declarant l'atmosphere absente du texte ne fournit
aucune reference — le critere devient `n/a`, plus `KO`. Sinon `hydro_czts` etait
compte en echec pour avoir correctement extrait « vacuum oven » de son sechage.

**Corpus5 apres correctif** : 4 papiers sur 5 a 100 % de precurseurs,
tracabilite 100 % partout, `solgel_cuo` complet sur tous les criteres mesures.
Les 4 « n/a » ne sont pas des echecs deguises : ces papiers ne DISENT pas leur
atmosphere, et le pipeline s'abstient au lieu de deviner.

**Suites de non-regression : 12 suites, 192 assertions, 0 echec.**


### 2026-08-20 — correctif 10 : recuperation des etapes de traitement final

**Le blocage.** `crystal` obtenait 100 % sur tous les criteres du comparateur et
restait IRREALISABLE : le rincage a l'eau distillee qui separe les cristaux du
flux residuel n'etait jamais extrait. Sans lui on recupere un bloc de SrCl2 fige
et aucun cristal. Le broyage initial manquait aussi.

**La cause, mesuree.** Sur les papiers en PROSE (corpus5) le modele declare
naturellement `mixing`, `washing`, `drying`, `centrifugation`. Le deficit est
propre aux papiers TABULAIRES : les conditions vivent dans un tableau, le
traitement final dans le texte courant, et le modele suit le tableau. Ce n'est
donc pas une affaire de prompt (budget deja consomme par le durcissement) mais
de post-traitement deterministe.

**`RouteBuilder._recover_workup_steps()`.** L'etape nait d'une PHRASE REELLE du
papier, qui devient sa citation ; aucun parametre numerique n'est deduit. Trois
abstentions : si le modele a deja declare une etape de la famille, si aucune
phrase ne porte le verbe, si la phrase n'a aucun indice de contexte (ce dernier
ecarte « the detector was washed before calibration »).

**Cible atteinte** : `crystal` passe **REFAISABLE** — 10 voies, 40 etapes
(cooling, heating, mixing, separation), 57 valeurs toutes prouvees. Premier
papier du corpus a franchir les 6 criteres de `tools/audit_reproductibilite.py`.

**Motifs elargis apres `cbd_mnse`** : « The mixture is filtered before being
added to the chemical bath » etait ecarte faute d'un mot de contexte reconnu, et
« The solution is mixed at 1000 rpm » faute d'une formulation prevue. Verification
sur les 8 sources REELLES apres elargissement : `cbd_mnse` gagne exactement ses
2 etapes manquantes, **les 7 autres n'en gagnent aucune** — pas de sur-declenchement.

**Deux fausses alertes de l'audit corrigees** :
- reprocher une etape que le PAPIER ne decrit pas (`crystal` n'a aucun sechage,
  et son gold n'en exige aucun) ;
- confondre « contenant nomme dans le papier mais non extrait » (defaut du
  pipeline) et « aucun contenant nomme » (limite de la SOURCE, que le pipeline
  ne peut combler sans inventer). `physrev` releve du second cas : il est au
  maximum de ce que sa source permet.

**Etat des 8 papiers** : 6 a 100 % de precurseurs, tracabilite 100 % PARTOUT.
`cbd_mnse` 75 %, `prepara` 40 % (OCR 1957).
**Suites de non-regression : 11 suites, 173 assertions, 0 echec.**

**Reste ouvert** : l'atmosphere n'est jamais extraite sur le corpus5 ; `prepara`
resiste (2 reactifs, proportions, atmosphere).


### 2026-08-19 (fin) — durcissement du prompt VALIDE + 2 trous anti-invention fermes

**Durcissement retenu** (decision de Terry). UNE phrase greffee sur le point 2 de
la liste MÉTHODE, +178 caracteres :
> Renseigne `equipment` avec le CONTENANT quand le texte le nomme (creuset de
> platine, autoclave, bombe de digestion, becher) : sans lui la synthese n'est
> pas refaisable.

Cible RESSERREE par `tools/audit_reproductibilite.py` : les etapes non thermiques
etaient deja bien extraites des que le papier les decrit en prose (`mixing`,
`washing`, `drying`, `centrifugation`, `grinding` presents sur les 5 nouveaux
papiers) — le deficit vu sur les iridates venait de leur format TABULAIRE. Seul
le contenant manquait sur 8/8. Ne pas reclamer l'inutile a evite de payer le
prompt au prix fort.

**Resultat mesure sur les 8 papiers — AUCUNE regression, 5 gains :**

| Papier | Precurseurs | Durees | Autre |
|---|---|---|---|
| crystal | 100 % = | 100 % = | tracabilite 57 valeurs a 100 % (43 avant) ; **`platinum crucible` extrait** |
| physrev | 100 % = | 100 % = | inchange |
| prepara | 20 -> **40 %** | 0 -> **100 %** | **`combustion boats` extraits** |
| hydro_czts | 100 % = | 33,3 % = | contenant manque encore |
| solgel_cuo | 100 % = | 66,7 -> **100 %** | `muffle furnace` |
| combu_ferrite | 83,3 -> **100 %** | 100 % = | ethanol enfin declare |
| cbd_mnse | 62,5 -> **75 %** | 100 % = | `beaker` correct |
| reduc_cu | 100 % = | 100 % = | inchange |

Contraste avec le durcissement du matin (precurseurs 100 -> 20 %) : la difference
n'est pas le PRINCIPE mais la FORME — quelques mots greffes dans une consigne
existante, pas un paragraphe ajoute en fin de prompt.

**Limite honnete** : le modele donne surtout l'APPAREIL (four, etuve, agitateur)
plutot que le CONTENANT. 3 papiers sur 8 livrent leur contenant reel. La
distinction est chimiquement decisive : un four se remplace, la matiere d'un
creuset non.

**8. Vitesse prouvee par SA VALEUR, pas par une notation.** `cooling_rate_c_per_h=0`
etait accepte sur « Sr214#1 ... 1300 C -> (8 C/h) 900 C -> RT » : il suffisait que
la citation contienne UNE notation de vitesse. Quatre etapes de `crystal`
portaient ainsi une vitesse de 0 C/h inventee (tracabilite 100 -> 92,2 % — l'ancien
100 % sur 43 valeurs etait donc partiellement faux, il ne mesurait pas ce qu'il
pretendait). Desormais le nombre doit figurer dans la citation.

**9. `equipment` ancre dans le texte source.** Des que le prompt a cite des
exemples de contenants, le modele en a recopie un : `equipment='becher'` sur
`hydro_czts`, papier ANGLAIS disant « acid digestion bomb ». Fuite d'exemple de
prompt — mode d'echec deja documente dans CLAUDE.md, rejoue a l'identique. Le
champ etait du texte libre admis SANS preuve. Il doit maintenant exister dans la
source.

> **Lecon** : durcir un prompt cree une surface d'invention nouvelle. Tout champ
> ajoute a une consigne doit etre ancre AVANT de durcir, pas apres.

**Etat des suites de non-regression : 10 suites, 159 assertions, 0 echec.**


### 2026-08-19 (nuit) — correctifs 6-7 et un defaut que J'AI introduit

**6. Ratios molaires deduits des quantites citees.** Sur `hydro_czts` le modele
relevait « 2 mmol / 2 mmol / 1 mmol / 4 mmol » dans `amount` : dans une meme
reaction ces nombres SONT les rapports molaires, mais la mesure affichait 0 %.
Deduction deterministe ajoutee, avec quatre garde-fous — unites MOLAIRES
uniquement (les grammes exigeraient les masses molaires, donc une inference),
une seule unite pour tous, au moins deux composes, et une plage (« 0-3 mmol »)
ne donne rien.

**DEFAUT QUE J'AI INTRODUIT, puis corrige.** La premiere version exigeait que le
nombre figure dans la citation via `_num_in`. Insuffisant : sur `hydro_czts` la
citation attachee etait la phrase de PURETE (« were of analytical grade and used
as received »), sans aucune quantite — et le « 2 » valide venait de **`2H2O`
dans la formule**. Deux ratios avaient ete inscrits sur une preuve inexistante,
soit exactement l'invention silencieuse que la regle d'or interdit. Detecte en
inspectant les donnees REELLES : les tests hors ligne passaient, parce qu'ils
avaient ete ecrits avec une citation propre.
Correctif : la citation doit porter le nombre **avec son unite**
(`re.search(rf"(?<![\d.]){nombre}\s*{unite}", citation)`). Sur ce cas la
deduction ne produit plus rien — resultat honnete, le modele ayant cite la
mauvaise phrase. Piege verrouille par un test dedie.
> **Lecon** : un test ecrit a partir du cas ideal ne prouve rien. Tout garde-fou
> doit etre confronte aux artefacts reels avant d'etre declare sur.

**7. Mesure alignee sur la composition elementaire.** `Cu(C2H3O2)2` (modele) et
`Cu(CH3COO)2` (gold) designent l'acetate de cuivre ; comparer les CHAINES faisait
echouer une extraction parfaite. `compare_tc_gold.py` compare desormais aussi la
composition, comme le validateur.

**Resultats corpus5 apres correctifs** (precurseurs) : `reduc_cu` 100 %,
`solgel_cuo` 0 % -> **100 %**, `hydro_czts` **100 %**, `combu_ferrite` 83,3 %,
`cbd_mnse` 25 % -> **62,5 %**.

> **Lecon dominante de l'extension** : a TROIS reprises un « echec du modele »
> etait un echec de l'outillage (validateur trop litteral, normaliseur incomplet,
> comparateur textuel). Verifier la mesure avant de conclure sur le modele.

### 2026-08-19 (soir) — 5 correctifs reveles par l'extension hors iridates

L'extension a 5 familles de synthese non ceramiques a mis au jour des defauts
INVISIBLES sur les iridates. Tous corriges, tous testes hors ligne
(**20 + 13 + 8 assertions nouvelles, 92 de non-regression, 0 echec**).

| # | Defaut | Cause | Correctif |
|---|---|---|---|
| 1 | Sequence ambigue | le modele donne `order=1` a deux etapes distinctes | renumerotation sequentielle sur collision |
| 2 | Palier descendant etiquete `heating` | `1100 -> 1300 -> 900 °C` : on DESCEND a 900 | requalification en `cooling` d'apres le signe de la difference, fail-safe si une temperature manque |
| 3 | Precurseurs corrects REFUSES | citation nommant le compose en toutes lettres (« copper acetate ») vs formule fournie | equivalence par bilan elementaire deterministe |
| 4 | Organiques et eau non reconcilies | absents du dictionnaire `normalize_compound_name` | ajout cysteine, EDTA, ascorbique, TEA, amidon, alcools, dioxane, glycine, PVP, CTAB, eau |
| 5 | Un ratio non prouve emportait le REACTIF | `add_precursor` tout-ou-rien la ou `add_operation` est tolerant par champ | le precurseur est conserve, le ratio non prouve est JETE (regle d'or intacte) |

**Le cas d'ecole (`solgel_cuo`)** : le pipeline annoncait 0 % de precurseurs. Le
modele avait trouve les BONS reactifs — c'est le validateur qui les refusait, la
citation les nommant « copper acetate » et « ammonium carbonate ». Les noms en
toutes lettres sont la norme en chimie de solution : ce refus condamnait tout un
pan du corpus, invisible tant qu'on ne testait que des iridates cites par formule.

**Deux trous fermes au passage, trouves par les tests** :
- une formule se normalisant en chaine vide matchait TOUT (`"" in texte` est
  toujours vrai) — trou dans la garde anti-invention ;
- le balayage ne couvrait que les groupes de 2-3 mots : `water`, `EDTA`, `TEA`,
  `starch` etaient invisibles. Etendu a 1 mot, MAIS un nom d'element seul ne vaut
  jamais preuve (sinon « copper acetate » prouverait le cuivre metallique) :
  deux elements distincts exiges.

**Biais de MESURE corrige** : `compare_tc_gold.py` classait toute valeur <= 100
en duree. Vrai sur les iridates (temperatures > 100 °C, durees < 100 h), FAUX des
qu'un sechage se fait a 60 °C. Un gold declarant `durations_h` fait desormais foi.
Chiffres des iridates inchanges apres correction (verifie).

**Consequence sur les chiffres publies** : `hydro_czts` etait annonce a 66,7 % de
precurseurs — il est a **100 %**. Le modele avait extrait les cinq reactifs ; le
gold les ecrivait en formules brutes que le comparateur ne savait pas rapprocher
de leurs noms. Corriger la mesure avant de conclure sur le modele.

**Nouvel outil : `tools/audit_reproductibilite.py`.** Les 9 criteres mesurent la
fidelite au gold, pas la faisabilite. Verdict : AUCUNE des 3 synthese d'iridate
n'est refaisable en l'etat, `crystal` compris malgre ses 100 % partout — il manque
le creuset de platine, le rincage final separant le flux, et le broyage initial.
Ce qui n'est pas mesure n'est jamais corrige.


### 2026-08-19 — V5_TC : gold atteint sur 2 iridates, repetabilite mesuree, extension a 5 papiers

**Resultat sur les 3 iridates (run `gold_final2`, Qwen3-8B, architecture tool-calling).**

| Papier | Precurseurs | Ratios | Durees | Temperatures | Tracabilite | Gold |
|---|---|---|---|---|---|---|
| crystal | 100 % | 100 % | 100 % | 100 % | 100 % (43 valeurs) | OUI |
| physrev | 100 % | n/a | 100 % | 100 % | 100 % (9 valeurs) | OUI |
| prepara | 20 % | n/a | 0 % | 100 % | 100 % (4 valeurs) | non |

**Ce qui a produit la qualite** : ce n'est JAMAIS la taille du modele (4 mesures
independantes le montrent), ce sont ~8 correctifs d'integration et de validation.
`crystal` est passe de 37,5 % a 100 % sur les temperatures avec le MEME modele 8B.
Le post-traitement deterministe ajoute sans retrancher ; alourdir le prompt deplace
l'attention d'un 8B et retranche ailleurs (teste : durees 0 -> 100 % mais precurseurs
100 -> 20 % sur `prepara` — revert documente dans `extractor_toolcalling.py`).

**Dernier correctif : deduplication NON destructive des etapes.** La dedup par
signature `(type, citation)` fusionnait 3 paliers distincts partageant une meme
citation (`physrev` : 100 % -> 33 % sur les temperatures). Corrige par detection de
conflit — deux etapes de meme signature dont un parametre DIFFERE sont deux etapes
reelles, on les garde :

```python
conflict = any(k in prev and prev[k] is not None and prev[k] != v
               for k, v in kept.items())
if conflict:
    continue          # etape reellement distincte : on la garde
```

Valide 4/4 hors ligne ; non-regression `test_graph_tools` 29 PASS, `test_tc_loop` 19 PASS.

**Repetabilite (2 runs identiques, meme code, meme modele).**
- `crystal` et `physrev` : resultats IDENTIQUES d'un run a l'autre — deterministes en
  pratique malgre l'echantillonnage du LLM.
- `prepara` : **INSTABLE**. 100 % puis 20 % de precurseurs sans changement de code.
  Deux causes cumulees : OCR degrade de 1957 (cesures, ligatures) et precurseurs
  enumeres par suffixe (`strontium oxide, carbonate, nitrate or hydroxide`). Le
  correctif d'enumeration fonctionne — il a donne 100 % plusieurs fois — mais le
  modele ne declare pas systematiquement les quatre variantes.
- **Consequence a retenir** : la repetabilite mesuree sur les papiers propres ne se
  generalise PAS aux textes degrades. Toute annonce de stabilite doit preciser sur
  quel type de texte elle a ete mesuree.

**Document des voies de synthese** : `VOIES_DE_SYNTHESE.md`, genere par
`tools/make_voies_doc.py`. Un chapitre par papier, une partie par voie extraite,
chaque valeur accompagnee de la citation qui la prouve et confrontee au gold.

**Extension hors iridates (5 papiers, 5 familles de synthese distinctes).**
Corpus `data/corpus5/`, gold annote a la main dans `data/gold/gold_corpus5.json` :

| Cle | Famille | Materiau |
|---|---|---|
| `hydro_czts` | hydrothermale | Cu2ZnSnS4 kesterite |
| `solgel_cuo` | sol-gel + calcination | CuO poreux |
| `combu_ferrite` | auto-combustion | Ni-Cu-Zn ferrite |
| `cbd_mnse` | bain chimique (CBD) | MnSe couche mince |
| `reduc_cu` | reduction chimique | nanoparticules Cu |

Gold verifie objectivement contre les textes sources : **89 verifications, 0 erreur**
(chaque citation, temperature, duree, rampe, pH et precurseur existe litteralement
dans son papier). Chaque entree porte une liste `pieges` — notamment `solgel_cuo`,
dont la premiere phrase decrit la voie GENERIQUE vers la malachite (nitrate de cuivre
+ carbonate de sodium) alors que les reactifs reellement employes sont l'acetate de
cuivre et le carbonate d'ammonium.


### 2026-08-17 — V4.20 (boucle correctifs guidée par gold : A3, A4, A1)

**Contexte.** Bench nocturne 6 modèles (cf. `HANDOFF_BENCH_NUIT.md`, rapports Word
`rapport_benchmark_modeles.docx` et `rapport_gold_et_ameliorations.docx`) →
11 axes d'amélioration. Terry arbitre : boucle correctif → run complet 3 papiers →
comparaison gold, une étape à la fois.

**Outils créés**
- `data/gold/gold_sr2iro4.json` — référence annotée MANUELLEMENT (3 papiers Sr2IrO4,
  10 séquences thermiques du papier 1, pièges documentés). Résout l'Étape C.
- `tools/compare_gold_sr2iro4.py` — juge de la boucle : rappel précurseurs (avec
  détection du FLUX manquant, éliminatoire), températures, rampes, atmosphère,
  valeurs hors référence.
- `tools/bench_metrics.py` + `bench_night.py` + `bench_watchdog.py` + `bench_recompute.py`.

**Correctifs livrés** (36/36 tests offline, aucune régression)
- **A3 — atmosphère** : validée sur les citations DU PROTOCOLE (ni l'étape isolée,
  trop strict ; ni le document entier, trop laxiste). Contradiction franche dans la
  citation de l'étape → purge prioritaire. Non prouvée → `MissingParameter` (choix
  de Terry : purge stricte).
- **A4 — vitesse ≠ durée** : une valeur en °C/h ne peut plus alimenter `duration_h` ;
  détection par l'unité du champ ET par la citation (nombres nus).
- **A1 — re-ancrage** : une valeur absente de sa citation mais présente dans UNE
  ligne de tableau y est ré-ancrée ; dans PLUSIEURS → conservée + marquée ambiguë ;
  introuvable partout → purgée (avec journal `[A1:purgées]` de ce qui disparaît).

**Résultat mesuré : AUCUN gain sur le gold.** precurseurs 100 %, températures 79,2 %,
atmosphère 0/3 KO, rampes en durée 1/3 — identiques avant et après les trois axes.
Acquis réels : garantie anti-invention (5 atmosphères non prouvées purgées),
21 valeurs marquées ambiguës. A4 est resté **inerte** (0 déclenchement).

**Pièges rencontrés (à ne pas réapprendre)**
- `_OCR_CONFUSABLES` (0→o, 1→l) est fait pour les MOTS, jamais pour les NOMBRES :
  appliqué à « 1150 » il produit « llso ». Oublié sur l'atmosphère (`flowing 02`
  avec un zéro → O2 purgé à tort, régression), puis appliqué à tort aux valeurs
  numériques (aucune valeur avec 0 ou 1 retrouvable). Deux runs perdus.
- Un pattern de vitesse doit exiger l'unité de température ET le séparateur `/`|`per`,
  sinon « 24 h » est lu comme une vitesse et des durées légitimes disparaissent.
- Le re-ancrage ne peut corriger que ce qui est EXTRAIT : les 5 températures
  manquantes (750/880/1050/1125/1150, Tables 2-3) ne sont pas un défaut de
  traçabilité mais d'extraction — aucun protocole n'est créé pour ces échantillons.

**Diagnostic clé pour la suite.** L'extraction PDF n'est PAS en cause :
opendataloader reconstitue déjà les lignes de tableau (`- Sr214#2 1 : 2 : 7 1100◦C
→ (45◦C/h) …`) et `_build_focused_text` les inclut déjà dans la fenêtre du modèle
(log `[P11] 3 tableau(x) référencé(s)`). Le modèle reçoit les données et ne les
exploite pas.

**Prochaine étape (validée par Terry, non commencée) : UN PROTOCOLE PAR ÉCHANTILLON.**
Construire déterministement une voie par ligne de tableau (Sr214/Sr327#1-3, Sr327).
Seul correctif capable d'apporter les 5 températures, et qui rendra A4 + le
re-ancrage opérants. Champs `sequence_id`/`step_index` sur `Operation` — PAS de
nouveau nœud (arbitrage Terry : aucune migration Neo4j).

**Base archivée.** Les 36 graphes antérieurs sont dans
`logs/archive_corpus_38_pre_V4.20_20260817/` (README explicatif). Neo4j est à
l'arrêt, rien n'y a été touché. Reconstruction prévue par lots de 5 papiers avec
création d'un gold à chaque lot, après validation sur les 3 papiers Sr2IrO4.

### 2026-07-12 — V4.5 (audit initial → fixes N1/N2/N3, C3/C4)
- Cypher paramétré, paper_id partout, base `synthgraph` du YAML, comptage échecs injection.
- Suppression des fallbacks fictifs (ex-TiO2_350C), fail-closed, qa_status dans le graphe.

### 2026-07-12 — V4.6 (anti-hallucination citations)
- Découvert : le 8B « cite » ses propres instructions et fabrique des recettes entières.
- Grounding des citations + prompt durci + valeurs squelette improbables (555/665).
- Durci ensuite en majorité STRICTE (fragments dégénérés à 3/6 passaient).

### 2026-07-12 — V4.7 (fiabilité + vitesse)
- Veto : stoich ÉCHEC → REJECT forcé (avant : REVISE mensonger).
- Rattrapage précurseurs guidé par bilan élémentaire (1→3 précurseurs, reproductible).
- Dédup directives (papier 3 : 62 min → 5 min avec le plafond QA).
- `QA_MAX_TOKENS=2048` (9 agents QA).

### 2026-07-12 — V4.7.1 (précurseurs inventés)
- Découvert : précurseurs fabriqués (SrO2) avec citation réelle mais hors sujet.
- `_name_in_source` : la formule doit exister dans la source ; compte dans le ratio de drop.

### 2026-07-12 — V4.7.3 (séquences céramiques — correction signalée par Terry)
- Cava 1994 : « 900; 1000; 1100 with many intermediate grindings » = UNE séquence,
  pas 3 variantes. Fusion/insertion déterministe (retry LLM abandonné : il réécrivait
  les citations → auto-rejeté). Validé live sur les 2 formes.
- `tools/triage_corpus.py` créé (classes d'échec + historique JSONL).

### Autorisation modèles (Terry, 2026-07-12)
Autorisé à tester d'autres LLM pour tests/améliorations. **Candidats GGUF locaux (8 Go VRAM, in-process)** :
`Qwen2.5-7B-Instruct-Q4_K_M` (4.4G — candidat n°1 : réputé meilleur en JSON strict/instruction-following),
`DeepSeek-R1-Distill-Llama-8B-Q4_K_M` (4.6G — raisonnement, mais <think> verbeux → lent),
`gemma-4-E2B/E4B` (3.3/5.0G), PaliGemma (vision, pour l'Agent Vision futur).
**Méthode** : changer via `SYNTHGRAPH_MODEL_PATH` ou `settings.yaml:llm.model_path` ; comparer
sur le golden set avec `tools/triage_corpus.py` (mêmes métriques) + `benchmark_llms.py`.
Déclencheurs légitimes d'un test de modèle : classe d'échec persistante après 2 correctifs
code (ex: EXTRACTION_LOSSY récurrent, qa_status jamais ACCEPT), pas la curiosité.
Un seul facteur à la fois : jamais changer modèle + code dans la même itération.

### 2026-07-12 — V4.8 (Agent Vision réactivé — demande Terry)
- La simulation `trigger_vision_agent` (« Données simulées ») est SUPPRIMÉE.
- Nouveau `synthgraph/agents/vision.py` : PaliGemma-3B GGUF (2.5 Go) via
  MTMDChatHandler (fallback Llava15), **swap VRAM** (unload 8B → lot de questions →
  unload PaliGemma). Config `settings.yaml: vision.{enabled, model_path, max_queries}`.
- `step3c_vision_fill` (runner) : déclenché UNIQUEMENT si trou requis ou citation
  `reference_only` (valeurs « dans la Table N »). Questions courtes par lot sur les
  2 images les plus denses ; réponse convertie par `convert_value` ; valeur écrite
  avec `<param>_provenance = vision:<image>` (jamais de fausse citation) ; réponse
  'not shown'/inparseable → le trou RESTE déclaré.
- `PDFReaderTool.extract_images` : fichiers `logs/extracted_images/<stem>/p{page}_i{n}.{ext}`
  (filtrage vignettes <160px/<8Ko) au lieu de base64 en mémoire.
- ❌ SMOKE TEST : le GGUF texte PaliGemma charge OK (arch gemma) mais le mmproj
  (format llava historique) CRASHE mtmd_init_from_file (access violation) — llama-cpp-python
  0.3.31 a unifié tous les handlers sur mtmd. Vision = échec gracieux (flag _broken,
  1 seul essai/process, trous conservés). DÉBLOCAGE : télécharger un couple GGUF+mmproj
  compatible mtmd — candidat n°1 : Qwen2.5-VL-3B-Instruct (handler natif Qwen25VLChatHandler
  présent, excellent en lecture de tables/OCR, ~2.5 Go + mmproj 0.6 Go) — DEMANDER À TERRY
  avant tout téléchargement.

### 2026-07-13 — INCIDENT V4.9 : crash CUDA en cascade via vision
- Batch 1 re-run débat : le swap vision (unload 8B → load PaliGemma) a crashé nativement
  (mmproj incompatible mtmd) en CORROMPANT le contexte CUDA → « Failed to load model »
  pour tous les papiers suivants (3/5 perdus). Le fusible Python ne protège pas d'une
  corruption d'état natif.
- Leçon : un crash natif dans le process = risque pour TOUT le batch. `vision.enabled: false`
  tant qu'un modèle vision sain n'est pas smoke-testé. Option structurelle au backlog :
  isoler la vision dans un sous-processus jetable (à discuter avec Terry — nuance avec la
  contrainte « pas de subprocess pour le cycle de vie LLM », ici c'est de l'isolation de crash).

### 2026-07-13 — V4.10 (décisions Terry)
- ✅ Téléchargement Qwen2.5-VL-3B GGUF+mmproj autorisé et effectué (ggml-org/HF ;
  curl --ssl-no-revoke nécessaire sous Windows/schannel). Vision : handler dédié
  Qwen25VLChatHandler ; settings pointe sur Qwen ; `enabled` reste false jusqu'au
  smoke test GPU. VRAM : ~3,3 Go seul (swap identique, cohabitation 8B impossible).
- ✅ ACCEPT DÉTERMINISTE validé par Terry : REVISE promu → ACCEPT si stoich Python OK
  + 0 trou requis + 0 flag suspect. `p.qa_basis='deterministic'|'llm'|'none'` sur le
  protocole pour distinguer. REJECT/QA_FAILED jamais promus.
- Sous-processus vision : FAIT (décision Terry) — `vision_worker.py` jetable, un spawn
  par lot, contrat JSON stdin-fichier/stdout, timeout 180s+40s/question, fusible _broken
  sur échec structurel. Plomberie testée : erreur structurée / succès / crash rc=139.
  VRAM inchangée (swap : unload 8B → worker ~3,3 Go → mort du worker → reload 8B).
- V4.9.1 : rattrapage 0-précurseur, chunk court enrichi (<800 chars), retry from-scratch
  sur extraction vide d'emblée, instrumentation tok/s dans SynthAgent.
- PLAN (ordre) : fin runs Cu+golden → smoke test Qwen-VL → vision enabled →
  RELANCE BATCH 1 COMPLET avec la nouvelle architecture (consigne Terry) → triage →
  si propre, batch 2 (10 papiers).

### 2026-07-15 — V4.11 (résolution des 6 problèmes de l'audit complet)
Audit multi-agents (7 agents, vérification adversariale) → artifact 'audit-v4.10'. Correctifs :
1. Cohérence 0-précurseur : pathway avec étapes mais 0 précurseur → trou REQUIS 'precursors'
   (step_type='protocol') déclaré au graphe. Ni suppression ni protocole vide silencieux.
   (Constaté : 9/10 protocoles GO vides vs route Fe3O4 supprimée pour le même symptôme.)
2. Images JPEG2000 : extract_images convertit tout format ≠ png/jpeg en PNG via fitz.Pixmap
   (constaté : 8 images .jpx du PDF MnSe → 0 réponse vision sur 8, silencieux).
3. Compteur vision honnête : 'N exploitables, M refus (not shown), K échecs' + WARNING si 100%
   d'échecs ; stderr du worker relayé en INFO (était en DEBUG → invisible par construction).
4. Anti-faux-positif grounding : citation qui échoue sur la fenêtre focalisée → repêchage
   contre le PDF ENTIER (cas KMnO4/H2SO4/H2O2 réels flaggés suspects car fenêtre mal cadrée ;
   une citation du prompt reste introuvable partout → toujours rejetée). Testé les 2 sens.
5. Garde _deterministic_accept : pathways vide ou sans précurseur → jamais promu (l'audit
   avait identifié la promotion vacueuse théorique).
6. Golden set re-run réel APRÈS fix _route_signature : lancé ce jour (la validation
   n'était qu'unitaire — prouvé par chronologie mtime dans l'audit).
Backlog restant de l'audit : pertinence sémantique des citations (phrase réelle mais décrivant
une méthode alternative de l'intro — conservée à tort), bilan stœchiométrique quantitatif
(présence seule aujourd'hui), unload VRAM in-process non isolable (documenté, accepté).

### 2026-07-16 — V4.11.1 (robustesse fallback QA + verdicts des runs V4.11)
Analyse des 2 runs de validation V4.11 (golden + papiers affectés, débat) :
- **Golden** : Crystal growth **OK** (crash historique `_route_signature` franchi en réel,
  6 protocoles, 4× stoich OK, 20,7 min) ; preparation-Sr2IrO4 STOICH_UNKNOWN (backlog prose,
  3 protocoles sains) ; **PhysRevB NO_DATA** — l'unique route fail-closed, citations
  fabriquées 2× vérifiées contre le PDF ENTIER. Baseline v4.7.3 : 88 requêtes Cypher pour ce
  même papier → **variance run-à-run du 8B** (parfois il cite juste, parfois il fabrique).
  Règle d'or respectée, mais recette perdue = coût de la taille du modèle, pas un bug code.
- **GO (graphène)** : 6 protocoles **AVEC précurseurs** (Marcano 4/variante, Proposed 1) —
  le symptôme d'audit « 9/10 protocoles vides » ne s'est pas reproduit (extraction réussie
  cette fois ; nœuds rendus en `:Material`, pas `:Precursor` — piège de grep). Route Hummers
  perdue fail-closed (recopie du squelette 555/665 même au retry). Fix 1 présent mais non
  déclenché en réel (aucun pathway 0-précurseur) — couvert offline (fixture rX).
- **MnSe** : fixes vision **2/3 validés en réel** — images .jpx → PNG encodées par le worker
  (`nx=868, ny=560`, réponse « not shown » honnête), compteur `0 exploitable / 1 refus /
  1 échec`, diagnostics `[Vision·worker]` visibles en INFO. Veto déterministe a bloqué la
  route pH (« MnSe contient [Se] qu'AUCUN précurseur (Mn(NO3)2) ne fournit ») : vrai trou
  de rappel d'extraction, correctement fail-closed.
- **Bug trouvé et corrigé (V4.11.1)** : Défenseur 3× ValidationError (champ `reasoning`
  omis) → fallback « JSON brut » = chaîne → `'str' object has no attribute 'get'` → toute
  la couche QA en QA_FAILED alors que le débat thermo avait réussi (CBD_MnSe_pH_t1).
  Fix : gardes `isinstance` sur `rt_data`/`ctx_data`/`veto_decisions`/
  `parameters_declared_missing`/`corrected_synthesis` dans `step5b_red_team_audit`.
  Test offline 5/5 (crash réel reproduit + non-régression nominale).

### 2026-07-16 — V4.12 (auto-consistance) + V4.13 (grammaire Défenseur) — chantier « petits modèles », palier 1
Diagnostic acté avec Terry : les erreurs restantes (fabrication, variance run-à-run,
rappel, non-respect de schéma) sont des limites du 8B, pas des bugs. Plan en 3 paliers :
(1) mitigations sans entraînement, (2) benchmark NuExtract 3 / GLiNER2, (3) fine-tune
QLoRA maison (~15-40 $, dataset distillé + extractions validées accumulées).
- **V4.12** : le retry from-scratch devient une boucle de 2 tentatives, la 2e à
  **température 0.45** (défaut 0.1). Constat : à T=0.1 la fabrication est un mode
  SYSTÉMATIQUE (Hummers recopié au run initial ET au retry) alors que PhysRevB prouve
  qu'un tirage différent peut réussir (88 requêtes en baseline, 0 en V4.11). Sans risque
  règle d'or : le grounding déterministe reste le filtre. `extract_single_shot` accepte
  `temperature=`. Test offline 4/4 (séquence des températures, arrêt au 1er succès ancré,
  fail-closed préservé, nominal inchangé).
- **V4.13** : grammaire GBNF **réactivée pour le Défenseur** (`use_grammar` était False —
  seul agent QA sans grammaire, et précisément celui qui a échoué 3× 'reasoning' omis le
  2026-07-15). Vérifié hors-ligne : la grammaire force l'ordre reasoning → veto_decisions
  → corrected_synthesis, additionalProperties:true (pas d'objet vide forcé), enum decision
  contraint. L'extracteur reste SANS grammaire (choix délibéré : son problème est le
  contenu, pas la forme ; schéma trop gros → 30-50 % plus lent).
- Reste du palier 1 (à faire) : citations par ID de phrase (effort élevé, ultracode) ;
  filet GLiNER2 rappel précurseurs (palier 2b).

### 2026-07-16 — V4.14 (repli confusables OCR — cause racine PhysRevB trouvée)
Le run V4.12 sur PhysRevB a encore échoué (2 retries, T=0.45 compris). Diagnostic
systématique au lieu de conclure « variance » : les citations de la baseline v4.7.3
matchent ENCORE le texte actuel → le texte est bon. MAIS le scan 1994 écrit 'Ir02',
'Ru02', 'flowing 02' avec le CHIFFRE zéro ; quand le modèle normalise en IrO2/O2 en
citant (comportement spontané d'un LLM), la citation RÉELLE échouait le matching
littéral → 2/4 = pile le seuil de rejet → route perdue. La « variance » PhysRevB
était donc : le run réussit quand le modèle recopie l'erreur OCR, échoue quand il la
corrige. Correctifs :
- `_clean_for_match` replie les confusables OCR **0→o et 1→l** (cas 'A1203'→Al2O3)
  APRÈS lowercasing, des DEUX côtés du matching. Présence uniquement : rien de stocké
  ne change, les fabrications 555/665 restent rejetées (testé).
- Observabilité : `dropped_pathways[].citations_rejetees` persiste désormais les
  citations refusées (avant : seuls les comptes '2/4' — diagnostic post-mortem impossible).
- Tests : offline 4/4 (normalisées gardées, verbatim gardées, fabrications rejetées+
  persistées, précurseur IrO2 vs Ir02 ancré) + suites anti-hallucination/étape 3/étape 4
  toutes vertes. Run réel PhysRevB V4.14 : voir tableau.

### 2026-07-16 — V4.14.1 (CRITIQUE : la Bible était une source de grounding valide)
Le run PhysRevB V4.14 est passé « OK » au triage (54 requêtes, ACCEPT déterministe,
5,7 min)… mais l'inspection des citations a révélé des étapes citant les CHROMITES du
manuel de West. Mécanisme : `_build_focused_text` insère un bloc `[RÉFÉRENCE BIBLE]`
(1500 chars de manuel) dans le texte focalisé → le grounding validait contre focused_text
→ toute citation du manuel passait pour une citation du papier. Le modèle a construit un
programme thermique entier depuis le manuel ; précurseurs justes (IrO2/RuO2/SrCO3),
étapes fausses, ACCEPT. **Violation de la règle d'or entrée dans un graphe.**
Correctifs :
- Grounding tronqué au marqueur `[RÉFÉRENCE BIBLE` : la source de vérité redevient LE
  PAPIER (fenêtre + PDF entier). `[EXTRAITS PERTINENTS]` (chunks pdf_chunks du papier)
  et `[TABLE RÉFÉRENCÉE]` (fenêtres de full_text) restent licites.
- Marqueur Bible renforcé dans le prompt : « CE N'EST PAS LE PAPIER : n'en extrais
  AUCUNE étape et n'en cite JAMAIS une phrase ».
- Test offline 3/3 (Bible rejetée, papier gardé, mix majorité-Bible rejeté).
- **Nouvel outil `tools/audit_citations.py`** (+ TOOLS.md créé) : rejoue le grounding
  entre les `citation:` d'un .cypher et le PDF seul. **Audit rétroactif : 4 graphes
  contaminés sur 8** — PhysRevB (4 cit. manuel), Fe3O4 batch 1 (1), graphène (1
  'nanodiamond'), et le GOLDEN the-preparation-Sr2IrO4 (1 : 'Mixtures of iridium metal
  powder and strontium oxide were used.'). Crystal growth, Cu NPs, mésoporeux, MnSe :
  propres. → TOUS les graphes doivent être régénérés en ≥V4.14.1 ; l'audit devient une
  étape de fin de batch obligatoire.

### 2026-07-17 — V4.14.2 (suppression dure des éléments citant la Bible)
Le run V4.14.1 a validé le rejet des variantes majoritairement-Bible (0/5, 0/4,
retry ancré) MAIS une citation manuel a survécu : la variante retenue n'avait qu'UNE
citation vérifiable (précurseurs 'IrO2' trop courts pour être jugés) → la règle de
majorité (checked>=2) ne s'appliquait pas → étape-manuel gardée, flaggée mais présente.
Fix : une citation absente du papier mais présente dans le bloc Bible est une PREUVE
POSITIVE de contamination (pas un doute type OCR) → l'élément est supprimé DUR,
indépendamment de la majorité. Tests offline 5/5 + suites (cas 7 anti-hallucination
adapté : le fixture contient un vrai bloc Bible, le texte additionnel passe par
full_text). Confirmation historique : le fixture debug_focused_flux_method_t1.txt
(golden the-preparation) contient le passage chromites de West → la contamination du
golden venait bien du même mécanisme.

### 2026-07-17 — V4.14.3 + V4.15 (la Bible quitte le contexte d'extraction)
- **V4.14.3** : « retry retenu » exige de vraies étapes (après purge anti-contamination,
  un pathway précurseurs-seuls court-circuitait le retry 2 à T=0.45).
- **V4.15** : bloc [RÉFÉRENCE BIBLE] **retiré du texte focalisé d'extraction**. Sur 4
  runs PhysRevB successifs, le 8B préférait la recette du manuel au court paragraphe
  expérimental du papier — le manuel ne peut jamais être une source légitime d'étapes
  (l'extraction est une copie-du-papier par définition). La QA garde son BibleRAG
  (valider ≠ extraire). Les gardes V4.14.1/V4.14.2 restent en défense en profondeur.
- `audit_citations.py` distingue désormais « hors-papier SILENCIEUX » (grave) de
  « suspect déclaré » (citation_grounded=false dans le graphe — design assumé).
- **Verdict final PhysRevB V4.15** : propre (0 contamination silencieuse), 1 protocole,
  vrais précurseurs (IrO2/RuO2/SrCO3), stoich OK, 1 paraphrase flaggée, 9 min,
  EXTRACTION_LOSSY (honnête). Historique complet du papier : baseline 88 requêtes
  (contaminées ?) → V4.11-V4.12 NO_DATA → V4.14 54 requêtes CONTAMINÉES-ACCEPT (faux
  OK) → V4.15 propre et honnête.

### 2026-07-18 — V4.15.1 (timeout opendataloader — batch 2 gelé 24 h)
Le run batch 2 --no-debate est resté SUSPENDU 24 h sur le papier 8 (ball-milling,
ncomms10308) : `opendataloader_pdf.convert()` (Java) gelé, appel bloquant sans
timeout → le fallback PyMuPDF n'était jamais atteint, 2 processus java de 8 Go
orphelins, modèle chargé en VRAM pour rien. (La tâche planifiée 5 h n'a rien fait —
comportement correct : elle a vu la VRAM occupée.) Fix : convert() vit dans un
sous-processus python tuable (`taskkill /T` emporte le java petit-fils), timeout
240 s → TimeoutError → fallback PyMuPDF. Validé sur le PDF coupable : gel → kill à
240 s → fallback → 49 771 chars. Annotation GOLD des 10 papiers du batch 2 faite à
la main pendant l'attente (scratchpad gold_batch2.json, 14 routes, citations
verbatim) → servira à mesurer rappel/précision du pipeline et de données
d'entraînement palier 3.

### 2026-07-18 18:25 — Point de contrôle watchdog (tâche planifiée)
VRAM 6826/8192 MB, log `logs/run_batch2_nodebate2.log` écrit il y a 4 min (18:21:01),
process réel confirmé (`PID 11120 : python run.py --input data/corpus_batch_2/ --no-debate`),
progression saine au papier 2/10 (route CVD, MoS2_growth). Run sain → aucune action
(pas de second run GPU, pas de kill). Rien à trianger : aucun log terminé non encore
journalisé depuis le 17/07. Prochaine étape dès la fin du run : triage
(`tools/triage_corpus.py --run-log logs/run_batch2_nodebate2.log`) + comparaison au
gold set (scratchpad `gold_batch2.json`) → étape (b) du protocole batch 2.

### 2026-07-18 — V4.16 + V4.17 (batch 2 : la comparaison GOLD paie)
Batch 2 --no-debate (V4.15.1) : 5 OK, 4 GAPS_REQUIRED, 1 NO_DATA. La comparaison à
l'annotation gold manuelle (tools/compare_gold.py : rappel précurseurs 63 %, valeurs
38 %) a révélé DEUX problèmes invisibles au triage :
- **V4.16** : NO_DATA CoSi = la fenêtre focalisée ratait la section expérimentale des
  papiers longs (1re occurrence de « synthesis » = le titre !). Fenêtre désormais choisie
  par SCORE DE DENSITÉ DE RECETTE (quantités, verbes opératoires, signaux
  pureté/fournisseur ; piège corrigé : le ° nu comptait les angles XRD). Testé 5/5
  (CoSi, CZTS, PhysRevB, ferrite, golden Crystal growth) ; run réel CoSi : NO_DATA →
  2 protocoles conformes au gold (Si/CoCl2/LiI/KI).
- **V4.17** : le graphe ferrite « OK » contenait le programme thermique SQUELETTE
  (555/665 °C, 5/7 h) — rattrapage retenu sur ses seuls précurseurs, valeurs recopiées
  flaggées mais écrites au graphe. Purge dure : valeur non-ancrée == squelette → null +
  trou déclaré ; rattrapage rejeté s'il augmente les valeurs non-ancrées.
- Restent (constatés gold, à traiter) : route hydrothermale AgVO3 dédupliquée à tort
  (extraction hydro n'avait pas capté 180 °C/16 h — à re-tester post-V4.16), rappel
  paramètres secondaires (durées de mélange/broyage souvent manqués), ligne de log
  trompeuse « Modèle sélectionné : gemma (llama-server) » = étiquette legacy de
  llm_config.json (le modèle réel chargé est bien Llama-3.1-8B — à nettoyer).
Run débat batch 2 lancé (V4.17) avec watchdog. Gold : scratchpad gold_batch2.json.

### 2026-07-20 — V4.18 (ratios molaires + rendement — décision Terry)
Réponse au constat de repro : « en tant que chimiste, puis-je refaire les matériaux ? ».
Terry : représentation canonique = RATIO MOLAIRE des précurseurs (+ quantité brute en
appui), + rendement expérimental si donné. Nouveau module DÉTERMINISTE
`synthgraph/validation/quantities.py` (0 LLM, 0 invention) :
- 5 sources de ratio par priorité : ratio explicite (« 2:2:1 »), moles directes
  (« 2 mmol »), masse→mol (masses atomiques + hydrates), molarité×volume, déclarations
  (equimolar/stoichiometric). Appariement à la quantité la PLUS PROCHE du nom (fix :
  précurseurs partageant une citation) ; moles directes préférées aux masses.
- Champ `amount` du LLM utilisé SEULEMENT s'il est ancré dans le texte source (règle d'or).
- Câblé step3 (annotation) → step6 (nœuds Material : molar_ratio/moles/amount_raw ;
  SynthesisProtocol : ratio_source + yield_percent). Trou 'molar_ratio' déclaré si aucun
  ratio ancrable.
- `compare_gold.py` gagne une métrique rappel des ratios ; 8 ratios gold annotés à la main.
- **Test réel : CoSi (masses→moles) Si:Co=1.53:1 ✅ + LiI:KI 14.5:8.5 (=0.63:0.37) ;
  CZTS (moles) Cu:Zn:Sn:cys 2:2:1:4 ✅ — rappel ratios 4/4 (100 %) sur le test.** Offline
  19/19 + non-régression complète verte.

### 2026-07-29 — V4.19 — Phase 0 : abstraction « modèle par rôle » (refactor pur, non committé)
Prépare le plan multi-modèles (Phase 1 = harness bench) sans changer aucun comportement :
tant que tous les rôles pointent sur `default`, le pipeline charge exactement le même GGUF
qu'avant, zéro swap.
- `config/settings.yaml` : nouvelle section `models:` (`default` = définition GGUF concrète,
  `extractor`/`qa`/`strategist` = `{alias: default}`). `llm:` legacy conservé et lu en
  fallback si `models` est absent (`synthgraph/config.py`, `_resolve_model_roles` +
  `get_model_config(role)` — rôle inconnu retombe silencieusement sur `default`, fail-safe).
- `synthgraph/llm/engine.py` : `LlamaEngineManager.get_llm(role="default")` charge le GGUF
  du rôle et **décharge l'ancien d'abord si le chemin diffère** (contrainte VRAM : un seul
  gros modèle à la fois). Instrumentation `n_swaps` / `total_swap_seconds` / `swap_stats()`,
  log `[LlamaEngine] Swap {ancien} → {nouveau} : X.Xs`. `get_instance()`/`unload_model()`
  intacts (vision.py inchangé) ; `load_model()` sans argument = alias de `get_llm("default")`.
- `synthgraph/agents/base.py` : `SynthAgent.role` **réutilisé** — avant Phase 0 ce champ ne
  portait qu'un libellé humain jamais relu ailleurs (vérifié par grep) ; devient le rôle de
  routage modèle, défaut `"default"`, transmis à `get_llm(role)` dans `call()`. Champ déplacé
  après `system_prompt` dans le dataclass (contrainte Python : un champ à défaut ne peut pas
  précéder un champ sans défaut) — sans impact, tous les appels existants utilisent des kwargs.
  `create_agents()` route désormais orchestrateur/extracteur → `"extractor"`, contextuel/
  thermodynamicien/architecte_graphe/reranker → `"qa"` (fonction actuellement non appelée par
  le pipeline réel — `runner.py` a son propre `get_agent()` local, volontairement NON câblé
  en Phase 0 : les rôles qu'il passe (ex: `role=name`) ne matchent aucune clé configurée et
  retombent sur `default`, donc zéro régression).
- `runner.py` : ligne de log trompeuse « Modèle sélectionné : gemma (llama-server) »
  (backlog V4.17) remplacée par le vrai chemin GGUF résolu du rôle `default`.
- Tests offline 24/24 (mapping rôle→modèle depuis le vrai settings.yaml, swap 1x sur alias
  différents / 0x sur alias identiques, routage `SynthAgent(role=...)`, rétrocompat section
  `models` absente) + fumée : `create_agents()`, `get_agent()` (runner + base),
  `extractor_singleshot` s'importent et s'instancient sans erreur. Suite anti-hallucination
  existante (scratchpad d'une session précédente) introuvable pour re-run — fichier expiré,
  à recréer si besoin avant la Phase 1.
- **Non committé** (revue Terry en attente). Phase 1 (harness bench) devra câbler les
  rôles réels dans `runner.py` (actuellement `get_agent()` local, indépendant de
  `create_agents()`) pour que le swap ait un effet observable en run réel.

### 2026-07-29 — V4.19 Phase 2 bench réel NuExtract 3 vs Llama-3.1-8B (extractor)
Bench sur 3 papiers (CZTS ratio explicite, CoSi masses→moles, Cérine solvant DES),
no-debate. Rapport `logs/bench/nuextract_v_llama/report.md`.

**Ce qui marche parfaitement** :
- Dispatcher (`extract_single_shot` détecte `NuExtract` dans le chemin → route) ✓
- Swap VRAM strategist↔extractor (~3,6 s/swap, 4 swaps totaux) ✓
- Contamination : 0/3 dans les deux arms ✓
- Durée : **6,3 min (NuExtract) vs 8,7 min (Llama)** = **-28 %**
- Précurseurs : NuExtract les trouve tous (Si, CoCl2, LiI, KI sur CoSi)

**Ce qui ne marche PAS (à corriger avant adoption)** :
- NuExtract est verbatim par design : il extrait `silicon nanoparticles`,
  `cobalt(II) chloride` **tels que écrits** dans le papier.
- La baseline Llama normalise en `Si`, `CoCl2` (formules chimiques).
- Le parseur V4.18 (`quantities.py`) suppose des formules normalisées pour calculer
  les masses molaires → **incapable de convertir 63,2 mg → 2,3 mmol** pour NuExtract.
- Résultat : **CoSi baseline capture 4 ratios molaires (Si:Co, LiI:KI), candidat 0**.
- CZTS (ratio explicite `2:2:1:4`) : identique sur les deux (le parseur explicit_ratio
  ne dépend pas de la normalisation).

**Verdict** : adoption **bloquée** sur ajout d'un normaliseur nom→formule
(backlog déjà connu : « parseur stœchio prose »). Deux voies :
1. Enrichir `extractor_nuextract.py` avec un dictionnaire nom→formule sur les
   ~60 composés usuels de synthèse inorganique.
2. Enrichir `validation/deterministic.py::parse_composition` pour comprendre les
   noms en prose (« silicon » → Si, « cobalt(II) chloride » → CoCl2).
Le n°2 profite aussi aux STOICH_UNKNOWN historiques → priorité.

**Points annexes** :
- Vision worker `Prompt exceeds n_ctx: 2699 > 2048` sur le run candidat (worker
  Qwen2.5-VL vraisemblablement mal dimensionné pour les prompts longs — bug
  préexistant indépendant de NuExtract, à traiter séparément).
- Métriques gold `—` dans le rapport : `gold_batch2.json` (scratchpad volatile)
  purgé entre-temps → migrer les golds dans le repo (`tests/gold/` ou `data/gold/`)
  pour qu'ils survivent aux rotations.

Code : commits ff5768e (Phase 0), 8c55b23 (Phase 1), 720cb6b (Phase 2), tags
`v4.19.0-phase0`, `v4.19.1-phase1`, `v4.19.2-phase2`. Aucune régression sur les
suites offline (24/24 + 42/0 + 37/0).

### Problèmes connus / backlog
- [ ] Faux positifs grounding numérique sur valeurs converties (90 min → 1.5 h flaggé).
- [ ] Parseur stœchio : composés en prose (« iridium metal powder » → Ir) pour
      transformer les INDÉTERMINÉ des vieux papiers en verdicts.
- [ ] Near-duplicates : le Stratège crée parfois 2 routes quasi identiques (même recette,
      1 champ divergent) — candidat dédup floue post-extraction.
- [ ] Étiquetage macro_method parfois faux (solid-state nommé flux_growth) — données
      justes, label discutable.
- [x] ~~qa_status plafonne à REVISE — envisager un ACCEPT déterministe~~ FAIT en V4.10
      (promotion déterministe REVISE→ACCEPT, `qa_basis='deterministic'`).
- [ ] Pertinence sémantique des citations (audit V4.11) : une phrase réelle mais hors
      sujet (intro, résultats) peut ancrer une étape — cas PhysRevB flux (REVISE flaggé).
- [ ] Séquences de pulses ALD/MLD hors registre d'étapes (batch 3) : « 4 s pulse /
      6 s purge » n'a pas de step_type — les cycles ALD sont aplatis ou perdus.
- [ ] Garde PDF illisible à durcir : ratio alphanumérique (le PDF corrompu passe
      par _read_as_text binaire et produit ~500 chars de bruit).
- [ ] Ligne de log « Modèle sélectionné : gemma (llama-server) » trompeuse — étiquette
      legacy de llm_config.json, le modèle réel est Llama-3.1-8B (nettoyer cli/runner).
- [ ] Rappel des paramètres secondaires ~57 % (mesuré gold) : durées de
      mélange/broyage, débits, vitesses de spin — candidats registre étendu ou palier 2/3.
- [ ] Ratios molaires : couvrir « at.% doping » (Nb-TiO2), fractions massiques (wt%),
      et propager le ratio aux variantes fusionnées.

## Corpus

**Source** : `D:\projet\Synthesis_Routes_DB\data\pdfs_open_access\` — 1418 PDFs au
2026-07-12 (Terry en télécharge d'autres). Métadonnées : `data/metadata/synthesis_routes_metadata.csv`.
~11 % de reviews/roadmaps → NO_DATA attendu et CORRECT sur celles-ci (à distinguer d'un
NO_DATA sur papier expérimental = vraie erreur).
Batchs copiés dans `SynthGraph_V4.4/data/corpus_batch_N/`.

**Batch 1 (5 papiers, familles de méthodes toutes ≠ des iridates)** :
solvothermal Fe3O4 (srep07493), réduction chimique Cu NPs, chemical bath deposition
MnSe films, oxydation Hummers graphène oxide, soft-template mésoporeux + carbonisation.

## État du protocole corpus

| Date | Batch | Taille | Mode | Erreurs | Décision |
|---|---|---|---|---|---|
| 2026-07-12 | Validation initiale (3 papiers Sr2IrO4) | 3 | débat | **0** (3× OK) | ✅ GO batch 1. Golden set → logs/golden_set_v473/ |
| 2026-07-12 | Batch 1 (5 méthodes ≠) | 5 | no-debate | 4 (2×ROUTE_LOST, 1×SLOW, 1×GAPS_REQUIRED) | Fixes V4.9 : plafond extracteur 4096 (appels 420-440s constatés) + retry from-scratch si route vidée par grounding + triage ROUTE_LOST/filtre run. Re-run débat |
| 2026-07-12 | Batch 1 re-run | 5 | débat | 4 classes (dont GO protocoles sans précurseurs, vision jpx muette) | Audit complet → 6 problèmes → V4.11 |
| 2026-07-15 | Golden re-run V4.11 | 3 | débat | 1 NO_DATA (PhysRevB, fail-closed — baseline avait 88 requêtes → variance 8B), 1 STOICH_UNKNOWN (prose, backlog) | Crash historique franchi ✅. Fixes vision/grounding validés en réel |
| 2026-07-15 | Papiers affectés V4.11 (GO+MnSe) | 2 | débat | 1 ROUTE_LOST (Hummers, squelette recopié ×2), 1 STOICH_FAIL (Se manquant, veto correct) + bug QA fallback → V4.11.1 | Les pertes restantes sont des limites MODÈLE (fabrication, rappel), pas des bugs code → chantier « modèle spécialisé » ouvert avec Terry |
| 2026-07-16/17 | Boucle PhysRevB V4.12→V4.15 | 1×5 runs | débat | Cause racine « variance » = confusables OCR + CONTAMINATION BIBLE (4 graphes/8, dont 1 golden) | V4.12 à V4.15 + audit_citations.py. Anciens graphes tous invalides |
| 2026-07-17 | **Régénération complète V4.15** (goldens + batch 1) | 8 | débat | **0 crash, 0 NO_DATA, 0 ROUTE_LOST, 0 contamination silencieuse (audit 8/8 propre)**. Restent : 5×GAPS_REQUIRED (trous déclarés — comportement règle d'or), 3×STOICH_UNKNOWN (parseur prose, backlog) | ✅ Baseline saine → logs/golden_set_v415/. Prochaines options : batch 2 (10 papiers) et/ou benchmark NuExtract 3 (GGUF téléchargé) |

| 2026-07-18 | Batch 2 no-debate (V4.15.1) | 10 | no-debate | 1 NO_DATA (CoSi, fenêtre), gold révèle : squelette dans ferrite « OK », route AgVO3 perdue | V4.16 (fenêtre par densité de recette) + V4.17 (purge squelette + garde rattrapage) |
| 2026-07-18 | **Batch 2 débat (V4.17)** | 10 | débat | **0 bloquante** (6 GAPS_REQUIRED, 3 STOICH_UNKNOWN — non-bloquants). Audit : 18 graphes, 0 contamination. **Gold : précurseurs 77 %, valeurs 65 % (vs 63/38 en no-debate)** | ✅ GO **batch 3 = 20 papiers** (sélection diversifiée, éviter reviews ; la tâche horaire peut le lancer) |

| 2026-07-18 | Batch 3 no-debate (V4.17, 20 papiers, 16 familles : ALD/MBE/PLD/sputtering/électrofilage/colloïdal/SILAR/vertes…) | 20 | no-debate | 9 OK, 10 GAPS_REQUIRED, 1 « CRASH » = faux positif (PDF spray ZnO corrompu, géré) → V4.17.1 (helper silencieux + saut PDF illisibles). **Gold 20 papiers/25 routes : précurseurs 75 %, valeurs 55 %** dès le no-debate | Gold : scratchpad gold_batch3.json. Manqués typiques : séquences de pulses ALD (hors registre d'étapes — backlog), précurseurs organiques. Run débat lancé |

| 2026-07-19 | **Batch 3 débat (V4.17.1)** | 20 | débat (2 runs — coupure session à 9/20, reprise sur les 11 restants) | **0 bloquante données** (10 GAPS_REQUIRED, 5 STOICH_UNKNOWN, 1 SLOW technique = 1 appel >350 s sur MBE). **Audit : 38 graphes, 0 contamination silencieuse. Gold : précurseurs 77 %, valeurs 57 %** | ✅ GO **batch 4 = 40 papiers**. Backlog + : séquences pulses ALD hors registre ; garde PDF illisible à durcir (ratio alphanumérique — le PDF corrompu passe par _read_as_text binaire) |

*(mettre à jour ce tableau après chaque batch)*

## 2026-08-22 — Le maillon manquant : les voies atteignent enfin le graphe

**Constat** : zéro fichier `.cypher` dans tout l'arbre V5_TC. L'extraction
tool-calling — 12 papiers, égalité stricte au gold sur 8, traçabilité 100 % —
produisait des `logs/pathways_*.json` que **rien** ne convertissait. Le projet
s'appelle SynthGraph et n'avait pas de graphe.

Le constructeur existait pourtant depuis la V4.4 : `step6_graph_architect`
(runner.py:1323) bâtit du Cypher **paramétré** de façon déterministe et consomme
exactement la forme émise par `RouteBuilder.to_pathways_dict()`. Il ne manquait
que le câblage — `context` et `model` y sont même inutilisés.

**Livré** : `tools/pathways_to_cypher.py` → `logs/cypher/*.cypher`.
12 papiers, 21 voies, **858 requêtes**.

Deux choix qui engagent la fidélité, écrits dans le module pour qu'ils se voient :
- `qa_status = QA_SKIPPED`, `qa_confidence = null`. Le V5_TC n'a pas de QA par
  débat ; écrire ACCEPT ferait passer pour validé ce qui n'a jamais été jugé.
  **Une confiance fabriquée est une invention comme une autre.**
- Les voies sont **groupées par méthode** avant conversion. Les dix voies de
  `crystal` sont dix échantillons d'une même croissance en flux : elles sont bien
  `VARIANT_OF` l'une de l'autre. Deux méthodes distinctes ne le sont pas.

**Vérifié** — `tools/verifier_cypher.py`, **776 contrôles, 0 erreur** :
A complétude (chaque précurseur et chaque étape a son nœud) · B non-invention
(chaque nombre du Cypher existe dans le JSON) · C collision (aucun identifiant
partagé entre papiers — garde-fou N1) · D **attribution** (chaque valeur est
portée par l'étape qui la cite, rattachée par la citation).

Le contrôle D a été ajouté après avoir vu que B seul est trop faible : il ne
compare que des ENSEMBLES, donc une valeur du bon papier mais de la mauvaise
étape y passerait. Instrument falsifié avant d'être cru : trois valeurs
fabriquées sont bien rejetées, un précurseur supprimé bien vu.

**Syntaxe** : 858 instructions rendues, **0 chaîne non fermée**. L'échappement
est exercé pour de vrai — `PhysRevB` contient `1100'C`, la forme OCR où
l'apostrophe sert de degré, correctement échappée en `\'`.

**Réserve à connaître** : 8 point-virgules vivent À L'INTÉRIEUR de citations
(« 900°C, 24 h; 1000°C, 60 h; 1100°C, 60 h »). `cypher-shell` analyse
correctement, mais tout script de rejeu qui découpe naïvement sur `;` cassera ces
instructions. *(Mon propre vérificateur est tombé dans ce piège et a rapporté 8
faux déséquilibres avant que je suive l'état de chaîne — cf. règle 3 : une
aiguille trop faible donne une fausse confirmation.)*

**Non fait, volontairement** : aucune injection dans une base Neo4j vivante. Le
driver `neo4j` n'est pas installé dans cet environnement, et brancher la base
engage Terry.

## 2026-08-22 (suite) — Un même geste compté trois fois, et ce que la traque a révélé

**Défaut** : sur `combu_ferrite`, trois étapes de calcination identiques
(600 °C, 4 h) pour une seule dans le papier — un chimiste aurait calciné 12 h au
lieu de 4. Invisible à la métrique : **le gold ne contient aucune liste
d'étapes**, seulement des valeurs. Trois fois « 600 » et « 4 » lui paraissent
identiques à une fois.

**Correctif** : `_fusionner_gestes_dupliques()` absorbe une étape seulement si sa
citation est CONTENUE dans celle d'une autre, qu'elle n'apporte aucune valeur
propre, et que les types concordent — ou que le sien soit `generic`. Une
déduplication par ÉGALITÉ existait déjà dans `add_operation` ; celle-ci traite
l'INCLUSION, qu'elle ne couvrait pas. Complémentaires, pas redondantes.

**Vérifié EN PRODUCTION, dans les deux sens** :
- il TIRE : `[doublon] etape 5 (generic) absorbee par 4 (cooling)` sur `reduc_cu` ;
- il REFUSE : sur `physrev`, les trois paliers sont chacun examinés puis gardés —
  `valeurs propres ['duration_h', 'temperature_c']`. 100 % égalité stricte.

### Deux défauts que seul le run réel a révélés

Le mécanisme était vert sur 17 assertions et **totalement inerte en production**.
Un journal de REFUS (`[doublon?] ... mais GARDEE : <raison>`) a livré la cause en
un run :

1. **Le type était `settling`**, que le registre ignore. `normalize_steps` en
   fait un `generic` — mais PLUS TARD. Mes tests, écrits sur les JSON déjà
   normalisés, voyaient `generic` là où le mécanisme voyait `settling`.
   *Le piège exact de la règle 2, que j'avais pourtant écrite.*
   → `_type_final()`, dérivé du registre. `_type_canonique` reste intact : la
   déduplication par égalité s'en sert pour comparer des types ENTRE EUX, et y
   rabattre tous les inconnus sur `generic` les rendrait fusionnables.
2. **`_missing_vessel` est une clé de PREMIER NIVEAU**, pas nichée dans
   `other_parameters` comme je le croyais : elle comptait comme « valeur propre »
   et bloquait toute fusion.

**Leçon d'outillage** : le journal de refus a fait en un run ce que la lecture de
code n'avait pas fait en trois. Un mécanisme qui ne se déclenche pas doit dire
POURQUOI, pas seulement se taire.

### Découverte incidente, plus lourde : le LOT change l'extraction

`reduc_cu` seul, deux fois → **strictement identique** (6 étapes, 21 appels).
Le même papier après `combu_ferrite` → **7 étapes, 12 appels**.
Le moteur est déterministe ; la variable est la COMPOSITION DU LOT.

Conséquences directes :
- les artefacts archivés servant de référence dépendent du lot qui les a
  produits — ma mesure initiale (« 3 papiers à gestes dupliqués ») portait sur
  une configuration que je n'avais pas identifiée ;
- les deux configurations donnent **100 % égalité stricte** sur `reduc_cu`.
  La métrique est stable pendant que la STRUCTURE change : cinquième défaut
  structurel qu'un score au gold ne peut pas voir.

**Erreur de méthode à ne pas répéter** : mon propre test lisait
`logs/pathways_*.json`, que le run suivant a écrasés — trois assertions sont
tombées d'un coup. Le CLAUDE.md l'interdit explicitement, et je l'avais cité.
Les tests lisent désormais `logs/baseline_20260822/`.

**Autre erreur** : j'ai attendu la fin d'un run avec un `ps` de Git Bash, qui NE
VOIT PAS les processus lancés par `Start-Process`. Il a rendu « terminé »
instantanément et j'ai lu des journaux figés comme définitifs — à une phrase de
déclarer inerte un run d'une minute. Attendre avec `Wait-Process`.

**Bug corrigé au passage** (`compare_tc_gold.py`) : le nom du fichier de sortie
dérivait du CHEMIN du modèle. `../models/Qwen3-8B-...` donnait
`logs/pathways_../models/Qwen3_x.json` et le run plantait à l'ÉCRITURE, après
93 s de GPU déjà dépensées.

Graphe régénéré : 12 papiers, 21 voies, **844 requêtes**, 750 contrôles, 0 erreur.
Tests : 59 suites, 1339 assertions, 0 échec.

## 2026-08-22 (fin) — Le contexte hérité déplaçait les extractions (#48)

**Cause trouvée et corrigée en une ligne.** L'objet `Llama` est créé UNE fois et
sert à tous les papiers ; son cache de préfixe leur survit. Rien n'appelait
`Llama.reset()`, qui existe pourtant.

**Preuve, cinq runs** :

| configuration | résultat sur `reduc_cu` |
|---|---|
| seul, run A | 6 étapes, 21 appels |
| seul, run B | 6 étapes, 21 appels — **strictement identique** |
| après `combu_ferrite`, sans remise à zéro | **7 étapes, 12 appels** |
| après `combu_ferrite`, avec remise à zéro | 6 étapes, 21 appels — **identique au run seul** |
| en position 1 d'un lot inversé | 6 étapes, 21 appels |

Le moteur est donc **déterministe** ; c'était le contexte hérité qui déplaçait le
résultat. Invariant vérifié dans les deux sens : `combu_ferrite` en position 2
redonne exactement son extraction de position 1 (comparaison étape par étape,
citations et valeurs comprises).

**Où vit le correctif** : `_contexte_vierge()` au seuil de `extract_all_samples`,
PAS chez l'appelant. `LlamaEngineManager.get_llm()` renvoie la même instance en
cache tant que la configuration ne change pas — le défaut ne touchait donc pas
que l'outil de mesure. La remise à zéro placée d'abord dans `compare_tc_gold.py`
a été retirée : une seule source de vérité.

**Ce que ça invalide** : toute mesure archivée est conditionnée par le lot qui
l'a produite. Ma mesure initiale des « 3 papiers à gestes dupliqués » portait sur
une configuration non identifiée et ne se reproduit pas en runs isolés — le
défaut était réel, sa fréquence inconnue. Et les deux configurations donnaient
**100 % égalité stricte** : la métrique restait stable pendant que la structure
changeait.

**Reste ouvert (#49)** : le pipeline de production `run.py` passe par
`extractor_singleshot`, qui obtient son moteur via `get_llm()` — même instance en
cache, même défaut, et aucune remise à zéro. Vérifié par lecture
(`engine.py:96`), PAS encore mesuré : le harnais de mesure actuel n'exerce que le
chemin tool-calling. À corriger avec sa propre mesure, pas à l'aveugle.

Après correctif : `combu_ferrite` et `reduc_cu` à 100 % égalité stricte,
traçabilité 100 %. 59 suites, 1339 assertions, 0 échec.

## 2026-08-22 (#49) — Le chemin de production n'avait PAS le défaut : j'avais tort

Dans le rapport de #48 j'ai affirmé que « le pipeline de production a le même
défaut », sur la seule base d'une lecture de `engine.py:96` (`get_llm()` rend la
même instance en cache). J'ai refusé de corriger à l'aveugle et exécuté le
protocole. **Il m'a donné tort.**

Deux runs de `run.py --no-debate` :

| configuration | Cypher produit |
|---|---|
| `reduc_cu` seul | 21 034 car., 88 instructions |
| `reduc_cu` en 2ᵉ position, après `combu_ferrite` | 21 034 car., 88 instructions |

**Identiques à l'octet.** Et c'est précisément la paire qui faisait diverger le
chemin tool-calling (6 étapes / 21 appels seul contre 7 / 12 en lot) : le test
est pertinent, pas complaisant.

**Pourquoi les deux chemins diffèrent** : vérifié qu'aucun swap de modèle n'a
lieu pendant le lot (0 ligne « Swap ») — la même instance sert bien les deux
papiers. La différence tient au MODE D'APPEL. Le tool-calling enchaîne de
nombreux tours dont le préfixe grandit, ce qui fait dépendre lourdement le calcul
du cache hérité ; le single-shot fait UN appel par voie, dont le texte diverge
dès le début du prompt.

**Décision** : ne PAS poser `_contexte_vierge()` sur ce chemin. Ajouter une
prudence non mesurée est une dette (règle 4), et ici la mesure dit qu'elle serait
inutile tout en coûtant une réévaluation complète du contexte.

**Leçon** : une déduction par lecture de code est une hypothèse, pas un résultat.
La règle 9 — vérifier avant d'accuser — vaut aussi quand c'est le CODE que
j'accuse, et pas le modèle.

**Ouvert (#50)** : la remise à zéro de #48 est faite par PAPIER, pas par
ÉCHANTILLON. Sur `crystal` (dix échantillons, 30 précurseurs, 40 étapes) chaque
échantillon hérite du précédent. Non mesuré — et la continuité y est peut-être
souhaitable : c'est un arbitrage à trancher sur la mesure, pas un bug évident.

## 2026-08-22 (#50, EN COURS) — L'héritage entre ÉCHANTILLONS : mesure interrompue

Arrêté à la demande de Terry après 3/10 échantillons.

**Question** : la remise à zéro de #48 est faite par PAPIER, mais
`extract_all_samples` lance une boucle tool-calling par ÉCHANTILLON, sans rien
réinitialiser entre eux.

**Étape 1 acquise, par une voie plus forte qu'un run répété** : l'extraction de
`crystal` est **strictement identique à l'archive**, alors que celle-ci vient
d'une configuration de lot différente. Le papier le plus exposé du corpus
(10 échantillons, 30 précurseurs, 40 étapes) ne bouge pas.
Run A : 126 appels, 1600 s, précurseurs / ratios / durées / rampes à 100 %,
traçabilité 100 % sur 57 valeurs, températures 87,5 % (750 °C manquant).

**Aucune régression de #47 ni #48 sur ce papier** : zéro fusion sur `crystal` —
les lignes du journal sont des REFUS corrects du garde-fou. Le 750 °C manquant
est **préexistant** : températures identiques à l'archive, valeur portée par une
ligne de tableau « 750 ◦C → RT ».

**Étape 2, résultat partiel déjà concluant sur un point** : l'inversion de
l'ordre des échantillons (`SG_SAMPLES_REVERSE=1`, instrumentation inerte en
production) rend l'extraction **~6× plus lente** — 210 s, 1196 s, 898 s contre
~160 s en ordre document, là où le seuil SLOW du projet est à 300 s.
La réutilisation de contexte ENTRE ÉCHANTILLONS est donc **massive** : en ordre
document chacun profite du préfixe du précédent, inversés ils se le détruisent.
Le mécanisme interrogé est réel — observé par son COÛT avant même d'avoir
comparé les voies.

**Reste à faire** : un run inversé complet (~2 h GPU), puis comparaison voie par
voie PAR `sample_id`, pas par position.

**Arbitrage à ne pas trancher d'avance** : la continuité entre échantillons est
peut-être souhaitable — même papier, même prompt système, et le gain de vitesse
mesuré est d'un facteur 6. Si les voies ne changent pas selon l'ordre, ne rien
toucher (règle 4). Une remise à zéro par échantillon coûterait cher et devrait
être justifiée par un gain de fidélité MESURÉ.
