#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Quels PARAMÈTRES le corpus porte-t-il, que le schéma ne sait pas recevoir ?

Décision de Terry (20/08) sur les paramètres propres à chaque papier : ne PAS
prédéfinir la liste par opération — on devinerait ce qu'on ne connaît pas — mais
laisser le corpus dicter le vocabulaire.

Cet outil est la PREMIÈRE étape, celle qui ne risque rien : avant d'ouvrir un
champ libre dans l'interface du modèle (donc avant tout changement de schéma,
avec le risque de déplacement d'attention déjà mesuré), on regarde ce que les
papiers énoncent réellement.

Il cherche dans les textes sources les motifs « valeur + unité » et les
tournures « paramètre = valeur », puis écarte tout ce que le schéma capte déjà.
Ce qui reste, trié par fréquence et par nombre de papiers, est la file d'attente
de promotion vers le schéma — arbitrée par Terry, pas par l'outil.

Usage :
    python tools/vocabulaire_parametres.py
    python tools/vocabulaire_parametres.py --min-papiers 2
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Unités rencontrées en synthèse inorganique, groupées par grandeur. La valeur
# est la grandeur telle qu'un chimiste la nommerait, pas le nom de colonne.
_UNITES = [
    (r"\bpH\s*(?:=|of|de)?\s*\d+(?:[.,]\d+)?", "pH"),
    (r"\d+(?:[.,]\d+)?\s*rpm\b", "vitesse d'agitation (rpm)"),
    (r"\d+(?:[.,]\d+)?\s*(?:MPa|GPa|bar|atm|Torr|psi)\b", "pression"),
    (r"\d+(?:[.,]\d+)?\s*(?:mL|ml)\s*/\s*min\b", "débit (mL/min)"),
    (r"\d+(?:[.,]\d+)?\s*(?:sccm|L/min)\b", "débit gazeux"),
    (r"\d+(?:[.,]\d+)?\s*(?:M|mM|µM|N)\b(?![a-zA-Z])", "concentration molaire"),
    (r"\d+(?:[.,]\d+)?\s*(?:wt|at)\.?\s*%", "fraction massique/atomique"),
    (r"\d+(?:[.,]\d+)?\s*(?:kV|mA|V\b|W\b)", "paramètre électrique"),
    (r"\d+(?:[.,]\d+)?\s*(?:kHz|MHz|Hz)\b", "fréquence"),
    (r"\d+(?:[.,]\d+)?\s*(?:nm|µm|um|mm)\b", "dimension"),
    (r"\d+(?:[.,]\d+)?\s*(?:g|mg|kg)\b(?![a-zA-Z/])", "masse"),
    (r"\bfill(?:ing)?\s+(?:factor|degree)\b[^.]{0,20}\d+", "taux de remplissage"),
]

# Ce que le schéma capte déjà : inutile de le proposer à la promotion.
_DEJA_AU_SCHEMA = {
    "température", "durée", "vitesse de chauffe", "vitesse de refroidissement",
    "atmosphère", "contenant", "solvant", "répétitions", "rapport molaire",
}

# Sections de CARACTÉRISATION : un « 40 kV » de diffractomètre n'est pas un
# paramètre de synthèse. Même exclusion que dans les récupérations du pipeline.
_CARACTERISATION = re.compile(
    r"\b(XRD|SEM|FESEM|TEM|HRTEM|DLS|BET|FTIR|Raman|EDX|EDS|XPS|TGA|DSC|"
    r"diffract\w*|spectro\w*|microscop\w*|isotherm|adsorption|scan(?:ning)?\s+rate|"
    r"radiation|wavelength|detector|calibrat\w*)\b", re.I)


def phrases(texte: str) -> list[str]:
    return [p.strip() for p in re.split(r"(?<=[.;])\s+", texte) if p.strip()]


def analyser(cle: str, texte: str) -> dict[str, list[str]]:
    """Grandeurs présentes dans les phrases de SYNTHÈSE, avec un exemple."""
    trouve: dict[str, list[str]] = defaultdict(list)
    for ph in phrases(texte):
        if not (20 < len(ph) < 400) or _CARACTERISATION.search(ph):
            continue
        for motif, grandeur in _UNITES:
            m = re.search(motif, ph)
            if m and grandeur not in _DEJA_AU_SCHEMA:
                trouve[grandeur].append(" ".join(m.group(0).split()))
    return trouve


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-papiers", type=int, default=1,
                    help="ne montrer que les grandeurs vues dans au moins N papiers")
    a = ap.parse_args()

    sources = sorted((ROOT / "logs").glob("odl_*.txt"))
    if not sources:
        print("aucun texte source en cache (logs/odl_*.txt)")
        return 1

    par_grandeur: dict[str, Counter] = defaultdict(Counter)
    exemples: dict[str, str] = {}
    for f in sources:
        cle = f.stem.replace("odl_", "")
        for grandeur, occurrences in analyser(cle, f.read_text(encoding="utf-8")).items():
            par_grandeur[grandeur][cle] += len(occurrences)
            exemples.setdefault(grandeur, occurrences[0])

    classement = sorted(par_grandeur.items(),
                        key=lambda kv: (len(kv[1]), sum(kv[1].values())),
                        reverse=True)

    print(f"{len(sources)} papiers analysés\n")
    print(f"{'grandeur':30s} {'papiers':>8s} {'occur.':>7s}   exemple")
    print("-" * 92)
    retenues = 0
    for grandeur, compte in classement:
        if len(compte) < a.min_papiers:
            continue
        retenues += 1
        print(f"{grandeur:30s} {len(compte):>8d} {sum(compte.values()):>7d}   "
              f"« {exemples[grandeur][:34]} »")
        print(f"{'':30s} {'':>8s} {'':>7s}   {', '.join(sorted(compte))}")

    if not retenues:
        print("(aucune grandeur hors schéma au seuil demandé)")
    print(f"\nCes grandeurs ne sont PAS captées aujourd'hui. Promouvoir au schéma\n"
          f"celles qui reviennent sur plusieurs papiers ; ignorer le reste.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
