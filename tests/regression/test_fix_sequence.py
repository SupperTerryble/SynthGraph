"""Test hors ligne de _fix_sequence (aucun GPU, aucun LLM).

Les deux defauts sont ceux releves en relisant les voies extraites en chimiste :
collision d'ordre, et palier descendant etiquete « heating ».
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


def build(ops):
    rb = RouteBuilder(source_text="x", target="T", method_type="m")
    rb.operations = ops
    rb._fix_sequence()
    return sorted(rb.operations, key=lambda o: o["order"])


print("\n=== 1. collision d'ordre : deux etapes distinctes a order=1 ===")
r = build([
    {"type": "heating", "operation": "heating", "order": 1, "target_temperature_c": 1100.0},
    {"type": "heating", "operation": "heating", "order": 1, "target_temperature_c": 900.0},
])
ck("les ordres deviennent 1 et 2", [o["order"] for o in r] == [1, 2])

print("\n=== 2. palier descendant requalifie en cooling ===")
ck("l'etape a 900 °C apres 1100 °C est un refroidissement",
   r[1]["type"] == "cooling" and r[1]["operation"] == "cooling")

print("\n=== 3. la rampe descendante devient une vitesse de refroidissement ===")
r = build([
    {"type": "heating", "operation": "heating", "order": 1, "target_temperature_c": 1300.0},
    {"type": "heating", "operation": "heating", "order": 2, "target_temperature_c": 900.0,
     "ramp_rate_c_per_h": 8.0},
])
ck("ramp_rate_c_per_h -> cooling_rate_c_per_h",
   r[1].get("cooling_rate_c_per_h") == 8.0 and "ramp_rate_c_per_h" not in r[1])

print("\n=== 4. une vraie montee n'est JAMAIS requalifiee ===")
r = build([
    {"type": "heating", "operation": "heating", "order": 1, "target_temperature_c": 900.0},
    {"type": "heating", "operation": "heating", "order": 2, "target_temperature_c": 1000.0},
    {"type": "heating", "operation": "heating", "order": 3, "target_temperature_c": 1100.0},
])
ck("les 3 paliers montants restent heating",
   all(o["type"] == "heating" for o in r))
ck("les ordres 1,2,3 distincts sont preserves", [o["order"] for o in r] == [1, 2, 3])

print("\n=== 5. fail-safe : temperature manquante -> aucune requalification ===")
r = build([
    {"type": "heating", "operation": "heating", "order": 1, "target_temperature_c": 1200.0},
    {"type": "heating", "operation": "heating", "order": 2},
    {"type": "heating", "operation": "heating", "order": 3, "target_temperature_c": 1200.0},
])
ck("l'etape sans temperature reste intacte", r[1]["type"] == "heating")
ck("le palier egal (1200 -> 1200) reste heating", r[2]["type"] == "heating")

print("\n=== 6. un cooling deja correct n'est pas retouche ===")
r = build([
    {"type": "heating", "operation": "heating", "order": 1, "target_temperature_c": 1300.0},
    {"type": "cooling", "operation": "cooling", "order": 2, "target_temperature_c": 900.0,
     "cooling_rate_c_per_h": 8.0},
])
ck("cooling conserve son type et sa vitesse",
   r[1]["type"] == "cooling" and r[1]["cooling_rate_c_per_h"] == 8.0)

print(f"\n{ok} OK / {fail} ECHECS")
sys.exit(1 if fail else 0)
