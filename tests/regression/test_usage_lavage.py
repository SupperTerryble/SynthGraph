"""Un compose prouve par une SEULE phrase de lavage n'est pas un reactif.

Cas reel `solgel_cuo` : le modele declarait l'ethanol de rincage comme
precurseur du CuO, avec pour citation « washed with ethanol and distilled
water ». Un chimiste tenterait de l'ajouter au milieu reactionnel.

On ne supprime rien — l'information reste, qualifiee par son usage — et le
solvant du lavage figure de toute facon sur l'etape correspondante.
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


def ajoute(formule, citation, role="reactant"):
    rb = RouteBuilder(source_text=citation, target="CuO", method_type="sol-gel")
    rb.add_precursor(formule, citation, role=role)
    return rb.precursors[0] if rb.precursors else None


print("\n=== 1. cas reel : l'ethanol de rincage est qualifie ===")
p = ajoute("C2H5OH", "the gel precipitate was collected by centrifugation, "
                     "washed with ethanol and distilled water.", role="solvent")
ck("le compose est CONSERVE", p is not None)
ck("son usage est 'lavage'", p and p.get("usage") == "lavage")

print("\n=== 2. un reactif reel n'est jamais qualifie ainsi ===")
p = ajoute("Cu(CH3COO)2", "stoichiometric amounts of fresh aqueous 15 mM copper "
                          "acetate and 15 mM ammonium carbonate were mixed.")
ck("l'acetate de cuivre n'a pas d'usage 'lavage'", p and p.get("usage") is None)

p = ajoute("H2O", "2 mmol CuCl2 were dispersed in 20 ml of deionized water.")
ck("l'eau de dispersion n'est pas un lavage", p and p.get("usage") is None)

print("\n=== 3. une phrase qui lave ET synthetise reste un reactif ===")
p = ajoute("C2H5OH", "the powder was dissolved in ethanol and washed with "
                     "ethanol before heating.")
ck("indice de synthese present : aucun usage 'lavage'",
   p and p.get("usage") is None)

print("\n=== 4. autres formulations de lavage ===")
for formule, cit in (("H2O", "the crystals were rinsed with distilled water."),
                     ("C3H6O", "the solid was rinsed with acetone twice.")):
    p = ajoute(formule, cit)
    ck(f"« {cit[:38]}... » qualifie", p and p.get("usage") == "lavage")

print("\n=== 5. la citation reste intacte ===")
CIT = "washed with ethanol and distilled water."
p = ajoute("C2H5OH", CIT, role="solvent")
ck("citation conservee telle quelle", p and p["citation"] == CIT.strip())
ck("role conserve", p and p["role"] == "solvent")

print(f"\n{ok} OK / {fail} ECHECS")
sys.exit(1 if fail else 0)
