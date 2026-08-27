"""
synthgraph/cli.py — Point d'entrée unique de SynthGraph V4.4.

Fusionne l'ancien `run_pipeline.py` (corps du pipeline) et `main.py`
(métadonnées PDF, ingestion Bible, option Neo4j, logging VRAM, journal).

Usage : python run.py --input data/paper.pdf [--neo4j]
"""

from __future__ import annotations

import sys
import logging
import argparse
from pathlib import Path
from datetime import datetime

# Emojis / accents sous Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


def parse_args(argv=None):
    p = argparse.ArgumentParser(
        description="SynthGraph — Pipeline multi-agents d'extraction de voies de synthèse inorganique",
    )
    p.add_argument("--input", "-i", default="data/sample_paper.pdf",
                   help="Chemin vers un PDF, ou un dossier de PDF (traités en boucle)")
    p.add_argument("--provider", choices=["ollama", "llama-server"], default="llama-server",
                   help="Backend LLM (inférence in-process via llama-cpp-python quel que soit le choix)")
    p.add_argument("--use-marker", action="store_true", help="Utiliser Marker-pdf pour la lecture")
    p.add_argument("--neo4j", action="store_true", help="Injecter le Cypher généré dans Neo4j")
    p.add_argument("--no-debate", action="store_true",
                   help="Sauter la couche QA (débat Thermo/Contextuel + Red Team). "
                        "Le graphe déterministe est identique ; ~5x plus rapide pour construire la BDD.")
    p.add_argument("--debug-text", action="store_true",
                   help="Sauvegarder le texte focalisé dans logs/debug_focused_<route>.txt")
    p.add_argument("--title",   default="Unknown Title")
    p.add_argument("--authors", default="Unknown Authors")
    p.add_argument("--year",    type=int, default=2024)
    p.add_argument("--doi",     default="N/A")
    p.add_argument("--journal", default="N/A")
    return p.parse_args(argv)


def setup_logging():
    Path("logs").mkdir(exist_ok=True)
    log_path = f"logs/run_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(log_path, encoding="utf-8", mode="w"),
        ],
    )
    return logging.getLogger("SynthGraph.CLI")


def main(argv=None):
    args = parse_args(argv)
    logger = setup_logging()

    if not Path(args.input).exists():
        logger.error(f"Fichier/dossier introuvable : {args.input}")
        logger.error("Générez un PDF de test avec : python data/generate_sample_paper.py")
        sys.exit(1)

    logger.info("=" * 70)
    logger.info("🧪 SynthGraph V4.4 — Système Multi-Agents pour Synthèse Inorganique")
    logger.info("=" * 70)
    logger.info(f"Entrée : {args.input} | Provider : {args.provider} | Neo4j : {args.neo4j}")

    # Import APRÈS setup_logging pour que le runner hérite des handlers configurés
    from synthgraph.pipeline.runner import run_pipeline
    run_pipeline(args)

    logger.info("✅ Pipeline terminé. Livrables : logs/cypher_output_*.cypher, logs/pipeline_result_*.json")


if __name__ == "__main__":
    main()
