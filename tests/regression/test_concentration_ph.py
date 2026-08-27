"""Concentration molaire et pH, recuperes des citations.

Mesure du corpus (`tools/vocabulaire_parametres.py`) : la concentration figure
dans les phrases operatoires de 7 papiers sur 8 sans avoir de colonne au schema.
En chimie de solution c'est la donnee de pesee — « 5 mL de nitrate de manganese »
ne dit rien sans « 0,001 M ».

Recuperation DETERMINISTE, jamais en demandant au modele : deux mesures
independantes ont etabli que tout ajout a son interface se paie ailleurs.
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


def conc(formule, citation):
    rb = RouteBuilder(source_text=citation, target="x", method_type="y")
    rb.precursors = [{"name": formule, "formula": formule, "role": "reactant",
                      "amount": "", "unit": "", "citation": citation,
                      "molar_ratio": None}]
    rb._recover_concentrations()
    return rb.precursors[0].get("concentration")


def ph(citation):
    rb = RouteBuilder(source_text=citation, target="x", method_type="y")
    rb.operations = [{"type": "soak", "operation": "soak", "order": 1,
                      "citation": citation}]
    rb._recover_ph()
    return rb.operations[0].get("ph")


BAIN = ("The components of the baths were 8 % HCl, 5 mL 0.001 M manganese "
        "nitrate, 5 mL of the prepared Se source solution, and 5 mL "
        "triethanolamine (TEA).")

print("\n=== 1. la concentration PRECEDE le compose ===")
ck("« 0.001 M manganese nitrate » -> Mn(NO3)2",
   conc("Mn(NO3)2", BAIN) == "0.001 M")
ck("nom en toutes lettres, formule enregistree : le lien est fait",
   conc("Mn(NO3)2", BAIN) is not None)

print("\n=== 2. PIEGE : un voisin ne herite pas ===")
# HCl est donne a « 8 % », pas en molarite — et il n'est qu'a quatorze
# caracteres du « 0.001 M » qui appartient au nitrate.
ck("HCl ne recoit pas la concentration du nitrate", conc("HCl", BAIN) is None)
ck("la TEA non plus", conc("C6H15NO3", BAIN) is None)

print("\n=== 3. la concentration SUIT, entre parentheses ===")
ck("« CuSO4 5H2O (0.1 M) »",
   conc("CuSO4·5H2O", "Copper sulphate pentahydrate CuSO4 5H2O (0.1 M) was used.")
   == "0.1 M")
ck("« Sodium hydroxide NaOH (1 M) »",
   conc("NaOH", "Sodium hydroxide NaOH (1 M) were purchased.") == "1 M")

print("\n=== 4. les millimolaires aussi ===")
ck("« 15 mM copper acetate »",
   conc("Cu(CH3COO)2", "mixing stoichiometric amounts of fresh aqueous 15 mM "
                       "copper acetate and 15 mM ammonium carbonate.") == "15 mM")

print("\n=== 5. REGLE D'OR : sans concentration dans la citation, rien ===")
ck("une citation sans molarite ne donne rien",
   conc("SrCO3", "Powders of IrO2, SrCO3, and SrCl2 were thoroughly mixed.") is None)
ck("un compose absent de sa citation ne recoit rien",
   conc("KOH", "0.1 M copper sulfate was dissolved in water.") is None)

print("\n=== 6. pH de CONSIGNE seulement ===")
ck("« adjust the pH value of the solution to 10 » -> 10",
   ph("In order to adjust the pH value of the solution to 10, 2 mL of "
      "8 % HCl were added.") == 10.0)
# Cas REEL de cbd_mnse : la phrase pose TROIS bains d'un coup.
ck("« ... to 10, 9, 8 » : abstention, ce sont trois experiences",
   ph("In order to adjust the pH value of the solution to 10, 9, 8; 2, 4 and "
      "8 mL of 8 % HCl, respectively, were added to the solutions.") is None)
ck("« prepared with pH: 11 » -> 11",
   ph("baths prepared with pH: 11 were used for the deposition.") == 11.0)

print("\n=== 7. PIEGE : un pH de RESULTAT n'est pas une consigne ===")
ck("« the best crystalline at pH: 9 » -> rien",
   ph("The films had the best crystalline at pH: 9.") is None)
ck("« the highest refractive index at a pH of 10 » -> rien",
   ph("The highest refractive index was observed in films at a pH of 10.") is None)

print("\n=== 8. fail-safe ===")
ck("citation vide : aucune concentration", conc("NaOH", "") is None)
ck("citation vide : aucun pH", ph("") is None)

print(f"\n{ok} OK / {fail} ECHECS")
sys.exit(1 if fail else 0)
