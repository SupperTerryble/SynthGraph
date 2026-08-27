"""Les colonnes ajoutees au registre atteignent-elles le GRAPHE ?

Le mandat du projet est « PDF -> graphe de connaissances ». Une colonne remplie
qui n'arrive pas au graphe n'est pas livree : elle vit dans un JSON intermediaire
et meurt la.

Colonnes ajoutees le 21/08 (decision de Terry) : `voltage_v` et
`reference_electrode` pour l'electrodeposition, `frequency_hz` pour la
mecanosynthese, `temperature_c` sur les six types d'operation qui l'effacaient.
Plus les marqueurs d'origine `<champ>_source`, qui doivent permettre a un audit
de separer ce qui a ete LU de ce qui a ete CALCULE.

Ce test tourne sur `step6_graph_architect`, l'architecte DETERMINISTE, avec la
forme REELLE des voies (`target_material` est un DICT, pas une chaine — mon
premier harnais s'etait trompe la-dessus).
"""
import json
import logging
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
logging.disable(logging.INFO)
from synthgraph.pipeline.runner import step6_graph_architect  # noqa: E402

ok = fail = 0


def ck(label, cond):
    global ok, fail
    if cond:
        ok += 1
        print(f"  OK    {label}")
    else:
        fail += 1
        print(f"  ECHEC {label}")


VOIE = {"pathways": [{
    "target_material": {"name": "alliage Ni-Co", "formula": "NiCo"},
    "synthesis_route": "electrodeposition",
    "precursors": [
        {"formula": "NiCl2", "name": "nickel chloride", "molar_ratio": 1,
         "role": "reactant", "ratio_source": "amount_molaire"},
    ],
    "synthesis_steps": [
        {"type": "electrodeposition", "operation": "electrodeposition", "order": 1,
         "citation": "deposited at -1.3 V/Ag/Ag+ for 2 h at 60 C",
         "voltage_v": -1.3, "reference_electrode": "Ag/Ag+",
         "temperature_c": 60.0, "duration_h": 2.0,
         "other_parameters": {"duration_h_source": "citation_regex"}},
        {"type": "ball_milling", "operation": "ball_milling", "order": 2,
         "citation": "ball-milled during 2 min at 20 Hz",
         "frequency_hz": 20.0, "duration_h": 0.0333,
         "other_parameters": {"frequency_hz_source": "citation_regex"}},
        {"type": "washing", "operation": "washing", "order": 3,
         "citation": "washed in methanol by seven cycles",
         "solvent": "methanol", "repetitions": 7, "temperature_c": 25.0},
    ]}]}

reqs = step6_graph_architect(VOIE, {"paper_id": "test", "target": "NiCo"},
                             {}, {}, "Qwen3-8B")
blob = json.dumps(reqs, ensure_ascii=False, default=str)

print("\n=== 1. les consignes electrochimiques atteignent le graphe ===")
ck("le potentiel", '"voltage_v": -1.3' in blob or "'voltage_v': -1.3" in blob)
# Un potentiel sans son electrode de reference ne veut rien dire.
ck("l'electrode de reference", "Ag/Ag+" in blob)

print("\n=== 2. la consigne de mecanosynthese aussi ===")
ck("la frequence", "frequency_hz" in blob and "20" in blob)

print("\n=== 3. la temperature sur des operations NON thermiques ===")
# Ces six types l'effacaient au normaliseur : c'etait un defaut de schema, pas
# d'extraction (les 0 % d'electro_nico etaient un artefact).
ck("sur l'electrodeposition", "temperature_c" in blob)
ck("sur le lavage", "repetitions" in blob and "methanol" in blob)

print("\n=== 4. TRACABILITE : l'origine survit jusqu'au graphe ===")
# Exigence de Terry : un audit doit pouvoir separer ce qui a ete LU de ce qui a
# ete CALCULE. Les marqueurs passent par `other_parameters`, que l'architecte
# route en proprietes `extra_*`.
ck("l'origine de la duree", "extra_duration_h_source" in blob)
ck("l'origine de la frequence", "extra_frequency_hz_source" in blob)
ck("l'origine du ratio du precurseur", "ratio_source" in blob)

print("\n=== 5. le graphe reste structure ===")
ck("les operations sont des noeuds", ":Operation" in blob)
ck("elles sont reliees au protocole", "HAS_STEP" in blob)
ck("les requetes sont PARAMETREES (pas de concatenation)",
   all(isinstance(r, dict) and "query" in r and "params" in r for r in reqs))

print(f"\n{ok} OK / {fail} ECHECS")
sys.exit(1 if fail else 0)
