"""
src/agents.py — SynthGraph
Définition des 5 agents spécialisés avec leurs system prompts.

Les agents communiquent via un moteur de débat itératif.
"""

# ==============================================================================
#  CONSTANTES
# ==============================================================================
OLLAMA_BASE_URL      = "http://localhost:11434"
AGENT_TIMEOUT        = 180       # secondes par appel LLM
DEFAULT_TEMPERATURE  = 0.1       # Déterministe pour extraction
DEBATE_TEMPERATURE   = 0.1       # Même température pour économiser RAM
MAX_DEBATE_ROUNDS    = 2         # Réduit pour économiser RAM
CONFIDENCE_THRESHOLD = 0.70
AGENT_SLEEP_BETWEEN  = 0         # Pause entre appels LLM (moteur singleton : plus besoin d'anti-OOM)
AGENT_MAX_TOKENS     = 8192      # Tokens max par réponse (augmenté pour éviter les coupures JSON)

# ==============================================================================
#  SYSTEM PROMPTS DES AGENTS
# ==============================================================================

SYSTEM_PROMPTS = {

    "orchestrateur": """Tu es l'Agent Orchestrateur Manager d'un laboratoire virtuel d'analyse de publications scientifiques.

RÔLE : Tu es le chef de projet. Tu ne dois plus te contenter d'identifier la méthode macro, tu dois rédiger des Ordres de Mission précis (Extraction Directives) pour l'Agent Extracteur.

RESPONSABILITÉS :
1. Analyser la structure du document et identifier les différentes voies de synthèse.
2. Pour chaque voie distincte, rédiger un Ordre de Mission ("Extraction Directive") strict.
3. Chaque directive doit cibler un seul matériau ou variante.

FORMAT DE SORTIE (JSON strict) :
{
  "document_type": "article|revue|thèse|brevet",
  "extraction_directives": [
    {
      "pathway_id": "R1",
      "target_material": "formule chimique ciblée (incluant les dopants si applicable)",
      "macro_method": "solid_state|flux_method|sol_gel|hydrothermal|crystal_growth|thin_film|hybrid",
      "method_justification": "Explication scientifique validant le choix de cette méthode (en utilisant le tool call ou le texte)",
      "mission_summary": "Une phrase résumant l'objectif de cette extraction (ex: 'Extraire la recette pour l'échantillon dopé au Lanthane')",
      "key_directives": [
        "Chercher la température exacte du premier palier",
        "Identifier la quantité précise d'agent flux",
        "Vérifier le temps de broyage intermédiaire"
      ]
    }
  ],
  "sections_identified": ["experimental", "results"],
  "priority_chunks": [indices des chunks les plus importants],
  "confidence": 0.0-1.0,
  "orchestrator_notes": "observations générales"
}

RÈGLES ABSOLUES :
- Retourner UNIQUEMENT du JSON valide. Aucun texte avant ou après.
- Tu as accès à l'outil 'get_route_definition' : UTILISE-LE OBLIGATOIREMENT pour vérifier la définition d'une méthode avant de la choisir de manière définitive.
- La valeur de `macro_method` DOIT ÊTRE EXACTEMENT l'une des valeurs suivantes : "solid_state", "flux_method", "sol_gel", "hydrothermal", "crystal_growth", "thin_film", "hybrid".
- Si la synthèse est complexe, multi-étapes ou inclassable, utilise "hybrid" et explique-le dans `method_justification`.
- Tes `key_directives` doivent être des injonctions fortes et spécifiques pour guider l'Extracteur sur les points les plus critiques de cette voie.
- Sépare BIEN les voies de synthèse distinctes dans 'extraction_directives'. S'il y a 2 matériaux synthétisés différemment, fais 2 directives distinctes.

MULTI-AGENT COMMUNICATION :
- Tu connais les autres agents : @thermodynamicien (validation chimique), @contextuel (vérificateur implicite), @executeur (outils Python, nettoyage).
- L'agent @extracteur exécutera tes Extraction Directives à la lettre.""",

    "extracteur": """Tu es l'Agent Extracteur, expert en lecture de protocoles expérimentaux de chimie inorganique.

RÔLE : Extraire TOUS les paramètres cinétiques et expérimentaux d'un protocole de synthèse.

CAPACITÉS :
- Extraction texte : paramètres quantitatifs (températures, durées, quantités, concentrations)
- Identification des précurseurs, solvants, agents de traitement
- Extraction des conditions opératoires (atmosphère, pression, agitation)

FORMAT DE SORTIE (JSON strict) :
{
  "pathways": [
    {
      "target_material": {"name": str, "formula": str},
      "concentration_or_variant": "détails sur la concentration ou la variante si applicable",
      "synthesis_route": "méthode utilisée pour cette voie",
      "precursors": [
        {"name": str, "formula": str, "amount": float, "unit": "g|mg|mmol|mL|molar_ratio", "purity": str|null}
      ],
      "solvents": [{"name": str, "volume_mL": float|null}],
      "synthesis_steps": [
        {
          "step_number": int,
          "operation": str,
          "temperature_C": float|null,
          "duration_min": float|null,
          "atmosphere": str|null,
          "pressure_atm": float|null,
          "stirring": str|null,
          "equipment": str|null,
          "raw_text": "extrait exact du texte source"
        }
      ],
      "byproducts": [str],
      "yield_percent": float|null
    }
  ],
  "needs_vision_clarification": bool,
  "needs_additional_text": bool,
  "confidence": 0.0-1.0,
  "extraction_notes": str
}

RÈGLES ABSOLUES :
- Copier le texte exact dans 'raw_text' pour traçabilité. Lorsqu'une seule phrase décrit une séquence d'étapes multiples (ex: paliers de température successifs), utilisez l'intégralité de cette phrase comme raw_text pour CHACUNE des étapes générées issues de cette séquence. Ne tronquez pas la phrase artificiellement.
- Ne jamais inventer des valeurs numériques.
- Si le texte ne donne pas de poids (grammes) mais donne des ratios molaires (ex: 1:1:1), autorise-toi à remplir le champ amount avec ces valeurs relatives SI ET SEULEMENT SI le champ unit est défini sur 'molar_ratio'.
- Retourner UNIQUEMENT du JSON valide.
- Si le texte te semble ne contenir qu'une discussion générale MAIS qu'il fait référence à un tableau (ex: 'Table 1'), tu ne dois PAS déclarer que les paramètres sont absents. Tu DOIS activer ton flag `needs_vision_clarification` ou `needs_additional_text` pour que le système aille extraire les données de ce tableau.
- ATTENTION : Soyez extrêmement vigilants aux opérations mécaniques (grinding, milling, mixing, pelletizing) mentionnées au sein des cycles thermiques. Si le texte mentionne des broyages intermédiaires (intermediate grindings) entre différentes températures, vous DEVEZ générer des étapes de synthèse distinctes de type operation: "Grinding" intercalées entre les étapes de chauffage.""",

    "contextuel": """Tu es l'Agent d'Analyse Contextuelle, spécialiste de la rhétorique scientifique et des connaissances tacites.

RÔLE : Identifier ce que les auteurs ne disent PAS explicitement — la "matière noire" de la science.

ANALYSE :
1. RHÉTORIQUE D'OPTIMISATION : Phrases indiquant des essais/échecs ("optimal conditions were found", "after extensive screening")
2. CONTEXTE IMPLICITE : Atmosphère, pression, équipement non mentionnés (ex: alumine = four à air)
3. CONNAISSANCES TACITES : Conventions de laboratoire sous-entendues
4. EXPÉRIENCES ÉCHOUÉES : Variants implicitement rejetés

FORMAT DE SORTIE (JSON strict) :
{
  "implicit_conditions": {
    "atmosphere": str,
    "pressure": str,
    "vessel_type": str|null
  },
  "optimization_rhetoric": [
    {"phrase": str, "interpretation": str, "implies_failure": bool}
  ],
  "dark_matter_experiments": [
    {
      "description": str,
      "inferred_condition": str,
      "reason_for_failure": str|null,
      "confidence": float
    }
  ],
  "tacit_knowledge": [
    {"knowledge": str, "source_phrase": str}
  ],
  "missing_critical_info": [str],
  "contextual_confidence": 0.0-1.0,
  "debate_notes": str
}

RÈGLES ABSOLUES :
- Distinguer clairement ce qui est EXPLICITE vs INFÉRÉ.
- Justifier chaque inférence avec une citation du texte source.
- Retourner UNIQUEMENT du JSON valide.

MULTI-AGENT COMMUNICATION :
- Tu connais les autres agents : @thermodynamicien (chimie pure), @executeur (script/data cleaning).
- 🚨 RÈGLE STRICTE ANTI-DÉLÉGATION : TU NE DOIS JAMAIS, SOUS AUCUN PRÉTEXTE, INVOQUER `@orchestrateur`. L'Orchestrateur est hors de portée dans cette phase. Ne le mentionne pas.
- Tu peux demander l'avis d'un autre agent en incluant dans tes notes textuelles (ex: debate_notes) la syntaxe `@nomagent ta question ?`.""",

    "thermodynamicien": """Tu es l'Agent Thermodynamicien, expert en chimie inorganique et thermodynamique des matériaux.

RÔLE : Valider la cohérence scientifique des extractions avant intégration dans le graphe.

VALIDATIONS :
1. CONSERVATION DE LA MASSE : Les réactifs produisent-ils les produits déclarés ?
2. VIABILITÉ DES TEMPÉRATURES : Les T° sont-elles physiquement plausibles ?
3. COHÉRENCE ATMOSPHÉRIQUE : L'atmosphère est-elle compatible avec la réaction ?
4. STÔÉCHIOMÉTRIE : Les ratios molaires sont-ils corrects ?
5. RISQUES THERMODYNAMIQUES : Réduction/oxydation non voulue, décomposition prématurée ?

FORMAT DE SORTIE (JSON strict) :
{
  "validation_passed": bool,
  "mass_balance": {
    "equation": "ex: 2SrCO3 + IrO2 -> Sr2IrO4 + 2CO2",
    "issues": [str]
  },
  "temperature_validity": {
    "all_valid": bool,
    "checks": [{"step": str, "temp_C": float, "status": "valid|warning|error", "reason": str}]
  },
  "atmosphere_coherence": {
    "coherent": bool,
    "risks": [str]
  },
  "stoichiometry": {
    "correct": bool,
    "molar_ratios": str,
    "notes": str
  },
  "overall_confidence": 0.0-1.0,
  "critical_issues": [str],
  "warnings": [str],
  "thermodynamic_notes": str,
  "recommendation": "ACCEPT|REVISE|REJECT"
}

RÈGLES ABSOLUES :
- Être rigoureux. Un matériau réductible sous H2 à haute T° doit être signalé comme CRITIQUE.
- CRITIQUE : TU DOIS IMPÉRATIVEMENT RÉPONDRE UNIQUEMENT AVEC UN OBJET JSON VALIDE. NE GÉNÈRE AUCUN TEXTE AVANT OU APRÈS LE JSON. NE GÉNÈRE JAMAIS DE TABLEAU MARKDOWN. SI TU VEUX FAIRE UN TABLEAU, UTILISE UNE LISTE D'OBJETS JSON.
- 'recommendation' doit être l'un de : ACCEPT, REVISE, REJECT.

MULTI-AGENT COMMUNICATION :
- Tu connais les autres agents : @contextuel (analyse implicite), @executeur.
- 🚨 RÈGLE STRICTE ANTI-DÉLÉGATION : TU NE DOIS JAMAIS, SOUS AUCUN PRÉTEXTE, INVOQUER `@orchestrateur`. L'Orchestrateur est hors de portée dans cette phase. Ne le mentionne pas.
- Tu peux demander l'avis d'un autre agent en incluant dans tes notes (ex: thermodynamic_notes) la syntaxe `@nomagent ta question ?`.""",

    "architecte_graphe": """Tu es l'Agent Architecte du Graphe, expert en modélisation de graphes de connaissances Neo4j.

RÔLE : Transformer les données de synthèse validées en requêtes Cypher pour Neo4j.

ARCHITECT_PROMPT_TEMPLATE = \"\"\"Tu es un Architecte Graphe Neo4j expert en science des matériaux.
{system_prompt}

PLAN D'EXTRACTION (Orchestrateur) :
{orchestrator_plan}

DONNÉES EXTRAITES (Multiples Pathways possibles) :
{extraction}

Génère une série de requêtes Cypher pour représenter ces données. 
Assure-toi de lier chaque chemin de synthèse (pathway) à son propre matériau cible (Target).\"\"\"

SCHÉMA CIBLE :
Nœuds :
  (:Material {name, formula, role: "Precursor|Target|Intermediate|Byproduct"})
  (:Operation {type, temperature_C, duration_min, atmosphere, pressure_atm})
  (:Reference {doi, title, year, authors, reliability_score})
  (:Failure {description, inferred_condition, confidence})

Relations :
  (m:Material)-[:UNDERGOES]->(op:Operation)
  (op:Operation)-[:PRODUCES]->(m2:Material)
  (m:Material)-[:EXTRACTED_FROM {confidence_score}]->(ref:Reference)
  (op:Operation)-[:HAS_VARIANT]->(f:Failure)

FORMAT DE SORTIE (JSON strict) :
{
  "cypher_queries": [
    {
      "type": "CREATE_NODE|CREATE_RELATION|MERGE",
      "description": str,
      "query": "requête Cypher complète"
    }
  ],
  "node_count": int,
  "relation_count": int,
  "graph_summary": str,
  "validation_queries": ["requête pour vérifier l'intégrité du graphe"]
}

- Chaque requête Cypher doit être syntaxiquement correcte et autonome.""",

    "reranker": """Tu es un expert documentaliste en science des matériaux.
Ton rôle est de filtrer et de sélectionner les 3 extraits les plus pertinents parmi une liste de candidats, afin de répondre à une question posée par le Thermodynamicien.

RÈGLES STRICTES :
1. Tu vas recevoir une LISTE de documents avec leurs sources et leurs contenus.
2. Tu vas recevoir une QUESTION.
3. Tu dois sélectionner EXACTEMENT 3 extraits (les plus pertinents) qui permettent de répondre à la question (ou le maximum si moins de 3 sont pertinents).
4. Tu dois retourner le résultat sous forme de JSON structuré avec la clé "selected_chunks" contenant une liste d'objets avec "source" et "content".

Exemple de sortie attendue :
{
  "selected_chunks": [
    {
      "source": "LivreA.pdf",
      "content": "Texte pertinent..."
    }
  ]
}""",

    "executeur": """Tu es l'Agent Exécuteur d'un laboratoire virtuel.
Ton rôle est d'analyser la commande d'un autre agent et d'utiliser l'un de tes outils Python pour lui répondre.
Tu as accès à des scripts de nettoyage de données et à des vérificateurs stœchiométriques.
Réponds toujours de manière concise et directe en te focalisant sur le résultat brut de l'outil."""
}

# ==============================================================================
#  IMPORTS
# ==============================================================================
import time
import gc
import re
import json
import logging
import requests
from dataclasses import dataclass, field
from typing import Optional
from synthgraph.utils.tools import safe_json_parse
from synthgraph.llm.vram import VRAMManager

logger = logging.getLogger("SynthGraph.Agents")
# ==============================================================================
#  CLASSE AGENT BASE
# ==============================================================================

@dataclass
class AgentMessage:
    """Message échangé entre agents."""
    agent_name:  str
    content:     str           # Texte brut de la réponse
    parsed_json: Optional[dict] = None
    confidence:  float = 0.0
    duration_s:  float = 0.0
    round_num:   int = 0

def _sanitize_json_for_schema(data: dict, schema_model) -> dict:
    """Nettoie les valeurs incompatibles avec le schéma Pydantic AVANT validation.
    - Convertit les strings dans les champs float en null
    - Convertit None dans les champs string en chaîne vide
    Appliqué récursivement sur les listes de sous-objets (steps, precursors).
    """
    if not schema_model or not data:
        return data

    import copy
    data = copy.deepcopy(data)

    # Récupérer les annotations de type du modèle Pydantic
    try:
        fields = schema_model.model_fields
    except AttributeError:
        return data

    for field_name, field_info in fields.items():
        if field_name not in data:
            continue
        annotation = field_info.annotation
        ann_str = str(annotation)

        # Champ float/int optionnel : convertir les strings non-numériques en None
        if "float" in ann_str or "int" in ann_str:
            val = data[field_name]
            if isinstance(val, str):
                try:
                    data[field_name] = float(val)
                except (ValueError, TypeError):
                    data[field_name] = None

        # Champ str : convertir None en ""
        elif annotation is str or "str" in ann_str:
            if data[field_name] is None:
                data[field_name] = ""

        # Champ List[SubModel] : appliquer récursivement
        elif "List" in ann_str and isinstance(data.get(field_name), list):
            # Essayer d'extraire le modèle interne
            for arg in getattr(annotation, "__args__", []):
                if hasattr(arg, "model_fields"):
                    data[field_name] = [
                        _sanitize_json_for_schema(item, arg) if isinstance(item, dict) else item
                        for item in data[field_name]
                    ]
                    break

    return data


@dataclass
class SynthAgent:
    """Agent LLM spécialisé.

    `role` (Phase 0 — plan multi-modèles) : rôle de ROUTAGE MODÈLE, transmis à
    `LlamaEngineManager.get_llm(role)` pour sélectionner le GGUF en VRAM
    (cf `config/settings.yaml: models`). Valeurs attendues : "extractor", "qa",
    "strategist", ou "default" (défaut). Un rôle non reconnu retombe sur
    `default` sans erreur (fail-safe) — donc un agent créé avec un `role`
    quelconque (ex: un identifiant d'instance) n'a d'incidence QUE si ce rôle
    est explicitement configuré dans `models:`.
    NB : avant Phase 0, ce champ portait un simple libellé humain (jamais lu
    ailleurs que dans le constructeur) — aucune régression de comportement.
    """
    name:        str
    model:       str
    system_prompt: str
    role:        str = "default"
    base_url:    str = OLLAMA_BASE_URL
    endpoint:    str = "/api/generate"
    api_format:  str = "ollama"
    temperature: float = DEFAULT_TEMPERATURE
    max_tokens:  int = AGENT_MAX_TOKENS
    timeout:     int = AGENT_TIMEOUT
    _messages:   list = field(default_factory=list)

    def call(self, user_prompt: str, context: str = "", schema_model=None, images: list = None, tools: list = None, use_grammar: bool = True) -> AgentMessage:
        """Appelle le LLM avec le system prompt de l'agent en natif via LlamaEngineManager.

        use_grammar=False : n'attache PAS la grammaire GBNF du schéma (mode json_object
        simple). Beaucoup plus rapide pour les schémas complexes ; la validation Pydantic
        se fait en aval via generate_validated_json.
        """
        from synthgraph.llm.engine import LlamaEngineManager
        import json
        import time
        import re
        from synthgraph.utils.tools import safe_json_parse
        
        full_prompt = f"{self.system_prompt}\n\n"
        if context:
            full_prompt += f"CONTEXTE DES AGENTS PRÉCÉDENTS :\n{context}\n\n"
        full_prompt += f"INSTRUCTION :\n{user_prompt}"

        if len(full_prompt) > 6000:
            full_prompt = full_prompt[:6000] + "\n\n[... contenu tronqué pour économiser RAM ...]"
            
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": f"CONTEXTE:\n{context}\n\nINSTRUCTION:\n{user_prompt}" if context else user_prompt}
        ]

        llm = LlamaEngineManager.get_instance().get_llm(self.role)
        
        kwargs = {
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
        
        if tools:
            kwargs["tools"] = tools
            
        if schema_model and use_grammar:
            kwargs["response_format"] = {
                "type": "json_object",
                "schema": schema_model.model_json_schema()
            }
        elif schema_model or "json" in full_prompt.lower() or "{" in full_prompt:
            # Mode json_object simple (pas de grammaire schéma) : rapide, validation en aval
            kwargs["response_format"] = {"type": "json_object"}
            
        start = time.time()
        completion_tokens = None  # [V4.9.1] instrumentation débit (diagnostic SLOW)
        try:
            from synthgraph.utils.tools import OntologyTool
            MAX_TOOL_LOOPS = 3
            loop_count = 0

            while loop_count < MAX_TOOL_LOOPS:
                loop_count += 1
                resp = llm.create_chat_completion(**kwargs)
                completion_tokens = (resp.get("usage") or {}).get("completion_tokens", completion_tokens)
                message = resp["choices"][0]["message"]
                
                # S'il y a un tool_call (Llama-cpp-python format)
                if message.get("tool_calls"):
                    messages.append(message)
                    for tc in message["tool_calls"]:
                        func_name = tc["function"]["name"]
                        args_str = tc["function"]["arguments"]
                        
                        logger.info(f"[{self.name}] 🛠️ Tool Call: {func_name}({args_str})")
                        if func_name == "get_route_definition":
                            try:
                                args_dict = json.loads(args_str)
                                route_name = args_dict.get("route_name", "")
                                tool_result = OntologyTool.get_route_definition(route_name)
                            except Exception as e:
                                tool_result = json.dumps({"error": str(e)})
                        else:
                            tool_result = json.dumps({"error": f"Unknown tool: {func_name}"})
                            
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc["id"],
                            "name": func_name,
                            "content": tool_result
                        })
                    
                    # Mise à jour des kwargs avec les nouveaux messages
                    kwargs["messages"] = messages
                    continue
                else:
                    raw_text = message.get("content", "")
                    break
            else:
                raw_text = json.dumps({"error": "Max tool loops reached", "agent": self.name})
                
        except Exception as e:
            logger.error(f"[{self.name}] Erreur LLM Natif : {e}")
            raw_text = json.dumps({"error": str(e), "agent": self.name})

        duration = time.time() - start
        parsed   = safe_json_parse(raw_text)

        def _safe_float(x, default=0.5):
            try:
                return float(x)
            except (TypeError, ValueError):
                return default

        if parsed:
            _conf = parsed.get("confidence",
                               parsed.get("overall_confidence",
                                          parsed.get("contextual_confidence", 0.5)))
            confidence = _safe_float(_conf, 0.5)
        else:
            confidence = 0.0

        msg = AgentMessage(
            agent_name=self.name,
            content=raw_text,
            parsed_json=parsed,
            confidence=confidence,
            duration_s=round(duration, 2)
        )
        self._messages.append(msg)

        think_match = re.search(r'<think>(.*?)</think>', raw_text, flags=re.DOTALL)
        if think_match:
            think_content = think_match.group(1).strip()
            import os
            run_id = os.environ.get("SYNTHGRAPH_CURRENT_RUN_ID", "default_run")
            log_path = f"logs/think_debates_{run_id}.md"
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(f"\n## 🧠 Agent : {self.name.capitalize()} (Confiance : {confidence:.2f})\n\n")
                f.write(f"```text\n{think_content}\n```\n")
        _tok_info = ""
        if completion_tokens and duration > 0:
            _tok_info = f", tokens={completion_tokens} ({completion_tokens / duration:.1f} tok/s)"
        logger.info(f"[{self.name}] Réponse reçue — confiance={confidence:.2f}, durée={duration:.1f}s{_tok_info}")
        try:
            from synthgraph.llm.vram import VRAMManager
            VRAMManager.log_vram_usage(f"Post-génération [{self.name}]")
        except Exception:
            pass
        time.sleep(AGENT_SLEEP_BETWEEN)
        return msg

    def generate_validated_json(self, user_prompt: str, context: str = "", schema_model=None, images: list = None, tools: list = None, max_retries: int = 2, use_grammar: bool = True) -> dict:
        """Appelle le LLM avec retry automatique sur erreur de validation Pydantic."""
        from pydantic import ValidationError

        current_user_prompt = user_prompt

        for attempt in range(max_retries + 1):
            msg = self.call(current_user_prompt, context=context, schema_model=schema_model, images=images, tools=tools, use_grammar=use_grammar)
            data = msg.parsed_json or {}

            if not data or "error" in data:
                logger.warning(f"[{self.name}] Réponse vide ou erreur LLM (tentative {attempt + 1})")
                if attempt < max_retries:
                    current_user_prompt = (
                        f"{user_prompt}\n\n"
                        f"⚠️ Ta réponse précédente était vide ou invalide. "
                        f"Génère un JSON valide respectant strictement le schéma."
                    )
                    continue
                return data

            if not schema_model:
                return data

            data = _sanitize_json_for_schema(data, schema_model)

            try:
                validated = schema_model(**data)
                logger.info(f"[{self.name}] Validation Pydantic réussie (tentative {attempt + 1})")
                return validated.model_dump()
            except ValidationError as e:
                if attempt < max_retries:
                    error_msg = str(e)
                    logger.warning(
                        f"[{self.name}] ValidationError (tentative {attempt + 1}/{max_retries + 1}): "
                        f"{error_msg[:200]}"
                    )
                    current_user_prompt = (
                        f"{user_prompt}\n\n"
                        f"⚠️ ERREUR DE VALIDATION (tentative précédente) :\n"
                        f"{error_msg}\n\n"
                        f"CORRECTIONS REQUISES :\n"
                        f"1. Les champs numériques (temperature_c, duration_h, ramp_rate_c_per_h, "
                        f"pressure_mpa, speed_rpm, etc.) DOIVENT être des nombres (float/int) ou null. "
                        f"JAMAIS une chaîne de texte comme 'slowly raised' ou 'room temperature'.\n"
                        f"2. Les champs texte (amount, citation, details) DOIVENT être des chaînes, "
                        f"JAMAIS null — utilise une chaîne vide '' si inconnu.\n"
                        f"3. Si une valeur numérique n'est pas clairement indiquée dans le texte, "
                        f"mets null plutôt que d'inventer.\n"
                        f"Corrige UNIQUEMENT les champs fautifs et renvoie le JSON complet."
                    )
                else:
                    logger.error(
                        f"[{self.name}] Validation échouée après {max_retries + 1} tentatives."
                    )
                    # Dernière tentative avec nettoyage agressif
                    sanitized = _sanitize_json_for_schema(data, schema_model)
                    try:
                        validated = schema_model(**sanitized)
                        logger.info(f"[{self.name}] Récupéré via nettoyage automatique des champs.")
                        return validated.model_dump()
                    except ValidationError:
                        logger.error(f"[{self.name}] Nettoyage insuffisant. Utilisation du JSON brut en fallback.")
                        return sanitized  # au moins les types corrigés

        return {}

# ==============================================================================
#  FACTORY DES AGENTS
# ==============================================================================

def create_agents(config: dict) -> dict[str, SynthAgent]:
    """Crée les 5 agents à partir de la configuration modulaire (llm_config.json)."""
    
    active_prov = config.get("active_provider", "ollama")
    provider_config = config.get("providers", {}).get(active_prov, {})
    
    base_url   = provider_config.get("base_url", OLLAMA_BASE_URL)
    endpoint   = provider_config.get("endpoint", "/api/generate")
    api_format = provider_config.get("api_format", "ollama")
    
    agent_models = config.get("agent_models", {})
    gen_params   = config.get("generation_params", {})
    
    temp       = gen_params.get("temperature", DEFAULT_TEMPERATURE)
    max_tokens = gen_params.get("max_tokens", AGENT_MAX_TOKENS)

    def _get_agent(name: str, model_role: str, key: str, temp_override: float = temp) -> SynthAgent:
        return SynthAgent(
            name=name,
            role=model_role,
            model=agent_models.get(key, "llama3.2:latest"),
            system_prompt=SYSTEM_PROMPTS.get(key, ""),
            base_url=base_url,
            endpoint=endpoint,
            api_format=api_format,
            temperature=temp_override,
            max_tokens=max_tokens
        )

    # [Phase 0 — plan multi-modèles] Mapping agent → rôle de routage modèle :
    # orchestrateur/extracteur → "extractor" ; agents de débat/QA → "qa".
    agents = {
        "orchestrateur":     _get_agent("Orchestrateur", "extractor", "orchestrateur"),
        "extracteur":        _get_agent("Extracteur", "extractor", "extracteur"),
        "contextuel":        _get_agent("Contextuel", "qa", "contextuel", temp_override=DEBATE_TEMPERATURE),
        "thermodynamicien":  _get_agent("Thermodynamicien", "qa", "thermodynamicien"),
        "architecte_graphe": _get_agent("ArchitecteGraphe", "qa", "architecte_graphe"),
        "reranker":          _get_agent("ReRanker", "qa", "reranker", temp_override=0.0)
    }

    # Rôle "strategist" (si un agent stratège est présent dans la config future)
    if "strategist" in agents and isinstance(agents["strategist"], SynthAgent):
        agents["strategist"].role = "strategist"

    # Instanciation de l'Agent Executeur (Outil Python)
    from synthgraph.agents.executor import AgentExecuteur
    agents["executeur"] = AgentExecuteur(model_name=agent_models.get("executeur", "llama3.2:latest"))

    logger.info(f"5 agents créés — Provider: {active_prov} | API: {api_format} | Endpoint: {base_url}{endpoint}")
    return agents

def get_agent(name: str, sys_prompt: str, model: str) -> SynthAgent:
    """Instancie un SynthAgent proprement avec la bonne configuration."""
    return SynthAgent(
        name=name, role=name, model=model, system_prompt=sys_prompt,
        base_url=OLLAMA_BASE_URL, api_format="openai"
    )
