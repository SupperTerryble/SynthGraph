"""Un rapport ECRIT EN TOUTES LETTRES doit etre lu.

Sur `electro_nico`, le modele declare `ratio = 1` pour l'ethylamine ET pour
l'acide nitrique — les BONNES valeurs — mais attache la phrase des REACTIFS
(« Ethylamine (CH3CH2NH2, 70 wt.% in water, Acros Organics), nitric acid
(HNO3, ...) »), qui ne porte aucun rapport. Les deux sont donc ecartes.

Le rapport est pourtant dans la phrase voisine, aussi explicite que possible :

    « Ethylammonium nitrate (EAN) was prepared by mixing ethylamine and nitric
      acid with a MOLAR RATIO OF 1:1 »

Aucun des trois mecanismes d'inference existants ne couvre ce cas :
`_infer_ratios_from_enumeration` lit une enumeration, `_infer_ratios_from_amounts`
des quantites pesees, `_infer_ratios_from_target_formula` deduit d'une formule.
Aucun ne lit un rapport ENONCE.

PORTEE MESUREE AVANT D'ECRIRE : 2 papiers du corpus enoncent un rapport en
toutes lettres, et un seul en manque les valeurs — `electro_nico`, a 0 % de
ratios, le plus faible du corpus. Deux occurrences, mais un gain REEL : ce que
j'ai refuse de construire le meme jour a 2 occurrences (heritage de maintien)
n'apportait RIEN de nouveau, les valeurs figurant deja ailleurs.
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


def ratios(source, formules, citation=None):
    rb = RouteBuilder(source_text=source, target="EAN", method_type="X")
    cit = citation or source
    rb.precursors = [{"name": f, "formula": f, "role": "reactant", "unit": "",
                      "amount": "", "citation": cit, "molar_ratio": None}
                     for f in formules]
    rb._infer_ratios_from_enonce()
    return {p["formula"]: p.get("molar_ratio") for p in rb.precursors}


EAN = ("Ethylammonium nitrate (EAN) was prepared by mixing ethylamine and "
       "nitric acid with a molar ratio of 1:1.")
REACTIFS = ("Ethylamine (CH3CH2NH2, 70 wt.% in water, Acros Organics), nitric "
            "acid (HNO3, 68 wt.% in water) were used as received.")

print("\n=== 1. cas reel electro_nico ===")
r = ratios(REACTIFS + " " + EAN, ["CH3CH2NH2", "HNO3"], citation=REACTIFS)
ck("l'ethylamine recoit 1", r.get("CH3CH2NH2") == 1)
ck("l'acide nitrique aussi", r.get("HNO3") == 1)

print("\n=== 2. l'origine est TRACEE ===")
rb = RouteBuilder(source_text=REACTIFS + " " + EAN, target="EAN", method_type="X")
rb.precursors = [{"name": f, "formula": f, "role": "reactant", "unit": "",
                  "amount": "", "citation": REACTIFS, "molar_ratio": None}
                 for f in ("CH3CH2NH2", "HNO3")]
rb._infer_ratios_from_enonce()
ck("origine = ratio_enonce",
   all(p.get("ratio_source") == "ratio_enonce" for p in rb.precursors))

print("\n=== 3. un rapport NOMME suit ses composes ===")
SEL = ("2.9 g LiI (21.7 mmol) and 2.1 g KI (12.7 mmol) (molar ratio LiI:KI "
       "0.63:0.37) were ball-milled.")
r = ratios(SEL, ["LiI", "KI"])
ck("LiI recoit 0,63", r.get("LiI") == 0.63)
ck("KI recoit 0,37", r.get("KI") == 0.37)

print("\n=== 4. le rapport ne concerne QUE les composes NOMMES ===")
# Regle CORRIGEE apres mesure : exiger que le nombre de termes egale le nombre
# de precurseurs SANS RAPPORT rendait le mecanisme INERTE — `electro_nico` a
# QUATRE precurseurs sans rapport et l'enonce n'a que DEUX termes, parce que la
# phrase ne concerne que l'ethylamine et l'acide nitrique. Les chlorures de
# nickel et de cobalt n'y sont pour rien.
r4 = ratios(EAN + " " + REACTIFS, ["CH3CH2NH2", "HNO3", "NiCl2", "CoCl2"],
            citation=REACTIFS)
ck("les deux composes NOMMES recoivent 1:1",
   r4.get("CH3CH2NH2") == 1 and r4.get("HNO3") == 1)
ck("les deux autres restent intacts",
   r4.get("NiCl2") is None and r4.get("CoCl2") is None)

print("\n=== 4bis. GARDE : le compte des NOMMES doit correspondre ===")
# L'eau n'est pas nommee par l'enonce : elle ne recoit rien, et les deux
# composes cites sont servis. C'est la garde qui compte desormais — l'ancienne,
# fondee sur TOUS les precurseurs sans rapport, rendait le mecanisme inerte.
r = ratios(EAN, ["CH3CH2NH2", "HNO3", "H2O"])
ck("les deux composes nommes sont servis",
   r.get("CH3CH2NH2") == 1 and r.get("HNO3") == 1)
ck("l'eau, non nommee, ne recoit rien", r.get("H2O") is None)
# TROIS termes face a DEUX composes nommes : impossible de repartir.
r = ratios("the reagents were mixed in a molar ratio of 1:2:7 as described, "
           "with IrO2 and SrCO3 as sources.", ["IrO2", "SrCO3"])
ck("trois termes, deux composes -> abstention",
   not any(v for v in r.values()))

print("\n=== 5. GARDE : un ratio DEJA connu n'est pas ecrase ===")
rb = RouteBuilder(source_text=EAN, target="EAN", method_type="X")
rb.precursors = [{"name": "CH3CH2NH2", "formula": "CH3CH2NH2", "role": "reactant",
                  "unit": "", "amount": "", "citation": EAN, "molar_ratio": 9.0},
                 {"name": "HNO3", "formula": "HNO3", "role": "reactant",
                  "unit": "", "amount": "", "citation": EAN, "molar_ratio": None}]
rb._infer_ratios_from_enonce()
ck("le ratio lu est conserve", rb.precursors[0]["molar_ratio"] == 9.0)

print("\n=== 6. REGLE D'OR : sans enonce, RIEN ===")
r = ratios("Powders of IrO2 and SrCO3 were thoroughly mixed.", ["IrO2", "SrCO3"])
ck("aucun rapport enonce", not any(v for v in r.values()))
r = ratios("", ["IrO2", "SrCO3"])
ck("source vide", not any(v for v in r.values()))

print("\n=== 7. PIEGE : une PLAGE n'est pas un rapport ===")
# « between 1.5 and 4.3 V » ou « 170 to 190 °C » ne sont pas des proportions.
r = ratios("The cells were tested between 1.5 and 4.3 V.", ["A", "B"])
ck("une plage de tension ne donne rien", not any(v for v in r.values()))

print(f"\n{ok} OK / {fail} ECHECS")
sys.exit(1 if fail else 0)
