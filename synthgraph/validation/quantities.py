# -*- coding: utf-8 -*-
"""quantities.py — [V4.18] Extraction DÉTERMINISTE des ratios molaires et rendements.

Décision Terry (2026-07-19) : la représentation canonique des quantités est le
RATIO MOLAIRE des précurseurs (normalisé au plus petit), la quantité brute
(`amount_raw`) n'étant gardée qu'en appui. Le rendement expérimental est extrait
quand le papier le donne. Règle d'or inchangée : tout vient d'un motif textuel
dans une citation DÉJÀ ANCRÉE ou dans le texte source — jamais d'invention ;
si rien n'est parsable, les champs restent absents.

Sources de ratio (par priorité) :
  1. ratio explicite  — « molar ratio of 4:6 », « Cu/Zn/Sn at 2:2:1 », « 1.1:1:2 »
  2. moles directes   — « 2 mmol », « 1.5 mmol », « (2.3 mmol) »
  3. masse → moles    — « 63.2 mg » + formule lisible (masses atomiques)
  4. molarité×volume  — « 0.5 M ... 50 cm3 », « 30 mM »+« 15 mL »
  5. déclaré           — « equimolar » (1:1), « stoichiometric amounts »
     (ratio = composition de la cible, ratio_source='stoichiometric_declared')
"""
from __future__ import annotations

import re

from synthgraph.validation.deterministic import normalize_compound_name

# Masses atomiques (g/mol) — éléments usuels des synthèses inorganiques
ATOMIC_MASS = {
    "H": 1.008, "Li": 6.94, "B": 10.81, "C": 12.011, "N": 14.007, "O": 15.999,
    "F": 18.998, "Na": 22.99, "Mg": 24.305, "Al": 26.982, "Si": 28.085,
    "P": 30.974, "S": 32.06, "Cl": 35.45, "K": 39.098, "Ca": 40.078,
    "Ti": 47.867, "V": 50.942, "Cr": 51.996, "Mn": 54.938, "Fe": 55.845,
    "Co": 58.933, "Ni": 58.693, "Cu": 63.546, "Zn": 65.38, "Ga": 69.723,
    "Ge": 72.63, "As": 74.922, "Se": 78.971, "Br": 79.904, "Rb": 85.468,
    "Sr": 87.62, "Y": 88.906, "Zr": 91.224, "Nb": 92.906, "Mo": 95.95,
    "Ru": 101.07, "Rh": 102.906, "Pd": 106.42, "Ag": 107.868, "Cd": 112.414,
    "In": 114.818, "Sn": 118.71, "Sb": 121.76, "Te": 127.6, "I": 126.904,
    "Cs": 132.905, "Ba": 137.327, "La": 138.905, "Ce": 140.116, "Nd": 144.242,
    "Sm": 150.36, "Gd": 157.25, "W": 183.84, "Re": 186.207, "Ir": 192.217,
    "Pt": 195.084, "Au": 196.967, "Hg": 200.592, "Pb": 207.2, "Bi": 208.98,
}

_MOL_UNITS = {"mol": 1.0, "mmol": 1e-3, "µmol": 1e-6, "umol": 1e-6, "nmol": 1e-9}
_MASS_UNITS = {"kg": 1000.0, "g": 1.0, "mg": 1e-3, "µg": 1e-6, "ug": 1e-6}
_VOL_UNITS = {"l": 1.0, "ml": 1e-3, "cm3": 1e-3, "cm³": 1e-3, "µl": 1e-6, "ul": 1e-6}

_NUM = r"(\d+(?:[.,]\d+)?)"


def molar_mass(formula: str) -> float | None:
    """Masse molaire d'une formule simple (hydrates « ·xH2O » inclus).
    None si un symbole est illisible — jamais d'estimation.

    [Étape A] Si `formula` est un nom en prose (« cobalt(II) chloride »)
    plutôt qu'une formule, tente `normalize_compound_name` avant de conclure
    à l'illisibilité. Limite connue : le parseur ci-dessous ne gère pas les
    groupes parenthésés avec multiplicateur (ex. Sr(NO3)2, Zn(CH3COO)2) — le
    repli ne débloque donc que les formules normalisées sans parenthèses
    (Si, CoCl2, LiI, KI, ...)."""
    if not formula:
        return None
    direct = _molar_mass_direct(formula)
    if direct is not None:
        return direct
    normalized = normalize_compound_name(formula)
    if normalized and normalized != formula:
        return _molar_mass_direct(normalized)
    return None


def _molar_mass_direct(formula: str) -> float | None:
    """Corps original de `molar_mass` (parsing direct, sans normalisation)."""
    if not formula:
        return None
    total = 0.0
    # hydrates : SrCl2·6H2O, CuCl2.2H2O
    parts = re.split(r"[·•.]\s*(?=\d*H2O)", formula.strip())
    for part in parts:
        m_hyd = re.match(r"^(\d+)?(H2O)$", part.replace(" ", ""))
        mult = 1.0
        body = part
        if m_hyd:
            mult = float(m_hyd.group(1) or 1)
            body = "H2O"
        tokens = re.findall(r"([A-Z][a-z]?)(\d*\.?\d*)", body.replace(" ", ""))
        if not tokens:
            return None
        consumed = "".join(t[0] + t[1] for t in tokens)
        if consumed != re.sub(r"[()\s]", "", body):
            return None  # parenthèses/dopage complexes → illisible, pas d'estimation
        for sym, count in tokens:
            if sym not in ATOMIC_MASS:
                return None
            total += mult * ATOMIC_MASS[sym] * (float(count) if count else 1.0)
    return total if total > 0 else None


def _to_float(s: str) -> float:
    return float(s.replace(",", "."))


def _name_position(text: str, name: str) -> int:
    """Position de la mention de `name` (nom OU token significatif) dans `text`.
    -1 si absent."""
    if not name or not text:
        return -1
    low, ln = text.lower(), name.lower()
    i = low.find(ln)
    if i != -1:
        return i
    for tok in re.findall(r"[a-z0-9]{3,}", ln):
        i = low.find(tok)
        if i != -1:
            return i
    return -1


# Motifs de quantité (moles directes, masse, molarité) avec leur position — sert
# à apparier CHAQUE précurseur à la quantité la plus proche de son nom quand
# plusieurs partagent une citation « 63.2 mg Si (2.3 mmol), 194.8 mg CoCl2 … ».
_QTY_RE = re.compile(_NUM + r"\s*(mmol|µmol|umol|nmol|mol|mg|µg|ug|kg|g)\b", re.IGNORECASE)


def _nearest_moles(text: str, name: str, formula: str | None) -> tuple[float, str] | None:
    """Quantité en moles la plus proche de la mention de `name` dans `text`.
    Préfère une mole DIRECTE (mmol/mol) proche à une masse : la conversion
    masse→mole suppose masse molaire + hydratation + pureté, moins fiable."""
    pos = _name_position(text, name)
    if pos == -1:
        return moles_from_text(text, formula)  # nom absent : 1re quantité
    direct, direct_d = None, 1e9   # mmol/mol
    indirect, indirect_d = None, 1e9  # masse / M×V
    for m in _QTY_RE.finditer(text):
        got = moles_from_text(m.group(0), formula)
        if not got:
            continue
        d = abs(m.start() - pos)
        is_direct = bool(re.search(r"mol\b", m.group(0), re.IGNORECASE))
        if is_direct and d < direct_d:
            direct, direct_d = got, d
        elif not is_direct and d < indirect_d:
            indirect, indirect_d = got, d
    # mole directe raisonnablement proche (≤ 60 chars) prime sur la masse
    if direct and direct_d <= 60:
        return direct
    return indirect or direct or moles_from_text(text, formula)


def moles_from_text(text: str, formula: str | None = None) -> tuple[float, str] | None:
    """Cherche une quantité convertible en moles dans un fragment de texte.
    Renvoie (moles, motif_source) ou None. Priorité : moles > masse > M×V."""
    if not text:
        return None
    low = text.lower()
    m = re.search(_NUM + r"\s*(mmol|µmol|umol|nmol|mol)\b", low)
    if m:
        return _to_float(m.group(1)) * _MOL_UNITS[m.group(2)], m.group(0)
    m = re.search(_NUM + r"\s*(mg|µg|ug|kg|g)\b", low)
    if m:
        mm = molar_mass(formula or "")
        if mm:
            grams = _to_float(m.group(1)) * _MASS_UNITS[m.group(2)]
            return grams / mm, m.group(0)
        return None
    m = re.search(_NUM + r"\s*m?M\b", text)  # 0.5 M / 30 mM (casse significative)
    if m:
        conc = _to_float(m.group(1)) * (1e-3 if m.group(0).rstrip("M").rstrip().endswith("m") else 1.0)
        v = re.search(_NUM + r"\s*(ml|cm3|cm³|µl|ul|l)\b", low)
        if v:
            return conc * _to_float(v.group(1)) * _VOL_UNITS[v.group(2)], f"{m.group(0)} × {v.group(0)}"
    return None


def explicit_ratio(text: str) -> tuple[list[float], str] | None:
    """Ratio explicite « 2:2:1 » / « 4:6 » / « 1.1:1:2 » (≥2 termes)."""
    if not text:
        return None
    m = re.search(r"(\d+(?:\.\d+)?(?:\s*:\s*\d+(?:\.\d+)?){1,5})", text)
    if m and (":" in m.group(1)):
        vals = [float(x) for x in re.split(r"\s*:\s*", m.group(1))]
        if all(v > 0 for v in vals):
            return vals, m.group(0)
    return None


def normalize_ratio(moles: list[float]) -> list[float]:
    """Normalise au plus petit terme non nul, arrondi lisible (2 décimales)."""
    base = min(v for v in moles if v > 0)
    return [round(v / base, 2) for v in moles]


def annotate_pathway_quantities(pathway: dict, source_text: str = "") -> dict:
    """Annote les précurseurs d'un pathway : amount_raw, moles, molar_ratio.

    Déterministe et fail-safe : un précurseur sans motif reste sans ratio.
    ratio_source ∈ {'explicit', 'per_precursor_moles', 'equimolar_declared',
    'stoichiometric_declared'} — posé au niveau du pathway."""
    precs = [p for p in (pathway.get("precursors") or []) if isinstance(p, dict)]
    if not precs:
        return pathway
    low_src = (source_text or "").lower()

    # 1. ratio explicite dans une citation de précurseur ou le texte proche
    for p in precs:
        r = explicit_ratio(p.get("citation") or "")
        if r and len(r[0]) == len(precs):
            for prec, val in zip(precs, r[0]):
                prec["molar_ratio"] = val
                prec["ratio_provenance"] = r[1]
            pathway["ratio_source"] = "explicit"
            return pathway

    # 2. moles par précurseur — la quantité doit être celle ACCOLÉE au nom du
    # précurseur (fenêtre centrée sur sa mention), pas la 1re du texte partagé.
    moles, hits = [], 0
    src_clean = re.sub(r"\s+", " ", (source_text or "")).lower()

    def _amount_grounded(amount: str) -> bool:
        """Règle d'or : le champ `amount` (produit par le LLM) n'est cru que si sa
        quantité chiffrée existe dans le texte source (« 2 mmol » présent au papier).
        Sinon on l'ignore — pas d'invention."""
        m = _QTY_RE.search(amount or "")
        if not m:
            return False
        num, unit = m.group(1), m.group(2).lower()
        # variantes d'écriture : « 2 mmol », « 2mmol », « 2 mmol of »
        return bool(re.search(rf"{re.escape(num)}\s*{re.escape(unit)}\b", src_clean))

    for p in precs:
        name = p.get("name") or p.get("formula") or ""
        formula = p.get("formula") or name
        # [Étape A] Traçabilité : si le nom verbatim (NuExtract, prose) se
        # normalise vers une formule, on le note SANS écraser `name`/`formula`
        # (le graphe garde le verbatim ET la formule).
        norm = normalize_compound_name(formula) if formula else None
        if norm and norm != formula:
            p["formula_normalized"] = norm
        cite = p.get("citation") or ""
        amt = p.get("amount") or ""
        # [V4.18] le LLM place souvent la quantité dans son champ dédié `amount`
        # (« 2 mmol ») plutôt que dans la citation (= nom du réactif). On l'utilise
        # SEULEMENT si elle est ancrée dans le texte source (règle d'or), sinon
        # on retombe sur la citation ancrée.
        got = None
        if _amount_grounded(amt):
            got = moles_from_text(amt, formula)
        if not got:
            got = _nearest_moles(cite, name, formula)
        if got:
            p["amount_raw"] = got[1]
            moles.append(got[0]); hits += 1
        else:
            moles.append(0.0)
    if hits >= 2:
        with_m = [v for v in moles if v > 0]
        norm = normalize_ratio(moles) if all(v > 0 for v in moles) else None
        for i, p in enumerate(precs):
            if moles[i] > 0:
                p["moles"] = round(moles[i], 8)
                if norm:
                    p["molar_ratio"] = norm[i]
        pathway["ratio_source"] = "per_precursor_moles" if norm else "partial_moles"
        return pathway

    # 3. déclarations textuelles (preuve = le mot est dans la source)
    if "equimolar" in low_src or "equal molar" in low_src:
        for p in precs:
            p["molar_ratio"] = 1.0
        pathway["ratio_source"] = "equimolar_declared"
    elif "stoichiometric" in low_src:
        pathway["ratio_source"] = "stoichiometric_declared"  # ratio = formule cible
    return pathway


def extract_yield(source_text: str) -> tuple[float, str] | None:
    """Rendement expérimental : « yield of 96.7% », « yield around 90% »…
    Renvoie (pourcentage, citation courte) ou None."""
    if not source_text:
        return None
    m = re.search(
        r"yield(?:ed|s)?\s*(?:of|was|is|around|about|:)?\s*[~≈]?\s*"
        r"(\d{1,3}(?:\.\d+)?)\s*%", source_text, re.IGNORECASE)
    if m:
        pct = float(m.group(1))
        if 0 < pct <= 100:
            i = max(0, m.start() - 60)
            return pct, source_text[i:m.end()].strip()[-100:]
    return None
