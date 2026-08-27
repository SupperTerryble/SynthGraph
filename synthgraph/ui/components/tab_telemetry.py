"""
synthgraph/ui/components/tab_telemetry.py — Onglet 3: Télémétrie LLM & Métriques Multi-Agents.

Analyse la consommation de jetons (prompt/réponse), la vitesse d'inférence (tok/s),
la durée des étapes du pipeline et le suivi VRAM.
"""

from __future__ import annotations

import json
from pathlib import Path
import streamlit as st

from synthgraph.ui.components.styles import render_metric_card

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
STEPS_DIR = PROJECT_ROOT / "logs" / "steps"
VRAM_LOG_PATH = PROJECT_ROOT / "logs" / "vram_tracking.log"


def render_tab_telemetry():
    """Affiche le module de Télémétrie LLM."""
    st.subheader("📊 Télémétrie LLM & Performance des Agents")
    st.markdown("Consultez la consommation de jetons, les débits d'inférence et l'utilisation de la VRAM GPU.")

    # 1. Analyse des jetons par agent
    agent_stats = _aggregate_token_stats()

    total_prompt = sum(s["prompt_tokens"] for s in agent_stats.values())
    total_gen = sum(s["gen_tokens"] for s in agent_stats.values())
    total_tokens = total_prompt + total_gen
    avg_speed = _calc_avg_speed(agent_stats)

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        render_metric_card("Total Jetons Consommés", f"{total_tokens:,}", "Prompt + Réponses", "#58a6ff")
    with c2:
        render_metric_card("Jetons de Prompt", f"{total_prompt:,}", "Contexte d'entrée", "#30363d")
    with c3:
        render_metric_card("Jetons Générés", f"{total_gen:,}", "Réponses LLM", "#00e676")
    with c4:
        render_metric_card("Vitesse Moyenne", f"{avg_speed:.1f} tok/s", "Inférence llama-cpp", "#ffd600")

    st.markdown("---")

    col_chart1, col_chart2 = st.columns([1, 1])

    with col_chart1:
        st.markdown("#### 🤖 Consommation de Jetons par Agent")
        if agent_stats:
            chart_data = {
                "Agent": list(agent_stats.keys()),
                "Prompt Tokens": [s["prompt_tokens"] for s in agent_stats.values()],
                "Generated Tokens": [s["gen_tokens"] for s in agent_stats.values()]
            }
            st.bar_chart(chart_data, x="Agent", stack=False)
        else:
            st.info("Aucune donnée de télémétrie disponible dans logs/steps/.")

    with col_chart2:
        st.markdown("#### ⏱️ Durée d'Exécution par Étape (sec)")
        if agent_stats:
            time_data = {
                "Agent": list(agent_stats.keys()),
                "Durée (s)": [round(s["duration_s"], 1) for s in agent_stats.values()]
            }
            st.bar_chart(time_data, x="Agent", y="Durée (s)", color="#a371f7")
        else:
            st.info("Aucune donnée de durée disponible.")

    st.markdown("---")

    # 3. Suivi de la VRAM GPU
    st.markdown("### 🖥️ Suivi de la VRAM GPU & Mémoire CUDA")
    if VRAM_LOG_PATH.exists():
        try:
            with open(VRAM_LOG_PATH, "r", encoding="utf-8") as f:
                lines = f.readlines()[-30:]
            st.code("".join(lines), language="text")
        except Exception as e:
            st.error(f"Erreur lecture VRAM log : {e}")
    else:
        st.caption("Journal vram_tracking.log non détecté.")


def _aggregate_token_stats() -> dict:
    """Parcourt les fichiers logs/steps pour agréger les métriques d'agents."""
    stats = {}

    for p in STEPS_DIR.glob("step*.json"):
        try:
            with open(p, "r", encoding="utf-8") as f:
                d = json.load(f)

            agent_name = _extract_agent_name(p.name)
            p_tok = d.get("prompt_tokens", d.get("usage", {}).get("prompt_tokens", 0))
            g_tok = d.get("completion_tokens", d.get("usage", {}).get("completion_tokens", 0))
            dur = d.get("duration", d.get("execution_time_s", 0))

            if agent_name not in stats:
                stats[agent_name] = {"prompt_tokens": 0, "gen_tokens": 0, "duration_s": 0.0, "runs": 0}

            stats[agent_name]["prompt_tokens"] += p_tok
            stats[agent_name]["gen_tokens"] += g_tok
            stats[agent_name]["duration_s"] += dur
            stats[agent_name]["runs"] += 1
        except Exception:
            continue

    return stats


def _extract_agent_name(filename: str) -> str:
    if "orchestrator" in filename: return "Orchestrateur"
    if "extraction" in filename or "singleshot" in filename: return "Extracteur"
    if "contextual" in filename: return "Contextuel"
    if "thermo" in filename: return "Thermodynamicien"
    if "red_team" in filename: return "Red Team"
    if "graph" in filename: return "Architecte Graphe"
    return "Autre Agent"


def _calc_avg_speed(stats: dict) -> float:
    tot_gen = sum(s["gen_tokens"] for s in stats.values())
    tot_dur = sum(s["duration_s"] for s in stats.values())
    if tot_dur > 0:
        return tot_gen / tot_dur
    return 0.0
