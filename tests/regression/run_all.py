#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Lance TOUTES les suites de non-regression et renvoie un code d'echec global.

Ces suites gardent les garde-fous anti-invention du projet : chaque correctif
livre depuis le 19/08 y a son test, et chaque PIEGE rencontre sur donnees
reelles y est verrouille (fuite d'exemple de prompt, negation d'atmosphere,
flacon de stockage pris pour un reacteur, hydrate lu comme un decimal...).

Elles vivaient dans un dossier temporaire de session : un nettoyage les aurait
effacees, laissant le projet sans filet. Rapatriees ici le 20/08.

Usage :
    python tests/regression/run_all.py
    python tests/regression/run_all.py -v      # sortie complete de chaque suite
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ICI = Path(__file__).resolve().parent
VERBEUX = "-v" in sys.argv


def main() -> int:
    suites = sorted(f for f in ICI.glob("test_*.py"))
    if not suites:
        print("aucune suite trouvee")
        return 1

    # Ces suites doivent tourner HORS LIGNE. Un script qui charge un modele
    # n'a rien a faire ici : le 20/08, un diagnostic GPU rapatrie par erreur a
    # lance deux processus de 10 Go qui concurrencaient une mesure en cours.
    interdits = []
    for f in suites:
        t = f.read_text(encoding="utf-8", errors="replace")
        if "llama_cpp" in t or ".gguf" in t:
            interdits.append(f.name)
    if interdits:
        print("REFUS : ces fichiers chargent un modele, ils ne sont pas des "
              "tests hors ligne — deplacez-les vers tools/diagnostics/ :")
        for x in interdits:
            print(f"  - {x}")
        return 1

    total_ok = total_ko = echecs = 0
    for f in suites:
        r = subprocess.run([sys.executable, str(f)], capture_output=True,
                           text=True, encoding="utf-8", errors="replace")
        sortie = (r.stdout or "") + (r.stderr or "")

        # Chercher le bilan DANS TOUTE la sortie, pas sur la derniere ligne :
        # certaines suites terminent par un WARNING de log, et le bilan
        # disparaissait. Pire, une suite pouvait etre comptee verte alors que
        # sa derniere ligne etait une erreur (constate le 20/08).
        import re
        m = None
        for x in reversed(sortie.splitlines()):
            m = re.search(r"(\d+)\s*(?:OK|PASS)\s*/\s*(\d+)\s*(?:ECHECS?|FAIL)", x)
            if m:
                resume = x.strip()
                break
        if m:
            total_ok += int(m.group(1))
            total_ko += int(m.group(2))
            rate = int(m.group(2)) > 0
        else:
            resume = "AUCUN BILAN TROUVE — la suite n'a pas rendu son compte"
            rate = True

        if r.returncode != 0 or rate:
            echecs += 1

        etat = "OK  " if (r.returncode == 0 and not rate) else "ECHEC"
        print(f"  {etat}  {f.name:26s} {resume}")
        if VERBEUX or r.returncode != 0:
            print("        " + "\n        ".join(sortie.strip().splitlines()[-25:]))

    print(f"\n{len(suites)} suites | {total_ok} assertions OK | {total_ko} echecs "
          f"| {echecs} suite(s) en echec")
    return 1 if echecs else 0


if __name__ == "__main__":
    raise SystemExit(main())
