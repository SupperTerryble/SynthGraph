"""Tests de la boucle agentique avec un LLM SIMULE (aucun GPU).
On valide les garde-fous : outil inconnu, boucle, plafond, cloture forcee."""
import json
import pathlib
import sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from synthgraph.agents.extractor_toolcalling import extract_with_tools

ok = fail = 0
def check(label, cond, detail=""):
    global ok, fail
    if cond: ok += 1; print(f"  PASS  {label}")
    else:    fail += 1; print(f"  FAIL  {label}  {detail}")

SRC = """Powders of IrO2, SrCO3, and SrCl2 6H2O were thoroughly mixed in a molar ratio
of 1 : 2 : 7 and placed in a platinum crucible covered with a lid.
- Sr214#1 1 : 2 : 7 1300 C -> (8 C/h) 900 C -> RT"""

def call(name, **args):
    return {"id": f"c{abs(hash(name+str(args)))%9999}", "type": "function",
            "function": {"name": name, "arguments": json.dumps(args, ensure_ascii=False)}}

class FakeLLM:
    """Rejoue une sequence d'appels predefinie."""
    def __init__(self, script): self.script = list(script); self.n = 0
    def create_chat_completion(self, **kw):
        self.n += 1
        calls = self.script.pop(0) if self.script else []
        return {"choices": [{"message": {"content": "", "tool_calls": calls}}]}

CIT_PREC = "Powders of IrO2, SrCO3, and SrCl2 6H2O were thoroughly mixed in a molar ratio"
CIT_ROW = "- Sr214#1 1 : 2 : 7 1300 C -> (8 C/h) 900 C -> RT"

print("=== parcours nominal ===")
llm = FakeLLM([
    [call("add_precursor", formula="IrO2", citation=CIT_PREC)],
    [call("add_precursor", formula="SrCO3", citation=CIT_PREC)],
    [call("add_operation", step_type="heating", citation=CIT_ROW, temperature_c=1300)],
    [call("finalize_route", target="Sr2IrO4", sample_id="Sr214#1")],
])
r = extract_with_tools(llm, SRC, "Sr2IrO4", "flux")
s = r["tool_stats"]
check("finalise", s["finalized"], s)
check("4 appels acceptes", s["accepted"] == 4, s)
check("0 refus", s["refused"] == 0, s)
check("arret des finalize", s["stop_reason"] == "finalized", s)
check("pathway produit", len(r["pathways"]) == 1)
check("variant_id = echantillon", r["pathways"][0]["variant_id"] == "Sr214#1")

print("\n=== outil halluciné ===")
llm = FakeLLM([
    [call("add_temperature_step", value=1300)],          # n'existe pas
    [call("add_precursor", formula="IrO2", citation=CIT_PREC)],
    [call("add_operation", step_type="heating", citation=CIT_ROW, temperature_c=1300)],
    [call("finalize_route")],
])
r = extract_with_tools(llm, SRC, "Sr2IrO4", "flux")
s = r["tool_stats"]
check("outil inconnu compte", s["unknown_tool"] == 1, s)
check("la boucle continue malgre tout", s["finalized"], s)

print("\n=== boucle infinie ===")
llm = FakeLLM([[call("add_precursor", formula="XX", citation=CIT_PREC)] for _ in range(12)])
r = extract_with_tools(llm, SRC, "Sr2IrO4", "flux")
s = r["tool_stats"]
check("boucle detectee", s["loop_breaks"] >= 1, s)
check("arret pour boucle", s["stop_reason"] == "loop_detected", s)
check("pas de tour infini", s["turns"] <= 6, s)

print("\n=== oubli de finalize -> cloture auto ===")
llm = FakeLLM([
    [call("add_precursor", formula="IrO2", citation=CIT_PREC)],
    [call("add_operation", step_type="heating", citation=CIT_ROW, temperature_c=1300)],
    [],   # le modele arrete d'appeler des outils
])
r = extract_with_tools(llm, SRC, "Sr2IrO4", "flux")
s = r["tool_stats"]
check("cloture automatique", s["stop_reason"] == "no_tool_call_autofinalize", s)
check("donnees conservees", len(r["pathways"]) == 1 and r["pathways"][0]["precursors"])

print("\n=== plafond de tours ===")
llm = FakeLLM([[call("add_precursor", formula=f"F{i}", citation=CIT_PREC)] for i in range(40)])
r = extract_with_tools(llm, SRC, "Sr2IrO4", "flux", max_turns=5)
s = r["tool_stats"]
check("plafond respecte", s["turns"] <= 5, s)

print("\n=== refus -> correction au tour suivant ===")
llm = FakeLLM([
    [call("add_operation", step_type="heating",
          citation="The crucibles were heated in a programmable box furnace",  # ne prouve pas 1300
          temperature_c=1300)],
    [call("add_precursor", formula="IrO2", citation=CIT_PREC)],
    [call("add_operation", step_type="heating", citation=CIT_ROW, temperature_c=1300)],
    [call("finalize_route")],
])
r = extract_with_tools(llm, SRC, "Sr2IrO4", "flux")
s = r["tool_stats"]
check("1 refus enregistre", s["refused"] == 1, s)
check("puis acceptation", s["accepted"] == 3, s)
# 2 entrees : la citation tentee (diagnostic) + le message de refus
check("rejet trace", len(r["rejections"]) >= 1, r["rejections"])

print("\n=== inference qui plante ===")
class BoomLLM:
    def create_chat_completion(self, **kw): raise RuntimeError("CUDA error")
r = extract_with_tools(BoomLLM(), SRC, "Sr2IrO4", "flux")
check("erreur capturee sans crash", r["tool_stats"]["stop_reason"].startswith("inference_error"))
check("sortie exploitable", "pathways" in r)

print(f"\nTOTAL {ok} PASS / {fail} FAIL")
