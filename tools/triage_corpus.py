#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tools/triage_corpus.py — SynthGraph V4.7

Tableau de santé d'un run de corpus : agrège les signaux de diagnostic
(pipeline_result_*.json, cypher_output_*.cypher, log de run) en un rapport
par papier + classes d'échec, pour piloter la boucle diagnostic→correctif.

Usage :
    python tools/triage_corpus.py                       # analyse logs/
    python tools/triage_corpus.py --run-log logs/run_corpus.log
    python tools/triage_corpus.py --json                # sortie machine (JSONL)

Sorties :
    logs/corpus_triage.md      rapport lisible (tableau + buckets)
    logs/corpus_triage.jsonl   1 ligne JSON par papier (historisable)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOGS = ROOT / "logs"

# Classes d'échec, de la plus grave à la plus bénigne
BUCKETS = [
    ("CRASH",            "Erreur fatale / traceback pendant le traitement"),
    ("NO_DATA",          "Aucune requête Cypher produite (pas de synthèse trouvée ?)"),
    ("ROUTE_LOST",       "Route entière perdue (extraction vide après rejets) — recette du papier manquante"),
    ("ALL_REJECTED",     "Tous les protocoles REJECT ou QA_FAILED"),
    ("EXTRACTION_LOSSY", "Plus de variantes supprimées que conservées (hallucinations)"),
    ("STOICH_FAIL",      "Au moins un bilan élémentaire ÉCHEC non résolu"),
    ("STOICH_UNKNOWN",   "Bilan INDÉTERMINÉ (précurseurs illisibles/en prose)"),
    ("SLOW",             "Durée > 45 min ou appel LLM > 350 s (critère Terry : qualité > vitesse)"),
    ("GAPS_REQUIRED",    "Trous 'required' dans le graphe (recette incomplète)"),
    ("OK",               "Aucun signal d'alerte"),
]


def _parse_run_log(run_log: Path) -> dict:
    """Extrait par papier : timings, drops anti-hallucination, verdicts stoich,
    rattrapages, erreurs — depuis le log texte du pipeline."""
    per_paper: dict[str, dict] = {}
    current = None
    t_start = None
    if not run_log or not run_log.exists():
        return per_paper

    ts_re = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})")

    def _ts(line):
        m = ts_re.match(line)
        return datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S") if m else None

    for line in run_log.read_text(encoding="utf-8", errors="ignore").splitlines():
        if "Traitement de :" in line:
            name = Path(line.split("Traitement de :", 1)[1].strip()).name
            current = per_paper.setdefault(name, {
                "drops": 0, "stoich": [], "rattrapages": 0, "grind_fix": 0,
                "errors": 0, "max_call_s": 0.0, "duration_min": None,
                "routes_lost": 0,
            })
            t_start = _ts(line)
        if current is None:
            continue
        if "SUPPRIMÉE" in line and "Anti-Hallucination" in line:
            current["drops"] += 1
        if "extraction vide, sautée" in line:
            current["routes_lost"] += 1
        if "Verdict déterministe :" in line:
            v = line.split("Verdict déterministe :", 1)[1].strip().split(" ")[0]
            current["stoich"].append(v)
        if "Rattrapage retenu" in line:
            current["rattrapages"] += 1
        if "broyage(s) intermédiaire(s) inséré(s)" in line or "Fusion séquentielle" in line:
            current["grind_fix"] += 1
        if "Erreur fatale" in line or "Traceback" in line:
            current["errors"] += 1
        m = re.search(r"durée=([\d.]+)s", line)
        if m:
            current["max_call_s"] = max(current["max_call_s"], float(m.group(1)))
        if "Fichier Cypher généré" in line and t_start is not None:
            t_end = _ts(line)
            if t_end:
                current["duration_min"] = round((t_end - t_start).total_seconds() / 60, 1)
    return per_paper


def _parse_cypher(cy: Path) -> dict:
    text = cy.read_text(encoding="utf-8", errors="ignore")
    qa = re.findall(r"qa_status='([^']*)'", text)
    return {
        "protocols": len(re.findall(r"MERGE \(p:SynthesisProtocol", text)),
        "operations": len(re.findall(r"MERGE \(n:Operation", text)),
        "materials": len(re.findall(r"MERGE \(n:Material", text)),
        "gaps_required": len(re.findall(r"severity='required'", text)),
        "gaps_recommended": len(re.findall(r"severity='recommended'", text)),
        "suspect_flags": len(re.findall(r"grounded: false", text)),
        "qa_statuses": sorted(set(qa)),
        "targets": sorted(set(re.findall(r"p\.target='([^']*)'", text))),
    }


def classify(paper: dict) -> str:
    log = paper.get("log", {})
    cy = paper.get("cypher", {})
    res = paper.get("result", {})
    if log.get("errors"):
        return "CRASH"
    if res.get("status") == "NO_DATA" or (cy and cy.get("protocols", 0) == 0):
        return "NO_DATA"
    qa = set(cy.get("qa_statuses", []))
    if qa and qa <= {"REJECT", "QA_FAILED"}:
        return "ALL_REJECTED"
    if log.get("routes_lost", 0) > 0:
        return "ROUTE_LOST"
    stoich = log.get("stoich", [])
    kept = cy.get("protocols", 0)
    if log.get("drops", 0) > max(2, kept):
        return "EXTRACTION_LOSSY"
    if "ÉCHEC" in stoich and not log.get("rattrapages"):
        return "STOICH_FAIL"
    if "INDÉTERMINÉ" in stoich:
        return "STOICH_UNKNOWN"
    if (log.get("duration_min") or 0) > 45 or log.get("max_call_s", 0) > 350:
        return "SLOW"
    if cy.get("gaps_required", 0) > 0:
        return "GAPS_REQUIRED"
    return "OK"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-log", type=Path, default=None,
                    help="Log du run (défaut: le plus récent logs/run_*.log)")
    ap.add_argument("--json", action="store_true", help="Imprime le JSONL sur stdout")
    args = ap.parse_args()

    run_log = args.run_log
    if run_log is None:
        candidates = sorted(LOGS.glob("run_*.log"), key=lambda p: p.stat().st_mtime)
        run_log = candidates[-1] if candidates else None

    log_data = _parse_run_log(run_log) if run_log else {}

    papers = {}
    for rj in LOGS.glob("pipeline_result_*.json"):
        res = json.loads(rj.read_text(encoding="utf-8"))
        name = res.get("paper", rj.stem)
        papers.setdefault(name, {})["result"] = res
    for cy in LOGS.glob("cypher_output_*.cypher"):
        stem = cy.stem.replace("cypher_output_", "")
        match = next((n for n in papers if stem[:30] in n.replace(" ", "_")), None)
        key = match or stem
        papers.setdefault(key, {})["cypher"] = _parse_cypher(cy)
    for name, d in log_data.items():
        match = next((n for n in papers if n == name), None)
        papers.setdefault(match or name, {})["log"] = d

    # Si un run-log est fourni, ne trier QUE les papiers de ce run (les artefacts
    # d'anciens runs — golden set… — restent dans logs/ mais ne polluent pas le tableau)
    if log_data:
        papers = {n: p for n, p in papers.items() if "log" in p}

    rows = []
    for name, p in sorted(papers.items()):
        bucket = classify(p)
        cy = p.get("cypher", {})
        log = p.get("log", {})
        rows.append({
            "paper": name, "bucket": bucket,
            "protocols": cy.get("protocols", 0),
            "targets": cy.get("targets", []),
            "qa": cy.get("qa_statuses", []),
            "drops": log.get("drops", 0),
            "stoich": log.get("stoich", []),
            "rattrapages": log.get("rattrapages", 0),
            "grind_fix": log.get("grind_fix", 0),
            "gaps_req": cy.get("gaps_required", 0),
            "gaps_rec": cy.get("gaps_recommended", 0),
            "suspects": cy.get("suspect_flags", 0),
            "duration_min": log.get("duration_min"),
            "max_call_s": log.get("max_call_s", 0),
            "ts": datetime.now().isoformat(timespec="seconds"),
        })

    # ── Rapport Markdown ──
    md = [f"# Triage corpus — {datetime.now().isoformat(timespec='minutes')}",
          f"Log analysé : `{run_log}`" if run_log else "Log : aucun", ""]
    counts = {}
    for r in rows:
        counts[r["bucket"]] = counts.get(r["bucket"], 0) + 1
    md.append("## Classes d'échec (à corriger dans l'ordre)")
    for b, desc in BUCKETS:
        if counts.get(b):
            md.append(f"- **{b}** ×{counts[b]} — {desc}")
    md.append("\n## Détail par papier\n")
    md.append("| Papier | Classe | Protocoles | Drops | Stoich | Rattrap. | Trous req/rec | Durée |")
    md.append("|---|---|---|---|---|---|---|---|")
    for r in rows:
        md.append(f"| {r['paper'][:45]} | {r['bucket']} | {r['protocols']} | {r['drops']} "
                  f"| {','.join(r['stoich']) or '—'} | {r['rattrapages']}+{r['grind_fix']}g "
                  f"| {r['gaps_req']}/{r['gaps_rec']} | {r['duration_min'] or '?'} min |")

    out_md = LOGS / "corpus_triage.md"
    out_md.write_text("\n".join(md), encoding="utf-8")
    out_jsonl = LOGS / "corpus_triage.jsonl"
    with open(out_jsonl, "a", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    if args.json:
        for r in rows:
            print(json.dumps(r, ensure_ascii=False))
    else:
        print("\n".join(md))
    print(f"\n→ {out_md}\n→ {out_jsonl} (historique cumulatif)", file=sys.stderr)


if __name__ == "__main__":
    main()
