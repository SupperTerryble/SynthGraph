"""Recuperation du SOLVANT DE REACTION (hors ligne).

L'eau manquait sur `reduc_cu` et `cbd_mnse`, le dioxane sur `cbd_mnse` — jamais
PROPOSES par le modele. Le piege a ne pas rater : `hydro_czts` ecrit « dispersed
into ethanol by ultrasound », mais pour une observation TEM, pas pour la synthese.
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


def run(src, existants=()):
    rb = RouteBuilder(source_text=src, target="x", method_type="y")
    for f, c in existants:
        rb.precursors.append({"name": f, "formula": f, "role": "reactant",
                              "amount": "", "unit": "", "citation": c,
                              "molar_ratio": None})
    n = rb._recover_solvents()
    return rb, n


def formules(rb):
    return {p["formula"] for p in rb.precursors}


print("\n=== 1. cas reels du corpus ===")
rb, n = run("De-ionized water was used for all the experiment.")
ck("« water was used for all the experiment » -> H2O", "H2O" in formules(rb))

rb, n = run("5 ml Se source solution and 5 mL TEA were added to a beaker which "
            "was filled with 40 ml deionized water.")
ck("« filled with 40 ml deionized water » -> H2O", "H2O" in formules(rb))

rb, n = run("The solution is mixed at 1000 rpm and is completed with distilled "
            "water to 100 mL.")
ck("« completed with distilled water » -> H2O", "H2O" in formules(rb))

rb, n = run("2 mmol CuCl2 and 4 mmol of L-cysteine were dispersed in 20 ml of "
            "deionized water for 5 min under constant stirring.")
ck("« dispersed in 20 ml of deionized water » -> H2O", "H2O" in formules(rb))

print("\n=== 2. PIEGE : le solvant d'une MESURE n'est pas celui de la synthese ===")
rb, n = run("Observations of the CZTS sample by TEM and HRTEM were performed "
            "after it had been dispersed into ethanol by ultrasound.")
ck("dispersion pour le TEM : aucun solvant ajoute", n == 0)

rb, n = run("the synthesized nanopowder was dispersed in a water-based solution "
            "with 0.5% sodium dodecylsulfat as a detergent for DLS measurement.")
ck("dispersion pour la DLS : aucun solvant ajoute", n == 0)

print("\n=== 3. PIEGE : un LAVAGE n'est pas un solvant de reaction ===")
rb, n = run("The precipitates were separated by filtration and washed with "
            "deionized water and ethanol for three times.")
ck("« washed with ethanol » : aucun solvant ajoute", n == 0)

print("\n=== 4. REGLE D'OR : le compose doit etre NOMME par la phrase ===")
rb, n = run("The mixture was dissolved in the prepared medium and stirred.")
ck("« the prepared medium » n'est pas un compose : rien", n == 0)

print("\n=== 5. pas de doublon avec un precurseur deja enregistre ===")
CIT = "the powder was dispersed in 20 ml of deionized water for 5 min."
rb, n = run(CIT, existants=[("H2O", CIT)])
ck("H2O deja present : aucun ajout", n == 0)
ck("un seul H2O au total",
   sum(1 for p in rb.precursors if p["formula"] == "H2O") == 1)

print("\n=== 6. le role est bien 'solvent' et la provenance tracee ===")
rb, n = run("De-ionized water was used for all the experiment.")
p = next(p for p in rb.precursors if p["formula"] == "H2O")
ck("role = solvent", p.get("role") == "solvent")
ck("provenance tracee", p.get("precursor_source") == "solvant_recupere")
ck("la citation vient du texte", p.get("citation") in
   "De-ionized water was used for all the experiment.")

print("\n=== 6bis. un VOLUME nomme un reactif (cas reel cbd_mnse) ===")
# « Twenty milliliters concentrate 1-4 dioxane ... are added to a beaker » :
# seule mention du dioxane, jamais declare autrement par le modele.
rb, n = run("Twenty milliliters concentrate 1-4 dioxane and 0.01 mol solid "
            "selenium are added to a beaker with 0.01 mol KOH.")
ck("« Twenty milliliters ... 1-4 dioxane » -> C4H8O2", "C4H8O2" in formules(rb))
p = next((p for p in rb.precursors if p["formula"] == "C4H8O2"), None)
ck("  le dioxane est qualifie de solvant", p and p.get("role") == "solvent")

rb, n = run("5 mL triethanolamine was added to the bath.")
p = next((p for p in rb.precursors if p["formula"] == "C6H15NO3"), None)
ck("la triethanolamine n'est PAS un solvant (agent complexant)",
   p is not None and p.get("role") == "reactant")

print("\n=== 7. fail-safe ===")
rb, n = run("The sample was heated to 1300 C for 24 h.")
ck("aucune tournure de solvant : rien", n == 0)
rb = RouteBuilder(source_text="", target="x", method_type="y")
ck("source vide : rien", rb._recover_solvents() == 0)

print(f"\n{ok} OK / {fail} ECHECS")
sys.exit(1 if fail else 0)
