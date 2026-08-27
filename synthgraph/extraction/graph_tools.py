#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
synthgraph/extraction/graph_tools.py — SynthGraph V5 (tool-calling)

Outils de CONSTRUCTION INCRÉMENTALE d'une voie de synthèse.

Pourquoi cette architecture (mandat Terry, 2026-08-17) : en single-shot, le
modèle produit d'un bloc une recette dont les valeurs numériques sont souvent
détachées de leur preuve — mesuré sur le corpus, 22,6 % seulement des valeurs
figurent dans la citation censée les justifier. Ici chaque valeur entre dans le
graphe PAR UN APPEL D'OUTIL qui la refuse si sa citation ne la contient pas :
la preuve est exigée à l'insertion, plus vérifiée après coup.

Le retour d'erreur est la pièce maîtresse — il est rédigé pour être ACTIONNABLE
par le modèle au tour suivant (« ta citation ne contient pas 1300 ; copie la
ligne du tableau où figure cette valeur »), ce que le single-shot ne permet pas.

Granularité retenue : UNE OPÉRATION COMPLÈTE PAR APPEL (~10-14 tours/papier).
Plus fin (un paramètre par appel) ferait dériver un 8B au-delà de 6-7 tours,
d'après la note d'audit `tool_calling_architecture_analysis.md`.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any, Optional

logger = logging.getLogger("SynthGraph.GraphTools")

# Repli des confusables OCR — POUR LES MOTS uniquement (formules, noms).
# Ne JAMAIS l'appliquer à des nombres : « 1150 » deviendrait « llso ».
_OCR_CONFUSABLES = str.maketrans("01", "ol")

# Ligatures typographiques : les PDF scientifiques écrivent « ﬂux », « conﬁrmé »,
# « puriﬁé » avec UN SEUL caractère (U+FB01/FB02…). Sans décomposition, la
# normalisation les supprime comme non-alphanumériques et « residual flux »
# devient introuvable dans un texte qui le contient pourtant.
_LIGATURES = {ord(k): v for k, v in {
    "ﬀ": "ff", "ﬁ": "fi", "ﬂ": "fl", "ﬃ": "ffi", "ﬄ": "ffl", "ﬅ": "ft", "ﬆ": "st",
    "œ": "oe", "æ": "ae", "Œ": "OE", "Æ": "AE",
}.items()}

_MIN_CITATION_LEN = 15


def _norm_words(s: str) -> str:
    """Normalise un texte pour comparer des MOTS et des CHIFFRES.

    Les PDF scientifiques emploient des symboles que le modèle re-normalise en
    citant : « 1300◦C » vs « 1300 °C », « SrCl2 · 6H2O » vs « SrCl2 6H2O »,
    tirets longs, espaces insécables. Comparer littéralement rejette alors des
    citations pourtant fidèles — constaté au test de faisabilité : 8 refus sur 8.
    On réduit donc au squelette alphanumérique : la citation reste vérifiable
    sur ses mots et ses nombres, mais la ponctuation ne fait plus échouer.
    """
    s = (s or "").translate(_LIGATURES).lower().translate(_OCR_CONFUSABLES)
    # Césure typographique : les articles anciens coupent les mots en fin de
    # ligne (« by the reac-\n\ntion between iridium metal powder »). Sans
    # recollage, la source contient « reac tion » quand le modèle cite
    # « reaction » — aucune citation ne peut alors correspondre, ce qui
    # bloquait TOUTES les extractions du papier de 1957.
    # Appliqué des deux côtés : la normalisation reste symétrique.
    s = re.sub(r"-\s+", "", s)
    s = re.sub(r"[^a-z0-9]+", " ", s)   # tout symbole devient un séparateur
    return re.sub(r"\s+", " ", s).strip()


# FAMILLES D'UNITES, baties sur les ECRITURES REELLES du corpus. Le degre y est
# ecrit de six facons selon l'OCR : « 1300◦C » (anneau), « 900'C » (apostrophe),
# « 1200° » (sans le C), « 180 ℃ » (caractere unique), « 50 ºC » (ordinal) et
# « 900 C » (degre perdu). Un motif trop etroit refuserait des extractions
# JUSTES — mesure faite AVANT d'ecrire : 60 des 74 valeurs du corpus portaient
# deja une unite compatible, les 14 autres relevaient de ces ecritures.
_FAMILLES_UNITE = {
    "temperature": r"(?:\s*(?:°|˚|◦|º|')?\s*[CK]\b|\s*℃|\s*°(?![a-zA-Z]))",
    "temps": r"\s*(?:h|hr|hrs|hours?|heures?|min|mins|minutes?|s|sec|seconds?)\b",
    "rotation": r"\s*(?:rpm|tr\s*/\s*min)\b",
    "frequence": r"\s*k?Hz\b",
    "tension": r"\s*m?V\b",
    "courant": r"\s*m?A\b",
    "pression": r"\s*(?:MPa|kPa|Pa|bar|mbar|torr)\b",
    "concentration": r"\s*(?:m?M\b|mol\s*/\s*L)",
    "debit": r"\s*sccm\b",
    "puissance": r"\s*m?W\b",
}
# L'unite DECLAREE PAR LE REGISTRE decide de la famille : source unique, comme
# pour la couverture du grounding. Les grandeurs sans dimension (`count`, `%`)
# et les VITESSES (`°C/h`, verifiees par leur NOTATION et non par leur valeur)
# ne sont pas controlees.
_UNITE_VERS_FAMILLE = {
    "°C": "temperature", "h": "temps", "min": "temps", "s": "temps",
    "rpm": "rotation", "Hz": "frequence", "kHz": "frequence", "V": "tension",
    "mA": "courant", "MPa": "pression", "torr": "pression",
    "mol/L": "concentration", "sccm": "debit", "W": "puissance",
}
try:
    from synthgraph.schemas.step_schema import STEP_PARAMETERS as _SP
    _COLONNE_FAMILLE = {}
    for _d in _SP.values():
        for _bloc in ("required", "optional"):
            for _c, _u in (_d.get(_bloc) or {}).items():
                _f = _UNITE_VERS_FAMILLE.get(_u or "")
                if _f:
                    _COLONNE_FAMILLE.setdefault(_c, _f)
    _COLONNE_FAMILLE.setdefault("target_temperature_c", "temperature")
    _COLONNE_FAMILLE.setdefault("concentration_mol_l", "concentration")
except Exception:  # noqa: BLE001 — une extraction ne tombe pas pour si peu
    _COLONNE_FAMILLE = {}


def _num_in(value: float, text: str, colonne: str = None) -> bool:
    """La valeur numérique apparaît-elle littéralement dans le texte ?
    Bornes strictes pour éviter que 6 matche dans 16."""
    forms = {f"{value:g}"}
    if value == int(value):
        forms.add(str(int(value)))
    # UNITE. Sans ce controle, « 20 Hz » prouvait `temperature_c=20`, « 23 mm »
    # (diametre d'une bille) prouvait 23 °C et « 62.3 g » prouvait 62,3 °C. Le
    # run du 21/08 a REELLEMENT pose « 20 °C » sur un broyage a partir de
    # « 20 Hz » : une valeur fabriquee franchissait la regle d'or.
    # Repli OUVERT : une colonne dont le registre ne declare pas d'unite connue
    # garde le comportement d'origine — durcir sans mesure casse des
    # extractions justes.
    famille = _COLONNE_FAMILLE.get(colonne or "")
    # CONVERSION. La citation dit « in 40 min », le modele declare 0.6667 h — la
    # valeur EXACTE — et le garde-fou la refusait parce que « 0.6667 » n'est pas
    # ecrit. Une ligne plus bas, `_DUREE_RE` lit « 40 min » et ecrit 0.6667 : le
    # pipeline refusait au modele ce qu'il calcule lui-meme. Un modele qui fait
    # bien le travail etait puni, un modele qui laisse le champ vide etait
    # rattrape. 9 refus de ce type sur 5 papiers.
    # LA REGLE D'OR TIENT : accepter une conversion n'est pas accepter une
    # valeur ABSENTE — la duree source doit etre ECRITE, seule l'unite change.
    if famille == "temps":
        for m in re.finditer(
                r"(?<![\d.])(\d+(?:[.,]\d+)?)\s*"
                r"(h\b|hr\b|hrs\b|hours?\b|heures?\b|min\b|mins\b|minutes?\b|"
                r"s\b|sec\b|seconds?\b)", text, re.IGNORECASE):
            brut = float(m.group(1).replace(",", "."))
            u = m.group(2).lower()
            heures = (brut / 60.0 if u.startswith("min")
                      else brut / 3600.0 if u.startswith("s")
                      else brut)
            # Tolerance d'ARRONDI, pas d'a-peu-pres : 0,67 vaut 40 min,
            # 0,7 ne les vaut plus.
            if abs(heures - value) <= max(0.005, abs(heures) * 0.005):
                return True

    motif = _FAMILLES_UNITE.get(famille or "")
    # UNITE PARTAGEE : « 170 to 190 C », « 300 and 400 °C », « 6 to 16 h ». Le
    # premier nombre n'a pas d'unite a lui — l'exiger refuserait des valeurs
    # JUSTES. Constate immediatement : deux suites de tests sont tombees sur ce
    # seul motif des le durcissement. La chaine n'admet QUE des separateurs et
    # des nombres, donc « 62.3 g ... 23 mm » ne peut pas l'enjamber.
    chaine = r"(?:\s*(?:,|-|–|to|and|or|et|ou)\s*-?\d+(?:[.,]\d+)?)*"
    for f in forms:
        rx = rf"(?<![\d.]){re.escape(f)}(?![\d])"
        if motif:
            rx += chaine + motif
        if re.search(rx, text, re.IGNORECASE if motif else 0):
            return True
    return False


# Énumération à préfixe implicite : « strontium oxide, carbonate, nitrate or
# hydroxide » désigne QUATRE composés, mais « strontium carbonate » n'est jamais
# écrit d'un bloc. Exiger le nom complet dans la citation faisait perdre 3 des
# 5 précurseurs du papier de 1957 (rappel bloqué à 20-40 %).
# On accepte donc si le préfixe ET le suffixe figurent dans la citation, séparés
# UNIQUEMENT par une énumération — pas de preuve inventée, les deux termes sont
# bien présents et liés par la syntaxe de l'énumération.
# La normalisation ayant déjà supprimé la ponctuation, on ne peut pas exiger une
# virgule dans l'intervalle. On vérifie plutôt qu'il ne contient AUCUN mot
# structurant : dès qu'un verbe ou une préposition apparaît, les deux termes
# appartiennent à des propositions différentes et le lien est rompu.
_ENUM_BREAKERS = {
    "at", "in", "on", "was", "were", "is", "are", "be", "been", "with", "by",
    "from", "to", "for", "of", "the", "a", "an", "then", "after", "before",
    "under", "using", "used", "obtained", "heated", "mixed", "added", "placed",
    "prevent", "temperature", "reaction", "air", "powder",
}


# Synonymes d'atmosphère : le texte écrit « in air », « under argon »,
# « flowing 02 » (avec un zéro OCR) pour ce que le modèle déclare « air »,
# « Ar », « O2 ».
_ATM_SYNONYMS = {
    "air": ("air", "ambient"), "ambient": ("air", "ambient"),
    "ar": ("ar", "argon"), "argon": ("ar", "argon"),
    "n2": ("n2", "nitrogen", "azote"), "nitrogen": ("n2", "nitrogen"),
    "o2": ("o2", "oxygen"), "oxygen": ("o2", "oxygen"),
    "vacuum": ("vacuum", "vide"), "vide": ("vacuum", "vide"),
    "h2": ("h2", "hydrogen"), "hydrogen": ("h2", "hydrogen"),
}

# Le gaz peut etre SUJET de la phrase : « argon (99.999%) was used as the
# carrier gas » (cvd_mos2), « argon was bubbled in the electrolyte »
# (electro_nico). Tous les motifs `_ATM_MARKERS` exigeaient « in/under <gaz> » :
# cette seule contrainte de syntaxe faisait perdre TOUTE l'atmosphere de deux
# papiers sur quatre, alors qu'elle y est enoncee sans ambiguite.
# La parenthese optionnelle absorbe la purete : « argon (99.999%) was used ».
# Defini au niveau MODULE : dans un corps de classe, une comprehension ne voit
# pas les attributs de classe.
_ATM_SUJET_TPL = (r"\b(?:%s)\b(?:\s*\([^)]*\))?\s+(?:gas\s+)?"
                  r"(?:was|were|is|are)\s+"
                  r"(?:used\s+as|introduced|bubbled|purged|sparged|flushed|"
                  r"flowed|passed|fed)\b")
_ATM_SUJET_MARKERS = tuple(
    (_ATM_SUJET_TPL % gaz, val) for gaz, val in (
        ("ar|argon", "Ar"), ("n2|nitrogen", "N2"),
        ("o2|02|oxygen", "O2"), ("h2|hydrogen", "H2"),
    )
)


# Un equipement est soit un CONTENANT (ce qui tient la matiere — sa nature
# decide de la faisabilite : un flux de SrCl2 a 1300 °C detruit un creuset
# d'alumine), soit un APPAREIL (ce qui applique le traitement — remplaçable).
# Tout le reste est refuse : « room temperature » figurait dans le texte et
# passait donc le controle d'ancrage, sans etre un equipement.
_VESSEL_NOUNS = (r"crucibles?|autoclaves?|(?:digestion\s+)?bombs?|boats?|beakers?|"
                 r"vials?|ampoules?|flasks?|liners?|dishe?s?|mortars?|"
                 r"creusets?|nacelles?|bechers?|ballons?|"
                 # Le tube scelle est le contenant le plus courant de la chimie
                 # du solide et des sels fondus. Mais « tube furnace » est un
                 # APPAREIL : sans cette exclusion, le four passerait pour le
                 # contenant — l'inversion exacte que la distinction
                 # contenant/appareil existe pour empecher.
                 r"tubes?(?!\s+(?:furnaces?|ovens?|reactors?|mills?|kilns?))|"
                 r"tubes?\s+a\s+essai")
_APPARATUS_NOUNS = (r"furnaces?|ovens?|kilns?|stirrers?|mills?|centrifuges?|"
                    r"evaporators?|reactors?|hot\s*plates?|gloveboxe?s?|presses|"
                    r"sonicators?|pumps?|autoclaves?|fours?|etuves?|agitateurs?")
_EQUIPMENT_RE = re.compile(rf"\b(?:{_VESSEL_NOUNS}|{_APPARATUS_NOUNS})\b", re.I)
_VESSEL_ONLY_RE = re.compile(rf"\b(?:{_VESSEL_NOUNS})\b", re.I)


# La duree est souvent ECRITE dans la citation sans que le modele remplisse le
# champ. La recuperation d'origine exigeait « for|during|pendant » IMMEDIATEMENT
# suivi du nombre : sur cvd_mos2 elle manquait les QUATRE durees du gold, toutes
# presentes en toutes lettres (« in 40 min », « for next 25 min », « for about
# 10 min »), et « by 6 hours » sur selfondu_cosi.
# La TEMPERATURE est le pendant exact de la duree : ecrite dans la citation, et
# laissee vide par le modele. Sur `electro_nico`, « under stirring at 70°C for
# 24 h » rendait duration_h=24 et temperature=None — les deux valeurs sont a
# quatre mots l'une de l'autre, seule celle qui avait un mecanisme etait lue.
# Le degre est ecrit de quatre facons selon l'OCR (°, ˚, ◦, º), parfois perdu,
# parfois fondu en un seul caractere (℃). PAS de re.IGNORECASE : « 0.2 cm2 »
# donnerait un « c » suivi de « m », et la frontiere de mot le rattrape, mais on
# ne prend pas le risque.
_TEMP_RE = re.compile(
    r"(-?\d+(?:[.,]\d+)?)\s*(?:°|˚|◦|º)?\s*(?:C\b|℃)"
    # « 5 ◦C/h » est une RAMPE, pas un palier.
    r"(?!\s*(?:/|per\s)\s*(?:min|h|s|sec)|\s*h\s*[-−]\s*1|\s*min\s*[-−]\s*1)")
# « discharged at 0.15 C » est un REGIME de batterie (broyage_na), pas une
# temperature. Le « C » nu est ambigu : on s'abstient sur toute la phrase.
_TEMP_REGIME = re.compile(
    r"\b(?:discharg\w*|charg\w*|C-rate|cycling|coulombic)\b", re.I)
# Une parenthese qui nomme un FABRICANT decrit le MATERIEL, pas la consigne :
# « (Freeze Dryer -86℃, OPERON CO., LTD.) » donne la caracteristique du
# lyophilisateur, pas la temperature a appliquer.
_TEMP_FABRICANT = re.compile(
    r"\b(?:co\.|ltd|inc\b|gmbh|corp|instruments?|technolog\w+|scientific)\b"
    r"|®|™", re.I)


def _temperatures_citees(citation: str) -> list[float]:
    """Temperatures DISTINCTES qu'enonce cette citation, dans l'ordre."""
    if not citation or _TEMP_REGIME.search(citation):
        return []
    zones = [(m.start(), m.end()) for m in re.finditer(r"\([^)]*\)", citation)
             if _TEMP_FABRICANT.search(m.group(0))]
    vues: list[float] = []
    # UNITE PARTAGEE : « 300 and 400 °C » enonce DEUX temperatures, mais le
    # premier nombre n'a pas de degre a lui. Sans cette lecture on n'en voyait
    # qu'une, donc pas d'ambiguite, donc on retenait 400 — alors que le papier
    # decrit deux syntheses distinctes (coeur-coquille et homogene). C'est le
    # piege central de `selfondu_cosi`. Vaut aussi pour les plages
    # (« 170 to 190 °C »), ou l'abstention est tout aussi juste.
    for m in re.finditer(
            r"(-?\d+(?:[.,]\d+)?)\s*(?:,\s*|\s+(?:and|or|et|ou|to|a)\s+)"
            r"(?=-?\d+(?:[.,]\d+)?\s*(?:°|˚|◦|º)?\s*(?:C\b|℃))", citation):
        if any(a <= m.start() < b for a, b in zones):
            continue
        v = float(m.group(1).replace(",", "."))
        if -273 < v < 3000 and v not in vues:
            vues.append(v)
    for m in _TEMP_RE.finditer(citation):
        if any(a <= m.start() < b for a, b in zones):
            continue
        v = float(m.group(1).replace(",", "."))
        if -273 < v < 3000 and v not in vues:
            vues.append(v)
    return vues


_DUREE_PREPOS = r"for|during|pendant|in|within|over|after|by|en"
# Jusqu'a deux qualificatifs entre la preposition et le nombre.
_DUREE_QUALIF = (r"(?:(?:the\s+)?(?:next|additional|further|another|about|"
                 r"approximately|around|roughly|some|ca\.?)\s+){0,2}")
_DUREE_RE = re.compile(
    r"\b(" + _DUREE_PREPOS + r")\s+" + _DUREE_QUALIF
    + r"(\d+(?:[.,]\d+)?)\s*"
    # « 20 Hz » ne doit jamais devenir 20 heures : `h\b` echoue sur « Hz ».
    r"(min\b|mins\b|minutes?\b|h\b|hrs?\b|hours?\b|heures?\b)",
    re.IGNORECASE)
# « in 40 min » mesure le temps pour ATTEINDRE la consigne ; « for 25 min » est
# un palier. Les deux sont des durees du protocole — un chimiste releve les deux
# et le gold les retient — mais on NE convertit JAMAIS une montee en rampe
# °C/h : cette conversion inventee a deja rendu l'egalite stricte inatteignable
# sur combu_ferrite. On se contente donc de tracer la difference.
_DUREE_MONTEE = ("in", "within", "over")


# Colonnes numeriques declarees par le REGISTRE d'etapes. Import tolerant :
# une extraction ne doit jamais echouer parce qu'un registre manque.
try:
    from synthgraph.schemas.step_schema import colonnes_numeriques as _cn
    _COLONNES_REGISTRE = _cn()
except Exception:  # noqa: BLE001
    _COLONNES_REGISTRE = set()


def _value_in_minutes(value: float, citation: str) -> bool:
    """La citation exprime-t-elle CETTE valeur en minutes ?

    « heating for 15 min., regrinding … and reheating for 15 min. » : le modèle
    déclare duration_h=15 alors qu'il s'agit de 15 MINUTES. On ne convertit que
    si la citation dit explicitement « min » juste après le nombre, et jamais si
    elle dit « h » — en cas d'ambiguïté on ne touche à rien.
    """
    num = f"{value:g}"
    pat_min = rf"(?<![\d.]){re.escape(num)}\s*(?:min\b|minutes?\b|mn\b)"
    pat_h = rf"(?<![\d.]){re.escape(num)}\s*(?:h\b|hr\b|hours?\b|heures?\b)"
    return (re.search(pat_min, citation, re.IGNORECASE) is not None
            and re.search(pat_h, citation, re.IGNORECASE) is None)


def _atm_in_text(atm: str, text: str) -> bool:
    """L'atmosphère (ou un synonyme) figure-t-elle dans le texte ?"""
    key = _norm_words(str(atm))
    hay = _norm_words(text)
    for cand in _ATM_SYNONYMS.get(key, (key,)):
        if re.search(rf"\b{re.escape(cand)}\b", hay):
            return True
    return False


def _enumerated_compound(name: str, citation: str) -> bool:
    """« strontium carbonate » est-il prouvé par « strontium oxide, carbonate… » ?"""
    toks = _norm_words(name).split()
    if len(toks) < 2:
        return False
    prefix, suffix = toks[0], toks[-1]
    cit = _norm_words(citation)
    if prefix not in cit or suffix not in cit:
        return False
    for m in re.finditer(rf"\b{re.escape(prefix)}\b", cit):
        for s in re.finditer(rf"\b{re.escape(suffix)}\b", cit):
            if s.start() <= m.end():
                continue
            gap = cit[m.end():s.start()]
            # Fenêtre courte ET aucun mot de rupture : les deux termes
            # appartiennent alors à la même énumération.
            if len(gap) <= 60 and not (set(gap.split()) & _ENUM_BREAKERS):
                return True
    return False


_POLYMERE_RE = re.compile(r"\)\s*[nx]\s*$", re.I)


def _composition_key(formula: str):
    """Signature elementaire d'un compose, ou None si illisible (fail-safe)."""
    try:
        from synthgraph.validation.deterministic import parse_composition
        # Notation polymere : « (C6H10O5)n » (amidon) ne se parse pas a cause du
        # « n » terminal, et l'amidon se voyait alors AJOUTE une seconde fois —
        # etiquete solvant, alors qu'il est l'agent de coiffage. On retire le
        # marqueur de motif repete pour comparer le monomere.
        f = _POLYMERE_RE.sub(")", (formula or "").strip())
        c = parse_composition(f)
    except Exception:  # noqa: BLE001 — un validateur ne doit jamais planter
        return None
    if not c:
        return None
    return tuple(sorted((e, round(float(n), 3)) for e, n in c.items()))


# Une phrase de LAVAGE seule ne fait pas d'un compose un reactif. On exige
# l'absence de tout indice de synthese dans la meme phrase : « washed with
# ethanol » qualifie l'usage, « dissolved in ethanol and heated » non.
_LAVAGE_SEUL = re.compile(
    r"\b(washed|washing|rinsed|rinsing|rinse)\s+(?:out\s+)?with\b", re.I)
_SYNTHESE_HINT = re.compile(
    r"\b(dissolved|dispersed|mixed|added\s+to|reacted|heated\s+with|"
    r"stoichiometric|precursor|starting\s+material)\b", re.I)


def _enumerated_by_name(formula: str, text: str) -> bool:
    """« SrCO3 » est-il prouve par « strontium oxide, carbonate, nitrate… » ?

    `_enumerated_compound` a ete ecrit pour des NOMS : il decoupe « strontium
    carbonate » en prefixe + suffixe. Or le modele fournit des FORMULES, et
    « SrCO3 » normalise ne fait qu'un seul mot — la fonction abandonnait aussitot.
    Sur `prepara` (1957), les trois sources de strontium etaient donc refusees
    comme « absentes du texte » alors que le modele les avait correctement
    proposees : rappel bloque a 40 %.

    Le projet sait deja traduire « strontium carbonate » -> SrCO3 ; il manquait
    le chemin inverse. On cherche donc les NOMS connus qui designent ce compose,
    et on teste l'enumeration sur eux.
    """
    want = _composition_key(formula)
    if not want:
        return False
    try:
        from synthgraph.validation.deterministic import COMPOUND_NAME_TO_FORMULA
    except Exception:  # noqa: BLE001
        return False
    hay = _norm_words(text)
    for nom, f in COMPOUND_NAME_TO_FORMULA.items():
        if _composition_key(f) != want or not _enumerated_compound(nom, text):
            continue
        # Exiger une VRAIE enumeration : prefixe et suffixe separes par au moins
        # un mot. Colles, ils forment une mention litterale — deja couverte par
        # `_compound_named_in` — et le rapprochement devient une coincidence de
        # sous-chaine : « strontium-iridium oxide », qui designe le PRODUIT
        # Sr2IrO4, faisait accepter IrO2 comme precurseur du papier de 1957.
        toks = _norm_words(nom).split()
        if len(toks) < 2:
            continue
        if re.search(rf"\b{re.escape(toks[0])}\s+{re.escape(toks[-1])}\b", hay):
            continue
        return True
    return False


def _position_du_compose(formula: str, texte: str) -> int:
    """Ou le compose est-il mentionne dans ce texte ? (-1 si absent)

    `_compound_named_in` dit SI un compose est nomme ; situer une concentration
    demande de savoir OU. Sur `cbd_mnse`, le precurseur est enregistre
    `Mn(NO3)2` alors que la citation ecrit « 0.001 M manganese nitrate » : la
    formule n'y figure pas, seul le nom. Sans ce chemin, la concentration reste
    introuvable sur les papiers de chimie en solution — ceux-la memes qui la
    portent.

    Positions exprimees dans l'espace NORMALISE, comme partout ailleurs.
    """
    norm = _norm_words(texte)
    cle = _norm_words(formula)
    if cle and cle in norm:
        return norm.find(cle)

    want = _composition_key(formula)
    if not want:
        return -1
    try:
        from synthgraph.validation.deterministic import COMPOUND_NAME_TO_FORMULA
    except Exception:  # noqa: BLE001
        return -1
    meilleures = -1
    for nom, f in COMPOUND_NAME_TO_FORMULA.items():
        if _composition_key(f) != want:
            continue
        n = _norm_words(nom)
        if n and n in norm:
            p = norm.find(n)
            # Le nom le PLUS LONG situe le mieux : « manganese nitrate » plutot
            # que « nitrate » seul, qui pointerait sur un autre reactif.
            if meilleures < 0 or len(n) > len(_norm_words(nom)):
                meilleures = p
    return meilleures


# Un qualificatif de FORME accompagne souvent le compose : le modele suit la
# formulation de l'article (« Si nanoparticles », « Cu powder », « Zn foil »).
# La formule ne se parse alors plus, le repli par composition elementaire est
# saute, et le compose est refuse — le silicium, reactif PRINCIPAL de
# selfondu_cosi, a ete perdu ainsi, trois refus de suite.
# On ne retire QUE des mots de forme. Les mots de CHIMIE (acetate, oxide,
# chloride) portent la composition : les retirer ferait passer n'importe quel
# sel de cuivre pour du cuivre metal.
_MORPHOLOGIE_RE = re.compile(
    r"\b(?:nano(?:particles?|powders?|crystals?|sheets?|rods?|wires?|spheres?|"
    r"tubes?)|micro(?:particles?|spheres?|powders?)|particles?|powders?|"
    r"crystals?|flakes?|foils?|wires?|granules?|pellets?|chunks?|pieces?|"
    r"beads?|spheres?|wafers?|films?|sheets?|grains?|turnings?|shots?|lumps?|"
    r"ribbons?|strips?|fib(?:er|re)s?|bulk|metal)\b", re.I)


def _strip_morphologie(formula: str) -> str:
    """Retire les mots de FORME d'une formule. Chaine vide si il n'en reste rien.

    Une formule qui n'etait QUE de la morphologie (« nanoparticles ») ne nomme
    aucun compose : rendre la chaine d'origine la ferait matcher litteralement
    dans le texte, ce qui rouvrirait la porte que la regle d'or ferme.
    """
    net = _MORPHOLOGIE_RE.sub(" ", formula or "")
    return re.sub(r"\s+", " ", net).strip()


def _compound_named_in(formula: str, text: str) -> bool:
    """Le compose est-il nomme dans ce texte, formule OU nom en toutes lettres ?

    Sur `solgel_cuo`, le modele proposait `Cu(C2H3O2)2` et `(NH4)2CO3` — les BONS
    reactifs — mais la citation les nomme « copper acetate » et « ammonium
    carbonate ». Le controle litteral les refusait tous : 0 % de precurseurs sur
    un papier ou l'extraction etait juste. Les noms en toutes lettres sont la
    norme en chimie de solution, ce refus condamnait tout un pan du corpus.

    La regle d'or reste intacte : on exige toujours une preuve textuelle nommant
    le compose. On reconnait simplement que « copper acetate » nomme
    Cu(CH3COO)2, via le bilan elementaire deterministe du projet — deux
    ecritures de meme composition designent le meme corps. Fail-safe : toute
    formule illisible ne matche rien.
    """
    # Une formule qui se normalise en chaine vide (« !!! ») matcherait TOUT,
    # puisque "" est contenu dans n'importe quel texte : trou dans la garde
    # anti-invention, ferme ici.
    formula = _strip_morphologie(formula)
    nf = _norm_words(formula)
    if not nf:
        return False
    if nf in _norm_words(text):
        return True
    want = _composition_key(formula)
    if want is None:
        return False
    try:
        from synthgraph.validation.deterministic import normalize_compound_name
    except Exception:  # noqa: BLE001
        return False
    mots = re.findall(r"[A-Za-z][A-Za-z-]+", text or "")
    for n in (3, 2, 1):
        for i in range(len(mots) - n + 1):
            f = normalize_compound_name(" ".join(mots[i:i + n]))
            if not f:
                continue
            got = _composition_key(f)
            if got != want:
                continue
            # Un mot isole ne vaut preuve que pour un COMPOSE (« water »,
            # « EDTA », « starch »...). Un nom d'element seul en vaudrait une
            # pour le metal pur : la phrase « copper acetate » prouverait alors
            # le precurseur « Cu », ce qui est faux. Deux elements distincts au
            # minimum ferment cette porte.
            if n == 1 and len(got) < 2:
                continue
            return True
    return False


class RouteBuilder:
    """Accumule une voie de synthèse au fil des appels d'outils.

    Chaque `add_*` renvoie un dict {"ok": bool, "message": str} destiné à être
    réinjecté tel quel au modèle comme résultat d'outil.
    """

    # Paramètres numériques dont la valeur doit être prouvée par la citation.
    # Socle historique, COMPLETE par toutes les colonnes numeriques du
    # registre : celui-ci est la source unique, et une colonne ajoutee la-bas
    # passe desormais sous controle sans autre geste. Voir
    # `test_couverture_grounding.py`, qui verrouille l'invariant.
    _RATE_KEYS = {"ramp_rate_c_per_h", "cooling_rate_c_per_h"}
    _CHECKED_NUM = {
        "temperature_c", "target_temperature_c", "min_temperature_c",
        "max_temperature_c", "duration_h", "min_duration_h", "max_duration_h",
        "speed_rpm", "pressure_mpa", "ph", "concentration_mol_l",
    } | (_COLONNES_REGISTRE - _RATE_KEYS)
    # Dérivées d'un calcul : leur valeur n'a pas à figurer telle quelle
    # (ex. 5 °C/min → 300 °C/h). On vérifie alors la présence d'une notation
    # de vitesse dans la citation, pas le nombre lui-même.
    _RATE_HINT = re.compile(r"[°˚]?\s*[ckf]\s*(?:/|per\s+)\s*(?:h|hr|hour|min)|[°˚]?\s*[ckf]\s*h\s*[-−]\s*1",
                            re.IGNORECASE)

    def __init__(self, source_text: str, target: str = "", method_type: str = "",
                 route_id: str = "r1", full_text: str = ""):
        self.source = source_text or ""
        # Le texte FOCALISE fait 8 500 caracteres la ou le papier en fait 30 000 :
        # la phrase « Pure kesterite a ete synthetise a 180 °C pour 12 h » en est
        # exclue. Certaines recuperations ont besoin du papier ENTIER, mais pas
        # toutes — l'elargir partout ferait rentrer les sections de
        # caracterisation que la focalisation ecarte a juste titre. Seule la
        # condition optimale l'utilise, et ses garde-fous sont stricts.
        self.full_source = full_text or self.source
        self._source_norm = _norm_words(self.source)
        self.target = target
        self.method_type = method_type
        self.route_id = route_id
        self.precursors: list[dict] = []
        self.operations: list[dict] = []
        self.finalized = False
        self.rejections: list[str] = []   # trace de tout ce qui a été refusé
        self._order = 0

    # ------------------------------------------------------------------
    #  Vérifications communes
    # ------------------------------------------------------------------
    def _citation_in_source(self, citation: str) -> bool:
        """La citation est-elle présente dans la source ?

        Gère les citations ABRÉGÉES : le modèle remplace couramment un passage
        par « … » (constaté au test de faisabilité : « SrCl2 … were thoroughly
        mixed »). Une ellipse est une coupure, pas une invention — on exige donc
        que CHAQUE fragment soit présent ET dans l'ordre, ce qui reste vérifiable
        et n'autorise aucun ajout de texte.
        """
        norm = _norm_words(citation)
        if norm in self._source_norm:
            return True

        # 1) Coupure explicite par ellipse
        parts = [p for p in re.split(r"\s*(?:…|\.\.\.)\s*", citation) if p.strip()]
        if len(parts) >= 2 and self._fragments_in_order(parts, min_words=3):
            return True

        # 2) Phrase scindée par la MISE EN PAGE (sans ellipse).
        #    Les articles scientifiques sont en deux colonnes et l'extraction
        #    entrelace les paragraphes : sur PhysRevB, « Starting materials
        #    SrCO3, Ir02, and Ru02 were mixed in proportions to » est coupée en
        #    plein milieu par un paragraphe d'une autre colonne, puis reprend
        #    par « span the solid-solution series ». Aucune citation contiguë
        #    n'est alors possible — le modèle réessayait 6 fois puis bouclait.
        #    On découpe donc en fenêtres de mots et on exige que CHACUNE existe
        #    dans la source ET dans l'ordre : une phrase inventée ne passe pas,
        #    une phrase seulement scindée est acceptée.
        # Désactivable : la permissivité de cette étape est un LEVIER DE QUALITÉ,
        # pas un simple confort. Trop tolérante, elle laisse passer une citation
        # vague et dispense le modèle d'aller chercher la ligne de tableau qui
        # prouve la valeur. SYNTHGRAPH_STRICT_CITATION=1 la coupe pour comparer.
        if os.environ.get("SYNTHGRAPH_STRICT_CITATION") == "1":
            return False
        return self._greedy_cover(_norm_words(citation))

    def _greedy_cover(self, norm_citation: str, min_words: int = 5) -> bool:
        """La citation est-elle intégralement couverte par des fragments de la
        source, pris dans l'ordre ?

        Un découpage à pas fixe échoue ici : la fenêtre tombe à cheval sur la
        coupure de colonne. On consomme donc la citation par morceaux MAXIMAUX —
        à chaque position, on prend le plus long fragment encore présent dans la
        source, puis on repart de là.

        Rigueur préservée : chaque mot doit appartenir à un fragment retrouvé,
        et la position ne recule jamais. On peut donc couper une phrase, jamais
        en inventer une ni réagencer des morceaux épars.
        """
        words = norm_citation.split()
        if len(words) < min_words * 2:
            return False
        i, pos, n_frag = 0, 0, 0
        while i < len(words):
            best_j = -1
            for j in range(len(words), i + min_words - 1, -1):
                frag = " ".join(words[i:j])
                found = self._source_norm.find(frag, pos)
                if found >= 0:
                    best_j, pos = j, found + len(frag)
                    break
            if best_j < 0:
                return False          # un morceau n'existe nulle part en aval
            i = best_j
            n_frag += 1
            # Plafond SERRÉ (3, pas 6) : une coupure de colonne ou une césure
            # ne produit que 2 morceaux. Au-delà, la citation est trop vague —
            # et une validation trop permissive dispense le modèle d'aller
            # chercher la ligne de tableau qui prouve vraiment la valeur.
            if n_frag > 3:
                return False
        return True

    def _fragments_in_order(self, parts: list[str], min_words: int,
                            already_normalised: bool = False) -> bool:
        """Chaque fragment doit exister dans la source, dans l'ordre du texte.

        L'ordre est ce qui empêche de recomposer une citation à partir de
        morceaux épars : on ne peut que couper, jamais réagencer.
        """
        pos = 0
        for part in parts:
            np = part if already_normalised else _norm_words(part)
            if len(np.split()) < min_words:
                return False
            found = self._source_norm.find(np, pos)
            if found < 0:
                return False
            pos = found + len(np)
        return True

    def _phrase_la_plus_proche(self, citation: str) -> str:
        """Phrase de la source qui recouvre le mieux la citation tentee.

        Rendue au modele dans le message de refus pour qu'il puisse recopier la
        bonne. On exige un recouvrement FORT (au moins la moitie des mots de la
        citation, et au moins quatre mots) : sans ce seuil on suggererait une
        phrase au hasard, ce qui orienterait le modele vers une citation qui
        n'a rien a voir avec ce qu'il voulait dire.
        """
        mots = set(_norm_words(citation).split())
        if len(mots) < 4:
            return ""
        meilleure, score = "", 0.0
        for ph in re.split(r"(?<=[.;])\s+", self.full_source or self.source):
            ph = " ".join(ph.split())
            if not (20 < len(ph) < 400):
                continue
            communs = mots & set(_norm_words(ph).split())
            r = len(communs) / len(mots)
            if r > score:
                meilleure, score = ph, r
        return meilleure[:300] if score >= 0.5 else ""

    def _check_citation(self, citation: str) -> Optional[str]:
        """Renvoie un message d'erreur si la citation n'est pas exploitable."""
        if not citation or len(citation.strip()) < _MIN_CITATION_LEN:
            return (f"REFUSE : citation trop courte (< {_MIN_CITATION_LEN} caracteres). "
                    f"Copie une phrase COMPLETE et EXACTE du texte source.")
        if not self._citation_in_source(citation):
            # La citation tentée est conservée dans la trace (pas dans le message
            # au modèle) : sans elle, un échec massif est indiagnosticable.
            self.rejections.append(f"[citation absente] {citation[:120]!r}")
            # Le message de refus est la SEULE prise du modele pour se corriger
            # au tour suivant. Cas reel de cvd_mos2 : il a ecrit « the furnace
            # was FIRST heated to 300 °C » la ou le papier ecrit « FIRSTLY » —
            # un mot d'ecart sur quinze. L'etape a ete refusee deux fois et le
            # palier a 300 °C perdu, alors que la phrase visee etait la bonne.
            # On lui rend donc la phrase du texte dont il s'est le plus
            # approche. Aucun garde-fou n'est assoupli : la citation doit
            # toujours etre EXACTE, et les valeurs restent validees contre elle.
            proche = self._phrase_la_plus_proche(citation)
            return ("REFUSE : cette citation n'existe pas dans le texte source. "
                    "Tu dois COPIER une phrase mot pour mot depuis le texte "
                    "fourni, sans la reformuler ni la traduire."
                    + (f" La phrase du texte la plus proche de la tienne est : "
                       f"\"{proche}\" — recopie-la EXACTEMENT." if proche else ""))
        return None

    # ------------------------------------------------------------------
    #  Outil 1 — précurseur
    # ------------------------------------------------------------------
    def add_precursor(self, formula: str, citation: str,
                      molar_ratio: float = None, amount: str = None,
                      role: str = "reactant") -> dict:
        err = self._check_citation(citation)
        if err:
            self.rejections.append(f"add_precursor({formula}): {err}")
            return {"ok": False, "message": err}

        if not formula or not formula.strip():
            return {"ok": False, "message": "REFUSE : formula est obligatoire."}

        nettoye = _strip_morphologie(formula)
        if not nettoye:
            return {"ok": False,
                    "message": "REFUSE : formula ne nomme aucun compose."}
        formula = nettoye

        # Le nom du precurseur doit exister dans la source (anti-invention).
        # Même tolérance que ci-dessous pour les énumérations à préfixe
        # implicite : « strontium carbonate » n'existe nulle part en toutes
        # lettres, mais ses deux termes sont bien dans le texte.
        if (_norm_words(formula) not in self._source_norm
                and not _enumerated_compound(formula, self.source)
                and not _compound_named_in(formula, self.source)
                and not _enumerated_by_name(formula, self.source)):
            msg = (f"REFUSE : '{formula}' n'apparait pas dans le texte source. "
                   f"N'ajoute que des composes explicitement cites.")
            self.rejections.append(f"add_precursor({formula}): {msg}")
            return {"ok": False, "message": msg}

        # Le precurseur doit figurer dans SA PROPRE citation (citation pertinente).
        if (_norm_words(formula) not in _norm_words(citation)
                and not _enumerated_compound(formula, citation)
                and not _compound_named_in(formula, citation)
                and not _enumerated_by_name(formula, citation)):
            msg = (f"REFUSE : la citation fournie ne mentionne pas '{formula}'. "
                   f"Choisis la phrase du texte qui nomme ce compose.")
            self.rejections.append(f"add_precursor({formula}): {msg}")
            return {"ok": False, "message": msg}

        # Un ratio non prouve ne doit pas emporter le PRECURSEUR avec lui.
        # Sur `cbd_mnse`, LiAlH4 et la triethanolamine — tous deux nommes dans
        # leur citation — ont ete rejetes en bloc parce que le modele y avait
        # joint « molar_ratio=1 » absent du texte : deux reactifs perdus pour un
        # champ facultatif. `add_operation` ecarte deja le parametre fautif tout
        # en conservant l'etape ; add_precursor s'aligne. La regle d'or tient :
        # la valeur non prouvee n'est JAMAIS enregistree, elle est jetee.
        ratio_refuse = None
        if molar_ratio is not None and not _num_in(float(molar_ratio), citation):
            ratio_refuse = (f"ratio {float(molar_ratio):g} ecarte (absent de la citation)")
            self.rejections.append(f"add_precursor({formula}): {ratio_refuse}")
            molar_ratio = None

        # DÉDUPLICATION : un même composé était enregistré 2 ou 3 fois par voie
        # (mesuré : SrCO3 trois fois sur Sr214#1). Cela gonflait les compteurs
        # d'appels acceptés et laissait des entrées sans ratio à côté d'entrées
        # qui en avaient un. Un second appel ENRICHIT l'entrée existante :
        # c'est ainsi que le ratio arrive, quand le modèle finit par citer la
        # phrase qui le porte (« of 1 : 2 : 7 ») plutôt que celle qui nomme les
        # composés. On n'écrase jamais une valeur déjà prouvée.
        key = _norm_words(formula)
        for p in self.precursors:
            if _norm_words(p["formula"]) != key:
                continue
            enriched = []
            if molar_ratio is not None and p.get("molar_ratio") is None:
                p["molar_ratio"] = float(molar_ratio)
                p["citation"] = citation.strip()   # la citation qui prouve le ratio
                enriched.append(f"ratio={molar_ratio:g}")
            if amount and not p.get("amount"):
                p["amount"] = amount
                enriched.append(f"amount={amount}")
            if role and role != "reactant" and p.get("role") == "reactant":
                p["role"] = role
                enriched.append(f"role={role}")
            return {"ok": True, "duplicate": True,
                    "message": (f"DEJA ENREGISTRE : '{formula}'"
                                + (f" — complete avec {', '.join(enriched)}." if enriched
                                   else ". Passe au compose SUIVANT, ou a add_operation."))}

        # Un compose dont la SEULE preuve est une phrase de lavage n'est pas un
        # reactif de la synthese : `solgel_cuo` declarait l'ethanol de rincage
        # comme precurseur du CuO, ce qu'un chimiste tenterait d'ajouter au
        # milieu. On ne supprime rien — l'information reste, qualifiee par son
        # usage, et le solvant du lavage figure de toute facon sur l'etape.
        entree = {
            "name": formula.strip(), "formula": formula.strip(),
            "role": role or "reactant", "amount": amount or "",
            "unit": "", "citation": citation.strip(),
            "molar_ratio": float(molar_ratio) if molar_ratio is not None else None,
        }
        if _LAVAGE_SEUL.search(citation) and not _SYNTHESE_HINT.search(citation):
            entree["usage"] = "lavage"
        self.precursors.append(entree)
        if ratio_refuse:
            # Le modele doit savoir POURQUOI le ratio manque, sinon il ne
            # rappellera jamais l'outil avec la bonne citation.
            return {"ok": True, "partial": True,
                    "message": (f"PARTIEL : precurseur '{formula}' enregistre SANS ratio "
                                f"— {ratio_refuse}. Si le rapport molaire existe, "
                                f"rappelle add_precursor en citant la ligne EXACTE "
                                f"qui le porte.")}
        return {"ok": True,
                "message": f"OK : precurseur '{formula}' enregistre "
                           f"({len(self.precursors)} au total)."}

    # ------------------------------------------------------------------
    #  Outil 2 — opération
    # ------------------------------------------------------------------
    def add_operation(self, step_type: str, citation: str,
                      order: int = None, atmosphere_citation: str = None,
                      **params) -> dict:
        # L'atmosphère vit dans la PROSE (« heated in air »), les valeurs dans
        # les TABLEAUX : une seule citation ne peut pas prouver les deux, et
        # l'atmosphère disparaissait du graphe. Elle dispose donc de sa propre
        # citation — chaque donnée garde une preuve, la règle d'or est intacte.
        err = self._check_citation(citation)
        if err:
            self.rejections.append(f"add_operation({step_type}): {err}")
            return {"ok": False, "message": err}

        if not step_type or not step_type.strip():
            return {"ok": False, "message": "REFUSE : step_type est obligatoire."}

        # Chaque valeur numerique doit etre PROUVEE par la citation.
        refused: list[str] = []
        kept: dict[str, Any] = {}
        for k, v in (params or {}).items():
            if v is None or v == "":
                continue
            if k in self._RATE_KEYS:
                # Il ne suffit PAS que la citation contienne une notation de
                # vitesse : le nombre propose doit y figurer. Sans cette seconde
                # condition, `cooling_rate_c_per_h=0` passait sur la citation
                # « Sr214#1 ... 1300◦C → (8◦C/h) 900◦C → RT » — une vitesse de
                # 0 °C/h inscrite dans le graphe alors que le papier dit 8.
                # Constate sur 4 etapes de `crystal` (tracabilite 100 -> 92,2 %).
                if not self._RATE_HINT.search(citation):
                    refused.append(f"{k}={v} (aucune notation de vitesse dans la citation)")
                    continue
                try:
                    fv = float(v)
                except (TypeError, ValueError):
                    kept[k] = v
                    continue
                if _num_in(fv, citation):
                    kept[k] = fv
                else:
                    refused.append(f"{k}={v} (cette VALEUR n'apparait pas dans la citation)")
                continue
            if k in self._CHECKED_NUM:
                try:
                    fv = float(v)
                except (TypeError, ValueError):
                    kept[k] = v
                    continue
                if _num_in(fv, citation, k):
                    # UNITÉ : « heating for 15 min. » était enregistré
                    # duration_h=15, soit 15 HEURES au lieu de 15 minutes —
                    # un chimiste chaufferait 60 fois trop longtemps. Si la
                    # citation exprime la valeur en minutes, on convertit.
                    if k.endswith("duration_h") and _value_in_minutes(fv, citation):
                        fv = round(fv / 60.0, 4)
                        logger.info(f"  [unite] {k}={v:g} exprimé en MINUTES dans la "
                                    f"citation → {fv:g} h")
                    kept[k] = fv
                else:
                    refused.append(f"{k}={v:g}" if isinstance(v, float) else f"{k}={v}")
                continue

            # `equipment` etait un texte libre, admis SANS aucune preuve. Des que
            # le prompt a cite des exemples de contenants, le modele en a recopie
            # un : `equipment='becher'` sur un papier ANGLAIS qui dit « acid
            # digestion bomb ». Fuite d'exemple de prompt, mode d'echec deja
            # documente. Le contenant doit donc exister dans le TEXTE SOURCE,
            # comme toute autre donnee du graphe.
            # Le champ LIBRE ne peut pas etre la porte d'entree que tous les
            # autres garde-fous interdisent : chaque valeur doit figurer dans la
            # citation, exactement comme une temperature ou une duree.
            if k == "extra_parameters" and isinstance(v, dict):
                gardes: dict[str, str] = {}
                for nom, val in v.items():
                    val_s = str(val).strip()
                    if not nom or not val_s:
                        continue
                    nb = re.search(r"\d+(?:[.,]\d+)?", val_s)
                    prouve = (_num_in(float(nb.group(0).replace(",", ".")), citation)
                              if nb else _norm_words(val_s) in _norm_words(citation))
                    if prouve:
                        gardes[str(nom).strip()] = val_s
                    else:
                        refused.append(f"{nom}={val_s} (absent de la citation)")
                if gardes:
                    kept[k] = gardes
                continue

            if k == "equipment" and isinstance(v, str) and v.strip():
                if not (_norm_words(v) and _norm_words(v) in self._source_norm):
                    refused.append(f"{k}={v} (absent du texte source)")
                elif not _EQUIPMENT_RE.search(v):
                    # Exister dans la source ne suffit pas : encore faut-il que
                    # ce soit un equipement. `equipment='room temperature'` etait
                    # accepte sur `hydro_czts` — la valeur figure bien dans le
                    # texte, mais ce n'est ni un contenant ni un appareil.
                    refused.append(f"{k}={v} (ni contenant ni appareil)")
                else:
                    kept[k] = v
                continue

            kept[k] = v

        # ── Atmosphère : elle entrait SANS AUCUNE preuve (elle tombait dans le
        # cas générique ci-dessus). Elle doit être prouvée par la citation de
        # l'étape OU par sa citation dédiée, laquelle doit exister dans la
        # source. Sinon elle est écartée — jamais devinée.
        atm = kept.get("atmosphere")
        if atm:
            atm_cit = atmosphere_citation or ""
            proved = _atm_in_text(atm, citation)
            if not proved and atm_cit:
                if not self._citation_in_source(atm_cit):
                    refused.append(f"atmosphere={atm} (citation dédiée introuvable dans le texte)")
                    kept.pop("atmosphere", None)
                    atm = None
                elif _atm_in_text(atm, atm_cit):
                    proved = True
                    kept["atmosphere_citation"] = atm_cit.strip()
            if atm and not proved:
                refused.append(f"atmosphere={atm} (aucune citation ne la prouve)")
                kept.pop("atmosphere", None)

        # ACCEPTATION PARTIELLE plutôt que tout-ou-rien.
        # Mesuré au test de faisabilité : en refusant l'opération entière dès
        # qu'un paramètre n'était pas prouvé, le modèle restait bloqué et
        # bouclait sur finalize_route — 0 étape enregistrée. On garde donc ce
        # qui est prouvé et on écarte le reste, qui devient un trou déclaré :
        # la règle d'or est respectée (rien d'invente n'entre), et l'agent
        # progresse au lieu de se figer.
        # DURÉE non déclarée mais ÉCRITE dans la citation : le modèle omet
        # souvent « heating for 15 min. » alors que la durée est un paramètre
        # essentiel (sans elle, on ne sait pas combien de temps chauffer).
        # Déduction déterministe, sur preuve textuelle — comme pour les ratios.
        if "duration_h" not in kept:
            # `mixing` et `grinding` etaient exclus par prudence : leur citation
            # enonce souvent PLUSIEURS actions, et leur attribuer la duree du
            # chauffage qui suit fabriquerait une recette fausse. Mais la mesure
            # du 21/08 a montre que cette exclusion coute une valeur reelle —
            # les 5 min de dispersion de `hydro_czts`, difference entre
            # l'egalite stricte sur les durees et son echec.
            # On leve l'exclusion en gardant ce qu'elle protegeait : pour un
            # melange ou un broyage, la citation ne doit porter qu'UNE SEULE
            # duree distincte. Deux durees, c'est l'ambiguite visee — abstention.
            m = _DUREE_RE.search(citation)
            if m and step_type.strip().lower() in ("mixing", "grinding",
                                                   "milling", "ball milling",
                                                   "ball_milling", "broyage"):
                vues = set()
                for x in _DUREE_RE.finditer(citation):
                    v = float(x.group(2).replace(",", "."))
                    u = x.group(3).lower()
                    vues.add(round(v / 60.0, 4) if u.startswith("min") else v)
                if len(vues) != 1:
                    m = None
            if m:
                val = float(m.group(2).replace(",", "."))
                unit = m.group(3).lower()
                hours = round(val / 60.0, 4) if unit.startswith("min") else val
                kept["duration_h"] = hours
                kept["duration_h_source"] = (
                    "citation_regex_montee"
                    if m.group(1).lower() in _DUREE_MONTEE else "citation_regex")
                logger.info(f"  [duree] {val:g} {unit} déduit de la citation "
                            f"→ duration_h={hours:g}")

        # TEMPERATURE non declaree mais ECRITE dans la citation. Meme discipline
        # que la duree : recuperation deterministe sur preuve textuelle.
        # REGLE D'OR : la citation ne doit porter qu'UNE temperature distincte.
        # Deux, ce sont deux etapes — on ne peut pas dire laquelle appartient a
        # celle-ci, donc on s'abstient. Meme raisonnement que pour les trois pH
        # de `cbd_mnse` et les deux temperatures de `selfondu_cosi`
        # (« pre-heated to the reaction temperature 300 and 400 °C »).
        if not any(k in kept for k in ("temperature_c", "target_temperature_c")):
            vues = _temperatures_citees(citation)
            if len(vues) == 1:
                kept["temperature_c"] = vues[0]
                kept["temperature_c_source"] = "citation_regex"
                logger.info(f"  [temperature] {vues[0]:g} °C deduit de la citation")

        # DÉDUPLICATION des opérations : le modèle réémet la même étape à
        # plusieurs tours (constaté : 3 fois le même « heating 1300 °C » avec la
        # même citation). Un second appel ENRICHIT l'étape existante au lieu de
        # la répéter — sans quoi le graphe contient trois fois la même opération
        # et un chimiste croit à trois chauffages successifs.
        # ATTENTION : une même citation peut décrire PLUSIEURS étapes distinctes.
        # « 900°C, 24 h; 1000°C, 60 h; 1100°C, 60 h » = trois paliers cités par
        # la même phrase. Fusionner sur (type, citation) seuls les écrasait :
        # températures 100 % → 33 % sur PhysRevB. On ne fusionne donc QUE si
        # aucun paramètre commun ne porte une valeur DIFFÉRENTE.
        # Type CANONIQUE, pas le type brut. Defaut trouve en relisant le
        # document des voies : sur `broyage_na` le pipeline emettait DEUX
        # etapes pour un seul geste — « grinding » avec la duree, puis
        # « ball_milling » avec l'atmosphere, sur la MEME phrase. Un chimiste
        # y lisait deux broyages successifs. Le papier etait pourtant a
        # l'egalite stricte complete : les durees se dedoublonnent, la mesure
        # ne voyait rien. Un defaut de STRUCTURE, invisible a une comparaison
        # de valeurs.
        # La regle de non-fusion sur valeur DIFFERENTE reste entiere : elle
        # protege « 900°C, 24 h; 1000°C, 60 h; 1100°C, 60 h », une phrase pour
        # TROIS paliers, dont la fusion avait fait tomber PhysRevB a 33 %.
        sig = (self._type_canonique(step_type), _norm_words(citation))
        for prev in self.operations:
            if (self._type_canonique(prev["type"]),
                    _norm_words(prev.get("citation", ""))) != sig:
                continue
            conflict = any(k in prev and prev[k] is not None and prev[k] != v
                           for k, v in kept.items())
            if conflict:
                continue          # étape réellement distincte : on la garde
            added = []
            for k, v in kept.items():
                if prev.get(k) is None:
                    prev[k] = v
                    added.append(k)
            return {"ok": True, "duplicate": True, "kept": len(added),
                    "message": (f"DEJA ENREGISTREE : etape '{step_type}' avec cette citation"
                                + (f" — completee ({', '.join(added)})." if added
                                   else ". Passe a l'etape SUIVANTE ou a finalize_route."))}

        # NEUTRALITE DU DIALOGUE. Le message renvoye annonce « N parametre(s)
        # valide(s) », et ce N incluait les valeurs recuperees APRES COUP par
        # les post-traitements : le modele s'entendait dire « 4 parametre(s)
        # valide(s) » alors qu'il n'en avait fourni AUCUN, et le compte
        # DESCENDAIT quand il fournissait correctement la temperature — message
        # inversement informatif.
        # Mesure du 21/08 : trois runs strictement identiques donnent des
        # resultats IDENTIQUES (le moteur est deterministe, `temperature=0.0`),
        # et pourtant `solgel_cuo` divergeait entre deux runs a texte focalise
        # identique. La seule variable restante etait le DIALOGUE : un
        # post-traitement cense ne rien couter deplacait la trajectoire du
        # modele au tour suivant, et rendait les correctifs inattribuables.
        # Une valeur recuperee porte un marqueur `<champ>_source` : on l'exclut
        # du compte. Elle reste dans l'etape — invisible au dialogue, presente
        # dans le graphe.
        n_modele = sum(1 for k in kept
                       if not k.endswith("_source") and f"{k}_source" not in kept)

        self._order += 1
        op = {"type": step_type.strip(), "operation": step_type.strip(),
              "order": int(order) if order else self._order,
              "citation": citation.strip(), **kept}
        self.operations.append(op)

        if refused:
            self.rejections.append(
                f"add_operation({step_type}) valeurs ecartees : {', '.join(refused)}")
            # `partial` distingue « étape créée avec des données » de « étape
            # créée vide ». Sans ce drapeau, un appel dont TOUS les paramètres
            # sont écartés comptait comme un succès : sur PhysRevB, 23 appels
            # « acceptés » n'avaient produit aucune donnée exploitable.
            return {"ok": True, "partial": True, "kept": n_modele,
                    "message": (f"PARTIEL : operation '{step_type}' enregistree (etape "
                                f"{op['order']}) avec {n_modele} parametre(s) prouve(s). "
                                f"ECARTES car absents de ta citation : {', '.join(refused)}. "
                                f"Si ces valeurs existent, rappelle add_operation en citant "
                                f"la ligne EXACTE (souvent une ligne de tableau) qui les porte.")}

        return {"ok": True, "partial": False, "kept": n_modele,
                "message": f"OK : operation '{step_type}' enregistree "
                           f"(etape {op['order']}, {n_modele} parametre(s) valide(s))."}

    # ------------------------------------------------------------------
    #  Outil 3 — clôture
    # ------------------------------------------------------------------
    def finalize_route(self, target: str = None, method_type: str = None,
                       sample_id: str = None) -> dict:
        if not self.precursors:
            msg = ("REFUSE : aucun precurseur enregistre. Une voie de synthese sans "
                   "reactif est inexploitable — appelle add_precursor d'abord.")
            return {"ok": False, "message": msg}
        if not self.operations:
            msg = ("REFUSE : aucune operation enregistree. Appelle add_operation "
                   "pour decrire au moins une etape.")
            return {"ok": False, "message": msg}
        if target:
            self.target = target
        if method_type:
            self.method_type = method_type
        self.sample_id = sample_id
        self.finalized = True
        return {"ok": True,
                "message": f"OK : voie finalisee ({len(self.precursors)} precurseurs, "
                           f"{len(self.operations)} operations). Ne rappelle plus d'outil."}

    # ------------------------------------------------------------------
    #  Export au format du pipeline existant
    # ------------------------------------------------------------------
    # « Powders of IrO2, SrCO3, and SrCl2·6H2O … in a molar ratio of 1 : 2 : 7 »
    # L'expression des ratios ne nomme AUCUN composé : pour attribuer 1 à IrO2
    # il faut relier l'ordre d'énumération à l'ordre des chiffres. Le modèle ne
    # le fait que pour le composé du milieu (mesuré : 1 ratio sur 3).
    # L'ordre EST une preuve textuelle — on l'exploite de façon déterministe,
    # sans rien deviner : on n'attribue que si le nombre de composés cités
    # correspond exactement au nombre de ratios, et dans le même ordre.
    _RATIO_EXPR = re.compile(r"(?:molar\s+)?ratios?\s+of\s+([\d.]+(?:\s*:\s*[\d.]+)+)",
                             re.IGNORECASE)

    # Dans les papiers réels, les proportions vivent dans un TABLEAU :
    #     en-tête :  IrO2 : SrCO3 : SrCl2
    #     ligne   :  - Sr214#1  1 : 2 : 7  1300◦C → (8◦C/h) 900◦C → RT
    # L'appariement se fait donc entre l'EN-TÊTE (formules) et la LIGNE
    # (nombres), et non dans une phrase du texte courant.
    _HEADER_RE = re.compile(r"([A-Za-z][A-Za-z0-9()·\.]*(?:\s*:\s*[A-Za-z][A-Za-z0-9()·\.]*){1,5})")
    _NUMROW_RE = re.compile(r"(?<![\d.])(\d+(?:\.\d+)?(?:\s*:\s*\d+(?:\.\d+)?){1,5})")

    def _ratio_pairs_from_table(self) -> list[tuple[list[str], list[float]]]:
        """Couples (formules de l'en-tête, valeurs d'une ligne) de même longueur."""
        pairs = []
        headers: list[list[str]] = []
        for raw in self.source.splitlines():
            line = raw.strip()
            if not line:
                continue
            for m in self._HEADER_RE.finditer(line):
                names = [x.strip() for x in re.split(r"\s*:\s*", m.group(1))]
                # Un en-tête de ratios ne contient que des noms de composés
                if len(names) >= 2 and all(any(c.isupper() for c in n) for n in names):
                    headers.append(names)
            m = self._NUMROW_RE.search(line)
            if m and headers:
                vals = [float(x) for x in re.split(r"\s*:\s*", m.group(1))]
                if len(vals) == len(headers[-1]):
                    pairs.append((headers[-1], vals))
        return pairs

    def _infer_ratios_from_enumeration(self) -> int:
        """Complète les ratios manquants. Deux sources, toutes deux textuelles :
        l'en-tête d'un tableau de proportions, ou l'ordre d'énumération d'une
        phrase. Renvoie le nombre de ratios déduits."""
        if not self.precursors:
            return 0

        # --- source 1 : tableau (cas dominant dans les papiers réels) ---
        n = 0
        for names, vals in self._ratio_pairs_from_table():
            mapping = {}
            for name, v in zip(names, vals):
                key = _norm_words(name)
                for p in self.precursors:
                    pk = _norm_words(p["formula"])
                    if pk == key or pk.startswith(key) or key.startswith(pk):
                        mapping[id(p)] = v
            # On n'applique que si TOUS les composés de l'en-tête sont reconnus
            if len(mapping) != len(names):
                continue
            for p in self.precursors:
                v = mapping.get(id(p))
                if v is None:
                    continue
                if p.get("molar_ratio") is None:
                    p["molar_ratio"] = v
                    p["ratio_source"] = "table_header"
                    n += 1
                elif abs(p["molar_ratio"] - v) > 0.01:
                    return n          # contradiction : on s'arrête là
            if n:
                logger.info(f"  [ratios] {n} ratio(s) déduit(s) de l'en-tête de tableau "
                            f"({' : '.join(names)} = {':'.join(f'{v:g}' for v in vals)})")
                return n

        # --- source 2 : énumération dans une phrase ---
        m = self._RATIO_EXPR.search(self.source)
        if not m:
            return n
        values = [float(x) for x in re.split(r"\s*:\s*", m.group(1))]

        # Ordre d'apparition des composés enregistrés, AVANT l'expression.
        head = _norm_words(self.source[:m.start()])
        positions = []
        for p in self.precursors:
            key = _norm_words(p["formula"])
            core = key.split(" ")[0] if key else ""
            idx = head.rfind(key) if key in head else (head.rfind(core) if core else -1)
            if idx < 0:
                return 0                     # un composé absent → on s'abstient
            positions.append((idx, p))
        positions.sort(key=lambda t: t[0])

        if len(positions) != len(values):    # correspondance stricte exigée
            return 0

        n = 0
        for (_, p), v in zip(positions, values):
            if p.get("molar_ratio") is None:
                p["molar_ratio"] = v
                p["ratio_source"] = "enumeration_order"
                n += 1
            elif abs(p["molar_ratio"] - v) > 0.01:
                return 0                     # contradiction → on annule tout
        if n:
            logger.info(f"  [ratios] {n} ratio(s) déduit(s) de l'ordre d'énumération "
                        f"({m.group(1)})")
        return n

    _COOL_KEYS = ("cooling_rate_c_per_h", "ramp_rate_c_per_h")

    _TYPES_PREPARATION = ("mixing", "grinding", "ball_milling", "dissolution",
                          "ultrasonication")
    _TYPES_THERMIQUES = ("heating", "cooling", "calcination", "sintering",
                         "annealing", "soak", "hydrothermal", "cvd",
                         "flux_growth", "crystal_growth", "drying",
                         "quenching")

    def _preparation_en_tete(self) -> bool:
        """Une recette commence par la PREPARATION, jamais par le four.

        Trouve par l'audit de REFAISABILITE, pas par la comparaison au gold :
        `crystal` obtient 100 % en precurseurs, ratios et durees, et ses DIX
        voies sont pourtant INEXECUTABLES — elles commencent par « heating » et
        placent en DERNIER « Powders of IrO2, SrCO3 and SrCl2 · 6H2O were
        thoroughly mixed and placed in a platinum crucible ». On melange les
        poudres AVANT de les enfourner.

        Cause : l'ordre suit la lecture du papier, et le modele a cite la ligne
        du TABLEAU (le programme thermique) avant la phrase des Methods.

        Effet de bord mesure : l'atmosphere « in air », portee par cette etape
        placee en dernier, ne propageait vers RIEN — la propagation ne va que
        vers l'avant. D'ou 8 atmospheres manquantes sur ce seul papier.

        MESURE AVANT D'ECRIRE : 12 voies sur 3 papiers sont dans ce cas.

        PIEGE : `physrev` decrit « with many INTERMEDIATE grindings ». Un
        broyage entre deux paliers est REEL. On ne deplace donc QU'UNE etape, et
        seulement quand AUCUNE preparation ne precede le premier traitement
        thermique — sur `prepara`, le broyage intermediaire ne bouge pas.
        """
        ops = sorted(self.operations, key=lambda o: o.get("order") or 0)
        types = [self._type_canonique(o.get("type")) for o in ops]
        i_therm = next((i for i, t in enumerate(types)
                        if t in self._TYPES_THERMIQUES), None)
        if i_therm is None:
            return False
        if any(t in self._TYPES_PREPARATION for t in types[:i_therm]):
            return False                     # une preparation ouvre deja la voie
        tardives = [i for i, t in enumerate(types)
                    if t in self._TYPES_PREPARATION and i > i_therm]
        if not tardives:
            return False
        op = ops.pop(tardives[-1])           # la DERNIERE, jamais un intermediaire
        ops.insert(0, op)
        for i, o in enumerate(ops, 1):
            o["order"] = i
        self.operations = ops
        logger.info(f"  [sequence] preparation '{op.get('type')}' remontee en "
                    f"tete : une recette ne commence pas par le four")
        return True

    def _fix_sequence(self) -> None:
        """Deux corrections deterministes revelees par la relecture en chimiste.

        1. COLLISION D'ORDRE. Le modele passe parfois `order=1` a deux etapes
           DIFFERENTES : la sequence devient ambigue, donc irreproductible au
           laboratoire. On renumerote alors sequentiellement selon l'ordre
           d'enregistrement (qui suit l'ordre de lecture du papier).

        2. « HEATING » VERS UNE TEMPERATURE PLUS BASSE. Sur `Sr214#2`
           (1100 °C -> 1300 °C -> 900 °C), le palier a 900 °C etait etiquete
           `heating` alors qu'on y DESCEND. Un chimiste qui suit la recette
           telle quelle chauffe au lieu de refroidir. Les deux temperatures
           viennent du papier : la correction ne fabrique aucune valeur, elle
           lit le signe de leur difference. Fail-safe : on ne touche a rien si
           l'une des deux temperatures manque.
        """
        ops = self.operations
        if len(set(o.get("order") for o in ops)) != len(ops):
            for i, o in enumerate(ops, 1):
                o["order"] = i

        prev_t = None
        for o in sorted(ops, key=lambda x: x.get("order") or 0):
            t = o.get("target_temperature_c")
            if t is None:
                continue
            if (prev_t is not None and t < prev_t
                    and o.get("type", "").strip().lower() == "heating"):
                o["type"] = o["operation"] = "cooling"
                # une rampe qui descend est une vitesse de REFROIDISSEMENT
                if "ramp_rate_c_per_h" in o and "cooling_rate_c_per_h" not in o:
                    o["cooling_rate_c_per_h"] = o.pop("ramp_rate_c_per_h")
                logger.info(f"  [sequence] etape {o.get('order')} requalifiee "
                            f"heating -> cooling ({prev_t} -> {t} °C)")
            prev_t = t

    # Unites listees de la plus longue a la plus courte : « mol » avalerait
    # le debut de « moles » et laisserait un residu.
    _AMOUNT_RE = re.compile(
        r"^\s*(\d+(?:[.,]\d+)?)\s*(mmol|moles|mole|mol)\b", re.I)

    # Familles d'etapes recuperables : (types deja equivalents, verbes, indices
    # de contexte). L'indice de contexte evite de confondre le traitement du
    # PRODUIT avec une phrase de caracterisation ou de nettoyage d'appareil.
    _WORKUP = (
        ("separation", ("washing", "filtration", "separation", "centrifugation",
                        "rinsing", "decantation"),
         r"\b(separated|separation|rins(?:ed|ing)|wash(?:ed|ing)|"
         r"filtrat(?:ed|ion)|filter(?:ed|ing)|centrifug(?:ed|ation)|"
         r"decant(?:ed|ation))\b"),
        ("mixing", ("mixing", "grinding", "milling"),
         r"\b(mixed|mixing|ground together|gr(?:ou|i)nd(?:ed|ing)|milled|"
         r"stirred|dispersed|dissolved)\b"),
    )
    # Indices de contexte : la phrase doit parler de la MATIERE, pas d'un
    # appareil ou d'une mesure. Elargi apres `cbd_mnse`, ou « The mixture is
    # filtered before being added to the chemical bath » etait ecarte faute d'un
    # seul mot reconnu — l'etape de filtration du gold etait donc perdue.
    _WORKUP_CONTEXT = re.compile(
        r"\b(crystals?|product|precipitates?|powders?|sample|residual|flux|"
        r"water|ethanol|alcohol|solvent|acetone|solution|mixture|bath|gel|"
        r"suspension|slurry|filtrate|supernatant|reagents?|materials?)\b", re.I)

    def _recover_workup_steps(self) -> int:
        """Recupere depuis la SOURCE les etapes que le modele n'a pas declarees.

        Sur les papiers TABULAIRES (les iridates), les conditions vivent dans un
        tableau et le traitement final dans le texte courant : le modele suit le
        tableau et oublie la prose. `crystal` n'avait ainsi que des etapes
        `heating`/`cooling`, sans le rincage a l'eau distillee qui separe le flux
        residuel — sans lui on recupere un bloc de SrCl2 fige et aucun cristal,
        la synthese est irrealisable. Sur les papiers en prose (corpus5) ces
        etapes sortent naturellement : la recuperation ne s'y declenche pas.

        On ne fabrique RIEN : l'etape est creee A PARTIR d'une phrase reelle du
        papier, qui devient sa citation. Aucun parametre numerique n'est deduit.
        Fail-safe : on s'abstient si une etape equivalente existe deja, si aucune
        phrase ne porte le verbe, ou si la phrase n'a aucun indice de contexte
        (pour ne pas confondre le traitement du produit avec une phrase de
        caracterisation).
        """
        if not self.source:
            return 0
        # Types CANONIQUES, pas bruts. Defaut trouve en relisant le document des
        # voies : le modele avait declare « ball-milling », ce mecanisme ne le
        # reconnaissait pas comme un broyage deja present et AJOUTAIT une etape
        # — d'ou deux operations pour un seul geste sur `broyage_na`, et un
        # chimiste qui y lisait deux broyages successifs. Le papier etait
        # pourtant a l'egalite stricte complete : un defaut de STRUCTURE, que
        # la comparaison de valeurs ne peut pas voir.
        presents = set()
        for o in self.operations:
            brut = (o.get("type") or "").strip().lower()
            presents.add(brut)
            presents.add(self._type_canonique(brut))
        phrases = re.split(r"(?<=[.;])\s+", self.source)
        n = 0
        for famille, equivalents, verbes in self._WORKUP:
            equiv = set(equivalents) | {self._type_canonique(e) for e in equivalents}
            if presents & equiv:
                continue                       # deja declaree par le modele
            rx = re.compile(verbes, re.I)
            for ph in phrases:
                ph = ph.strip()
                if not (15 < len(ph) < 400) or not rx.search(ph):
                    continue
                if not self._WORKUP_CONTEXT.search(ph):
                    continue
                self._order += 1
                self.operations.append({
                    "type": famille, "operation": famille,
                    "order": self._order, "citation": ph,
                    "citation_source": "recuperation_deterministe",
                })
                logger.info(f"  [workup] etape '{famille}' recuperee du texte : "
                            f"{ph[:70]}")
                n += 1
                break
        return n

    # Marqueurs d'atmosphere : le mot NU ne suffit pas (« air-sensitive »,
    # « air quality »...). On exige la tournure qui designe un milieu reactionnel.
    _ATM_MARKERS = (
        (r"\b(?:in|under|dans|sous)\s+(?:an?\s+|the\s+)?(?:static\s+|flowing\s+|"
         r"synthetic\s+|dry\s+|ambient\s+|open\s+)?air\b", "air"),
        (r"\b(?:in|under)\s+(?:an?\s+)?ambient\s+(?:atmosphere|conditions?)\b", "air"),
        (r"\b(?:in|under)\s+(?:a\s+)?(?:dynamic\s+|static\s+|primary\s+|"
         r"secondary\s+|high\s+)?vacuum\b|\bvacuum\s+(?:oven|furnace|dried)\b",
         "vacuum"),
        (r"\b(?:in|under)\s+(?:an?\s+)?(?:flowing\s+)?(?:ar|argon)\b", "Ar"),
        (r"\b(?:in|under)\s+(?:an?\s+)?(?:flowing\s+)?(?:n2|nitrogen)\b", "N2"),
        # « 02 » avec un ZERO : les PDF scannes confondent O et 0. PhysRevB
        # (1994) ecrit « heated in flowing 02 » — la table `_ATM_SYNONYMS`
        # traitait deja ce cas, pas les motifs de recuperation.
        (r"\b(?:in|under)\s+(?:an?\s+)?(?:flowing\s+)?(?:o2|02|oxygen)\b", "O2"),
        (r"\b(?:in|under)\s+(?:an?\s+)?(?:flowing\s+)?(?:h2|hydrogen)\b", "H2"),
    ) + _ATM_SUJET_MARKERS
    # « without inert gas protection » (reduc_cu) ne doit JAMAIS donner une
    # atmosphere : une negation dit ce qui N'A PAS ete fait.
    _ATM_NEGATION = re.compile(
        r"\b(without|absence of|no|not|non|free of|devoid of|sans)\b", re.I)

    def _recover_atmosphere(self) -> int:
        """Recupere l'atmosphere depuis la CITATION de chaque etape.

        L'atmosphere n'etait jamais extraite sur le corpus5 (5 papiers sur 5)
        alors qu'elle figure dans les citations que le modele utilise deja :
        `solgel_cuo` porte « dried in a muffle furnace IN AIR at 60 °C ». La
        preuve est donc la, seule la declaration manquait — meme schema que les
        etapes de traitement final.

        Rien n'est invente : le marqueur doit apparaitre dans la citation de
        l'etape. Trois abstentions : etape ayant deja une atmosphere, marqueur
        precede d'une NEGATION dans la meme proposition (`reduc_cu` :
        « without inert gas protection »), ou aucun marqueur.
        """
        n = 0
        for op in self.operations:
            if op.get("atmosphere"):
                continue
            cit = op.get("citation") or ""
            for pat, valeur in self._ATM_MARKERS:
                m = re.search(pat, cit, re.I)
                if not m:
                    continue
                # Fenetre avant le marqueur, bornee a la proposition courante :
                # une negation d'une AUTRE phrase ne doit pas bloquer ici.
                debut = max(0, m.start() - 60)
                avant = cit[debut:m.start()]
                avant = re.split(r"[.;]", avant)[-1]
                if self._ATM_NEGATION.search(avant):
                    self.rejections.append(
                        f"atmosphere '{valeur}' ecartee : niee dans la citation "
                        f"(« ...{avant.strip()[-40:]} »)")
                    break
                op["atmosphere"] = valeur
                op["atmosphere_citation"] = cit
                logger.info(f"  [atmosphere] '{valeur}' recuperee de la citation "
                            f"de l'etape {op.get('order')}")
                n += 1
                break
        n += self._atmosphere_depuis_source()
        n += self._propager_atmosphere()
        return n

    # « Pure kesterite CZTS has been synthesized at 180°C for 12 h » : la
    # CONDITION RETENUE, distincte de la plage explorée. Le marqueur d'optimalite
    # est exige — sans lui, n'importe quelle phrase portant une temperature et
    # une duree serait prise pour la recette.
    # Marqueurs de REUSSITE uniquement. « was » ou « has been » ne suffisent
    # pas : « The mixture WAS stirred at 180 C for 12 h » serait pris pour la
    # recette retenue alors qu'il decrit une etape parmi d'autres.
    _OPTIMUM_RE = re.compile(
        r"\b(?:pure|purity|optimal|optimum|best|successfully|single[- ]phase|"
        r"phase[- ]pure|highest)\b[^.]{0,120}?"
        r"(\d+(?:[.,]\d+)?)\s*[°˚◦]?\s*C[^.]{0,40}?for\s+(\d+(?:[.,]\d+)?)\s*h\b",
        re.I)

    # « 0.001 M manganese nitrate », « 15 mM copper acetate » : la concentration
    # PRECEDE le compose. Mesure du corpus : presente dans les phrases
    # operatoires de 7 papiers sur 8, sans colonne au schema.
    _CONC_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(mM|M)\b(?![a-zA-Z])")
    # Un pH de CONSIGNE (« adjust the pH to 10 ») n'est pas un pH de resultat
    # (« the best crystalline at pH: 9 » decrit ce qu'on a obtenu).
    _PH_RE = re.compile(r"\bpH\b[^.\d]{0,30}?(\d+(?:[.,]\d+)?)", re.I)
    # « adjust the pH value of the solution to 10, 9, 8 » pose TROIS bains
    # distincts. Retenir « 10 » attribuerait a une etape ce qui decrit trois
    # experiences : en presence d'une enumeration, on s'abstient.
    # La valeur suivante doit etre un pH NU, sans unite : « 10, 9, 8 » enumere
    # trois bains, « 10, 2 mL of HCl » donne un pH puis un VOLUME.
    _PH_MULTIPLE = re.compile(
        r"\bpH\b[^.]{0,30}?\d+(?:[.,]\d+)?\s*(?:,|;|\bor\b|\band\b)\s*"
        # La negation englobe l'espace : « \s*(?![a-zA-Z]) » se satisfait en ne
        # consommant aucun espace, et juge alors l'espace lui-meme.
        r"\d+(?:[.,]\d+)?(?!\s*[a-zA-Z])", re.I)
    _PH_CONSIGNE = re.compile(
        r"\b(adjust\w*|set|bring\w*|maintain\w*|fixed|regulated|prepared\s+with|"
        r"buffered)\b", re.I)

    def _recover_concentrations(self) -> int:
        """Concentration molaire d'un precurseur, depuis SA citation.

        En chimie de solution, c'est la donnee de pesee : « 5 mL de nitrate de
        manganese » ne dit rien sans « 0,001 M ». Le corpus la porte sur 7
        papiers sur 8 et le schema n'avait pas de colonne pour la recevoir.

        On retient la concentration qui PRECEDE le compose — c'est la convention
        d'ecriture — et la plus proche de lui, pour ne pas attribuer a l'un ce
        qui appartient a l'autre dans « 5 mL 0.001 M manganese nitrate, 5 mL
        TEA ». Piege ecarte : « 0.5 M Na2SO4 was used as the electrolyte »
        appartient a une mesure photoelectrochimique, pas a la synthese — la
        citation du precurseur ne la contient pas.
        """
        n = 0
        for p in self.precursors:
            if p.get("concentration"):
                continue
            cit = p.get("citation") or ""
            f = (p.get("formula") or "").strip()
            if not cit or not f:
                continue
            # Position du compose : par sa formule, ou par un nom qui le designe
            pos = _position_du_compose(f, cit)
            if pos < 0:
                continue
            # Les positions se comparent dans le MEME espace : on renormalise
            # chaque prefixe pour situer les concentrations.
            avant = [(len(_norm_words(cit[:m.start()])),
                      f"{m.group(1).replace(',', '.')} {m.group(2)}",
                      "(" in cit[max(0, m.start() - 2):m.start()])
                     for m in self._CONC_RE.finditer(cit)]
            # La concentration doit etre ACCOLEE au compose : « 0.001 M
            # manganese nitrate ». Sans borne de distance, dans « 5 mL 0.001 M
            # manganese nitrate, 5 mL de Se, et 5 mL triethanolamine », la TEA
            # heritait du 0,001 M du nitrate — la mauvaise attribution que cette
            # regle est censee empecher. Quelques mots au plus, jamais la phrase.
            # Deux ecritures, toutes deux reelles dans le corpus :
            #   « 0.001 M manganese nitrate »   -> la concentration PRECEDE
            #   « CuSO4 5H2O (0.1 M) »          -> elle SUIT, entre parentheses
            # Dans les deux cas elle doit etre ACCOLEE : sans borne, la TEA de
            # `cbd_mnse` heritait du 0,001 M du nitrate, trois composes plus loin.
            # ADJACENCE, pas proximite. Dans « 8 % HCl, 5 mL 0.001 M manganese
            # nitrate », le HCl n'est qu'a quatorze caracteres du « 0.001 M » et
            # heritait d'une concentration qui appartient au nitrate — alors que
            # le papier le donne a 8 %. Deux cas seulement :
            #   la concentration PRECEDE immediatement  -> « 0.001 M manganese nitrate »
            #   elle SUIT immediatement le compose      -> « CuSO4 5H2O (0.1 M) »
            # Le cas « suit » exige une PARENTHESE : c'est le seul discriminant
            # fiable. Sans elle, `HCl` — court, donc proche du « 0.001 M » qui
            # le suit — heritait d'une concentration qui n'est pas la sienne.
            longueur = len(_norm_words(f)) or 6
            proches = [c for c in avant
                       if (0 <= pos - c[0] <= 14)                        # precede
                       or (c[2] and -(longueur + 6) <= pos - c[0] < 0)]  # suit, ( )
            if not proches:
                continue
            proches.sort(key=lambda c: abs(pos - c[0]))
            p["concentration"] = proches[0][1]
            p["concentration_source"] = "citation"
            n += 1
        if n:
            logger.info(f"  [concentration] {n} precurseur(s) enrichi(s)")
        return n

    def _recover_ph(self) -> int:
        """pH de CONSIGNE d'une operation, depuis sa citation.

        Sur `cbd_mnse`, le pH decide la phase obtenue : « At pHs of 11 and 10
        the MnSeO4 structure was observed » — ce n'est pas MnSe. Un pH manquant
        rend la recette inexploitable.

        On ne retient QUE le pH de consigne : « In order to adjust the pH value
        of the solution to 10 ». Un pH de resultat (« the best crystalline at
        pH: 9 ») decrit ce qu'on a obtenu, pas ce qu'il faut regler.
        """
        n = 0
        for op in self.operations:
            if op.get("ph") is not None:
                continue
            cit = op.get("citation") or ""
            m = self._PH_RE.search(cit)
            if not m or not self._PH_CONSIGNE.search(cit):
                continue
            if self._PH_MULTIPLE.search(cit):
                self.rejections.append(
                    "pH ecarte : la citation en pose plusieurs (bains distincts)")
                continue
            op["ph"] = float(m.group(1).replace(",", "."))
            op["ph_source"] = "citation"
            n += 1
        if n:
            logger.info(f"  [pH] {n} operation(s) enrichie(s)")
        return n

    def _completer_hydrate(self) -> int:
        """Retablit la forme HYDRATEE quand la citation la porte.

        Sur `crystal`, le modele enregistre `SrCl2` alors que sa propre citation
        dit « Powders of IrO2, SrCO3, and SrCl2 · 6H2O ». L'ecart n'est pas
        cosmetique : 266,6 g/mol contre 158,5 — un chimiste qui pese le sel
        anhydre se trompe de 40 %.

        On ne fait que COMPLETER, jamais retirer : un hydrate deja enregistre
        n'est pas touche, et l'anhydre n'est promu que si la citation de CE
        precurseur porte explicitement la forme hydratee.
        """
        n = 0
        for p in self.precursors:
            f = (p.get("formula") or "").strip()
            cit = p.get("citation") or ""
            if not f or "h2o" in f.lower():
                continue
            m = re.search(
                rf"{re.escape(f)}\s*[·.x·*]\s*(\d*)\s*H2O", cit, re.I)
            if not m:
                continue
            hydrate = f"{f}·{m.group(1) or ''}H2O"
            p["formula"] = p["name"] = hydrate
            p["hydrate_source"] = "citation"
            logger.info(f"  [hydrate] '{f}' complete en '{hydrate}' "
                        f"d'apres sa citation")
            n += 1
        return n

    def _recover_condition_optimale(self, etapes: list[dict] | None = None) -> int:
        """La condition RETENUE, quand le modele n'a cite que la plage exploree.

        Sur `hydro_czts`, la citation « conducted at 170°C to 190°C for 6 to
        16 h » dit ce qui a ete TESTE ; une autre phrase dit ce qui a MARCHE :
        « Pure kesterite Cu2ZnSnS4 has been synthesized at 180°C for 12 h ». Un
        chimiste doit refaire l'optimum, pas une borne de la plage.

        Fail-safe strict : on n'agit que sur une etape portant deja une PLAGE,
        et seulement si les deux valeurs tombent DANS cette plage. Hors plage,
        la phrase parle d'autre chose et on s'abstient.
        """
        # Texte ENTIER : la focalisation ecarte la phrase d'optimum, qui vit
        # dans la section resultats et non dans le mode operatoire.
        source = self.full_source
        if not source:
            return 0
        m = self._OPTIMUM_RE.search(source)
        if not m:
            return 0
        t = float(m.group(1).replace(",", "."))
        d = float(m.group(2).replace(",", "."))
        phrase = " ".join(source[max(0, m.start()):m.end() + 30].split())

        n = 0
        for op in (etapes if etapes is not None else self.operations):
            tmin, tmax = op.get("min_temperature_c"), op.get("max_temperature_c")
            dmin, dmax = op.get("min_duration_h"), op.get("max_duration_h")
            if None in (tmin, tmax, dmin, dmax):
                continue
            if not (tmin <= t <= tmax and dmin <= d <= dmax):
                continue
            op["target_temperature_c"] = t
            op["duration_h"] = d
            op["condition_citation"] = phrase
            op["condition_source"] = "optimum_du_papier"
            logger.info(f"  [optimum] condition retenue {t} °C / {d} h "
                        f"(plage {tmin}-{tmax} °C, {dmin}-{dmax} h)")
            n += 1
        return n

    @staticmethod
    def _est_ligne_de_tableau(citation: str) -> bool:
        """Cette citation est-elle une LIGNE DE TABLEAU ?

        Un tableau est IMPRIME ailleurs que la prose : sa position dans le
        document ne dit rien de sa position dans la recette. Sur `crystal`, la
        mention « The crucibles were heated ... IN AIR » est en position 10479
        et les lignes qui portent les programmes thermiques en 9200 — donc
        « avant ». La contrainte de position excluait ainsi HUIT atmospheres
        pourtant presentes dans la source.

        Meme detection que le re-ancrage des citations sur les tableaux
        (`_TABLE_ROW_HINT`, runner.py) : import paresseux pour ne pas creer de
        dependance circulaire, motif de repli identique.
        """
        if not citation or len(citation) < 12:
            return False
        try:
            from synthgraph.pipeline.runner import _TABLE_ROW_HINT as rx
        except Exception:  # noqa: BLE001
            rx = re.compile(r"(→|->|\s:\s|;\s*\d|\|)"
                            r"|(\d\s*[°◦˚]\s*c.{0,40}\d\s*[°◦˚]\s*c)", re.I)
        return bool(rx.search(citation))

    def _atmosphere_depuis_source(self) -> int:
        """Aucune etape n'a d'atmosphere : la chercher dans le TEXTE SOURCE.

        Sur `physrev`, « heated in flowing 02 » vit dans une phrase qu'aucune
        etape ne cite — la propagation ne pouvait donc rien propager. Meme
        dispositif que le contenant : on situe la mention dans la source et on
        l'attribue aux etapes qui la suivent.

        Fail-safe : on ne fait rien si une etape porte deja une atmosphere (la
        propagation s'en chargera), si la source n'en nomme aucune, ou si elle
        en nomme PLUSIEURS — on ne devine pas laquelle s'applique.
        """
        if not self.source or any(o.get("atmosphere") for o in self.operations):
            return 0
        trouvees = []
        for pat, valeur in self._ATM_MARKERS:
            for m in re.finditer(pat, self.source, re.I):
                debut = max(0, m.start() - 60)
                avant = re.split(r"[.;]", self.source[debut:m.start()])[-1]
                if self._ATM_NEGATION.search(avant):
                    continue
                phrase = self.source[max(0, m.start() - 90):m.end() + 40]
                trouvees.append((len(_norm_words(self.source[:m.start()])),
                                 valeur, " ".join(phrase.split())))
        if len({v for _, v, _ in trouvees}) != 1:
            return 0                      # aucune, ou plusieurs : on s'abstient

        norm_src = _norm_words(self.source)
        pos0, valeur, phrase = sorted(trouvees)[0]
        n = 0
        for op in sorted(self.operations, key=lambda o: o.get("order") or 0):
            cit = _norm_words(op.get("citation") or "")
            if len(cit) < 20:
                continue
            p = norm_src.find(cit[:60])
            # Une LIGNE DE TABLEAU echappe a la contrainte de position : elle
            # est imprimee ailleurs que la prose, et son rang dans le document
            # ne dit rien de son rang dans le protocole. Le projet a deja
            # arbitre que le tableau est une source de PREMIER RANG.
            if not self._est_ligne_de_tableau(op.get("citation") or ""):
                if p < 0 or p + len(cit) < pos0:
                    continue              # etape ANTERIEURE a la mention
            elif p < 0:
                continue
            op["atmosphere"] = valeur
            op["atmosphere_citation"] = phrase
            op["atmosphere_source"] = "source"
            n += 1
        if n:
            logger.info(f"  [atmosphere] '{valeur}' trouvee dans la source, "
                        f"appliquee a {n} etape(s)")
        return n

    def _propager_atmosphere(self) -> int:
        """Une atmosphere declaree vaut jusqu'a ce qu'une autre soit nommee.

        12 trous sur 5 papiers venaient de la meme cause : le marqueur existe
        dans le papier mais pas dans la citation de l'etape. « The crucibles
        were heated in a programmable box furnace IN AIR » vaut pour la chauffe
        ET pour le refroidissement qui suit — c'est ainsi qu'on lit un protocole,
        et c'est le mecanisme deja eprouve sur le contenant.

        Propagation vers l'AVANT uniquement, jamais en arriere : une atmosphere
        nommee tardivement ne dit rien de ce qui s'est passe avant.

        On ne propage PAS les temperatures par le meme moyen : chaque palier a
        la sienne, et propager inventerait des valeurs fausses. La limite entre
        « lire un protocole » et « inventer » passe exactement la.
        """
        n = 0
        courante = courante_cit = None
        for op in sorted(self.operations, key=lambda o: o.get("order") or 0):
            if op.get("atmosphere"):
                courante = op["atmosphere"]
                courante_cit = (op.get("atmosphere_citation")
                                or op.get("citation") or "")
                continue
            if not courante:
                continue
            # Une etape qui SORT la matiere (lavage, filtration) met fin a la
            # continuite : le produit quitte le four, l'atmosphere ne le suit pas.
            if (op.get("type") or "").strip().lower() in (
                    "washing", "filtration", "separation", "centrifugation",
                    "rinsing", "decantation"):
                courante = None
                continue
            op["atmosphere"] = courante
            op["atmosphere_citation"] = courante_cit
            op["atmosphere_source"] = "propagee"
            n += 1
        if n:
            logger.info(f"  [atmosphere] propagee a {n} etape(s) suivante(s)")
        return n

    # Un contenant ne compte que s'il RECOIT la matiere. Exiger le verbe de
    # transfert ecarte deux fausses pistes reelles : « VialTweeter » (un
    # sonicateur de marque, ou `vial` est un morceau de mot) et « stored in
    # glass vial for further analysis » (stockage APRES synthese, pas un
    # recipient reactionnel).
    _VESSEL_TRANSFER = re.compile(
        r"\b(?:placed?|transferred?|added?|loaded|poured|introduced|filled|"
        r"carried\s+out|conducted|performed|run|sealed|contained)\s+"
        r"(?:\w+\s+){0,3}?(?:in|into|to|within)\s+"
        # Jusqu'a 5 mots avant le nom : « platinum or zirconium silicate
        # combustion boats » (prepara) en compte cinq.
        r"(?:an?\s+|the\s+)?((?:\w+\s+){0,5}?"
        rf"(?:{_VESSEL_NOUNS}))\b", re.I)

    # Tournures qui introduisent le SOLVANT DE REACTION, relevees sur le corpus.
    _SOLVENT_INTRO = (
        r"(?:dissolved|dispersed|suspended)\s+(?:in|into)\s+"
        r"(?:\d+(?:[.,]\d+)?\s*m?[lL]\s+of\s+)?(?:an?\s+|the\s+)?([a-z][a-z\- ]{2,30}?)"
        r"(?=[,.;]|\s+(?:for|at|under|with|and|by|to)\b)",
        r"filled\s+with\s+(?:\d+(?:[.,]\d+)?\s*m?[lL]\s+(?:of\s+)?)?([a-z][a-z\- ]{2,30}?)"
        r"(?=[,.;]|\s+(?:for|at|under|with|and|by|to)\b)",
        r"completed\s+with\s+([a-z][a-z\- ]{2,30}?)(?=[,.;]|\s+to\b)",
        r"([a-z][a-z\- ]{2,30}?)\s+(?:was|were|is|are)\s+used\s+"
        r"(?:as\s+(?:the\s+)?solvent|for\s+all\s+the\s+experiment)",
        # Un VOLUME nomme un reactif reel : « Twenty milliliters concentrate 1-4
        # dioxane ... are added to a beaker » introduit le dioxane, jamais
        # declare autrement. Le qualificatif eventuel (« concentrate ») est
        # ignore, sinon la normalisation echoue.
        r"(?:\d+(?:[.,]\d+)?|twenty|thirty|forty|fifty|ten|five)\s*"
        r"(?:m[lL]|milliliters?|millilitres?)\s+(?:of\s+)?(?:concentrate[d]?\s+)?"
        r"([a-z0-9][a-z0-9,\- ]{2,28}?)"
        r"(?=\s*(?:and|are|is|was|were|to|for|then|[,.;])|$)",
    )
    # Un compose introduit par un volume n'est pas forcement le SOLVANT : la
    # triethanolamine est un agent complexant. On ne qualifie « solvent » que ce
    # qui en est un ; le reste entre comme reactif, ce que le gold attend.
    # eau, ethanol, methanol, isopropanol, acetone, dioxane, ethylene glycol.
    # La triethanolamine en est volontairement ABSENTE : c'est un agent
    # complexant, pas un milieu.
    _SOLVANTS = {"H2O", "C2H5OH", "CH3OH", "C3H8O", "C3H6O", "C4H8O2", "C2H6O2"}
    # Le solvant d'une MESURE n'est pas celui de la synthese. `hydro_czts` ecrit
    # « dispersed into ethanol by ultrasound » — pour une observation TEM.
    # Un lavage non plus : « washed with ethanol » ne fait pas de l'ethanol un
    # milieu reactionnel.
    _NON_SYNTHESE = re.compile(
        r"\b(tem|hrtem|sem|fesem|xrd|dls|bet|ftir|raman|edx|eds|xps|"
        r"spectr\w*|isotherm|adsorption|diffract\w*|microscop\w*|measurement|"
        r"analys\w*|characteriz\w*|washed|washing|rins\w+)\b", re.I)

    def _recover_solvents(self) -> int:
        """Ajoute le SOLVANT DE REACTION quand le modele l'a omis.

        L'eau manquait sur `reduc_cu` et `cbd_mnse`, le dioxane sur `cbd_mnse` —
        et le modele ne les avait jamais PROPOSES (aucun rejet a leur nom) : pure
        omission. Sans solvant la recette n'est pas executable, et toute la
        chimie en solution est concernee.

        Rien n'est fabrique : on passe par `add_precursor`, donc tous les
        garde-fous existants s'appliquent — le compose doit etre nomme par la
        phrase, qui devient sa citation. Deux exclusions propres a ce cas : les
        phrases de CARACTERISATION (« dispersed into ethanol by ultrasound »
        pour une image TEM) et celles de LAVAGE (« washed with ethanol »).
        """
        if not self.source:
            return 0
        try:
            from synthgraph.validation.deterministic import normalize_compound_name
        except Exception:  # noqa: BLE001
            return 0

        # Deduplication par COMPOSITION, pas par chaine : l'amidon etait deja
        # enregistre sous `(C6H10O5)n` et se voyait rajoute en `C6H10O5` — un
        # doublon, qui plus est etiquete « solvant » alors que c'est l'agent de
        # coiffage. Meme equivalence elementaire que partout ailleurs.
        deja = {_norm_words(p["formula"]) for p in self.precursors}
        deja_keys = {k for k in (_composition_key(p["formula"])
                                 for p in self.precursors) if k}
        n = 0
        for ph in re.split(r"(?<=[.;])\s+", self.source):
            ph = ph.strip()
            if not (20 < len(ph) < 400) or self._NON_SYNTHESE.search(ph):
                continue
            for pat in self._SOLVENT_INTRO:
                m = re.search(pat, ph, re.I)
                if not m:
                    continue
                brut = " ".join(m.group(1).split())
                formule = normalize_compound_name(brut)
                if not formule or _norm_words(formule) in deja:
                    continue
                cle = _composition_key(formule)
                if cle and cle in deja_keys:
                    continue
                role = "solvent" if formule in self._SOLVANTS else "reactant"
                r = self.add_precursor(formule, ph, role=role)
                if r.get("ok"):
                    deja.add(_norm_words(formule))
                    if cle:
                        deja_keys.add(cle)
                    self.precursors[-1]["precursor_source"] = "solvant_recupere"
                    logger.info(f"  [solvant] '{formule}' recupere de : {ph[:70]}")
                    n += 1
                break
        return n

    # La virgule ARRETE la capture — elle ne peut pas etre a la fois un
    # caractere admis et un separateur, sinon « 30% and 80% ethanol, followed by
    # drying at 60C » etait avale en entier.
    # « washed IN methanol », « rinsed USING distilled water » : la preposition
    # n'est pas toujours « with ». Mesure du 21/08 sur selfondu_cosi, dont
    # l'etape de lavage ressortait VIDE alors que `solvent` est REQUIS.
    _LAVAGE_SOLVANT = re.compile(
        r"\b(?:washed|washing|rinsed|rinsing|rinse)\s+(?:out\s+)?"
        r"(?:with|in|using)\s+"
        r"([a-z0-9%\- ]{3,70}?)"
        # La capture s'arrete AVANT le quantificateur et avant un participe :
        # elle rendait « ethanol three times » et « deionized water twice be »,
        # ce dernier tronque en plein mot. Un champ pollue est pire qu'un trou
        # declare — il passe pour une donnee.
        # FRONTIERES DE MOT indispensables : sans elles le « to » de la liste
        # correspond au « to » d'« aceTOne », et le solvant devient « ace ».
        # Le defaut etait ANTERIEUR — l'ancienne liste portait deja `to` nu.
        r"(?=\s*(?:(?:for|to|then|before|prior|after|followed|under|once|"
        r"twice|thrice)\b|and\s+dried\b|by\s+\w+\s+cycles?\b|"
        r"(?:two|three|four|five|six|seven|eight|nine|ten|\d+)\s*"
        r"(?:times?|cycles?)\b|[,.;])|$)", re.I)
    _REPETITIONS = {"once": 1, "twice": 2, "thrice": 3, "two": 2, "three": 3,
                    "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
                    "nine": 9, "ten": 10}
    # « twice » et « thrice » s'emploient SEULS ; « three times » exige le nom.
    # « seven CYCLES of centrifugation/redispersion » compte aussi : un cycle de
    # lavage est une repetition, quel que soit le mot employe.
    _REPET_RE = re.compile(
        r"\b(?:(once|twice|thrice)\b|"
        r"(two|three|four|five|six|seven|eight|nine|ten|\d+)\s+"
        r"(?:times?|cycles?)\b)", re.I)

    def _recover_washing_details(self) -> int:
        """Solvant et repetitions d'un lavage, depuis SA propre citation.

        Les citations de lavage nomment le solvant — « washed with ethanol and
        distilled water », « washed with 30% and 80% ethanol » — mais le modele
        ne renseigne pas le champ `solvent`, pourtant REQUIS pour un lavage.
        Trois etapes du corpus etaient concernees. Meme dispositif que
        `_recover_atmosphere` : la preuve est la citation de l'etape.

        Le solvant est conserve TEL QUE LE PAPIER L'ECRIT : « 30% and 80%
        ethanol » n'est pas de l'ethanol pur, et normaliser en `C2H5OH`
        perdrait la concentration, qui change le resultat du lavage.
        """
        n = 0
        for op in self.operations:
            if (op.get("type") or "").strip().lower() not in (
                    "washing", "rinsing", "separation"):
                continue
            cit = op.get("citation") or ""
            if not op.get("solvent"):
                m = self._LAVAGE_SOLVANT.search(cit)
                if m:
                    brut = " ".join(m.group(1).split()).rstrip(" ,")
                    # « washed IN a beaker » : admettre « in » ouvre la porte au
                    # CONTENANT. Un recipient n'est pas un solvant, et le
                    # prendre pour tel inventerait un reactif.
                    if brut and not _EQUIPMENT_RE.search(brut):
                        op["solvent"] = brut
                    n += 1
            if not op.get("repetitions"):
                m = self._REPET_RE.search(cit)
                if m:
                    mot = (m.group(1) or m.group(2)).lower()
                    op["repetitions"] = self._REPETITIONS.get(
                        mot, int(mot) if mot.isdigit() else None)
                    if op["repetitions"] is None:
                        op.pop("repetitions")
                    else:
                        n += 1
        if n:
            logger.info(f"  [lavage] {n} detail(s) recupere(s) des citations")
        return n

    def _recover_vessel_per_step(self) -> int:
        """Attribue a CHAQUE operation le contenant qui la recoit.

        Choix de Terry (20/08) : le contenant doit etre extrait operation par
        operation, pas porte par la voie entiere. Principe chimique : un
        contenant nomme lors d'un TRANSFERT vaut pour les operations suivantes
        jusqu'au transfert suivant — c'est ainsi qu'on lit un protocole.

        La propagation est une lecture, pas une invention : le contenant vient
        d'une phrase reelle, conservee dans `vessel_citation` pour etre relue.
        Meme dispositif que `atmosphere_citation`, deja en place pour une valeur
        prouvee par une AUTRE phrase que la citation principale de l'etape.

        Fail-safe : sans verbe de transfert on ne retient rien, et une etape
        dont la citation est introuvable dans la source n'herite de rien.
        """
        if not self.source:
            return 0
        # Positions calculees dans l'espace NORMALISE, jamais sur le texte brut.
        # Deux raisons, chacune constatee :
        #  - `prepara` : l'OCR de 1957 coupe les mots (« combustion » et
        #    « boats » separes par un saut de ligne) alors que le modele cite la
        #    forme recollee — aucune citation n'etait localisee ;
        #  - `crystal` : ses citations sont des LIGNES DE TABLEAU, pas des
        #    phrases — un decoupage en phrases ne les retrouve jamais.
        # La normalisation resout les deux ; le contenant garde sa phrase BRUTE
        # comme preuve, pour rester relisible.
        norm_src = _norm_words(self.source)

        transferts = []      # (position normalisee, contenant, phrase de preuve)
        for m in self._VESSEL_TRANSFER.finditer(self.source):
            npos = len(_norm_words(self.source[:m.start()]))
            transferts.append((npos, " ".join(m.group(1).split()),
                               " ".join(m.group(0).split())))
        if not transferts:
            return 0

        # Une SEPARATION sort la matiere de son recipient : apres une filtration
        # ou un lavage, le produit n'est plus dans la bombe. Propager au-dela
        # ecrivait « sechage a l'etuve sous vide, contenant = acid digestion
        # bomb » — une contradiction qu'un chimiste releve aussitot. La chaine
        # reprend au transfert suivant, s'il y en a un.
        _SORTIE = {"washing", "filtration", "separation", "centrifugation",
                   "rinsing", "decantation", "drying"}
        n = 0
        sorti = False
        for op in sorted(self.operations, key=lambda o: o.get("order") or 0):
            if (op.get("type") or "").strip().lower() in _SORTIE:
                sorti = True
            if op.get("vessel_name") or op.get("vessel"):
                continue
            cit = _norm_words(op.get("citation") or "")
            if len(cit) < 20:
                continue
            pos = norm_src.find(cit[:60])
            if pos < 0:
                continue
            idx = pos + len(cit)
            # Dernier transfert jusqu'a la phrase de l'etape INCLUSE : un
            # contenant nomme DANS sa propre phrase la concerne d'abord elle
            # (« placed in an alumina crucible and calcined »).
            courant = [t for t in transferts if t[0] <= idx]
            # Apres une sortie de recipient, seul un transfert POSTERIEUR a la
            # separation peut redonner un contenant : sinon la matiere n'est
            # plus nulle part de connu, et on s'abstient.
            if sorti and courant and courant[-1][0] < idx - len(cit):
                continue
            if not courant:
                # Aucun transfert AVANT cette etape. `prepara` (1957) decrit ses
                # nacelles apres coup : sa phrase arrive en position 5198 quand
                # toutes les etapes citees sont entre 1420 et 4879. Si le papier
                # ne nomme QU'UN SEUL contenant, l'ambiguite est nulle et il
                # vaut pour la voie entiere ; des qu'il y en a deux, on ne
                # devine pas lequel et on s'abstient.
                uniques = {t[1].lower() for t in transferts}
                if len(uniques) != 1:
                    continue
                courant = transferts
            _, vessel, phrase = courant[-1]
            # `vessel` est deja un ALIAS de `crucible_material` dans
            # `step_schema.py`, champ reserve a certains types d'etape : la
            # valeur etait donc SUPPRIMEE sur un `mixing` ou un `washing`.
            # `vessel_name` n'est mappe nulle part et suit le meme chemin que sa
            # preuve — il atterrit dans `other_parameters`, sans toucher au
            # schema du graphe.
            op["vessel_name"] = vessel
            op["vessel_citation"] = phrase.strip()
            n += 1
        if n:
            logger.info(f"  [vessel] contenant attribue a {n} operation(s)")
        return n

    # Operations qui TIENNENT la matiere : sans recipient, elles ne sont pas
    # executables. Un sechage peut se faire a l'air libre, un broyage au mortier
    # (deja un contenant en soi) — pour celles-la le trou est « recommande ».
    _VESSEL_REQUIS = {"heating", "cooling", "calcination", "annealing", "soak",
                      "melting", "sintering", "quenching", "combustion",
                      "hydrothermal", "solvothermal", "dissolution", "mixing"}

    # « 300 and 400 °C for core-shell and homogenous nanoparticles,
    # RESPECTIVELY » : une phrase, DEUX syntheses. Le premier nombre n'a pas
    # d'unite a lui — c'est le motif meme.
    _VARIANTES_RE = re.compile(
        r"(\d+(?:[.,]\d+)?)\s*(?:,\s*|\s+(?:and|or|et|ou)\s+)"
        r"(\d+(?:[.,]\d+)?)\s*(?:°\s*C|℃|\bC\b|\bh\b|\bhours?\b|\bmin\b)", re.I)
    # Le marqueur « respectively » et l'appariement a des PRODUITS nommes font
    # la difference avec une PLAGE (« between 1.5 and 4.3 V », cyclage de
    # batterie) ou avec trois bains distincts (« pH to 10, 9, 8 », cbd_mnse),
    # ou l'abstention est la bonne reponse et une declaration serait fausse.
    _VARIANTES_MARQUEUR = re.compile(r"\brespectively\b", re.I)

    def _declarer_variantes_non_extraites(self) -> int:
        """Signale qu'une phrase enoncait N conditions et qu'UNE seule est sortie.

        Ce n'est pas une invention — la valeur retenue est reelle et prouvee.
        C'est une recette PARTIELLE presentee comme complete, plus insidieuse
        qu'une valeur fausse : un chimiste croit qu'il n'y a qu'une synthese.

        MESURE (21/08) : 9 phrases du corpus portent une unite partagee, une
        SEULE est operatoire avec « respectively ». Scinder les voies — un
        changement de representation — ne se justifie pas pour un cas isole. On
        DECLARE le trou, ce que le projet fait de tout ce qui manque.
        """
        n = 0
        for op in self.operations:
            if op.get("_variante_non_extraite"):
                continue
            cit = op.get("citation") or ""
            if not cit or not self._VARIANTES_MARQUEUR.search(cit):
                continue
            m = self._VARIANTES_RE.search(cit)
            if not m:
                continue
            vues = [float(m.group(1).replace(",", ".")),
                    float(m.group(2).replace(",", "."))]
            retenue = op.get("temperature_c", op.get("target_temperature_c"))
            if retenue is None:
                retenue = op.get("duration_h")
            if retenue is None:
                continue
            # La valeur retenue doit VENIR de l'enumeration : sinon la phrase
            # ne decrit pas la variante de cette etape.
            autres = [v for v in vues if abs(v - float(retenue)) > 1e-6]
            if len(autres) != 1:
                continue
            op["_variante_non_extraite"] = f"{autres[0]:g}"
            n += 1
        if n:
            logger.info(f"  [variante] {n} condition(s) alternative(s) DECLAREE(S) "
                        f"non extraite(s)")
        return n

    def _declare_missing_vessels(self) -> int:
        """Un contenant absent est DECLARE, jamais passe sous silence.

        Demande de Terry (20/08). Sans cela, un chimiste ne distingue pas
        « aucun recipient necessaire » de « on n'a pas su le trouver » — et la
        regle du projet est explicite : « un trou n'est jamais comble, il est
        declare » (`normalize_steps`). Le trou remonte dans `missing_parameters`,
        d'ou l'aval cree le noeud `MissingParameter` relie au protocole
        (REQUIRES_CLARIFICATION) et a l'etape (MISSING_PARAM).
        """
        n = 0
        for op in self.operations:
            if op.get("vessel_name") or op.get("vessel"):
                continue
            if _VESSEL_ONLY_RE.search(str(op.get("equipment") or "")):
                continue                      # le modele l'a cite lui-meme
            stype = (op.get("type") or "").strip().lower()
            op.setdefault("_missing_vessel",
                          "required" if stype in self._VESSEL_REQUIS
                          else "recommended")
            n += 1
        if n:
            logger.info(f"  [vessel] contenant DECLARE MANQUANT sur {n} operation(s)")
        return n

    # L'oxygene, l'hydrogene, le carbone et l'azote sont partout : ils
    # n'IDENTIFIENT personne. Pour une cible CuO, le carbonate d'ammonium
    # partage l'oxygene et serait servi a tort. On exige un element DISTINCTIF.
    _ELEMENTS_BANALS = frozenset({"O", "H", "C", "N"})

    @staticmethod
    def _formule_de_la_cible(libelle: str):
        """Formule chimique cachee dans un LIBELLE de cible.

        Les cibles ne sont pas des formules mais des phrases lisibles :
        « Na3P (particules) », « nanoparticules de CoSi (coeur-coquille a
        300 °C) », « MoS2 (mono- et few-layer, sur graphene) ». Aucune ne se
        decompose telle quelle — l'inference par formule cible ne pouvait donc
        JAMAIS se declencher, alors qu'elle fonctionnait en test.

        Gardes : un candidat doit COMMENCER par une majuscule (sinon
        « particules » passerait pour un compose) et porter soit un chiffre,
        soit au moins deux elements distincts. On rend le candidat le plus
        riche, pas le premier venu.
        """
        try:
            from synthgraph.validation.deterministic import parse_composition
        except Exception:  # noqa: BLE001
            return None
        direct = parse_composition(libelle or "")
        if direct:
            return direct
        meilleur = None
        for tok in re.findall(r"[A-Z][A-Za-z0-9()\u00b7.]*", libelle or ""):
            comp = parse_composition(tok)
            if not comp:
                continue
            if len(comp) < 2 and not re.search(r"\d", tok):
                continue        # « P » seul, « Na » seul : trop peu pour cibler
            if meilleur is None or len(comp) > len(meilleur):
                meilleur = comp
        return meilleur

    def _infer_ratios_from_target_formula(self) -> int:
        """« Stoichiometric amounts » + formule cible enoncee -> rapports.

        DECISION DE TERRY (21/08) : deduire un rapport d'une formule ECRITE est
        une LECTURE, pas une invention — meme famille que les deux inferences
        deja en place. Le ratio porte `ratio_source` pour qu'un audit separe
        toujours ce qui a ete LU de ce qui a ete CALCULE.

        Cas de reference, `broyage_na` : « Stoichiometric amounts of metallic
        sodium and red phosphorus ... to obtain Na3P particles ». Aucune masse,
        aucune mole — mais le rapport 3:1 est entierement determine.

        Quatre conditions, sinon abstention :
          - le mot « stoichiometric » figure dans la source (la preuve que les
            proportions suivent la formule) ;
          - la formule cible se decompose ;
          - chaque precurseur retenu apporte UN element DISTINCTIF de la cible,
            et un seul precurseur par element (sinon on ne sait pas repartir) ;
          - au moins DEUX precurseurs servis : un « 1 » solitaire sans son
            partenaire est trompeur, pas informatif.
        """
        if not re.search(r"stoechiom|stoichiom|st\u0153chiom", self.source, re.I):
            return 0
        try:
            from synthgraph.validation.deterministic import parse_composition
        except Exception:  # noqa: BLE001 — une inference ne doit jamais planter
            return 0
        cible = self._formule_de_la_cible(self.target or "")
        if not cible:
            return 0
        # Une cible NON STOECHIOMETRIQUE (Na0.67[Fe0.5Mn0.5]O2) ne se deduit
        # pas : ses indices fractionnaires ne donnent aucun rapport entier.
        if any(abs(float(v) - round(float(v))) > 1e-6 for v in cible.values()):
            return 0
        distinctifs = {e: n for e, n in cible.items()
                       if e not in self._ELEMENTS_BANALS}
        if not distinctifs:
            return 0

        par_element: dict[str, list] = {}
        for pr in self.precursors:
            if pr.get("molar_ratio") is not None:
                continue
            comp = parse_composition(pr.get("formula") or "")
            if not comp:
                continue
            porte = [e for e in comp if e in distinctifs]
            if len(porte) != 1:
                continue            # aucun element cible, ou plusieurs : ambigu
            par_element.setdefault(porte[0], []).append(pr)

        # Deux precurseurs pour le meme element : impossible de repartir.
        servis = {e: v[0] for e, v in par_element.items() if len(v) == 1}
        if len(servis) < 2 or any(len(v) > 1 for v in par_element.values()):
            return 0
        for e, pr in servis.items():
            pr["molar_ratio"] = float(distinctifs[e])
            pr["ratio_source"] = "formule_cible"
        logger.info(f"  [ratios] {len(servis)} ratio(s) deduit(s) de la formule "
                    f"cible {self.target}")
        return len(servis)

    # « ball-milled during 2 min at 20 Hz » : le regime en tours/min ne couvre
    # pas un broyeur vibrant. Les kHz appartiennent aux ultrasons, autre
    # colonne — d'ou la frontiere negative.
    _FREQ_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*Hz\b", re.I)
    _FREQ_KHZ = re.compile(r"\d+(?:[.,]\d+)?\s*kHz\b", re.I)
    _TYPES_BROYAGE = ("grinding", "ball_milling")

    @staticmethod
    def _type_canonique(brut: str) -> str:
        """Type d'operation ramene au vocabulaire du REGISTRE.

        Le modele ecrit le type comme le papier : « ball-milled », donc
        « ball-milling » avec un trait d'union. Ma liste ne connaissait que
        « ball milling » avec une espace, et la recuperation de frequence ne se
        declenchait JAMAIS — alors qu'elle passait ses tests, ecrits sur les
        types DEJA normalises. On passe donc par la table `SYNONYMS` du
        registre, qui est la source unique de cette taxonomie.
        """
        t = re.sub(r"[\-_]+", " ", (brut or "").strip().lower())
        try:
            from synthgraph.schemas.step_schema import SYNONYMS
        except Exception:  # noqa: BLE001
            return t.replace(" ", "_")
        return SYNONYMS.get(t, SYNONYMS.get(t.replace(" ", "_"),
                                            t.replace(" ", "_")))
    # « -1.3 V/Ag/Ag+ », « -0.8 V vs SCE » : un potentiel ne veut rien dire sans
    # son electrode de reference.
    _POTENTIEL_RE = re.compile(
        r"(-?\d+(?:[.,]\d+)?)\s*V\s*(?:/|vs\.?\s*)\s*"
        r"([A-Za-z][A-Za-z0-9/+\-]{1,12})", re.I)
    _POTENTIEL_NU = re.compile(r"(-?\d+(?:[.,]\d+)?)\s*V\b(?!\w)")
    # La VOLTAMMETRIE mesure, elle ne prescrit pas : les potentiels de pic du
    # papier electro_nico (-0,50 / -0,59 / -0,94 V) sont de la caracterisation.
    _VOLTAMMETRIE = re.compile(
        r"\b(?:voltammetr\w*|voltammogram\w*|cv\b|peak|oxidation|reduction\s+of|"
        r"onset|open\s+circuit)\b", re.I)

    def _recover_parametres_procede(self) -> int:
        """Frequence de broyage et potentiel de depot, depuis la citation.

        Colonnes ajoutees au registre le 21/08 (decision de Terry) que RIEN ne
        remplissait : une colonne inatteignable ne vaut pas mieux qu'une colonne
        absente. Recuperation DETERMINISTE, comme la concentration et le pH —
        deux mesures ont etabli que tout ajout a l'interface du MODELE se paie
        ailleurs.

        Chaque grandeur est restreinte aux operations ou elle a un SENS : une
        frequence n'appartient qu'a un broyage, un potentiel qu'a une
        electrodeposition. Sans cette restriction, les potentiels de pic releves
        en voltammetrie cyclique — de la caracterisation — passeraient pour des
        consignes de depot.
        """
        n = 0
        for op in self.operations:
            cit = op.get("citation") or ""
            if not cit:
                continue
            typ = self._type_canonique(op.get("type"))

            if typ in self._TYPES_BROYAGE and op.get("frequency_hz") is None:
                # « 40 kHz » est la frequence d'un bain a ultrasons : on retire
                # ces occurrences avant de chercher les Hz.
                sans_khz = self._FREQ_KHZ.sub(" ", cit)
                m = self._FREQ_RE.search(sans_khz)
                if m:
                    op["frequency_hz"] = float(m.group(1).replace(",", "."))
                    op["frequency_hz_source"] = "citation_regex"
                    n += 1
                    logger.info(f"  [procede] {op['frequency_hz']:g} Hz deduit "
                                f"de la citation")

            if typ == "electrodeposition" and op.get("voltage_v") is None:
                if self._VOLTAMMETRIE.search(cit):
                    self.rejections.append(
                        "potentiel ecarte : la citation releve une VOLTAMMETRIE, "
                        "pas une consigne de depot")
                    continue
                m = self._POTENTIEL_RE.search(cit)
                if m:
                    op["voltage_v"] = float(m.group(1).replace(",", "."))
                    op["reference_electrode"] = m.group(2)
                    op["voltage_v_source"] = "citation_regex"
                    n += 1
                    logger.info(f"  [procede] {op['voltage_v']:g} V/"
                                f"{m.group(2)} deduit de la citation")
        if n:
            logger.info(f"  [procede] {n} parametre(s) de procede recupere(s)")
        return n

    def _quantite_adjacente(self, precurseur: dict, nombre: str,
                            unite: str) -> bool:
        """La quantite est-elle ACCOLEE au compose dans le texte SOURCE ?

        Le modele attache souvent au precurseur une phrase qui le NOMME sans le
        doser. Sur `hydro_czts` c'est la phrase de purete — « CuCl2 · 2H2O,
        ZnCl2 ... were of analytical grade » — tandis que les millimoles sont
        dans la phrase suivante. Les quatre rapports molaires du papier etaient
        ainsi perdus, alors qu'un chimiste peut peser sans hesiter.

        On elargit la preuve au texte, PAS la credulite : meme regle
        d'ADJACENCE que pour les concentrations. « 2 mmol CuCl2 · 2H2O » prouve
        le 2 du chlorure de cuivre ; un « 2 mmol » situe trois composes plus
        loin ne prouve rien. Et le nombre doit toujours porter SON UNITE — sans
        quoi le « 2 » de « 2H2O » suffirait, defaut reel deja corrige.
        """
        f = precurseur.get("formula") or ""
        # TOUTES les occurrences, pas seulement la premiere : sur `hydro_czts`
        # le compose est d'abord nomme dans la phrase de PURETE, en position 0,
        # loin de toute quantite. La mention DOSEE arrive plus loin. Ne
        # regarder que la premiere condamnait la recherche d'avance.
        norm, cle = _norm_words(self.source), _norm_words(f)
        positions, i = [], (norm.find(cle) if cle else -1)
        while i >= 0:
            positions.append(i)
            i = norm.find(cle, i + 1)
        if not positions:
            pos = _position_du_compose(f, self.source)   # repli par le NOM
            if pos < 0:
                return False
            positions = [pos]
        motif = rf"(?<![\d.]){re.escape(nombre)}\s*{re.escape(unite)}\b"
        for m in re.finditer(motif, self.source, re.I):
            # Positions comparees dans le MEME espace normalise, comme partout.
            q = len(_norm_words(self.source[:m.start()]))
            if any(0 <= pos - q <= 14 for pos in positions):
                return True
        return False

    # « with a molar ratio of 1:1 », « (molar ratio LiI:KI 0.63:0.37) » : le
    # rapport ECRIT EN TOUTES LETTRES, la formulation la plus explicite qu'un
    # papier puisse donner.
    _RATIO_ENONCE = re.compile(
        r"\b(?:molar\s+ratio|mole\s+ratio|stoichiometric\s+ratio|ratio\s+of)"
        r"[^.]{0,60}?(\d+(?:[.,]\d+)?(?:\s*:\s*\d+(?:[.,]\d+)?)+)", re.I)

    def _infer_ratios_from_enonce(self) -> int:
        """Rapport molaire ENONCE dans la source, pas dans la citation.

        Sur `electro_nico`, le modele declare `ratio = 1` pour l'ethylamine ET
        pour l'acide nitrique — les BONNES valeurs — mais attache la phrase des
        REACTIFS, qui ne porte aucun rapport. Les deux sont donc ecartes, et le
        papier reste a 0 % de ratios, le plus faible du corpus. Le rapport est
        pourtant dans la phrase voisine : « ... with a MOLAR RATIO OF 1:1 ».

        Aucun des trois mecanismes existants ne lisait un rapport ENONCE :
        l'un lit une enumeration, l'autre des quantites pesees, le troisieme
        deduit d'une formule cible.

        GARDES : le nombre de termes doit egaler le nombre de precurseurs sans
        rapport, et l'ordre suit celui des composes dans la phrase quand elle
        les nomme. Sans correspondance exacte, abstention — repartir au hasard
        fabriquerait des proportions.
        """
        if not self.source:
            return 0
        sans = [p for p in self.precursors if p.get("molar_ratio") is None]
        if len(sans) < 2:
            return 0
        for ph in re.split(r"(?<=[.;])\s+", self.source):
            ph = " ".join(ph.split())
            if not (20 < len(ph) < 340):
                continue
            m = self._RATIO_ENONCE.search(ph)
            if not m:
                continue
            termes = [float(x.replace(",", ".")) for x in
                      re.split(r"\s*:\s*", m.group(1))]
            # Apparier les termes aux composes que LA PHRASE NOMME, pas a tous
            # les precurseurs sans rapport. Sur `electro_nico`, la phrase
            # « mixing ethylamine and nitric acid with a molar ratio of 1:1 »
            # ne concerne QUE ces deux-la ; les chlorures de nickel et de
            # cobalt, sans rapport ici, faisaient echouer un comptage global et
            # rendaient le mecanisme INERTE.
            nommes = [(pos, pr) for pr in sans
                      for pos in (_position_du_compose(pr["formula"], ph),)
                      if pos >= 0]
            if len(nommes) != len(termes):
                continue                 # on ne sait pas repartir : abstention
            # L'ordre suit celui des composes DANS LA PHRASE.
            ordonnes = [pr for _, pr in sorted(nommes, key=lambda t: t[0])]
            for pr, val in zip(ordonnes, termes):
                pr["molar_ratio"] = val
                pr["ratio_source"] = "ratio_enonce"
            logger.info(f"  [ratios] {len(termes)} ratio(s) lus d'un ENONCE : "
                        f"{m.group(1)}")
            return len(termes)
        return 0

    def _infer_ratios_from_amounts(self) -> int:
        """Quantites molaires citees -> rapports molaires.

        Sur `hydro_czts` le modele releve « 2 mmol / 2 mmol / 1 mmol / 4 mmol » :
        dans une meme reaction ces nombres SONT les rapports molaires, mais ils
        atterrissaient dans `amount` et la mesure affichait 0 % de ratios alors
        qu'un chimiste peut peser sans ambiguite.

        Trois garde-fous, sinon on s'abstient :
          - unites MOLAIRES uniquement (mmol/mol). Des grammes exigeraient les
            masses molaires, donc une inference — interdit.
          - une seule et meme unite pour tous les composes retenus.
          - la quantite doit etre PROUVEE par la citation du precurseur ; le
            champ `amount` n'est pas verifie a l'enregistrement.
        Une plage (« 0-3 mmol ») ne donne aucun nombre unique : ignoree.
        """
        cands, unites = [], set()
        for p in self.precursors:
            if p.get("molar_ratio") is not None:
                continue
            m = self._AMOUNT_RE.match(str(p.get("amount") or ""))
            if not m:
                continue
            val = float(m.group(1).replace(",", "."))
            unite = m.group(2)
            # La citation doit porter le nombre AVEC SON UNITE. Chercher le seul
            # chiffre est un piege : sur `hydro_czts` la citation attachee etait
            # la phrase de purete (« were of analytical grade »), sans aucune
            # quantite — et le « 2 » trouve venait de « 2H2O » dans la formule.
            # Deux ratios avaient ainsi ete inscrits sur une preuve inexistante.
            if not (re.search(rf"(?<![\d.]){re.escape(m.group(1))}\s*{unite}\b",
                              p.get("citation") or "", re.I)
                    or self._quantite_adjacente(p, m.group(1), unite)):
                continue
            unites.add(unite.lower().rstrip("es"))
            cands.append((p, val))

        if len(cands) < 2 or len(unites) != 1:
            return 0
        for p, val in cands:
            p["molar_ratio"] = val
            p["ratio_source"] = "amount_molaire"
        logger.info(f"  [ratios] {len(cands)} ratio(s) deduit(s) de quantites "
                    f"molaires citees ({unites.pop()})")
        return len(cands)

    # --- cles STRUCTURELLES : des etiquettes, pas des valeurs mesurees.
    _CLES_NON_MESUREES = {"citation", "order", "type", "step_type", "step_name",
                          "operation", "other_parameters"}

    @classmethod
    def _valeurs_mesurees(cls, op: dict) -> dict:
        """Ce que l'etape AFFIRME du protocole, debarrasse des etiquettes.

        `other_parameters` est aplati car il porte de vraies valeurs
        (`cooling_rate_c_per_h`), mais ses cles techniques prefixees par « _ »
        (`_missing_vessel`, pose par la declaration de trous) n'en sont pas :
        deux etapes identiques recevaient « required » et « recommended » selon
        leur type, ce qui aurait suffi a les faire passer pour differentes.
        """
        vides = (None, "", [], {})
        vals = {k: v for k, v in op.items()
                if k not in cls._CLES_NON_MESUREES
                and not str(k).startswith("_")
                and not k.endswith("_source") and v not in vides}
        for k, v in (op.get("other_parameters") or {}).items():
            if not str(k).startswith("_") and v not in vides:
                vals[f"other.{k}"] = v
        return vals

    @classmethod
    def _type_final(cls, brut: str) -> str:
        """Le type tel que le GRAPHE le verra, pas celui que le modele a ecrit.

        Diagnostic du 22/08 : en production l'etape portait « settling », que
        le registre ignore. `normalize_steps` en fait un `generic` — mais plus
        tard. Mes tests, ecrits sur les JSON deja normalises, voyaient donc
        `generic` la ou le mecanisme voyait `settling`, et la fusion ne se
        declenchait jamais. Exactement le piege de la regle 2.

        On ne touche pas a `_type_canonique` : la deduplication par EGALITE
        (add_operation) s'en sert pour comparer des types entre eux, et y
        rabattre tous les inconnus sur `generic` les rendrait fusionnables
        entre eux. On derive ici du registre, sans en recopier la table.
        """
        t = cls._type_canonique(brut)
        try:
            from synthgraph.schemas.step_schema import STEP_PARAMETERS
        except Exception:  # noqa: BLE001
            return t
        return t if t in STEP_PARAMETERS else "generic"

    def _fusionner_gestes_dupliques(self):
        """UN geste ne doit pas devenir TROIS etapes.

        Mesure du 22/08 : `combu_ferrite` sort TROIS calcinations (600 C, 4 h),
        toutes citant la meme phrase. Un chimiste lisant ce graphe calcinerait
        12 h au lieu de 4 — la recette est materiellement fausse.

        INVISIBLE A LA METRIQUE : le gold n'enregistre pas de liste d'etapes,
        seulement des VALEURS. Une calcination triplee fournit trois fois 600 et
        trois fois 4 ; la comparaison ensembliste ne voit rien. Quatrieme defaut
        structurel que le score au gold ne peut pas attraper.

        REGLE VOLONTAIREMENT ETROITE — 14 etapes du corpus partagent une
        citation et NEUF de ces cas sont corrects :
          - la ligne « 1300C -> (8C/h) 900C -> RT » decrit bien un chauffage ET
            un refroidissement : types differents, on ne touche pas ;
          - les paliers de `physrev` (900 / 1000 / 1100 C, 24 / 60 / 60 h)
            portent des valeurs DISTINCTES : le sous-ensemble echoue, on ne
            touche pas. C'est ce discriminant, et non le type, qui protege la
            recette sequentielle que le CLAUDE.md demande de preserver.

        On absorbe donc une etape seulement si sa citation est CONTENUE dans
        celle d'une autre, qu'elle n'apporte AUCUNE valeur que l'autre n'ait
        deja, et que leurs types concordent — ou que la sienne soit `generic`,
        c'est-a-dire qu'elle n'affirme meme pas de quel geste il s'agit.
        """
        if len(self.operations) < 2:
            return
        absorbees = set()
        for i, a in enumerate(self.operations):
            if i in absorbees:
                continue
            ca = (a.get("citation") or "").strip()
            if not ca:
                continue
            va = self._valeurs_mesurees(a)
            ta = self._type_final(a.get("type") or a.get("operation") or "")
            for j, b in enumerate(self.operations):
                if i == j or j in absorbees:
                    continue
                cb = (b.get("citation") or "").strip()
                if not cb or ca not in cb:
                    continue
                # citations EGALES : ne retirer que la seconde, jamais les deux.
                if ca == cb and j < i:
                    continue
                vb = self._valeurs_mesurees(b)
                tb = self._type_final(b.get("type") or b.get("operation") or "")
                propres = {k: v for k, v in va.items()
                           if k not in vb or vb[k] != v}
                if propres:
                    logger.info(f"  [doublon?] etape {a.get('order')} ({ta}) incluse "
                                f"dans {b.get('order')} ({tb}) mais GARDEE : valeurs "
                                f"propres {sorted(propres)}")
                    continue
                if ta != tb and ta != "generic":
                    logger.info(f"  [doublon?] etape {a.get('order')} ({ta}) incluse "
                                f"dans {b.get('order')} ({tb}) mais GARDEE : types "
                                f"incompatibles")
                    continue
                absorbees.add(i)
                logger.info(f"  [doublon] etape {a.get('order')} ({ta}) absorbee "
                            f"par {b.get('order')} ({tb}) : meme geste, "
                            f"aucune valeur propre")
                break
        if not absorbees:
            return
        self.operations = [o for k, o in enumerate(self.operations)
                           if k not in absorbees]
        for n, op in enumerate(self.operations, start=1):
            op["order"] = n
        self._order = len(self.operations)

    def to_pathways_dict(self) -> dict:
        self._completer_hydrate()
        self._recover_concentrations()
        self._recover_ph()
        self._recover_parametres_procede()
        self._infer_ratios_from_enumeration()
        self._infer_ratios_from_amounts()
        self._infer_ratios_from_enonce()
        # EN DERNIER : une quantite PESEE prime toujours sur un rapport
        # deduit de la formule. La deduction ne sert que les composes
        # qu'aucune des deux precedentes n'a pu servir.
        self._infer_ratios_from_target_formula()
        self._recover_workup_steps()
        self._preparation_en_tete()
        self._recover_atmosphere()
        self._recover_solvents()
        self._recover_washing_details()
        self._recover_vessel_per_step()
        # Appele SEPAREMENT : `_recover_vessel_per_step` sort des qu'aucun
        # contenant n'est nomme dans le papier — or c'est precisement le cas ou
        # le trou doit etre declare.
        self._declare_missing_vessels()
        self._declarer_variantes_non_extraites()
        self._fusionner_gestes_dupliques()
        self._fix_sequence()
        """Produit la structure `pathways` attendue par l'Architecte Graphe,
        afin de réutiliser tel quel tout l'aval (Cypher, QA, MissingParameter)."""
        from synthgraph.schemas.step_schema import normalize_steps

        # TRACABILITE des etapes. Le normaliseur ne garde que les colonnes du
        # registre : `duration_h_source`, `temperature_c_source` et
        # `frequency_hz_source` etaient donc effaces, et la voie finale ne disait
        # plus si une valeur avait ete LUE chez le modele ou RECUPEREE par
        # post-traitement. Les precurseurs, eux, gardaient bien leur
        # `ratio_source` — l'exigence de Terry etait tenue pour les ratios et
        # perdue pour les etapes.
        # `other_parameters` figure dans les cles STRUCTURELLES preservees :
        # on y route les marqueurs plutot que d'ajouter une colonne `_source`
        # a chacun des vingt-huit types d'operation.
        for _op in self.operations:
            _marqueurs = {k: v for k, v in _op.items()
                          if k.endswith("_source") and v is not None}
            if _marqueurs:
                _op.setdefault("other_parameters", {}).update(_marqueurs)

        normalized, missing = normalize_steps(self.operations)
        # Les plages min/max ne sont posees QUE par `normalize_steps` : la
        # condition optimale, qui doit tomber dans ces bornes, ne peut donc etre
        # appliquee qu'ensuite. On lui passe la liste NORMALISEE sans toucher a
        # `self.operations` — la remplacer effacait les marqueurs de contenant
        # manquant, portes par les etapes d'origine.
        self._recover_condition_optimale(normalized)
        for st in normalized:
            st["step_name"] = f"{st.get('type', 'step')}_{st.get('order', '')}"

        # Les trous de CONTENANT sont ajoutes ici, apres normalisation : porte
        # par l'etape, le marqueur serait filtre comme l'a ete `vessel` (alias
        # de `crucible_material`, reserve a certains types d'etape). On le lit
        # donc sur les operations d'origine et on le verse dans la liste des
        # trous, structure identique a celle de `normalize_steps`.
        for op in self.operations:
            sev = op.get("_missing_vessel")
            if not sev:
                continue
            missing.append({"step_order": op.get("order"),
                            "step_type": op.get("type"),
                            "parameter": "vessel", "unit": None,
                            "severity": sev})

        for op in self.operations:
            alt = op.get("_variante_non_extraite")
            if not alt:
                continue
            missing.append({"step_order": op.get("order"),
                            "step_type": op.get("type"),
                            "parameter": f"variante_non_extraite ({alt})",
                            "unit": None, "severity": "recommended"})

        pathway = {
            "target_material": {"name": self.target, "formula": self.target},
            "synthesis_route": self.method_type,
            "variant_id": getattr(self, "sample_id", None) or "v1",
            "precursors": self.precursors,
            "synthesis_steps": normalized,
            "missing_parameters": missing,
            "missing_info": [],
        }
        return {
            "pathways": [pathway] if (self.precursors or normalized) else [],
            "reasoning": "",
            "confidence": 0.8 if normalized else 0.3,
            "route_id": self.route_id,
            "method_type": self.method_type,
            "extraction_notes": (f"tool-calling ({len(normalized)} etapes, "
                                 f"{len(self.precursors)} precurseurs, "
                                 f"{len(missing)} params manquants, "
                                 f"{len(self.rejections)} appel(s) refuse(s))"),
        }


# ==============================================================================
#  SCHÉMAS OpenAI-compatibles exposés au modèle
# ==============================================================================

TOOL_SCHEMAS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "add_precursor",
            "description": ("Enregistre UN reactif ou solvant de la synthese. "
                            "La citation doit etre une phrase copiee mot pour mot du "
                            "texte, et doit nommer ce compose."),
            "parameters": {
                "type": "object",
                "properties": {
                    "formula": {"type": "string",
                                "description": "Formule ou nom exact tel qu'ecrit dans le texte"},
                    "citation": {"type": "string",
                                 "description": "Phrase EXACTE du texte mentionnant ce compose"},
                    "molar_ratio": {"type": "number",
                                    "description": "Proportion molaire si elle est ecrite dans la citation"},
                    "amount": {"type": "string", "description": "Quantite telle qu'ecrite (ex: '2 mmol')"},
                    "role": {"type": "string", "enum": ["reactant", "solvent", "flux"],
                             "description": "flux = agent de croissance en exces (ex: SrCl2)"},
                },
                "required": ["formula", "citation"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_operation",
            "description": ("Ajoute UNE etape de synthese avec TOUS ses parametres. "
                            "Chaque valeur numerique doit apparaitre dans la citation, "
                            "sinon l'appel est refuse."),
            "parameters": {
                "type": "object",
                "properties": {
                    "step_type": {"type": "string",
                                  "description": "mixing, grinding, heating, soak, cooling, "
                                                 "calcination, washing, drying, quenching..."},
                    "citation": {"type": "string",
                                 "description": "Phrase ou LIGNE DE TABLEAU exacte decrivant cette etape"},
                    "order": {"type": "integer", "description": "Rang de l'etape (1, 2, 3...)"},
                    "temperature_c": {"type": "number"},
                    "duration_h": {"type": "number"},
                    "ramp_rate_c_per_h": {"type": "number"},
                    "cooling_rate_c_per_h": {"type": "number"},
                    "atmosphere": {"type": "string",
                                   "description": "air, Ar, N2, O2, vacuum, H2..."},
                    "atmosphere_citation": {
                        "type": "string",
                        "description": "Phrase EXACTE prouvant l'atmosphere, si elle "
                                       "n'est pas dans la citation principale (souvent "
                                       "dans le texte courant alors que les valeurs "
                                       "sont dans un tableau)"},
                    "equipment": {"type": "string"},
                    # Champ LIBRE (choix de Terry, 20/08) : les papiers portent
                    # des grandeurs qu'aucune liste anticipee ne contiendrait.
                    # Mesure sur le corpus : le pH n'apparait que sur 2 papiers
                    # mais y decide la phase obtenue (« At pHs of 11 and 10 the
                    # MnSeO4 structure was observed »), et la CONCENTRATION est
                    # presente sur 7 papiers sur 8 sans avoir de colonne.
                    # Dictionnaire PLAT et non tableau d'objets : un 8B produit
                    # mal le JSON imbrique, et l'empreinte sur l'interface doit
                    # rester minimale (cf. l'effondrement mesure au durcissement
                    # du prompt).
                    # Expose au modele SEULEMENT si l'interrupteur est arme —
                    # voir `EXPOSER_EXTRA_PARAMETERS` plus bas. La validation
                    # reste active dans tous les cas : si le champ revient, il
                    # obeit deja a la regle d'or.
                    **({"extra_parameters": {
                        "type": "object",
                        "description": ("Autres parametres CHIFFRES de cette etape, "
                                        "tels que le papier les nomme — ex. "
                                        "{\"pH\": \"10\", \"concentration\": \"0.001 M\"}. "
                                        "Chaque valeur doit figurer dans ta citation."),
                    }} if os.environ.get("SYNTHGRAPH_EXTRA_PARAMS") == "1" else {}),
                },
                "required": ["step_type", "citation"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "finalize_route",
            "description": ("Cloture la voie de synthese. A appeler UNE SEULE FOIS, "
                            "quand tous les precurseurs et toutes les etapes sont enregistres."),
            "parameters": {
                "type": "object",
                "properties": {
                    "target": {"type": "string", "description": "Materiau vise"},
                    "method_type": {"type": "string", "description": "Methode de synthese"},
                    "sample_id": {"type": "string",
                                  "description": "Identifiant d'echantillon si le papier en donne un "
                                                 "(ex: Sr214#1)"},
                },
                "required": [],
            },
        },
    },
]

TOOL_NAMES = {t["function"]["name"] for t in TOOL_SCHEMAS}
