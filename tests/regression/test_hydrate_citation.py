"""La forme HYDRATEE est retablie quand la citation la porte.

Cas reel `crystal` : le modele enregistre `SrCl2` alors que SA PROPRE citation
dit « Powders of IrO2, SrCO3, and SrCl2 · 6H2O were thoroughly mixed ». L'ecart
n'est pas cosmetique : 266,6 g/mol contre 158,5 — un chimiste qui pese le sel
anhydre se trompe de 40 %.

On ne fait que COMPLETER, jamais retirer.
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


def run(formule, citation):
    rb = RouteBuilder(source_text=citation, target="x", method_type="y")
    rb.precursors = [{"name": formule, "formula": formule, "role": "reactant",
                      "amount": "", "unit": "", "citation": citation,
                      "molar_ratio": None}]
    rb._completer_hydrate()
    return rb.precursors[0]


CIT = "Powders of IrO2, SrCO3, and SrCl2 · 6H2O were thoroughly mixed."

print("\n=== 1. cas reel crystal ===")
p = run("SrCl2", CIT)
ck("SrCl2 devient SrCl2·6H2O", p["formula"] == "SrCl2·6H2O")
ck("  le nom suit la formule", p["name"] == p["formula"])
ck("  la provenance est tracee", p.get("hydrate_source") == "citation")

print("\n=== 2. les autres composes de la meme citation sont INTACTS ===")
ck("IrO2 reste IrO2", run("IrO2", CIT)["formula"] == "IrO2")
ck("SrCO3 reste SrCO3", run("SrCO3", CIT)["formula"] == "SrCO3")

print("\n=== 3. un hydrate DEJA enregistre n'est pas retouche ===")
p = run("SrCl2·6H2O", CIT)
ck("la forme hydratee est conservee telle quelle",
   p["formula"] == "SrCl2·6H2O" and p.get("hydrate_source") is None)

print("\n=== 4. sans hydrate dans la citation, rien ===")
p = run("SrCl2", "Powders of IrO2, SrCO3, and SrCl2 were thoroughly mixed.")
ck("l'anhydre reste anhydre", p["formula"] == "SrCl2")

print("\n=== 5. autres notations de l'hydrate ===")
for cit, attendu in (
        ("2 mmol CuCl2 · 2H2O were dispersed in water.", "CuCl2·2H2O"),
        ("Copper sulphate pentahydrate CuSO4.5H2O was used.", "CuSO4·5H2O")):
    formule = attendu.split("·")[0]
    p = run(formule, cit)
    ck(f"« {cit[:34]}... » -> {attendu}", p["formula"] == attendu)

print("\n=== 6. fail-safe ===")
p = run("SrCl2", "")
ck("citation vide : rien", p["formula"] == "SrCl2")

print(f"\n{ok} OK / {fail} ECHECS")
sys.exit(1 if fail else 0)
