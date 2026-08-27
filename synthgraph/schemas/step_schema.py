"""
synthgraph/schemas/step_schema.py — SynthGraph V4.4

Registre CANONIQUE des types d'étapes de synthèse et normalisation.

Choix de conception validé (B/B) :
  - Les traitements thermiques sont des types SÉPARÉS et NOMMÉS
    (heating / soak / cooling / quenching / calcination / sintering / annealing),
    PAS un unique "thermal_treatment" avec un champ dwell+purpose.
  - Chaque palier / rampe / refroidissement est une ÉTAPE DISTINCTE.

Chaque type possède des colonnes STRICTES (required + optional) avec des UNITÉS FIXES.
`normalize_steps()` projette chaque étape brute sur les colonnes strictes de son type,
convertit les unités vers l'unité canonique, et remplit `missing_parameters`.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Optional

logger = logging.getLogger("SynthGraph.StepSchema")


# ==============================================================================
#  REGISTRE CANONIQUE — colonnes strictes + unités fixes par type
#  unit = None  → champ catégoriel / texte (pas de conversion)
# ==============================================================================

STEP_PARAMETERS: dict[str, dict[str, dict[str, Optional[str]]]] = {
    # --- Opérations mécaniques / préparation ---
    "mixing": {
        "required": {},
        "optional": {"method": None, "medium": None, "duration_h": "h",
                     "speed_rpm": "rpm", "atmosphere": None, "equipment": None,
                     "temperature_c": "°C"},
    },
    "grinding": {
        "required": {},
        # `atmosphere` MANQUAIT ici alors que `ball_milling` et `mixing` l'ont —
        # et `ball_milling` se canonicalise justement en `grinding`. Un broyage
        # en boite a gants sous argon est un cas courant (broyage_na, sodium
        # metallique), et l'atmosphere y etait retrogradee en parametre annexe.
        "optional": {"method": None, "medium": None, "duration_h": "h",
                     "speed_rpm": "rpm", "ball_to_powder_ratio": None,
                     "equipment": None, "temperature_c": "°C",
                     "frequency_hz": "Hz", "atmosphere": None},
    },
    # [B4 - Étape B quick win] Broyage mécanique à haute énergie — distinct de
    # "grinding" (mortier manuel) : constaté à l'audit, dégradé en "mixing" sans
    # BPR/vitesse/atmosphère (89 cas d'opérations dégradées).
    "ball_milling": {
        "required": {},
        # La FREQUENCE est la consigne du broyeur vibrant : « ball-milled
        # during 2 min at 20 Hz » (Retsch MM400, selfondu_cosi). Le
        # regime en tours/min ne la couvre pas.
        "optional": {"duration_h": "h", "speed_rpm": "rpm",
                     "ball_to_powder_ratio": None, "atmosphere": None,
                     "temperature_c": "°C", "frequency_hz": "Hz"},
    },
    "ultrasonication": {
        "required": {},
        "optional": {"duration_h": "h", "temperature_c": "°C", "frequency_khz": "kHz"},
    },
    "centrifugation": {
        "required": {},
        "optional": {"speed_rpm": "rpm", "duration_h": "h"},
    },
    "spin_coating": {
        "required": {},
        "optional": {"speed_rpm": "rpm", "duration_h": "h"},
    },
    "electrodeposition": {
        "required": {},
        # `voltage_v` existait deja. Un potentiel ne veut rien dire sans
        # son ELECTRODE DE REFERENCE : -1,3 V/Ag/Ag+ n'est pas -1,3 V/ECS.
        # Le papier electro_nico montre que -1,1 / -1,2 / -1,3 V donnent
        # 11, 23 et 48 at% de cobalt : c'est LA consigne du depot.
        "optional": {"voltage_v": "V", "current_ma": "mA", "duration_h": "h",
                     "reference_electrode": None, "temperature_c": "°C"},
    },
    "deposition_cycle": {
        "required": {},
        "optional": {"pulse_sequence": None, "n_cycles": "count", "temperature_c": "°C"},
    },
    "pressing": {
        "required": {},
        "optional": {"pressure_mpa": "MPa", "duration_min": "min",
                     "die_diameter_mm": "mm", "shape": None,
                     "min_pressure_mpa": "MPa", "max_pressure_mpa": "MPa"},
    },
    "dissolution": {
        "required": {"solvent": None},
        "optional": {"concentration_mol_l": "mol/L", "temperature_c": "°C", "duration_h": "h"},
    },

    # --- Traitements thermiques (types SÉPARÉS, choix B) ---
    "heating": {   # rampe de MONTÉE vers une consigne
        "required": {"target_temperature_c": "°C"},
        "optional": {"ramp_rate_c_per_h": "°C/h", "duration_h": "h",
                     "atmosphere": None, "equipment": None,
                     "min_temperature_c": "°C", "max_temperature_c": "°C",
                     # `heating` pouvait porter une plage de TEMPERATURE mais
                     # pas de DUREE : sur `hydro_czts`, « conducted at 170°C to
                     # 190°C for 6 to 16 h » gardait 170-190 °C et perdait le
                     # « 6 » de la plage horaire (durees a 33 %).
                     "min_duration_h": "h", "max_duration_h": "h"},
    },
    "soak": {      # palier / maintien isotherme (dwell)
        "required": {"temperature_c": "°C", "duration_h": "h"},
        "optional": {"atmosphere": None, "equipment": None,
                     "min_temperature_c": "°C", "max_temperature_c": "°C",
                     "min_duration_h": "h", "max_duration_h": "h"},
    },
    "calcination": {
        "required": {"temperature_c": "°C", "duration_h": "h"},
        "optional": {"ramp_rate_c_per_h": "°C/h", "atmosphere": None, "equipment": None,
                     "min_temperature_c": "°C", "max_temperature_c": "°C",
                     "min_duration_h": "h", "max_duration_h": "h"},
    },
    "sintering": {
        "required": {"temperature_c": "°C", "duration_h": "h"},
        "optional": {"ramp_rate_c_per_h": "°C/h", "pressure_mpa": "MPa",
                     "atmosphere": None, "equipment": None,
                     "min_temperature_c": "°C", "max_temperature_c": "°C",
                     "min_duration_h": "h", "max_duration_h": "h",
                     "min_pressure_mpa": "MPa", "max_pressure_mpa": "MPa"},
    },
    "annealing": {
        "required": {"temperature_c": "°C", "duration_h": "h"},
        "optional": {"ramp_rate_c_per_h": "°C/h", "atmosphere": None, "equipment": None,
                     "min_temperature_c": "°C", "max_temperature_c": "°C",
                     "min_duration_h": "h", "max_duration_h": "h"},
    },
    "cooling": {   # rampe de DESCENTE vers une consigne
        "required": {"target_temperature_c": "°C"},
        "optional": {"cooling_rate_c_per_h": "°C/h", "atmosphere": None, "equipment": None,
                     "min_temperature_c": "°C", "max_temperature_c": "°C"},
    },
    "quenching": {  # refroidissement rapide
        "required": {"quench_medium": None},
        "optional": {"from_temperature_c": "°C"},
    },
    "drying": {
        "required": {},
        "optional": {"temperature_c": "°C", "duration_h": "h", "atmosphere": None, "equipment": None},
    },

    # --- Croissance cristalline / flux ---
    "flux_growth": {
        "required": {"max_temperature_c": "°C"},
        "optional": {"flux_material": None, "crucible_material": None, "soak_time_h": "h",
                     "cooling_rate_c_per_h": "°C/h", "atmosphere": None},
    },
    "crystal_growth": {
        "required": {},
        "optional": {"method": None, "max_temperature_c": "°C", "cooling_rate_c_per_h": "°C/h",
                     "atmosphere": None, "equipment": None},
    },

    # --- Voies solution / hydrothermale ---
    "hydrothermal": {
        "required": {"temperature_c": "°C", "duration_h": "h"},
        "optional": {"solvent": None, "fill_factor_percent": "%", "vessel": None, "pressure_mpa": "MPa",
                     "min_temperature_c": "°C", "max_temperature_c": "°C",
                     "min_duration_h": "h", "max_duration_h": "h"},
    },

    # --- Dépôts en phase vapeur ---
    "cvd": {
        "required": {"temperature_c": "°C"},
        "optional": {"precursor_gas": None, "carrier_gas": None, "pressure_torr": "torr",
                     "gas_flow_sccm": "sccm", "duration_h": "h", "substrate": None,
                     "min_temperature_c": "°C", "max_temperature_c": "°C"},
    },
    "pvd": {
        "required": {},
        "optional": {"temperature_c": "°C", "pressure_torr": "torr", "power_w": "W",
                     "target_material": None, "substrate": None, "duration_h": "h"},
    },
    "ald": {
        "required": {"temperature_c": "°C"},
        "optional": {"precursor": None, "num_cycles": "count", "pulse_time_s": "s",
                     "purge_time_s": "s", "substrate": None,
                     "min_temperature_c": "°C", "max_temperature_c": "°C"},
    },

    # --- Post-traitement ---
    "washing": {
        "required": {"solvent": None},
        "optional": {"repetitions": "count", "temperature_c": "°C"},
    },
    "filtration": {
        "required": {},
        "optional": {"filter_type": None, "washing_solvent": None, "repetitions": "count"},
    },
    "separation": {
        "required": {},
        "optional": {"method": None, "solvent": None},
    },

    # --- Fallback ---
    "generic": {
        "required": {},
        # Le fourre-tout ne portait QUE `description` : toute etape que le
        # modele n'arrive pas a classer perdait chacune de ses valeurs
        # numeriques, MEME prouvees par leur citation. Cout mesure le 21/08 :
        # le 65 °C de combu_ferrite, « The solution was allowed for gel
        # formation on the magnetic stirrer at 65°C » — une phrase qui ne
        # correspond a aucun verbe du registre, donc classee `generic`, donc
        # videe. Refuser d'INVENTER est la regle du projet ; JETER ce qui est
        # prouve n'en fait pas partie. Une etape mal typee vaut mieux qu'une
        # valeur perdue : le type se corrige, la valeur ne se retrouve pas.
        "optional": {"description": None, "temperature_c": "°C",
                     "duration_h": "h", "atmosphere": None,
                     "equipment": None},
    },
}


def colonnes_numeriques() -> set[str]:
    """Toutes les colonnes du registre porteuses d'une UNITE, donc numeriques.

    La liste des colonnes soumises au controle anti-invention etait RECOPIEE a
    la main a trois endroits, pendant que ce registre vivait sa vie. Mesure du
    21/08 : DIX-NEUF colonnes numeriques y echappaient — `voltage_v`,
    `gas_flow_sccm`, `from_temperature_c`, `repetitions`... Ce n'etait pas une
    omission ponctuelle mais une derive structurelle : toute colonne ajoutee au
    registre echappait automatiquement au controle, en silence.

    Le registre est desormais la SOURCE UNIQUE. Ajouter une colonne ici la
    soumet au controle sans autre geste.
    """
    return {col
            for definition in STEP_PARAMETERS.values()
            for bloc in ("required", "optional")
            for col, unite in (definition.get(bloc) or {}).items()
            if unite is not None}


# ==============================================================================
#  [V4.5/Étape 4] PARAMÈTRES RECOMMANDÉS — optionnels dans le schéma, mais leur
#  absence compromet la REPRODUCTIBILITÉ. Chaque absence génère un nœud
#  MissingParameter (severity='recommended') visible dans Neo4j pour le chimiste.
# ==============================================================================

# ══════════════════════════════════════════════════════════════════════════
#  MINIMUM DE REFAISABILITÉ (décision de Terry, 2026-08-20)
#
#  Constat qui l'a motivée : `heating` n'exigeait que `target_temperature_c`
#  — ni durée, ni atmosphère — et `mixing` n'exigeait RIEN. Un chimiste ne peut
#  refaire ni l'un ni l'autre. Les scores élevés mesuraient donc des critères
#  trop faibles.
#
#  Ces colonnes s'ajoutent aux `required` de STEP_PARAMETERS. Tout manque
#  devient un trou DÉCLARÉ (`MissingParameter`), jamais une valeur devinée.
#  Le contenant fait exception : il est traité par
#  `RouteBuilder._declare_missing_vessels`, car il ne vit pas dans les colonnes
#  d'étape mais dans `other_parameters`.
#
#  Couche SÉPARÉE et non fusionnée dans STEP_PARAMETERS : le motif du
#  durcissement reste ainsi lisible, et réversible d'une ligne.
# ══════════════════════════════════════════════════════════════════════════
MINIMUM_REFAISABILITE: dict[str, list[str]] = {
    "heating":     ["duration_h", "atmosphere"],
    "calcination": ["atmosphere"],          # température + durée déjà requises
    "annealing":   ["atmosphere"],
    "sintering":   ["atmosphere"],
    "soak":        ["atmosphere"],
    "cooling":     ["cooling_rate_c_per_h"],
    # Un mélange sans milieu ni méthode ni durée n'est pas reproductible : on
    # exige au moins de savoir COMMENT (méthode/milieu). La durée reste
    # recommandée — beaucoup de papiers disent « thoroughly mixed » sans plus.
    "mixing":      ["method"],
    "grinding":    ["method"],
    "washing":     ["repetitions"],         # `solvent` est déjà requis
    "drying":      ["temperature_c", "duration_h"],
}


RECOMMENDED_PARAMETERS: dict[str, list[str]] = {
    "heating":     ["ramp_rate_c_per_h", "atmosphere"],
    "soak":        ["atmosphere"],
    "calcination": ["atmosphere", "ramp_rate_c_per_h"],
    "sintering":   ["atmosphere"],
    "annealing":   ["atmosphere"],
    "cooling":     ["cooling_rate_c_per_h"],
    "quenching":   ["from_temperature_c"],
    "pressing":    ["pressure_mpa"],
    "grinding":    ["duration_h"],
    "drying":      ["temperature_c", "duration_h"],
    "flux_growth": ["flux_material", "cooling_rate_c_per_h", "crucible_material"],
    "hydrothermal": ["fill_factor_percent", "vessel"],
    "cvd":         ["precursor_gas", "pressure_torr"],
}


# ==============================================================================
#  SYNONYMES — nom d'opération (LLM) → type canonique
#  Recherche par sous-chaîne (le plus spécifique d'abord).
# ==============================================================================

SYNONYMS: dict[str, str] = {
    # thermiques (montée)
    "heating up": "heating", "heat up": "heating", "ramp up": "heating",
    "ramping": "heating", "raise temperature": "heating", "heating": "heating",
    "montée": "heating", "chauffage": "heating", "heat to": "heating",
    # palier / maintien
    "dwell": "soak", "hold at": "soak", "holding": "soak", "isothermal": "soak",
    "isotherme": "soak", "soaking": "soak", "soak": "soak", "plateau": "soak",
    "palier": "soak", "maintien": "soak", "melting": "soak", "melt": "soak",
    # calcination / frittage / recuit
    "calcination": "calcination", "calcine": "calcination", "calcining": "calcination",
    "sintering": "sintering", "sinter": "sintering", "frittage": "sintering",
    "annealing": "annealing", "anneal": "annealing", "recuit": "annealing",
    # refroidissement
    "slow cooling": "cooling", "cool down": "cooling", "cooling": "cooling",
    "cool to": "cooling", "refroidissement": "cooling", "furnace cooling": "cooling",
    # trempe
    "quenching": "quenching", "quench": "quenching", "trempe": "quenching",
    # mécanique
    "ball milling": "grinding", "ball-milling": "grinding", "milling": "grinding",
    "grinding": "grinding", "grind": "grinding", "broyage": "grinding", "mortar": "grinding",
    "mixing": "mixing", "mix": "mixing", "blend": "mixing", "mélange": "mixing", "melange": "mixing",
    "pelletizing": "pressing", "pelletize": "pressing", "pressing": "pressing",
    "press": "pressing", "pastillage": "pressing", "cold pressing": "pressing",
    # solution
    "dissolution": "dissolution", "dissolve": "dissolution", "dissolving": "dissolution",
    "hydrothermal": "hydrothermal", "solvothermal": "hydrothermal", "autoclave": "hydrothermal",
    # dépôts
    "chemical vapor deposition": "cvd", "cvd": "cvd", "mocvd": "cvd",
    "physical vapor deposition": "pvd", "pvd": "pvd", "sputtering": "pvd", "pulvérisation": "pvd",
    "atomic layer deposition": "ald", "ald": "ald",
    # croissance
    "flux growth": "flux_growth", "flux method": "flux_growth", "flux": "flux_growth",
    "crystal growth": "crystal_growth", "single crystal growth": "crystal_growth",
    "growth": "crystal_growth", "czochralski": "crystal_growth",
    # post
    "washing": "washing", "wash": "washing", "rinsing": "washing", "rinse": "washing",
    "lavage": "washing", "rincage": "washing", "rinçage": "washing",
    "filtration": "filtration", "filter": "filtration", "filtering": "filtration",
    "drying": "drying", "dry": "drying", "séchage": "drying", "sechage": "drying",
    "separation": "separation", "separate": "separation", "separating": "separation",
    "crystal separation": "separation",
}


def resolve_step_type(operation: str) -> str:
    """Résout un nom d'opération libre vers un type canonique via SYNONYMS."""
    if not operation:
        return "generic"
    op = str(operation).lower().strip()
    if op in STEP_PARAMETERS:
        return op
    # correspondance exacte de synonyme
    if op in SYNONYMS:
        return SYNONYMS[op]
    # sous-chaîne (le plus long synonyme correspondant gagne)
    best = None
    for syn, canon in SYNONYMS.items():
        if syn in op and (best is None or len(syn) > len(best[0])):
            best = (syn, canon)
    return best[1] if best else "generic"


# ==============================================================================
#  ALIAS DE COLONNES — nom canonique → variantes que le LLM peut produire
# ==============================================================================

COLUMN_ALIASES: dict[str, list[str]] = {
    "target_temperature_c": ["temperature_c", "temp_c", "max_temperature_c", "target_temp_c", "temperature"],
    "temperature_c": ["target_temperature_c", "temp_c", "temperature"],
    "max_temperature_c": ["temperature_c", "target_temperature_c", "max_temp_c", "maximum_temperature_c"],
    "from_temperature_c": ["temperature_c", "target_temperature_c", "start_temperature_c"],
    "ramp_rate_c_per_h": ["heating_rate_c_per_h", "rate_c_per_h", "ramp_rate", "heating_rate"],
    "cooling_rate_c_per_h": ["rate_c_per_h", "ramp_rate_c_per_h", "cooling_rate", "cool_rate_c_per_h"],
    "duration_h": ["dwell_h", "soak_time_h", "hold_time_h", "time_h", "duration", "dwell_time_h", "dwell"],
    "soak_time_h": ["duration_h", "dwell_h", "hold_time_h", "dwell"],
    "quench_medium": ["medium", "quenching_medium"],
    "flux_material": ["flux", "flux_agent"],
    "crucible_material": ["crucible", "equipment", "vessel"],
    "concentration_mol_l": ["concentration", "molarity", "conc_mol_l"],
    "speed_rpm": ["rpm", "speed", "rotation_speed"],
    "pressure_mpa": ["pressure", "applied_pressure"],
    "pressure_torr": ["pressure"],
    "gas_flow_sccm": ["flow_rate_sccm", "gas_flow", "flow_sccm"],
    "num_cycles": ["cycles", "n_cycles", "number_of_cycles"],
    "repetitions": ["repeats", "n_washes", "times"],
    "medium": ["quench_medium", "solvent"],
    "solvent": ["medium", "washing_solvent"],
    "duration_min": ["duration", "time_min"],
}


# ==============================================================================
#  CONVERSION D'UNITÉS
# ==============================================================================

_TIME_TO_H = {
    "h": 1.0, "hr": 1.0, "hrs": 1.0, "hour": 1.0, "hours": 1.0,
    "min": 1 / 60, "mins": 1 / 60, "minute": 1 / 60, "minutes": 1 / 60,
    "s": 1 / 3600, "sec": 1 / 3600, "secs": 1 / 3600, "second": 1 / 3600, "seconds": 1 / 3600,
    "d": 24.0, "day": 24.0, "days": 24.0,
}
_TIME_TO_MIN = {k: v * 60 for k, v in _TIME_TO_H.items()}


def _parse_num_unit(raw: Any) -> tuple[Optional[float], str]:
    """Extrait (nombre, unité) d'une valeur brute (nombre, ou str type '30 min', '1273 K')."""
    if raw is None:
        return None, ""
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        return float(raw), ""
    s = str(raw).strip()
    m = re.match(r"\s*(-?\d+(?:[.,]\d+)?)\s*([a-zA-Z°µ/%]+.*)?$", s)
    if not m:
        return None, ""
    num = float(m.group(1).replace(",", "."))
    unit = (m.group(2) or "").strip().lower()
    return num, unit


def convert_value(raw: Any, target_unit: Optional[str]) -> Any:
    """Convertit une valeur brute vers l'unité canonique de la colonne.

    - target_unit None (catégoriel) → renvoie la chaîne telle quelle.
    - Sinon parse nombre+unité et convertit (temps, température, rampe...).
    """
    if raw is None:
        return None
    if target_unit is None:
        # Champ texte : renvoyer tel quel (str)
        return raw if not isinstance(raw, float) else str(raw)

    num, unit = _parse_num_unit(raw)
    if num is None:
        return None

    tu = target_unit.lower()

    # Températures → °C
    if tu == "°c":
        if unit.startswith("k"):          # Kelvin → °C
            return round(num - 273.15, 3)
        if unit.startswith("°f") or unit == "f":  # Fahrenheit → °C
            return round((num - 32) * 5 / 9, 3)
        return num

    # Durées → h
    if tu == "h":
        if unit in _TIME_TO_H:
            return round(num * _TIME_TO_H[unit], 4)
        return num  # supposé déjà en heures

    # Durées → min
    if tu == "min":
        if unit in _TIME_TO_MIN:
            return round(num * _TIME_TO_MIN[unit], 3)
        return num

    # Rampes → °C/h
    if tu == "°c/h":
        if "/min" in unit or unit.endswith("min"):
            return round(num * 60, 3)
        if "/s" in unit or unit.endswith("s"):
            return round(num * 3600, 3)
        return num  # supposé déjà en °C/h

    # Autres unités (MPa, torr, sccm, mol/L, rpm, %, mm, W, count) : nombre tel quel
    return num


# ==============================================================================
#  [B1 - Étape B quick win] RAMPES °C/min → °C/h DEPUIS LA CITATION
#  Constat audit (notes_incorrect_parameters_summary.md #1) : « heated at a rate
#  of 5 °C/min » présent dans la citation mais ramp_rate_c_per_h reste null car
#  l'extracteur ne convertit pas °C/min → °C/h. Motif tolérant à l'OCR (°, ˚, u
#  substitués au degré ; « min21 »/« min-1 » substitués à min⁻¹).
#  Preuve textuelle uniquement — motif introuvable = rien (règle d'or).
# ==============================================================================

_RATE_PER_MIN_RE = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*[°˚u]?\s*[ck]\s*(?:/\s*min|per\s*min|\s+min)"
    r"(?:\s*[-−]?\s*1|\s*21)?",
    re.IGNORECASE,
)


def _fill_ramp_rate_from_citation(norm: dict, spec: dict, citation: str) -> None:
    """[B1] Remplit ramp_rate_c_per_h / cooling_rate_c_per_h (×60) si absents
    ET si la citation contient un motif 'X °C/min' (ou variante OCR). N'écrase
    JAMAIS une valeur déjà présente."""
    if not citation:
        return
    m = _RATE_PER_MIN_RE.search(citation)
    if not m:
        return
    try:
        num = float(m.group(1).replace(",", "."))
    except (TypeError, ValueError):
        return
    rate_c_per_h = round(num * 60, 3)
    cols = {**spec["required"], **spec["optional"]}
    if "ramp_rate_c_per_h" in cols and norm.get("ramp_rate_c_per_h") is None:
        norm["ramp_rate_c_per_h"] = rate_c_per_h
        norm.setdefault("deterministic_fills", []).append(
            {"parameter": "ramp_rate_c_per_h", "value": rate_c_per_h, "source": "citation_rate_regex"})
        logger.info(f"  [B1] ramp_rate_c_per_h={rate_c_per_h} déduit de la citation "
                    f"({num}/min détecté)")
    if "cooling_rate_c_per_h" in cols and norm.get("cooling_rate_c_per_h") is None:
        norm["cooling_rate_c_per_h"] = rate_c_per_h
        norm.setdefault("deterministic_fills", []).append(
            {"parameter": "cooling_rate_c_per_h", "value": rate_c_per_h, "source": "citation_rate_regex"})
        logger.info(f"  [B1] cooling_rate_c_per_h={rate_c_per_h} déduit de la citation "
                    f"({num}/min détecté)")


# ==============================================================================
#  [B2 - Étape B quick win] PLAGES °C / h DEPUIS LA CITATION
#  Constat audit #2 : « 170°C to 190°C for 6 to 16 h » écrasé en un scalaire
#  (170.0°C, 6.0h) ; min_temperature_c/max_temperature_c/min_duration_h/
#  max_duration_h restent vides. Si la citation contient une plage ET que les
#  bornes du schéma sont null → on les remplit depuis la citation. Si un
#  scalaire existant tombe HORS de la plage détectée, on ne l'écrase pas mais
#  on flague range_mismatch=true.
# ==============================================================================

_TEMP_RANGE_RE = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*(?:[°˚]\s*c)?\s*(?:to|-|–|—|and)\s*"
    r"(\d+(?:[.,]\d+)?)\s*[°˚]\s*c",
    re.IGNORECASE,
)
_TEMP_RANGE_FR_RE = re.compile(
    r"entre\s+(\d+(?:[.,]\d+)?)\s*(?:[°˚]\s*c)?\s*et\s+"
    r"(\d+(?:[.,]\d+)?)\s*[°˚]\s*c",
    re.IGNORECASE,
)
_DUR_RANGE_RE = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*(?:to|-|–|—|and)\s*(\d+(?:[.,]\d+)?)\s*h(?:ours?|rs?)?\b",
    re.IGNORECASE,
)


def _fill_range_from_citation(norm: dict, spec: dict, citation: str, step: dict) -> None:
    """[B2] Remplit min/max_temperature_c et min/max_duration_h depuis une
    plage détectée dans la citation, si les colonnes existent pour ce type ET
    sont encore ABSENTES DE L'ÉTAPE BRUTE (`step`, pas `norm` déjà projeté :
    `max_temperature_c` a un alias vers le scalaire `temperature_c` qui le
    pré-remplirait sinon avec une valeur partielle/fausse — exactement le bug
    audit #2 qu'on corrige). Ne remplace jamais un scalaire existant ; si
    celui-ci tombe hors plage, flague range_mismatch=true (pas d'écrasement)."""
    if not citation:
        return
    cols = {**spec["required"], **spec["optional"]}

    if "min_temperature_c" in cols and "max_temperature_c" in cols:
        m = _TEMP_RANGE_RE.search(citation) or _TEMP_RANGE_FR_RE.search(citation)
        if m:
            lo, hi = sorted((float(m.group(1).replace(",", ".")),
                              float(m.group(2).replace(",", "."))))
            if step.get("min_temperature_c") is None and step.get("max_temperature_c") is None:
                norm["min_temperature_c"] = lo
                norm["max_temperature_c"] = hi
                norm.setdefault("deterministic_fills", []).append(
                    {"parameter": "min_temperature_c/max_temperature_c",
                     "value": [lo, hi], "source": "citation_range_regex"})
                logger.info(f"  [B2] plage température {lo}-{hi}°C déduite de la citation")
            for scalar_col in ("temperature_c", "target_temperature_c"):
                sval = norm.get(scalar_col)
                if sval is not None and not (lo <= sval <= hi):
                    norm["range_mismatch"] = True

    if "min_duration_h" in cols and "max_duration_h" in cols:
        m = _DUR_RANGE_RE.search(citation)
        if m:
            lo, hi = sorted((float(m.group(1).replace(",", ".")),
                              float(m.group(2).replace(",", "."))))
            if step.get("min_duration_h") is None and step.get("max_duration_h") is None:
                norm["min_duration_h"] = lo
                norm["max_duration_h"] = hi
                norm.setdefault("deterministic_fills", []).append(
                    {"parameter": "min_duration_h/max_duration_h",
                     "value": [lo, hi], "source": "citation_range_regex"})
                logger.info(f"  [B2] plage durée {lo}-{hi}h déduite de la citation")
            sval = norm.get("duration_h")
            if sval is not None and not (lo <= sval <= hi):
                norm["range_mismatch"] = True


# ==============================================================================
#  [B4 - Étape B quick win] RECLASSIFICATION DÉTERMINISTE DES OPÉRATIONS
#  Constat audit #6 (89 cas d'opérations dégradées) : ball_milling→mixing,
#  ultrasonication→mixing, centrifugation perdue... Si le type résolu est
#  générique (mixing/heating/generic) MAIS que la citation contient un mot-clé
#  discriminant sans ambiguïté, on reclasse vers le type précis. Preuve
#  textuelle uniquement — mot absent = pas de reclassement (règle d'or).
# ==============================================================================

_RECLASSIFIABLE_GENERIC_TYPES = {"mixing", "heating", "generic"}

_RECLASSIFY_PATTERNS: dict[str, "re.Pattern[str]"] = {
    "ball_milling": re.compile(r"ball[\s-]?mill", re.IGNORECASE),
    "ultrasonication": re.compile(r"ultrasonic|sonicat", re.IGNORECASE),
    "centrifugation": re.compile(r"centrifug", re.IGNORECASE),
    "spin_coating": re.compile(r"spin[\s-]?coat", re.IGNORECASE),
    "electrodeposition": re.compile(r"electrodeposit", re.IGNORECASE),
    "deposition_cycle": re.compile(r"pulse.*purge", re.IGNORECASE | re.DOTALL),
}


def _reclassify_from_citation(stype: str, citation: str) -> Optional[str]:
    """[B4] Reclasse un type générique vers un type précis si la citation
    contient un mot-clé discriminant. Renvoie None si aucun reclassement."""
    if stype not in _RECLASSIFIABLE_GENERIC_TYPES or not citation:
        return None
    for canon, pattern in _RECLASSIFY_PATTERNS.items():
        if pattern.search(citation):
            return canon
    return None


# ==============================================================================
#  NORMALISATION
# ==============================================================================

_STRUCTURAL_KEYS = {"order", "operation", "type", "citation", "raw_text_citation",
                    "details", "other_parameters", "step_name"}


def _find_raw(step: dict, col: str) -> Any:
    """Cherche la valeur d'une colonne dans l'étape (champ direct, alias, other_parameters)."""
    if step.get(col) is not None:
        return step[col]
    for a in COLUMN_ALIASES.get(col, []):
        if step.get(a) is not None:
            return step[a]
    op = step.get("other_parameters") or {}
    if isinstance(op, dict):
        if op.get(col) is not None:
            return op[col]
        for a in COLUMN_ALIASES.get(col, []):
            if op.get(a) is not None:
                return op[a]
    return None


# ==============================================================================
#  [A4 — V4.20] UNE VITESSE N'EST PAS UNE DURÉE
#  Constat gold (papier « Crystal growth ») : les séquences tabulées s'écrivent
#  « 1300 °C → (8 °C/h) → 900 °C ». Les valeurs 8 et 45 sont des VITESSES DE
#  REFROIDISSEMENT ; le pipeline les rangeait dans duration_h, produisant des
#  paliers fantômes de 8 h et 45 h. Un chimiste qui suit ce protocole attend
#  8 heures au lieu de refroidir à 8 °C/h : la recette devient irréalisable.
#  Défense déterministe : une valeur brute portant une unité de TAUX ne peut
#  jamais alimenter un champ de durée ; elle est redirigée vers le champ de
#  vitesse si le type d'étape en possède un, sinon abandonnée (jamais devinée).
# ==============================================================================

_DURATION_COLS = {"duration_h", "duration_min", "min_duration_h", "max_duration_h",
                  "soak_time_h", "dwell_h", "hold_time_h"}
_RATE_COLS = ("ramp_rate_c_per_h", "cooling_rate_c_per_h")

# « 8 °C/h », « 8 C/h », « 45 K/h », « 5°C h-1 », tolérant aux dégradations OCR
_RATE_UNIT_RE = re.compile(
    r"[°˚]?\s*[ckf]\s*(?:/|per\s+|\s+)\s*(?:h|hr|hour|min)\b|"
    r"[°˚]\s*[ckf]\s*h\s*[-−]?\s*1",
    re.IGNORECASE,
)


def _is_rate_value(raw: Any) -> bool:
    """La valeur brute porte-t-elle une unité de TAUX (°C/h, K/h, °C/min) ?"""
    if raw is None or isinstance(raw, (int, float)):
        return False  # un nombre nu ne porte pas d'unité : indécidable ici
    return bool(_RATE_UNIT_RE.search(str(raw)))


def _num_is_rate_in_citation(value: float, citation: str) -> bool:
    """La citation présente-t-elle CE nombre comme une VITESSE ?

    Complément indispensable à `_is_rate_value` : le LLM écrit le plus souvent
    un nombre nu (`duration_h: 8`) sans reporter l'unité. La valeur seule est
    indécidable — mais la citation, elle, porte la preuve : « (8 °C/h) ».
    Mesuré sur le gold : sans ce contrôle, 8 et 45 restaient des paliers de
    8 h et 45 h. Même principe que B1 : preuve textuelle, sinon abstention.
    """
    if not citation:
        return False
    num = f"{value:g}"
    # L'unité de température est OBLIGATOIRE, et le séparateur doit être « / »
    # ou « per » : sans cela « 24 h » (vingt-quatre heures) serait lu comme une
    # vitesse et une durée légitime disparaîtrait du graphe.
    pat = (rf"(?<![\d.]){re.escape(num)}\s*[°˚]?\s*[ckf]\s*(?:/|per\s+)\s*(?:h|hr|hour|min)\b"
           rf"|(?<![\d.]){re.escape(num)}\s*[°˚]?\s*[ckf]\s*h\s*[-−]\s*1")
    return bool(re.search(pat, citation, re.IGNORECASE))


def normalize_step(step: dict) -> dict:
    """Projette une étape brute sur les colonnes strictes de son type canonique."""
    op = step.get("operation") or step.get("type") or ""
    stype = resolve_step_type(op)
    cit = step.get("citation") or step.get("raw_text_citation") or ""

    # [B4] Reclassification déterministe AVANT projection sur les colonnes :
    # un type générique (mixing/heating/generic) mal attribué par le LLM est
    # reclassé vers son type précis si la citation contient un mot-clé
    # discriminant (preuve textuelle uniquement).
    reclassified = _reclassify_from_citation(stype, cit)
    if reclassified:
        logger.info(f"  [B4] Reclassification déterministe : '{stype}' → "
                    f"'{reclassified}' (mot-clé trouvé dans la citation, "
                    f"step order={step.get('order')})")
        stype = reclassified

    spec = STEP_PARAMETERS.get(stype, STEP_PARAMETERS["generic"])
    cols = {**spec["required"], **spec["optional"]}

    norm: dict[str, Any] = {
        "type": stype,
        "order": step.get("order"),
        "operation": op,
    }
    _rate_rescued: list[tuple[str, Any]] = []
    for col, unit in cols.items():
        raw = _find_raw(step, col)
        # [A4] Garde : une vitesse (°C/h) ne peut pas devenir une durée.
        if col in _DURATION_COLS and _is_rate_value(raw):
            logger.info(f"  [A4] '{raw}' refusé pour {col} (unité de vitesse, "
                        f"pas de durée) — step order={step.get('order')}")
            _rate_rescued.append((col, raw))
            continue
        val = convert_value(raw, unit)
        if val is not None and val != "":
            norm[col] = val

    # [A4] Récupération : si le type d'étape possède un champ de vitesse encore
    # vide, la valeur refusée y est réaffectée — sinon elle est abandonnée
    # (on ne devine jamais un champ qui n'existe pas pour ce type).
    # Nombres nus : le champ ne porte pas d'unité, mais la citation si. Une
    # durée dont la citation présente la valeur comme « N °C/h » est en fait
    # une vitesse — on la retire du champ de durée et on la redirige.
    for _dcol in list(_DURATION_COLS & set(norm)):
        _dval = norm.get(_dcol)
        if isinstance(_dval, (int, float)) and _num_is_rate_in_citation(float(_dval), cit):
            logger.info(f"  [A4] {_dcol}={_dval} retiré : la citation présente cette valeur "
                        f"comme une VITESSE — step order={step.get('order')}")
            del norm[_dcol]
            _rate_rescued.append((_dcol, f"{_dval:g} °C/h"))

    # Une valeur de taux peut aussi avoir été rangée par le LLM dans un champ
    # que ce type d'étape ne possède pas (ex. duration_h sur un 'cooling') :
    # elle n'est alors jamais visitée par la boucle ci-dessus et se perdrait
    # dans other_parameters. On la récupère ici — l'unité °C/h vaut preuve.
    if any(rc in cols and norm.get(rc) is None for rc in _RATE_COLS):
        for _k, _v_raw in step.items():
            if _k in cols or not _is_rate_value(_v_raw):
                continue
            _rate_rescued.append((_k, _v_raw))
            break

    for _col, _raw in _rate_rescued:
        for _rate_col in _RATE_COLS:
            if _rate_col not in cols or norm.get(_rate_col) is not None:
                continue  # ce type n'a pas ce champ, ou il est déjà rempli
            _v = convert_value(_raw, cols[_rate_col])
            if _v is not None and _v != "":
                norm[_rate_col] = _v
                logger.info(f"  [A4] '{_raw}' (champ '{_col}') réaffecté à {_rate_col}={_v}")
                break

    # Colonnes requises non remplies → missing (au niveau de l'étape)
    step_missing = [c for c in spec["required"] if norm.get(c) is None]
    if step_missing:
        norm["_missing_required"] = step_missing

    # Extras non mappés (traçabilité) → other_parameters
    known = set(cols) | _STRUCTURAL_KEYS | {a for al in COLUMN_ALIASES.values() for a in al}
    extras: dict[str, Any] = {}
    for k, v in step.items():
        if k not in known and v not in (None, "", {}, []):
            extras[k] = v
    for k, v in (step.get("other_parameters") or {}).items():
        if k not in cols and v not in (None, "", {}, []):
            extras[k] = v
    if extras:
        norm["other_parameters"] = extras

    if cit:
        norm["citation"] = cit
    if step.get("details"):
        norm["details"] = step["details"]

    # [B1] Rampes °C/min → °C/h et [B2] plages écrasées : preuve textuelle
    # uniquement, jamais d'écrasement d'une valeur déjà présente.
    _fill_ramp_rate_from_citation(norm, spec, cit)
    _fill_range_from_citation(norm, spec, cit, step)

    return norm


def normalize_steps(steps: list[dict]) -> tuple[list[dict], list[dict]]:
    """Normalise une liste d'étapes brutes.

    Returns:
        (normalized_steps, missing_parameters)
        - normalized_steps : chaque étape projetée sur les colonnes strictes de son type.
        - missing_parameters : liste {step_order, step_type, parameter, unit, severity}
          des colonnes REQUISES absentes (severity='required') ET des colonnes
          RECOMMANDÉES absentes (severity='recommended', cf. RECOMMENDED_PARAMETERS).
          Règle d'or SynthGraph : un trou n'est jamais comblé, il est déclaré.
    """
    normalized: list[dict] = []
    missing: list[dict] = []
    for i, step in enumerate(steps or []):
        if not isinstance(step, dict):
            continue
        norm = normalize_step(step)
        norm["order"] = norm.get("order") or (i + 1)
        stype = norm["type"]
        spec = STEP_PARAMETERS.get(stype, STEP_PARAMETERS["generic"])
        for col, unit in spec["required"].items():
            if norm.get(col) is None:
                missing.append({"step_order": norm["order"], "step_type": stype,
                                "parameter": col, "unit": unit, "severity": "required"})
        # Minimum de refaisabilite : mêmes trous « required », mais tracés par
        # leur origine pour qu'on puisse distinguer, dans le graphe comme dans
        # les mesures, ce qui relève du schéma d'origine et ce qui relève du
        # durcissement du 20/08.
        for col in MINIMUM_REFAISABILITE.get(stype, []):
            if col in spec["required"]:
                continue
            if norm.get(col) is None:
                missing.append({"step_order": norm["order"], "step_type": stype,
                                "parameter": col,
                                "unit": spec["optional"].get(col),
                                "severity": "required",
                                "origine": "minimum_refaisabilite"})
        for col in RECOMMENDED_PARAMETERS.get(stype, []):
            if col in spec["required"]:
                continue  # déjà couvert ci-dessus
            if col in MINIMUM_REFAISABILITE.get(stype, []):
                continue  # promu « required » par le durcissement : pas de doublon
            if norm.get(col) is None:
                unit = spec["optional"].get(col)
                missing.append({"step_order": norm["order"], "step_type": stype,
                                "parameter": col, "unit": unit, "severity": "recommended"})
        norm.pop("_missing_required", None)
        normalized.append(norm)
    return normalized, missing
