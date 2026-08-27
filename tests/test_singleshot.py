#!/usr/bin/env python3
"""Test A/B : extracteur single-shot sur la fenêtre recette de Sr2IrO4 (flux)."""
import sys, time, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
import fitz

PDF = "data/Crystal growth and intrinsic magnetic behaviour of Sr2IrO4.pdf"

def get_text():
    doc = fitz.open(PDF)
    full = "\n".join(p.get_text() for p in doc)
    low = full.lower()
    start = low.find("table 1")
    if start < 0: start = low.find("experimental")
    return full[max(0, start-200):start+5000]

def main():
    from synthgraph.agents.extractor_singleshot import extract_single_shot
    text = get_text()
    print(f"### texte fourni = {len(text)} chars\n")
    t0 = time.time()
    res = extract_single_shot(text, "flux_growth", "Sr2IrO4", route_id="flux_growth")
    dt = time.time() - t0
    print(f"===== SINGLE-SHOT ({dt:.0f}s) =====")
    print("notes:", res.get("extraction_notes"))
    print("confidence:", res.get("confidence"))
    if not res["pathways"]:
        print("ÉCHEC — aucune pathway"); return
    pw = res["pathways"][0]
    print("target:", pw["target_material"])
    print("precursors:")
    for p in pw["precursors"]:
        print("   ", {k: p.get(k) for k in ("name","formula","role","amount","unit")})
    print("\n=== ÉTAPES NORMALISÉES PAR TYPE ===")
    for st in pw["synthesis_steps"]:
        stype = st.pop("type", "?")
        order = st.get("order")
        cols = {k: v for k, v in st.items()
                if k not in ("order", "operation", "step_name", "citation", "details", "other_parameters")}
        print(f"   [{order}] type={stype:14s} {cols}")
        if st.get("other_parameters"):
            print(f"        other_parameters: {st['other_parameters']}")
        if st.get("citation"):
            print(f"        cit: {st['citation'][:70]!r}")
    print("\n=== MISSING_PARAMETERS (requis absents) ===")
    for m in pw.get("missing_parameters", []):
        print("   ", m)
    print("\nnotes:", pw.get("missing_info"))

if __name__ == "__main__":
    main()
