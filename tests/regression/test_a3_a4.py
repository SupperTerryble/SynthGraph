"""Tests offline A3 (atmosphere sur citation) + A4 (vitesse != duree)."""
import pathlib
import sys
# Racine du depot, pas un chemin absolu : ce test pointait en dur vers un dossier
# SynthGraph_V4.4, donc il validait le code d'une ANCIENNE version des que
# celle-ci existait sur la machine.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from synthgraph.schemas.step_schema import normalize_step
from synthgraph.pipeline.runner import _validate_extraction_against_text

ok = fail = 0
def check(label, cond, detail=""):
    global ok, fail
    if cond:
        ok += 1; print(f"  PASS  {label}")
    else:
        fail += 1; print(f"  FAIL  {label}  {detail}")

print("=== A4 : une vitesse ne doit jamais devenir une duree ===")

# Cas reel du gold : « 1300 C -> (8 C/h) -> 900 C »
# NB: on verifie d'abord que le type possede BIEN un champ duration_h, sinon
# le test serait faussement vert (rien a refuser).
from synthgraph.schemas.step_schema import STEP_PARAMETERS, resolve_step_type
_t = resolve_step_type("calcination")
_cols = {**STEP_PARAMETERS[_t]["required"], **STEP_PARAMETERS[_t]["optional"]}
assert "duration_h" in _cols, "le test doit porter sur un type ayant duration_h"

s = normalize_step({"operation": "calcination", "citation": "1300 C to 900 C",
                    "duration_h": "8 °C/h"})
check("'8 °C/h' refuse pour duration_h (type AVEC duration_h)",
      s.get("duration_h") is None, f"got={s.get('duration_h')}")
check("'8 °C/h' reaffecte a une vitesse", s.get("ramp_rate_c_per_h") == 8.0
      or s.get("cooling_rate_c_per_h") == 8.0,
      f"ramp={s.get('ramp_rate_c_per_h')} cool={s.get('cooling_rate_c_per_h')}")

# et le type cooling doit rediriger vers cooling_rate_c_per_h
s = normalize_step({"operation": "cooling", "citation": "1300 C to 900 C",
                    "duration_h": "8 °C/h"})
check("type cooling : reaffecte a cooling_rate_c_per_h",
      s.get("cooling_rate_c_per_h") == 8.0, f"got={s.get('cooling_rate_c_per_h')}")

s = normalize_step({"operation": "cooling", "citation": "x", "duration_h": "45 C/h"})
check("'45 C/h' (sans degre) refuse", s.get("duration_h") is None, f"got={s.get('duration_h')}")

s = normalize_step({"operation": "soak", "citation": "held for 24 h", "duration_h": "24 h"})
check("'24 h' reste une duree", s.get("duration_h") == 24.0, f"got={s.get('duration_h')}")

s = normalize_step({"operation": "soak", "citation": "held", "duration_h": 24})
check("nombre nu 24 reste une duree", s.get("duration_h") == 24.0, f"got={s.get('duration_h')}")

s = normalize_step({"operation": "calcination", "citation": "at 5 °C/min",
                    "duration_h": "5 °C/min"})
check("'5 °C/min' refuse pour duration_h", s.get("duration_h") is None, f"got={s.get('duration_h')}")

print("\n=== A3 : atmosphere justifiee par SA citation ===")

def run_a3(atm, citation, full_text):
    ex = {"pathways": [{"synthesis_steps": [
        {"order": 1, "type": "heating", "atmosphere": atm, "citation": citation}]}]}
    _validate_extraction_against_text(ex, citation, full_text)
    st = ex["pathways"][0]["synthesis_steps"][0]
    holes = [m for m in ex["pathways"][0].get("missing_parameters", [])
             if m.get("parameter") == "atmosphere"]
    return st.get("atmosphere"), holes

# justifiee -> conservee
a, h = run_a3("air", "heated in a box furnace in air", "... in air ...")
check("'air' justifiee par sa citation -> conservee", a == "air", f"got={a}")

# LE cas dangereux : citation dit H2, graphe dit air
a, h = run_a3("air", "reduction was achieved under a 20 ml/min H2 atmosphere",
              "blah air blah H2")
check("'air' contredite par H2 -> purgee", a is None, f"got={a}")
check("  et un trou est declare", len(h) == 1, f"trous={len(h)}")

# muette : le mot existe ailleurs dans le doc mais pas dans la citation
a, h = run_a3("vacuum", "hydrothermal synthesis at 170 C in an electric oven",
              "... dried under vacuum ... electric oven ...")
check("'vacuum' presente au doc mais absente de la citation -> purgee",
      a is None, f"got={a}")

# synonyme accepte
a, h = run_a3("N2", "annealed under nitrogen flow", "nitrogen")
check("'N2' justifiee par le synonyme 'nitrogen'", a == "N2", f"got={a}")

a, h = run_a3("O2", "heated in flowing O2", "flowing O2")
check("'O2' justifiee par sa citation", a == "O2", f"got={a}")

print(f"\n{ok} PASS / {fail} FAIL")

print("\n=== A4b : nombre nu + preuve dans la citation ===")
s = normalize_step({"operation": "calcination", "duration_h": 8,
                    "citation": "1300 °C → (8 °C/h) → 900 °C → RT"})
check("duration_h=8 nu retire (citation dit 8 °C/h)", s.get("duration_h") is None,
      f"got={s.get('duration_h')}")
check("  et reaffecte en vitesse", s.get("ramp_rate_c_per_h") == 8.0
      or s.get("cooling_rate_c_per_h") == 8.0,
      f"ramp={s.get('ramp_rate_c_per_h')}")

s = normalize_step({"operation": "calcination", "duration_h": 24,
                    "citation": "1300 °C (24 h dwell) → (8 °C/h) → 1100 °C"})
check("duration_h=24 CONSERVEE (24 est un palier, pas une vitesse)",
      s.get("duration_h") == 24.0, f"got={s.get('duration_h')}")

s = normalize_step({"operation": "soak", "duration_h": 60,
                    "citation": "1000 °C, 60 h; and 1100 °C, 60 h"})
check("duration_h=60 conservee (vraie duree)", s.get("duration_h") == 60.0,
      f"got={s.get('duration_h')}")

print("\n=== A3b : atmosphere prouvee AILLEURS dans le protocole ===")
def run_pw(steps, extra=""):
    # full_text doit CONTENIR les citations, sinon le grounding supprime la voie
    full = " ".join(s.get("citation","") for s in steps) + " " + extra
    ex = {"pathways": [{"synthesis_steps": steps}]}
    _validate_extraction_against_text(ex, full, full)
    pws = ex.get("pathways") or []
    if not pws:
        return [None] * len(steps)
    return [s.get("atmosphere") for s in pws[0]["synthesis_steps"]]

# cas PhysRevB : O2 prouve par la citation de l'etape de melange
res = run_pw([
    {"order":1,"type":"mixing","citation":"Starting materials SrCO3, IrO2, and RuO2 were mixed and heated in flowing O2"},
    {"order":2,"type":"heating","atmosphere":"O2","citation":"900 °C, 24 h; 1000 °C, 60 h"},
], "flowing O2 ... 900 C")
check("O2 conservee (prouvee par une autre citation du protocole)",
      res[1] == "O2", f"got={res[1]}")

# contradiction : purge malgre une preuve ailleurs
res = run_pw([
    {"order":1,"type":"mixing","citation":"heated in air"},
    {"order":2,"type":"heating","atmosphere":"air","citation":"reduction under a 20 ml/min H2 atmosphere"},
], "air ... H2")
check("air PURGEE si sa propre citation dit H2 (contradiction prime)",
      res[1] is None, f"got={res[1]}")

# aucune preuve nulle part
res = run_pw([
    {"order":1,"type":"mixing","citation":"powders were mixed"},
    {"order":2,"type":"heating","atmosphere":"vacuum","citation":"heated at 900 C"},
], "no atmosphere here")
check("vacuum purgee (aucune preuve dans le protocole)", res[1] is None, f"got={res[1]}")

print(f"\nTOTAL {ok} PASS / {fail} FAIL")

print("\n=== A3c : confusables OCR (0 lu pour O) ===")
# Cas REEL de PhysRevB : le scan ecrit « flowing 02 » avec un ZERO
res = run_pw([
    {"order":1,"type":"mixing","citation":"Starting materials SrCO3, IrO2, and RuO2 were mixed and heated in flowing 02."},
    {"order":2,"type":"heating","atmosphere":"O2","citation":"900 C, 24 h; 1000 C, 60 h"},
])
check("O2 conservee malgre 'flowing 02' (zero OCR)", res[1] == "O2", f"got={res[1]}")

res = run_pw([
    {"order":1,"type":"heating","atmosphere":"O2","citation":"heated in flowing 02 for 24 h"},
])
check("O2 justifiee par sa propre citation OCR-degradee", res[0] == "O2", f"got={res[0]}")

# non-regression : une atmosphere reellement absente reste purgee
res = run_pw([
    {"order":1,"type":"heating","atmosphere":"argon","citation":"heated in flowing 02 for 24 h"},
])
check("argon purgee (citation dit O2, contradiction)", res[0] is None, f"got={res[0]}")

print(f"\nTOTAL FINAL {ok} PASS / {fail} FAIL")
