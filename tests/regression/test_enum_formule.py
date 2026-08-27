"""Une FORMULE prouvee par une enumeration de NOMS (hors ligne).

Cas reel `prepara` (1957) : « the reaction between iridium metal powder and
strontium oxide, carbonate, nitrate or hydroxide » designe QUATRE sources de
strontium. Le modele proposait SrCO3, Sr(NO3)2 et Sr(OH)2 — refusees comme
« absentes du texte », car `_enumerated_compound` decoupe un NOM en prefixe +
suffixe et « SrCO3 » ne fait qu'un mot. Rappel bloque a 40 %.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from synthgraph.extraction.graph_tools import (  # noqa: E402
    RouteBuilder, _enumerated_by_name)

ok = fail = 0


def ck(label, cond):
    global ok, fail
    if cond:
        ok += 1
        print(f"  OK    {label}")
    else:
        fail += 1
        print(f"  ECHEC {label}")


ENUM = ("Strontium-iridium oxide is obtained readily by the reaction between "
        "iridium metal powder and strontium oxide, carbonate, nitrate or "
        "hydroxide at 1200 in air.")

print("\n=== 1. les formules de l'enumeration sont prouvees ===")
for f in ("SrCO3", "Sr(NO3)2", "Sr(OH)2"):
    ck(f"{f} prouve par l'enumeration", _enumerated_by_name(f, ENUM))

print("\n=== 2. PIEGE : le nom du PRODUIT ne prouve pas un precurseur ===")
# « strontium-iridium oxide » contient « iridium oxide » par accident de
# sous-chaine : c'est le produit Sr2IrO4, pas un precurseur IrO2.
ck("IrO2 n'est PAS prouve", not _enumerated_by_name("IrO2", ENUM))

print("\n=== 3. REGLE D'OR : un compose hors enumeration reste refuse ===")
for f in ("NaOH", "SrCl2", "BaCO3", "K2CO3"):
    ck(f"{f} n'est pas prouve", not _enumerated_by_name(f, ENUM))

print("\n=== 4. bout en bout : add_precursor accepte les trois sources ===")
rb = RouteBuilder(source_text=ENUM, target="Sr2IrO4", method_type="etat solide")
for f in ("SrCO3", "Sr(NO3)2", "Sr(OH)2"):
    r = rb.add_precursor(f, ENUM)
    ck(f"add_precursor({f}) accepte", r.get("ok") is True)
ck("les 3 sources sont enregistrees", len(rb.precursors) == 3)

print("\n=== 5. bout en bout : un compose absent reste REFUSE ===")
ck("add_precursor(NaOH) refuse", rb.add_precursor("NaOH", ENUM).get("ok") is False)
ck("add_precursor(BaCO3) refuse", rb.add_precursor("BaCO3", ENUM).get("ok") is False)

print("\n=== 6. fail-safe ===")
ck("texte vide : rien", not _enumerated_by_name("SrCO3", ""))
ck("formule illisible : rien", not _enumerated_by_name("!!!", ENUM))

print(f"\n{ok} OK / {fail} ECHECS")
sys.exit(1 if fail else 0)
