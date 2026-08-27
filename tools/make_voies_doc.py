#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tools/make_voies_doc.py — document des VOIES DE SYNTHÈSE extraites

Objet (demande de Terry) : prouver que le modèle a extrait CORRECTEMENT chaque
voie de synthèse. Un chapitre par papier, une partie par voie, et pour chaque
valeur la CITATION qui la prouve — c'est la citation qui fait la démonstration,
pas le chiffre seul.

Chaque voie est confrontée au gold annoté à la main : ce qui concorde, ce qui
manque, ce qui a été déduit par post-traitement déterministe (et depuis quoi).

Usage :
    python tools/make_voies_doc.py                    # markdown
    python tools/make_voies_doc.py --docx             # + conversion Word
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GOLD = json.loads((ROOT / "data" / "gold" / "gold_sr2iro4.json").read_text(encoding="utf-8"))
# Le gold des iridates est indexe par TITRE, celui du corpus5 par cle de papier :
# on fusionne les deux pour n'avoir qu'une table de lookup en aval.
GOLD.update(json.loads(
    (ROOT / "data" / "gold" / "gold_corpus5.json").read_text(encoding="utf-8")))
GOLD.update(json.loads(
    (ROOT / "data" / "gold" / "gold_corpus9.json").read_text(encoding="utf-8")))

PAPERS = [
    ("crystal", "Crystal growth and intrinsic magnetic behaviour of Sr2IrO4",
     "Sung et al., Philosophical Magazine"),
    ("physrev", "PhysRevB.49.11890", "Crawford et al., Phys. Rev. B 49, 11890 (1994)"),
    ("prepara", "the-preparation-of-a-strontium-iridium-oxide-sr2iro41-2 (1)",
     "Randall, Katz & Ward, JACS 79 (1957)"),
    # Extension hors iridates : 5 familles de synthese distinctes, gold annote
    # a la main et verifie contre les textes sources (89 controles, 0 erreur).
    ("hydro_czts", "hydro_czts", "Xia et al., Nanoscale Res. Lett. 9 (2014) — hydrothermale, Cu2ZnSnS4"),
    ("solgel_cuo", "solgel_cuo", "Dorner et al., Sci. Rep. 9 (2019) — sol-gel, CuO poreux"),
    ("combu_ferrite", "combu_ferrite", "Batoo & Ansari, Nanoscale Res. Lett. 7 (2012) — auto-combustion, ferrite Ni-Cu-Zn"),
    ("cbd_mnse", "cbd_mnse", "Kariper, Materials Research (2018) — bain chimique, MnSe"),
    ("reduc_cu", "reduc_cu", "Khan et al., Int. Nano Lett. 6 (2016) — reduction chimique, Cu"),
    # Quatre familles SANS RAPPORT avec l'inorganique haute temperature : chacune
    # a revele des defauts que les huit papiers precedents ne pouvaient pas
    # montrer (schema qui efface la temperature, focalisation qui coupe les
    # conditions, vocabulaire d'atmosphere trop etroit).
    ("cvd_mos2", "cvd_mos2", "Zhu et al., npj 2D Mater. Appl. (2017) — CVD, MoS2"),
    ("electro_nico", "electro_nico", "Xie et al., Appl. Surf. Sci. — electrodeposition en liquide ionique, Ni-Co"),
    ("broyage_na", "broyage_na", "Nature Communications — mecanosynthese, Na3P"),
    ("selfondu_cosi", "selfondu_cosi", "JACS — sels fondus LiI-KI, CoSi"),
]

_SRC_LABEL = {
    "table_header": "déduit de l'en-tête du tableau",
    "enumeration_order": "déduit de l'ordre d'énumération",
    "citation_regex": "déduit de la citation",
    "citation_regex_montee": "déduit de la citation (temps de MONTÉE, pas un palier)",
    "amount_molaire": "déduit des quantités molaires citées",
    "formule_cible": "déduit de la formule cible énoncée",
}


def _fmt(v) -> str:
    if isinstance(v, float):
        return f"{v:g}"
    return str(v)


def _step_params(st: dict) -> list[str]:
    """Paramètres lisibles d'une étape, hors champs de structure."""
    skip = {"type", "operation", "order", "citation", "step_name",
            "_missing_required", "other_parameters", "duration_h_source",
            "atmosphere_citation", "ambiguous_values", "citation_source"}
    out = []
    for k, v in st.items():
        if k in skip or v is None or v == "":
            continue
        out.append(f"`{k}` = **{_fmt(v)}**")
    # Le CONTENANT vit dans `other_parameters` (`vessel_name` n'est mappe nulle
    # part, cf. graph_tools). Or c'est lui qui decide de la faisabilite : un flux
    # de SrCl2 a 1300 °C detruit un creuset d'alumine. Un document cense prouver
    # que la synthese est refaisable ne peut pas l'omettre.
    op = st.get("other_parameters") or {}
    if op.get("vessel_name"):
        out.append(f"`contenant` = **{op['vessel_name']}**")
    return out


def paper_chapter(key: str, gold_name: str, ref: str) -> list[str]:
    p = ROOT / "logs" / f"pathways_Qwen3_{key}.json"
    if not p.exists():
        return [f"\n## {ref}\n\n_Extraction indisponible ({p.name})._\n"]
    data = json.loads(p.read_text(encoding="utf-8"))
    g = GOLD[gold_name]
    pws = data.get("pathways", [])

    L = [f"\n# {ref}", "",
         f"**Matériau visé** : {g.get('target')}  ",
         f"**Méthode** : {g.get('method_type')}  ",
         f"**Voies extraites** : {len(pws)}", ""]

    # --- référence attendue ---
    L += ["## Référence annotée à la main", "",
          "| Précurseur | Ratio molaire | Rôle |", "|---|---|---|"]
    for gp in g["precursors"]:
        L.append(f"| `{gp['formula']}` | {gp.get('molar_ratio', '—')} | {gp.get('role', 'reactant')} |")
    L += ["", f"**Atmosphère** : {g.get('atmosphere')}  "]
    if g.get("vessel"):
        L.append(f"**Contenant** : {g['vessel']}  ")
    if g.get("washing"):
        L.append(f"**Traitement final** : {g['washing']}  ")
    L.append("")

    # --- une partie par voie ---
    for i, pw in enumerate(pws, 1):
        # Un papier sans identifiants d'échantillon hérite parfois de ceux d'un
        # autre (`Sr214#1` sur prepara) : trompeur dans un document censé
        # prouver l'extraction. On ne garde l'identifiant que s'il apparaît
        # vraiment dans CE papier.
        vid = pw.get("variant_id") or ""
        src_txt = (ROOT / "logs" / f"odl_{key}.txt")
        if vid and vid not in (src_txt.read_text(encoding="utf-8") if src_txt.exists() else ""):
            vid = ""
        title = f"{vid}" if vid else f"voie {i} sur {len(pws)}"
        L += [f"## Voie extraite — {title}", ""]

        precs = pw.get("precursors", [])
        if precs:
            L += ["### Précurseurs", "",
                  "| Composé | Ratio | Provenance | Citation qui le prouve |",
                  "|---|---|---|---|"]
            for pr in precs:
                r = pr.get("molar_ratio")
                src = _SRC_LABEL.get(pr.get("ratio_source"), "cité par le modèle" if r is not None else "—")
                cit = (pr.get("citation") or "").replace("|", "/")[:150]
                L.append(f"| `{pr.get('formula')}` | {_fmt(r) if r is not None else '—'} "
                         f"| {src} | {cit} |")
            L.append("")

        steps = pw.get("synthesis_steps", [])
        if steps:
            L += ["### Séquence opératoire", "",
                  "| # | Opération | Paramètres prouvés | Citation |", "|---|---|---|---|"]
            for st in sorted(steps, key=lambda s: s.get("order") or 0):
                params = ", ".join(_step_params(st)) or "_aucun paramètre prouvé_"
                cit = (st.get("citation") or "").replace("|", "/")[:150]
                L.append(f"| {st.get('order', '')} | **{st.get('type', '?')}** | {params} | {cit} |")
            L.append("")

        # --- confrontation au gold, voie par voie ---
        # Comparer les CHAINES declarait « L-cysteine » absente face au
        # `C3H7NO2S` du gold, sur une extraction pourtant complete. On aligne le
        # document sur la composition elementaire, comme le validateur, le
        # comparateur et l'audit — un document de preuve ne peut pas contredire
        # la mesure.
        import sys as _sys
        _sys.path.insert(0, str(ROOT))
        from synthgraph.extraction.graph_tools import _composition_key
        got_forms = {re.sub(r"[^a-z0-9]", "", (pr.get("formula") or "").lower()) for pr in precs}
        got_keys = {k for k in (_composition_key(pr.get("formula") or "") for pr in precs) if k}
        missing = []
        for gp in g["precursors"]:
            f = re.sub(r"[^a-z0-9]", "", gp["formula"].lower())
            core = re.sub(r"[^a-z0-9]", "", gp["formula"].split("·")[0].lower())
            gk = _composition_key(gp["formula"])
            if gk and gk in got_keys:
                continue
            if not any(f == x or (core and (x.startswith(core) or core.startswith(x)))
                       for x in got_forms if x):
                missing.append(gp["formula"])
        verdict = ("Tous les précurseurs de la référence sont présents."
                   if not missing else
                   f"**Manquant(s)** : {', '.join('`'+m+'`' for m in missing)}")
        L += [f"> **Confrontation au gold** — {verdict}", ""]

    return L


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=ROOT / "VOIES_DE_SYNTHESE.md")
    a = ap.parse_args()

    L = ["# Voies de synthèse extraites automatiquement", "",
         "Ce document présente les voies de synthèse extraites des publications par",
         "**Qwen3-8B** en architecture tool-calling, et les confronte au gold annoté",
         "manuellement. Chaque valeur est accompagnée de **la citation qui la prouve** :",
         "c'est cette citation qui démontre l'extraction, non le chiffre seul.",
         "",
         "Aucune valeur ne peut entrer dans le graphe sans une citation du papier qui la",
         "contienne — les valeurs marquées « déduit » proviennent d'un post-traitement",
         "déterministe (en-tête de tableau, ordre d'énumération, citation), jamais d'une",
         "supposition du modèle.", ""]

    for key, gold_name, ref in PAPERS:
        L += paper_chapter(key, gold_name, ref)

    a.out.write_text("\n".join(L), encoding="utf-8")
    print(f"écrit : {a.out} ({len('\n'.join(L))} caractères)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
