"""Qwen3 echoue-t-il a cause de son mode <think> ?

Trois configurations comparees sur le MEME appel :
  A. chat_format='chatml-function-calling'  (ce qu'on faisait -> echec)
  B. template NATIF du modele (il gere tool_call nativement)
  C. natif + '/no_think' (desactive le raisonnement)

On regarde : un tool_call est-il emis, et le contenu contient-il <think> ?
"""
import json
import os
import sys
from pathlib import Path

from llama_cpp import Llama

MODEL = sys.argv[1] if len(sys.argv) > 1 else str(
    Path(os.environ.get("MODELS_DIR", "models")) / "Qwen3-8B-Q4_K_M.gguf")

TOOLS = [{
    "type": "function",
    "function": {
        "name": "add_precursor",
        "description": "Enregistre un precurseur de la synthese.",
        "parameters": {
            "type": "object",
            "properties": {
                "formula": {"type": "string"},
                "citation": {"type": "string"},
            },
            "required": ["formula", "citation"],
        },
    },
}]

TEXT = ("Powders of IrO2, SrCO3, and SrCl2 6H2O were thoroughly mixed in a molar "
        "ratio of 1 : 2 : 7 and placed in a platinum crucible.")

def run(label, chat_format, no_think):
    print("=" * 70)
    print(f"### {label}")
    print("=" * 70)
    kw = {"model_path": MODEL, "n_ctx": 4096, "n_gpu_layers": -1, "verbose": False}
    if chat_format:
        kw["chat_format"] = chat_format
    try:
        llm = Llama(**kw)
    except Exception as e:
        print(f"  chargement KO : {type(e).__name__}: {e}"); return

    sysmsg = "Tu extrais des protocoles. Utilise les outils fournis."
    if no_think:
        sysmsg += " /no_think"
    msgs = [{"role": "system", "content": sysmsg},
            {"role": "user", "content": f"Texte:\n{TEXT}\n\nEnregistre le premier precurseur."}]
    try:
        r = llm.create_chat_completion(messages=msgs, tools=TOOLS,
                                       tool_choice="auto", temperature=0.0,
                                       max_tokens=768)
    except Exception as e:
        print(f"  inference KO : {type(e).__name__}: {str(e)[:150]}"); del llm; return

    m = r["choices"][0]["message"]
    tc = m.get("tool_calls")
    content = m.get("content") or ""
    print(f"  tool_calls emis : {bool(tc)}")
    print(f"  <think> dans le contenu : {'<think>' in content}")
    if tc:
        for c in tc:
            fn = c.get("function", {})
            print(f"    nom={fn.get('name')!r}")
            print(f"    args={str(fn.get('arguments'))[:170]}")
    else:
        print(f"    contenu brut : {content[:300]!r}")
    del llm

run("A. chatml-function-calling (config actuelle)", "chatml-function-calling", False)
run("B. template NATIF du modele", None, False)
run("C. natif + /no_think", None, True)
