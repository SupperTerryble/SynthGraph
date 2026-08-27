"""Le MINIMUM DE REFAISABILITE est-il exige, et les trous declares ?

Decision de Terry (20/08). Constat qui l'a motivee : `heating` n'exigeait que
`target_temperature_c` — ni duree, ni atmosphere — et `mixing` n'exigeait RIEN.
Un chimiste ne peut refaire ni l'un ni l'autre : les scores eleves mesuraient
des criteres trop faibles.

Regle d'or inchangee : un manque n'est jamais comble, il est DECLARE.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from synthgraph.schemas.step_schema import (  # noqa: E402
    MINIMUM_REFAISABILITE, normalize_steps)

ok = fail = 0


def ck(label, cond):
    global ok, fail
    if cond:
        ok += 1
        print(f"  OK    {label}")
    else:
        fail += 1
        print(f"  ECHEC {label}")


def trous(step):
    _, missing = normalize_steps([step])
    return {m["parameter"]: m for m in missing}


print("\n=== 1. une chauffe sans duree ni atmosphere : deux trous requis ===")
t = trous({"type": "heating", "order": 1, "target_temperature_c": 1300})
ck("`duration_h` est un trou", "duration_h" in t)
ck("  severite required", t.get("duration_h", {}).get("severity") == "required")
ck("  origine tracee", t.get("duration_h", {}).get("origine") == "minimum_refaisabilite")
ck("`atmosphere` est un trou", "atmosphere" in t)

print("\n=== 2. une chauffe COMPLETE ne cree aucun de ces trous ===")
t = trous({"type": "heating", "order": 1, "target_temperature_c": 1300,
           "duration_h": 24, "atmosphere": "air"})
ck("aucun trou de duree", "duration_h" not in t)
ck("aucun trou d'atmosphere", "atmosphere" not in t)

print("\n=== 3. un melange sans methode est declare incomplet ===")
t = trous({"type": "mixing", "order": 1})
ck("`method` est un trou requis",
   t.get("method", {}).get("severity") == "required")
t = trous({"type": "mixing", "order": 1, "method": "ball milling"})
ck("avec la methode, plus de trou", "method" not in t)

print("\n=== 4. un refroidissement sans vitesse ===")
t = trous({"type": "cooling", "order": 1, "target_temperature_c": 900})
ck("`cooling_rate_c_per_h` est requis",
   t.get("cooling_rate_c_per_h", {}).get("severity") == "required")

print("\n=== 5. un sechage sans temperature ni duree ===")
t = trous({"type": "drying", "order": 1})
ck("`temperature_c` requis", t.get("temperature_c", {}).get("severity") == "required")
ck("`duration_h` requis", t.get("duration_h", {}).get("severity") == "required")

print("\n=== 6. NON-REGRESSION : les trous d'origine subsistent ===")
t = trous({"type": "washing", "order": 1})
ck("`solvent` (requis d'origine) toujours declare",
   t.get("solvent", {}).get("severity") == "required")
ck("  sans marqueur d'origine", "origine" not in t.get("solvent", {}))
ck("`repetitions` ajoute par le durcissement",
   t.get("repetitions", {}).get("origine") == "minimum_refaisabilite")

print("\n=== 7. aucun doublon entre les deux couches ===")
t = trous({"type": "calcination", "order": 1})
_, missing = normalize_steps([{"type": "calcination", "order": 1}])
noms = [m["parameter"] for m in missing]
ck("chaque parametre n'apparait qu'une fois", len(noms) == len(set(noms)))

print("\n=== 8. un type sans minimum defini n'est pas penalise ===")
_, missing = normalize_steps([{"type": "generic", "order": 1, "citation": "x"}])
ck("`generic` ne recoit aucun trou de refaisabilite",
   all(m.get("origine") != "minimum_refaisabilite" for m in missing))
ck("les types couverts sont bien ceux valides par Terry",
   set(MINIMUM_REFAISABILITE) == {"heating", "calcination", "annealing",
                                  "sintering", "soak", "cooling", "mixing",
                                  "grinding", "washing", "drying"})

print(f"\n{ok} OK / {fail} ECHECS")
sys.exit(1 if fail else 0)
