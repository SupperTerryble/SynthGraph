import json
import logging
import time
from typing import Dict, Any, List
from synthgraph.validation.deterministic import compute_stoichiometry_report, classify_synthesis_method, classify_solvent

logger = logging.getLogger("SynthGraph.Executeur")

class AgentExecuteur:
    def __init__(self, model_name: str = "deepseek-r1:8b"):
        self.model_name = model_name

    def execute_command(self, command_str: str) -> str:
        """
        Invoque le LLM pour parser la commande textuelle et choisir un outil Python.
        Exécute l'outil et retourne le résultat formaté pour le débat.
        """
        logger.info(f"[AgentExecuteur] Réception commande : {command_str[:80]}")
        
        # Import retardé pour éviter les imports circulaires
        from synthgraph.agents.base import get_agent, SYSTEM_PROMPTS
        
        sys_prompt = SYSTEM_PROMPTS.get("executeur", 
            "Tu es l'Agent Exécuteur. Choisis l'outil à exécuter."
        )
        
        sys_prompt += "\n\nRéponds UNIQUEMENT par un JSON valide de la forme :\n"
        sys_prompt += '{"tool": "nom_de_l_outil_ou_none", "args": {"arg1": "val1"}, "reasoning": "pourquoi"}'
        
        agent = get_agent("Executeur", sys_prompt, self.model_name)
        msg = agent.call(command_str)
        
        parsed = msg.parsed_json or {}
        tool_name = parsed.get("tool")
        args = parsed.get("args", {})
        
        logger.info(f"[AgentExecuteur] Le modèle a choisi l'outil : {tool_name}")
        
        result = ""
        if tool_name == "tool_check_stoichiometry":
            precs = args.get("precursors", [])
            target = args.get("target", "")
            if isinstance(precs, str): precs = [precs]
            res = compute_stoichiometry_report(precs, target)
            result = f"Rapport Stœchiométrique : {res}"
            
        elif tool_name == "tool_classify_method":
            text = args.get("text", "")
            keywords = args.get("keywords", "")
            if isinstance(keywords, list): keywords = " ".join(keywords)
            res = classify_synthesis_method(text, keywords)
            result = f"Classification de la méthode : {res}"
            
        elif tool_name == "tool_classify_solvent":
            name = args.get("name", "")
            temp = args.get("temp_C", None)
            if isinstance(temp, str) and temp.replace('.', '', 1).isdigit():
                temp = float(temp)
            elif isinstance(temp, str):
                temp = None
            res = classify_solvent(name, temp)
            result = f"Classification du solvant '{name}' : {res}"
            
        else:
            result = parsed.get("response", "Aucun outil n'a pu être sélectionné pour répondre à cette requête.")
            
        final_response = f"Rapport de l'Agent Exécuteur :\n{result}\n(Justification: {parsed.get('reasoning', 'N/A')})"
        logger.info(f"[AgentExecuteur] Résultat : {final_response}")
        return final_response
