"""Un ratio non prouve ne doit plus emporter le precurseur (hors ligne).

Cas reel `cbd_mnse` : LiAlH4 et la triethanolamine, tous deux nommes dans leur
citation, rejetes en bloc parce que le modele y avait joint « molar_ratio=1 »
absent du texte. La regle d'or reste : la valeur non prouvee est JETEE, jamais
enregistree.
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


SRC = ("Then 0.01 mol LiAlH4 is added immediately to the beaker before the gel cools. "
       "The components of the baths were 8 % HCl, 5 mL 0.001 M manganese nitrate, "
       "5 mL of the prepared Se source solution, and 5 mL triethanolamine (TEA). "
       "Powders of IrO2, SrCO3 were mixed in a 1 : 2 ratio and heated.")

CIT_LIALH4 = "Then 0.01 mol LiAlH4 is added immediately to the beaker before the gel cools."
CIT_RATIO = "Powders of IrO2, SrCO3 were mixed in a 1 : 2 ratio and heated."


def rb():
    return RouteBuilder(source_text=SRC, target="MnSe", method_type="CBD")


print("\n=== 1. le precurseur survit a un ratio non prouve ===")
r = rb()
res = r.add_precursor("LiAlH4", CIT_LIALH4, molar_ratio=1)
ck("l'appel est accepte", res.get("ok") is True)
ck("il est signale comme PARTIEL", res.get("partial") is True)
ck("LiAlH4 est bien enregistre", any(p["formula"] == "LiAlH4" for p in r.precursors))

print("\n=== 2. REGLE D'OR : le ratio non prouve n'est PAS enregistre ===")
ck("molar_ratio reste None", r.precursors[0]["molar_ratio"] is None)
ck("le rejet est trace", any("ecarte" in x for x in r.rejections))

print("\n=== 3. un ratio PROUVE est toujours conserve ===")
r2 = rb()
r2.add_precursor("IrO2", CIT_RATIO, molar_ratio=1)
r2.add_precursor("SrCO3", CIT_RATIO, molar_ratio=2)
ck("IrO2 garde son ratio 1", r2.precursors[0]["molar_ratio"] == 1.0)
ck("SrCO3 garde son ratio 2", r2.precursors[1]["molar_ratio"] == 2.0)

print("\n=== 4. les autres refus restent des refus ===")
r3 = rb()
ck("compose absent du texte : REFUSE",
   r3.add_precursor("NaOH", CIT_LIALH4).get("ok") is False)
ck("citation trop courte : REFUSE",
   r3.add_precursor("LiAlH4", "8 % HCl").get("ok") is False)
ck("citation ne nommant pas le compose : REFUSE",
   r3.add_precursor("LiAlH4", CIT_RATIO).get("ok") is False)

print("\n=== 5. enrichissement : le ratio arrive au second appel ===")
r4 = rb()
r4.add_precursor("IrO2", CIT_RATIO, molar_ratio=99)      # 99 absent -> ecarte
ck("premier appel : aucun ratio", r4.precursors[0]["molar_ratio"] is None)
r4.add_precursor("IrO2", CIT_RATIO, molar_ratio=1)       # 1 present -> garde
ck("second appel : le ratio prouve complete l'entree",
   r4.precursors[0]["molar_ratio"] == 1.0)
ck("un seul IrO2 enregistre (pas de doublon)", len(r4.precursors) == 1)

print(f"\n{ok} OK / {fail} ECHECS")
sys.exit(1 if fail else 0)
