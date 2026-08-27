"""Un qualificatif de FORME ne doit pas faire perdre le compose.

Mesure de selfondu_cosi (run corpus9, 20/08) : le silicium — reactif PRINCIPAL
du papier — refuse trois fois de suite, avec le message « la citation fournie ne
mentionne pas 'Si nanoparticles' ». Or le compose y est, deux fois :

  phrase des reactifs   « silicon nanoparticles (99%, Nanomakers) »
  phrase operatoire     « 63.2 mg Si nanoparticles (2.3 mmol) »

Le modele avait raison et suivait la formulation exacte de l'article. C'est le
controle qui echouait : `_compound_named_in("Si", ...)` rend True, mais
`"Si nanoparticles"` rend False — la formule ne se parse plus, donc le repli par
composition elementaire est saute.

Sixieme cas de la meme famille dans ce projet : l'outillage accusait le modele.

La REGLE D'OR n'est pas assouplie — on retire un mot de FORME (nanoparticules,
poudre, feuille...), jamais un mot de CHIMIE. Le compose doit toujours etre
prouve dans le texte, et un compose absent reste refuse.
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


REAG = ("Lithium iodide (99%, Alfa Aesar), potassium iodide (99%, Sigma-Aldrich), "
        "silicon nanoparticles (99%, Nanomakers, France) and cobalt(II) chloride "
        "(99.7%, Alfa Aesar) were stored in an Ar-filled glovebox.")
OPER = ("63.2 mg Si nanoparticles (2.3 mmol), 194.8 mg CoCl2 (1.5 mmol), 2.9 g "
        "LiI (21.7 mmol) and 2.1 g KI (12.7 mmol) were ball-milled during 2 min.")

print("\n=== 1. cas reel : le silicium, sous ses deux ecritures ===")
ck("« Si nanoparticles » prouve par « silicon nanoparticles »",
   _compound_named_in("Si nanoparticles", REAG))
ck("« Si nanoparticles » prouve par la phrase operatoire",
   _compound_named_in("Si nanoparticles", OPER))
ck("« Si » seul continue de passer", _compound_named_in("Si", REAG))

print("\n=== 2. autres qualificatifs de forme ===")
# BORNE DELIBEREE, inchangee par ce correctif : un mot d'element NU ne prouve
# jamais un metal, sinon « copper » suffirait a prouver du cuivre metal dans
# n'importe quel papier qui parle d'oxyde de cuivre. Il faut au moins deux mots
# — et c'est bien le cas reel : « silicon nanoparticles ».
ck("« Cu powder » N'EST PAS prouve par « copper » seul",
   not _compound_named_in("Cu powder", "copper was used as received"))
ck("« Zn foil » non plus par « zinc » seul",
   not _compound_named_in("Zn foil", "a zinc electrode was polished"))
ck("« MoO2 nanopowder »",
   _compound_named_in("MoO2 nanopowder", "a boat containing 1 mg of MoO2"))

print("\n=== 3. REGLE D'OR : un compose ABSENT reste refuse ===")
ck("« Ag nanoparticles » absent du texte",
   not _compound_named_in("Ag nanoparticles", REAG))
ck("un qualificatif seul ne prouve rien",
   not _compound_named_in("nanoparticles", REAG))
ck("une formule illisible ne matche rien", not _compound_named_in("!!!", REAG))

print("\n=== 4. les mots de CHIMIE ne sont jamais retires ===")
# « acetate », « oxide », « chloride » portent la composition : les retirer
# ferait passer n'importe quel sel de cuivre pour du cuivre metal.
ck("« copper acetate » n'est pas reduit a « copper »",
   not _compound_named_in("Cu(CH3COO)2", "copper was used as received"))
ck("« CuO » n'est pas prouve par « copper » seul",
   not _compound_named_in("CuO", "copper foil was cleaned"))

print("\n=== 5. non-regression sur les ecritures deja acceptees ===")
ck("hydrate au point median",
   _compound_named_in("CuSO4·5H2O", "Copper sulphate pentahydrate CuSO4 5H2O"))
ck("nom en toutes lettres", _compound_named_in("SrCO3", "strontium carbonate was mixed"))
ck("formule litterale", _compound_named_in("LiI", REAG))

print("\n=== 6. la formule STOCKEE est nettoyee ===")
# Sans quoi le comparateur cherche « Si » et trouve « Si nanoparticles ».
rb = RouteBuilder(source_text=OPER, target="CoSi", method_type="sels fondus")
r = rb.add_precursor("Si nanoparticles", OPER)
ck("le precurseur est ACCEPTE", r.get("ok") is True)
ck("il est stocke sous « Si »",
   bool(rb.precursors) and rb.precursors[0].get("formula") == "Si")

print(f"\n{ok} OK / {fail} ECHECS")
sys.exit(1 if fail else 0)
