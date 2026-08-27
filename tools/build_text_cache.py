#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Pré-extrait le texte des papiers (opendataloader) et le met en cache.

L'extraction ODL prend 1 à 4 min par papier ; la mettre en cache évite de la
refaire à chaque comparaison au gold et à chaque changement de modèle.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from synthgraph.rag.pdf_parser import parse_pdf_for_vision  # noqa: E402

# (clé, sous-dossier de data/, nom du PDF)
PAPERS = {
    "crystal": ("bench_night", "Crystal growth and intrinsic magnetic behaviour of Sr2IrO4.pdf"),
    "physrev": ("bench_night", "PhysRevB.49.11890.pdf"),
    "prepara": ("bench_night", "the-preparation-of-a-strontium-iridium-oxide-sr2iro41-2 (1).pdf"),
    # extension hors iridates : 5 familles de synthese distinctes
    "hydro_czts":    ("corpus5", "hydro_czts.pdf"),      # hydrothermal
    "solgel_cuo":    ("corpus5", "solgel_cuo.pdf"),      # sol-gel
    "combu_ferrite": ("corpus5", "combu_ferrite.pdf"),   # auto-combustion
    "cbd_mnse":      ("corpus5", "cbd_mnse.pdf"),        # chemical bath deposition
    "reduc_cu":      ("corpus5", "reduc_cu.pdf"),        # reduction chimique
    # Second elargissement : 4 familles encore absentes du corpus, choisies
    # pour n'avoir AUCUN point commun avec les 8 papiers precedents.
    "cvd_mos2":     ("corpus9", "cvd_mos2.pdf"),        # CVD, phase gazeuse
    "electro_nico": ("corpus9", "electro_nico.pdf"),    # electrodeposition
    "broyage_na":   ("corpus9", "broyage_na.pdf"),      # broyage a billes
    "selfondu_cosi": ("corpus9", "selfondu_cosi.pdf"),  # sels fondus
}

for key, (sub, name) in PAPERS.items():
    out = ROOT / "logs" / f"odl_{key}.txt"
    if out.exists() and out.stat().st_size > 1000:
        print(f"{key:10s} deja en cache ({out.stat().st_size} car.)", flush=True)
        continue
    pdf = ROOT / "data" / sub / name
    if not pdf.exists():
        print(f"{key:10s} PDF INTROUVABLE : {name}", flush=True)
        continue
    try:
        txt = parse_pdf_for_vision(str(pdf), str(ROOT / "logs" / "img_tmp"))
        out.write_text(txt, encoding="utf-8")
        print(f"{key:10s} extrait : {len(txt)} car.", flush=True)
    except Exception as e:  # noqa: BLE001
        print(f"{key:10s} ECHEC : {type(e).__name__}: {e}", flush=True)
