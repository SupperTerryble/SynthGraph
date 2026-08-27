"""
extraction_state.py — SynthGraph V4.2
State Machine Python pour l'extraction séquentielle par Tool Calling.

L'ExtractionState est l'unique source de vérité construite progressivement
par les appels d'outils de l'AgentExtracteurToolCaller.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field

# ==============================================================================
# TYPES DE CHAMPS REQUIS PAR TYPE D'ÉTAPE (Phase 2)
# Ces champs DOIVENT être remplis pour qu'une étape soit "complète".
# ==============================================================================

REQUIRED_FIELDS_BY_STEP_TYPE: Dict[str, List[str]] = {
    "heating":             ["temperature_C"],
    "calcination":         ["temperature_C"],
    "annealing":           ["temperature_C"],
    "sintering":           ["temperature_C"],
    "grinding":            [],
    "mixing":              [],
    "dissolution":         ["solvent"],
    "filtration":          [],
    "drying":              ["temperature_C"],
    "pressing":            [],
    "hydrothermal_treatment": ["temperature_C", "duration_min", "solvent"],
    "flux_growth":         ["maximum_temperature_C", "flux_material", "crucible_type"],
    "cvd_deposition":      ["temperature_C", "precursor_gas", "substrate"],
    "generic":             [],
}

OPTIONAL_FIELDS_BY_STEP_TYPE: Dict[str, List[str]] = {
    "heating":             ["duration_min", "atmosphere", "ramp_rate_C_per_min", "equipment", "cooling_protocol"],
    "calcination":         ["duration_min", "atmosphere", "ramp_rate_C_per_min", "equipment", "cooling_protocol"],
    "annealing":           ["duration_min", "atmosphere", "ramp_rate_C_per_min", "equipment", "cooling_protocol"],
    "sintering":           ["duration_min", "atmosphere", "ramp_rate_C_per_min", "equipment", "cooling_protocol"],
    "grinding":            ["duration_min", "equipment", "speed_rpm", "ball_to_powder_ratio", "medium"],
    "mixing":              ["duration_min", "speed_rpm", "solvent", "method"],
    "dissolution":         ["duration_min", "concentration_molL", "temperature_C", "solute"],
    "filtration":          ["filter_type", "washing_solvent", "repetitions"],
    "drying":              ["duration_min", "atmosphere", "equipment"],
    "pressing":            ["pressure_MPa", "duration_s", "die_diameter_mm", "shape"],
    "hydrothermal_treatment": ["vessel_type", "pressure_MPa", "fill_factor_percent"],
    "flux_growth":         ["soaking_duration_min", "cooling_rate_C_per_h", "atmosphere", "separation_method"],
    "cvd_deposition":      ["duration_min", "pressure_torr", "gas_flow_rate_sccm", "carrier_gas"],
    "generic":             ["description", "parameters"],
}

# ==============================================================================
# PHASE 1 — Template Step (Ossature de la méthode)
# ==============================================================================

STEP_TYPE = Literal[
    "heating", "calcination", "annealing", "sintering",
    "grinding", "mixing", "dissolution", "filtration",
    "drying", "pressing", "hydrothermal_treatment",
    "flux_growth", "cvd_deposition", "generic"
]


class TemplateStep(BaseModel):
    """Une étape de l'ossature de la méthode (Phase 1)."""
    step_name: str = Field(description="Identifiant unique ex: 'heating_1', 'grinding_2'")
    step_type: str = Field(description="Type d'étape parmi les types standards")
    order: int = Field(description="Position dans la séquence (1-indexed)")
    citation: str = Field(description="Extrait exact du texte source justifiant cette étape")
    description: Optional[str] = Field(default=None, description="Courte description libre")


class Phase1Template(BaseModel):
    """Résultat complet de la Phase 1 : ossature de la méthode."""
    synthesis_method: str = Field(description="Méthode globale (ex: solid_state, sol_gel, flux_growth)")
    synthesis_method_citation: str = Field(description="Citation justifiant la méthode identifiée")
    steps: List[TemplateStep] = Field(default_factory=list)
    missing_info_flags: List[str] = Field(default_factory=list, description="Informations manquantes détectées")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


# ==============================================================================
# PHASE 2 — Données remplies (Paramètres)
# ==============================================================================

class FilledValue(BaseModel):
    """Une valeur numérique ou textuelle avec citation obligatoire."""
    value: Any = Field(description="La valeur extraite")
    citation: str = Field(description="Extrait exact du texte source")
    confirmed: bool = Field(default=False, description="True si valeur a été confirmée après conflit")


class FilledStep(BaseModel):
    """Une étape avec ses paramètres remplis (Phase 2)."""
    step_name: str
    step_type: str
    fields: Dict[str, FilledValue] = Field(default_factory=dict)

    def get_required_fields(self) -> List[str]:
        return REQUIRED_FIELDS_BY_STEP_TYPE.get(self.step_type, [])

    def get_optional_fields(self) -> List[str]:
        return OPTIONAL_FIELDS_BY_STEP_TYPE.get(self.step_type, [])

    def get_missing_required(self) -> List[str]:
        return [f for f in self.get_required_fields() if f not in self.fields]

    def get_missing_optional(self) -> List[str]:
        return [f for f in self.get_optional_fields() if f not in self.fields]

    def is_complete(self) -> bool:
        return len(self.get_missing_required()) == 0


class TargetMaterial(BaseModel):
    name: str = ""
    formula: str = ""
    citation: str = ""


class Precursor(BaseModel):
    name: str
    formula: str
    role: Literal["reactant", "flux", "solvent", "dopant", "additive"] = "reactant"
    amount: Optional[str] = None   # string pour gérer "2.5 g" ou "stoichiometric"
    unit: Optional[str] = None
    citation: str


class VisionQuery(BaseModel):
    """Trace d'un appel à l'agent Vision."""
    figure_ref: str
    question: str
    answer: str
    model_used: str


# ==============================================================================
# EXTRACTION STATE — Source de vérité centrale
# ==============================================================================

class ExtractionState(BaseModel):
    """
    State Machine centrale de l'extraction V4.2.
    Construite progressivement par les appels d'outils de l'AgentExtracteur.
    """

    # Phase 1 output
    phase1_template: Optional[Phase1Template] = None

    # Phase 2 output
    target_material: Optional[TargetMaterial] = None
    precursors: List[Precursor] = Field(default_factory=list)
    filled_steps: List[FilledStep] = Field(default_factory=list)

    # Audit trail
    call_log: List[str] = Field(default_factory=list)
    vision_queries: List[VisionQuery] = Field(default_factory=list)
    phase1_call_count: int = 0
    phase2_call_count: int = 0

    # Chunk navigation
    chunks: List[str] = Field(default_factory=list, description="Liste des chunks de texte")
    current_chunk_idx: int = 0

    # ------------------------------------------------------------------ #
    # Helpers Phase 1
    # ------------------------------------------------------------------ #

    def log(self, msg: str):
        self.call_log.append(msg)

    def init_filled_steps_from_template(self):
        """Initialise les FilledStep depuis le template Phase 1 validé."""
        if not self.phase1_template:
            raise ValueError("phase1_template must be set before Phase 2")
        self.filled_steps = [
            FilledStep(step_name=s.step_name, step_type=s.step_type)
            for s in self.phase1_template.steps
        ]

    def get_filled_step(self, step_name: str) -> Optional[FilledStep]:
        for s in self.filled_steps:
            if s.step_name == step_name:
                return s
        return None

    # ------------------------------------------------------------------ #
    # Phase 2 — insert_value logic
    # ------------------------------------------------------------------ #

    def insert_value(
        self,
        step_name: str,
        field: str,
        value: Any,
        citation: str,
        confirm: bool = False,
    ) -> dict:
        """
        Insère une valeur dans une étape.
        Retourne un dict status + liste des valeurs/étapes manquantes.
        """
        step = self.get_filled_step(step_name)
        if step is None:
            return {
                "status": "error",
                "message": f"Étape '{step_name}' inconnue. Étapes disponibles: {[s.step_name for s in self.filled_steps]}",
                "missing_values": self._get_missing_summary(),
                "missing_steps":  self._get_incomplete_steps(),
            }

        existing = step.fields.get(field)

        if existing is not None and not confirm:
            # Demande de confirmation
            return {
                "status": "confirm_required",
                "message": f"Le champ '{field}' de l'étape '{step_name}' est déjà rempli. Renvoie avec confirm=true pour écraser.",
                "previous_value":    existing.value,
                "previous_citation": existing.citation,
            }

        # Conversion heures -> minutes
        if field == "duration_min":
            try:
                f_val = float(value)
                cit_low = citation.lower()
                if "hour" in cit_low or " h" in cit_low:
                    value = f_val * 60.0
                elif "sec" in cit_low or " s" in cit_low:
                    value = f_val / 60.0
                else:
                    value = f_val
            except Exception:
                pass

        # Insertion (ou écrasement confirmé)
        step.fields[field] = FilledValue(
            value=value,
            citation=citation,
            confirmed=(existing is not None),  # True si c'était un écrasement
        )

        action = "overwrite" if existing else "insert"
        self.log(f"[Phase2] {action.upper()} {step_name}.{field} = {value!r}  (citation: {citation[:60]}...)")

        return {
            "status": "ok",
            "action": action,
            "missing_values": self._get_missing_summary(),
            "missing_steps":  self._get_incomplete_steps(),
        }

    def get_state_snapshot(self) -> dict:
        """Retourne le JSON courant + flags de complétion pour l'outil get_state()."""
        missing = []
        for step in self.filled_steps:
            for field in step.get_missing_required():
                missing.append({"step": step.step_name, "field": field, "required": True})
            for field in step.get_missing_optional():
                missing.append({"step": step.step_name, "field": field, "required": False})

        total_required = sum(
            len(s.get_required_fields()) for s in self.filled_steps
        )
        filled_required = sum(
            len([f for f in s.get_required_fields() if f in s.fields])
            for s in self.filled_steps
        )
        pct = (filled_required / total_required * 100) if total_required > 0 else 100.0

        return {
            "current_state": self._to_readable_dict(),
            "missing":        missing,
            "completion_percent": round(pct, 1),
        }

    # ------------------------------------------------------------------ #
    # Export final compatible DebateEngine / V4.1
    # ------------------------------------------------------------------ #

    def to_extraction_dict(self) -> dict:
        """
        Sérialise l'ExtractionState au format attendu par le DebateEngine (compatible V4.1).
        """
        pathways = []

        template = self.phase1_template
        method = template.synthesis_method if template else "unknown"

        steps_out = []
        for fs in self.filled_steps:
            step_dict: dict = {"operation": fs.step_type, "step_name": fs.step_name}
            for fname, fval in fs.fields.items():
                step_dict[fname] = fval.value
                step_dict[f"{fname}_citation"] = fval.citation
            steps_out.append(step_dict)

        pathway = {
            "target_material": {
                "name":    self.target_material.name    if self.target_material else "",
                "formula": self.target_material.formula if self.target_material else "",
            },
            "synthesis_route": method,
            "precursors": [
                {
                    "name":    p.name,
                    "formula": p.formula,
                    "role":    p.role,
                    "amount":  p.amount,
                    "unit":    p.unit,
                    "citation": p.citation,
                }
                for p in self.precursors
            ],
            "synthesis_steps": steps_out,
            "missing_info": template.missing_info_flags if template else [],
        }
        pathways.append(pathway)

        return {
            "pathways": pathways,
            "needs_vision_clarification": len(self.vision_queries) > 0,
            "confidence": template.confidence if template else 0.5,
            "extraction_notes": f"V4.2 Tool Calling — {self.phase2_call_count} tool calls — {len(self.vision_queries)} vision queries",
        }

    # ------------------------------------------------------------------ #
    # Helpers privés
    # ------------------------------------------------------------------ #

    def _get_missing_summary(self) -> List[dict]:
        result = []
        for step in self.filled_steps:
            missing_req = step.get_missing_required()
            missing_opt = step.get_missing_optional()
            if missing_req or missing_opt:
                result.append({
                    "step": step.step_name,
                    "missing_required": missing_req,
                    "missing_optional": missing_opt,
                })
        return result

    def _get_incomplete_steps(self) -> List[str]:
        return [s.step_name for s in self.filled_steps if not s.is_complete()]

    def _to_readable_dict(self) -> dict:
        return {
            "synthesis_method": self.phase1_template.synthesis_method if self.phase1_template else None,
            "target_material":  self.target_material.model_dump() if self.target_material else None,
            "precursors":       [p.model_dump() for p in self.precursors],
            "steps": [
                {
                    "step_name": s.step_name,
                    "step_type": s.step_type,
                    "fields":    {k: {"value": v.value, "citation": v.citation} for k, v in s.fields.items()},
                    "complete":  s.is_complete(),
                    "missing_required": s.get_missing_required(),
                }
                for s in self.filled_steps
            ],
        }
