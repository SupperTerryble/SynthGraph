import gc
import logging
import time
from typing import Optional

from synthgraph.config import MODEL_PATH, N_CTX, N_GPU_LAYERS, N_BATCH, get_model_config, setup_cuda_dll

# Configure les DLL CUDA (Windows) AVANT d'importer llama_cpp
setup_cuda_dll()

from llama_cpp import Llama

logger = logging.getLogger("SynthGraph.LlamaEngine")

class LlamaEngineManager:
    """
    Gestionnaire centralisé pour l'instance Llama native.
    Permet un contrôle agressif de la VRAM, particulièrement utile pour les 'Model Swaps'
    (ex: décharger Gemma avant de charger PaliGemma).

    [Phase 0 — plan multi-modèles] `get_llm(role=...)` charge le modèle associé au
    rôle demandé (cf `synthgraph.config.get_model_config`) et décharge l'ancien
    d'abord si le GGUF diffère (contrainte : un seul gros modèle en VRAM à la
    fois, RTX 3070 8 Go). Tant que tous les rôles pointent sur le même alias
    (`default`), aucun swap ne se produit — comportement strictement identique
    à l'ancienne API `get_llm()` sans argument.
    """

    _instance = None

    def __init__(self, model_path: str = MODEL_PATH, n_ctx: int = N_CTX, n_gpu_layers: int = N_GPU_LAYERS):
        self.model_path = model_path
        self.n_ctx = n_ctx
        self.n_gpu_layers = n_gpu_layers
        self._llm: Optional[Llama] = None
        self._current_role: Optional[str] = None
        self._current_config: Optional[dict] = None
        # Instrumentation swap (Phase 0 — pour le harness bench de la Phase 1)
        self.n_swaps: int = 0
        self.total_swap_seconds: float = 0.0

    @classmethod
    def get_instance(cls, model_path: str = MODEL_PATH) -> "LlamaEngineManager":
        """Singleton pattern for central access."""
        if cls._instance is None:
            cls._instance = LlamaEngineManager(model_path=model_path)
        return cls._instance

    def _load_config(self, cfg: dict, role: str) -> Llama:
        """Charge le GGUF décrit par `cfg` = {path, n_ctx, n_gpu_layers, n_batch}."""
        logger.info(f"Chargement natif du modèle GGUF (rôle={role}) : {cfg['path']}")
        logger.info(f"Configuration : n_gpu_layers={cfg['n_gpu_layers']}, n_ctx={cfg['n_ctx']}")

        llm = Llama(
            model_path=cfg["path"],
            n_gpu_layers=cfg["n_gpu_layers"],
            n_ctx=cfg["n_ctx"],
            n_batch=cfg.get("n_batch", N_BATCH),   # Optimisation : ingestion massive pour accélérer le Prompt Eval
            flash_attn=True,   # Équivalent de TurboQuant : réduit drastiquement la conso VRAM du contexte
            verbose=False
        )
        logger.info("Modèle chargé en VRAM avec succès (Flash Attention / TurboQuant ACTIF).")
        return llm

    def _unload_native(self) -> None:
        """Déchargement natif silencieux (utilisé en interne par `get_llm` lors d'un swap)."""
        if self._llm is None:
            return
        del self._llm
        self._llm = None
        gc.collect()
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except ImportError:
            pass

    def load_model(self) -> Llama:
        """Charge le modèle en VRAM si ce n'est pas déjà fait.

        Rétrocompat : équivalent à `get_llm("default")` — charge le rôle `default`.
        """
        return self.get_llm("default")

    def get_llm(self, role: str = "default") -> Llama:
        """Retourne l'instance Llama pour `role` (la charge si nécessaire).

        Si le modèle du rôle demandé diffère de celui actuellement en VRAM,
        l'ancien est déchargé AVANT le chargement du nouveau (un seul gros
        modèle en VRAM à la fois). Rôle inconnu → repli sur `default`
        (cf `synthgraph.config.get_model_config`, fail-safe).
        """
        cfg = get_model_config(role)

        if self._llm is not None and self._current_config == cfg:
            # Même modèle déjà chargé (rôle identique, ou alias pointant sur le
            # même GGUF) : aucune action, pas de swap.
            return self._llm

        previous_role = self._current_role
        t0 = time.time()

        if self._llm is not None:
            self._unload_native()

        self._llm = self._load_config(cfg, role)
        self._current_role = role
        self._current_config = cfg

        if previous_role is not None:
            elapsed = time.time() - t0
            self.n_swaps += 1
            self.total_swap_seconds += elapsed
            logger.info(f"[LlamaEngine] Swap {previous_role} → {role} : {elapsed:.1f}s")

        return self._llm

    def swap_stats(self) -> dict:
        """Instrumentation : nombre de swaps et temps cumulé passé à swapper."""
        return {
            "n_swaps": self.n_swaps,
            "total_swap_seconds": round(self.total_swap_seconds, 2),
        }

    def unload_model(self):
        """
        Déchargement agressif du modèle pour libérer 100% de la VRAM.
        Indispensable avant d'appeler l'Agent Vision ou un autre gros processus CUDA.
        """
        if self._llm is not None:
            logger.info(f"Déchargement de {self._current_role or self.model_path} de la VRAM...")

            self._unload_native()
            self._current_role = None
            self._current_config = None

            # Vider le cache CUDA (PyTorch) déjà géré par _unload_native ; log final.
            logger.info("VRAM libérée avec succès.")
        else:
            logger.debug("Aucun modèle à décharger (VRAM déjà libre).")
