#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
synthgraph/extraction/sample_detect.py — SynthGraph V5 (tool-calling)

Détection DÉTERMINISTE des échantillons décrits par un papier.

Pourquoi : le papier « Crystal growth » décrit DIX expériences (Sr214#1 à #4,
Sr214−δ#1-2, Sr214/Sr327#1-3, Sr327) qui donnent des phases différentes —
Sr2IrO4 stœchiométrique, Sr2IrO4−δ lacunaire, Sr3Ir2O7. Le single-shot n'en
restituait qu'une : neuf expériences perdues, et cinq températures du gold
introuvables (750, 880, 1050, 1125, 1150 °C).

Plutôt que d'espérer qu'un LLM enchaîne quarante tours d'outils sans dériver
(la note d'audit le donne instable dès 6-7 tours), on repère les échantillons
par le code, puis on lance UNE boucle agentique COURTE par échantillon.

Aucune invention : un échantillon n'est retenu que s'il porte un identifiant
écrit dans le texte ET une ligne décrivant des conditions.
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger("SynthGraph.SampleDetect")

# Identifiant d'échantillon tel qu'on les rencontre dans les tableaux :
#   Sr214#1 · Sr214−δ#2 · Sr214/Sr327#1 · Sr327 · S1 · sample A
# On exige un ancrage en début de ligne pour éviter de capter une référence
# bibliographique ou une formule au fil du texte.
_SAMPLE_ID = re.compile(
    r"^[-•*\s]*("
    r"[A-Z][A-Za-z0-9]*(?:[−\-–/][A-Za-zδ0-9]+)*#\d+"   # Sr214#1, Sr214/Sr327#1, Sr214−δ#2
    r"|[A-Z][a-z]?\d{2,}"                                # Sr327, S214
    r"|(?:sample|echantillon|échantillon)\s+[A-Za-z0-9#-]+"
    r")\b",
    re.IGNORECASE,
)

# Une ligne n'est retenue que si elle décrit VRAIMENT des conditions.
_HAS_CONDITIONS = re.compile(
    r"(\d\s*[°◦˚]?\s*c\b)|(\d\s*:\s*\d)|(→|->)|(\d\s*h\b)", re.IGNORECASE)

_MIN_LINE = 18
_MAX_LINE = 400


# Identifiant apparaissant EN MILIEU de ligne : l'extraction PDF colle parfois
# deux lignes de tableau bout à bout. Constaté sur « Crystal growth » :
#   « …Sr214/Sr327#3 1 : 2 : 7 1050°C … → RT Sr327 2 : 3 : 7 1050 °C … → 750 °C »
# soit DEUX échantillons sur une ligne — le second (Sr327) n'était jamais
# détecté, et sa température de 750 °C restait introuvable dans toutes les
# mesures. On scinde donc au second identifiant.
_INLINE_ID = re.compile(
    r"\s(?=(?:[A-Z][A-Za-z0-9]*(?:[−\-–/][A-Za-zδ0-9]+)*#\d+|[A-Z][a-z]?\d{3,})\s+\d+\s*:\s*\d)")


def _split_glued_rows(line: str) -> list[str]:
    """Scinde une ligne portant plusieurs échantillons collés."""
    parts, last = [], 0
    for m in _INLINE_ID.finditer(line):
        if m.start() > last + _MIN_LINE:
            parts.append(line[last:m.start()].strip())
            last = m.start()
    parts.append(line[last:].strip())
    return [p for p in parts if len(p) >= _MIN_LINE]


def detect_samples(text: str, max_samples: int = 20) -> list[dict]:
    """Repère les échantillons décrits par des lignes de conditions.

    Returns:
        Liste de {"sample_id", "line"}, dans l'ordre d'apparition, sans doublon.
    """
    found: dict[str, str] = {}
    for raw in (text or "").splitlines():
        base = raw.strip()
        if not (_MIN_LINE <= len(base) <= _MAX_LINE):
            continue
        if not _HAS_CONDITIONS.search(base):
            continue
        for line in _split_glued_rows(base):
            m = _SAMPLE_ID.match(line)
            if not m:
                continue
            sid = m.group(1).strip()
            # Un identifiant purement numérique ou trop court n'est pas fiable.
            if len(sid) < 3 or sid.isdigit():
                continue
            if sid not in found:
                found[sid] = line
        if len(found) >= max_samples:
            break

    samples = [{"sample_id": k, "line": v} for k, v in found.items()]
    if samples:
        logger.info(f"  [samples] {len(samples)} échantillon(s) détecté(s) : "
                    f"{', '.join(s['sample_id'] for s in samples)}")
    else:
        logger.info("  [samples] aucun échantillon identifié — extraction unique")
    return samples


def table_rows_block(text: str, max_rows: int = 30) -> str:
    """Bloc des lignes de conditions, à injecter tel quel dans le contexte.

    Sert de repli si le modèle ne cite pas spontanément les tableaux : les
    lignes lui sont alors présentées isolément, sous un intitulé explicite.
    """
    rows = []
    for raw in (text or "").splitlines():
        line = raw.strip().lstrip("-•*").strip()
        if _MIN_LINE <= len(line) <= _MAX_LINE and _HAS_CONDITIONS.search(line):
            if line not in rows:
                rows.append(line)
        if len(rows) >= max_rows:
            break
    if not rows:
        return ""
    listing = "\n".join(f"  [ligne {i+1}] {r}" for i, r in enumerate(rows))
    return ("\n\nLIGNES DE TABLEAU DISPONIBLES (copie l'une d'elles comme citation "
            "pour toute valeur numérique) :\n" + listing)
