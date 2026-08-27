"""Une LIGNE DE TABLEAU n'a pas de position dans le deroule du protocole.

L'atmosphere trouvee dans la source n'est appliquee qu'aux etapes dont la
citation apparait APRES la mention — une atmosphere nommee tardivement ne dit
rien de ce qui s'est passe avant, et cette regle est juste pour du texte suivi.

Mais sur `crystal` elle bloque tout : la mention « The crucibles were heated in
a programmable box furnace IN AIR » est en position 10479, tandis que les
lignes du TABLEAU qui portent les programmes thermiques sont en 9200 — donc
« avant ». Or un tableau est IMPRIME ailleurs ; sa position dans le document ne
dit rien de sa position dans la recette.

Cout mesure : 8 atmospheres manquantes sur ce seul papier, toutes presentes
dans la source. `crystal` obtient pourtant 100 % en precurseurs, ratios et
durees — l'audit de REFAISABILITE le voit, la comparaison au gold non.

Le projet a deja arbitre que le tableau est une SOURCE DE PREMIER RANG
(re-ancrage des citations sur les lignes de tableau, runner.py). On applique ici
le meme principe : une citation qui est une ligne de tableau echappe a la
contrainte de position.
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


# Ordre REEL du papier : le tableau AVANT la prose qui nomme l'atmosphere.
SRC = ("Table 1. Sr214#1 1 : 2 : 7 1300 C to 900 C then RT. "
       "Sr214#2 1 : 2 : 7 1100 C to 1300 C then 900 C. "
       "Powders of IrO2, SrCO3, and SrCl2 were thoroughly mixed and placed in "
       "a platinum crucible covered with a lid. "
       "The crucibles were heated in a programmable box furnace in air then "
       "cooled to room temperature.")
LIGNE = "Sr214#1 1 : 2 : 7 1300 C to 900 C then RT"
PROSE = ("Powders of IrO2, SrCO3, and SrCl2 were thoroughly mixed and placed in "
         "a platinum crucible covered with a lid")


def voie(paires):
    rb = RouteBuilder(source_text=SRC, target="Sr2IrO4", method_type="flux")
    for typ, cit in paires:
        rb.add_operation(typ, cit)
    st = rb.to_pathways_dict()["pathways"][0]["synthesis_steps"]
    return {(s.get("type") or "").lower(): s.get("atmosphere")
            for s in sorted(st, key=lambda x: x.get("order") or 0)}


print("\n=== 1. cas reel crystal : le tableau precede la prose ===")
par = voie([("heating", LIGNE), ("mixing", PROSE)])
ck("le chauffage cite par le TABLEAU recoit l'air", par.get("heating") == "air")

print("\n=== 2. REGLE D'OR : le melange n'herite de RIEN ===")
# Attente CORRIGEE : le papier dit « The CRUCIBLES WERE HEATED ... in air ».
# Rien n'y attribue une atmosphere au melange des poudres, et la propagation ne
# va que vers l'avant. Lui en donner une serait une invention — mon assertion
# initiale etait plus gourmande que la regle, pas l'inverse.
ck("le melange, ANTERIEUR a la mention, n'a pas d'atmosphere",
   par.get("mixing") is None)

print("\n=== 3. GARDE : une atmosphere tardive ne remonte pas a du TEXTE SUIVI ===")
# Une phrase de prose situee avant la mention ne doit toujours rien recevoir :
# c'est la regle d'origine, et elle protege contre une atmosphere retroactive.
SRC2 = ("The precursors were dissolved in deionized water under constant "
        "stirring for 10 min. Later the gel was calcined in a tube furnace "
        "under flowing argon at 600 C.")
rb = RouteBuilder(source_text=SRC2, target="X", method_type="Y")
rb.add_operation("mixing", "The precursors were dissolved in deionized water "
                           "under constant stirring for 10 min")
st = rb.to_pathways_dict()["pathways"][0]["synthesis_steps"]
ck("une dissolution ANTERIEURE ne recoit pas l'argon",
   all(s.get("atmosphere") is None for s in st))

print("\n=== 4. le tableau reste reconnaissable a ses separateurs ===")
rb = RouteBuilder(source_text=SRC, target="Sr2IrO4", method_type="flux")
ck("« 1 : 2 : 7 ... 1300 C to 900 C » est une ligne de tableau",
   rb._est_ligne_de_tableau(LIGNE))
ck("une phrase de prose n'en est pas une",
   not rb._est_ligne_de_tableau(PROSE))
ck("une phrase vide non plus", not rb._est_ligne_de_tableau(""))

print(f"\n{ok} OK / {fail} ECHECS")
sys.exit(1 if fail else 0)
