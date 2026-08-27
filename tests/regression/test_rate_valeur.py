"""Une vitesse doit etre prouvee par SA VALEUR, pas par la presence d'une notation.

Cas reel `crystal` : `cooling_rate_c_per_h=0` accepte sur la citation
« Sr214#1 1 : 2 : 7 1300 C -> (8 C/h) 900 C -> RT ». Une vitesse de 0 °C/h
inscrite dans le graphe alors que le papier dit 8 — invention silencieuse.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from synthgraph.extraction.graph_tools import RouteBuilder  # noqa: E402

ok = fail = 0


def ck(label, cond):
    global ok, fail
    if cond:
        ok += 1
        print(f"  OK    {label}")
    else:
        fail += 1
        print(f"  ECHEC {label}")


CIT = "Sr214#1 1 : 2 : 7 1300\u25e6C \u2192 (8\u25e6C/h) 900\u25e6C \u2192 RT"


def op(**params):
    rb = RouteBuilder(source_text=CIT, target="Sr2IrO4", method_type="flux")
    r = rb.add_operation("cooling", CIT, **params)
    return rb, r


print("\n=== 1. la vitesse REELLE du papier est conservee ===")
rb, r = op(cooling_rate_c_per_h=8)
ck("8 C/h accepte", rb.operations[0].get("cooling_rate_c_per_h") == 8.0)

print("\n=== 2. REGLE D'OR : une vitesse absente de la citation est ecartee ===")
rb, r = op(cooling_rate_c_per_h=0)
ck("0 C/h n'entre PAS dans le graphe",
   "cooling_rate_c_per_h" not in rb.operations[0])
ck("l'appel est signale PARTIEL", r.get("partial") is True)
ck("le motif est explicite", any("n'apparait pas" in x for x in rb.rejections))

rb, r = op(cooling_rate_c_per_h=45)
ck("45 C/h (valeur d'une AUTRE ligne) est ecarte",
   "cooling_rate_c_per_h" not in rb.operations[0])

print("\n=== 3. citation sans aucune notation de vitesse : refus inchange ===")
SANS = "The crucibles were heated in a programmable box furnace in air"
rb = RouteBuilder(source_text=SANS, target="x", method_type="y")
rb.add_operation("cooling", SANS, cooling_rate_c_per_h=8)
ck("aucune notation de vitesse : ecarte",
   "cooling_rate_c_per_h" not in rb.operations[0])
ck("le motif distingue les deux cas",
   any("aucune notation" in x for x in rb.rejections))

print("\n=== 4. non-regression : les autres parametres passent toujours ===")
rb, r = op(cooling_rate_c_per_h=8, temperature_c=900)
ck("900 C conserve", rb.operations[0].get("target_temperature_c") == 900.0
   or rb.operations[0].get("temperature_c") == 900.0)
ck("8 C/h conserve", rb.operations[0].get("cooling_rate_c_per_h") == 8.0)

print(f"\n{ok} OK / {fail} ECHECS")
sys.exit(1 if fail else 0)
