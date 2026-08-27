"""
synthgraph/agents/extractor_nuextract.py — SynthGraph V4.19 Phase 2

Adaptateur NuExtract 3 (NuMind) — DROP-IN pour `extract_single_shot()`
(cf `synthgraph/agents/extractor_singleshot.py`).

Pourquoi NuExtract : c'est un modèle 4B spécialisé EXTRACTION STRUCTURÉE PAR
TEMPLATE. Le prompt décrit un schéma JSON où chaque valeur est un TYPE :
  - "verbatim-string" : la sortie DOIT être une sous-chaîne LITTÉRALE du texte
    source (contrainte au niveau génération, pas juste une instruction dans le
    prompt) → attaque directement le problème n°1 constaté sur Llama-3.1-8B
    (« il cite ses propres instructions », citations/recettes fabriquées —
    cf CLAUDE.md « Leçons durement apprises »).
  - "integer" / "number" : champ numérique (ou null si absent du texte).
  - liste de littéraux (ex: ["reactant","flux",...]) : champ catégoriel/enum,
    le modèle choisit parmi les valeurs proposées (ou "" si aucune ne convient).
  - `[ {...} ]` (liste contenant UN objet-gabarit) : champ RÉPÉTÉ, NuExtract
    génère 0..N objets conformes à ce gabarit (précurseurs, étapes).

Format d'appel : PAS un chat (system/user) comme `SynthAgent.call()`. NuExtract
est fine-tuné sur un format texte brut :
    # Template:
    {...JSON du template...}
    # Context:
    {texte source}
On appelle donc directement `Llama.create_completion()` (complétion brute) sur
l'objet renvoyé par `LlamaEngineManager.get_instance().get_llm("extractor")` —
même moteur in-process, même singleton, AUCUNE modification d'`engine.py`.

Règle d'or (non négociable, cf CLAUDE.md) : si NuExtract renvoie une liste
vide ou un champ vide, on renvoie une liste/un champ vide. Aucun fallback
fictif, aucune valeur devinée.
"""

from __future__ import annotations

import json as _json
import logging
from collections import defaultdict
from typing import Any, Optional

from synthgraph.llm.engine import LlamaEngineManager
from synthgraph.schemas.step_schema import STEP_PARAMETERS, normalize_steps
from synthgraph.utils.tools import safe_json_parse

logger = logging.getLogger("SynthGraph.ExtracteurNuExtract")

# ==============================================================================
#  TEMPLATE NuExtract — couvre les champs essentiels de FlatExtraction /
#  FlatPrecursor / FlatStep (cf extractor_singleshot.py lignes 29-96).
# ==============================================================================

# Mêmes rôles de précurseur que le system prompt Llama existant (règle 3 du
# SYSTEM_PROMPT dans extractor_singleshot.py) — champ catégoriel NuExtract.
PRECURSOR_ROLES: list[str] = ["reactant", "flux", "solvent", "dopant", "additive"]

# Types d'étape canoniques : dérivés du REGISTRE PARTAGÉ `STEP_PARAMETERS`
# (schemas/step_schema.py) — si le registre évolue (nouveau type d'étape), le
# template NuExtract suit automatiquement sans modification de ce module.
STEP_OPERATIONS: list[str] = list(STEP_PARAMETERS.keys())

NUEXTRACT_TEMPLATE: dict[str, Any] = {
    "target": "verbatim-string",
    "method": "verbatim-string",
    "precursors": [
        {
            "name": "verbatim-string",
            "role": PRECURSOR_ROLES,
            "amount": "verbatim-string",
            "citation": "verbatim-string",
        }
    ],
    "steps": [
        {
            "order": "integer",
            "variant_id": "verbatim-string",
            "operation": STEP_OPERATIONS,
            "temperature_c": "number",
            "target_temperature_c": "number",
            "duration_h": "number",
            "ramp_rate_c_per_h": "number",
            "cooling_rate_c_per_h": "number",
            "atmosphere": "verbatim-string",
            "equipment": "verbatim-string",
            "citation": "verbatim-string",
        }
    ],
    "notes": "verbatim-string",
}


def _build_prompt(text: str, method_type: str, target: str,
                   directive: dict | None, extra_hint: str) -> str:
    """Construit le prompt brut NuExtract : `# Template:\\n{...}\\n# Context:\\n{...}`.

    La cible/méthode connues (transmises par l'Orchestrateur) et la directive
    sont injectées EN TÊTE du contexte, pas dans le template : elles orientent
    la lecture sans jamais être elles-mêmes une source de citation verbatim
    valide (le texte source, lui, l'est).
    """
    template_str = _json.dumps(NUEXTRACT_TEMPLATE, ensure_ascii=False)
    context_parts = [
        f"TARGET MATERIAL: {target}",
        f"METHOD: {method_type}",
    ]
    if directive:
        context_parts.append(
            f"MISSION DIRECTIVE (objectif de mission, PAS le texte source) : "
            f"{_json.dumps(directive, ensure_ascii=False)}"
        )
    if extra_hint:
        context_parts.append(extra_hint)
    context_parts.append(text)
    context = "\n".join(context_parts)
    return f"# Template:\n{template_str}\n# Context:\n{context}"


def extract_single_shot_nuextract(
    text: str, method_type: str, target: str,
    model: str = "nuextract-3", route_id: str = "route_1",
    directive: dict | None = None, use_grammar: bool = False,
    extra_hint: str = "", temperature: float | None = None,
) -> dict:
    """Extraction structurée via NuExtract 3 — DROP-IN pour `extract_single_shot()`.

    Renvoie un dict `{pathways, confidence, extraction_notes, route_id,
    method_type}` strictement compatible avec `_to_pathways_dict` (même forme
    que le backend Llama). `use_grammar` est accepté pour compatibilité de
    signature mais sans effet ici : NuExtract est déjà contraint par son
    format de TEMPLATE (pas de grammaire GBNF nécessaire/pertinente).

    temperature : None → 0.0 (extraction déterministe, cohérent avec le
    défaut historique de l'extracteur Llama, DEFAULT_TEMPERATURE=0.1 ≈ quasi
    déterministe ; NuExtract étant un modèle d'extraction pure, 0.0 est le
    réglage recommandé NuMind).
    """
    prompt = _build_prompt(text, method_type, target, directive, extra_hint)

    llm = LlamaEngineManager.get_instance().get_llm("extractor")

    completion_kwargs = dict(
        prompt=prompt,
        max_tokens=4096,
        temperature=temperature if temperature is not None else 0.0,
    )
    try:
        resp = llm.create_completion(**completion_kwargs)
        raw_text = (resp.get("choices") or [{}])[0].get("text", "")
    except Exception as e:
        logger.error(f"[NuExtract-{route_id}] Erreur d'inférence : {e}")
        return {"pathways": [], "confidence": 0.0, "extraction_notes": "nuextract inference failed",
                "route_id": route_id, "method_type": method_type}

    data = safe_json_parse(raw_text)
    if not data:
        logger.warning(f"[NuExtract-{route_id}] Sortie non parseable : {raw_text[:200]!r}")
        return {"pathways": [], "confidence": 0.0, "extraction_notes": "nuextract unparseable output",
                "route_id": route_id, "method_type": method_type}

    # Forcer method/target si absents/vides (on les connaît via la directive) —
    # même comportement que le backend Llama (`data.setdefault`).
    if not data.get("method"):
        data["method"] = method_type
    if not data.get("target"):
        data["target"] = target

    return _to_pathways_dict_nuextract(data, method_type, route_id)


def _to_pathways_dict_nuextract(data: dict, method_type: str, route_id: str) -> dict:
    """Convertit la sortie NuExtract (conforme à `NUEXTRACT_TEMPLATE`) → `pathways`,
    avec étapes NORMALISÉES par type (`normalize_steps`, même registre que le
    backend Llama). Regroupe les étapes par `variant_id`.

    Défensif par construction : précurseur sans `name` → écarté (jamais de
    précurseur fantôme) ; `role`/`variant_id` vides → repli sur les défauts du
    schéma plat historique ("reactant" / "v1"), PAS une valeur inventée — ce
    sont les mêmes défauts que `FlatPrecursor`/`FlatStep` (Pydantic) appliquent
    déjà côté Llama.
    """
    raw_steps = [s for s in (data.get("steps") or []) if isinstance(s, dict)]

    variants: dict[str, list[dict]] = defaultdict(list)
    for s in raw_steps:
        vid = (s.get("variant_id") or "v1")
        vid = vid.strip() if isinstance(vid, str) else "v1"
        variants[vid or "v1"].append(s)
    if not variants:
        variants["v1"] = []

    precursors = []
    for p in (data.get("precursors") or []):
        if not isinstance(p, dict):
            continue
        name = (p.get("name") or "").strip()
        if not name:
            continue  # jamais de précurseur fantôme (règle d'or)
        role = (p.get("role") or "").strip() or "reactant"
        precursors.append({
            "name": name, "formula": name,
            "role": role, "amount": p.get("amount", "") or "",
            "unit": "", "citation": p.get("citation", "") or "",
        })

    notes = [data.get("notes", "")] if data.get("notes") else []
    pathways = []
    total_steps = 0
    total_missing = 0

    for vid in sorted(variants.keys()):
        variant_steps = variants[vid]
        normalized_steps, missing_parameters = normalize_steps(variant_steps)
        for st in normalized_steps:
            st["step_name"] = f"{st.get('type', 'step')}_{st.get('order', '')}"

        pathway = {
            "target_material": {"name": data.get("target", ""), "formula": data.get("target", "")},
            "synthesis_route": method_type,
            "variant_id": vid,
            "precursors": precursors,
            "synthesis_steps": normalized_steps,
            "missing_parameters": missing_parameters,
            "missing_info": notes,
        }
        pathways.append(pathway)
        total_steps += len(normalized_steps)
        total_missing += len(missing_parameters)

    return {
        "pathways": pathways,
        "reasoning": "",
        "confidence": 0.8 if total_steps else 0.3,
        "route_id": route_id,
        "method_type": method_type,
        "extraction_notes": (f"nuextract ({total_steps} étapes normalisées, "
                             f"{len(precursors)} précurseurs, {total_missing} params requis manquants, "
                             f"{len(pathways)} variante(s))"),
    }
