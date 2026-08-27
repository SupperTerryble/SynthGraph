"""Les reactifs les plus courants doivent se reconnaitre sous leur nom d'usage.

Mesure du 21/08 : 16 noms usuels sur 31 testes etaient absents de
`COMPOUND_NAME_TO_FORMULA` — dont TOUS les acides mineraux (nitrique,
chlorhydrique, sulfurique, phosphorique, fluorhydrique), l'ammoniac et l'eau
oxygenee. Toute la chimie en solution etait concernee.

Consequence constatee sur `electro_nico` : « nitric acid » et « ethylamine »,
ecrits en toutes lettres dans la citation choisie par le modele, ne pouvaient
prouver aucune formule. Les DEUX reactifs de la premiere synthese du papier
etaient refuses a chaque tour — 8 refus sur 14 appels, zero valeur extraite.

Le modele avait raison a chaque fois. C'est la meme cause que `solgel_cuo`
(0 % de precurseurs sur une extraction juste, parce que la citation nommait
« copper acetate ») : la table etait trop courte, pas le modele.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from synthgraph.extraction.graph_tools import _compound_named_in  # noqa: E402
from synthgraph.validation.deterministic import (  # noqa: E402
    normalize_compound_name)

ok = fail = 0


def ck(label, cond):
    global ok, fail
    if cond:
        ok += 1
        print(f"  OK    {label}")
    else:
        fail += 1
        print(f"  ECHEC {label}")


EAN = ("Ethylammonium nitrate (EAN) was prepared by mixing ethylamine and "
       "nitric acid with a molar ratio of 1:1.")

print("\n=== 1. cas reel electro_nico : la phrase nomme, la formule est declaree ===")
ck("« ethylamine » prouve CH3CH2NH2", _compound_named_in("CH3CH2NH2", EAN))
ck("« nitric acid » prouve HNO3", _compound_named_in("HNO3", EAN))

print("\n=== 2. acides mineraux ===")
for nom, f in (("nitric acid", "HNO3"), ("hydrochloric acid", "HCl"),
               ("sulfuric acid", "H2SO4"), ("sulphuric acid", "H2SO4"),
               ("phosphoric acid", "H3PO4"), ("hydrofluoric acid", "HF"),
               ("acetic acid", "CH3COOH"), ("formic acid", "HCOOH")):
    ck(f"« {nom} » -> {f}", normalize_compound_name(nom) == f)

print("\n=== 3. bases, oxydants, organiques ===")
for nom, f in (("ammonia", "NH3"), ("hydrogen peroxide", "H2O2"),
               ("hydrazine", "N2H4"), ("ethylamine", "C2H7N"),
               ("glycerol", "C3H8O3"), ("toluene", "C7H8")):
    ck(f"« {nom} » -> {f}", normalize_compound_name(nom) == f)

print("\n=== 4. elements sous leur nom d'usage (cas broyage_na) ===")
ck("« red phosphorus » -> P", normalize_compound_name("red phosphorus") == "P")
ck("« metallic sodium » -> Na", normalize_compound_name("metallic sodium") == "Na")

print("\n=== 5. MoO2 et MoO3 restent DISTINCTS (piege de cvd_mos2) ===")
# Le papier ecarte explicitement MoO3 : « we choose MoO2, RATHER THAN MoO3 ».
# Les confondre inverserait la lecture.
ck("« molybdenum dioxide » -> MoO2",
   normalize_compound_name("molybdenum dioxide") == "MoO2")
ck("« molybdenum trioxide » -> MoO3",
   normalize_compound_name("molybdenum trioxide") == "MoO3")
ck("les deux ne se confondent pas",
   normalize_compound_name("molybdenum dioxide")
   != normalize_compound_name("molybdenum trioxide"))

print("\n=== 6. non-regression sur les noms deja connus ===")
for nom, f in (("ethanol", "C2H5OH"), ("ascorbic acid", "C6H8O6"),
               ("sodium hydroxide", "NaOH"), ("copper acetate", "Cu(CH3COO)2"),
               ("lithium iodide", "LiI"), ("potassium iodide", "KI")):
    ck(f"« {nom} » -> {f}", normalize_compound_name(nom) == f)

print("\n=== 7. REGLE D'OR : un nom inconnu ne fabrique rien ===")
ck("nom fantaisiste", normalize_compound_name("unobtainium sulfate") is None)
ck("chaine vide", not normalize_compound_name(""))
ck("un compose absent de la phrase reste refuse",
   not _compound_named_in("H2SO4", EAN))

print(f"\n{ok} OK / {fail} ECHECS")
sys.exit(1 if fail else 0)
