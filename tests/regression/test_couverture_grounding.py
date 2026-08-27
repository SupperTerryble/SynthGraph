"""TOUTE colonne numerique du schema doit passer le controle anti-invention.

La regle d'or du projet est que rien ne s'invente. Elle repose sur un controle
qui exige, pour chaque valeur numerique, une preuve dans la citation. Mais la
liste des colonnes controlees etait RECOPIEE a la main a trois endroits —
`_CHECKED_NUM` (graph_tools) et deux listes du runner — pendant que le registre
d'etapes, lui, vivait sa vie.

Mesure du 21/08 : DIX-NEUF colonnes numeriques echappaient au controle, dont
`voltage_v`, `gas_flow_sccm`, `from_temperature_c` et `repetitions`. Ce n'est
pas une omission ponctuelle mais une DERIVE STRUCTURELLE : toute colonne ajoutee
au registre y echappait automatiquement, en silence.

Ce test ne verifie pas trois noms : il verifie l'INVARIANT. Ajouter demain une
colonne au registre sans la brancher au controle fera echouer la suite.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from synthgraph.extraction.graph_tools import RouteBuilder  # noqa: E402
from synthgraph.schemas.step_schema import (  # noqa: E402
    STEP_PARAMETERS, colonnes_numeriques)

ok = fail = 0


def ck(label, cond):
    global ok, fail
    if cond:
        ok += 1
        print(f"  OK    {label}")
    else:
        fail += 1
        print(f"  ECHEC {label}")


print("\n=== 1. le registre sait lister ses colonnes numeriques ===")
num = colonnes_numeriques()
ck("la liste n'est pas vide", len(num) > 10)
ck("elle contient les colonnes historiques",
   {"temperature_c", "duration_h", "speed_rpm"} <= num)
ck("elle contient les colonnes ajoutees le 21/08",
   {"voltage_v", "frequency_hz"} <= num)
ck("elle EXCLUT les champs textuels",
   not ({"method", "medium", "atmosphere", "equipment", "description",
         "reference_electrode"} & num))

print("\n=== 2. INVARIANT : aucune colonne numerique n'echappe au controle ===")
couvert = set(RouteBuilder._CHECKED_NUM) | set(RouteBuilder._RATE_KEYS)
echappent = sorted(num - couvert)
ck(f"aucune colonne hors controle (trouve : {echappent[:6]})", not echappent)

print("\n=== 3. le runner partage la MEME liste ===")
try:
    from synthgraph.pipeline.runner import _NUMERIC_STEP_KEYS
    manquantes = sorted(num - set(_NUMERIC_STEP_KEYS)
                        - set(RouteBuilder._RATE_KEYS))
    ck(f"le runner couvre tout (trouve : {manquantes[:6]})", not manquantes)
except ImportError as e:      # le runner tire llama-cpp : ne pas casser la suite
    print(f"  (runner non importable ici : {type(e).__name__})")

print("\n=== 4. les vitesses restent traitees a part ===")
# Une rampe est DERIVEE d'un calcul : sa valeur n'a pas a figurer telle quelle
# (5 °C/min -> 300 °C/h). On verifie la NOTATION, pas le nombre.
ck("les rampes sont dans _RATE_KEYS",
   {"ramp_rate_c_per_h", "cooling_rate_c_per_h"} <= set(RouteBuilder._RATE_KEYS))
ck("et pas dans le controle par valeur",
   not (set(RouteBuilder._RATE_KEYS) & set(RouteBuilder._CHECKED_NUM)))

print("\n=== 5. le registre reste coherent ===")
sans_unite = {c for t, d in STEP_PARAMETERS.items()
              for bloc in ("required", "optional")
              for c, u in (d.get(bloc) or {}).items() if u is None}
ck("aucune colonne n'est a la fois numerique et textuelle",
   not (num & sans_unite))

print(f"\n{ok} OK / {fail} ECHECS")
sys.exit(1 if fail else 0)
