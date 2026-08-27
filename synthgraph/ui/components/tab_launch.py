"""
synthgraph/ui/components/tab_launch.py — Onglet 1: Lancement & File d'attente (Batch Queue & Live Monitoring).

Gère l'importation de PDF, la configuration des paramètres de run, la file d'attente multi-papiers,
et le suivi en direct du pipeline et des agents LLM.
"""

from __future__ import annotations

import os
import json
import time
from pathlib import Path
import streamlit as st

from synthgraph.ui.components.styles import render_metric_card, render_status_badge
from synthgraph.ui.components.queue_manager import BatchQueueManager

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
EXEC_LOG_PATH = PROJECT_ROOT / "logs" / "execution_log.md"
STEP_PROGRESS_PATH = PROJECT_ROOT / "logs" / "pipeline_status.json"


def render_tab_launch():
    """Affiche le module de Lancement et de Suivi Temps Réel."""
    queue_mgr = BatchQueueManager()

    st.subheader("🚀 Centre de Lancement & File d'Attente (Batch Processing)")
    st.markdown("Planifiez l'extraction de vos articles scientifiques en lot ou à l'unité sans bloquer l'interface.")

    # -------------------------------------------------------------------------
    # 1. BARRE DE CONTRÔLE DE LA FILE D'ATTENTE & KPIS
    # -------------------------------------------------------------------------
    summary = queue_mgr.get_summary()

    col_kpi1, col_kpi2, col_kpi3, col_kpi4, col_kpi5 = st.columns(5)
    with col_kpi1:
        render_metric_card("Total Travaux", str(summary["total"]), "Fichiers chargés", "#30363d")
    with col_kpi2:
        render_metric_card("En Attente", str(summary["pending"]), "Dans la queue", "#d29922")
    with col_kpi3:
        render_metric_card("En Cours", str(summary["running"]), "Extraction active", "#00f2fe")
    with col_kpi4:
        render_metric_card("Terminés", str(summary["completed"]), "Cypher / Neo4j généré", "#2ea043")
    with col_kpi5:
        render_metric_card("Échecs", str(summary["failed"]), "Erreurs / Rejets", "#f85149")

    # Boutons de contrôle de la file
    c_btn1, c_btn2, c_btn3, c_btn4 = st.columns([2, 2, 2, 2])
    with c_btn1:
        if st.button("🚀 Démarrer la File", type="primary", use_container_width=True, disabled=summary["running"] or summary["pending"] == 0):
            queue_mgr.start_processing()
            st.toast("File d'attente démarrée !", icon="🚀")
            st.rerun()

    with c_btn2:
        if summary["is_paused"]:
            if st.button("▶️ Reprendre", use_container_width=True):
                queue_mgr.start_processing()
                st.toast("File d'attente reprise", icon="▶️")
                st.rerun()
        else:
            if st.button("⏸️ Pause", use_container_width=True, disabled=not summary["running"]):
                queue_mgr.pause_processing()
                st.toast("File d'attente mise en pause", icon="⏸️")
                st.rerun()

    with c_btn3:
        if st.button("🛑 Annuler Run Actuel", use_container_width=True, disabled=not summary["running"]):
            queue_mgr.cancel_current_job()
            st.toast("Run actuel annulé", icon="🛑")
            st.rerun()

    with c_btn4:
        if st.button("🗑️ Vider la File", use_container_width=True, disabled=summary["running"]):
            queue_mgr.clear_queue()
            st.toast("Queue nettoyée", icon="🗑️")
            st.rerun()

    st.markdown("---")

    # -------------------------------------------------------------------------
    # 2. SECTIONS PRINCIPALES (TABLEAU DE LA QUEUE & FEED LIVE)
    # -------------------------------------------------------------------------
    col_queue, col_live = st.columns([1, 1])

    with col_queue:
        st.markdown("### 📋 File d'Attente")
        if not queue_mgr.jobs:
            st.info("La file d'attente est actuellement vide. Utilisez la barre latérale pour ajouter des fichiers PDF.")
        else:
            for idx, job in enumerate(queue_mgr.jobs):
                with st.container(border=True):
                    col_j1, col_j2 = st.columns([3, 1])
                    with col_j1:
                        st.markdown(f"**{idx+1}. {job.filename}**")
                        opts = []
                        if job.use_debate: opts.append("Débat QA")
                        if job.use_neo4j: opts.append("Neo4j")
                        if job.use_vision: opts.append("Vision/Nougat")
                        st.caption("Options: " + (", ".join(opts) if opts else "Standard"))
                    with col_j2:
                        badge_html = render_status_badge(job.status)
                        st.markdown(badge_html, unsafe_allow_html=True)
                        if job.end_time and job.start_time:
                            dur = int(job.end_time - job.start_time)
                            st.caption(f"⏱️ {dur}s")

    with col_live:
        st.markdown("### ⚡ Suivi Temps Réel du Pipeline")

        # Visualisation des agents du pipeline
        active_step = _detect_current_step()
        _render_agent_stepper(active_step)

        # Journal d'exécution Live
        st.markdown("#### 📜 Console de Logs (Live)")
        auto_refresh = st.checkbox("Rafraîchir automatiquement les logs", value=summary["running"])

        log_content = _read_log_file()
        st.markdown(f'<div class="log-terminal">{log_content}</div>', unsafe_allow_html=True)

        if auto_refresh and summary["running"]:
            time.sleep(2)
            st.rerun()


def _detect_current_step() -> str:
    """Détecte l'étape active à partir des logs/steps et pipeline_status.json."""
    if STEP_PROGRESS_PATH.exists():
        try:
            with open(STEP_PROGRESS_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("current_step", "Initialisation")
        except Exception:
            pass
    return "En attente"


def _render_agent_stepper(active_step: str):
    """Affiche une chaîne visuelle des agents LLM actifs."""
    agents = [
        ("📄 PDF", "Lecture PDF"),
        ("🎯 Stratège", "Stratège"),
        ("🔬 Extracteur", "Extracteur"),
        ("🧠 Contextuel", "Contextuel"),
        ("⚗️ Thermo", "Thermodynamicien"),
        ("🛡️ Red Team", "Red Team"),
        ("🗄️ Cypher", "Architecte Graphe")
    ]

    pills_html = '<div style="display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 16px;">'
    for name, step_key in agents:
        is_active = (step_key.lower() in active_step.lower()) or (active_step == "Terminé")
        active_cls = "active" if is_active else ""
        pills_html += f'<div class="agent-pill {active_cls}">{name}</div>'
    pills_html += '</div>'

    st.markdown(pills_html, unsafe_allow_html=True)


def _read_log_file() -> str:
    """Lit le journal d'exécution."""
    if EXEC_LOG_PATH.exists():
        try:
            with open(EXEC_LOG_PATH, "r", encoding="utf-8") as f:
                content = f.read()
                return content[-4000:] if len(content) > 4000 else content
        except Exception as e:
            return f"Erreur de lecture du journal : {e}"
    return "Aucune session d'extraction en cours..."
