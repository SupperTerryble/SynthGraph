"""Le TUBE est un contenant — mais « tube furnace » est un appareil.

Mesure de selfondu_cosi (run corpus9, 20/08) : `equipment=quartz tube
(Ø28×H345mm)` REFUSE, « ni contenant ni appareil », puis `equipment=Schlenk
tube` refuse de meme. Or le tube de quartz scelle est le contenant le plus
courant de la chimie du solide et des sels fondus, et sa nature decide de la
faisabilite au meme titre qu'un creuset : ce papier chauffe a 400 °C sous vide
dynamique avec un piege a azote liquide en aval.

Le piege est immediat : « tube furnace » est un APPAREIL. Ajouter « tube » sans
precaution ferait passer le four pour le contenant — exactement l'inversion que
la distinction contenant/appareil a ete ecrite pour empecher.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from synthgraph.extraction.graph_tools import (  # noqa: E402
    _EQUIPMENT_RE, _VESSEL_ONLY_RE)

ok = fail = 0


def ck(label, cond):
    global ok, fail
    if cond:
        ok += 1
        print(f"  OK    {label}")
    else:
        fail += 1
        print(f"  ECHEC {label}")


def contenant(s):
    return bool(_VESSEL_ONLY_RE.search(s))


def equipement(s):
    return bool(_EQUIPMENT_RE.search(s))


print("\n=== 1. cas reels de selfondu_cosi ===")
ck("« quartz tube » est un contenant", contenant("quartz tube (28x345mm)"))
ck("« Schlenk tube » est un contenant", contenant("dried in a Schlenk tube"))

print("\n=== 2. autres tubes de la chimie du solide ===")
for t in ("sealed tube", "silica tube", "glass tube", "reaction tube",
          "centrifuge tube", "test tube"):
    ck(f"« {t} »", contenant(t))

print("\n=== 3. PIEGE : « tube furnace » est un APPAREIL, pas un contenant ===")
ck("« tube furnace » n'est PAS un contenant", not contenant("heated in a tube furnace"))
ck("  mais reste un equipement reconnu", equipement("heated in a tube furnace"))
ck("« tubular furnace » n'est pas un contenant",
   not contenant("placed in a tubular furnace"))
ck("« tube reactor » n'est pas un contenant", not contenant("a tube reactor was used"))

print("\n=== 4. non-regression : les contenants deja connus ===")
for t in ("platinum crucible", "autoclave", "acid digestion bomb", "boat",
          "quartz ampoule", "beaker", "Teflon liner"):
    ck(f"« {t} »", contenant(t))

print("\n=== 5. fail-safe ===")
ck("chaine vide", not contenant(""))
ck("« room temperature » n'est pas un contenant", not contenant("room temperature"))

print(f"\n{ok} OK / {fail} ECHECS")
sys.exit(1 if fail else 0)
