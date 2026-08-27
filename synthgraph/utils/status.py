import json
from pathlib import Path

STATUS_PATH = Path("logs/pipeline_status.json")

def init_status(paper_name: str):
    """Initialise le fichier de statut pour un nouveau papier."""
    STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "status": "running",
        "current_paper": paper_name,
        "step": "Lecture PDF",
        "tokens_generated": 0,
        "tokens_prompt": 0,
        "agent_tokens": {},
        "nougat_status": "idle",
        "debate_messages": []
    }
    with open(STATUS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def update_status(status=None, step=None, current_paper=None, add_tokens_generated=0, add_tokens_prompt=0, nougat_status=None, debate_message=None):
    """Met à jour les informations du statut en cours."""
    STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    if STATUS_PATH.exists():
        try:
            with open(STATUS_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = {}
    else:
        data = {}

    data.setdefault("status", "running")
    data.setdefault("current_paper", "")
    data.setdefault("step", "")
    data.setdefault("tokens_generated", 0)
    data.setdefault("tokens_prompt", 0)
    data.setdefault("agent_tokens", {})
    data.setdefault("nougat_status", "idle")
    data.setdefault("debate_messages", [])

    if status is not None:
        data["status"] = status
    if step is not None:
        data["step"] = step
    if current_paper is not None:
        data["current_paper"] = current_paper
        
    current_agent = data.get("step", "")
        
    if add_tokens_generated > 0:
        data["tokens_generated"] += add_tokens_generated
        if current_agent:
            data["agent_tokens"].setdefault(current_agent, {"generated": 0, "prompt": 0})
            data["agent_tokens"][current_agent]["generated"] += add_tokens_generated
            
    if add_tokens_prompt > 0:
        data["tokens_prompt"] += add_tokens_prompt
        if current_agent:
            data["agent_tokens"].setdefault(current_agent, {"generated": 0, "prompt": 0})
            data["agent_tokens"][current_agent]["prompt"] += add_tokens_prompt
            
    if nougat_status is not None:
        data["nougat_status"] = nougat_status
    if debate_message is not None:
        data["debate_messages"].append(debate_message)

    with open(STATUS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def get_status() -> dict:
    """Récupère le statut actuel."""
    if STATUS_PATH.exists():
        try:
            with open(STATUS_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "status": "idle",
        "current_paper": "",
        "step": "",
        "tokens_generated": 0,
        "tokens_prompt": 0,
        "nougat_status": "idle",
        "debate_messages": []
    }
