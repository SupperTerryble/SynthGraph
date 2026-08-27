"""La quantite molaire peut etre prouvee par le TEXTE, pas seulement la citation.

Sur `hydro_czts` le modele releve correctement « 2 mmol / 2 mmol / 1 mmol /
4 mmol » — dans une meme reaction, ces nombres SONT les rapports molaires. Mais
il attache a chaque precurseur la phrase de PURETE :

    « CuCl2 · 2H2O, ZnCl2, SnCl2 · 2H2O, L-cysteine, and EDTA were of
      analytical grade »

...qui ne porte aucune quantite. Le garde-fou exigeant la preuve dans la
citation DU PRECURSEUR ecartait donc les quatre, et la mesure affichait 0 % de
ratios sur un papier ou un chimiste peut peser sans hesiter.

Ce garde-fou est JUSTE et reste en place — il a ete pose apres que deux ratios
eurent ete inscrits sur une preuve inexistante, le « 2 » trouve venant de
« 2H2O » dans la formule. On l'elargit au TEXTE SOURCE avec la meme regle
d'ADJACENCE que les concentrations : la quantite doit toucher le compose.
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


SRC = ("CuCl2 · 2H2O, ZnCl2, SnCl2 · 2H2O, L-cysteine, and EDTA were of "
       "analytical grade and used without further purification. In a typical "
       "synthesis, 2 mmol CuCl2 · 2H2O, 2 mmol of ZnCl2, 1 mmol of SnCl2 · "
       "2H2O, 4 mmol of L-cysteine, and 0 to 3 mmol of EDTA were dispersed in "
       "20 ml of deionized water for 5 min under constant stirring.")
PURETE = ("CuCl2 · 2H2O, ZnCl2, SnCl2 · 2H2O, L-cysteine, and EDTA were of "
          "analytical grade and used without further purification.")


def infere(compo, source=SRC, citation=PURETE):
    rb = RouteBuilder(source_text=source, target="Cu2ZnSnS4", method_type="hydro")
    rb.precursors = [{"name": f, "formula": f, "role": "reactant", "unit": "",
                      "amount": a, "citation": citation, "molar_ratio": None}
                     for f, a in compo]
    n = rb._infer_ratios_from_amounts()
    return n, {p["formula"]: p.get("molar_ratio") for p in rb.precursors}


print("\n=== 1. cas reel hydro_czts : la quantite est dans le TEXTE ===")
n, r = infere([("CuCl2·2H2O", "2 mmol"), ("ZnCl2", "2 mmol"),
               ("SnCl2·2H2O", "1 mmol"), ("L-cysteine", "4 mmol")])
ck("quatre ratios deduits", n == 4)
ck("CuCl2·2H2O -> 2", r.get("CuCl2·2H2O") == 2)
ck("ZnCl2 -> 2", r.get("ZnCl2") == 2)
ck("SnCl2·2H2O -> 1", r.get("SnCl2·2H2O") == 1)
ck("L-cysteine -> 4", r.get("L-cysteine") == 4)

print("\n=== 2. la preuve par la CITATION marche toujours ===")
CIT = "2 mmol CuCl2 · 2H2O and 1 mmol of SnCl2 · 2H2O were dispersed"
n, r = infere([("CuCl2·2H2O", "2 mmol"), ("SnCl2·2H2O", "1 mmol")],
              source=CIT, citation=CIT)
ck("deux ratios deduits", n == 2)

print("\n=== 3. REGLE D'OR : le « 2 » de 2H2O ne prouve RIEN ===")
# Defaut reel, corrige le 20/08 : deux ratios avaient ete inscrits parce que le
# chiffre nu se trouvait dans la formule elle-meme.
SANS = ("CuCl2 · 2H2O and SnCl2 · 2H2O were of analytical grade and used "
        "without further purification in this synthesis of kesterite.")
n, r = infere([("CuCl2·2H2O", "2 mmol"), ("SnCl2·2H2O", "1 mmol")],
              source=SANS, citation=SANS)
ck("aucun ratio sur une preuve inexistante", n == 0)

print("\n=== 4. ADJACENCE : une quantite lointaine n'est pas la sienne ===")
LOIN = ("2 mmol of copper chloride was weighed. After a long paragraph about "
        "the furnace, the crucible, the atmosphere and the cooling profile, "
        "we finally mention ZnCl2 which is a common reagent in this field.")
n, r = infere([("ZnCl2", "2 mmol")], source=LOIN, citation=LOIN)
ck("ZnCl2 ne capte pas le « 2 mmol » du cuivre", r.get("ZnCl2") is None)

print("\n=== 5. GARDES d'unites, inchangees ===")
n, r = infere([("Cu(CH3COO)2", "15 mM"), ("(NH4)2CO3", "15 mM")])
ck("une CONCENTRATION n'est pas une quantite", n == 0)
n, r = infere([("CuCl2·2H2O", "2.5 g"), ("ZnCl2", "1.5 g")])
ck("des GRAMMES exigeraient les masses molaires : refus", n == 0)
n, r = infere([("EDTA", "0 to 3 mmol"), ("ZnCl2", "2 mmol")])
ck("une PLAGE ne donne aucun nombre unique", r.get("EDTA") is None)

print("\n=== 6. GARDES structurelles ===")
n, r = infere([("ZnCl2", "2 mmol")])
ck("un seul candidat ne fait pas un rapport", n == 0)
MIXTE = ("2 mmol of ZnCl2 and 1 mol of SnCl2 were used in this typical "
         "synthesis of the kesterite phase.")
n, r = infere([("ZnCl2", "2 mmol"), ("SnCl2", "1 mol")], source=MIXTE, citation=MIXTE)
ck("deux unites differentes : abstention", n == 0)

print("\n=== 7. un ratio DEJA connu n'est pas ecrase ===")
rb = RouteBuilder(source_text=SRC, target="Cu2ZnSnS4", method_type="hydro")
rb.precursors = [
    {"name": "ZnCl2", "formula": "ZnCl2", "amount": "2 mmol", "citation": PURETE,
     "molar_ratio": 9.0, "role": "reactant", "unit": ""},
    {"name": "SnCl2·2H2O", "formula": "SnCl2·2H2O", "amount": "1 mmol",
     "citation": PURETE, "molar_ratio": None, "role": "reactant", "unit": ""},
    {"name": "CuCl2·2H2O", "formula": "CuCl2·2H2O", "amount": "2 mmol",
     "citation": PURETE, "molar_ratio": None, "role": "reactant", "unit": ""}]
rb._infer_ratios_from_amounts()
ck("le ratio lu est conserve", rb.precursors[0]["molar_ratio"] == 9.0)

print("\n=== 8. fail-safe ===")
n, r = infere([])
ck("aucun precurseur", n == 0)
n, r = infere([("ZnCl2", ""), ("CuCl2", "")])
ck("aucune quantite", n == 0)

print(f"\n{ok} OK / {fail} ECHECS")
sys.exit(1 if fail else 0)
