"""Le nom en toutes lettres vaut-il preuve pour la formule ? (hors ligne)

Cas reel : sur `solgel_cuo` le modele proposait Cu(C2H3O2)2 et (NH4)2CO3 — les
BONS reactifs — refuses parce que la citation dit « copper acetate » et
« ammonium carbonate ». La regle d'or doit rester intacte : un compose ABSENT du
texte reste refuse.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from synthgraph.extraction.graph_tools import (  # noqa: E402
    RouteBuilder, _compound_named_in)

ok = fail = 0


def ck(label, cond):
    global ok, fail
    if cond:
        ok += 1
        print(f"  OK    {label}")
    else:
        fail += 1
        print(f"  ECHEC {label}")


CIT = ("solutions were prepared by mixing stoichiometric amounts of fresh aqueous "
       "15 mM copper acetate (Sigma Aldrich) and 15 mM ammonium carbonate "
       "(Alfa Aesar) solutions at room temperature")

print("\n=== 1. le nom en toutes lettres prouve la formule ===")
ck("« copper acetate » prouve Cu(C2H3O2)2", _compound_named_in("Cu(C2H3O2)2", CIT))
ck("« copper acetate » prouve aussi l'ecriture Cu(CH3COO)2",
   _compound_named_in("Cu(CH3COO)2", CIT))
ck("« ammonium carbonate » prouve (NH4)2CO3", _compound_named_in("(NH4)2CO3", CIT))

print("\n=== 2. REGLE D'OR : un compose absent reste refuse ===")
ck("SrCO3 n'est pas prouve par cette citation", not _compound_named_in("SrCO3", CIT))
ck("NaOH n'est pas prouve par cette citation", not _compound_named_in("NaOH", CIT))
ck("un compose absent d'un texte vide est refuse", not _compound_named_in("CuO", ""))

print("\n=== 3. composition differente = compose different ===")
# CuO et Cu2O partagent les memes elements mais pas la meme composition
ck("« copper acetate » ne prouve PAS CuO", not _compound_named_in("CuO", CIT))

print("\n=== 4. fail-safe : formule illisible ne matche rien ===")
ck("une chaine non chimique ne matche rien",
   not _compound_named_in("!!!", CIT) and not _compound_named_in("", CIT))

print("\n=== 4bis. noms d'UN SEUL mot (water, EDTA, TEA, starch...) ===")
LAV = ("The gel precipitate was collected by centrifugation, washed with "
       "ethanol and distilled water.")
ENUM = "2 mmol of L-cysteine, and 0 to 3 mmol of EDTA were dispersed in 20 ml of water"
ck("« water » prouve H2O", _compound_named_in("H2O", LAV))
ck("« ethanol » prouve C2H5OH", _compound_named_in("C2H5OH", LAV))
ck("« EDTA » prouve C10H16N2O8", _compound_named_in("C10H16N2O8", ENUM))
ck("« L-cysteine » prouve C3H7NO2S", _compound_named_in("C3H7NO2S", ENUM))

print("\n=== 4ter. PIEGE : un nom d'element seul ne prouve pas le metal pur ===")
ck("« copper acetate » ne prouve PAS le cuivre metallique",
   not _compound_named_in("Cu", "Powders of copper acetate were mixed"))
ck("« strontium carbonate » ne prouve PAS le strontium metallique",
   not _compound_named_in("Sr", "Powders of strontium carbonate were mixed"))
ck("SrCO3 reste absent d'une citation de lavage",
   not _compound_named_in("SrCO3", LAV))

print("\n=== 5. bout en bout dans add_precursor ===")
rb = RouteBuilder(source_text=CIT, target="CuO", method_type="sol-gel")
r1 = rb.add_precursor("Cu(C2H3O2)2", CIT)
ck("add_precursor accepte la formule prouvee par le nom", r1.get("ok") is True)
r2 = rb.add_precursor("(NH4)2CO3", CIT)
ck("add_precursor accepte le carbonate d'ammonium", r2.get("ok") is True)
r3 = rb.add_precursor("SrCl2", CIT)
ck("add_precursor REFUSE un compose absent du texte", r3.get("ok") is False)

print("\n=== 6. non-regression : la formule litterale marche toujours ===")
CIT2 = "Powders of IrO2, SrCO3, and SrCl2 · 6H2O were thoroughly mixed"
rb2 = RouteBuilder(source_text=CIT2, target="Sr2IrO4", method_type="flux")
ck("SrCO3 cite litteralement est accepte", rb2.add_precursor("SrCO3", CIT2).get("ok") is True)
ck("un compose absent est toujours refuse",
   rb2.add_precursor("NaOH", CIT2).get("ok") is False)

print(f"\n{ok} OK / {fail} ECHECS")
sys.exit(1 if fail else 0)
