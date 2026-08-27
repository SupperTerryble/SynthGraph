"""Quantites molaires citees -> rapports molaires (hors ligne).

Cas reel `hydro_czts` : « 2 mmol / 2 mmol / 1 mmol / 4 mmol » releves dans
`amount`, ratios affiches a 0 % alors qu'un chimiste peut peser. La regle d'or
impose de ne rien deduire d'une quantite non prouvee ni d'une unite massique.
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


CIT = ("2 mmol CuCl2 · 2H2O, 2 mmol of ZnCl2, 1 mmol of SnCl2 · 2H2O, 4 mmol of "
       "L-cysteine, and 0 to 3 mmol of EDTA were dispersed in 20 ml of deionized water")


def build(entries):
    rb = RouteBuilder(source_text=CIT, target="CZTS", method_type="hydrothermale")
    for formula, amount in entries:
        rb.precursors.append({"name": formula, "formula": formula, "role": "reactant",
                              "amount": amount, "unit": "", "citation": CIT,
                              "molar_ratio": None})
    rb._infer_ratios_from_amounts()
    return rb.precursors


print("\n=== 1. les mmol cites deviennent des rapports molaires ===")
p = build([("CuCl2·2H2O", "2 mmol"), ("ZnCl2", "2 mmol"),
           ("SnCl2·2H2O", "1 mmol"), ("L-cysteine", "4 mmol")])
ck("CuCl2·2H2O -> 2", p[0]["molar_ratio"] == 2.0)
ck("SnCl2·2H2O -> 1", p[2]["molar_ratio"] == 1.0)
ck("L-cysteine -> 4", p[3]["molar_ratio"] == 4.0)
ck("la provenance est tracee", p[0]["ratio_source"] == "amount_molaire")

print("\n=== 2. une PLAGE ne donne aucun ratio ===")
p = build([("CuCl2·2H2O", "2 mmol"), ("ZnCl2", "2 mmol"), ("EDTA", "0-3 mmol")])
ck("EDTA reste sans ratio", p[2]["molar_ratio"] is None)
ck("les autres sont quand meme deduits", p[0]["molar_ratio"] == 2.0)

print("\n=== 3. REGLE D'OR : les GRAMMES ne donnent rien (masse molaire = inference) ===")
p = build([("CuCl2·2H2O", "2 g"), ("ZnCl2", "2 g")])
ck("aucun ratio deduit d'une masse", all(x["molar_ratio"] is None for x in p))

print("\n=== 4. REGLE D'OR : une quantite ABSENTE de la citation ne compte pas ===")
rb = RouteBuilder(source_text=CIT, target="CZTS", method_type="h")
for f, a in (("CuCl2·2H2O", "7 mmol"), ("ZnCl2", "9 mmol")):
    rb.precursors.append({"name": f, "formula": f, "role": "reactant", "amount": a,
                          "unit": "", "citation": CIT, "molar_ratio": None})
rb._infer_ratios_from_amounts()
ck("7 et 9 absents du texte : aucun ratio",
   all(x["molar_ratio"] is None for x in rb.precursors))

print("\n=== 4bis. REGLE D'OR : le chiffre doit venir de la QUANTITE, pas d'ailleurs ===")
# Cas reel `hydro_czts` : le modele avait attache la phrase de PURETE, qui ne
# porte aucune quantite. Le « 2 » qu'on y trouvait venait de « 2H2O » dans la
# formule — deux ratios avaient ete inscrits sur une preuve inexistante.
PURETE = ("CuCl2 · 2H2O, ZnCl2, SnCl2 · 2H2O, L-cysteine, and EDTA were of "
          "analytical grade and used as received without further purification")
rb = RouteBuilder(source_text=PURETE, target="CZTS", method_type="h")
for f, a in (("CuCl2·2H2O", "2 mmol"), ("ZnCl2", "2 mmol"), ("SnCl2·2H2O", "1 mmol")):
    rb.precursors.append({"name": f, "formula": f, "role": "reactant", "amount": a,
                          "unit": "", "citation": PURETE, "molar_ratio": None})
n = rb._infer_ratios_from_amounts()
ck("citation sans quantite : AUCUN ratio deduit", n == 0)
ck("  le « 2 » de 2H2O ne vaut pas preuve",
   all(x["molar_ratio"] is None for x in rb.precursors))

print("\n=== 5. unites melangees : abstention ===")
p = build([("CuCl2·2H2O", "2 mmol"), ("ZnCl2", "1 mol")])
ck("mmol + mol : aucun ratio deduit", all(x["molar_ratio"] is None for x in p))

print("\n=== 6. un ratio DEJA prouve n'est jamais ecrase ===")
rb = RouteBuilder(source_text=CIT, target="CZTS", method_type="h")
rb.precursors.append({"name": "CuCl2·2H2O", "formula": "CuCl2·2H2O", "role": "reactant",
                      "amount": "2 mmol", "unit": "", "citation": CIT, "molar_ratio": 5.0})
rb.precursors.append({"name": "ZnCl2", "formula": "ZnCl2", "role": "reactant",
                      "amount": "2 mmol", "unit": "", "citation": CIT, "molar_ratio": None})
rb._infer_ratios_from_amounts()
ck("le ratio existant 5.0 est conserve", rb.precursors[0]["molar_ratio"] == 5.0)

print("\n=== 7. un seul candidat : abstention (pas de ratio a un terme) ===")
p = build([("CuCl2·2H2O", "2 mmol")])
ck("un seul compose : aucun ratio", p[0]["molar_ratio"] is None)

print(f"\n{ok} OK / {fail} ECHECS")
sys.exit(1 if fail else 0)
