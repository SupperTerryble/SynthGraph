#!/usr/bin/env python3
"""
synthgraph/pipeline/runner.py — SynthGraph V4.4
Corps du pipeline multi-agents : étapes 1→6 avec fork par voie de synthèse.
Chaque étape sauvegarde son résultat JSON dans logs/steps/.

Point d'entrée : `run_pipeline(args)`, appelé par synthgraph.cli (voir run.py).
"""

# ==============================================================================
#  CONSTANTES
# ==============================================================================
STEP_RESULTS_DIR     = "logs/steps"
EXECUTION_LOG_PATH   = "logs/execution_log.md"
CYPHER_OUTPUT_PATH   = "logs/cypher_output.cypher"
ASSIGNMENT_FILE_PATH = "logs/model_assignment.json"
TOOL_EVENTS_LOG_PATH = "logs/tool_events.jsonl"
GEMINI_LOG_PATH      = "Gemini_update.log"
SLEEP_BETWEEN_STEPS  = 1    # Secondes entre chaque étape (moteur singleton : plus besoin de 5s anti-OOM)
AGENT_TIMEOUT        = 180  # Secondes par appel LLM
AGENT_MAX_TOKENS     = 8192  # Tokens par réponse (extraction : longs JSON)
QA_MAX_TOKENS        = 2048  # [V4.7] Agents QA (débat/audit) : petits JSON. Constaté en
                             # run réel : 3 générations dégénérées à ~590s chacune (plafond
                             # 8192 atteint) = 30 min perdues sur un seul papier.
MAX_VALIDATION_RETRIES = 2  # Retries LLM sur erreur de validation Pydantic (GroundedFloat)

OLLAMA_BASE_URL = "http://localhost:11434"
LLAMA_SERVER_URL = "http://localhost:11434"
LLM_PROVIDER = "llama-server" # par défaut

# ==============================================================================
#  IMPORTS
# ==============================================================================
import os
import sys
import json
import hashlib
sys.stdout.reconfigure(encoding='utf-8')
import time
import gc
import re
import logging
import argparse
import requests
import subprocess
from pathlib import Path
from datetime import datetime
from pydantic import ValidationError

# Load agent prompts (depuis config/)
from synthgraph.config import AGENT_PROMPTS_PATH, get_model_config
if AGENT_PROMPTS_PATH.exists():
    with open(AGENT_PROMPTS_PATH, "r", encoding="utf-8") as f:
        AGENT_PROMPTS = json.load(f)
else:
    AGENT_PROMPTS = {}

from synthgraph.schemas.core import (
    OrchestratorPlan, ExtractionResult, RouteExtractionResult,
    ContextualAnalysis, ExtractorClarification, DebateValidation,
    ContextualReply, GraphModel, RedTeamAudit, ContextualAuditReply,
    SynthesisRouteList, SynthesisRoute, MissingParameter, Precursor,
    VetoDecision, GroundingStats, BibleQuery
)
from synthgraph.schemas.synthesis import get_extraction_model_for_method, METHOD_REGISTRY
from synthgraph.rag.manager import DocumentRAG, BibleRAG
from synthgraph.utils.status import init_status, update_status

# Logger UTF-8 pour éviter la corruption des caractères accentués
_log_formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
_root_logger = logging.getLogger()
_root_logger.setLevel(logging.INFO)
if not _root_logger.handlers:
    _ch = logging.StreamHandler()
    _ch.setFormatter(_log_formatter)
    _root_logger.addHandler(_ch)
logger = logging.getLogger("SynthGraph.Runner")

# ==============================================================================
#  UTILITAIRES
# ==============================================================================

def load_model() -> str:
    """Charge le modèle sélectionné par le benchmark."""
    if Path(ASSIGNMENT_FILE_PATH).exists():
        with open(ASSIGNMENT_FILE_PATH) as f:
            d = json.load(f)
        return d.get("reasoning_model", "deepseek-r1")
    return "deepseek-r1"


LLM_TRANSCRIPT = []
_DEBUG_TEXT = False

from synthgraph.agents.base import SynthAgent

def get_agent(name: str, sys_prompt: str, model: str, max_tokens: int = None,
              role: str = "default") -> SynthAgent:
    """Instancie un SynthAgent proprement avec la bonne configuration.

    max_tokens : plafond de génération (défaut AGENT_MAX_TOKENS ; utiliser
    QA_MAX_TOKENS pour les agents de débat/audit dont les JSON sont courts).
    role : [Phase 1 — plan multi-modèles] rôle de ROUTAGE MODÈLE transmis à
    `SynthAgent.role` → `LlamaEngineManager.get_llm(role)` (cf `config/settings.yaml:
    models`). AVANT ce correctif, `role` valait `name` (libellé d'instance, ex:
    "Contextuel-route_1") qui ne matchait JAMAIS une entrée de `models:` → tous les
    agents du runner retombaient silencieusement sur le rôle `default`. Défaut
    inchangé ("default") : aucune régression si l'appelant omet le paramètre.
    """
    global LLM_PROVIDER
    mt = max_tokens or AGENT_MAX_TOKENS
    if LLM_PROVIDER == "llama-server":
        return SynthAgent(
            name=name, role=role, model=model, system_prompt=sys_prompt,
            base_url=LLAMA_SERVER_URL, api_format="openai", max_tokens=mt
        )
    return SynthAgent(
        name=name, role=role, model=model, system_prompt=sys_prompt,
        base_url=OLLAMA_BASE_URL, api_format="ollama", max_tokens=mt
    )

def append_transcript(step_name: str, model: str, sys_prompt: str, user_prompt: str, agent: SynthAgent):
    """Met à jour le journal de bord global."""
    if agent._messages:
        msg = agent._messages[-1]
        LLM_TRANSCRIPT.append({
            "step": step_name,
            "model": model,
            "system_prompt": sys_prompt,
            "user_prompt": user_prompt,
            "raw_response": msg.content
        })
        # Mise à jour minimaliste du statut pour l'UI
        # On ne calcule pas les tokens parfaits ici car on a délégué l'appel à SynthAgent
        update_status(add_tokens_generated=len(msg.content)//4, add_tokens_prompt=len(user_prompt)//4)


def write_log(text: str):
    Path(EXECUTION_LOG_PATH).parent.mkdir(exist_ok=True)
    mode = "a" if Path(EXECUTION_LOG_PATH).exists() else "w"
    with open(EXECUTION_LOG_PATH, mode, encoding="utf-8") as f:
        if mode == "w":
            f.write(f"# SynthGraph — Journal d'Exécution\n**Date** : {datetime.now().isoformat()}\n\n")
        f.write(text + "\n")


def log_tool_event(
    agent: str,
    phase: str,
    tool_name: str,
    call_index: int,
    args: dict = None,
    result_status: str = "ok",
    error: str = None,
    duration_ms: int = None,
    route_id: str = None,
):
    """Enregistre un événement d'appel d'outil dans tool_events.jsonl (format JSONL)."""
    Path(TOOL_EVENTS_LOG_PATH).parent.mkdir(exist_ok=True)
    event = {
        "ts": datetime.now().isoformat(),
        "agent": agent,
        "phase": phase,
        "route_id": route_id,
        "tool": tool_name,
        "call_index": call_index,
        "status": result_status,
        "duration_ms": duration_ms,
        "error": error,
        "args_summary": {k: str(v)[:120] for k, v in (args or {}).items()},
    }
    with open(TOOL_EVENTS_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")
    # Aussi dans le logger standard pour visibilité immédiate
    status_icon = "✅" if result_status == "ok" else ("⚠️" if result_status == "warning" else "❌")
    logger.info(
        f"[TOOL] {status_icon} [{agent}/{phase}] #{call_index} → {tool_name} "
        + (f"| {duration_ms}ms" if duration_ms else "")
        + (f" | ERREUR: {error}" if error else "")
    )


def save_step(name: str, data: dict):
    Path(STEP_RESULTS_DIR).mkdir(parents=True, exist_ok=True)
    path = f"{STEP_RESULTS_DIR}/{name}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    logger.info(f"Résultat sauvegardé : {path}")


def load_step(name: str) -> dict:
    path = f"{STEP_RESULTS_DIR}/{name}.json"
    if Path(path).exists():
        with open(path) as f:
            return json.load(f)
    return {}


def kill_llama_server():
    """Ne fait rien. Le serveur est géré par l'utilisateur."""
    pass

def start_llama_server(model_type="text"):
    """Ne fait rien. Le serveur est géré par l'utilisateur."""
    logger.info(f"[System] Le serveur est géré en externe. On assume qu'il est prêt en mode {model_type}.")
    pass


# ==============================================================================
#  ÉTAPE 1b : ROUTE SPLITTER / CLASSIFIER (Anti Context-Bleeding)
# ==============================================================================

def step1b_strategic_analysis(full_text: str, model: str):
    """Agent Stratège (ScientificIntentAnalyst) V4.3.
    
    Identifie l'intention scientifique, extrait le contexte global et isole les
    voies de synthèse distinctes par citation exacte pour empêcher le Context Bleeding.
    
    Returns:
        SynthesisStrategy (objet Pydantic complet)
    """
    logger.info("ÉTAPE 1b — Agent Stratège (ScientificIntentAnalyst)")
    
    sys_prompt = AGENT_PROMPTS.get("agent_stratege", {}).get(
        "system_prompt",
        "Tu es l'Agent Stratège."
    )
    user_prompt = f"TEXTE COMPLET :\n{full_text[:8000]}"
    
    from synthgraph.schemas.core import SynthesisStrategy
    agent = get_agent("AgentStratege", sys_prompt, model, role="strategist")
    data = agent.generate_validated_json(user_prompt, schema_model=SynthesisStrategy)
    append_transcript("AgentStratege", model, sys_prompt, user_prompt, agent)

    if not data or "error" in data:
        logger.warning("[AgentStratege] Échec de l'extraction, fallback générique.")
        return None
        
    strategy = SynthesisStrategy.model_validate(data)
    total = len(strategy.pathways)
    
    logger.info(f"[AgentStratege] Intention : {strategy.intent}")
    logger.info(f"[AgentStratege] {total} route(s) identifiée(s)")
    for p in strategy.pathways:
        logger.info(f"  → {p.pathway_id}: {p.method_name}")
    
    # Log du Global Context
    gctx = strategy.global_context.model_dump()
    logger.info(f"[AgentStratege V4.3] GlobalContext extrait ✅ : {list(k for k, v in gctx.items() if v)}")
    
    save_step("step1b_strategy", strategy.model_dump())
    write_log(
        f"### Étape 1b : Agent Stratège V4.3\n"
        f"- Intention : {strategy.intent}\n"
        f"- Routes détectées : {total}\n"
        f"- Méthodes : {[p.method_name for p in strategy.pathways]}\n"
        f"- GlobalContext : {list(k for k, v in gctx.items() if v) if gctx else 'vide'}\n"
    )
    
    time.sleep(SLEEP_BETWEEN_STEPS)
    return strategy


# ==============================================================================
#  ÉTAPES DU PIPELINE
# ==============================================================================

def step1_read_pdf(file_path: str, use_marker: bool = False) -> dict:
    """Extraction texte depuis le PDF via PyMuPDF Vision."""
    logger.info("ÉTAPE 1/6 — Lecture PDF")

    # Utilisation du module Tool unifié
    from synthgraph.utils.tools import PDFReaderTool
    reader = PDFReaderTool()
    data = reader.process(file_path, use_marker=use_marker)
    text = data.get("full_text", "")
    exp_text = data.get("sections", {}).get("experimental", text)

    # Extraire section expérimentale
    low = text.lower()
    exp_idx = next((low.find(k) for k in ["experimental", "synthesis", "materials and methods"] if low.find(k) != -1), -1)
    exp_text = text[exp_idx:exp_idx+4000] if exp_idx != -1 else text[:4000]
    
    images = reader.extract_images(file_path)
    
    # Filtrer les balises [FIGURE DÉTECTÉE...] pour ne pas polluer le RAG
    text = re.sub(r'\[FIGURE DÉTECTÉE.*?\]', '', text)
    exp_text = re.sub(r'\[FIGURE DÉTECTÉE.*?\]', '', exp_text)

    result = {
        "full_text": text,
        "full_text_snippet": text[:500],
        "experimental_text": exp_text,
        "total_chars": len(text),
        "images": images
    }
    save_step("step1_pdf", {"full_text_snippet": text[:500], "total_chars": len(text), "images_count": len(images)})
    write_log(f"### Étape 1 : Lecture PDF\n- Chars : {len(text)}\n- Section exp : {len(exp_text)} chars\n- Images extraites : {len(images)}\n")
    return result


def step2_orchestrator(rag_context: str, model: str, route: dict = None) -> dict:
    """Orchestrateur : plan d'extraction structurée (Pydantic + RAG), scopé par route."""
    route_id = route.get("route_id", "route_1") if route else "route_1"
    method_type = route.get("method_type", "operation_generique") if route else "operation_generique"
    
    logger.info(f"ÉTAPE 2 — Orchestrateur (RAG) [Route: {route_id}]")
    sys_prompt = AGENT_PROMPTS.get("orchestrator", {}).get(
        "system_prompt", "Tu es l'Agent Orchestrateur."
    ).replace("{route_id}", route_id).replace("{method_type}", method_type)
    user_prompt = f"MORCEAUX PERTINENTS DU PDF :\n{rag_context}"

    agent = get_agent(f"Orchestrateur-{route_id}", sys_prompt, model, role="strategist")
    
    tools = [{
        "type": "function",
        "function": {
            "name": "get_route_definition",
            "description": "Retourne la définition standard et les étapes pour une méthode de synthèse donnée.",
            "parameters": {
                "type": "object",
                "properties": {
                    "route_name": {
                        "type": "string",
                        "description": "Nom de la méthode (ex: sol-gel, hydrothermal, solid-state, flux)"
                    }
                },
                "required": ["route_name"]
            }
        }
    }]
    
    data = agent.generate_validated_json(user_prompt, schema_model=OrchestratorPlan, tools=tools)
    append_transcript(f"Orchestrateur-{route_id}", model, sys_prompt, user_prompt, agent)

    if not data or "error" in data:
        data = {"reasoning": "Fallback par défaut car échec LLM.", "extraction_targets": [{"target_material": "Inconnu", "formula": "?", "synthesis_route": method_type, "key_steps": ["étape non identifiée"]}], "confidence": 0.5, "note": "fallback"}
    
    save_step(f"step2_orchestrator_{route_id}", {"parsed": data})
    write_log(f"### Étape 2 : Orchestrateur [{route_id}]\n```json\n{json.dumps(data, indent=2, ensure_ascii=False)[:600]}\n```\n")
    time.sleep(SLEEP_BETWEEN_STEPS)
    return data



# [V4.8] L'ancienne simulation trigger_vision_agent (« Données simulées ») est SUPPRIMÉE :
# elle injectait de l'hallucination par construction. Le vrai Agent Vision est dans
# synthgraph/agents/vision.py (PaliGemma, swap VRAM) et est appelé par step3c_vision_fill.


def step3c_vision_fill(extraction: dict, images: list, route_id: str,
                       max_queries: int = 4) -> tuple[dict, int]:
    """[V4.8] Comble les trous REQUIS via l'Agent Vision (PaliGemma) quand le papier
    met l'information dans une figure/table.

    Déclencheurs (besoin réel uniquement) :
      - paramètre requis manquant (missing_parameters severity='required'), OU
      - étape dont la citation renvoie à une table (citation_quality='reference_only').
    Règle d'or : la valeur lue porte `<param>_provenance = vision:<image>` dans le
    graphe (interprétation du modèle vision, PAS une citation textuelle). Réponse
    non exploitable → le trou RESTE déclaré. Config : settings.yaml `vision.enabled`.
    """
    # Config (défaut : activé si les poids existent)
    enabled = True
    try:
        import yaml
        from synthgraph.config import SETTINGS_PATH
        if Path(SETTINGS_PATH).exists():
            vcfg = (yaml.safe_load(open(SETTINGS_PATH, encoding="utf-8")) or {}).get("vision", {})
            enabled = bool(vcfg.get("enabled", True))
            max_queries = int(vcfg.get("max_queries", max_queries))
    except Exception:
        pass
    if not enabled or not images:
        return extraction, 0

    # Déclencheurs
    triggers = []  # (pathway, param_name, step_type, step_order, unit)
    for pw in extraction.get("pathways") or []:
        for mp in pw.get("missing_parameters") or []:
            if isinstance(mp, dict) and mp.get("severity", "required") == "required":
                triggers.append((pw, mp))
        has_table_ref = any(s.get("citation_quality") == "reference_only"
                            for s in pw.get("synthesis_steps") or [])
        if has_table_ref and not triggers:
            # les valeurs sont « dans la Table N » : re-vérifie les requis même recommandés
            for mp in (pw.get("missing_parameters") or [])[:2]:
                if isinstance(mp, dict):
                    triggers.append((pw, mp))
    if not triggers:
        return extraction, 0

    from synthgraph.agents.vision import VisionAgent, is_informative_answer
    agent = VisionAgent.get_instance()
    if not agent.available():
        logger.info(f"[{route_id}] Vision : poids PaliGemma absents — trous conservés tels quels.")
        return extraction, 0

    # Les 2 images les plus « riches » (taille fichier ≈ densité d'information)
    top_images = sorted(images, key=lambda p: Path(p).stat().st_size if Path(p).exists() else 0,
                        reverse=True)[:2]

    queries = []
    for pw, mp in triggers[:max_queries]:
        target = (pw.get("target_material") or {}).get("name", "the material")
        pname = str(mp.get("parameter", "")).replace("_", " ")
        for img in top_images:
            queries.append({
                "image": img, "pw_id": id(pw), "mp": mp,
                "question": (f"In this figure or table from a paper about the synthesis of {target}, "
                             f"what is the {pname} of the {mp.get('step_type', '')} step?"),
            })

    logger.info(f"[{route_id}] 👁️ Agent Vision : {len(triggers[:max_queries])} trou(s) requis, "
                f"{len(queries)} question(s) sur {len(top_images)} image(s) [swap VRAM]")
    results = agent.ask_batch(queries)

    from synthgraph.schemas.step_schema import convert_value
    filled = 0
    answered: set = set()
    for r in results:
        mp = r["mp"]
        key = (r["pw_id"], mp.get("parameter"), mp.get("step_order"))
        if key in answered or not is_informative_answer(r.get("answer")):
            continue
        val = convert_value(r["answer"], mp.get("unit"))
        if val is None or val == "":
            continue
        # Retrouver l'étape et remplir avec provenance explicite
        pw = next((p for p in extraction.get("pathways", []) if id(p) == r["pw_id"]), None)
        if pw is None:
            continue
        step = next((s for s in pw.get("synthesis_steps", [])
                     if s.get("order") == mp.get("step_order")), None)
        if step is None:
            continue
        param = mp.get("parameter")
        step[param] = val
        step[f"{param}_provenance"] = f"vision:{Path(r['image']).name}"
        pw["missing_parameters"] = [m for m in pw.get("missing_parameters", []) if m is not mp]
        answered.add(key)
        filled += 1
        logger.info(f"[{route_id}] 👁️ Vision a comblé {param}={val} (étape {mp.get('step_order')}, "
                    f"provenance {Path(r['image']).name}, réponse brute {r['answer']!r})")

    if filled:
        extraction["extraction_notes"] = (extraction.get("extraction_notes", "")
                                          + f" | {filled} paramètre(s) comblé(s) par l'Agent Vision")
    return extraction, filled

def step3_extractor(
    rag_context: str,
    orchestrator_plan: dict,
    model: str,
    images: list = None,
    rag_manager = None,
    route: dict = None,
    global_context: dict = None,
    directive: dict = None,
) -> dict:
    """
    [V4.3] Extracteur basé sur Tool Calling séquentiel (AgentExtracteurToolCaller).

    Phase 1 : Gemma construit l'ossature du template (méthode + étapes).
              Le template est renvoyé à l'Orchestrateur pour validation par le DebateEngine.
    Phase 2 : Gemma remplit les paramètres de chaque étape via insert_value().
              La mécanique de confirmation empêche l'écrasement silencieux de valeurs.

    [V4.3] global_context : variables communes à toute l'étude (extrait par le Stratège).
           Injecté dans le System Prompt de l'Extracteur pour éviter la 'Vision Tunnel'.

    Note : le modèle Gemma est choisi via le paramètre 'gemma_model' dans llm_config.
           PaliGemma est chargé automatiquement via model swap si ask_vision_agent() est appelé.
    """
    from synthgraph.agents.extractor import AgentExtracteurToolCaller

    route_id    = route.get("route_id",    "route_1")           if route else "route_1"
    method_type = route.get("method_type", "operation_generique") if route else "operation_generique"
    global_context = global_context or {}

    logger.info(f"ÉTAPE 3 V4.3 — AgentExtracteur Tool Calling [Route: {route_id}]")
    if global_context:
        logger.info(f"  [V4.3] GlobalContext injecté : {list(k for k,v in global_context.items() if v)}")

    # --- Résolution du modèle Gemma depuis la config ---
    gemma_model = AGENT_PROMPTS.get("extractor_tool_caller", {}).get(
        "model", "llama-3.1-8b-instruct"
    )

    # --- Mapping images (chemin) par référence figure ---
    images_map: dict = {}
    if images:
        for img_path in images:
            import os
            basename = os.path.basename(img_path)
            # Ex: "Figure_3.png" → "Fig. 3", "Table_1.png" → "Table 1"
            ref = basename.replace("_", " ").replace(".png", "").replace(".jpg", "")
            images_map[ref] = img_path
            images_map[basename] = img_path

    # ======== PHASE 1 : Template Builder ========
    agent = AgentExtracteurToolCaller(
        model=gemma_model,
    )

    logger.info(f"[{route_id}] Phase 1 — construction du template...")
    template = agent.run_phase1(rag_context, directive=directive)

    if isinstance(template, dict) and template.get("status") == "ABORTED":
        logger.warning(f"[{route_id}] Phase 1 ABANDONNÉE via Fail-Fast : {template.get('reason')}")
        write_log(f"### Étape 3 Phase 1 [{route_id}] — ABANDONNÉE (Fail-Fast)\nRaison : {template.get('reason')}\n")
        return template  # Renvoie le dict ABORTED directement

    save_step(f"step3_phase1_template_{route_id}", template.model_dump())
    write_log(
        f"### Étape 3 Phase 1 [{route_id}] — Template ({len(template.steps)} étapes)\n"
        f"```json\n{template.model_dump_json(indent=2)}\n```\n"
    )

    logger.info(f"[{route_id}] Phase 1 terminée ✅ — méthode: {template.synthesis_method}, {len(template.steps)} étapes")

    # ======== VALIDATION DU TEMPLATE (DebateEngine — Phase 1 only) ========
    # La Phase 2 sera déclenchée par step3b_fill_extraction() après validation.
    template_dict = template.model_dump()
    template_dict["route_id"]    = route_id
    template_dict["method_type"] = method_type
    template_dict["_v43_phase"]  = "template_ready"  # Flag pour le pipeline
    template_dict["_global_context"] = global_context  # [V4.3] Passe le contexte à la Phase 2
    template_dict["_directive"] = directive # [V4.6] Passe la directive à la Phase 2

    time.sleep(SLEEP_BETWEEN_STEPS)
    return template_dict


def step3b_fill_extraction(
    rag_context: str,
    validated_template_dict: dict,
    images: list = None,
    route: dict = None,
    global_context: dict = None,
    directive: dict = None,
) -> dict:
    """
    [V4.2] Phase 2 de l'extraction : remplissage des paramètres par Tool Calling.

    À appeler après que le DebateEngine a validé le template Phase 1.

    Args:
        rag_context              : texte source du chunk
        validated_template_dict  : template Phase 1 validé (dict issu de Phase1Template)
        images                   : liste des chemins d'images disponibles
        route                    : dict de la route courante
        global_context           : [V4.3] variables communes à toute l'étude

    Returns:
        dict compatible avec le DebateEngine (format pathways V4.1)
    """
    from synthgraph.agents.extractor import AgentExtracteurToolCaller
    from synthgraph.extraction.state import Phase1Template, TemplateStep

    route_id    = route.get("route_id",    "route_1")           if route else "route_1"
    method_type = route.get("method_type", "operation_generique") if route else "operation_generique"

    logger.info(f"ÉTAPE 3b V4.2 — Phase 2 Value Filler [Route: {route_id}]")

    # Reconstruire le Phase1Template depuis le dict validé
    try:
        validated_template = Phase1Template(**validated_template_dict)
    except Exception as e:
        logger.error(f"[{route_id}] Erreur reconstruction Phase1Template: {e}")
        # Fallback minimal
        validated_template = Phase1Template(
            synthesis_method=validated_template_dict.get("synthesis_method", method_type),
            synthesis_method_citation="(fallback)",
            steps=[],
        )

    # Mapping images
    images_map: dict = {}
    if images:
        import os
        for img_path in images:
            basename = os.path.basename(img_path)
            ref = basename.replace("_", " ").replace(".png", "").replace(".jpg", "")
            images_map[ref] = img_path

    gemma_model = AGENT_PROMPTS.get("extractor_tool_caller", {}).get(
        "model", "gemma-4-E4B" # Fallback value if not found
    )

    agent = AgentExtracteurToolCaller(model=gemma_model)

    # [V4.3] Récupère le global_context depuis le template_dict si non fourni explicitement
    effective_global_context = global_context or validated_template_dict.get("_global_context", {})
    effective_directive = directive or validated_template_dict.get("_directive", {})

    logger.info(f"[{route_id}] Phase 2 — remplissage des valeurs...")
    state = agent.run_phase2(rag_context, validated_template, images_map,
                             global_context=effective_global_context, directive=effective_directive)

    if isinstance(state, dict) and state.get("status") == "ABORTED":
        logger.warning(f"[{route_id}] Phase 2 ABANDONNÉE via Fail-Fast : {state.get('reason')}")
        write_log(f"### Étape 3b Phase 2 [{route_id}] — ABANDONNÉE (Fail-Fast)\nRaison : {state.get('reason')}\n")
        return state  # Renvoie le dict ABORTED directement

    # Export au format DebateEngine (compatible V4.1)
    extraction_dict = state.to_extraction_dict()
    extraction_dict["route_id"]    = route_id
    extraction_dict["method_type"] = method_type

    save_step(f"step3b_extraction_{route_id}", extraction_dict)
    write_log(
        f"### Étape 3b Phase 2 [{route_id}] — Extraction remplie\n"
        f"```json\n{json.dumps(extraction_dict, indent=2, ensure_ascii=False)[:1000]}\n```\n"
    )

    snap = state.get_state_snapshot()
    logger.info(
        f"[{route_id}] Phase 2 terminée ✅ — {snap['completion_percent']}% complet, "
        f"{state.phase2_call_count} tool calls, {len(state.vision_queries)} vision queries"
    )

    time.sleep(SLEEP_BETWEEN_STEPS)
    return extraction_dict


def step4_contextual(rag_context: str, extraction: dict, model: str, route: dict = None) -> dict:
    """Agent Contextuel : connaissances tacites et matière noire, scopé par route."""
    route_id = route.get("route_id", "route_1") if route else "route_1"
    method_type = route.get("method_type", "operation_generique") if route else "operation_generique"
    
    logger.info(f"ÉTAPE 4 — Agent Contextuel (RAG) [Route: {route_id}]")
    sys_prompt = AGENT_PROMPTS.get("contextual", {}).get(
        "system_prompt", "Tu es l'Agent d'Analyse Contextuelle."
    ).replace("{route_id}", route_id).replace("{method_type}", method_type)
    user_prompt = f"EXTRACTION BRUTE :\n{json.dumps(extraction, ensure_ascii=False)[:1000]}\n\nMORCEAUX DE DISCUSSIONS (RAG) :\n{rag_context}"

    agent = get_agent(f"Contextuel-{route_id}", sys_prompt, model, max_tokens=QA_MAX_TOKENS, role="qa")
    data = agent.generate_validated_json(user_prompt, schema_model=ContextualAnalysis)
    append_transcript(f"Contextuel-{route_id}", model, sys_prompt, user_prompt, agent)

    # Boucle de feedback vers l'Extracteur
    needs_extractor = data.get("needs_extractor_clarification", False)
    extractor_questions = data.get("extractor_questions", [])
    
    if needs_extractor and extractor_questions:
        logger.info(f"[Multi-Agents] L'Agent Contextuel demande {len(extractor_questions)} clarifications à l'Extracteur !")
        
        sys_clarify = AGENT_PROMPTS.get("extractor_clarify", {}).get(
            "system_prompt", "Tu es l'Agent Extracteur."
        ).replace("{route_id}", route_id).replace("{method_type}", method_type)
        questions_str = "\n".join([f"- {q}" for q in extractor_questions])
        user_clarify = f"QUESTIONS :\n{questions_str}\n\nMORCEAUX EXPERIMENTAUX (RAG) :\n{rag_context}"
        
        agent_clarify = get_agent(f"Extracteur-Clarif-{route_id}", sys_clarify, model, max_tokens=QA_MAX_TOKENS, role="qa")
        clarify_data = agent_clarify.generate_validated_json(user_clarify, schema_model=ExtractorClarification)
        append_transcript(f"Extracteur-Clarif-{route_id}", model, sys_clarify, user_clarify, agent_clarify)
        if not clarify_data or "error" in clarify_data:
            clarify_data = {"reasoning": "Erreur", "answers": ["Information non trouvée"]}
            
        logger.info("[Contextuel] Deuxième passe avec les réponses de l'Extracteur...")
        answers_str = "\n".join(clarify_data.get("answers", []))
        user_prompt_with_answers = user_prompt + f"\n\nREPONSES DE L'EXTRACTEUR :\n{answers_str}"
        
        agent_pass2 = get_agent(f"Contextuel-{route_id} (Passe 2)", sys_prompt, model, max_tokens=QA_MAX_TOKENS, role="qa")
        data2 = agent_pass2.generate_validated_json(user_prompt_with_answers, schema_model=ContextualAnalysis)
        append_transcript(f"Contextuel-{route_id} (Passe 2)", model, sys_prompt, user_prompt_with_answers, agent_pass2)
        if data2 and "error" not in data2:
            data = data2

    if not data or "error" in data:
        # [V4.5/C3] FAIL-CLOSED : l'agent a échoué → on le déclare, on n'invente RIEN.
        # (L'ancien fallback injectait de la matière noire FICTIVE — ex: 'TiO2_350C'.)
        logger.error(f"[Contextuel-{route_id}] Échec de l'agent — aucune analyse contextuelle (fail-closed).")
        data = {
            "reasoning": "ÉCHEC de l'Agent Contextuel : aucune analyse effectuée. Aucune donnée inventée (fail-closed).",
            "implicit_atmosphere": None,
            "optimization_hints": [],
            "dark_matter": [],
            "tacit_knowledge": [],
            "missing_critical_info": [],
            "contextual_confidence": 0.0,
            "note": "QA_AGENT_FAILED",
        }
    save_step(f"step4_contextual_{route_id}", {"parsed": data})
    write_log(
        f"### Étape 4 : Agent Contextuel\n"
        f"- Atmosphère implicite : {data.get('implicit_atmosphere','?')}\n"
        f"- Matière noire : {len(data.get('dark_matter',[]))} items\n"
        f"```json\n{json.dumps(data, indent=2, ensure_ascii=False)[:800]}\n```\n"
    )
    time.sleep(SLEEP_BETWEEN_STEPS)
    return data

def _format_extraction_for_debate(extraction: dict, max_chars: int = 4500) -> str:
    """[V4.5/C2] Sérialise l'extraction COMPLÈTE en tableau texte compact pour le débat.

    Remplace `json.dumps(extraction)[:800]` qui tronquait la recette après ~2 étapes :
    le Thermodynamicien ne pouvait physiquement pas voir ce qu'il validait.
    ~30-60 chars/paramètre → une recette de 15 étapes tient en ~2000 chars.
    """
    lines = []
    pathways = extraction.get("pathways") or [extraction] if isinstance(extraction, dict) else []
    for pw in pathways:
        if not isinstance(pw, dict):
            continue
        tgt = pw.get("target_material") or {}
        tgt_name = tgt.get("name") or tgt.get("formula") or "?" if isinstance(tgt, dict) else str(tgt)
        lines.append(f"CIBLE: {tgt_name} | MÉTHODE: {pw.get('synthesis_route', '?')} "
                     f"| VARIANTE: {pw.get('variant_id', 'v1')}")
        precs = pw.get("precursors") or []
        if precs:
            lines.append("PRÉCURSEURS: " + "; ".join(
                f"{p.get('name', '?')} ({p.get('role', 'reactant')}"
                + (f", {p.get('amount')}" if p.get("amount") else "") + ")"
                for p in precs if isinstance(p, dict)))
        lines.append("ÉTAPES:")
        for st in pw.get("synthesis_steps") or []:
            if not isinstance(st, dict):
                continue
            parts = [f"#{st.get('order', '?')} {st.get('type', st.get('operation', '?'))}"]
            for key, label in (("temperature_c", "T°C"), ("target_temperature_c", "T_cible°C"),
                               ("from_temperature_c", "T_départ°C"), ("max_temperature_c", "T_max°C"),
                               ("duration_h", "t(h)"), ("ramp_rate_c_per_h", "rampe°C/h"),
                               ("cooling_rate_c_per_h", "refroid°C/h"), ("atmosphere", "atm"),
                               ("pressure_mpa", "P(MPa)"), ("solvent", "solvant"),
                               ("flux_material", "flux"), ("crucible_material", "creuset"),
                               ("quench_medium", "trempe"), ("equipment", "équip")):
                v = st.get(key)
                if v is not None and v != "":
                    parts.append(f"{label}={v}")
            cit = (st.get("citation") or "")[:90]
            if cit:
                parts.append(f'cit="{cit}"')
            lines.append("  " + " | ".join(parts))
        miss = [m for m in (pw.get("missing_parameters") or []) if isinstance(m, dict)]
        if miss:
            lines.append("PARAMÈTRES MANQUANTS DÉCLARÉS: " + "; ".join(
                f"étape {m.get('step_order', '?')} ({m.get('step_type', '?')}): {m.get('parameter', '?')}"
                for m in miss))
    out = "\n".join(lines)
    return out[:max_chars] if len(out) > max_chars else out


_GRIND_MENTION_RE = re.compile(r"intermediate\s+(?:re)?grind\w*|broyages?\s+interm\w*", re.IGNORECASE)


def _merge_sequential_variants(extraction: dict, focused_text: str) -> dict:
    """[V4.7.3] Fusion DÉTERMINISTE des fausses variantes séquentielles.

    Constaté sur Cava 1994 : '900°C, 24h; 1000°C, 60h; 1100°C, 60h with many
    intermediate grindings' extrait en 3 variantes au lieu d'UNE recette séquentielle
    avec rebroyages. Le retry LLM échouait (citations réécrites → rejetées par le
    grounding). Ici : zéro LLM — on réutilise les étapes DÉJÀ extraites et citées,
    on insère les 'grinding' avec la phrase réelle du texte comme citation.

    Conditions strictes (pour ne pas fusionner de VRAIES variantes) :
      - le texte mentionne des broyages intermédiaires ;
      - ≥2 variantes, même cible, mêmes précurseurs, même atmosphère ;
      - uniquement des étapes thermiques (+ mixing en tête) ;
      - températures de palier STRICTEMENT croissantes (900<1000<1100).
    """
    m = _GRIND_MENTION_RE.search(focused_text)
    pws = extraction.get("pathways") or []
    if not m or not pws:
        return extraction

    # Citation réelle du broyage : la phrase du texte contenant la mention
    _start = focused_text.rfind(".", 0, m.start()) + 1
    _end = focused_text.find(".", m.end())
    grind_citation = focused_text[_start:_end + 1 if _end != -1 else len(focused_text)].strip()[:200]

    PALIERS = {"soak", "calcination", "sintering", "annealing"}

    def _insert_grindings_in_sequence(pw) -> int:
        """Cas mono-variante : insère 'grinding' à chaque frontière palier→réchauffe
        (sémantique exacte de 'with intermediate grindings' en céramique)."""
        steps = sorted(pw.get("synthesis_steps") or [], key=lambda x: x.get("order") or 0)
        out, inserted = [], 0
        for i, s in enumerate(steps):
            out.append(s)
            nxt = steps[i + 1] if i + 1 < len(steps) else None
            if nxt and s.get("type") in PALIERS and nxt.get("type") == "heating":
                out.append({"type": "grinding", "operation": "intermediate grinding",
                            "citation": grind_citation})
                inserted += 1
        if inserted:
            for order, s in enumerate(out, 1):
                s["order"] = order
            from synthgraph.schemas.step_schema import normalize_steps
            pw["synthesis_steps"], pw["missing_parameters"] = normalize_steps(out)
        return inserted

    if len(pws) == 1:
        n_ins = _insert_grindings_in_sequence(pws[0])
        if n_ins:
            extraction["extraction_notes"] = (extraction.get("extraction_notes", "")
                                              + f" | {n_ins} broyage(s) intermédiaire(s) inséré(s) (déterministe)")
            logger.info(f"  🔗 [Grinding] {n_ins} broyage(s) intermédiaire(s) inséré(s) aux frontières "
                        f"palier→réchauffe (mention explicite dans le texte)")
        return extraction

    def _palier_temp(pw):
        temps = [s.get("temperature_c") or s.get("target_temperature_c")
                 for s in pw.get("synthesis_steps") or []]
        temps = [t for t in temps if isinstance(t, (int, float))]
        return max(temps) if temps else None

    def _prec_sig(pw):
        return tuple(sorted((p.get("name") or "").lower() for p in pw.get("precursors") or []))

    def _atm_sig(pw):
        return tuple(sorted({str(s.get("atmosphere")).lower()
                             for s in pw.get("synthesis_steps") or [] if s.get("atmosphere")}))

    THERMAL = {"heating", "soak", "cooling", "calcination", "sintering", "annealing"}
    targets = {((pw.get("target_material") or {}).get("name") or "") for pw in pws}
    if len(targets) != 1 or len({_prec_sig(pw) for pw in pws}) != 1 or len({_atm_sig(pw) for pw in pws}) != 1:
        return extraction
    for i, pw in enumerate(pws):
        steps = pw.get("synthesis_steps") or []
        allowed = THERMAL | ({"mixing"} if i == 0 else set())
        if not steps or not all(s.get("type") in allowed for s in steps):
            return extraction
    temps = [_palier_temp(pw) for pw in pws]
    if None in temps or any(b <= a for a, b in zip(temps, temps[1:])):
        return extraction

    # Citation réelle du broyage : la phrase du texte contenant la mention
    start = focused_text.rfind(".", 0, m.start()) + 1
    end = focused_text.find(".", m.end())
    grind_citation = focused_text[start:end + 1 if end != -1 else len(focused_text)].strip()[:200]

    merged_steps, order = [], 1
    for i, pw in enumerate(pws):
        for s in sorted(pw.get("synthesis_steps") or [], key=lambda x: x.get("order") or 0):
            s = dict(s)
            s["order"] = order
            merged_steps.append(s)
            order += 1
        if i < len(pws) - 1:
            merged_steps.append({"type": "grinding", "order": order,
                                 "operation": "intermediate grinding",
                                 "citation": grind_citation})
            order += 1

    from synthgraph.schemas.step_schema import normalize_steps
    merged_steps, missing = normalize_steps(merged_steps)

    base = dict(pws[0])
    base["variant_id"] = "v1"
    base["synthesis_steps"] = merged_steps
    base["missing_parameters"] = missing
    extraction["pathways"] = [base]
    extraction["extraction_notes"] = (extraction.get("extraction_notes", "")
                                      + f" | fusion séquentielle déterministe ({len(pws)} variantes → 1, "
                                      f"{len(merged_steps)} étapes, broyages intermédiaires insérés)")
    logger.info(f"  🔗 [Fusion séquentielle] {len(pws)} fausses variantes ({'→'.join(str(int(t)) for t in temps)}°C) "
                f"fusionnées en 1 recette de {len(merged_steps)} étapes avec broyages intermédiaires")
    return extraction


def _dedupe_directives(targets: list) -> list:
    """[V4.7] Déduplique les directives de l'Orchestrateur sur (cible, méthode).

    Constaté en run réel : 3 directives strictement identiques (Sr2IrO4/solid_state ×3)
    → 3 extractions + 3 boucles QA complètes payées pour la même recette (~40 min perdues).
    """
    seen, unique = set(), []
    for t in targets or []:
        if not isinstance(t, dict):
            continue
        key = (str(t.get("target_material", "")).strip().lower(),
               str(t.get("macro_method", "")).strip().lower())
        if key in seen:
            logger.warning(f"[Dédup directives] Directive ignorée (doublon cible+méthode) : "
                           f"{t.get('target_material')} / {t.get('macro_method')}")
            continue
        seen.add(key)
        unique.append(t)
    return unique


_CANONICAL_RECOMMENDATIONS = ("ACCEPT", "REJECT", "REVISE", "NEEDS_DATA", "QA_FAILED", "QA_SKIPPED")


def _deterministic_accept(extraction: dict, validation: dict) -> bool:
    """[V4.10 — validé par Terry] ACCEPT déterministe : le 8B ne dit jamais 'ACCEPT'
    franchement (tout sortait REVISE, même parfait). Si TOUTES les preuves objectives
    sont vertes, on promeut REVISE → ACCEPT sans avis LLM :
      - bilan élémentaire Python = OK (pas INDÉTERMINÉ, pas ÉCHEC) ;
      - zéro paramètre REQUIS manquant ;
      - zéro élément suspect (citation_grounded / name_grounded = false).
    Le REJECT (déterministe ou LLM) et le QA_FAILED ne sont JAMAIS promus.
    """
    fv = (validation or {}).get("final_validation", {}) or {}
    if fv.get("stoichiometry_verdict") != "OK":
        return False
    # [V4.11] Garde audit 4.1 : une extraction sans pathway (ou sans contenu) ne
    # peut PAS être promue — "rien à vérifier" n'est pas "vérifié".
    pathways = (extraction or {}).get("pathways") or []
    if not pathways or not any(isinstance(p, dict) and p.get("synthesis_steps")
                               and p.get("precursors") for p in pathways):
        return False
    for pw in (extraction or {}).get("pathways", []):
        if not isinstance(pw, dict):
            continue
        for m in pw.get("missing_parameters") or []:
            if isinstance(m, dict) and m.get("severity", "required") == "required":
                return False
        for item in list(pw.get("synthesis_steps") or []) + list(pw.get("precursors") or []):
            if isinstance(item, dict) and (item.get("citation_grounded") is False
                                           or item.get("name_grounded") is False):
                return False
    return True


def _normalize_recommendation(data: dict, agent_label: str) -> None:
    """[V4.5] Force `recommendation` sur une valeur CANONIQUE.

    Constaté en run réel : Llama-3.1-8B remplit parfois le champ avec une phrase
    libre ('Vérifiez la température...') qui finissait écrite telle quelle dans
    p.qa_status. Une phrase libre = réserve exprimée → 'REVISE' (jamais ACCEPT
    par défaut). La phrase d'origine est conservée dans `recommendation_raw`.
    """
    if not isinstance(data, dict):
        return
    raw = str(data.get("recommendation") or "").strip()
    s = raw.upper()
    canon = next((c for c in _CANONICAL_RECOMMENDATIONS if c in s), None)
    if canon is None:
        # Négatifs D'ABORD : 'INVALIDE' contient 'VALIDE' (piège de sous-chaîne)
        if any(k in s for k in ("REJET", "REFUS", "INVALID", "INCORRECT", "FAUX")):
            canon = "REJECT"
        elif any(k in s for k in ("ACCEPTÉ", "ACCEPTE", "VALIDÉ", "VALIDE", "APPROVED")):
            canon = "ACCEPT"
        else:
            canon = "REVISE"
    if canon != raw:
        data["recommendation_raw"] = raw
        data["recommendation"] = canon
        logger.info(f"[{agent_label}] recommendation normalisée : {raw[:60]!r} → {canon}")


def _apply_deterministic_veto(data: dict, stoich_report: dict, agent_label: str):
    """[V4.5/C1] Applique la règle de veto en ancrant le bilan élémentaire sur le
    rapport Python déterministe (quand disponible) au lieu de l'auto-déclaration LLM.

    - stoich ok=True  → mass_balance/all_precursors validés déterministiquement
    - stoich ok=False → REJECT forcé (veto déterministe)
    - stoich None/INDÉTERMINÉ → on garde les booléens du LLM (comportement V4.4)
    Ne touche pas aux réponses fail-closed (QA_AGENT_FAILED).
    """
    if not isinstance(data, dict) or data.get("note") == "QA_AGENT_FAILED":
        return
    audit = dict(data.get("audit_checklist") or {})
    if stoich_report is not None and stoich_report.get("ok") is not None:
        audit["mass_balance_mathematically_verified"] = bool(stoich_report["ok"])
        audit["all_precursors_accounted_for"] = bool(stoich_report["ok"])
        data["stoichiometry_verdict"] = stoich_report["verdict"]
        # [V4.7] Un ÉCHEC déterministe force REJECT quel que soit l'avis du LLM
        # (constaté : le LLM répond REVISE → le protocole sortait REVISE au lieu
        # de REJECT alors que le bilan atomique était mathématiquement faux).
        if stoich_report["ok"] is False:
            if data.get("recommendation") != "REJECT":
                logger.warning(f"[{agent_label}] Veto DÉTERMINISTE : REJECT forcé "
                               f"(bilan élémentaire ÉCHEC : {stoich_report['missing_elements']})")
            data["recommendation"] = "REJECT"
    data["audit_checklist"] = audit
    if not audit.get("mass_balance_mathematically_verified", False) or \
       not audit.get("temperature_matches_phase_diagram", False) or \
       not audit.get("all_precursors_accounted_for", False):
        if data.get("recommendation") == "ACCEPT":
            logger.warning(f"[{agent_label}] Veto : REJECT forcé (audit_checklist={audit})")
            data["recommendation"] = "REJECT"


def summarize_debate_history(debate_log: list, model: str) -> str:
    """Compresse l'historique des débats si trop long pour la VRAM."""
    if not debate_log:
        return "Aucun"
        
    history_str = json.dumps(debate_log, ensure_ascii=False)
    # Approximation : 1 token ~= 4 caractères
    if len(history_str) > 2500 * 4:
        logger.warning("Historique de débat très lourd (>2500 tokens approx). Compression en cours...")
        sys_prompt = "Tu es un agent de compression. Résume l'historique du débat en gardant uniquement les points de blocage et résolutions critiques."
        agent = get_agent("Compressor", sys_prompt, model, max_tokens=QA_MAX_TOKENS, role="qa")
        msg = agent.call(f"Historique brut : {history_str}")
        return msg.content
    return history_str


def step5_thermodynamician(extraction: dict, context: dict, model: str, route: dict = None) -> dict:
    """Agent Thermodynamicien : débat et validation QA, scopé par route."""
    route_id = route.get("route_id", "route_1") if route else "route_1"
    method_type = route.get("method_type", "operation_generique") if route else "operation_generique"
    
    logger.info(f"ÉTAPE 5 — Débat Thermodynamicien ↔ Contextuel [Route: {route_id}]")
    write_log(f"### Étape 5 : Débat inter-agents [{route_id}]\n")

    debate_log = []
    final_thermo = {}

    # [V4.5/C2] L'extraction COMPLÈTE en tableau compact (fini le json[:800])
    extraction_table = _format_extraction_for_debate(extraction)

    # [V4.5/C1] Bilan élémentaire DÉTERMINISTE (Python, zéro VRAM) — remplace
    # l'auto-déclaration LLM de la stœchiométrie (l'Agent Exécuteur n'était jamais appelé).
    stoich_report = None
    try:
        from synthgraph.validation.deterministic import element_balance_report
        _pw0 = (extraction.get("pathways") or [{}])[0] if isinstance(extraction, dict) else {}
        _tgt = _pw0.get("target_material") or {}
        _target_f = (_tgt.get("formula") or _tgt.get("name") or "") if isinstance(_tgt, dict) else str(_tgt)
        _prec_fs = [p.get("formula") or p.get("name") or "" for p in (_pw0.get("precursors") or [])
                    if isinstance(p, dict)]
        if _target_f and _prec_fs:
            stoich_report = element_balance_report(_prec_fs, _target_f)
            if stoich_report:
                logger.info(f"[Stoich-{route_id}] Verdict déterministe : {stoich_report['verdict']} "
                            f"— {stoich_report['detail'][:150]}")
                write_log(f"🧮 [Stœchiométrie Python] {stoich_report['verdict']} : {stoich_report['detail']}\n")
    except Exception as e:
        logger.warning(f"[Stoich-{route_id}] Vérification déterministe indisponible : {e}")

    stoich_block = ""
    if stoich_report:
        stoich_block = (f"\nRAPPORT STŒCHIOMÉTRIQUE DÉTERMINISTE (calculé par Python, FIABLE — "
                        f"ne le recalcule pas toi-même) :\n{stoich_report['detail']}\n")

    for round_num in range(1, 3):  # 2 rounds max
        logger.info(f"  Round {round_num}/2...")
        write_log(f"```\n{'─'*60}\n📢 ROUND {round_num}/2 [{route_id}]\n{'─'*60}")

        history_summary = summarize_debate_history(debate_log, model)
        sys_thermo = AGENT_PROMPTS.get("thermodynamic_critic", {}).get(
            "system_prompt", "Tu es l'Agent Thermodynamicien."
        ).replace("{route_id}", route_id).replace("{method_type}", method_type)

        # Dual-RAG: Étape A (Génération de Query)
        bible_query_prompt = f"EXTRACTION À VALIDER (recette complète) :\n{extraction_table[:2500]}\nANALYSE CONTEXTUELLE : {json.dumps(context, ensure_ascii=False)[:500]}\nHISTORIQUE DU DÉBAT : {history_summary}\n\nQuelle est la question thermodynamique ou cinétique la plus critique à poser à notre base de littérature (la 'Bible') pour valider cette extraction ? Formule une seule question claire. Réponds EXCLUSIVEMENT avec le JSON attendu pour le schéma BibleQuery."
        
        agent_bible = get_agent(f"Thermo-{route_id}-BibleQuery-R{round_num}", sys_thermo, model, max_tokens=QA_MAX_TOKENS, role="qa")
        bible_query_data = agent_bible.generate_validated_json(bible_query_prompt, schema_model=BibleQuery)
        append_transcript(f"Thermo-{route_id}-BibleQuery-R{round_num}", model, sys_thermo, bible_query_prompt, agent_bible)
        
        bible_context = ""
        if bible_query_data and "query" in bible_query_data:
            query = bible_query_data["query"]
            write_log(f"   → 📚 Question posée à la Bible : {query}")
            
            # Étape B (Interrogation)
            try:
                bible_rag = BibleRAG() # Lazy init
                bible_results = bible_rag.query_bible(query)
                if bible_results and "Avertissement" not in bible_results:
                    write_log(f"   → 📚 Extraits récupérés de la Bible.")
                    bible_context = f"\nEXTRAITS DE LA LITTÉRATURE (LA 'BIBLE') :\n{bible_results}\nUtilise ces extraits pour justifier ta validation (champ 'bible_justification')."
            except Exception as e:
                logger.error(f"Erreur BibleRAG : {e}")

        # Étape C (Validation finale) — [V4.5/C2] recette complète + rapport Python
        user_thermo = (f"EXTRACTION (recette complète) :\n{extraction_table}\n"
                       f"{stoich_block}"
                       f"ANALYSE CONTEXTUELLE : {json.dumps(context, ensure_ascii=False)[:800]}\n"
                       f"HISTORIQUE DU DÉBAT : {history_summary}")
        if bible_context:
            user_thermo += "\n" + bible_context

        agent_thermo = get_agent(f"Thermo-{route_id}-R{round_num}", sys_thermo, model, max_tokens=QA_MAX_TOKENS, role="qa")
        thermo_data = agent_thermo.generate_validated_json(user_thermo, schema_model=DebateValidation)
        append_transcript(f"Thermo-{route_id}-R{round_num}", model, sys_thermo, user_thermo, agent_thermo)
        if not thermo_data or "error" in thermo_data:
            # [V4.5/C3] FAIL-CLOSED : un validateur qui échoue ne valide PAS (plus de
            # fallback ACCEPT/0.80 — c'était un veto qui échouait en mode 'tout accepter').
            logger.error(f"[Thermo-{route_id}] Échec de l'agent — validation impossible (fail-closed).")
            thermo_data = {"reasoning": "ÉCHEC LLM : aucune validation thermodynamique effectuée.",
                           "temp_risks": [], "atmosphere_ok": False,
                           "overall_confidence": 0.0, "recommendation": "QA_FAILED",
                           "issues": ["Agent Thermodynamicien indisponible — protocole NON validé"],
                           "audit_checklist": {}, "note": "QA_AGENT_FAILED"}

        # [V4.5] Recommendation canonique (le LLM répond parfois en phrase libre)
        _normalize_recommendation(thermo_data, f"Thermo-{route_id}")

        # VETO RULE [V4.5/C1] : le bilan élémentaire vient du rapport PYTHON
        # (déterministe), plus de l'auto-déclaration du LLM. La température reste
        # jugée par le LLM (informé par la Bible).
        _apply_deterministic_veto(thermo_data, stoich_report, "Thermo")

        # Log Thermodynamicien message to status
        msg_thermo = {
            "round": round_num,
            "agent": "Thermodynamicien",
            "confidence": thermo_data.get("overall_confidence", 0.80),
            "recommendation": thermo_data.get("recommendation", "ACCEPT"),
            "issues": thermo_data.get("issues", []),
            "temp_risks": thermo_data.get("temp_risks", [])
        }
        update_status(debate_message=msg_thermo)

        write_log(
            f"⚗️  [Thermodynamicien] conf={thermo_data.get('overall_confidence',0):.2f} | "
            f"rec={thermo_data.get('recommendation','?')}\n"
            f"   Issues : {thermo_data.get('issues',[])}\n"
            f"   Risques T° : {thermo_data.get('temp_risks',[])}"
        )
        time.sleep(SLEEP_BETWEEN_STEPS)

        # [V4.5/C3] Validateur en échec → on interrompt le débat (fail-closed),
        # pas la peine de payer un round de plus avec un agent indisponible.
        if thermo_data.get("recommendation") == "QA_FAILED":
            debate_log.append({"round": round_num, "thermo": thermo_data,
                               "contextual_reply": None, "issue": "QA_FAILED"})
            final_thermo = thermo_data
            write_log("❌ QA_FAILED — débat interrompu (fail-closed)\n```\n")
            break

        sys_ctx_reply = AGENT_PROMPTS.get("contextual_reply", {}).get(
            "system_prompt", "Tu es l'Agent Contextuel."
        ).replace("{route_id}", route_id).replace("{method_type}", method_type)
        user_ctx_reply = f"ANALYSE THERMO : {json.dumps(thermo_data, ensure_ascii=False)[:500]}"

        agent_ctx_reply = get_agent(f"Contextuel-{route_id}-R{round_num}", sys_ctx_reply, model, max_tokens=QA_MAX_TOKENS, role="qa")
        ctx_reply = agent_ctx_reply.generate_validated_json(user_ctx_reply, schema_model=ContextualReply)
        append_transcript(f"Contextuel-{route_id}-R{round_num}", model, sys_ctx_reply, user_ctx_reply, agent_ctx_reply)
        if not ctx_reply or "error" in ctx_reply:
            # [V4.5/C3] FAIL-CLOSED : pas de résolution inventée ('La calcination en air
            # est correcte' était une affirmation chimique fabriquée).
            logger.error(f"[Contextuel-{route_id}-R{round_num}] Échec de l'agent — aucune réponse (fail-closed).")
            ctx_reply = {"reasoning": "ÉCHEC LLM : aucune réponse du Contextuel.", "resolution": [],
                         "additional_tacit": [], "contextual_confidence": 0.0,
                         "recommendation": "QA_FAILED", "audit_checklist": {}, "note": "QA_AGENT_FAILED"}

        # VETO RULE [V4.5/C1] : même ancrage déterministe pour le Contextuel
        _normalize_recommendation(ctx_reply, f"Contextuel-{route_id}")
        _apply_deterministic_veto(ctx_reply, stoich_report, "Contextuel")

        # Log Contextuel message to status
        msg_ctx = {
            "round": round_num,
            "agent": "Contextuel",
            "confidence": ctx_reply.get("contextual_confidence", 0.85),
            "recommendation": ctx_reply.get("recommendation", "ACCEPT"),
            "resolution": ctx_reply.get("resolution", [])
        }
        update_status(debate_message=msg_ctx)

        write_log(
            f"🧠 [Contextuel] conf={ctx_reply.get('contextual_confidence',0):.2f} | "
            f"recommendation={ctx_reply.get('recommendation','?')}\n"
            f"   Résolutions : {ctx_reply.get('resolution',[])[:2]}"
        )
        time.sleep(SLEEP_BETWEEN_STEPS)

        debate_log.append({
            "round": round_num, "thermo": thermo_data,
            "contextual_reply": ctx_reply, "issue": str(thermo_data.get("issues", [])[:1])
        })
        final_thermo = thermo_data

        if thermo_data.get("recommendation") == "ACCEPT":
            write_log(f"✅ CONSENSUS ATTEINT au round {round_num}\n```\n")
            break
        else:
            write_log(f"🔄 Pas de consensus — round suivant...\n")

    write_log(f"```\n**Débat terminé** | Décision : {final_thermo.get('recommendation','ACCEPT')}\n")
    result = {"debate_rounds": debate_log, "final_validation": final_thermo, "recommendation": final_thermo.get("recommendation", "ACCEPT")}
    save_step(f"step5_thermo_debate_{route_id}", result)
    return result



def step5b_red_team_audit(extraction: dict, context: dict, thermo_validation: dict,
                          model: str, route: dict = None) -> dict:
    """Audit Red Team avec droit de veto structuré, scopé par route."""
    route_id = route.get("route_id", "route_1") if route else "route_1"
    method_type = route.get("method_type", "operation_generique") if route else "operation_generique"
    protocol_id = f"Protocol_{method_type}_{route_id}"
    
    logger.info(f"ÉTAPE 5b — Audit Red Team [Route: {route_id}]")
    
    # Red Team scopée par route
    sys_rt = AGENT_PROMPTS.get("red_team", {}).get(
        "system_prompt", "Tu es la Red Team."
    ).replace("{route_id}", route_id).replace("{method_type}", method_type)
    # [V4.5/C2] Recette complète en tableau compact (fini le json[:800])
    user_rt = (
        f"EXTRACTION (recette complète):\n{_format_extraction_for_debate(extraction)}\n"
        f"CONTEXTE:\n{json.dumps(context, ensure_ascii=False)[:500]}\n"
        f"VALIDATION THERMO:\n{json.dumps(thermo_validation.get('final_validation', thermo_validation), ensure_ascii=False)[:600]}"
    )
    
    agent_rt = get_agent(f"RedTeam-{route_id}", sys_rt, model, max_tokens=QA_MAX_TOKENS, role="qa")
    rt_data = agent_rt.generate_validated_json(user_rt, schema_model=RedTeamAudit)
    append_transcript(f"RedTeam-{route_id}", model, sys_rt, user_rt, agent_rt)
    if not isinstance(rt_data, dict) or not rt_data or "error" in rt_data:
        rt_data = {"reasoning": "Fallback RedTeam", "critical_questions": ["Avez-vous bien vérifié ?"]}
    
    # Défenseur avec droit de veto
    sys_ctx_audit = AGENT_PROMPTS.get("contextual_audit_reply", {}).get(
        "system_prompt", "Tu es le Défenseur."
    ).replace("{route_id}", route_id
    ).replace("{method_type}", method_type
    ).replace("{protocol_id}", protocol_id)
    user_ctx_audit = (
        f"QUESTIONS RED TEAM:\n{json.dumps(rt_data.get('critical_questions', []), ensure_ascii=False)}\n"
        f"SYNTHÈSE ACTUELLE (recette complète):\n{_format_extraction_for_debate(extraction)}"
    )
    
    agent_defense = get_agent(f"Defenseur-{route_id}", sys_ctx_audit, model, max_tokens=QA_MAX_TOKENS, role="qa")
    # [V4.13] Grammaire RÉACTIVÉE pour le Défenseur : le run 2026-07-15 a montré 3×
    # ValidationError ('reasoning' omis — le modèle réécrivait la synthèse au lieu de
    # répondre) → fallback JSON brut → QA_FAILED. La grammaire GBNF force l'ordre et la
    # présence des champs requis (vérifié : root ::= reasoning-kv , veto-decisions-kv ,
    # corrected-synthesis-kv ; additionalProperties:true sur corrected_synthesis, pas
    # d'objet vide forcé). Coût : sampling ~30-50 % plus lent, borné par QA_MAX_TOKENS.
    ctx_data = agent_defense.generate_validated_json(user_ctx_audit, schema_model=ContextualAuditReply)
    append_transcript(f"Defenseur-{route_id}", model, sys_ctx_audit, user_ctx_audit, agent_defense)
    if not isinstance(ctx_data, dict) or not ctx_data or "error" in ctx_data:
        ctx_data = {
            "reasoning": "Fallback", "veto_decisions": [],
            "corrected_synthesis": extraction, "parameters_declared_missing": []
        }

    # Log des décisions de veto
    # [V4.11.1] Après 3 échecs Pydantic, le fallback "JSON brut" peut livrer des
    # chaînes là où le schéma exige des dicts ('str' object has no attribute 'get'
    # constaté sur CBD_MnSe_pH_t1, run 2026-07-15) : la couche QA entière partait
    # en QA_FAILED alors que le débat thermo avait réussi. On filtre les entrées
    # non conformes au lieu de tout perdre.
    veto_decisions = [v for v in (ctx_data.get("veto_decisions") or []) if isinstance(v, dict)]
    absent_count = sum(1 for v in veto_decisions if v.get("decision") == "ABSENT_FROM_TEXT")
    confirmed_count = sum(1 for v in veto_decisions if v.get("decision") == "CONFIRMED")
    missing_params = [m for m in (ctx_data.get("parameters_declared_missing") or [])
                      if isinstance(m, dict)]
    
    logger.info(
        f"[Audit-{route_id}] Vetos: {len(veto_decisions)} décisions "
        f"(CONFIRMED={confirmed_count}, ABSENT={absent_count}) | "
        f"Paramètres manquants déclarés : {len(missing_params)}"
    )
    
    save_step(f"step5b_red_team_{route_id}", {"red_team": rt_data, "contextual_audit": ctx_data})
    write_log(
        f"### Étape 5b : Audit Red Team [{route_id}]\n"
        f"- Questions soulevées : {len(rt_data.get('critical_questions', []))}\n"
        f"- Décisions CONFIRMED : {confirmed_count}\n"
        f"- Décisions ABSENT_FROM_TEXT : {absent_count}\n"
        f"- Paramètres manquants : {len(missing_params)}\n"
    )
    corrected = ctx_data.get("corrected_synthesis") or extraction
    if not isinstance(corrected, dict):  # [V4.11.1] même garde que ci-dessus
        corrected = extraction
    return corrected, missing_params

def _paper_id_from_reference(reference: dict) -> str:
    """[V4.5/N1] Identifiant court et stable du papier pour préfixer tous les IDs du graphe.

    Priorité au DOI (identifiant canonique) ; sinon nom de fichier source ; sinon titre.
    Sans ce préfixe, deux papiers produisant le même route_id (ex: 'R1_t1') fusionnent
    silencieusement leurs protocoles via MERGE dans Neo4j.
    """
    doi = str(reference.get("doi") or "").strip()
    if doi and doi.upper() not in ("N/A", "NA", "NONE", "UNKNOWN", ""):
        key = f"doi:{doi.lower()}"
    else:
        key = f"file:{str(reference.get('source_file') or reference.get('title') or 'unknown').lower()}"
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:10]


def _sanitize_prop_key(key) -> str:
    """Assainit un nom de propriété Neo4j (les clés viennent parfois du LLM :
    espaces, tirets, unités → identifiant valide)."""
    clean = re.sub(r"_+", "_", re.sub(r"\W", "_", str(key))).strip("_")
    if not clean or clean[0].isdigit():
        clean = f"p_{clean}" if clean else "prop"
    return clean


def _clean_props(d: dict) -> dict:
    """Ne garde que les scalaires non vides, avec clés assainies (pas d'invention :
    une valeur absente reste absente, elle n'est jamais remplacée par un défaut)."""
    out = {}
    for k, v in (d or {}).items():
        if v is None or v == "" or isinstance(v, (dict, list)):
            continue
        out[_sanitize_prop_key(k)] = v
    return out


def _cypher_literal(v) -> str:
    """Rend une valeur Python en littéral Cypher (pour le fichier .cypher de relecture)."""
    if v is None:
        return "null"
    if isinstance(v, bool):
        return str(v).lower()
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, dict):
        inner = ", ".join(f"{k}: {_cypher_literal(val)}" for k, val in v.items())
        return "{" + inner + "}"
    if isinstance(v, list):
        return "[" + ", ".join(_cypher_literal(x) for x in v) + "]"
    s = str(v).replace("\\", "\\\\").replace("'", "\\'")
    return f"'{s}'"


def render_cypher(query: str, params: dict = None) -> str:
    """Substitue les $params par leurs littéraux échappés — uniquement pour produire
    le fichier .cypher lisible/rejouable. L'injection Neo4j réelle passe par le driver
    avec les paramètres natifs (pas de concaténation de chaînes)."""
    if not params:
        return query
    def _sub(m):
        name = m.group(1)
        return _cypher_literal(params[name]) if name in params else m.group(0)
    return re.sub(r"\$(\w+)", _sub, query)


def step6_graph_architect(extraction: dict, context: dict, validation: dict,
                           reference: dict, model: str, route: dict = None,
                           missing_params: list = None, qa_status: str = "UNKNOWN",
                           qa_basis: str = "none") -> list:
    """[V4.4] Construction DÉTERMINISTE du Cypher depuis l'extraction normalisée.

    [V4.5] Requêtes PARAMÉTRÉES ({"query": str, "params": dict}) : plus de
    concaténation de chaînes (N3), IDs préfixés par paper_id (N1) pour empêcher
    la fusion silencieuse de protocoles entre papiers.
    [V4.5/C4] `qa_status` (ACCEPT/REJECT/QA_SKIPPED/QA_FAILED/...) est écrit sur le
    nœud SynthesisProtocol : le verdict du débat est enfin visible dans le graphe.
    """
    route_id = route.get("route_id", "route_1") if route else "route_1"
    method_raw = (route.get("method_type") or route.get("synthesis_route")) if route else "operation_generique"
    method_type = str(getattr(method_raw, "value", method_raw))
    missing_params = missing_params or []

    logger.info(f"ÉTAPE 6 — Architecte Graphe DÉTERMINISTE [Route: {route_id}]")

    paper_id = _paper_id_from_reference(reference)

    # Récupérer TOUTES les pathways (variantes) — extraction ou corrected_synthesis
    pathways_list = []
    if isinstance(extraction, dict):
        pws = extraction.get("pathways", [])
        pathways_list = pws if pws else [extraction]

    # [V4.5] Pas de confiance inventée : si la QA n'a pas tourné, le score est null.
    conf = None
    if isinstance(validation, dict):
        conf = validation.get("final_validation", {}).get("overall_confidence")
    if not isinstance(conf, (int, float)):
        conf = None

    queries: list[dict] = []

    def add(query: str, params: dict):
        queries.append({"query": query, "params": params})

    # Reference — MERGE sur paper_id : un MERGE sur doi='N/A' fusionnerait
    # tous les papiers sans DOI en un seul nœud.
    add(
        "MERGE (r:Reference {paper_id: $paper_id})\n"
        "SET r.doi=$doi, r.title=$title, r.authors=$authors, r.year=$year, "
        "r.reliability_score=$score;",
        {"paper_id": paper_id,
         "doi": str(reference.get("doi", "N/A")),
         "title": str(reference.get("title", "Unknown"))[:120],
         "authors": str(reference.get("authors", "Unknown")),
         "year": reference.get("year"),
         "score": round(float(conf), 2) if conf is not None else None},
    )

    protocol_ids = []  # pour les relations VARIANT_OF
    total_precursors = 0
    total_ops = 0
    total_missing = 0

    for pw_idx, pw in enumerate(pathways_list):
        variant_id = pw.get("variant_id", f"v{pw_idx + 1}")
        base_pid = f"Protocol_{paper_id}_{route_id}"
        protocol_id = f"{base_pid}_{variant_id}" if len(pathways_list) > 1 else base_pid
        protocol_ids.append(protocol_id)

        target = pw.get("target_material", {}) or {}
        target_name = target.get("name") or target.get("formula") or "Unknown"
        target_name = _fix_ocr_formulas(target_name)
        precursors = pw.get("precursors", []) or []
        steps = pw.get("synthesis_steps", []) or []
        missing_all = list(pw.get("missing_parameters", []) or []) + list(missing_params or [])

        # SynthesisProtocol
        add(
            "MERGE (p:SynthesisProtocol {protocol_id: $pid})\n"
            "SET p.method_type=$method, p.route_id=$route, p.target=$target, "
            "p.variant_id=$variant, p.paper_id=$paper_id, "
            "p.qa_status=$qa_status, p.qa_basis=$qa_basis, p.qa_confidence=$qa_conf, "
            # [V4.18] provenance du ratio molaire + rendement expérimental (null si absent)
            "p.ratio_source=$ratio_source, p.yield_percent=$yield_percent;",
            {"pid": protocol_id, "method": method_type, "route": route_id,
             "target": target_name, "variant": variant_id, "paper_id": paper_id,
             "qa_status": str(qa_status), "qa_basis": str(qa_basis),
             "qa_conf": round(float(conf), 2) if conf is not None else None,
             "ratio_source": pw.get("ratio_source"),
             "yield_percent": pw.get("yield_percent")},
        )
        add(
            "MATCH (p:SynthesisProtocol {protocol_id: $pid}), (r:Reference {paper_id: $paper_id})\n"
            "MERGE (p)-[:EXTRACTED_FROM]->(r);",
            {"pid": protocol_id, "paper_id": paper_id},
        )
        # Matériau cible
        tgt_id = f"{protocol_id}_target"
        add(
            "MERGE (n:Material {entity_id: $eid})\nSET n.name=$name, n.role='Target';",
            {"eid": tgt_id, "name": target_name},
        )
        add(
            "MATCH (n:Material {entity_id: $eid}), (p:SynthesisProtocol {protocol_id: $pid})\n"
            "MERGE (n)-[:SYNTHESIZED_VIA]->(p);",
            {"eid": tgt_id, "pid": protocol_id},
        )
        # Précurseurs
        for i, prec in enumerate(precursors):
            pid = f"{protocol_id}_prec_{i + 1}"
            pprops = _clean_props({
                "name": prec.get("name", ""), "formula": prec.get("formula", ""),
                "role": prec.get("role", "reactant"), "amount": prec.get("amount", ""),
                "citation": prec.get("citation", ""),
                "citation_grounded": prec.get("citation_grounded"),  # False si citation introuvable dans la source
                "name_grounded": prec.get("name_grounded"),          # False si le précurseur n'existe pas dans la source
                # [V4.18] quantités déterministes : ratio molaire (canonique),
                # moles et quantité brute en appui — absents si non ancrés.
                "molar_ratio": prec.get("molar_ratio"),
                "moles": prec.get("moles"),
                "amount_raw": prec.get("amount_raw"),
            })
            add(
                "MERGE (n:Material {entity_id: $eid})\nSET n += $props;",
                {"eid": pid, "props": pprops},
            )
            add(
                "MATCH (n:Material {entity_id: $eid}), (p:SynthesisProtocol {protocol_id: $pid})\n"
                "MERGE (n)-[:USED_IN {role: $role}]->(p);",
                {"eid": pid, "pid": protocol_id, "role": str(prec.get("role", "reactant"))},
            )
        # Opérations (étapes normalisées par type)
        for st in steps:
            order = st.get("order", 0)
            stype = st.get("type", st.get("operation", "operation"))
            op_id = f"{protocol_id}_op_{order}"
            opprops = {"step_type": stype, "order": order}
            for k, v in st.items():
                if k in ("type", "order", "operation", "step_name", "other_parameters", "variant_id"):
                    continue
                opprops[k] = v
            for k, v in (st.get("other_parameters") or {}).items():
                if k in ("variant_id", "type", "order", "operation"):
                    continue
                opprops[f"extra_{k}"] = v
            ungrounded_vals = extraction.get("ungrounded_values", [])
            if any(u.get("step") == order for u in ungrounded_vals):
                opprops["grounded"] = False
            add(
                "MERGE (n:Operation {entity_id: $eid})\nSET n += $props;",
                {"eid": op_id, "props": _clean_props(opprops)},
            )
            order_val = order if isinstance(order, (int, float)) else 0
            add(
                "MATCH (p:SynthesisProtocol {protocol_id: $pid}), (n:Operation {entity_id: $eid})\n"
                "MERGE (p)-[:HAS_STEP {order: $order}]->(n);",
                {"pid": protocol_id, "eid": op_id, "order": order_val},
            )
        # MissingParameter — Règle d'or : chaque trou du protocole est un nœud
        # VISIBLE, avec sa sévérité, relié au protocole ET à l'étape concernée.
        step_orders = {st.get("order") for st in steps if isinstance(st, dict)}
        for mp in missing_all:
            if isinstance(mp, dict):
                pname = mp.get("parameter") or mp.get("parameter_name") or "unknown"
                stype = mp.get("step_type", "")
                severity = mp.get("severity", "required")
                unit = mp.get("unit")
                step_order = mp.get("step_order")
            else:
                pname, stype, severity, unit, step_order = str(mp), "", "required", None, None
            # [V4.5] step_order dans l'ID : deux étapes du même type auxquelles il
            # manque le même paramètre ne fusionnent plus en un seul nœud.
            mp_id = (f"{protocol_id}_missing_{_sanitize_prop_key(pname)}_"
                     f"{_sanitize_prop_key(stype)}_{step_order if step_order is not None else 'x'}")
            add(
                "MERGE (n:MissingParameter {parameter_id: $mpid})\n"
                "SET n.parameter_name=$pname, n.step_type=$stype, n.severity=$severity, "
                "n.unit=$unit, n.step_order=$order;",
                {"mpid": mp_id, "pname": str(pname), "stype": str(stype),
                 "severity": str(severity), "unit": unit, "order": step_order},
            )
            add(
                "MATCH (p:SynthesisProtocol {protocol_id: $pid}), (n:MissingParameter {parameter_id: $mpid})\n"
                "MERGE (p)-[:REQUIRES_CLARIFICATION]->(n);",
                {"pid": protocol_id, "mpid": mp_id},
            )
            # [V4.5/Étape 4] Lien direct vers l'Operation : le chimiste voit QUELLE
            # étape du protocole est lacunaire, pas seulement 'quelque part'.
            if step_order is not None and step_order in step_orders:
                add(
                    "MATCH (op:Operation {entity_id: $oid}), (n:MissingParameter {parameter_id: $mpid})\n"
                    "MERGE (op)-[:MISSING_PARAM]->(n);",
                    {"oid": f"{protocol_id}_op_{step_order}", "mpid": mp_id},
                )

        total_precursors += len(precursors)
        total_ops += len(steps)
        total_missing += len(missing_all)

    # VARIANT_OF : relie chaque variante à la première (base)
    if len(protocol_ids) > 1:
        base_id = protocol_ids[0]
        for variant_pid in protocol_ids[1:]:
            add(
                "MATCH (base:SynthesisProtocol {protocol_id: $base_id}), "
                "(var:SynthesisProtocol {protocol_id: $var_id})\n"
                "MERGE (var)-[:VARIANT_OF]->(base);",
                {"base_id": base_id, "var_id": variant_pid},
            )

    save_step(f"step6_graph_{route_id}", {
        "queries_count": len(queries),
        "counts": {"precursors": total_precursors, "operations": total_ops,
                   "missing": total_missing, "variants": len(pathways_list)},
    })
    write_log(
        f"### Étape 6 : Architecte Graphe DÉTERMINISTE [{route_id}]\n"
        f"- {len(queries)} requêtes Cypher | {total_precursors} précurseurs, "
        f"{total_ops} opérations typées, {total_missing} paramètres manquants, "
        f"{len(pathways_list)} variante(s)\n"
    )
    logger.info(f"  → Cypher déterministe : {len(queries)} requêtes "
                f"({total_precursors} précurseurs, {total_ops} opérations, {len(pathways_list)} variante(s))")
    return queries

# ==============================================================================
#  PIPELINE PRINCIPAL
# ==============================================================================

METHOD_MARKERS = {
    "flux_growth": ["flux growth", "flux method", "molten flux", "flux"],
    "hydrothermal": ["hydrothermal", "autoclave", "solvothermal"],
    "sol_gel": ["sol-gel", "sol gel", "gel"],
    "solid_state": ["solid state", "solid-state", "ceramic"],
    "calcination": ["calcination", "calcine"],
    "sintering": ["sintering", "sinter"],
    "crystal_growth": ["crystal growth", "czochralski", "bridgman", "float zone"],
    "cvd": ["chemical vapor deposition", "cvd", "mocvd"],
    "pvd": ["physical vapor deposition", "pvd", "sputtering"],
    "ald": ["atomic layer deposition", "ald"],
    "coprecipitation": ["coprecipitation", "co-precipitation", "precipitation"],
}

def _fix_ocr_formulas(text: str) -> str:
    """Corrige les artefacts OCR courants dans les formules chimiques.
    - Zéro confondu avec O (oxygène) : Sr2Ir04 → Sr2IrO4
    - Espaces parasites dans les formules : Sr 2 IrO 4 → Sr2IrO4
    """
    import re
    # Pattern : Élément + chiffre + zéro + chiffre → probablement xOy (oxygène)
    # Ex: Ir04 → IrO4, Ti02 → TiO2, Fe203 → Fe2O3
    fixed = re.sub(r'([A-Z][a-z]?\d?)0(\d)', _ocr_zero_to_O, text)
    return fixed


def _ocr_zero_to_O(match):
    """Callback pour re.sub : remplace 0→O seulement si c'est dans un contexte de formule chimique."""
    prefix = match.group(1)
    suffix = match.group(2)
    # Vérifier que le préfixe se termine par une lettre (élément chimique)
    # ou par un chiffre précédé d'une lettre (stoéchiométrie)
    if prefix and prefix[-1].isalpha():
        return prefix + 'O' + suffix
    # Si le préfixe est type "Fe2" (chiffre), vérifier qu'il y a une lettre avant
    if len(prefix) >= 2 and prefix[-1].isdigit() and any(c.isalpha() for c in prefix):
        return prefix + 'O' + suffix
    return match.group(0)  # pas de correction


# [V4.16] Signaux quantitatifs d'une section expérimentale. Poids 2 pour les
# quantités chiffrées (mg/mmol/°C/h…), 3 pour les verbes de mode opératoire.
# NB : PAS de « ° » nu — les angles XRD des sections résultats (26.8°, 28.7°…)
# gonflaient leur score et volaient la fenêtre à la section expérimentale.
_RECIPE_QTY_RE = re.compile(
    r"\d+(?:\.\d+)?\s*(?:mg|mmol|mol|g\b|ml|mL|°C|℃|h\b|min\b|MPa|sccm|wt%|rpm|Hz)")
_RECIPE_VERB_RE = re.compile(
    r"\b(?:were|was)\s+(?:mixed|dissolved|dispersed|heated|stirred|washed|dried|"
    r"calcined|annealed|ground|ball-?milled|added|transferred|sintered|loaded|"
    r"precipitated|filtered|centrifuged|deposited|ignited|sealed|poured|prepared)\b",
    re.IGNORECASE)
# Signaux qu'on ne trouve QUE dans une section expérimentale : pureté, fournisseur,
# « used as received »… Poids fort : une phrase de résultats n'en contient jamais.
_RECIPE_EXP_RE = re.compile(
    r"\b(?:analytical grade|used as received|purchased|Sigma[- ]?Aldrich|Alfa Aesar|"
    r"Acros|Merck|Fisher|9[89](?:\.\d+)?\s*%|autoclave|crucible|Teflon|glove ?box|"
    r"Schlenk|muffle furnace)\b", re.IGNORECASE)


def _recipe_density(text: str) -> int:
    """Score déterministe : densité de signaux expérimentaux dans une fenêtre."""
    return (2 * len(_RECIPE_QTY_RE.findall(text))
            + 3 * len(_RECIPE_VERB_RE.findall(text))
            + 8 * len(_RECIPE_EXP_RE.findall(text)))


_CONSIGNE_UNITE = re.compile(
    r"\d+(?:[.,]\d+)?\s*(?:°\s*C|℃|\bC\b|\bh\b|\bhours?\b|\bmin\b|\bminutes?\b|"
    r"\bV\b|\bsccm\b|\bmbar\b|\bHz\b|\bmM\b|\bM\b|\brpm\b)", re.I)
_CONSIGNE_EXCLUE = re.compile(
    r"\b(?:xrd|sem|tem|stem|xps|ftir|raman|edx|eds|diffract\w*|spectr\w*|"
    r"microscop\w*|voltammetr\w*|measurement|measured|characteriz\w*|"
    r"et\s+al\.|fig\.|figure\s+\d)\b", re.I)


def _consignes_hors_fenetre(full_text: str, fenetre: str, method_type: str,
                            budget: int = 900) -> str:
    """Phrases porteuses de CONSIGNES de la methode cible, situees HORS fenetre.

    La focalisation choisit UNE fenetre contigue autour de la section
    experimentale. Or certains papiers donnent leurs conditions operatoires dans
    la DISCUSSION. Mesure du 21/08 sur `electro_nico` : « at the same
    temperature (60℃) ... duration of electrodeposition (2 hours) » et
    « a potential of -1.1, -1.2, and -1.3 V/Ag/Ag+ » n'atteignaient JAMAIS le
    modele. Il a extrait tout ce qu'on lui a donne — 12 appels, 11 acceptes —
    puis cloture. Son entree etait tronquee avant les valeurs.

    Selection VOLONTAIREMENT ETROITE : la phrase doit NOMMER le procede (un mot
    d'au moins huit lettres tire du `method_type`) ET porter une valeur avec son
    UNITE, et ne pas relever de la caracterisation. Si aucun mot du procede
    n'apparait dans le papier — cas d'un `method_type` francais sur un texte
    anglais — on n'ajoute RIEN : mieux vaut ne rien faire que rogner la fenetre
    des onze autres papiers.
    """
    mots = [m.lower() for m in re.findall(r"[A-Za-zÀ-ÿ]{8,}", method_type or "")]
    if not mots:
        return ""
    retenues, vus = [], set()
    for ph in re.split(r"(?<=[.;])\s+", full_text):
        ph = " ".join(ph.split())
        if not (40 < len(ph) < 520) or ph in vus:
            continue
        bas = ph.lower()
        if not any(m in bas for m in mots):
            continue
        # DEUX consignes au moins. La fenetre est saturee : tout caractere
        # ajoute en retire un a la recette, et l'echange n'en vaut la peine
        # que pour une phrase DENSE. Mesure : `solgel_cuo` declenchait le
        # bloc sur « precipitation » et « calcination », mots generiques qui
        # parsement sa discussion — il perdait 778 caracteres de recette
        # contre du commentaire, et a rendu 0 appel (0 accepte). La phrase
        # utile d'`electro_nico`, elle, porte QUATRE consignes.
        # SEUIL A TROIS, mesure : les trois phrases que `solgel_cuo`
        # proposait en portaient exactement DEUX — dont une qui decrit un
        # AUTRE travail (« For example, Cu(NO3)-salt solutions ... were
        # aged at 90 °C »). Les deux phrases utiles d'`electro_nico` en
        # portent QUATRE. Le seuil separe donc le commentaire de la
        # consigne sans reglage arbitraire.
        if len(_CONSIGNE_UNITE.findall(ph)) < 3 or _CONSIGNE_EXCLUE.search(ph):
            continue
        if ph[:60] in fenetre:          # deja vue par le modele
            continue
        vus.add(ph)
        retenues.append(ph)
    if not retenues:
        return ""
    # PRIORITE A LA DENSITE, pas a l'ordre du document. Le budget est etroit et
    # l'ABSTRACT parle du procede en premier : sur `electro_nico`, « Conversely,
    # when electrodeposition ... was performed at 60℃ » — UNE consigne —
    # evincait « at the same temperature (60℃), ion concentration (0.25 M
    # NiCl2 + 0.25 CoCl2) and the duration of electrodeposition (2 hours) »,
    # qui en porte quatre. A place egale, la phrase qui enonce le plus de
    # consignes vaut mieux.
    par_densite = sorted(enumerate(retenues),
                         key=lambda t: (-len(_CONSIGNE_UNITE.findall(t[1])), t[0]))
    gardees, total = [], 0
    for rang, ph in par_densite:
        if total + len(ph) + 1 > budget:
            continue
        gardees.append((rang, ph))
        total += len(ph) + 1
    # Restituees dans l'ordre du TEXTE : le modele lit une recette, pas un
    # classement.
    return "\n".join(ph for _, ph in sorted(gardees))


def _build_focused_text(full_text: str, rag, target: str, method_type: str) -> str:
    """Construit un texte focalisé qui contient la recette (précurseurs + programme
    thermique). Combine la fenêtre expérimentale (avec marge AVANT pour capter les
    tableaux) et des chunks RAG pertinents. Cap ~8500 chars (tient dans le contexte).
    """
    low = full_text.lower()
    markers = ["experimental", "synthesis", "sample prep", "crystal grow",
               "materials and methods", "preparation", "growth conditions",
               "starting material", "reagent", "precursor"]
    # [V4.16] TOUTES les occurrences de chaque marqueur, pas seulement la première :
    # sur un papier long (constaté : JACS CoSi, 88k chars), le premier « synthesis »
    # est dans le TITRE/intro → la fenêtre unique ratait la section expérimentale à
    # 60 % du document → 0 citation ancrable → 3 extractions fabriquées → NO_DATA.
    idxs = []
    for m in markers:
        start = 0
        while True:
            p = low.find(m, start)
            if p == -1:
                break
            idxs.append(p)
            start = p + 1

    rag_text = rag.query(
        f"{target} {method_type} precursors starting materials molar ratio temperature "
        f"furnace crucible atmosphere heating cooling rate dwell flux calcination sintering",
        n_results=5,
    )

    candidates = list(idxs)
    route_markers = METHOD_MARKERS.get(method_type, [])
    candidates += [low.find(m) for m in route_markers if low.find(m) != -1]
    if rag_text:
        first_chunk = rag_text.strip().split("\n")[0][:80]
        pos = full_text.find(first_chunk) if first_chunk else -1
        if pos != -1:
            candidates.append(pos)

    # [V4.16] Sélection par SCORE DE DENSITÉ DE RECETTE (déterministe, preuve
    # textuelle) : la bonne fenêtre est celle qui contient le plus de signaux
    # quantitatifs expérimentaux, pas la première occurrence d'un mot-clé.
    window = ""
    if candidates:
        best_i, best_score = None, -1
        for c in sorted(set(candidates)):
            cand = full_text[max(0, c - 2500): c + 6000]
            score = _recipe_density(cand)
            if score > best_score:
                best_i, best_score = c, score
        i = best_i
        window = full_text[max(0, i - 2500): i + 6000]

    combined = (window + "\n\n[EXTRAITS PERTINENTS]\n" + rag_text) if window else rag_text
    if not combined or len(combined) < 200:
        combined = rag.get_extraction_context()

    # Détection de références à des tableaux → inclure le corps si trouvé
    table_ref_re = re.compile(r"[Tt]ables?\s+\d+(?:\s*[-–]\s*\d+)?")
    search_zone = window or full_text[:12000]
    table_refs = list(table_ref_re.finditer(search_zone))
    if table_refs:
        table_extras = []
        seen_pos = set()
        for m in table_refs[:4]:
            ref_pos = full_text.find(m.group(0))
            if ref_pos < 0 or ref_pos in seen_pos:
                continue
            seen_pos.add(ref_pos)
            candidate = full_text[ref_pos: min(len(full_text), ref_pos + 4000)]
            table_lines = [l.strip() for l in candidate.splitlines()
                           if re.search(r"\d+\s*[°˚]\s*C|\d+\s*h\b|\d+\s*min\b", l) and len(l.strip()) > 5]
            if table_lines:
                table_extras.append("[TABLE RÉFÉRENCÉE: " + m.group(0) + "]\n" + "\n".join(table_lines[:25]))
        if table_extras:
            combined = combined + "\n\n" + "\n\n".join(table_extras)
            logger.info(f"  [P11] {len(table_extras)} tableau(x) référencé(s) inclus dans le texte focalisé")

    # [V4.15] Bible RETIRÉE du texte focalisé d'EXTRACTION. Historique : le bloc
    # [RÉFÉRENCE BIBLE] (1500 chars de manuel) devait « enrichir le contexte », mais
    # l'extraction est une copie-du-papier par définition — le manuel ne peut JAMAIS
    # être une source légitime d'étapes. Constaté sur PhysRevB (4 runs successifs) :
    # le 8B préfère systématiquement citer la recette du manuel (chromites de West)
    # plutôt que le court paragraphe expérimental du papier → 4 graphes sur 8
    # contaminés (audit rétroactif tools/audit_citations.py). La couche QA garde son
    # propre accès BibleRAG (usage légitime : VALIDER, pas extraire). Les gardes
    # V4.14.1/V4.14.2 (grounding paper-only + purge dure) restent en défense en
    # profondeur si un bloc Bible réapparaissait dans focused_text.

    # Les CONSIGNES situees hors de la fenetre sont ajoutees en RESERVANT leur
    # place : le plafond est une troncature dure, et ajouter apres coup les
    # aurait coupees — le correctif aurait ete inerte, comme cinq autres cette
    # nuit. On taille donc la fenetre AVANT de les concatener.
    consignes = _consignes_hors_fenetre(full_text, combined, method_type)
    if consignes:
        entete = "\n\n[CONSIGNES OPERATOIRES AILLEURS DANS LE TEXTE]\n"
        garde = 8500 - len(consignes) - len(entete)
        tete = combined[:max(0, garde)]
        # COUPER SUR UNE FRONTIERE DE PHRASE, jamais en plein mot. La fenetre
        # est TOUJOURS saturee a 8500 : le bloc prend donc forcement de la
        # place, et la premiere version tranchait au caractere pres —
        # « ... the freshly-was », « ... calomel electrode (SCE) we ». Sur
        # `solgel_cuo`, ce texte mutile a produit 0 appel (0 accepte) en 284 s :
        # une regression totale, d'une egalite stricte complete a rien.
        coupe = max(tete.rfind(". "), tete.rfind(".\n"), tete.rfind("\n\n"))
        if coupe > garde * 0.85:      # ne pas sacrifier plus de 15 % pour ca
            tete = tete[:coupe + 1]
        combined = tete + entete + consignes
        logger.info(f"  [focus] {consignes.count(chr(10)) + 1} phrase(s) de "
                    f"consigne recuperee(s) hors fenetre "
                    f"({len(combined) - len(tete)} car. pris a la fenetre)")

    return combined[:8500]


# [V4.14] Table de repli des confusables OCR pour le matching de grounding :
# 0 (zéro) → o, 1 (un) → l. Les vieux scans confondent systématiquement ces
# glyphes ('Ir02', 'A1203', 'flowing 02') et le LLM les re-normalise en citant.
_OCR_CONFUSABLES = str.maketrans("01", "ol")


# ══════════════════════════════════════════════════════════════════════════
# [A1 — V4.20] RE-ANCRAGE DES CITATIONS SUR LES LIGNES DE TABLEAU
#
# Diagnostic (17/08/2026) : en science des matériaux les conditions de synthèse
# vivent dans des TABLEAUX. opendataloader les reconstitue déjà en lignes
# complètes et citables — vérifié sur le papier « Crystal growth » :
#     - Sr214#2 1 : 2 : 7 1100◦C → (45◦C/h) 1300◦C → (8◦C/h) 900◦C → RT
# et `_build_focused_text` les inclut déjà dans la fenêtre du modèle.
# Le défaut n'est donc NI l'extraction NI la fenêtre : le modèle rattache une
# valeur juste (1300 °C, lue dans le tableau) à la phrase du texte courant
# (« The crucibles were heated in a programmable box furnace in air »), qui ne
# la contient pas. Conséquence mesurée : 22,6 % de valeurs justifiées seulement.
#
# Correction DÉTERMINISTE, sans appel LLM ni modification de prompt (leçon
# CLAUDE.md : lui faire réécrire ses citations les fait auto-rejeter).
# Règles arbitrées par Terry (17/08/2026) :
#   - valeur dans UNE SEULE ligne de tableau  → citation remplacée par la ligne
#   - valeur dans PLUSIEURS lignes            → conservée, marquée ambiguë,
#                                               jamais ré-ancrée (risque
#                                               d'attribuer une séquence à la
#                                               mauvaise recette)
#   - valeur INTROUVABLE partout              → purge + MissingParameter
# ══════════════════════════════════════════════════════════════════════════

# Socle historique, COMPLETE par le REGISTRE d'etapes — source unique. Cette
# liste etait recopiee a la main pendant que le registre vivait sa vie : au
# 21/08, DIX-NEUF colonnes numeriques echappaient au controle anti-invention,
# dont `voltage_v`, `gas_flow_sccm` et `from_temperature_c`. L'invariant est
# desormais verrouille par `tests/regression/test_couverture_grounding.py`.
try:
    from synthgraph.schemas.step_schema import colonnes_numeriques as _cn_reg
    _REGISTRE_NUM = tuple(sorted(_cn_reg()))
except Exception:  # noqa: BLE001 — le pipeline ne doit pas tomber pour si peu
    _REGISTRE_NUM = ()

_NUMERIC_STEP_KEYS = tuple(sorted({
    "temperature_c", "target_temperature_c", "from_temperature_c",
    "min_temperature_c", "max_temperature_c", "duration_h",
    "min_duration_h", "max_duration_h", "ramp_rate_c_per_h",
    "cooling_rate_c_per_h", "pressure_mpa", "speed_rpm", "concentration_mol_l",
} | set(_REGISTRE_NUM)))

# Une ligne de tableau porte des séparateurs de colonnes ou une séquence :
# « 1 : 2 : 7 », « 1300◦C → (8◦C/h) », « 900°C, 24 h; 1000°C, 60 h ».
_TABLE_ROW_HINT = re.compile(r"(→|->|\s:\s|;\s*\d|\|)|(\d\s*[°◦˚]\s*c.{0,40}\d\s*[°◦˚]\s*c)",
                             re.IGNORECASE)


def _candidate_table_rows(text: str) -> list[str]:
    """Lignes du texte source qui ressemblent à des lignes de tableau."""
    rows = []
    for raw in (text or "").splitlines():
        line = raw.strip().lstrip("-•*").strip()
        if len(line) < 12 or len(line) > 400:
            continue
        if _TABLE_ROW_HINT.search(line):
            rows.append(line)
    return rows


def _value_forms(val) -> list[str]:
    """Écritures possibles d'une valeur numérique dans le texte (24 / 24.0)."""
    try:
        f = float(val)
    except (TypeError, ValueError):
        return []
    forms = {f"{f:g}"}
    if f == int(f):
        forms.add(str(int(f)))
    return list(forms)


def _reanchor_values_on_table_rows(extraction: dict, focused_text: str,
                                   full_text: str = None) -> None:
    """Rattache chaque valeur numérique à la ligne de tableau qui la porte."""
    source = "\n".join(t for t in (focused_text, full_text) if t)
    rows = _candidate_table_rows(source)
    if not rows:
        return

    n_reanchored = n_ambiguous = 0
    purged_detail: list[str] = []

    for pw in extraction.get("pathways", []):
        for step in pw.get("synthesis_steps", []):
            # ATTENTION : PAS de repli OCR ici. `_OCR_CONFUSABLES` mappe 0→o et
            # 1→l : appliqué à un NOMBRE il le détruit (« 1150 » → « llso »), et
            # aucune valeur contenant 0 ou 1 ne pourrait plus être retrouvée.
            # Ce repli ne vaut que pour les mots (formules, atmosphères).
            cit = step.get("citation") or step.get("raw_text_citation") or ""
            cit_low = cit.lower()

            for key in _NUMERIC_STEP_KEYS:
                val = step.get(key)
                if val is None:
                    continue
                forms = _value_forms(val)
                if not forms:
                    continue

                # Déjà justifiée par sa propre citation : rien à faire.
                if any(re.search(rf"(?<![\d.]){re.escape(f)}(?![\d])", cit_low)
                       for f in forms):
                    continue

                matching = [r for r in rows
                            if any(re.search(rf"(?<![\d.]){re.escape(f)}(?![\d])", r.lower())
                                   for f in forms)]

                if len(matching) == 1:
                    step["citation"] = matching[0]
                    step.setdefault("citation_source", "table_row_reanchor")
                    n_reanchored += 1
                    logger.info(f"  [A1] {key}={val} ré-ancré sur sa ligne de tableau — "
                                f"« {matching[0][:80]} »")
                elif len(matching) > 1:
                    # Plusieurs séquences portent cette valeur : la rattacher à
                    # l'une d'elles serait un choix arbitraire aux conséquences
                    # chimiques réelles. On conserve et on signale.
                    step.setdefault("ambiguous_values", []).append(key)
                    n_ambiguous += 1
                else:
                    # Introuvable dans la citation ET dans toute ligne de
                    # tableau : la valeur n'est prouvée nulle part (règle d'or).
                    step[key] = None
                    # Journaliser CE QUI DISPARAÎT : une purge silencieuse rend
                    # une régression indétectable — on doit pouvoir vérifier
                    # après coup que chaque valeur supprimée l'était à raison.
                    purged_detail.append(f"step{step.get('order')}.{key}={val}")
                    pw.setdefault("missing_parameters", []).append({
                        "step_order": step.get("order"),
                        "step_type": step.get("type") or step.get("operation"),
                        "parameter": key, "unit": None, "severity": "recommended"})

    if n_reanchored or n_ambiguous or purged_detail:
        logger.warning(f"  🔗 [A1:re-ancrage] {n_reanchored} valeur(s) ré-ancrée(s) sur une "
                       f"ligne de tableau | {n_ambiguous} ambiguë(s) conservée(s) | "
                       f"{len(purged_detail)} introuvable(s) purgée(s) → trou déclaré")
        if purged_detail:
            logger.warning(f"  🗑️ [A1:purgées] {', '.join(purged_detail[:12])}"
                           f"{' …' if len(purged_detail) > 12 else ''}")


def _validate_extraction_against_text(extraction: dict, focused_text: str,
                                      full_text: str = None) -> dict:
    """Vérifie que les valeurs numériques extraites apparaissent dans le texte source.
    Ajoute un flag 'ungrounded' aux valeurs non trouvées.

    [V4.11] full_text (texte COMPLET du PDF, optionnel) : repêchage anti-faux-positif.
    Constaté par audit (papier graphène oxide) : des réactifs canoniques réels
    (KMnO4/H2SO4/H2O2, présents dans le PDF) étaient flaggés non-ancrés parce que
    la FENÊTRE focalisée de 8500 chars avait mal cadré la section — la variante n'a
    survécu que de justesse (6/9). Une citation qui échoue sur la fenêtre est donc
    re-testée contre le PDF entier : une vraie phrase du papier hors-fenêtre redevient
    ancrée ; une citation copiée du prompt reste introuvable partout → rejetée."""
    text_lower = focused_text.lower()
    has_rt_mention = any(rt in text_lower for rt in
                         ("room temperature", " rt ", "ambient",
                          "température ambiante", "temperature ambiante"))
    ungrounded = []

    for pw in extraction.get("pathways", []):
        for step in pw.get("synthesis_steps", []):
            order = step.get("order", "?")
            stype = step.get("type", step.get("operation", "?"))
            # Troisieme recopie de la meme liste, supprimee : on parcourt
            # desormais l'unique `_NUMERIC_STEP_KEYS`.
            for key in _NUMERIC_STEP_KEYS:
                val = step.get(key)
                if val is None:
                    continue
                str_val = str(int(val)) if val == int(val) else str(val)
                if str_val not in focused_text and str_val not in text_lower:
                    if has_rt_mention and isinstance(val, (int, float)) and 20 <= val <= 30 and "temperature" in key:
                        continue
                    ungrounded.append({"step": order, "type": stype, "param": key, "value": val})

    if ungrounded:
        logger.warning(f"  ⚠ {len(ungrounded)} valeur(s) non trouvée(s) dans le texte source : "
                       f"{ungrounded[:3]}")
        extraction["ungrounded_values"] = ungrounded

    _reanchor_values_on_table_rows(extraction, focused_text, full_text)

    # ══════════════════════════════════════════════════════════════════════
    # [B3 - Étape B quick win] GROUNDING DE L'ATMOSPHÈRE — anti-hallucination
    # silencieuse. Constaté à l'audit (notes_incorrect_parameters_summary.md
    # #4) : atmosphère 'air' écrite alors que le papier dit Argon/N2/vide —
    # fuite du squelette de prompt qui montre 'air'/'O2' en exemple. Le mot
    # d'atmosphère (avec ses synonymes) doit apparaître dans la source
    # (focused OU full_text), sinon c'est une donnée fabriquée silencieuse :
    # purge → null + trou 'atmosphere' recommandé déclaré (règle d'or), même
    # style que la purge squelette V4.17 ci-dessous.
    # ══════════════════════════════════════════════════════════════════════
    _ATM_SYNONYMS: dict[str, list[str]] = {
        "air": ["air", "ambient"],
        "ambient": ["air", "ambient"],
        "ar": ["ar", "argon"],
        "argon": ["ar", "argon"],
        "n2": ["n2", "n₂", "nitrogen", "azote"],
        "nitrogen": ["n2", "n₂", "nitrogen", "azote"],
        "o2": ["o2", "o₂", "oxygen", "oxygène"],
        "oxygen": ["o2", "o₂", "oxygen", "oxygène"],
        "vacuum": ["vacuum", "vide"],
        "vide": ["vacuum", "vide"],
        "h2": ["h2", "h₂", "hydrogen", "hydrogène", "forming gas"],
        "hydrogen": ["h2", "h₂", "hydrogen", "hydrogène", "forming gas"],
    }
    # ══════════════════════════════════════════════════════════════════════
    # [A3 — V4.20] DURCISSEMENT : validation AU NIVEAU DE LA CITATION.
    #
    # Le contrôle B3 ci-dessus cherchait le mot d'atmosphère dans TOUT le
    # document. Mesure sur le corpus : il ne rejetait presque rien (« air »,
    # « vacuum » figurent quasi toujours quelque part) — 82 % des atmosphères
    # n'étaient pas justifiées par la citation de leur propre étape, dont ce
    # cas relevé au bench :
    #     atmosphere='air'  ←  citation « ...under a 20 ml/min H2 atmosphere »
    # La citation dit H2, le graphe disait air. Un chimiste qui suit ce
    # protocole conduit sa réduction sous air : la synthèse échoue.
    #
    # Règle retenue (choix de Terry, 17/08/2026) : l'atmosphère doit être
    # justifiée par la citation de SON étape, sinon purge → MissingParameter.
    # Application stricte de la règle d'or, y compris quand la valeur est
    # chimiquement plausible : non prouvée = non écrite.
    # ══════════════════════════════════════════════════════════════════════
    def _atm_in(atm_value: str, hay: str) -> bool:
        """L'atmosphère (ou l'un de ses synonymes) figure-t-elle dans `hay` ?

        Le repli des confusables OCR est INDISPENSABLE ici : les scans anciens
        écrivent « flowing 02 » avec un zéro. Sans ce repli, une atmosphère O2
        parfaitement explicite dans l'article était purgée — régression mesurée
        sur PhysRevB, où le graphe se retrouvait sans aucune atmosphère.
        """
        key = str(atm_value).strip().lower().translate(_OCR_CONFUSABLES)
        hay_folded = (hay or "").translate(_OCR_CONFUSABLES)
        for cand in _ATM_SYNONYMS.get(key, [key]):
            cand = cand.translate(_OCR_CONFUSABLES)
            if re.search(r"\b" + re.escape(cand) + r"\b", hay_folded):
                return True
        return False

    # ── Portée de la preuve : LE PROTOCOLE, pas l'étape isolée ────────────
    # Première version de A3 : preuve exigée dans la citation de l'étape même.
    # Mesure contre le gold : RÉGRESSION. Sur PhysRevB, « heated in flowing O2 »
    # est porté par l'étape de MÉLANGE, tandis que l'atmosphère est déclarée sur
    # les étapes de chauffage (dont la citation est le tableau des paliers) —
    # l'O2, pourtant correct et explicite, était purgé.
    # Les auteurs déclarent l'atmosphère UNE fois pour toute la recette : exiger
    # sa répétition à chaque étape est un contresens sur l'écriture scientifique.
    # Portée retenue : l'ensemble des citations du protocole. Plus strict que le
    # document entier (B3, qui ne rejetait presque rien), plus juste que l'étape
    # seule. La preuve reste textuelle et locale à la recette.
    _atm_purged = _atm_contradicted = 0
    for pw in extraction.get("pathways", []):
        steps = pw.get("synthesis_steps", [])
        pw_citations = " ".join(
            str(s.get("citation") or s.get("raw_text_citation") or "") for s in steps
        ).lower()

        for step in steps:
            atm = step.get("atmosphere")
            if not atm:
                continue
            cit = (step.get("citation") or step.get("raw_text_citation") or "").lower()

            # 1) Contradiction franche dans la citation de l'étape : la citation
            #    nomme une AUTRE atmosphère. Cas le plus dangereux (air vs H2) —
            #    purge immédiate, quelle que soit la preuve ailleurs.
            if cit and not _atm_in(atm, cit):
                others = {k for k in _ATM_SYNONYMS if not _atm_in(k, str(atm).lower())}
                if any(_atm_in(o, cit) for o in others):
                    _atm_contradicted += 1
                    logger.warning(f"  ⛔ [A3] CONTRADICTION : atmosphere='{atm}' alors que la "
                                   f"citation de l'étape indique autre chose — « {cit[:85]} »")
                    step["atmosphere"] = None
                    _atm_purged += 1
                    pw.setdefault("missing_parameters", []).append({
                        "step_order": step.get("order"),
                        "step_type": step.get("type") or step.get("operation"),
                        "parameter": "atmosphere", "unit": None, "severity": "recommended"})
                    continue

            # 2) Preuve dans une citation quelconque du protocole → conservée.
            if pw_citations and _atm_in(atm, pw_citations):
                continue

            # 3) Aucune preuve nulle part dans la recette → règle d'or.
            step["atmosphere"] = None
            _atm_purged += 1
            pw.setdefault("missing_parameters", []).append({
                "step_order": step.get("order"),
                "step_type": step.get("type") or step.get("operation"),
                "parameter": "atmosphere", "unit": None, "severity": "recommended"})

    if _atm_purged:
        logger.warning(f"  🚫 [A3:atmosphere] {_atm_purged} atmosphère(s) non justifiée(s) par "
                       f"la citation de leur étape — purgée(s) → null + trou déclaré "
                       f"(dont {_atm_contradicted} contradiction(s) franche(s))")

    # [V4.17] PURGE SQUELETTE — les 555/665 °C sont les valeurs d'exemple
    # improbables du prompt (V4.6, choisies précisément comme détecteurs). Une
    # valeur non-ancrée ÉGALE à une valeur squelette est une recopie certaine :
    # les autres valeurs non-ancrées de la MÊME étape (durée 5/7 h recopiées
    # ensemble) sont purgées avec elle → null + trou déclaré (règle d'or).
    # Constaté (gold batch 2, ferrite) : citations réelles + programme thermique
    # squelette entier entré au graphe, flaggé mais présent, triage OK.
    _SKELETON_TEMPS = {555.0, 665.0}
    _purged = 0
    for pw in extraction.get("pathways", []):
        for step in pw.get("synthesis_steps", []):
            order = step.get("order", "?")
            step_ungrounded = [u for u in ungrounded if u["step"] == order]
            has_skeleton = any(u["param"].endswith("temperature_c")
                               and float(u["value"]) in _SKELETON_TEMPS
                               for u in step_ungrounded)
            if not has_skeleton:
                continue
            for u in step_ungrounded:
                if step.get(u["param"]) is None:
                    continue
                step[u["param"]] = None
                _purged += 1
                sev = ("required" if u["param"] in
                       ("temperature_c", "target_temperature_c", "duration_h")
                       else "recommended")
                pw.setdefault("missing_parameters", []).append({
                    "step_order": step.get("order"),
                    "step_type": step.get("type") or step.get("operation"),
                    "parameter": u["param"], "unit": None, "severity": sev})
    if _purged:
        logger.warning(f"  🚫 [Anti-Squelette] {_purged} valeur(s) recopiée(s) du squelette "
                       f"(555/665) purgée(s) → null + trou déclaré")

    # ══════════════════════════════════════════════════════════════════════
    # [V4.6] GROUNDING DES CITATIONS — anti-hallucination structurel.
    # Constaté en run réel : le LLM peut 'citer' ses propres instructions
    # (règles du prompt Orchestrateur, squelette d'exemple) au lieu du PDF,
    # et fabriquer une recette entière. Chaque citation doit donc exister
    # dans le texte source (matching insensible à la casse/ponctuation/OCR).
    # Si la MAJORITÉ des citations d'une variante sont introuvables →
    # variante SUPPRIMÉE (fail-closed, tracée dans dropped_pathways).
    # ══════════════════════════════════════════════════════════════════════
    def _clean_for_match(t: str) -> str:
        # [V4.14] Repli des confusables OCR (0↔O, 1↔l) APRÈS lowercasing, appliqué
        # aux DEUX côtés du matching. Cause racine PhysRevB (scan 1994) : le PDF
        # écrit 'Ir02', 'Ru02', 'flowing 02' (zéro) ; le modèle normalise
        # spontanément en IrO2/O2 en citant → citation RÉELLE rejetée (2/4 = pile
        # le seuil) → route perdue. Matching de PRÉSENCE uniquement : les textes
        # stockés au graphe ne sont pas modifiés, aucun risque règle d'or.
        return re.sub(r"[^a-z0-9]", "", (t or "").lower()).translate(_OCR_CONFUSABLES)

    # [V4.14.1] RÈGLE D'OR — la source de vérité du grounding est LE PAPIER, RIEN
    # d'autre. Le texte focalisé contient un bloc [RÉFÉRENCE BIBLE] (extraits du
    # manuel) destiné au CONTEXTE du modèle : constaté sur PhysRevB, le modèle a
    # construit des étapes en citant le manuel (chromites de West) et le grounding
    # les validait car le bloc était dans focused_text → protocole fabriqué ACCEPT.
    # On tronque donc tout ce qui suit le marqueur Bible avant le matching.
    # ([EXTRAITS PERTINENTS] et [TABLE RÉFÉRENCÉE] proviennent du papier lui-même
    # — chunks pdf_chunks et fenêtres de full_text — donc restent licites.)
    _parts = (focused_text or "").split("[RÉFÉRENCE BIBLE")
    _paper_only = _parts[0]
    cleaned_src = _clean_for_match(_paper_only)
    # [V4.14.2] Le bloc Bible lui-même sert de DÉTECTEUR POSITIF de contamination :
    # une citation absente du papier mais présente dans ce bloc n'est pas un « doute »
    # (OCR, fenêtre), c'est une preuve que l'étape vient du manuel → suppression DURE
    # de l'élément, sans passer par la règle de majorité (constaté PhysRevB : une
    # variante à 1 seule citation vérifiable gardait son étape-manuel flaggée).
    cleaned_bible = _clean_for_match(_parts[1]) if len(_parts) > 1 else ""
    # [V4.11] Source de repêchage : le PDF entier. Une citation du prompt n'y sera
    # jamais ; une vraie phrase hors-fenêtre, si.
    cleaned_full = _clean_for_match(full_text) if full_text else ""

    def _in_any_source(frag: str) -> bool:
        if frag in cleaned_src:
            return True
        return bool(cleaned_full) and frag in cleaned_full

    def _citation_in_source(cit: str) -> bool:
        frag = _clean_for_match(cit)
        if len(frag) < 12:
            return True  # trop courte pour juger — on ne pénalise pas
        if _in_any_source(frag):
            return True
        # Tolérance OCR/troncature : début OU fin de la citation suffit
        return _in_any_source(frag[:40]) or _in_any_source(frag[-40:])

    def _name_in_source(name: str) -> bool:
        """[V4.7.1] Un précurseur doit EXISTER dans le texte source. Formule exacte
        (SrCO3) ou, pour les noms en toutes lettres ('Iridium métal en poudre',
        traduits par le LLM), au moins un mot significatif (≥4 chars).
        [V4.11] Repêchage contre le PDF entier (cf. docstring)."""
        frag = _clean_for_match(name)
        if len(frag) < 4:
            return True  # trop court pour juger (ex: 'Ir')
        if _in_any_source(frag):
            return True
        words = [w for w in re.findall(r"[a-zA-Z0-9]+", (name or "").lower()) if len(w) >= 4]
        return any(_in_any_source(w) for w in words)

    kept_pathways, dropped = [], []
    for pw in extraction.get("pathways", []):
        checked, found = 0, 0
        _bible_items = []  # [V4.14.2] éléments citant le manuel → suppression dure
        for item in list(pw.get("synthesis_steps", []) or []) + list(pw.get("precursors", []) or []):
            if not isinstance(item, dict):
                continue
            is_precursor = "role" in item or item in (pw.get("precursors") or [])
            # [V4.7.1] Précurseur inexistant dans la source = invention (constaté :
            # 'SrO2' fabriqué avec une citation réelle mais hors sujet). Compte comme
            # non-ancré même si sa citation matche.
            name_ok = True
            if is_precursor:
                name_ok = _name_in_source(item.get("formula") or item.get("name") or "")
                if not name_ok:
                    item["name_grounded"] = False
            cit = item.get("citation") or ""
            if len(_clean_for_match(cit)) < 12:
                if is_precursor and not name_ok:
                    checked += 1  # précurseur inventé sans citation : pénalisé quand même
                continue
            checked += 1
            if _citation_in_source(cit) and name_ok:
                found += 1
            else:
                item["citation_grounded"] = False
                # [V4.14.2] Citation absente du papier mais présente dans le bloc
                # Bible = preuve de contamination → suppression dure de l'élément.
                _frag = _clean_for_match(cit)
                if cleaned_bible and (_frag in cleaned_bible or _frag[:40] in cleaned_bible
                                      or _frag[-40:] in cleaned_bible):
                    _bible_items.append(item)
        if _bible_items:
            pw["synthesis_steps"] = [s for s in (pw.get("synthesis_steps") or [])
                                     if not any(s is b for b in _bible_items)]
            pw["precursors"] = [p for p in (pw.get("precursors") or [])
                                if not any(p is b for b in _bible_items)]
            logger.warning(f"  🚫 [Anti-Contamination] {len(_bible_items)} élément(s) citant la "
                           f"BIBLE (manuel) supprimé(s) de la variante "
                           f"'{pw.get('variant_id', '?')}' — preuve positive de contamination")
        # [V4.6.1] MAJORITÉ STRICTE requise : constaté en live, une route hallucinée
        # survivait à exactement 3/6 (fragments dégénérés type 'hesis conditions'
        # qui matchent par hasard). grounded ≤ moitié → suppression.
        if checked >= 2 and found * 2 <= checked:
            vid = pw.get("variant_id", "?")
            # [V4.14] Observabilité : persister les citations REJETÉES (avant, seuls
            # les comptes '2/4' survivaient — impossible de diagnostiquer post-mortem
            # si le rejet était une vraie fabrication ou un artefact OCR).
            _rejected_cits = [
                (it.get("citation") or "")[:160]
                for it in list(pw.get("synthesis_steps") or []) + list(pw.get("precursors") or [])
                if isinstance(it, dict) and it.get("citation_grounded") is False
            ]
            dropped.append({
                "variant_id": vid,
                "reason": "citations introuvables dans le texte source (hallucination probable)",
                "citations_grounded": f"{found}/{checked}",
                "target": (pw.get("target_material") or {}).get("name", "?"),
                "citations_rejetees": _rejected_cits,
            })
            logger.warning(
                f"  🚫 [Anti-Hallucination] Variante '{vid}' SUPPRIMÉE : "
                f"seulement {found}/{checked} citations retrouvées dans le texte source. "
                f"Le LLM a probablement cité ses instructions au lieu du PDF."
            )
            continue
        if found < checked:
            logger.warning(f"  ⚠ [Citations] {checked - found}/{checked} citation(s) non retrouvée(s) "
                           f"dans la source (variante {pw.get('variant_id', '?')}) — flag citation_grounded=false")
        kept_pathways.append(pw)

    if dropped:
        extraction["pathways"] = kept_pathways
        extraction["dropped_pathways"] = dropped
        extraction["extraction_notes"] = (extraction.get("extraction_notes", "") +
                                          f" | {len(dropped)} variante(s) supprimée(s) pour hallucination de citations")

    # P11 — flag citation_quality="reference_only" si la citation renvoie à un tableau
    TABLE_CIT_RE = re.compile(
        r"(?:see|documented in|listed in|shown in|reported in|given in|detailed in)"
        r"\s+[Tt]ables?\s+\d+|[Tt]ables?\s+\d+(?:\s*[-–]\s*\d+)?",
        re.IGNORECASE,
    )
    for pw in extraction.get("pathways", []):
        for step in pw.get("synthesis_steps", []):
            cit = step.get("citation") or ""
            if TABLE_CIT_RE.search(cit):
                step["citation_quality"] = "reference_only"
                logger.info(f"  [P11] step {step.get('order')} marqué citation_quality=reference_only")

    for pw in extraction.get("pathways", []):
        for step in pw.get("synthesis_steps", []):
            dur = step.get("duration_h")
            cit = (step.get("citation") or "").lower()
            if dur is not None and dur > 0:
                if re.search(r"\b" + str(int(dur)) + r"\s*min", cit) and "hour" not in cit and "h\b" not in cit:
                    step["duration_h"] = round(dur / 60, 4)
                    logger.info(f"  [AutoFix] duration {dur}h → {step['duration_h']}h ({int(dur)} min détecté dans citation)")

    ATMOSPHERE_NORMALIZE = {
        "nitrogen": "N2", "n2": "N2", "n₂": "N2",
        "argon": "Ar", "ar atmosphere": "Ar", "under ar": "Ar", "ar gas": "Ar",
        "oxygen": "O2", "o2": "O2", "o₂": "O2", "flowing o2": "O2", "flowing oxygen": "O2",
        "air": "air", "in air": "air", "ambient air": "air",
        "vacuum": "vacuum", "under vacuum": "vacuum",
        "hydrogen": "H2", "h2": "H2", "forming gas": "H2",
    }
    ATM_PATTERN = re.compile(
        r"\b(in air|flowing\s+O2|flowing\s+oxygen|under\s+Ar|Ar\s+atmosphere|"
        r"N2\s+atmosphere|under\s+N2|vacuum|under\s+hydrogen|H2\s+atmosphere)\b",
        re.IGNORECASE,
    )
    for pw in extraction.get("pathways", []):
        for step in pw.get("synthesis_steps", []):
            if step.get("operation") not in ("heating", "soak", "cooling", "quenching"):
                continue
            atm = step.get("atmosphere")
            if atm:
                atm_lower = atm.lower().strip()
                for k, v in ATMOSPHERE_NORMALIZE.items():
                    if k in atm_lower:
                        step["atmosphere"] = v
                        break
            else:
                cit = (step.get("citation") or "").lower()
                m = ATM_PATTERN.search(cit) or ATM_PATTERN.search(focused_text[:5000])
                if m:
                    raw = m.group(0).lower().strip()
                    for k, v in ATMOSPHERE_NORMALIZE.items():
                        if k in raw:
                            step["atmosphere"] = v
                            logger.info(f"  [AutoFix:atm] step {step.get('order')} → atmosphere={v} (détecté dans citation/texte)")
                            break

    return extraction


def step3_extract_singleshot(full_text: str, rag, model, route: dict = None, directive: dict = None) -> dict:
    """[V4.4] Extraction single-shot : texte focalisé + 1 appel schéma-contraint.

    Remplace le tool-caller à 2 phases (fragile sur 8B, templates vides, débordement
    de contexte). Renvoie un dict `pathways` compatible avec le reste du pipeline.
    """
    from synthgraph.agents.extractor_singleshot import extract_single_shot

    route_id    = route.get("route_id", "route_1") if route else "route_1"
    method_raw  = (route.get("synthesis_route") or route.get("method_type")) if route else "operation_generique"
    # Coerce enum (MacroMethodEnum) -> str
    method_type = str(getattr(method_raw, "value", method_raw))
    target = (route.get("target_material") if route else None) \
        or (directive.get("target_material") if directive else None) or "?"

    logger.info(f"ÉTAPE 3 (single-shot) [{route_id}] — cible={target}, méthode={method_type}")

    focused_text = _build_focused_text(full_text, rag, target, method_type)
    focused_text = _fix_ocr_formulas(focused_text)
    logger.info(f"  Texte focalisé : {len(focused_text)} chars, début: {focused_text[:150]!r}...")
    if _DEBUG_TEXT:
        Path(f"logs/debug_focused_{route_id}.txt").write_text(focused_text, encoding="utf-8")
        logger.info(f"  → Texte focalisé sauvegardé : logs/debug_focused_{route_id}.txt")

    extraction = extract_single_shot(
        focused_text, method_type=method_type, target=target,
        model=model, route_id=route_id, directive=directive,
    )
    extraction = _validate_extraction_against_text(extraction, focused_text, full_text)

    # [V4.7] Rattrapage guidé par le bilan élémentaire : constaté en run réel, les
    # sous-routes t2/t3 perdent des précurseurs (1 seul au lieu de 3). Si le Python
    # détecte des éléments manquants avec ≤2 précurseurs, on redemande UNE fois au
    # modèle de RELIRE le texte (jamais d'invention : la consigne exige des citations).
    try:
        from synthgraph.validation.deterministic import element_balance_report
        _pw0 = (extraction.get("pathways") or [{}])[0]
        _precs = _pw0.get("precursors") or []
        _tgt_f = ((_pw0.get("target_material") or {}).get("formula")
                  or (_pw0.get("target_material") or {}).get("name") or target)
        _rep = element_balance_report(
            [p.get("formula") or p.get("name", "") for p in _precs], _tgt_f) if _precs else None
        # [V4.9.1] 0 précurseur + des étapes = recette trivialement incomplète (constaté
        # batch 1 : protocole Fe3O4 à 0 précurseur entré au graphe — le rattrapage
        # exigeait ≥1 précurseur pour calculer un bilan).
        _no_precs = (not _precs) and bool(_pw0.get("synthesis_steps"))
        if (_rep and _rep["ok"] is False and len(_precs) <= 2) or _no_precs:
            _missing = _rep["missing_elements"] if _rep else "tous (aucun précurseur listé)"
            logger.warning(f"[{route_id}] 🔁 Rattrapage : éléments {_missing} non couverts "
                           f"avec {len(_precs)} précurseur(s) — retry ciblé de l'extraction")
            hint = (f"⚠️ CONTRÔLE QUALITÉ AUTOMATIQUE (bilan atomique Python) : ta liste de précurseurs "
                    f"est {'VIDE' if _no_precs else 'INCOMPLÈTE'}. La cible {_tgt_f} nécessite des "
                    f"matériaux de départ ({_missing}). RELIS le TEXTE SOURCE et liste TOUS les "
                    f"réactifs, flux et solvants qui y sont mentionnés, chacun avec sa citation exacte. "
                    f"Si le texte ne les nomme réellement pas, indique-le dans 'notes' — n'invente rien.")
            retry = extract_single_shot(
                focused_text, method_type=method_type, target=target,
                model=model, route_id=route_id, directive=directive, extra_hint=hint,
            )
            retry = _validate_extraction_against_text(retry, focused_text, full_text)
            _rpw0 = (retry.get("pathways") or [{}])[0]
            _rprecs = _rpw0.get("precursors") or []
            _rrep = element_balance_report(
                [p.get("formula") or p.get("name", "") for p in _rprecs], _tgt_f) if _rprecs else None
            if _rep is None:  # cas 0 précurseur : tout précurseur ancré est un progrès
                better_balance = _rrep is None or _rrep["ok"] is not False
            else:
                better_balance = _rrep is not None and (_rrep["ok"] is not False
                                 or len(_rrep["missing_elements"]) < len(_rep["missing_elements"]))
            # [V4.17] Le rattrapage ne doit pas payer ses précurseurs en valeurs
            # fabriquées : un retry qui AUGMENTE les valeurs non-ancrées est rejeté
            # (constaté ferrite batch 2 : retry 1→4 précurseurs retenu avec 12
            # valeurs squelette dans le programme thermique).
            _n_ung_before = len(extraction.get("ungrounded_values") or [])
            _n_ung_after = len(retry.get("ungrounded_values") or [])
            if (len(_rprecs) > len(_precs) and better_balance
                    and _rpw0.get("synthesis_steps") and _n_ung_after <= _n_ung_before):
                logger.info(f"[{route_id}] 🔁 Rattrapage retenu : {len(_precs)} → {len(_rprecs)} précurseurs, "
                            f"bilan {_rrep['verdict'] if _rrep else '?'}")
                extraction = retry
                extraction["extraction_notes"] = (extraction.get("extraction_notes", "")
                                                  + " | rattrapage précurseurs (bilan élémentaire)")
            else:
                logger.info(f"[{route_id}] 🔁 Rattrapage non retenu (pas mieux) — extraction initiale conservée")
    except Exception as _e:
        logger.debug(f"[{route_id}] Rattrapage indisponible : {_e}")

    # [V4.7.2/V4.7.3] Broyages intermédiaires manquants (pattern GÉNÉRAL de la synthèse
    # céramique : 'fired at T1; T2; T3 with intermediate grindings' = UNE séquence).
    # 1) Fusion DÉTERMINISTE des fausses variantes (réutilise les étapes déjà citées) ;
    # 2) sinon retry LLM en dernier recours.
    try:
        _has_grind = any(s.get("type") == "grinding"
                         for p in (extraction.get("pathways") or []) if isinstance(p, dict)
                         for s in (p.get("synthesis_steps") or []))
        if _GRIND_MENTION_RE.search(focused_text) and not _has_grind and extraction.get("pathways"):
            _n_before = len(extraction["pathways"])
            extraction = _merge_sequential_variants(extraction, focused_text)
            _has_grind = any(s.get("type") == "grinding"
                             for p in extraction.get("pathways", [])
                             for s in (p.get("synthesis_steps") or []))
        if _GRIND_MENTION_RE.search(focused_text) and not _has_grind and extraction.get("pathways"):
            logger.warning(f"[{route_id}] 🔁 Rattrapage grinding : le texte mentionne des broyages "
                           f"intermédiaires, absents de l'extraction — retry ciblé")
            hint = ("⚠️ CONTRÔLE QUALITÉ AUTOMATIQUE : le TEXTE SOURCE mentionne des broyages "
                    "intermédiaires ('intermediate grindings') mais ton extraction ne contient "
                    "AUCUNE étape 'grinding'. Si les paliers de température forment une SÉQUENCE "
                    "progressive (ex: '900°C, 24 h; 1000°C, 60 h; 1100°C, 60 h with many intermediate "
                    "grindings'), c'est UNE SEULE recette séquentielle : enchaîne dans le MÊME "
                    "variant_id='v1' les étapes heating→soak→grinding→heating→soak→grinding→"
                    "heating→soak, dans l'ordre chronologique, avec les citations exactes. "
                    "N'utilise PAS une variante par palier.")
            retry = extract_single_shot(
                focused_text, method_type=method_type, target=target,
                model=model, route_id=route_id, directive=directive, extra_hint=hint,
            )
            retry = _validate_extraction_against_text(retry, focused_text, full_text)
            _r_pws = retry.get("pathways") or []
            _r_has_grind = any(s.get("type") == "grinding" for p in _r_pws if isinstance(p, dict)
                               for s in (p.get("synthesis_steps") or []))
            _n_steps_old = sum(len(p.get("synthesis_steps") or []) for p in extraction["pathways"])
            _n_steps_new = sum(len(p.get("synthesis_steps") or []) for p in _r_pws)
            if _r_has_grind and _r_pws and _n_steps_new >= _n_steps_old:
                logger.info(f"[{route_id}] 🔁 Rattrapage grinding retenu : {_n_steps_old} → {_n_steps_new} étapes, "
                            f"{len(extraction['pathways'])} → {len(_r_pws)} variante(s)")
                extraction = retry
                extraction["extraction_notes"] = (extraction.get("extraction_notes", "")
                                                  + " | rattrapage broyages intermédiaires")
            else:
                logger.info(f"[{route_id}] 🔁 Rattrapage grinding non retenu — extraction initiale conservée")
    except Exception as _e:
        logger.debug(f"[{route_id}] Rattrapage grinding indisponible : {_e}")

    # [V4.9] Route vidée par le grounding (TOUTES les variantes avaient des citations
    # fabriquées) → UN retry from-scratch avec consigne renforcée. Constaté batch 1 :
    # la route 'Marcano method' (vraie recette du papier graphène) était perdue.
    # From-scratch ≠ réécriture (le LLM repart du texte, pas de son ancien JSON).
    _empty_now = (not extraction.get("pathways")
                  or all(not p.get("synthesis_steps") for p in extraction["pathways"]))
    if _empty_now and (extraction.get("dropped_pathways") or directive):
        # [V4.9.1] Couvre aussi l'extraction vide D'EMBLÉE (0 étape sans rejet) quand
        # la route vient d'une directive du Stratège/Orchestrateur : le papier décrit
        # cette voie quelque part. Un seul retry ; s'il revient vide → vide (règle d'or).
        reason = ("citations fabriquées" if extraction.get("dropped_pathways")
                  else "extraction vide d'emblée")
        hint = ("⚠️ CONTRÔLE QUALITÉ AUTOMATIQUE : ta précédente extraction était inutilisable "
                "(vide ou citations ne provenant pas du TEXTE SOURCE). Recommence : relis TOUT "
                "le TEXTE SOURCE ci-dessus, extrais chaque étape de synthèse décrite, et pour "
                "CHAQUE champ `citation`, copie-colle un fragment EXACT de ce texte. "
                "Si le texte ne décrit vraiment pas cette synthèse, renvoie steps: [] — n'invente rien.")
        # [V4.12] Auto-consistance : à température 0.1, la fabrication est un mode
        # SYSTÉMATIQUE — la route Hummers a recopié le squelette au run initial ET au
        # retry (2026-07-15) ; et PhysRevB prouve la variance inter-runs (88 requêtes
        # en baseline v4.7.3, 0 en V4.11, même papier). D'où 2 retries, le second à
        # température ÉLEVÉE pour sortir du mode. Sans risque pour la règle d'or : le
        # grounding déterministe reste le filtre, rien d'inventé ne peut passer —
        # au pire, la variante est rejetée comme avant.
        for _attempt, _temp in ((1, None), (2, 0.45)):
            logger.warning(f"[{route_id}] 🔁 Extraction inutilisable ({reason}) — retry "
                           f"from-scratch {_attempt}/2"
                           f"{'' if _temp is None else f' (température {_temp})'}")
            try:
                retry = extract_single_shot(focused_text, method_type=method_type, target=target,
                                            model=model, route_id=route_id, directive=directive,
                                            extra_hint=hint, temperature=_temp)
                retry = _validate_extraction_against_text(retry, focused_text, full_text)
                # [V4.14.3] « retenu » exige de VRAIES étapes : après la purge
                # anti-contamination, un pathway peut survivre avec précurseurs mais
                # 0 étape — le retenir court-circuitait le retry 2 (T=0.45) et la
                # route finissait vide quand même (constaté PhysRevB V4.14.2).
                if any(isinstance(p, dict) and p.get("synthesis_steps")
                       for p in retry.get("pathways") or []):
                    logger.info(f"[{route_id}] 🔁 Retry from-scratch {_attempt}/2 retenu : "
                                f"{len(retry['pathways'])} variante(s) ancrée(s)")
                    retry["extraction_notes"] = (retry.get("extraction_notes", "")
                                                 + f" | retry from-scratch #{_attempt} après rejet grounding")
                    extraction = retry
                    break
            except Exception as _e:
                logger.warning(f"[{route_id}] Retry from-scratch {_attempt}/2 impossible : {_e}")
        else:
            logger.warning(f"[{route_id}] 🔁 Retry from-scratch également rejeté — "
                           f"route abandonnée (fail-closed)")

    # [V4.11] Cohérence 0-précurseur (audit, problème 1) : constaté sur le papier
    # graphène oxide — 9 protocoles écrits au graphe SANS AUCUN précurseur après
    # échec des rattrapages, alors que le même symptôme sur Fe3O4 supprimait la
    # route. Politique unifiée : on CONSERVE les étapes (données réelles) mais on
    # DÉCLARE un trou REQUIS 'precursors' → visible dans le graphe, bloque
    # l'ACCEPT déterministe, classé GAPS_REQUIRED au triage. Règle d'or : le trou
    # est déclaré, jamais masqué.
    for _pw in extraction.get("pathways") or []:
        if not isinstance(_pw, dict):
            continue
        if _pw.get("synthesis_steps") and not (_pw.get("precursors") or []):
            _mps = _pw.setdefault("missing_parameters", [])
            if not any(isinstance(m, dict) and m.get("parameter") == "precursors" for m in _mps):
                _mps.append({"step_order": None, "step_type": "protocol",
                             "parameter": "precursors", "unit": None,
                             "severity": "required"})
                logger.warning(f"[{route_id}] ⚠ Pathway {_pw.get('variant_id', '?')} sans "
                               f"AUCUN précurseur — trou REQUIS 'precursors' déclaré au graphe")

    # [V4.18] RATIOS MOLAIRES + RENDEMENT (déterministe, décision Terry 2026-07-19).
    # La représentation canonique des quantités est le ratio molaire des précurseurs,
    # extrait des citations DÉJÀ ANCRÉES (ratio explicite « 2:2:1 », moles, masse→mol,
    # M×V) ; le rendement du papier est capté s'il est écrit. Aucune invention : sans
    # motif parsable, molar_ratio reste absent → trou 'molar_ratio' déclaré plus bas.
    try:
        from synthgraph.validation.quantities import (
            annotate_pathway_quantities, extract_yield)
        _yield = extract_yield(full_text) or extract_yield(focused_text)
        for _pw in extraction.get("pathways") or []:
            if not isinstance(_pw, dict):
                continue
            annotate_pathway_quantities(_pw, focused_text)
            if _yield and "yield_percent" not in _pw:
                _pw["yield_percent"] = _yield[0]
                _pw["yield_citation"] = _yield[1]
            # trou 'molar_ratio' si aucun ratio n'a pu être ancré (règle d'or)
            _pr = [p for p in (_pw.get("precursors") or []) if isinstance(p, dict)]
            if len(_pr) >= 2 and not any(p.get("molar_ratio") is not None for p in _pr):
                _mps = _pw.setdefault("missing_parameters", [])
                if not any(isinstance(m, dict) and m.get("parameter") == "molar_ratio" for m in _mps):
                    _mps.append({"step_order": None, "step_type": "protocol",
                                 "parameter": "molar_ratio", "unit": None,
                                 "severity": "recommended"})
        if any((p.get("ratio_source") for p in extraction.get("pathways") or []
                if isinstance(p, dict))):
            _rs = [p.get("ratio_source") for p in extraction["pathways"]
                   if isinstance(p, dict) and p.get("ratio_source")]
            logger.info(f"[{route_id}] ⚗ Ratios molaires : {_rs}"
                        + (f" | rendement {_yield[0]}%" if _yield else ""))
    except Exception as _e:
        logger.debug(f"[{route_id}] Annotation quantités indisponible : {_e}")

    pw = extraction.get("pathways", [{}])
    n_steps = len(pw[0].get("synthesis_steps", [])) if pw else 0
    n_prec  = len(pw[0].get("precursors", [])) if pw else 0
    save_step(f"step3_extraction_{route_id}", extraction)
    write_log(f"### Étape 3 (single-shot) [{route_id}]\n"
              f"- Cible : {target} | Méthode : {method_type}\n"
              f"- {n_prec} précurseurs, {n_steps} étapes\n")
    logger.info(f"[{route_id}] Extraction single-shot ✅ — {n_prec} précurseurs, {n_steps} étapes")

    n_variants = len(set(
        s.get("variant_id", "v1") or "v1"
        for p in pw for s in p.get("synthesis_steps", [])
    )) if pw else 0
    if n_variants <= 1:
        import re as _re
        temp_matches = _re.findall(r'(\d{3,4})\s*[°˚]\s*C', focused_text)
        unique_temps = set(temp_matches)
        if len(unique_temps) >= 3:
            logger.warning(
                f"[{route_id}] ⚠ {len(unique_temps)} températures distinctes détectées "
                f"({', '.join(sorted(unique_temps))}°C) mais une seule variante extraite — "
                f"possible multi-variant non capturé"
            )

    time.sleep(SLEEP_BETWEEN_STEPS)
    return extraction


def _log_vram(label: str):
    """Log l'utilisation VRAM via nvidia-smi (no-op si indisponible)."""
    try:
        r = subprocess.run(
            ['nvidia-smi', '--query-gpu=memory.used,memory.total', '--format=csv,noheader,nounits'],
            capture_output=True, text=True,
        )
        if r.returncode == 0:
            used, total = map(float, r.stdout.strip().split(','))
            logger.info(f"[VRAM] {label}: {used/1024:.2f} GB / {total/1024:.2f} GB")
    except Exception as e:
        logger.debug(f"[VRAM] indisponible: {e}")


def _extract_pdf_metadata(pdf_path: Path, full_text: str = "") -> dict:
    """Extrait titre/auteurs/année natifs du PDF via PyMuPDF (best-effort).

    L'année est cherchée en priorité dans les métadonnées PyMuPDF
    (creationDate), puis en fallback via un regex sur le début du texte
    extrait (full_text).
    """
    meta = {}
    try:
        import fitz
        doc = fitz.open(str(pdf_path))
        m = doc.metadata or {}
        if m.get("title"):
            title = re.sub(r"<[^>]+>", "", m["title"])
            meta["title"] = title
        if m.get("author"):
            meta["authors"] = m["author"]

        doc.close()
    except Exception as e:
        logger.debug(f"Métadonnées PDF indisponibles: {e}")

    if full_text:
        received_match = re.search(
            r"[Rr]eceived\s+(?:\w+\s+\d{1,2},?\s+)?(\d{4})", full_text[:5000]
        )
        if received_match:
            candidate_year = int(received_match.group(1))
            if 1900 <= candidate_year <= 2030:
                meta["year"] = candidate_year
        if "year" not in meta:
            for match in re.finditer(r"\b(19|20)\d{2}\b", full_text[:3000]):
                candidate_year = int(match.group(0))
                if 1900 <= candidate_year <= 2030:
                    meta["year"] = candidate_year
                    break

    return meta


def _inject_neo4j(queries: list, paper_name: str):
    """Injecte les requêtes Cypher PARAMÉTRÉES dans Neo4j (option --neo4j).

    [V4.5] Utilise la base définie dans settings.yaml (N2) et compte les échecs
    au lieu d'affirmer que tout est passé (N3).
    """
    try:
        import yaml
        from synthgraph.config import SETTINGS_PATH
        from synthgraph.utils.tools import Neo4jTool
        cfg = {}
        if Path(SETTINGS_PATH).exists():
            with open(SETTINGS_PATH, encoding="utf-8") as f:
                cfg = (yaml.safe_load(f) or {}).get("neo4j", {})
        neo = Neo4jTool(
            uri=cfg.get("uri", "bolt://localhost:7687"),
            user=cfg.get("user", "neo4j"),
            password=cfg.get("password", "synthgraph2026"),
            database=cfg.get("database", "neo4j"),
        )
        if neo.connect():
            ok, failed = 0, 0
            for q in queries:
                if isinstance(q, dict):
                    result = neo.run_query(q["query"], q.get("params"))
                else:  # rétrocompatibilité (anciennes requêtes en chaîne)
                    result = neo.run_query(q)
                if result is None:
                    failed += 1
                else:
                    ok += 1
            neo.close()
            if failed:
                logger.warning(
                    f"[Neo4j] {ok}/{len(queries)} requêtes injectées pour {paper_name} "
                    f"— ⚠ {failed} ÉCHEC(S) (voir erreurs ci-dessus)"
                )
            else:
                logger.info(f"[Neo4j] {ok}/{len(queries)} requêtes injectées pour {paper_name} "
                            f"(base: {neo.database})")
        else:
            logger.warning("[Neo4j] Connexion impossible — injection ignorée.")
    except Exception as e:
        logger.error(f"[Neo4j] Injection échouée: {e}")


def run_pipeline(args):
    """Point d'entrée du pipeline multi-agents V4.4 (appelé par la CLI).

    args : Namespace avec input, provider, use_marker, neo4j, …
    """
    global LLM_PROVIDER, _DEBUG_TEXT
    LLM_PROVIDER = args.provider
    _DEBUG_TEXT = getattr(args, "debug_text", False)

    Path("logs").mkdir(exist_ok=True)
    model = load_model()
    if LLM_PROVIDER == "llama-server":
        model = "gemma-4-E2B-Q4_K_M"  # Affichage local
    # [Phase 0] L'ancienne ligne affichait une étiquette legacy trompeuse
    # ("gemma / llama-server") alors que le modèle réellement chargé in-process
    # est celui du rôle 'default' de config/settings.yaml (cf README_AUTONOME
    # V4.17, backlog). On affiche désormais le vrai chemin GGUF résolu.
    logger.info(f"Modèle par défaut (rôle 'default') : {get_model_config('default')['path']}")

    # Ingestion de la Bible (idempotente : les sources déjà indexées sont ignorées)
    try:
        logger.info("Initialisation de la base de connaissances (Bible)...")
        BibleRAG().ingest_bible()
    except Exception as e:
        logger.warning(f"Ingestion Bible ignorée: {e}")

    _log_vram("Début du pipeline")

    # Si c'est un dossier, on liste tous les PDF
    input_path = Path(args.input)
    pdf_files = list(input_path.glob("*.pdf")) if input_path.is_dir() else [input_path]

    if not pdf_files:
        logger.error(f"Aucun PDF trouvé dans {args.input}")
        return

    for idx, pdf_path in enumerate(pdf_files):
        pdf_str = str(pdf_path)
        logger.info("=" * 70)
        logger.info(f"🧪 SynthGraph — Pipeline Multi-Agents [{idx+1}/{len(pdf_files)}]")
        logger.info(f"Traitement de : {pdf_str}")
        logger.info("=" * 70)

        # Initialize status for this paper
        init_status(pdf_path.name)
        global LLM_TRANSCRIPT
        LLM_TRANSCRIPT = []

        # Wipe execution log to avoid appending failed attempts
        open(EXECUTION_LOG_PATH, "w", encoding="utf-8").close()

        try:
            # Swapping: On s'assure d'être sur le modèle texte au début
            if LLM_PROVIDER == "llama-server":
                start_llama_server("text")

            # ═══════════════════════════════════════════════════════════════
            # ÉTAPE 1 : Lecture PDF
            # ═══════════════════════════════════════════════════════════════
            pdf_data    = step1_read_pdf(pdf_str, use_marker=args.use_marker)
            full_text   = pdf_data.get("full_text", pdf_data.get("experimental_text", ""))
            extracted_images = pdf_data.get("images", [])

            # [V4.17.1] PDF illisible (corrompu/scanné : constaté batch 3, spray
            # ZnO tronqué → 0 char PyMuPDF) : faire tourner le LLM sur du vide ne
            # peut produire QUE des fabrications à rejeter. Papier sauté, déclaré.
            if len(full_text.strip()) < 500:
                logger.error(f"[Pipeline] PDF ILLISIBLE ({len(full_text.strip())} chars "
                             f"extraits) — papier sauté : {pdf_path.name}")
                write_log(f"### PAPIER SAUTÉ (PDF illisible, {len(full_text.strip())} chars)\n")
                continue
            
            # Vectorisation du PDF
            update_status(step="Indexation RAG")
            rag = DocumentRAG()
            num_chunks = rag.index_text(full_text)
            write_log(f"\n# Papier : {pdf_path.name}\n")
            write_log(f"### Indexation ChromaDB (RAG)\n- {num_chunks} chunks vectorisés avec `all-MiniLM-L6-v2`\n")

            # ═══════════════════════════════════════════════════════════════
            # ÉTAPE 1b : Agent Stratège (ScientificIntentAnalyst) V4.3
            # ═══════════════════════════════════════════════════════════════
            update_status(step="Agent Stratège")
            strategy = step1b_strategic_analysis(full_text, model)

            if not strategy:
                logger.error("[Orchestrateur] Échec de l'Agent Stratège. Fin du pipeline.")
                continue

            global_context = strategy.global_context.model_dump()
            
            # --- FILTRE ANTI-CARACTÉRISATION EN DUR ---
            synthesis_keywords = [
                "synthesis", "growth", "preparation", "deposition", "sintering",
                "calcination", "fabrication", "processing", "annealing", "reaction",
                "crystallization", "pressing", "milling", "mixing", "sol-gel",
                "hydrothermal", "solvothermal", "coprecipitation", "precipitation",
                "flux", "ceramic", "solid state", "solid-state",
                "synthèse", "croissance", "préparation", "dépôt", "frittage",
                "recuit", "réaction", "cristallisation", "broyage", "mélange",
            ]

            forbidden_keywords = [
                "x-ray", "xrd", "diffraction", "scattering", "raman",
                "magnetic", "magnetization", "resistivity", "tga", "optical",
                "conductivity", "measurement", "characterization", "sem", "tem",
                "spectroscopy", "microscopy", "analysis", "nmr", "titration", "titrage",
                # Techniques d'analyse/mesure supplémentaires (V4.4)
                "surface sensitive", "surface-sensitive", "sensitive technique",
                "photoemission", "arpes", "xps", "spectrometry", "probe", "imaging",
                "electron microscopy", "neutron", "susceptibility", "transport", "hall",
                # Mots-clés français
                "caractérisation", "mesure", "diffractométrie", "microscopie",
                "spectroscopie", "diffractomètre",
            ]

            filtered_pathways = []
            for p in strategy.pathways:
                method_lower = p.method_name.lower()
                has_synthesis = any(kw in method_lower for kw in synthesis_keywords)
                has_forbidden = any(kw in method_lower for kw in forbidden_keywords)
                if has_forbidden and not has_synthesis:
                    logger.warning(f"[Filtre Anti-Caractérisation] Voie rejetée : {p.method_name}")
                else:
                    filtered_pathways.append(p)
                    logger.info(f"[Filtre] Voie acceptée : {p.method_name}")

            pathways = filtered_pathways
            # ------------------------------------------

            write_log(f"\n## Intention Scientifique : {strategy.intent}\n")
            if global_context:
                write_log(f"### Contexte Global (V4.3)\n```json\n{json.dumps(global_context, indent=2, ensure_ascii=False)}\n```\n")
            
            write_log(f"\n## Pipeline Forké : {len(pathways)} voie(s) de synthèse(s) isolée(s)\n")

            # ═══════════════════════════════════════════════════════════════
            # FORK : Pipeline isolé par route
            # ═══════════════════════════════════════════════════════════════
            all_route_results = []
            all_queries = []
            
            # Initialisation Reference : métadonnées PDF (PyMuPDF) en priorité,
            # fallback sur les attributs du Stratège LLM.
            pdf_meta = _extract_pdf_metadata(pdf_path, full_text=full_text)

            doi = getattr(strategy, "paper_doi", "N/A")
            title = pdf_meta.get("title") or getattr(strategy, "paper_title", pdf_path.stem)
            authors = pdf_meta.get("authors") or getattr(strategy, "paper_authors", "Inconnu")
            year = pdf_meta.get("year") or getattr(strategy, "paper_year", 2024)

            reference = {"title": title, "authors": authors, "year": year, "doi": doi,
                         "journal": "", "source_file": pdf_path.name}
            
            for route_idx, pathway in enumerate(pathways):
                route_id = pathway.pathway_id
                method_type = pathway.method_name
                
                logger.info("═" * 60)
                logger.info(f"🔀 ROUTE {route_idx + 1}/{len(pathways)}: {method_type} (ID: {route_id})")
                logger.info("═" * 60)
                write_log(f"\n---\n## Route {route_idx + 1}/{len(pathways)} : `{method_type}` ({route_id})\n")
                
                # [V4.4] Extraction robuste du chunk via start_quote / end_quote (3 niveaux)
                import re
                def clean_text(t):
                    return re.sub(r'[^a-zA-Z0-9]', '', t).lower()

                low_full = full_text.lower()
                cleaned_full = clean_text(full_text)

                def _locate(quote: str, is_end: bool) -> int:
                    """Localise `quote` dans full_text avec 3 stratégies de repli."""
                    if not quote:
                        return -1

                    # Niveau 1 : matching normalisé (ponctuation/casse ignorées), puis
                    # ré-ancrage dans full_text autour de la position approximative trouvée.
                    cleaned_quote = clean_text(quote)
                    if cleaned_quote:
                        c_idx = cleaned_full.find(cleaned_quote)
                        if c_idx != -1:
                            # La position dans le texte "nettoyé" (sans ponctuation/espaces)
                            # est proche, en proportion, de la position dans le texte original
                            # (les deux ont ~même longueur relative). On approx. linéairement,
                            # puis on cherche un petit fragment exact dans une fenêtre ±200.
                            approx_pos = int(c_idx * (len(full_text) / max(1, len(cleaned_full))))
                            window_lo = max(0, approx_pos - 200)
                            window_hi = min(len(full_text), approx_pos + 200)
                            anchor = quote[:15] if not is_end else quote[-15:]
                            local_idx = low_full.find(anchor.lower(), window_lo, window_hi)
                            if local_idx != -1:
                                return local_idx
                            # à défaut, l'approx elle-même reste utilisable
                            return approx_pos

                    # Niveau 2 : sous-chaînes progressives, recherche case-insensitive globale
                    for n in (40, 30, 20, 15, 10):
                        frag = (quote[:n] if not is_end else quote[-n:]).strip().lower()
                        if len(frag) < 4:
                            continue
                        idx = low_full.find(frag) if not is_end else low_full.rfind(frag)
                        if idx != -1:
                            return idx

                    return -1

                start_idx = _locate(pathway.start_quote, is_end=False)
                end_idx = _locate(pathway.end_quote, is_end=True)

                route_text_chunk = None
                if start_idx != -1 and end_idx != -1 and start_idx < end_idx:
                    end_idx += len(pathway.end_quote)
                    route_text_chunk = full_text[start_idx:end_idx]
                    logger.info(f"  [✂️] Chunk extrait avec succès : de l'index {start_idx} à {end_idx} ({len(route_text_chunk)} chars)")
                else:
                    logger.warning(f"  [⚠️] Impossible de localiser les citations de début/fin (start_idx={start_idx}, end_idx={end_idx}). Fallback sur _build_focused_text.")

                # Validation : le chunk doit contenir un minimum de vocabulaire de synthèse
                synthesis_vocab = ("temperature", "precursor", "heated", "mixed", "°c", " k ",
                                    "furnace", "crucible", "sintering", "calcin", "flux",
                                    "hydrothermal", "hour", " h ", "ramp", "cooling", "heating")
                if route_text_chunk is not None:
                    chunk_low = route_text_chunk.lower()
                    if not any(kw in chunk_low for kw in synthesis_vocab):
                        logger.warning(
                            f"  [⚠️] Chunk extrait ({len(route_text_chunk)} chars) ne contient aucun mot-clé de "
                            f"synthèse attendu. Probable mauvaise section (ex: intro). Fallback sur _build_focused_text."
                        )
                        route_text_chunk = None

                # [V4.9.1] Chunk localisé mais trop court pour contenir une recette
                # (constaté : 357 chars → extraction vide) → on l'enrichit.
                if route_text_chunk is not None and len(route_text_chunk) < 800:
                    logger.info(f"  [✂️] Chunk court ({len(route_text_chunk)} chars) — enrichi via texte focalisé")
                    fallback_target = (global_context.get("target_material_global") if global_context else None) or "?"
                    route_text_chunk = (route_text_chunk + "\n\n[CONTEXTE ÉLARGI]\n"
                                        + _build_focused_text(full_text, rag, fallback_target, pathway.method_name))

                if route_text_chunk is None:
                    fallback_target = (global_context.get("target_material_global") if global_context else None) or "?"
                    route_text_chunk = _build_focused_text(full_text, rag, fallback_target, pathway.method_name)
                
                # Contexte RAG scopé par route
                route_rag_context = rag.query(route_text_chunk[:500], n_results=5) if route_text_chunk else rag.get_extraction_context()
                
                # Créer un dictionnaire route pour la rétrocompatibilité des fonctions suivantes
                route_dict = {
                    "route_id": route_id,
                    "method_type": method_type,
                    "relevant_text_chunk": route_text_chunk
                }

                # Orchestrateur scopé
                update_status(step=f"Orchestrateur [{route_id}]")
                plan = step2_orchestrator(route_rag_context, model, route=route_dict)
                
                targets = _dedupe_directives(plan.get("extraction_directives", []))
                if not targets:
                    targets = [{"target_material": "Inconnu", "formula": "?", "synthesis_route": method_type, "key_steps": []}]
                
                for t_idx, target_info in enumerate(targets):
                    sub_route_id = f"{route_id}_t{t_idx+1}"
                    # Mettre à jour route_dict avec les infos spécifiques
                    sub_route_dict = route_dict.copy()
                    sub_route_dict["route_id"] = sub_route_id
                    sub_route_dict["target_material"] = target_info.get("target_material")
                    sub_route_dict["formula"] = target_info.get("formula", "?")
                    sub_route_dict["synthesis_route"] = target_info.get("macro_method", method_type)
                    
                    # [V4.4] Extraction single-shot (1 appel schéma-contraint, texte focalisé)
                    update_status(step=f"Extraction [{sub_route_id}]")
                    extraction = step3_extract_singleshot(
                        full_text, rag, model, route=sub_route_dict, directive=target_info,
                    )

                    _pw = extraction.get("pathways") or []
                    if not _pw or not _pw[0].get("synthesis_steps"):
                        logger.warning(f"[Pipeline] Route {sub_route_id} : extraction vide, sautée.")
                        continue

                    # [V4.8] Agent Vision : comble les trous REQUIS depuis les
                    # figures/tables (swap VRAM PaliGemma). Best-effort : en cas
                    # d'échec, les trous restent déclarés (règle d'or).
                    try:
                        extraction, _n_vision = step3c_vision_fill(
                            extraction, extracted_images, sub_route_id)
                    except Exception as ve:
                        logger.warning(f"[{sub_route_id}] Agent Vision indisponible ({ve}) "
                                       f"— trous conservés déclarés.")

                    # --- Couche QA (best-effort) : ne DOIT JAMAIS bloquer la construction du graphe ---
                    # Le graphe est déterministe depuis l'extraction ; la QA n'ajoute que des
                    # annotations (missing_params). --no-debate la saute pour le débit BDD.
                    context = {}
                    validation = {"final_validation": {}, "recommendation": "QA_SKIPPED"}
                    corrected_synthesis, missing_params = extraction, []
                    qa_basis = "none"
                    if getattr(args, "no_debate", False):
                        qa_status = "QA_SKIPPED"
                        logger.info(f"[{sub_route_id}] Couche QA sautée (--no-debate).")
                    else:
                        try:
                            update_status(step=f"Contextuel [{sub_route_id}]")
                            context = step4_contextual(
                                rag.get_contextual_context(route_id=sub_route_id, method_type=sub_route_dict["synthesis_route"]),
                                extraction, model, route=sub_route_dict)

                            update_status(step=f"Débat [{sub_route_id}]")
                            validation = step5_thermodynamician(extraction, context, model, route=sub_route_dict)

                            update_status(step=f"Audit Red Team [{sub_route_id}]")
                            corrected_synthesis, missing_params = step5b_red_team_audit(
                                extraction, context, validation, model, route=sub_route_dict)

                            # [V4.5/C4] Le verdict du débat est PROPAGÉ au graphe
                            # (avant, un REJECT produisait le même graphe qu'un ACCEPT).
                            qa_status = str(validation.get("recommendation", "QA_FAILED")).upper()
                            if qa_status not in _CANONICAL_RECOMMENDATIONS:
                                qa_status = "REVISE"  # jamais de phrase libre dans le graphe
                            if context.get("note") == "QA_AGENT_FAILED" and qa_status == "ACCEPT":
                                qa_status = "ACCEPT_DEGRADED"  # thermo OK mais contextuel en échec
                            # [V4.10] Promotion déterministe REVISE → ACCEPT (preuves
                            # objectives toutes vertes ; validé par Terry 2026-07-13)
                            if qa_status == "REVISE" and _deterministic_accept(extraction, validation):
                                qa_status = "ACCEPT"
                                qa_basis = "deterministic"
                                logger.info(f"[{sub_route_id}] ✅ ACCEPT déterministe : stoich OK, "
                                            f"0 trou requis, 0 élément suspect")
                            else:
                                qa_basis = "llm"
                        except Exception as qa_err:
                            logger.warning(f"[{sub_route_id}] Couche QA échouée ({qa_err}) — fail-closed : qa_status=QA_FAILED.")
                            corrected_synthesis, missing_params = extraction, []
                            qa_status = "QA_FAILED"

                    # --- Architecte Graphe DÉTERMINISTE (toujours exécuté, sans LLM) ---
                    # On construit depuis l'EXTRACTION NORMALISÉE BRUTE (détail complet),
                    # pas depuis corrected_synthesis (le Red Team LLM peut écraser des étapes).
                    # missing_params du Red Team reste passé en annotation.
                    update_status(step=f"Architecte Graphe [{sub_route_id}]")
                    queries = step6_graph_architect(
                        extraction, context, validation, reference, model,
                        route=sub_route_dict, missing_params=missing_params,
                        qa_status=qa_status, qa_basis=qa_basis,
                    )

                    all_queries.extend(queries)
                    all_route_results.append({
                        "route_id": sub_route_id,
                        "queries": queries,
                        "synthesis": corrected_synthesis
                    })

            # --- Déduplication des routes quasi-identiques ---
            if len(all_route_results) > 1:
                def _route_signature(result):
                    # [V4.10.1] Robustesse : `synthesis` peut être une liste (variantes
                    # renvoyées par un chemin Red Team) au lieu d'un dict → CRASH constaté
                    # sur le golden (Crystal growth Sr2IrO4). On accepte les deux formes.
                    synthesis = result.get("synthesis") or {}
                    if isinstance(synthesis, list):
                        pws = synthesis
                    elif isinstance(synthesis, dict):
                        pws = synthesis.get("pathways") or []
                    else:
                        return ""
                    if not pws or not isinstance(pws[0], dict):
                        return ""
                    pw = pws[0]
                    prec_names = sorted(p.get("name", "").lower() for p in (pw.get("precursors") or []))
                    step_types = [s.get("type", s.get("operation", "?")) for s in (pw.get("synthesis_steps") or [])]
                    return f"{','.join(prec_names)}|{','.join(step_types)}"

                seen_sigs = {}
                deduped_results = []
                deduped_queries = []
                for result in all_route_results:
                    sig = _route_signature(result)
                    if sig and sig in seen_sigs:
                        logger.warning(
                            f"[Dédup] Route {result['route_id']} supprimée — identique à "
                            f"{seen_sigs[sig]} (mêmes précurseurs et étapes)"
                        )
                        continue
                    if sig:
                        seen_sigs[sig] = result["route_id"]
                    deduped_results.append(result)
                    deduped_queries.extend(result.get("queries", []))

                if len(deduped_results) < len(all_route_results):
                    logger.info(
                        f"[Dédup] {len(all_route_results)} → {len(deduped_results)} route(s) "
                        f"après suppression des doublons"
                    )
                    all_route_results = deduped_results
                    all_queries = deduped_queries

            # Écriture du fichier Cypher DÉDIÉ au papier courant
            safe_name = pdf_path.stem.replace(" ", "_")
            paper_cypher_path = Path(f"logs/cypher_output_{safe_name}.cypher")
            with open(paper_cypher_path, "w", encoding="utf-8") as f:
                f.write(f"// ============================================================\n")
                f.write(f"// SynthGraph — Paper: {pdf_path.name}\n")
                f.write(f"// ============================================================\n\n")
                for q in all_queries:
                    if isinstance(q, dict):
                        f.write(f"{render_cypher(q['query'], q.get('params'))}\n\n")
                    else:
                        f.write(f"{q}\n\n")
            
            logger.info(f"💾 Fichier Cypher généré : {paper_cypher_path}")

            # --- Résultat consolidé (JSON) ---
            paper_result = {
                "paper": pdf_path.name,
                "status": "SUCCESS" if all_queries else "NO_DATA",
                "intent": getattr(strategy, "intent", None),
                "routes_processed": len(all_route_results),
                "cypher_count": len(all_queries),
                "reference": reference,
                "timestamp": datetime.now().isoformat(),
            }
            result_path = Path(f"logs/pipeline_result_{safe_name}.json")
            with open(result_path, "w", encoding="utf-8") as f:
                json.dump(paper_result, f, indent=2, ensure_ascii=False, default=str)
            logger.info(f"💾 Résultat JSON généré : {result_path}")

            # --- Injection Neo4j (optionnelle) ---
            if getattr(args, "neo4j", False) and all_queries:
                _inject_neo4j(all_queries, pdf_path.name)

            # --- Journal Gemini ---
            try:
                with open(GEMINI_LOG_PATH, "a", encoding="utf-8") as f:
                    f.write(
                        f"\n[{datetime.now().isoformat()}] Pipeline '{pdf_path.name}' — "
                        f"Statut={paper_result['status']} — Routes={paper_result['routes_processed']} — "
                        f"Cypher={paper_result['cypher_count']} requêtes\n"
                    )
            except Exception:
                pass

        except Exception as e:
            logger.error(f"Erreur fatale lors du traitement de {pdf_path.name}: {e}")
            import traceback
            traceback.print_exc()

    _log_vram("Fin du pipeline")
