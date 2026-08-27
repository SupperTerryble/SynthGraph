#!/usr/bin/env python3
"""
run.py — Point d'entrée racine de SynthGraph V4.4.

Usage :
  python run.py --input data/paper.pdf
  python run.py --input data/ --neo4j --use-nougat
"""

import sys
from pathlib import Path

# Rendre le package `synthgraph` importable quel que soit le CWD
sys.path.insert(0, str(Path(__file__).resolve().parent))

from synthgraph.cli import main

if __name__ == "__main__":
    main()
