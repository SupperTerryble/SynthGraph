"""Tests A1 : re-ancrage des citations sur les lignes de tableau."""
import pathlib
import sys
# Racine du depot, pas un chemin absolu : ce test pointait en dur vers un dossier
# SynthGraph_V4.4, donc il validait le code d'une ANCIENNE version des que
# celle-ci existait sur la machine.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from synthgraph.pipeline.runner import (
    _candidate_table_rows, _reanchor_values_on_table_rows)

ok = fail = 0
def check(label, cond, detail=""):
    global ok, fail
    if cond: ok += 1; print(f"  PASS  {label}")
    else:    fail += 1; print(f"  FAIL  {label}  {detail}")

# Extrait REEL du texte opendataloader du papier 1
SRC = """
Table 1. Synthesis conditions for Sr2IrO4 crystals with fixed molar ratio.
- Sr214#1 1 : 2 : 7 1300 C -> (8 C/h) 900 C -> RT
- Sr214#2 1 : 2 : 7 1100 C -> (45 C/h) 1300 C -> (8 C/h) 900 C -> RT
- Sr214#3 1 : 2 : 7 1300 C (24h dwell) -> (8 C/h) 1100 C -> Quench
- Sr214/Sr327#1 1 : 2 : 7 1150 C (12 h dwell) -> (5 C/h) 880 C -> RT
- Sr327 2 : 3 : 7 1050 C (36 h dwell) -> (5 C/h) 750 C -> RT
The crucibles were heated in a programmable box furnace in air then cooled to room temperature.
"""

print("=== detection des lignes de tableau ===")
rows = _candidate_table_rows(SRC)
check(f"5 lignes de tableau detectees (got {len(rows)})", len(rows) == 5,
      f"rows={[r[:40] for r in rows]}")
check("la phrase de texte courant n'est PAS prise pour un tableau",
      not any("crucibles" in r for r in rows))

def run(steps):
    ex = {"pathways": [{"synthesis_steps": steps}]}
    _reanchor_values_on_table_rows(ex, SRC)
    return ex["pathways"][0]

print("\n=== cas 1 : valeur UNIQUE -> re-ancrage ===")
# 1150 n'apparait que dans la ligne Sr214/Sr327#1
pw = run([{"order": 1, "type": "heating", "target_temperature_c": 1150,
           "citation": "The crucibles were heated in a programmable box furnace in air"}])
st = pw["synthesis_steps"][0]
check("citation remplacee par la ligne de tableau", "Sr214/Sr327#1" in st["citation"],
      f"cit={st['citation'][:60]}")
check("valeur conservee", st["target_temperature_c"] == 1150)
check("origine tracee", st.get("citation_source") == "table_row_reanchor")

print("\n=== cas 2 : valeur AMBIGUE -> conservee, non re-ancree ===")
# 1300 apparait dans 3 lignes
pw = run([{"order": 1, "type": "heating", "target_temperature_c": 1300,
           "citation": "The crucibles were heated in a programmable box furnace in air"}])
st = pw["synthesis_steps"][0]
check("valeur CONSERVEE (correcte mais ambigue)", st["target_temperature_c"] == 1300)
check("citation NON remplacee", "crucibles" in st["citation"], f"cit={st['citation'][:50]}")
check("marquee ambigue", "target_temperature_c" in (st.get("ambiguous_values") or []))

print("\n=== cas 3 : valeur INTROUVABLE -> purge + trou ===")
pw = run([{"order": 1, "type": "heating", "target_temperature_c": 1234,
           "citation": "The crucibles were heated in a programmable box furnace in air"}])
st = pw["synthesis_steps"][0]
check("valeur purgee", st["target_temperature_c"] is None, f"got={st['target_temperature_c']}")
check("trou declare", any(m["parameter"] == "target_temperature_c"
                          for m in pw.get("missing_parameters", [])))

print("\n=== cas 4 : deja justifiee -> intacte ===")
pw = run([{"order": 1, "type": "heating", "target_temperature_c": 1300,
           "citation": "heated at 1300 C for 24 h"}])
st = pw["synthesis_steps"][0]
check("citation intacte", st["citation"] == "heated at 1300 C for 24 h")
check("non marquee ambigue", not st.get("ambiguous_values"))

print("\n=== cas 5 : la rampe 5 C/h devient citable (debloque A4) ===")
pw = run([{"order": 1, "type": "cooling", "duration_h": 5,
           "citation": "The crucibles were heated in a programmable box furnace in air"}])
st = pw["synthesis_steps"][0]
# 5 apparait dans 2 lignes (Sr214/Sr327#1 et Sr327) -> ambigu, conserve
check("5 traitee sans crash", st.get("duration_h") in (5, None))

print(f"\nTOTAL {ok} PASS / {fail} FAIL")
