"""
agent_extracteur_tool_caller.py — SynthGraph V4.3 Antigravity
Nouveau AgentExtracteur basé sur une State Machine + Tool Calling séquentiel.

Remplace le flux JSON monolithique (V4.1) par une boucle while dans laquelle
Gemma appelle des outils Python typés Pydantic, un par un.

Architecture :
  Phase 1 : Template Builder — Gemma construit l'ossature de la méthode
  Phase 2 : Value Filler    — Gemma remplit les paramètres de chaque étape
                              [V4.3] Reçoit un global_context injecté dans son
                              System Prompt pour éviter la 'Vision Tunnel'.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Dict, List, Optional
from datetime import datetime
from pathlib import Path

from pydantic import ValidationError

from synthgraph.extraction.state import ExtractionState, Phase1Template
from synthgraph.llm.engine import LlamaEngineManager

# Chemin du fichier de tracking d'outils
TOOL_EVENTS_LOG_PATH = "logs/tool_events.jsonl"

def _log_tool_event(agent: str, phase: str, tool_name: str, call_index: int,
                    args: dict = None, result_status: str = "ok", error: str = None,
                    duration_ms: int = None, route_id: str = None):
    Path(TOOL_EVENTS_LOG_PATH).parent.mkdir(exist_ok=True)
    event = {
        "ts": datetime.now().isoformat(),
        "agent": agent, "phase": phase, "route_id": route_id,
        "tool": tool_name, "call_index": call_index,
        "status": result_status, "duration_ms": duration_ms, "error": error,
        "args_summary": {k: str(v)[:120] for k, v in (args or {}).items()},
    }
    with open(TOOL_EVENTS_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")

from synthgraph.extraction.tools import (
    AgentActionPhase1, AgentActionPhase2,
    execute_phase1_tool,
    execute_phase2_tool,
    ToolResult,
)

logger = logging.getLogger("SynthGraph.AgentExtracteurToolCaller")

# ==============================================================================
# CONFIGURATION
# ==============================================================================

GEMMA_MODEL           = "llama-3.1-8b-instruct"
MAX_TOOL_CALLS_PHASE1 = 25
MAX_TOOL_CALLS_PHASE2 = 25   # Plus élevé car remplissage valeur par valeur
AGENT_TIMEOUT         = 120  # secondes
SLEEP_BETWEEN_CALLS   = 0.3  # pause légère pour éviter l'OOM


SYSTEM_PROMPT_PHASE1 = """Tu es l'Agent Extracteur de SynthGraph V4.4.2, Phase 1 : Template Builder.

MISSION : Lire le texte scientifique fourni et construire séquentiellement l'ossature
(le "template") de la méthode de synthèse décrite.

RÈGLES ABSOLUES :
1. Tu dois appeler les outils UN PAR UN — jamais plusieurs outils en un seul message.
2. Commence TOUJOURS par appeler `set_synthesis_method` pour identifier la méthode globale.
3. Ensuite appelle `add_synthesis_step` pour chaque étape opératoire dans l'ORDRE CHRONOLOGIQUE.
4. Si une information est absente du texte, appelle `flag_missing_info`.
5. Si tu vois une référence à une figure ("Fig. X", "Table Y"), appelle `ask_vision_agent`.
6. Quand tu as terminé, appelle `finalize_template`.
7. Chaque `citation` doit être un extrait EXACT du texte source (copier-coller).
8. Ne génère JAMAIS de texte libre. Réponds UNIQUEMENT avec un JSON d'appel d'outil.
9. Sois concis et rapide.

FORMAT DE RÉPONSE OBLIGATOIRE :
Tu dois répondre EXACTEMENT et UNIQUEMENT avec un JSON valide correspondant au schéma demandé, sans aucun texte avant ou après.
Exemple :
{"tool_name": "set_synthesis_method", "method_name": "flux_growth", "citation": "grown by the flux method", "confidence": 0.9}"""


SYSTEM_PROMPT_PHASE2_BASE = """Tu es l'Agent Extracteur de SynthGraph V4.4.2, Phase 2 : Value Filler.

MISSION : Remplir les paramètres de chaque étape du template validé, en lisant
attentivement le texte source.

CONTEXTE FOURNI : Le template validé de Phase 1 (liste des étapes avec leurs step_name),
le texte source du chunk expérimental, ET un CONTEXTE GLOBAL de l'étude.

RÈGLE V4.3 — ANTI-VISION-TUNNEL :
Si une valeur essentielle (atmosphère, concentration de dopant, condition commune) est
ABSENTE de ton chunk local mais présente dans le CONTEXTE GLOBAL, tu DOIS utiliser la
valeur du contexte global plutot que de la laisser vide. Cite alors la source comme
'[contexte global de l\'etude]' dans le champ citation.

RÈGLES ABSOLUES :
1. Tu DOIS ABSOLUMENT appeler `add_target_material` pour définir le matériau cible avant toute autre action.
2. Tu DOIS ABSOLUMENT appeler `add_precursor` pour CHAQUE réactif chimique mentionné.
3. Utilise `insert_value(step_name, field, value, citation)` pour remplir chaque température, temps, ou atmosphère.
4. Si `insert_value` retourne `confirm_required` : rappelle avec `confirm=true`.
5. Utilise `get_state()` si tu veux voir l'avancement.
6. Si tu vois une référence à une figure, appelle `ask_vision_agent`.
7. INTERDICTION FORMELLE d'appeler `finalize_extraction()` tant que tu n'as pas appelé au moins une fois `add_target_material` ET `add_precursor`. Tu dois travailler d'abord !
8. Ne JAMAIS inventer une valeur absente du texte ET du contexte global — laisse le champ vide.
9. Réponds UNIQUEMENT avec un JSON d'appel d'outil.

FORMAT DE RÉPONSE OBLIGATOIRE :
Tu dois répondre EXACTEMENT et UNIQUEMENT avec un JSON valide correspondant au schéma demandé, sans aucun texte avant ou après.
Exemple pour insérer une valeur :
{"tool_name": "insert_value", "step_name": "heating_1", "field": "temperature", "value": "1000", "citation": "heated to 1000 C", "confirm": false}"""


# ==============================================================================
# CLASSE PRINCIPALE
# ==============================================================================

class AgentExtracteurToolCaller:
    """
    Nouvel Agent Extracteur V4.2 basé sur Tool Calling séquentiel avec Gemma.

    Usage :
        agent = AgentExtracteurToolCaller()
        template = agent.run_phase1(chunk_text)
        # (le template est envoyé au DebateEngine pour validation)
        # après validation :
        state = agent.run_phase2(chunk_text, validated_template, images_map)
        extraction_dict = state.to_extraction_dict()
    """

    def __init__(
        self,
        model: str = GEMMA_MODEL,
        max_phase1_calls: int = MAX_TOOL_CALLS_PHASE1,
        max_phase2_calls: int = MAX_TOOL_CALLS_PHASE2,
        timeout: int = AGENT_TIMEOUT,
    ):
        self.model           = model
        self.max_phase1_calls = max_phase1_calls
        self.max_phase2_calls = max_phase2_calls
        self.timeout         = timeout
        self.state           = ExtractionState()
        
        # Instance unique du LLM Manager
        self.llm_manager = LlamaEngineManager.get_instance()

    # ------------------------------------------------------------------ #
    # Exécution LLM Structurée
    # ------------------------------------------------------------------ #
    
    def _call_llama_structured(self, messages: List[dict], schema_model) -> dict:
        """Appel llama-cpp-python avec génération CONTRAINTE par le JSON Schema (GBNF).

        Le schéma du modèle Pydantic (union discriminée des outils) est passé à
        llama.cpp qui construit une grammaire GBNF : la sortie est FORCÉE d'être
        un appel d'outil valide. Élimine les boucles "JSON invalide → correction"
        et les templates vides. Fallback json_object si la grammaire est rejetée.
        """
        from pydantic import TypeAdapter
        llm = self.llm_manager.get_llm()
        adapter = TypeAdapter(schema_model)

        # Schéma JSON pour la génération contrainte
        try:
            json_schema = adapter.json_schema()
        except Exception:
            json_schema = None

        def _run(response_format):
            resp = llm.create_chat_completion(
                messages=messages, response_format=response_format, temperature=0.1,
            )
            content = resp["choices"][0]["message"]["content"]
            try:
                action = adapter.validate_json(content)
                return {"content": content, "action": action, "error": None}
            except ValidationError as ve:
                return {"content": content, "action": None, "error": str(ve)}

        # 1) Tentative avec grammaire contrainte par schéma
        if json_schema is not None:
            try:
                return _run({"type": "json_object", "schema": json_schema})
            except Exception as e:
                logger.warning(f"[ExtracteurTC] Génération schéma-contrainte impossible ({e}); fallback json_object.")

        # 2) Fallback JSON libre
        try:
            return _run({"type": "json_object"})
        except Exception as e:
            logger.error(f"[ExtracteurTC] Erreur LLM structuré: {e}")
            raise

    # ------------------------------------------------------------------ #
    # PHASE 1 — Template Builder
    # ------------------------------------------------------------------ #

    def run_phase1(self, full_text: str, directive: dict = None) -> Phase1Template:
        """
        Lance la boucle Phase 1 : Llama appelle des outils pour construire le template en GBNF strict.
        """
        logger.info(f"[Phase1] Démarrage structuré (GBNF) — max_calls={self.max_phase1_calls}")
        history: List[dict] = []

        # Initialisation des chunks (par exemple, des blocs de 2500 caractères)
        chunk_size = 2500
        self.state.chunks = [full_text[i:i+chunk_size] for i in range(0, len(full_text), chunk_size)] if full_text else [""]
        self.state.current_chunk_idx = 0
        first_chunk = self.state.chunks[0]

        # [V4.4] Seeding proactif : l'Orchestrateur a DÉJÀ déterminé la méthode.
        # On la pré-enregistre pour éviter les templates vides (le modèle se
        # concentre alors sur l'ajout des étapes, pas sur l'identification).
        if directive and directive.get("macro_method"):
            self.state.phase1_template = Phase1Template(
                synthesis_method=directive["macro_method"],
                synthesis_method_citation="[directive de l'Orchestrateur]",
                confidence=0.7,
            )
            logger.info(f"[Phase1] Méthode pré-initialisée depuis la directive : {directive['macro_method']}")

        method_hint = directive.get("macro_method") if directive else None
        seeded_note = (
            f"La méthode de synthèse est DÉJÀ enregistrée ('{method_hint}'). "
            f"Ta mission est de trouver et d'ajouter les ÉTAPES opératoires.\n"
            if method_hint else
            f"Commence par appeler set_synthesis_method pour la méthode globale.\n"
        )
        user_first = (
            f"TEXTE SOURCE (chunk 1/{len(self.state.chunks)}) :\n{first_chunk}\n\n"
            f"---\n"
            f"{seeded_note}"
            f"Le document fait {len(self.state.chunks)} chunks. La recette (précurseurs, "
            f"températures, four, creuset) est souvent dans une section 'Experimental'/'Methods' "
            f"ou un tableau — utilise next_chunk pour la trouver si le chunk courant ne la contient pas.\n"
            f"Ajoute chaque étape opératoire (add_synthesis_step) dans l'ordre chronologique, "
            f"puis appelle finalize_template.\n"
            f"Effectue ton premier appel d'outil maintenant."
        )

        call_count = 0
        while call_count < self.max_phase1_calls:
            call_count += 1
            self.state.phase1_call_count = call_count

            # Construire les messages
            sys_prompt = SYSTEM_PROMPT_PHASE1
            if directive:
                dir_str = json.dumps(directive, ensure_ascii=False)
                sys_prompt = f"VOICI VOTRE ORDRE DE MISSION POUR CE PASSAGE :\n{dir_str}\n\nATTENTION : Même si l'Orchestrateur t'a déjà donné la méthode globale, TU DOIS OBLIGATOIREMENT appeler l'outil 'set_synthesis_method' pour l'enregistrer officiellement dans le système. Ensuite tu pourras ajouter les étapes. Ne saute surtout pas cette étape !\n\n" + sys_prompt

            messages = [{"role": "system", "content": sys_prompt}]
            messages += history
            if not history:
                messages.append({"role": "user", "content": user_first})

            # Génération JSON libre (guidée par prompt)
            msg_response = self._call_llama_structured(messages, AgentActionPhase1)
            content_str = msg_response["content"]
            history.append({"role": "assistant", "content": content_str})
            
            if msg_response["error"]:
                logger.warning(f"[Phase1] JSON Invalide. Demande de correction.")
                history.append({"role": "user", "content": f"ERREUR DE FORMAT JSON: {msg_response['error']}\nCorrige ton JSON pour qu'il respecte le schéma demandé."})
                time.sleep(SLEEP_BETWEEN_CALLS)
                continue
                
            action: AgentActionPhase1 = msg_response["action"]
            
            tool_name = action.tool_name
            tool_args = action.model_dump(exclude={"tool_name"})
            
            logger.info(f"[Phase1] Call {call_count}/{self.max_phase1_calls} → outil: {tool_name}")

            # Exécuter l'outil
            t0 = time.time()
            result: ToolResult = execute_phase1_tool(tool_name, tool_args, self.state, original_text=full_text, directive=directive)
            duration_ms = int((time.time() - t0) * 1000)
            
            _log_tool_event("AgentExtracteur", "Phase1", tool_name, call_count,
                            args=tool_args, result_status=result.status, error=getattr(result, 'message', ''),
                            duration_ms=duration_ms)

            # ANTI-BOUCLE Absolue Phase 1
            if result.status == "error" and tool_name == "finalize_template":
                if "set_synthesis_method" in result.message:
                    if not hasattr(self, "_p1_fails"): self._p1_fails = 0
                    self._p1_fails += 1
                    if self._p1_fails >= 2:
                        logger.warning("[Phase1] ANTI-LOOP DETECTED: Forçage de l'appel set_synthesis_method via directive.")
                        macro = directive.get("macro_method", "unknown") if directive else "unknown"
                        res = execute_phase1_tool("set_synthesis_method", {"method_name": macro, "citation": "[contexte global]", "confidence": 0.8}, self.state, original_text=full_text, directive=directive)
                        logger.info(f"[Phase1] Injection result: {res}")
                        self._p1_fails = 0
                        history.append({"role": "user", "content": f"J'AI AUTOMATIQUEMENT EXÉCUTÉ set_synthesis_method AVEC LA VALEUR '{macro}' POUR TE DÉBLOQUER. Maintenant, tu DOIS appeler add_synthesis_step."})
                        continue
                elif "add_synthesis_step" in result.message:
                    if not hasattr(self, "_p1_step_fails"): self._p1_step_fails = 0
                    self._p1_step_fails += 1
                    if self._p1_step_fails >= 2:
                        logger.warning("[Phase1] ANTI-LOOP DETECTED: Forçage de l'appel add_synthesis_step générique.")
                        res = execute_phase1_tool("add_synthesis_step", {"step_name": "etape_generique_1", "step_type": "generic", "citation": "[contexte global]"}, self.state, original_text=full_text, directive=directive)
                        logger.info(f"[Phase1] Injection result: {res}")
                        self._p1_step_fails = 0
                        history.append({"role": "user", "content": f"J'AI AUTOMATIQUEMENT EXÉCUTÉ add_synthesis_step POUR TE DÉBLOQUER. Tu peux maintenant finaliser le template."})
                        continue

            # Cas finalize
            if result.status == "finalize":
                logger.info(f"[Phase1] finalize_template() validé — {call_count} calls")
                break

            # Injecter le résultat
            result_msg = {
                "role": "user",
                "content": (
                    f"RÉSULTAT OUTIL `{tool_name}` :\n"
                    f"{json.dumps(result.model_dump(exclude_none=True), ensure_ascii=False, indent=2)}\n\n"
                    "Continue avec le prochain appel d'outil."
                ),
            }
            history.append(result_msg)
            time.sleep(SLEEP_BETWEEN_CALLS)

        else:
            logger.warning(f"[Phase1] Limite de {self.max_phase1_calls} calls atteinte — template partiel")

        if self.state.phase1_template is None:
            logger.warning("[Phase1] Template vide — création d'un fallback générique")
            from synthgraph.extraction.state import TemplateStep
            self.state.phase1_template = Phase1Template(
                synthesis_method="operation_generique",
                synthesis_method_citation="(fallback — non détecté)",
                steps=[
                    TemplateStep(
                        step_name="generic_1",
                        step_type="generic",
                        order=1,
                        citation="(fallback)",
                    )
                ],
            )

        logger.info(
            f"[Phase1] ✅ Template : méthode={self.state.phase1_template.synthesis_method}, "
            f"{len(self.state.phase1_template.steps)} étapes"
        )
        return self.state.phase1_template

    # ------------------------------------------------------------------ #
    # PHASE 2 — Value Filler
    # ------------------------------------------------------------------ #

    def run_phase2(
        self,
        full_text: str,
        validated_template: Phase1Template,
        images_map: Optional[Dict[str, str]] = None,
        global_context: Optional[dict] = None,
        directive: Optional[dict] = None
    ) -> ExtractionState:
        """
        Lance la boucle Phase 2 : Gemma remplit les paramètres de chaque étape.

        Args:
            full_text          : texte complet du document
            validated_template : template Phase 1 VALIDÉ par le DebateEngine
            images_map         : dict {figure_ref -> chemin_image} pour l'agent Vision
            global_context     : [V4.3] dict des variables communes à toute l'étude
            directive          : [V4.6] dict contenant l'ExtractionDirective (Mission)
        """

        # Injecter le template validé dans le state et initialiser les FilledSteps
        self.state.phase1_template = validated_template
        self.state.init_filled_steps_from_template()

        logger.info(
            f"[Phase2] Démarrage — {len(validated_template.steps)} étapes à remplir, "
            f"max_calls={self.max_phase2_calls} | global_context={'OUI' if global_context else 'NON'}"
        )

        chunk_size = 2500
        self.state.chunks = [full_text[i:i+chunk_size] for i in range(0, len(full_text), chunk_size)] if full_text else [""]
        self.state.current_chunk_idx = 0
        first_chunk = self.state.chunks[0]

        # Résumé du template validé pour le contexte
        template_summary = self._format_template_for_context(validated_template)

        # ------------------------------------------------------------------ #
        # [V4.3] Construction du System Prompt enrichi avec le contexte global
        # ------------------------------------------------------------------ #
        global_ctx_block = self._format_global_context(global_context)
        system_prompt_phase2 = SYSTEM_PROMPT_PHASE2_BASE + """
- review_context: Relire le contexte (précédent/suivant).
- abort_extraction: Abandonner immédiatement si le texte ne décrit PAS une synthèse (ex: caractérisation, introduction générale).

DROIT DE VETO (FAIL-FAST) : L'Orchestrateur peut se tromper en t'envoyant une route qui s'avère être une technique de caractérisation (ex: XRD, spectroscopie) au lieu d'une synthèse de matière. Dès que tu te rends compte que le texte ne décrit PAS la fabrication d'un matériau, tu DOIS IMMÉDIATEMENT appeler l'outil abort_extraction. Ne cherche pas de précurseurs, n'invente rien.
"""
        
        if directive:
            import json
            dir_str = json.dumps(directive, ensure_ascii=False)
            system_prompt_phase2 = f"VOICI VOTRE ORDRE DE MISSION POUR CE PASSAGE :\n{dir_str}\n\nATTENTION : Même si l'Orchestrateur t'a déjà donné le matériau cible et les précurseurs de départ, TU DOIS OBLIGATOIREMENT appeler 'add_target_material' puis 'add_precursor' pour les enregistrer officiellement dans le système avant de remplir les valeurs des étapes. Ne saute surtout pas cette étape !\n\n" + system_prompt_phase2

        if global_ctx_block:
            system_prompt_phase2 += (
                "\n\n"
                + "## CONTEXTE GLOBAL DE L'ÉTUDE [V4.3 — Anti-Vision-Tunnel]\n"
                + global_ctx_block
                + "\n\nSi une information manque dans ton chunk local mais figure ci-dessus, "
                + "utilise-la et cite '[contexte global de l\\'etude]'."
            )
            logger.info("[Phase2] Contexte global injecté dans le System Prompt ✅")

        user_first = (
            f"TEMPLATE VALIDÉ (Phase 1) :\n{template_summary}\n\n"
            f"---\n"
            f"TEXTE SOURCE (chunk 1/{len(self.state.chunks)}) :\n{first_chunk}\n\n"
            f"---\n"
            f"Utilise les outils de navigation (next_chunk, previous_chunk) pour lire tout le document.\n"
            f"Commence par définir le matériau cible, puis les précurseurs, "
            f"puis remplis les paramètres de chaque étape.\n"
            f"Utilise get_state() si tu as besoin de voir l'avancement.\n"
            f"Appelle un outil pour insérer la première valeur."
        )

        history: List[dict] = []
        call_count = 0

        while call_count < self.max_phase2_calls:
            call_count += 1
            self.state.phase2_call_count = call_count

            messages = [{"role": "system", "content": system_prompt_phase2}]
            messages += history
            if not history:
                messages.append({"role": "user", "content": user_first})

            msg_response = self._call_llama_structured(messages, AgentActionPhase2)
            content_str = msg_response["content"]
            history.append({"role": "assistant", "content": content_str})
            
            if msg_response["error"]:
                logger.warning(f"[Phase2] JSON Invalide. Demande de correction.")
                history.append({"role": "user", "content": f"ERREUR DE FORMAT JSON: {msg_response['error']}\nCorrige ton JSON pour qu'il respecte le schéma demandé."})
                time.sleep(SLEEP_BETWEEN_CALLS)
                continue
                
            action: AgentActionPhase2 = msg_response["action"]
            
            tool_name = action.tool_name
            tool_args = action.model_dump(exclude={"tool_name"})
            
            logger.info(f"[Phase2] Call {call_count}/{self.max_phase2_calls} → outil: {tool_name}")

            t0 = time.time()
            # Remarque : on passe '' comme base_url puisque ce n'est plus un proxy
            result: ToolResult = execute_phase2_tool(
                tool_name, tool_args, self.state, images_map, "", original_text=full_text, directive=directive
            )
            duration_ms = int((time.time() - t0) * 1000)

            _log_tool_event("AgentExtracteur", "Phase2", tool_name, call_count,
                            args=tool_args, result_status=result.status, error=getattr(result, 'message', ''),
                            duration_ms=duration_ms)

            if result.status == "aborted":
                logger.warning(f"[Phase2] Extraction abandonnée (Fail-Fast) : {result.message}")
                return {
                    "status": "ABORTED",
                    "reason": result.message,
                    "tool_calls": self.state.phase2_call_count,
                }

            # ANTI-BOUCLE Absolue Phase 2
            if result.status == "error" and tool_name == "finalize_extraction" and "add_target_material" in result.message:
                if not hasattr(self, "_p2_fails"): self._p2_fails = 0
                self._p2_fails += 1
                if self._p2_fails >= 2:
                    logger.warning("[Phase2] ANTI-LOOP DETECTED: Forçage de l'appel add_target_material via directive.")
                    target = directive.get("target_material", "unknown") if directive else "unknown"
                    precursors = directive.get("starting_materials", []) if directive else []
                    execute_phase2_tool("add_target_material", {"material_name": target, "citation": "[contexte global]", "confidence": 0.8}, self.state, images_map, "", original_text=full_text, directive=directive)
                    for prec in precursors:
                        execute_phase2_tool("add_precursor", {"material_name": prec, "role": "precursor", "citation": "[contexte global]", "confidence": 0.8}, self.state, images_map, "", original_text=full_text, directive=directive)
                    self._p2_fails = 0
                    history.append({"role": "user", "content": f"J'AI AUTOMATIQUEMENT EXÉCUTÉ add_target_material et add_precursor POUR TE DÉBLOQUER. Maintenant, remplis les étapes avec insert_value."})
                    continue

            if result.status == "finalize":
                logger.info(f"[Phase2] finalize_extraction() validé — {call_count} calls")
                break

            # Feedback
            result_dict = result.model_dump(exclude_none=True)
            feedback_content = (
                f"RÉSULTAT OUTIL `{tool_name}` :\n"
                f"{json.dumps(result_dict, ensure_ascii=False, indent=2)}\n\n"
            )

            # Rappel des étapes incomplètes
            incomplete = self.state._get_incomplete_steps()
            if incomplete:
                feedback_content += f"Étapes encore incomplètes : {incomplete}\n"
            feedback_content += "Continue avec le prochain appel d'outil."

            history.append({"role": "user", "content": feedback_content})
            time.sleep(SLEEP_BETWEEN_CALLS)

        else:
            logger.warning(f"[Phase2] Limite de {self.max_phase2_calls} calls atteinte — extraction partielle")

        snap = self.state.get_state_snapshot()
        logger.info(
            f"[Phase2] ✅ Extraction terminée — {snap['completion_percent']}% complet, "
            f"{len(self.state.vision_queries)} vision queries"
        )
        return self.state

    # ------------------------------------------------------------------ #
    # Formatage du template pour le contexte Phase 2
    # ------------------------------------------------------------------ #

    @staticmethod
    def _format_template_for_context(template: Phase1Template) -> str:
        """Résume le template Phase 1 validé pour le prompt Phase 2."""
        lines = [
            f"Méthode : {template.synthesis_method}",
            f"Confiance Phase 1 : {template.confidence:.2f}",
            f"\nÉtapes ({len(template.steps)}) :",
        ]
        for step in template.steps:
            from synthgraph.extraction.state import REQUIRED_FIELDS_BY_STEP_TYPE, OPTIONAL_FIELDS_BY_STEP_TYPE
            req  = REQUIRED_FIELDS_BY_STEP_TYPE.get(step.step_type, [])
            opt  = OPTIONAL_FIELDS_BY_STEP_TYPE.get(step.step_type, [])
            lines.append(
                f"  [{step.order}] {step.step_name} ({step.step_type})\n"
                f"       Champs REQUIS   : {req}\n"
                f"       Champs optionnels : {opt}"
            )
        if template.missing_info_flags:
            lines.append(f"\nInformations manquantes signalées : {template.missing_info_flags}")
        return "\n".join(lines)

    @staticmethod
    def _format_global_context(global_context: dict) -> str:
        """[V4.3] Formate le GlobalContext en bloc texte lisible pour le System Prompt.

        Convertit le dict GlobalContext (issu de SynthesisRouteList.global_context)
        en un bloc structuré injecté dans le System Prompt de la Phase 2.
        Les champs vides ou listes vides sont omis pour garder le prompt concis.

        Returns:
            str — bloc texte formaté, ou chaîne vide si le contexte est trivial.
        """
        if not global_context:
            return ""

        lines = []

        field_labels = {
            "goal":                    "Objectif scientifique",
            "target_material_global":  "Matériau cible global",
            "doping_elements":         "Éléments dopants",
            "doping_range":            "Plage de dopage",
            "common_atmosphere":       "Atmosphère commune",
            "common_conditions":       "Conditions communes",
            "characterization_techniques": "Techniques de caractérisation",
            "extra_global_vars":       "Variables globales supplémentaires",
        }

        for field, label in field_labels.items():
            value = global_context.get(field)
            if not value:
                continue
            if isinstance(value, list):
                if value:
                    lines.append(f"- {label} : {', '.join(str(v) for v in value)}")
            elif isinstance(value, dict):
                if value:
                    extras = "; ".join(f"{k}={v}" for k, v in value.items())
                    lines.append(f"- {label} : {extras}")
            else:
                lines.append(f"- {label} : {value}")

        return "\n".join(lines) if lines else ""

