"""
extraction_tools.py — SynthGraph V4.2
Définitions Pydantic et exécuteurs Python de chaque outil accessible
à l'AgentExtracteurToolCaller via son interface de Tool Calling.

Architecture :
  - ToolInput*   : modèles Pydantic validant les arguments de Gemma
  - ToolResult   : structure de retour standardisée vers Gemma
  - ToolRegistry : catalogue des outils avec leur JSON Schema (envoyé à Gemma)
  - execute_tool : dispatcher central appelé par la boucle while
"""

from __future__ import annotations

import base64
import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

import requests
from pydantic import BaseModel, Field, ValidationError, field_validator

from synthgraph.extraction.state import (
    ExtractionState, Phase1Template, TargetMaterial,
    Precursor, TemplateStep, VisionQuery, STEP_TYPE
)

logger = logging.getLogger("SynthGraph.ExtractionTools")

OLLAMA_BASE_URL = "http://localhost:11434"
PALIGEMMA_MODEL = "paligemma:3b-mix-448-q4_K_M"   # Le proxy injecte --mmproj automatiquement


# ==============================================================================
# Helper : Citation Verification
# ==============================================================================
from typing import Tuple

def verify_citation(citation: str, original_text: str) -> Tuple[bool, Optional[str]]:
    if not citation or citation.strip() == "":
        return True, None
    import re
    import difflib
    # Normalise whitespace and lowercase
    norm_cit = re.sub(r'\s+', '', citation.lower())
    norm_text = re.sub(r'\s+', '', original_text.lower())
    # Accepte si la citation normalisée est dans le texte
    if norm_cit in norm_text:
        return True, None
        
    # Sinon, on cherche une phrase proche
    sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', original_text) if s.strip()]
    matches = difflib.get_close_matches(citation, sentences, n=1, cutoff=0.85)
    if matches:
        return False, matches[0]
    return False, None

# ==============================================================================
# OUTIL RESULT — Retour standardisé
# ==============================================================================

class ToolResult(BaseModel):
    status: Literal["ok", "error", "confirm_required", "finalize"]
    message: str = ""
    # Champs optionnels selon le contexte
    previous_value: Optional[Any] = None
    previous_citation: Optional[str] = None
    missing_values: Optional[List[dict]] = None
    missing_steps: Optional[List[str]] = None
    state_snapshot: Optional[dict] = None
    vision_answer: Optional[str] = None


# ==============================================================================
# PHASE 1 — Tool Inputs
# ==============================================================================

class ToolAddSynthesisStep(BaseModel):
    """Ajoute une étape à l'ossature du template (Phase 1)."""
    tool_name: Literal["add_synthesis_step"] = "add_synthesis_step"
    step_type: Literal[
        "heating", "calcination", "annealing", "sintering", "grinding", "mixing", 
        "dissolution", "filtration", "drying", "pressing", "hydrothermal_treatment", 
        "flux_growth", "cvd_deposition", "generic"
    ] = Field(
        description=(
            "Type EXACT d'étape. Tu n'as PAS le droit d'inventer une valeur. "
            "Tu DOIS choisir parmi : heating, calcination, annealing, "
            "sintering, grinding, mixing, dissolution, filtration, drying, pressing, "
            "hydrothermal_treatment, flux_growth, cvd_deposition, generic"
        )
    )
    citation: str = Field(description="Extrait EXACT du texte source justifiant cette étape")
    description: Optional[str] = Field(default=None, description="Description courte optionnelle")

    @field_validator('step_type', mode='before')
    def validate_step_type(cls, v):
        allowed = ["heating", "calcination", "annealing", "sintering", "grinding", "mixing", 
                   "dissolution", "filtration", "drying", "pressing", "hydrothermal_treatment", 
                   "flux_growth", "cvd_deposition", "generic"]
        if v not in allowed:
            raise ValueError(f"ERREUR FATALE: Le type d'étape '{v}' n'existe pas. Tu DOIS choisir une valeur parmi : {', '.join(allowed)}.")
        return v


class ToolSetSynthesisMethod(BaseModel):
    """Définit la méthode de synthèse globale détectée."""
    tool_name: Literal["set_synthesis_method"] = "set_synthesis_method"
    method_name: str = Field(
        description=(
            "Méthode globale. Ex: solid_state, sol_gel, hydrothermal, "
            "flux_growth, coprecipitation, combustion, spray_pyrolysis, cvd"
        )
    )
    citation: str = Field(description="Extrait EXACT du texte source")
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)


class ToolFlagMissingInfo(BaseModel):
    """Signale une information manquante dans le texte."""
    tool_name: Literal["flag_missing_info"] = "flag_missing_info"
    description: str = Field(description="Description de ce qui manque")


class ToolAskVisionAgent(BaseModel):
    """Appelle l'agent Vision (PaliGemma) pour une figure ou un tableau."""
    tool_name: Literal["ask_vision_agent"] = "ask_vision_agent"
    figure_ref: str = Field(description="Référence de la figure (ex: 'Fig. 3', 'Table 2', 'Figure S1')")
    question: str = Field(description="Question précise à poser à l'agent vision")
    image_path: Optional[str] = Field(default=None, description="Chemin vers l'image si connu")


class ToolNextChunk(BaseModel):
    """Passe au morceau (chunk) de texte suivant dans le document."""
    tool_name: Literal["next_chunk"] = "next_chunk"

class ToolPreviousChunk(BaseModel):
    """Revient au morceau (chunk) de texte précédent dans le document."""
    tool_name: Literal["previous_chunk"] = "previous_chunk"

class ToolActualChunk(BaseModel):
    """Réaffiche le morceau (chunk) de texte actuel."""
    tool_name: Literal["actual_chunk"] = "actual_chunk"

class ToolReviewContext(BaseModel):
    """Affiche ta mission, la directive de l'Orchestrateur et ton rôle dans le pipeline."""
    tool_name: Literal["review_context"] = "review_context"


class ToolFinalizeTemplate(BaseModel):
    """Termine la Phase 1. Le template sera envoyé au groupe de débat."""
    tool_name: Literal["finalize_template"] = "finalize_template"


class ToolAbortExtraction(BaseModel):
    """Permet d'abandonner immédiatement l'extraction si le texte ne contient aucune synthèse."""
    tool_name: Literal["abort_extraction"] = "abort_extraction"
    reason: str = Field(description="Explication de l'abandon. Ex: 'Cette section décrit une caractérisation magnétique, pas une synthèse de matériau.'")


from typing import Annotated, Union
AgentActionPhase1 = Annotated[
    Union[
        ToolAddSynthesisStep,
        ToolSetSynthesisMethod,
        ToolFlagMissingInfo,
        ToolAskVisionAgent,
        ToolNextChunk,
        ToolPreviousChunk,
        ToolActualChunk,
        ToolReviewContext,
        ToolFinalizeTemplate,
        ToolAbortExtraction
    ],
    Field(discriminator="tool_name")
]


# ==============================================================================
# PHASE 2 — Tool Inputs
# ==============================================================================

class ToolInsertValue(BaseModel):
    """Insère ou met à jour une valeur dans une étape."""
    tool_name: Literal["insert_value"] = "insert_value"
    step_name: str = Field(description="Nom de l'étape (ex: 'heating_1', 'grinding_2')")
    field: str = Field(description="Nom du champ (ex: 'temperature_C', 'duration_min', 'atmosphere')")
    value: str = Field(description="Valeur extraite (toujours en string, Python la convertira)")
    citation: str = Field(description="Extrait EXACT du texte source justifiant cette valeur")
    confirm: bool = Field(
        default=False,
        description="Mettre à True pour confirmer l'écrasement d'une valeur déjà remplie"
    )


class ToolAddTargetMaterial(BaseModel):
    """Définit le matériau cible de la synthèse."""
    tool_name: Literal["add_target_material"] = "add_target_material"
    name: str = Field(description="Nom du matériau (ex: 'Strontium Titanate')")
    formula: str = Field(description="Formule chimique (ex: 'SrTiO3')")
    citation: str = Field(description="Extrait EXACT du texte source")


class ToolAddPrecursor(BaseModel):
    """Ajoute un précurseur à la liste."""
    tool_name: Literal["add_precursor"] = "add_precursor"
    name: str = Field(description="Nom du précurseur (ex: 'Strontium carbonate')")
    formula: str = Field(description="Formule chimique (ex: 'SrCO3')")
    role: Literal["reactant", "flux", "solvent", "dopant", "additive"] = Field(
        default="reactant",
        description="Rôle du précurseur dans la réaction"
    )
    amount: Optional[str] = Field(default=None, description="Quantité ex: '2.5 g', '0.1 mol'")
    citation: str = Field(description="Extrait EXACT du texte source")

    @field_validator("formula")
    @classmethod
    def prevent_atomic_elements(cls, v: str) -> str:
        v_clean = v.strip()
        if len(v_clean) <= 2 and v_clean.isalpha():
            raise ValueError("Un précurseur ne doit pas être un élément atomique pur (ex: Sr, Ir, O) sauf spécifié comme métal pur. Fournissez le composé (ex: SrO, IrO2).")
        return v_clean


class ToolGetState(BaseModel):
    """Retourne le JSON courant de l'ExtractionState et les valeurs manquantes."""
    tool_name: Literal["get_state"] = "get_state"




class ToolFinalizeExtraction(BaseModel):
    """Termine la Phase 2. L'ExtractionState final est renvoyé à l'Orchestrateur."""
    tool_name: Literal["finalize_extraction"] = "finalize_extraction"


AgentActionPhase2 = Annotated[
    Union[
        ToolAddTargetMaterial,
        ToolAddPrecursor,
        ToolInsertValue,
        ToolGetState,
        ToolAskVisionAgent,
        ToolNextChunk,
        ToolPreviousChunk,
        ToolActualChunk,
        ToolReviewContext,
        ToolFinalizeExtraction,
        ToolAbortExtraction
    ],
    Field(discriminator="tool_name")
]

# Les TOOL REGISTRY (PHASE1_TOOLS et PHASE2_TOOLS) et get_openai_tools 
# ne sont plus nécessaires avec la génération structurée native.


# ==============================================================================
# EXECUTEURS D'OUTILS — Phase 1
# ==============================================================================

def execute_phase1_tool(tool_name: str, arguments: dict, state: ExtractionState, original_text: str = "", directive: dict = None) -> ToolResult:
    """Dispatcher Phase 1."""
    state.phase1_call_count += 1
    
    cit = arguments.get("citation")
    if cit:
        is_valid, suggestion = verify_citation(cit, original_text)
        if not is_valid:
            msg = "La citation fournie n'est pas présente dans le texte original. Veuillez fournir un extrait exact."
            if suggestion:
                msg = f"La citation fournie n'est pas exacte. Vouliez-vous dire : '{suggestion}' ? Si oui, réessayez l'outil avec cette citation exacte."
            return ToolResult(status="error", message=msg)

    try:
        if tool_name == "abort_extraction":
            args = ToolAbortExtraction(**arguments)
            return ToolResult(status="aborted", message=args.reason)

        elif tool_name == "set_synthesis_method":
            args = ToolSetSynthesisMethod(**arguments)
            if state.phase1_template is None:
                state.phase1_template = Phase1Template(
                    synthesis_method=args.method_name,
                    synthesis_method_citation=args.citation,
                    confidence=args.confidence,
                )
            else:
                state.phase1_template.synthesis_method = args.method_name
                state.phase1_template.synthesis_method_citation = args.citation
                state.phase1_template.confidence = args.confidence
            state.log(f"[Phase1] SET_METHOD: {args.method_name}")
            return ToolResult(status="ok", message=f"Méthode '{args.method_name}' enregistrée.")

        elif tool_name == "add_synthesis_step":
            args = ToolAddSynthesisStep(**arguments)
            if state.phase1_template is None:
                state.phase1_template = Phase1Template(
                    synthesis_method="unknown",
                    synthesis_method_citation="",
                )
            order = len(state.phase1_template.steps) + 1
            # Génère un step_name unique (ex: heating_1, heating_2)
            count = sum(1 for s in state.phase1_template.steps if s.step_type == args.step_type)
            step_name = f"{args.step_type}_{count + 1}"
            step = TemplateStep(
                step_name=step_name,
                step_type=args.step_type,
                order=order,
                citation=args.citation,
                description=args.description,
            )
            state.phase1_template.steps.append(step)
            state.log(f"[Phase1] ADD_STEP: {step_name} (order={order})")
            return ToolResult(
                status="ok",
                message=f"Étape '{step_name}' ajoutée en position {order}.",
            )

        elif tool_name == "flag_missing_info":
            args = ToolFlagMissingInfo(**arguments)
            if state.phase1_template is None:
                state.phase1_template = Phase1Template(synthesis_method="unknown", synthesis_method_citation="")
            state.phase1_template.missing_info_flags.append(args.description)
            state.log(f"[Phase1] FLAG_MISSING: {args.description}")
            return ToolResult(status="ok", message=f"Information manquante signalée.")

        elif tool_name == "next_chunk":
            if state.current_chunk_idx < len(state.chunks) - 1:
                state.current_chunk_idx += 1
                new_chunk = state.chunks[state.current_chunk_idx]
                return ToolResult(status="ok", message=f"Passage au chunk {state.current_chunk_idx + 1}/{len(state.chunks)}.\n--- CONTENU ---\n{new_chunk}")
            else:
                return ToolResult(status="error", message="Tu es déjà au dernier chunk. Reviens en arrière avec previous_chunk si besoin.")
                
        elif tool_name == "previous_chunk":
            if state.current_chunk_idx > 0:
                state.current_chunk_idx -= 1
                new_chunk = state.chunks[state.current_chunk_idx]
                return ToolResult(status="ok", message=f"Retour au chunk {state.current_chunk_idx + 1}/{len(state.chunks)}.\n--- CONTENU ---\n{new_chunk}")
            else:
                return ToolResult(status="error", message="Tu es déjà au premier chunk.")
                
        elif tool_name == "actual_chunk":
            if not state.chunks:
                return ToolResult(status="error", message="Aucun chunk disponible.")
            chunk = state.chunks[state.current_chunk_idx]
            return ToolResult(status="ok", message=f"Chunk {state.current_chunk_idx + 1}/{len(state.chunks)}.\n--- CONTENU ---\n{chunk}")
            
        elif tool_name == "review_context":
            mission = directive.get("mission_summary", "") if directive else ""
            target = directive.get("target_material", "") if directive else ""
            macro = directive.get("macro_method", "") if directive else ""
            starting = directive.get("starting_materials", []) if directive else []
            msg = "Tu es l'Agent Extracteur. Tu seras ensuite audité par la Red Team (Contextuel et Thermodynamicien).\n"
            msg += f"Directive de l'Orchestrateur :\n- Objectif : {mission}\n- Cible : {target}\n- Matériaux de départ : {', '.join(starting)}\n- Méthode principale : {macro}"
            return ToolResult(status="ok", message=msg)

        elif tool_name == "finalize_template":
            if state.phase1_template is None or getattr(state.phase1_template, "synthesis_method", "unknown") == "unknown":
                return ToolResult(status="error", message="INTERDIT : L'outil finalize_template a été bloqué. Tu dois D'ABORD appeler l'outil 'set_synthesis_method' pour définir la méthode principale.")
            steps = state.phase1_template.steps if state.phase1_template else []
            if len(steps) == 0:
                return ToolResult(status="error", message="INTERDIT : L'outil finalize_template a été bloqué. Tu dois D'ABORD ajouter au moins une étape avec 'add_synthesis_step'.")
            
            if directive:
                macro = directive.get("macro_method")
                if macro:
                    has_macro = False
                    if state.phase1_template.synthesis_method == macro:
                        has_macro = True
                    for step in steps:
                        if step.step_type == macro:
                            has_macro = True
                    if not has_macro:
                        return ToolResult(status="error", message=f"Erreur : Tu DOIS insérer la méthode principale '{macro}' dictée par l'Orchestrateur (via add_synthesis_step ou set_synthesis_method).")
            
            state.log(f"[Phase1] FINALIZE_TEMPLATE — {len(steps)} étapes")
            return ToolResult(
                status="finalize",
                message=f"Template finalisé avec {len(steps)} étapes.",
            )

        else:
            return ToolResult(status="error", message=f"Outil Phase 1 inconnu: '{tool_name}'")

    except ValidationError as e:
        errs = [f"{err['loc']}: {err['msg']}" for err in e.errors()]
        return ToolResult(status="error", message=f"Validation Pydantic échouée: {'; '.join(errs)}")
    except Exception as e:
        return ToolResult(status="error", message=f"Erreur inattendue: {e}")


# ==============================================================================
# EXECUTEURS D'OUTILS — Phase 2
# ==============================================================================

def execute_phase2_tool(
    tool_name: str,
    arguments: dict,
    state: ExtractionState,
    images_map: Dict[str, str],  # figure_ref -> chemin image
    base_url: str = OLLAMA_BASE_URL,
    original_text: str = "",
    directive: dict = None,
) -> ToolResult:
    """Dispatcher Phase 2."""
    state.phase2_call_count += 1

    cit = arguments.get("citation")
    if cit:
        is_valid, suggestion = verify_citation(cit, original_text)
        if not is_valid:
            msg = "La citation fournie n'est pas présente dans le texte original. Veuillez fournir un extrait exact."
            if suggestion:
                msg = f"La citation fournie n'est pas exacte. Vouliez-vous dire : '{suggestion}' ? Si oui, réessayez l'outil avec cette citation exacte."
            return ToolResult(status="error", message=msg)

    try:
        if tool_name == "abort_extraction":
            args = ToolAbortExtraction(**arguments)
            return ToolResult(status="aborted", message=args.reason)

        elif tool_name == "add_target_material":
            args = ToolAddTargetMaterial(**arguments)
            state.target_material = TargetMaterial(
                name=args.name, formula=args.formula, citation=args.citation
            )
            state.log(f"[Phase2] SET_TARGET: {args.formula}")
            return ToolResult(
                status="ok", message=f"Matériau cible '{args.formula}' enregistré.",
                missing_values=state._get_missing_summary(),
                missing_steps=state._get_incomplete_steps(),
            )

        elif tool_name == "add_precursor":
            args = ToolAddPrecursor(**arguments)
            # Évite les doublons (même formule + rôle)
            existing = next(
                (p for p in state.precursors if p.formula == args.formula and p.role == args.role), None
            )
            if existing:
                return ToolResult(
                    status="confirm_required",
                    message=f"Précurseur '{args.formula}' ({args.role}) déjà dans la liste.",
                    previous_value=existing.model_dump(),
                    previous_citation=existing.citation,
                )
            state.precursors.append(
                Precursor(
                    name=args.name, formula=args.formula, role=args.role,
                    amount=args.amount, citation=args.citation
                )
            )
            state.log(f"[Phase2] ADD_PRECURSOR: {args.formula} ({args.role})")
            return ToolResult(
                status="ok", message=f"Précurseur '{args.name}' ajouté.",
                missing_values=state._get_missing_summary(),
                missing_steps=state._get_incomplete_steps(),
            )

        elif tool_name == "insert_value":
            args = ToolInsertValue(**arguments)
            # Conversion automatique de la valeur string vers float si possible
            value: Any = args.value
            try:
                value = float(args.value)
            except (ValueError, TypeError):
                pass

            result = state.insert_value(
                step_name=args.step_name,
                field=args.field,
                value=value,
                citation=args.citation,
                confirm=args.confirm,
            )
            return ToolResult(**result)

        elif tool_name == "get_state":
            snap = state.get_state_snapshot()
            return ToolResult(
                status="ok",
                message=f"État actuel : {snap['completion_percent']}% complet.",
                state_snapshot=snap,
            )

        elif tool_name == "ask_vision_agent":
            args = ToolAskVisionAgent(**arguments)
            answer = _call_vision_agent(
                figure_ref=args.figure_ref,
                question=args.question,
                image_path=args.image_path or images_map.get(args.figure_ref),
                base_url=base_url,
            )
            state.vision_queries.append(
                VisionQuery(
                    figure_ref=args.figure_ref,
                    question=args.question,
                    answer=answer,
                    model_used=PALIGEMMA_MODEL,
                )
            )
            state.log(f"[Phase2] VISION: {args.figure_ref} → {answer[:60]}...")
            return ToolResult(
                status="ok",
                message=f"Vision agent a répondu pour '{args.figure_ref}'.",
                vision_answer=answer,
            )

        elif tool_name == "next_chunk":
            if state.current_chunk_idx < len(state.chunks) - 1:
                state.current_chunk_idx += 1
                new_chunk = state.chunks[state.current_chunk_idx]
                return ToolResult(status="ok", message=f"Passage au chunk {state.current_chunk_idx + 1}/{len(state.chunks)}.\n--- CONTENU ---\n{new_chunk}")
            else:
                return ToolResult(status="error", message="Tu es déjà au dernier chunk. Reviens en arrière avec previous_chunk si besoin.")
                
        elif tool_name == "previous_chunk":
            if state.current_chunk_idx > 0:
                state.current_chunk_idx -= 1
                new_chunk = state.chunks[state.current_chunk_idx]
                return ToolResult(status="ok", message=f"Retour au chunk {state.current_chunk_idx + 1}/{len(state.chunks)}.\n--- CONTENU ---\n{new_chunk}")
            else:
                return ToolResult(status="error", message="Tu es déjà au premier chunk.")
                
        elif tool_name == "actual_chunk":
            if not state.chunks:
                return ToolResult(status="error", message="Aucun chunk disponible.")
            chunk = state.chunks[state.current_chunk_idx]
            return ToolResult(status="ok", message=f"Chunk {state.current_chunk_idx + 1}/{len(state.chunks)}.\n--- CONTENU ---\n{chunk}")
            
        elif tool_name == "review_context":
            mission = directive.get("mission_summary", "") if directive else ""
            target = directive.get("target_material", "") if directive else ""
            macro = directive.get("macro_method", "") if directive else ""
            starting = directive.get("starting_materials", []) if directive else []
            msg = "Tu es l'Agent Extracteur (Phase 2). Tu seras audité par la Red Team (Contextuel et Thermodynamicien).\n"
            msg += f"Directive de l'Orchestrateur :\n- Objectif : {mission}\n- Cible : {target}\n- Matériaux de départ : {', '.join(starting)}\n- Méthode principale : {macro}"
            return ToolResult(status="ok", message=msg)

        elif tool_name == "finalize_extraction":
            if not state.target_material:
                return ToolResult(status="error", message="INTERDIT : L'outil finalize_extraction a été bloqué. Tu dois D'ABORD appeler l'outil 'add_target_material' pour définir le matériau cible de cette synthèse.")
            
            if directive:
                target_dir = directive.get("target_material")
                if target_dir:
                    found_target = state.target_material.formula.lower() in target_dir.lower() or target_dir.lower() in state.target_material.formula.lower() or state.target_material.name.lower() in target_dir.lower() or target_dir.lower() in state.target_material.name.lower()
                    if not found_target:
                        return ToolResult(status="error", message=f"Erreur : Le matériau cible ajouté ({state.target_material.formula}) ne correspond pas du tout à la directive de l'Orchestrateur ({target_dir}).")

                starting_dir = directive.get("starting_materials", [])
                if starting_dir:
                    added_formulas = [p.formula.lower() for p in state.precursors] + [p.name.lower() for p in state.precursors]
                    for s_mat in starting_dir:
                        found = False
                        for added in added_formulas:
                            if s_mat.lower() in added or added in s_mat.lower():
                                found = True
                                break
                        if not found:
                            return ToolResult(status="error", message=f"Erreur : Tu DOIS ajouter le précurseur '{s_mat}' dicté par l'Orchestrateur (via add_precursor).")
            
            state.log("[Phase2] FINALIZE_EXTRACTION")
            return ToolResult(status="finalize", message="Extraction terminée.")

        else:
            return ToolResult(status="error", message=f"Outil Phase 2 inconnu: '{tool_name}'")

    except ValidationError as e:
        errs = [f"{err['loc']}: {err['msg']}" for err in e.errors()]
        return ToolResult(
            status="error",
            message=f"Validation Pydantic échouée — corrige les arguments: {'; '.join(errs)}",
        )
    except Exception as e:
        return ToolResult(status="error", message=f"Erreur inattendue: {e}")


# ==============================================================================
# AGENT VISION — Model Swap PaliGemma
# ==============================================================================

def _call_vision_agent(
    figure_ref: str,
    question: str,
    image_path: Optional[str],
    base_url: str = OLLAMA_BASE_URL,
) -> str:
    """
    Exécute un model swap Gemma → PaliGemma, pose la question à l'image,
    puis retourne la réponse textuelle. Le proxy injecte --mmproj automatiquement
    dès que le nom du modèle contient 'paligemma'.
    """
    if not image_path or not Path(image_path).exists():
        return f"[Vision] Image introuvable pour '{figure_ref}'. Chemin: {image_path}"

    logger.info(f"[Vision] Model swap → PaliGemma pour '{figure_ref}'")

    # 1. Le routeur dynamique gère la VRAM automatiquement
    pass

    # 2. Encodage de l'image en base64
    with open(image_path, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode("utf-8")

    # 3. Appel PaliGemma (le proxy injecte --mmproj automatiquement)
    payload = {
        "model": PALIGEMMA_MODEL,  # "paligemma:3b-mix-448"
        "messages": [
            {
                "role": "user",
                "content": (
                    f"Tu es un expert en chimie des matériaux. "
                    f"Analyse cette figure scientifique ({figure_ref}) et réponds PRÉCISÉMENT à la question suivante : "
                    f"{question}"
                ),
                "images": [img_b64],
            }
        ],
        "stream": False,
        "keep_alive": 0,
    }

    try:
        resp = requests.post(
            f"{base_url}/api/chat",
            json=payload,
            timeout=60,
        )
        resp.raise_for_status()
        answer = resp.json().get("message", {}).get("content", "")
        logger.info(f"[Vision] Réponse PaliGemma: {answer[:80]}...")
    except Exception as e:
        answer = f"[Vision ERROR] {e}"
        logger.error(f"[Vision] Erreur PaliGemma: {e}")

    # 4. Déchargement géré par le routeur dynamique
    pass

    return answer
