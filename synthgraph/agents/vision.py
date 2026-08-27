# -*- coding: utf-8 -*-
"""
synthgraph/agents/vision.py — SynthGraph V4.10

Agent Vision via SOUS-PROCESSUS JETABLE (décision Terry 2026-07-13).

Historique : la V4.8 chargeait le modèle vision in-process ; un crash natif du
mmproj PaliGemma legacy a corrompu le contexte CUDA du process entier → 3 papiers
d'un batch perdus. Désormais l'inférence vision vit dans `vision_worker.py`,
spawné pour UN lot de questions puis mort : un crash natif n'y tue que le worker,
et l'OS garantit la restitution de sa VRAM.

Budget VRAM inchangé (swap) : le parent décharge le 8B AVANT de lancer le worker
(Qwen2.5-VL-3B ≈ 3,3 Go seul), le 8B se recharge paresseusement après.

Règle d'or : une valeur lue dans une figure porte une provenance `vision:<image>`
dans le graphe — jamais déguisée en citation textuelle. Réponse invalide → le
trou reste déclaré.
"""

from __future__ import annotations

import json
import logging
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional

logger = logging.getLogger("SynthGraph.Vision")

DEFAULT_VISION_MODEL = "D:/projet/models/Qwen2.5-VL-3B-Instruct-Q4_K_M.gguf"
DEFAULT_VISION_MMPROJ = "D:/projet/models/mmproj-Qwen2.5-VL-3B-Instruct-f16.gguf"
WORKER_PATH = Path(__file__).with_name("vision_worker.py")
BASE_TIMEOUT_S = 180          # chargement modèle
PER_QUERY_TIMEOUT_S = 40
NOT_SHOWN_MARKERS = ("not shown", "not visible", "cannot", "unclear", "no information",
                     "unanswerable", "je ne", "non visible")


class VisionAgent:
    """Pilote le worker vision jetable. Singleton côté process principal."""

    _instance: Optional["VisionAgent"] = None
    _broken: bool = False  # échec STRUCTUREL (load failed / timeout) → ne plus réessayer

    def __init__(self, model_path: str = DEFAULT_VISION_MODEL,
                 mmproj_path: str = DEFAULT_VISION_MMPROJ):
        self.model_path = model_path
        self.mmproj_path = mmproj_path

    @classmethod
    def get_instance(cls) -> "VisionAgent":
        if cls._instance is None:
            model, mmproj = DEFAULT_VISION_MODEL, DEFAULT_VISION_MMPROJ
            try:
                import yaml
                from synthgraph.config import SETTINGS_PATH
                if Path(SETTINGS_PATH).exists():
                    cfg = (yaml.safe_load(open(SETTINGS_PATH, encoding="utf-8")) or {}).get("vision", {})
                    model = cfg.get("model_path", model)
                    mmproj = cfg.get("mmproj_path", mmproj)
            except Exception:
                pass
            cls._instance = VisionAgent(model, mmproj)
        return cls._instance

    def available(self) -> bool:
        return (not VisionAgent._broken and WORKER_PATH.exists()
                and Path(self.model_path).exists() and Path(self.mmproj_path).exists())

    def ask_batch(self, queries: list[dict]) -> list[dict]:
        """queries: [{'image': path, 'question': str, ...passthrough}] → ajoute 'answer'.

        UN worker jetable pour tout le lot. Échec structurel (chargement/timeout)
        → réponses None + fusible _broken (plus de tentative dans ce process)."""
        if not queries:
            return []
        if not self.available():
            if not VisionAgent._broken:
                logger.warning("[Vision] Modèle/worker introuvable — vision indisponible.")
            return [dict(q, answer=None) for q in queries]

        # SWAP : libérer la VRAM du 8B pour le worker (rechargé paresseusement après)
        try:
            from synthgraph.llm.engine import LlamaEngineManager
            LlamaEngineManager.get_instance().unload_model()
        except Exception as e:
            logger.warning(f"[Vision] Déchargement du modèle texte impossible : {e}")

        job = {"model_path": self.model_path, "mmproj_path": self.mmproj_path,
               "queries": [{"image": q["image"], "question": q["question"]} for q in queries]}
        with tempfile.NamedTemporaryFile("w", suffix="_vision_job.json", delete=False,
                                         encoding="utf-8") as f:
            json.dump(job, f, ensure_ascii=False)
            jobfile = f.name

        timeout = BASE_TIMEOUT_S + PER_QUERY_TIMEOUT_S * len(queries)
        logger.info(f"[Vision] Worker jetable : {len(queries)} question(s), timeout {timeout}s")
        answers: list = [None] * len(queries)
        try:
            proc = subprocess.run(
                [sys.executable, str(WORKER_PATH), jobfile],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=timeout,
            )
            # [V4.11] Audit, problèmes 2-3 : les diagnostics du worker partaient en
            # DEBUG (filtré par la config INFO) → échecs par requête invisibles par
            # construction. Relayés en INFO désormais (8 dernières lignes).
            for line in (proc.stderr or "").splitlines()[-8:]:
                logger.info(f"[Vision·worker] {line}")
            last = next((l for l in reversed((proc.stdout or "").splitlines()) if l.strip()), "")
            result = json.loads(last) if last.startswith("{") else {}
            if "answers" in result:
                answers = result["answers"]
                # [V4.11] Compteur HONNÊTE : distinguer les réponses exploitables
                # (une valeur) des refus ('not shown') et des échecs (None). Avant,
                # 'N réponse(s)' comptait les refus → le log suggérait un succès
                # alors qu'aucun trou n'était comblé.
                n_info = sum(1 for a in answers if is_informative_answer(a))
                n_refus = sum(1 for a in answers if a and not is_informative_answer(a))
                n_echec = sum(1 for a in answers if not a)
                logger.info(f"[Vision] Worker terminé (rc={proc.returncode}) — "
                            f"{n_info} exploitable(s), {n_refus} refus ('not shown'), "
                            f"{n_echec} échec(s) sur {len(answers)} question(s)")
                if answers and n_echec == len(answers):
                    logger.warning("[Vision] ⚠ 100% d'échecs par requête — vérifier le format "
                                   "des images (voir lignes [Vision·worker] ci-dessus)")
            else:
                logger.error(f"[Vision] Échec structurel du worker (rc={proc.returncode}) : "
                             f"{result.get('error', (proc.stderr or '')[-200:])} — fusible activé")
                VisionAgent._broken = True
        except subprocess.TimeoutExpired:
            logger.error(f"[Vision] Worker TIMEOUT ({timeout}s) — tué, fusible activé "
                         f"(le batch continue, trous conservés)")
            VisionAgent._broken = True
        except Exception as e:
            logger.error(f"[Vision] Lancement worker impossible : {e} — fusible activé")
            VisionAgent._broken = True
        finally:
            try:
                Path(jobfile).unlink(missing_ok=True)
            except Exception:
                pass

        return [dict(q, answer=(answers[i] if i < len(answers) else None))
                for i, q in enumerate(queries)]

    def ask(self, image_path: str, question: str) -> Optional[str]:
        """Question unique (utilisé par les smoke tests)."""
        res = self.ask_batch([{"image": image_path, "question": question}])
        return res[0].get("answer") if res else None


def is_informative_answer(answer: Optional[str]) -> bool:
    """Vrai si la réponse vision semble contenir une information exploitable."""
    if not answer:
        return False
    low = answer.lower()
    return not any(m in low for m in NOT_SHOWN_MARKERS)
