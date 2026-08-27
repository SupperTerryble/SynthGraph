"""Un gold SANS temperature doit distinguer l'abstention de la fabrication.

`broyage_na` (mecanosynthese Na3P) est le premier papier du corpus dont la voie
complete n'a pas un seul palier thermique. Deux comportements opposes du
pipeline doivent alors donner deux verdicts opposes :

  - ne rendre AUCUNE temperature : c'est la bonne reponse ;
  - inventer « 900 C / 12 h » : ces valeurs existent dans le papier mais
    appartiennent a un AUTRE compose (le precurseur P2, produit ailleurs et
    cite par reference). C'est le piege exact de ce papier.

Or `temperatures_pct` vaut `None` dans les DEUX cas — un pourcentage sur un
ensemble vide n'a pas de sens. Le signal ne peut donc venir que de l'egalite
stricte et des valeurs HORS GOLD. Ce test verrouille ce point : sans lui, le
tableau de synthese afficherait « n/a » pour une fabrication comme pour une
abstention, et la regle d'or du projet serait invisible a la mesure.
"""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
ROOT = pathlib.Path(__file__).resolve().parents[2]
from tools.compare_tc_gold import compare  # noqa: E402

ok = fail = 0


def ck(label, cond):
    global ok, fail
    if cond:
        ok += 1
        print(f"  OK    {label}")
    else:
        fail += 1
        print(f"  ECHEC {label}")


GOLD = json.loads((ROOT / "data" / "gold" / "gold_corpus9.json")
                  .read_text(encoding="utf-8"))["broyage_na"]

BROYAGE = {"type": "milling", "operation": "milling", "order": 1, "duration_h": 2}
# Valeurs REELLES du papier, mais rattachees a un autre compose.
FABRIQUE = {"type": "heating", "operation": "heating", "order": 2,
            "target_temperature_c": 900, "duration_h": 12}


def voie(steps):
    return [{"target_material": "Na3P", "synthesis_route": "milling",
             "precursors": [{"formula": "Na", "molar_ratio": 3},
                            {"formula": "P", "molar_ratio": 1}],
             "synthesis_steps": steps}]


print("\n=== le gold lui-meme n'a aucune temperature ===")
ck("key_values est vide", GOLD["key_values"] == [])
ck("une seule duree attendue", GOLD["durations_h"] == [2])

print("\n=== A. abstention : le pipeline ne rend aucune temperature ===")
a = compare(GOLD, voie([BROYAGE]))
ck("aucune temperature hors gold", a["temperatures_hors_gold"] == [])
ck("aucune duree hors gold", a["durations_hors_gold"] == [])
ck("duree retrouvee a 100 %", a["durations_pct"] == 100.0)
ck("egalite stricte sur les temperatures", a["egalite_stricte"]["temperatures"] is True)
ck("egalite stricte sur les durees", a["egalite_stricte"]["durations"] is True)

print("\n=== B. fabrication : 900 C / 12 h pris a un autre compose ===")
b = compare(GOLD, voie([BROYAGE, FABRIQUE]))
ck("la temperature inventee est signalee", b["temperatures_hors_gold"] == [900.0])
ck("la duree inventee est signalee", b["durations_hors_gold"] == [12.0])
ck("egalite stricte ROMPUE sur les temperatures",
   b["egalite_stricte"]["temperatures"] is False)
ck("egalite stricte ROMPUE sur les durees",
   b["egalite_stricte"]["durations"] is False)

print("\n=== C. le pourcentage seul ne suffit PAS a trancher ===")
# Ce test existe pour empecher qu'on rebranche un jour le verdict sur ce
# pourcentage : il est identique des deux cotes, par construction.
ck("temperatures_pct vaut None dans les deux cas",
   a["temperatures_pct"] is None and b["temperatures_pct"] is None)
ck("mais les verdicts d'egalite stricte, eux, different",
   a["egalite_stricte"]["temperatures"] != b["egalite_stricte"]["temperatures"])

print(f"\n{ok} OK / {fail} ECHECS")
sys.exit(1 if fail else 0)
