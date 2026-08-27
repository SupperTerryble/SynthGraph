#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Les quatre passes de verification, importees par `verifier_golds.py`.

Separees du socle pour que chaque passe se lise d'une traite : c'est leur
INDEPENDANCE qui fait leur valeur. Aucune des six erreurs d'annotation commises
sur ce corpus n'aurait ete prise par une seule d'entre elles.
"""
from __future__ import annotations

import re

from tools.verifier_golds import (  # noqa: E402
    DUREE, NON_SYNTHESE, REFERENCE, REGIME_BATTERIE, TEMP, VESSEL_FR_EN,
    VERBE_OPERATOIRE, _ecritures, _operatoire, _present, _valeurs, phrases)
from synthgraph.extraction.graph_tools import (  # noqa: E402
    _composition_key, _compound_named_in, _enumerated_by_name,
    _enumerated_compound, _norm_words)
from synthgraph.validation.deterministic import parse_composition  # noqa: E402


# ----------------------------------------------------------------------
#  PASSE 1 — SOURCAGE : tout ce que le gold affirme est-il ECRIT ?
# ----------------------------------------------------------------------
def passe1_sourcage(cle, gold, txt, rb, rap):
    n = _norm_words(txt)
    for c in gold.get("citations") or []:
        if _norm_words(c) in n or rb._greedy_cover(_norm_words(c)):
            rap.ok()
        else:
            rap.erreur(cle, 1, f"citation introuvable : {c[:70]!r}")

    for champ in ("key_values", "durations_h", "ramp_rates_c_per_h"):
        est_duree = champ == "durations_h"
        for v in _valeurs(gold, champ):
            if any(_present(txt, e) for e in _ecritures(v, est_duree)):
                rap.ok()
            else:
                # Cas de la RAMPE CONVERTIE : 300 degres/h absent du texte,
                # 5 degres/min present. C'est mon erreur no 4.
                indice = ""
                if champ.startswith("ramp") and _present(txt, f"{v / 60:g}"):
                    indice = (f" — mais {v / 60:g} l'est : conversion "
                              f"par minute vers par heure INVENTEE ?")
                rap.erreur(cle, 1, f"{champ}={v:g} n'est ecrit nulle part{indice}")

    # ATMOSPHERE : c'est ici que TROIS de mes erreurs se sont logees, l'« air »
    # ayant ete deduit du procede plutot que lu dans le texte.
    atm = gold.get("atmosphere") or ""
    # Un gold qui DECLARE l'atmosphere absente du texte n'affirme rien : son
    # champ explique pourquoi, et y lire le mot « air » comme une affirmation
    # inverse le sens. Memes marqueurs que le comparateur.
    if any(m in atm.lower() for m in ("non precisee", "non précisée", "autogene",
                                      "autogène", "presume", "présumé",
                                      "inference", "inférence")):
        atm = ""
    if atm:
        gaz = [g for g in ("argon", "ar", "air", "n2", "nitrogen", "o2", "02",
                           "oxygen", "vacuum", "vide", "h2", "hydrogen", "co2",
                           "nh3", "sccm")
               if re.search(rf"\b{g}\b", atm, re.I)]
        if not gaz:
            rap.signale(cle, 1, f"atmosphere sans gaz nommable : {atm[:60]!r}")
        # « 02 » avec un ZERO : les PDF scannes confondent O et 0, et PhysRevB
        # (1994) ecrit « heated in flowing 02 ». Le pipeline replie deja ces
        # confusables ; le verificateur doit admettre la meme equivalence,
        # sinon il accuse un gold JUSTE.
        elif any(re.search(rf"\b{g}\b", txt, re.I)
                 or re.search(rf"\b{g.replace('o', '0')}\b", txt, re.I)
                 for g in gaz):
            rap.ok()
        else:
            rap.erreur(cle, 1, f"atmosphere INFEREE : aucun de {gaz} n'apparait "
                               f"dans le texte")

    for pr in gold.get("precursors") or []:
        f = pr.get("formula") or ""
        if not f:
            rap.erreur(cle, 1, "precurseur sans formule")
        # ENUMERATION A PREFIXE IMPLICITE : « strontium oxide, carbonate,
        # nitrate or hydroxide » nomme SrCO3, Sr(NO3)2 et Sr(OH)2 sans
        # qu'aucun n'apparaisse en toutes lettres. Le pipeline le sait.
        elif (_norm_words(f) in n or rb._greedy_cover(_norm_words(f))
              or _compound_named_in(f, txt)
              or _enumerated_compound(f, txt)
              or _enumerated_by_name(f, txt)):
            rap.ok()
        else:
            rap.erreur(cle, 1, f"precurseur {f} introuvable dans le texte")


# ----------------------------------------------------------------------
#  PASSE 2 — COMPLETUDE : le texte porte-t-il des valeurs OUBLIEES ?
# ----------------------------------------------------------------------
def passe2_completude(cle, gold, txt, rap):
    """Cinquieme erreur : les 5 min de dispersion d'`hydro_czts`, simplement
    oubliees. Une passe de sourcage ne peut pas voir un OUBLI — elle ne
    controle que ce que le gold contient deja."""
    attendues_T = set(_valeurs(gold, "key_values"))
    attendues_d = set(_valeurs(gold, "durations_h"))
    vues_T, vues_d = {}, {}
    for ph in phrases(txt):
        if not (20 < len(ph) < 400):
            continue
        if not _operatoire(ph):
            continue
        if REFERENCE.search(ph):
            continue
        for m in TEMP.finditer(ph):
            v = float(m.group(1).replace(",", "."))
            if -273 < v < 3000 and not REGIME_BATTERIE.search(ph):
                vues_T.setdefault(v, ph)
        for m in DUREE.finditer(ph):
            v = float(m.group(1).replace(",", "."))
            h = round(v / 60.0, 4) if m.group(2).lower().startswith("min") else v
            vues_d.setdefault(h, ph)

    for v, ph in sorted(vues_T.items()):
        if v not in attendues_T:
            rap.signale(cle, 2, f"temperature {v:g} C en phrase operatoire, "
                                f"absente du gold : {ph[:78]!r}")
    for v, ph in sorted(vues_d.items()):
        if v not in attendues_d:
            rap.signale(cle, 2, f"duree {v:g} h en phrase operatoire, absente "
                                f"du gold : {ph[:78]!r}")


# ----------------------------------------------------------------------
#  PASSE 3 — ATTRIBUTION : la valeur appartient-elle a CETTE synthese ?
# ----------------------------------------------------------------------
def passe3_attribution(cle, gold, txt, rap):
    """Piege de `broyage_na` : « 900 C for 12 h in air » est bien dans le
    texte, mais decrit un AUTRE compose, produit ailleurs et cite par
    reference. Une passe de sourcage l'accepterait sans broncher."""
    # Une ligne de TABLEAU est longue par nature — celle de `crystal` fait
    # 496 caracteres et porte les HUIT sequences thermiques du papier. Un
    # plafond a 400 l'excluait, et la passe accusait alors un gold juste de
    # citer hors contexte operatoire.
    phs = [p for p in phrases(txt) if 20 < len(p) < 1400]
    for champ, est_duree in (("key_values", False), ("durations_h", True)):
        for v in _valeurs(gold, champ):
            porteuses = [p for p in phs
                         if any(_present(p, e) for e in _ecritures(v, est_duree))]
            if not porteuses:
                continue                       # deja signale par la passe 1
            operatoires = [p for p in porteuses if _operatoire(p)]
            if operatoires:
                rap.ok()
            else:
                rap.signale(cle, 3, f"{champ}={v:g} n'apparait que HORS contexte "
                                    f"operatoire : {porteuses[0][:78]!r}")


# ----------------------------------------------------------------------
#  PASSE 4 — COHERENCE : le gold se contredit-il lui-meme ?
# ----------------------------------------------------------------------
def passe4_coherence(cle, gold, txt, rap):
    for champ in ("key_values", "durations_h", "ramp_rates_c_per_h"):
        vals = _valeurs(gold, champ)
        if len(vals) != len(set(vals)):
            doubles = sorted({v for v in vals if vals.count(v) > 1})
            rap.erreur(cle, 4, f"{champ} contient des DOUBLONS : {doubles}")
        else:
            rap.ok()

    cible = _composition_key(gold.get("target") or "")
    elem_cible = set(dict(cible)) if cible else set()
    for pr in gold.get("precursors") or []:
        f = pr.get("formula") or ""
        role = (pr.get("role") or "reactant").lower()
        comp = parse_composition(f) if f else None
        if f and comp is None:
            rap.signale(cle, 4, f"formule non decomposable : {f!r}")
        elif comp and elem_cible and role == "reactant":
            if set(comp) & elem_cible:
                rap.ok()
            else:
                rap.signale(cle, 4, f"{f} declare 'reactant' n'apporte AUCUN "
                                    f"element de la cible "
                                    f"{gold.get('target')!r} — flux ou solvant "
                                    f"mal etiquete ?")
        r = pr.get("molar_ratio")
        if r is not None:
            if not isinstance(r, (int, float)) or r <= 0:
                rap.erreur(cle, 4, f"{f} : molar_ratio invalide ({r!r})")
            elif _present(txt, f"{float(r):g}"):
                rap.ok()
            else:
                # Sixieme erreur : des MILLIMOLES ecrites dans un champ de
                # rapport molaire, alors que le papier enonce le rapport.
                rap.signale(cle, 4, f"{f} : molar_ratio={float(r):g} n'est pas "
                                    f"ecrit tel quel (deduit ? a tracer)")

    if not (gold.get("citations") or []):
        rap.erreur(cle, 4, "aucune citation : le gold n'est adosse a rien")
    for c in gold.get("citations") or []:
        if len(c.strip()) < 25:
            rap.erreur(cle, 4, f"citation trop courte pour rien prouver : {c!r}")

    lav = gold.get("washing")
    if lav and not re.search(r"\b(wash\w*|rins\w*|lav\w*|clean\w*|centrifug\w*|"
                             r"filtr\w*|filter\w*|decant\w*)\b",
                             txt, re.I):
        rap.erreur(cle, 4, "un lavage est annote, le texte n'en parle pas")

    ves = gold.get("vessel")
    if ves:
        mots = []
        for w in re.findall(r"[a-zA-Zéèêàûîô]{4,}", ves):
            b = (w.lower().replace("é", "e").replace("è", "e")
                 .replace("ê", "e").replace("à", "a").replace("û", "u"))
            if b in ("dans", "avec", "pour", "contenant", "puis", "sous"):
                continue
            mots.append(VESSEL_FR_EN.get(b, b))
        if mots and not any(re.search(rf"\b{re.escape(w[:6])}", txt, re.I)
                            for w in mots):
            rap.signale(cle, 4, f"contenant annote sans appui textuel evident : "
                                f"{ves[:60]!r}")
