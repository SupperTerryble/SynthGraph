"""Un hydrate note avec un POINT doit donner la meme composition que le point median.

`Fe(NO3)2.9H2O` etait lu « 2,9 » comme un decimal : N=2,9 et O=9,7 au lieu de
N=2, O=15, H=18. Le bilan elementaire sert de VETO dans le pipeline (un bilan en
echec force REJECT quoi que dise le LLM) : une stoechiometrie corrompue pouvait
rejeter une extraction correcte, ou en valider une fausse.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from synthgraph.validation.deterministic import parse_composition  # noqa: E402
from synthgraph.extraction.graph_tools import _composition_key  # noqa: E402

ok = fail = 0


def ck(label, cond):
    global ok, fail
    if cond:
        ok += 1
        print(f"  OK    {label}")
    else:
        fail += 1
        print(f"  ECHEC {label}")


print("\n=== 1. les deux ecritures donnent la MEME composition ===")
PAIRES = [
    ("Fe(NO3)2.9H2O", "Fe(NO3)2\u00b79H2O"),
    ("Ni(NO3)2.6H2O", "Ni(NO3)2\u00b76H2O"),
    ("Zn(NO3)2.6H2O", "Zn(NO3)2\u00b76H2O"),
    ("SrCl2.6H2O", "SrCl2\u00b76H2O"),
    ("CuSO4.5H2O", "CuSO4\u00b75H2O"),
    ("CuCl2.2H2O", "CuCl2\u00b72H2O"),
]
for point, median in PAIRES:
    ck(f"{point} == {median}", parse_composition(point) == parse_composition(median))

print("\n=== 2. la stoechiometrie est la BONNE, pas seulement coherente ===")
c = parse_composition("Fe(NO3)2.9H2O")
ck("N = 2 (et non 2,9)", c.get("N") == 2.0)
ck("O = 15 (2x3 du nitrate + 9 de l'eau)", c.get("O") == 15.0)
ck("H = 18 (9 x H2O)", c.get("H") == 18.0)

print("\n=== 3. l'equivalence elementaire en profite ===")
ck("les cles de composition coincident",
   _composition_key("Fe(NO3)2.9H2O") == _composition_key("Fe(NO3)2\u00b79H2O"))

print("\n=== 4. NON-REGRESSION : un vrai decimal reste un decimal ===")
ck("Sr2.5Ir1O4 garde Sr = 2,5", parse_composition("Sr2.5Ir1O4").get("Sr") == 2.5)
ck("Sr1.8IrO4 garde Sr = 1,8", parse_composition("Sr1.8IrO4").get("Sr") == 1.8)

print("\n=== 5. non-regression : les formules simples sont intactes ===")
for f, attendu in (("SrCO3", {"Sr": 1.0, "C": 1.0, "O": 3.0}),
                   ("IrO2", {"Ir": 1.0, "O": 2.0}),
                   ("H2O", {"H": 2.0, "O": 1.0})):
    ck(f"{f} inchange", parse_composition(f) == attendu)

print(f"\n{ok} OK / {fail} ECHECS")
sys.exit(1 if fail else 0)
