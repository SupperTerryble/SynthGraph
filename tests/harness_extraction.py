#!/usr/bin/env python3
"""
tests/harness_extraction.py — Banc d'essai RAPIDE de l'extracteur (Phase 1 + Phase 2).

Exécute UNIQUEMENT l'AgentExtracteurToolCaller sur la voie flux du papier Sr2IrO4,
sans le reste du pipeline (Stratège, débat, graphe). Permet d'itérer en ~2-3 min.

Usage :
  python tests/harness_extraction.py [full|exp|rag]
    full : texte complet du PDF (comme le pipeline actuel)
    exp  : fenêtre expérimentale focalisée (contient Table 1 + prose recette)
    rag  : top-chunks RAG pertinents (précurseurs/température/four)
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import fitz  # PyMuPDF

PDF = "data/Crystal growth and intrinsic magnetic behaviour of Sr2IrO4.pdf"

# Directive telle que produite par l'Orchestrateur (précurseurs volontairement vides :
# on teste la capacité de l'extracteur à les retrouver dans le texte).
DIRECTIVE = {
    "pathway_id": "flux_growth",
    "target_material": "Sr2IrO4",
    "starting_materials": [],
    "macro_method": "flux_method",
    "mission_summary": "Extraire la recette de synthèse par flux de Sr2IrO4.",
}

# Vérité terrain (pour évaluation manuelle) :
GROUND_TRUTH = {
    "precursors": ["IrO2", "SrCO3", "SrCl2·6H2O (flux)"],
    "molar_ratio": "IrO2:SrCO3:SrCl2 = 1:2:7",
    "crucible": "platinum",
    "atmosphere": "air",
    "programs": ["1300°C →(8°C/h)→ 900°C →RT", "1100→1300→900", "dwell 24h/100h", "quench"],
    "workup": "rinsing residual flux with distilled water",
}


def get_full_text() -> str:
    doc = fitz.open(PDF)
    return "\n".join(p.get_text() for p in doc)


def select_text(mode: str, full: str) -> str:
    if mode == "full":
        return full
    if mode == "exp":
        low = full.lower()
        # Ancre sur la Table 1 (ratios) jusqu'à après la prose expérimentale
        start = low.find("table 1")
        if start < 0:
            start = low.find("experimental")
        start = max(0, start - 200)
        return full[start:start + 5000]
    if mode == "rag":
        from synthgraph.rag.manager import DocumentRAG
        rag = DocumentRAG()
        rag.index_text(full)
        return rag.query(
            "flux method precursors IrO2 SrCO3 SrCl2 molar ratio platinum crucible "
            "furnace temperature dwell cooling rate air synthesis", n_results=6)
    raise SystemExit(f"mode inconnu: {mode}")


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "exp"
    from synthgraph.agents.extractor import AgentExtracteurToolCaller

    full = get_full_text()
    text = select_text(mode, full)
    print(f"### MODE={mode} | texte fourni = {len(text)} chars (PDF total {len(full)})\n")

    agent = AgentExtracteurToolCaller(model="llama-3.1-8b")

    t0 = time.time()
    template = agent.run_phase1(text, directive=DIRECTIVE)
    dt1 = time.time() - t0
    print(f"\n===== PHASE 1  ({dt1:.0f}s, {template.confidence:.2f} conf) =====")
    print(f"méthode : {template.synthesis_method}")
    print(f"étapes  : {len(template.steps)}")
    for s in template.steps:
        print(f"   [{s.order}] {s.step_name}  ({s.step_type})  cit={str(s.citation)[:60]!r}")

    t1 = time.time()
    state = agent.run_phase2(text, template, {}, directive=DIRECTIVE)
    dt2 = time.time() - t1
    print(f"\n===== PHASE 2  ({dt2:.0f}s) =====")
    if isinstance(state, dict):
        print("ABORTED:", state)
        return

    ex = state.to_extraction_dict()
    pw = ex["pathways"][0]
    print(f"target     : {pw['target_material']}")
    print(f"precursors : {[(p['name'], p.get('amount'), p.get('unit'), p.get('role')) for p in pw['precursors']]}")
    print("steps :")
    for st in pw["synthesis_steps"]:
        vals = {k: v for k, v in st.items()
                if not k.endswith("_citation") and k not in ("operation", "step_name")}
        print(f"   - {st.get('step_name')} ({st.get('operation')}): {vals}")

    snap = state.get_state_snapshot()
    n_fields = sum(len(s.fields) for s in state.filled_steps)
    print(f"\n===== METRIQUES =====")
    print(f"temps total    : {dt1 + dt2:.0f}s")
    print(f"complétion     : {snap['completion_percent']}%")
    print(f"précurseurs    : {len(pw['precursors'])}  (attendu ~3)")
    print(f"étapes         : {len(pw['synthesis_steps'])}")
    print(f"champs remplis : {n_fields}")
    print(f"\nVÉRITÉ TERRAIN attendue : {GROUND_TRUTH}")


if __name__ == "__main__":
    main()
