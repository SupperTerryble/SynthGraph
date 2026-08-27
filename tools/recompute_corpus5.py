#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Recalcule les metriques du corpus5 depuis les voies DEJA extraites.

Le comparateur separait temperatures et durees par un seuil de 100, valable
seulement sur les iridates. Le correctif change la MESURE, pas l'extraction :
inutile de refaire tourner le GPU, les voies sont sauvegardees dans
`logs/pathways_Qwen3_<cle>.json`.

Usage :
    python tools/recompute_corpus5.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools.compare_tc_gold import compare  # noqa: E402

GOLD = json.loads((ROOT / "data" / "gold" / "gold_corpus5.json").read_text(encoding="utf-8"))
KEYS = ["hydro_czts", "solgel_cuo", "combu_ferrite", "cbd_mnse", "reduc_cu"]


def main() -> int:
    out = {}
    hdr = f"{'papier':15s} {'precurs':>8s} {'ratios':>8s} {'durees':>8s} {'temp':>8s} {'tracab':>8s}"
    print(hdr)
    print("-" * len(hdr))
    for key in KEYS:
        pw_file = ROOT / "logs" / f"pathways_Qwen3_{key}.json"
        if not pw_file.exists():
            print(f"{key:15s} voies absentes ({pw_file.name})")
            continue
        data = json.loads(pw_file.read_text(encoding="utf-8"))
        cmp = compare(GOLD[key], data.get("pathways", []))
        out[key] = cmp

        def f(v):
            return "n/a" if v is None else f"{v:.1f}%"

        print(f"{key:15s} {f(cmp['precursors_pct']):>8s} {f(cmp['molar_ratios_pct']):>8s} "
              f"{f(cmp['durations_pct']):>8s} {f(cmp['temperatures_pct']):>8s} "
              f"{f(cmp.get('traceability_pct')):>8s}")
        for label, field in (("precurseurs manquants", "precursors_missing"),
                             ("durees manquantes", "durations_missing"),
                             ("temperatures manquantes", "temperatures_missing"),
                             ("ratios FAUX", "ratios_FAUX")):
            v = cmp.get(field)
            if v:
                print(f"                 {label} : {v}")

    (ROOT / "logs" / "tc_vs_gold_corpus5_recompute.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
