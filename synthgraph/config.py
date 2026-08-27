"""
synthgraph/config.py — Configuration centralisée du projet.

Charge config/settings.yaml une seule fois et expose les chemins et paramètres
utilisés partout (modèle GGUF, CUDA, URL LLM, dossiers, fichiers de config).
Les valeurs peuvent être surchargées par variables d'environnement pour la portabilité.
"""

from __future__ import annotations

import os
from pathlib import Path

import yaml

# ==============================================================================
#  CHEMINS DE BASE
# ==============================================================================
PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR   = PROJECT_ROOT / "config"
LOGS_DIR     = PROJECT_ROOT / "logs"
DATA_DIR     = PROJECT_ROOT / "data"

SETTINGS_PATH       = CONFIG_DIR / "settings.yaml"
LLM_CONFIG_PATH     = CONFIG_DIR / "llm_config.json"
AGENT_PROMPTS_PATH  = CONFIG_DIR / "agent_prompts.json"
MACRO_METHODS_PATH  = CONFIG_DIR / "macro_methods_definitions.json"

# [Phase 1 — harness bench multi-modèles] Permet à `tools/benchmark_models.py`
# (ou tout autre outil) de faire tourner le pipeline sur un settings.yaml
# temporaire (ex: models.<role> pointé sur un candidat) sans toucher au fichier
# du dépôt. Absent → comportement inchangé (SETTINGS_PATH par défaut).
_SETTINGS_PATH_OVERRIDE = os.environ.get("SYNTHGRAPH_SETTINGS_PATH")


def _load_settings() -> dict:
    path = Path(_SETTINGS_PATH_OVERRIDE) if _SETTINGS_PATH_OVERRIDE else SETTINGS_PATH
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


SETTINGS = _load_settings()
_llm     = SETTINGS.get("llm", {})
_system  = SETTINGS.get("system", {})
_models_section = SETTINGS.get("models") or {}

# ==============================================================================
#  MODÈLE LLM (in-process llama-cpp-python)
# ==============================================================================
# [Phase 0 — abstraction "modèle par rôle"] La section `models:` du YAML est la
# source de vérité si présente ; `llm.*` reste lu en FALLBACK rétrocompatible
# (comportement inchangé pour les installations sans section `models`).
_default_model_cfg = _models_section.get("default")
if not isinstance(_default_model_cfg, dict):
    _default_model_cfg = {}

MODEL_PATH = os.environ.get(
    "SYNTHGRAPH_MODEL_PATH",
    _default_model_cfg.get(
        "path",
        _llm.get("model_path", str(PROJECT_ROOT.parent / "models" / "Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf")),
    ),
)
N_CTX        = int(_default_model_cfg.get("n_ctx", _llm.get("n_ctx", 8192)))
N_GPU_LAYERS = int(_default_model_cfg.get("n_gpu_layers", _llm.get("n_gpu_layers", -1)))
N_BATCH      = int(_default_model_cfg.get("n_batch", _llm.get("n_batch", 4096)))
LLM_BASE_URL = _llm.get("base_url", "http://localhost:11434")


def _resolve_model_roles(models_section: dict, default_cfg: dict) -> dict:
    """Résout la section `models:` en dict {role: {path, n_ctx, n_gpu_layers, n_batch}}.

    Format attendu :
        models:
          default:    {path: "...", n_ctx: 8192}
          extractor:  {alias: default}
          qa:         {alias: default}
          strategist: {alias: default}

    - Une entrée avec `path` est une définition concrète de modèle (alias de base).
    - Une entrée avec `alias` pointe vers une autre entrée (résolu récursivement,
      garde-fou anti-cycle).
    - Rôle/alias introuvable ou section absente → repli sur `default_cfg`
      (fail-safe : jamais d'exception, jamais de comportement changé si `models`
      est absent du YAML).
    """
    concrete: dict = {}
    alias_of: dict = {}
    for key, val in models_section.items():
        if not isinstance(val, dict):
            continue
        if "alias" in val:
            alias_of[key] = val["alias"]
        elif "path" in val:
            concrete[key] = {
                "path":         val["path"],
                "n_ctx":        int(val.get("n_ctx", default_cfg["n_ctx"])),
                "n_gpu_layers": int(val.get("n_gpu_layers", default_cfg["n_gpu_layers"])),
                "n_batch":      int(val.get("n_batch", default_cfg["n_batch"])),
            }

    resolved: dict = dict(concrete)
    resolved.setdefault("default", dict(default_cfg))

    for role, target in alias_of.items():
        seen = {role}
        cur = target
        while cur in alias_of and cur not in seen:
            seen.add(cur)
            cur = alias_of[cur]
        resolved[role] = dict(resolved.get(cur, default_cfg))

    return resolved


MODEL_ROLES = _resolve_model_roles(
    _models_section,
    {"path": MODEL_PATH, "n_ctx": N_CTX, "n_gpu_layers": N_GPU_LAYERS, "n_batch": N_BATCH},
)


def get_model_config(role: str = "default") -> dict:
    """Retourne la config résolue {path, n_ctx, n_gpu_layers, n_batch} pour `role`.

    Rôle inconnu → repli silencieux sur 'default' (fail-safe, jamais d'exception).
    """
    return MODEL_ROLES.get(role) or MODEL_ROLES["default"]

# ==============================================================================
#  SYSTÈME (CUDA)
# ==============================================================================
CUDA_PATH = os.environ.get(
    "CUDA_PATH",
    _system.get("cuda_path", "C:/Program Files/NVIDIA GPU Computing Toolkit/CUDA/v13.3"),
)


def setup_cuda_dll() -> None:
    """Windows : ajoute les répertoires DLL CUDA au chemin de recherche.

    No-op sur les autres OS ou si les répertoires n'existent pas.
    À appeler AVANT tout `import llama_cpp`.
    """
    if os.name != "nt":
        return
    for sub in ("bin", os.path.join("bin", "x64")):
        p = os.path.join(CUDA_PATH, sub)
        if os.path.isdir(p):
            try:
                os.add_dll_directory(p)
            except Exception:
                pass
