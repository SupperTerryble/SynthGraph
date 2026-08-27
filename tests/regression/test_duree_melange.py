"""Un melange a droit a sa duree — si sa citation n'en porte qu'UNE.

La recuperation de duree excluait `mixing` et `grinding`, par prudence : une
citation de melange enonce souvent PLUSIEURS actions, et lui attribuer la duree
du chauffage qui suit fabriquerait une recette fausse.

Mesure du 21/08 : cette prudence coute exactement une valeur sur `hydro_czts`.
L'etape 1 est un `mixing` dont la citation dit « dispersed in 20 ml of deionized
water FOR 5 MIN under constant stirring » ; le modele n'a pas rempli le champ et
l'exclusion a bloque le rattrapage. C'est la difference entre l'egalite stricte
sur les durees et son echec.

J'avais decide de laisser l'exclusion faute de cout mesure. La mesure l'a
dementi. On la leve donc, en gardant ce qu'elle protegeait : pour un melange ou
un broyage, la citation ne doit porter qu'UNE SEULE duree distincte. Deux durees
dans la meme phrase, c'est l'ambiguite que l'exclusion visait — abstention.
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


def duree(citation, step_type):
    rb = RouteBuilder(source_text=citation, target="CZTS", method_type="hydro")
    rb.add_operation(step_type, citation)
    return rb.operations[0].get("duration_h") if rb.operations else None


def presque(a, b):
    return a is not None and abs(a - b) < 0.001


HYDRO = ("2 mmol CuCl2 and 4 mmol of L-cysteine were dispersed in 20 ml of "
         "deionized water for 5 min under constant stirring, and then "
         "transferred to an acid digestion bomb")

print("\n=== 1. cas reel hydro_czts : une seule duree dans la phrase ===")
ck("le melange recoit ses 5 min", presque(duree(HYDRO, "mixing"), 0.0833))
ck("un broyage aussi",
   presque(duree("the powders were ground for 30 min in a mortar", "grinding"), 0.5))
ck("« ball-milled during 2 min » (broyage_na)",
   presque(duree("the solids were ball-milled during 2 min at 20 Hz", "milling"), 0.0333))

print("\n=== 2. GARDE : deux durees dans la phrase -> ABSTENTION ===")
# C'est exactement ce que l'exclusion protegeait : attribuer au melange la duree
# du traitement thermique qui le suit fabriquerait une recette fausse.
DEUX = ("the mixture was stirred for 10 min and then heated at 180 C for 12 h")
ck("un melange n'en retient AUCUNE", duree(DEUX, "mixing") is None)
ck("un broyage non plus", duree(DEUX, "grinding") is None)

print("\n=== 3. les autres operations gardent le comportement acquis ===")
# Pour un chauffage, la premiere duree de la citation reste retenue : ce
# comportement est teste par test_duree_citation.py et ne change pas.
ck("un chauffage retient la premiere duree", presque(duree(DEUX, "heating"), 0.1667))
ck("« for 24 h »", presque(duree("stirred at 70 C for 24 h", "heating"), 24.0))

print("\n=== 4. REGLE D'OR : rien de chiffre, rien de produit ===")
ck("melange sans duree",
   duree("the powders were thoroughly mixed in an agate mortar", "mixing") is None)
ck("« overnight » ne donne rien",
   duree("the slurry was stirred overnight", "mixing") is None)
ck("citation vide", duree("", "mixing") is None)

print("\n=== 5. deux mentions de la MEME duree ne sont pas une ambiguite ===")
MEME = "each powder was milled for 15 min, then milled again for 15 min"
ck("« 15 min » deux fois -> 0.25", presque(duree(MEME, "grinding"), 0.25))

print(f"\n{ok} OK / {fail} ECHECS")
sys.exit(1 if fail else 0)
