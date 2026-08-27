"""
synthgraph/ui/components/queue_manager.py — Gestionnaire de file d'attente de batchs (Queue).

Permet de planifier, exécuter, suspendre et annuler le traitement de plusieurs PDF
sans figer l'interface Streamlit.
"""

from __future__ import annotations

import os
import sys
import time
import subprocess
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict, Optional, Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
PYTHON_EXE = sys.executable or "python"


@dataclass
class JobItem:
    job_id: str
    pdf_path: str
    filename: str
    use_debate: bool = True
    use_neo4j: bool = False
    use_vision: bool = False
    status: str = "PENDING"  # PENDING, RUNNING, COMPLETED, FAILED, CANCELLED
    added_at: float = field(default_factory=time.time)
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    error_msg: Optional[str] = None
    log_output: str = ""


class BatchQueueManager:
    """Gestionnaire thread-safe de la file d'attente des PDF."""
    
    _instance: Optional[BatchQueueManager] = None
    _lock = threading.Lock()

    def __new__(cls) -> BatchQueueManager:
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(BatchQueueManager, cls).__new__(cls)
                cls._instance._init_manager()
            return cls._instance

    def _init_manager(self) -> None:
        self.jobs: List[JobItem] = []
        self.is_running: bool = False
        self.is_paused: bool = False
        self.current_process: Optional[subprocess.Popen] = None
        self._worker_thread: Optional[threading.Thread] = None
        self._queue_lock = threading.Lock()

    def add_job(self, pdf_path: str, use_debate: bool = True, use_neo4j: bool = False, use_vision: bool = False) -> JobItem:
        """Ajoute un papier PDF à la file d'attente."""
        with self._queue_lock:
            p = Path(pdf_path)
            job_id = f"job_{int(time.time()*1000)}_{len(self.jobs)}"
            job = JobItem(
                job_id=job_id,
                pdf_path=str(p),
                filename=p.name,
                use_debate=use_debate,
                use_neo4j=use_neo4j,
                use_vision=use_vision,
                status="PENDING"
            )
            self.jobs.append(job)
            return job

    def start_processing(self) -> None:
        """Démarre la boucle de la file d'attente en arrière-plan."""
        with self._queue_lock:
            if self.is_running:
                self.is_paused = False
                return
            self.is_running = True
            self.is_paused = False
            self._worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
            self._worker_thread.start()

    def pause_processing(self) -> None:
        """Met la file d'attente en pause."""
        with self._queue_lock:
            self.is_paused = True

    def cancel_current_job(self) -> None:
        """Annule le travail en cours d'exécution."""
        with self._queue_lock:
            if self.current_process and self.current_process.poll() is None:
                try:
                    self.current_process.terminate()
                    time.sleep(0.5)
                    if self.current_process.poll() is None:
                        self.current_process.kill()
                except Exception:
                    pass
            for j in self.jobs:
                if j.status == "RUNNING":
                    j.status = "CANCELLED"
                    j.end_time = time.time()

    def clear_queue(self) -> None:
        """Efface tous les travaux terminés ou en attente."""
        with self._queue_lock:
            if not self.is_running:
                self.jobs.clear()
            else:
                self.jobs = [j for j in self.jobs if j.status == "RUNNING"]

    def get_summary(self) -> Dict[str, Any]:
        """Retourne un résumé de l'état de la queue."""
        with self._queue_lock:
            total = len(self.jobs)
            pending = sum(1 for j in self.jobs if j.status == "PENDING")
            running = sum(1 for j in self.jobs if j.status == "RUNNING")
            completed = sum(1 for j in self.jobs if j.status == "COMPLETED")
            failed = sum(1 for j in self.jobs if j.status == "FAILED")
            cancelled = sum(1 for j in self.jobs if j.status == "CANCELLED")
            return {
                "total": total,
                "pending": pending,
                "running": running,
                "completed": completed,
                "failed": failed,
                "cancelled": cancelled,
                "is_running": self.is_running,
                "is_paused": self.is_paused
            }

    def _worker_loop(self) -> None:
        """Boucle du thread d'arrière-plan."""
        while self.is_running:
            if self.is_paused:
                time.sleep(1)
                continue

            target_job: Optional[JobItem] = None
            with self._queue_lock:
                for j in self.jobs:
                    if j.status == "PENDING":
                        target_job = j
                        target_job.status = "RUNNING"
                        target_job.start_time = time.time()
                        break

            if target_job is None:
                # Aucun travail en attente
                with self._queue_lock:
                    self.is_running = False
                break

            # Lancement de l'exécution
            cmd = [PYTHON_EXE, "run.py", "--input", target_job.pdf_path]
            if not target_job.use_debate:
                cmd.append("--no-debate")
            if target_job.use_neo4j:
                cmd.append("--neo4j")
            if target_job.use_vision:
                cmd.append("--use-nougat")

            env = os.environ.copy()
            env["PYTHONIOENCODING"] = "utf-8"

            try:
                self.current_process = subprocess.Popen(
                    cmd,
                    cwd=str(PROJECT_ROOT),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    env=env
                )

                output_lines = []
                if self.current_process.stdout:
                    for line in iter(self.current_process.stdout.readline, ''):
                        output_lines.append(line)
                        target_job.log_output = "".join(output_lines[-100:])  # Garder les 100 dernières lignes

                self.current_process.wait()
                ret = self.current_process.returncode

                with self._queue_lock:
                    target_job.end_time = time.time()
                    if ret == 0:
                        target_job.status = "COMPLETED"
                    elif target_job.status != "CANCELLED":
                        target_job.status = "FAILED"
                        target_job.error_msg = f"Code de sortie non nul : {ret}"
            except Exception as e:
                with self._queue_lock:
                    target_job.end_time = time.time()
                    target_job.status = "FAILED"
                    target_job.error_msg = str(e)
            finally:
                self.current_process = None

        with self._queue_lock:
            self.is_running = False
