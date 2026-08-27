import gc
import logging
import requests

try:
    import torch
except ImportError:
    torch = None

logger = logging.getLogger("SynthGraph.VRAMManager")

class VRAMManager:
    """
    Gestionnaire agressif de VRAM pour SynthGraph V4.
    Assure le déchargement des modèles avant et après l'inférence.
    """
    def __init__(self, agent_name: str, model_name: str, base_url: str = "http://localhost:11434"):
        self.agent_name = agent_name
        self.model_name = model_name
        self.base_url = base_url

    def __enter__(self):
        logger.debug(f"[{self.agent_name}] Préparation de la VRAM pour le modèle {self.model_name}")
        self._cleanup()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        logger.debug(f"[{self.agent_name}] Libération de la VRAM après inférence")
        self._cleanup()

    def _cleanup(self):
        """Force le nettoyage de la VRAM."""
        # 1. Déchargement via l'API locale Ollama (keep_alive=0)
        try:
            requests.post(
                f"{self.base_url}/api/generate",
                json={"model": self.model_name, "keep_alive": 0},
                timeout=5
            )
        except Exception as e:
            logger.debug(f"Impossible de contacter l'API locale pour le déchargement: {e}")

        # 2. Garbage Collection Python
        gc.collect()

        # 3. Vidage du cache CUDA si PyTorch est disponible
        try:
            if torch is not None and torch.cuda.is_available():
                torch.cuda.empty_cache()
                if hasattr(torch.cuda, "ipc_collect"):
                    torch.cuda.ipc_collect()
        except Exception:
            pass

    @staticmethod
    def log_vram_usage(context: str = ""):
        """Enregistre l'utilisation actuelle de la VRAM (nécessite nvidia-smi)."""
        import subprocess
        try:
            result = subprocess.run(['nvidia-smi', '--query-gpu=memory.used,memory.total', '--format=csv,nounits,noheader'], 
                                    capture_output=True, text=True, check=True)
            vram_info = result.stdout.strip().split('\n')[0].split(', ')
            used_vram = int(vram_info[0])
            total_vram = int(vram_info[1])
            percent = (used_vram / total_vram) * 100
            
            log_msg = f"[VRAM] {context} - Utilisée: {used_vram} MB / {total_vram} MB ({percent:.1f}%)"
            logger.info(log_msg)
            
            # Logger aussi dans un fichier dédié pour le suivi
            with open("logs/vram_tracking.log", "a", encoding="utf-8") as f:
                import datetime
                f.write(f"{datetime.datetime.now().isoformat()} - {log_msg}\n")
                
        except Exception as e:
            logger.debug(f"[VRAM] Impossible de logger la VRAM : {e}")
