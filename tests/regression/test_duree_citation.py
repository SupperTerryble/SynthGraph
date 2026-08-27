"""La duree ECRITE dans la citation doit etre lue, quelle que soit la tournure.

Mesure de cvd_mos2 (run corpus9, 20/08) : durees 0 % — les QUATRE durees du
gold manquees — alors que le modele avait produit six etapes dont les citations
portaient la duree en toutes lettres. La recuperation existait deja, mais elle
exigeait « for|during|pendant » IMMEDIATEMENT suivi du nombre :

  « heated to 750 °C IN 40 min »           preposition absente de la liste
  « kept for NEXT 25 min »                 mot intercale
  « held for THE NEXT 10 min »             mots intercales
  « lasts for ABOUT 10 min »               mot intercale
  « reaching 180 °C IN 2 min »             preposition absente

Un temps de MONTEE (« in 40 min ») n'est pas un palier (« kept for 25 min ») :
les deux sont conserves comme durees — c'est ce que le gold annote et ce qu'un
chimiste releve — mais `duration_h_source` garde la distinction. On ne convertit
JAMAIS une montee en rampe °C/h : cette conversion inventee a deja rendu
l'egalite stricte inatteignable sur combu_ferrite.
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


def duree(citation, step_type="heating"):
    """duration_h retenue par `add_operation` pour cette citation."""
    rb = RouteBuilder(source_text=citation, target="MoS2", method_type="CVD")
    rb.add_operation(step_type, citation)
    return rb.operations[0].get("duration_h") if rb.operations else None


def presque(a, b):
    return a is not None and abs(a - b) < 0.001


print("\n=== 1. cas reels de cvd_mos2, tous manques avant correctif ===")
ck("« heated to 750 °C in 40 min » -> 0.6667",
   presque(duree("the furnace was heated to 750 °C in 40 min"), 0.6667))
ck("« kept for next 25 min » -> 0.4167",
   presque(duree("and kept for next 25 min"), 0.4167))
ck("« held for the next 10 min » -> 0.1667",
   presque(duree("and then held for the next 10 min"), 0.1667))
ck("« lasts for about 10 min » -> 0.1667",
   presque(duree("The total growth time lasts for about 10 min"), 0.1667))
ck("« reaching 180 °C in 2 min » -> 0.0333",
   presque(duree("with its temperature reaching 180 °C in 2 min"), 0.0333))

print("\n=== 2. non-regression : les tournures deja lues le restent ===")
ck("« for 24 h » -> 24", presque(duree("under stirring at 70°C for 24 h"), 24.0))
ck("« heating for 15 min. » -> 0.25",
   presque(duree("heating for 15 min. at 1000 C"), 0.25))
ck("« during 2 min » -> 0.0333",
   presque(duree("were ball-milled during 2 min at 20 Hz"), 0.0333))
ck("« for 6 hours » -> 6",
   presque(duree("followed by 6 hours of thermal treatment"), 6.0))

print("\n=== 3. REGLE D'OR : ce qui n'est pas chiffre ne donne RIEN ===")
ck("« during the night » : trou, surtout pas 12 h",
   duree("was later dried in a Schlenk tube under vacuum during the night") is None)
ck("« overnight » non plus", duree("the sample was dried overnight") is None)
ck("une citation sans duree", duree("the powder was placed in a crucible") is None)
ck("citation vide", duree("") is None)

print("\n=== 4. PIEGES d'unites : un nombre voisin n'est pas une duree ===")
# « 20 Hz » ne doit jamais devenir 20 heures.
ck("« at 20 Hz » ne donne aucune duree",
   duree("the mixture was milled at 20 Hz") is None)
ck("« in 20 ml of water for 5 min » retient 5 min, pas 20",
   presque(duree("dispersed in 20 ml of deionized water for 5 min"), 0.0833))
ck("« 300 mg of sulfur » ne donne aucune duree",
   duree("heating of 300 mg of sulfur source was started") is None)
ck("« 10-3 mbar » ne donne aucune duree",
   duree("under dynamic vacuum of 10-3 mbar") is None)

print("\n=== 5. la MONTEE reste distinguable du PALIER ===")
rb = RouteBuilder(source_text="the furnace was heated to 750 °C in 40 min",
                  target="MoS2", method_type="CVD")
rb.add_operation("heating", "the furnace was heated to 750 °C in 40 min")
src = rb.operations[0].get("duration_h_source") or ""
ck("une montee est tracee comme telle", "montee" in src)
rb2 = RouteBuilder(source_text="and kept for next 25 min",
                   target="MoS2", method_type="CVD")
rb2.add_operation("heating", "and kept for next 25 min")
src2 = rb2.operations[0].get("duration_h_source") or ""
ck("un palier ne l'est pas", src2 and "montee" not in src2)

print(f"\n{ok} OK / {fail} ECHECS")
sys.exit(1 if fail else 0)
