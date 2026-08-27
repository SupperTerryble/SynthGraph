"""
synthgraph/ui/components/styles.py — Styles CSS personnalisés "Dark Material Science".

Propose un design sombre moderne avec badges fluorescents, cartes réactives,
et indicateurs visuels pour les agents LLM et les métriques de synthèse.
"""

import streamlit as st

DARK_MATERIAL_CSS = """
<style>
/* Main dark background enhancements */
.stApp {
    background-color: #0d1117;
    color: #c9d1d9;
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
}

/* Sidebar styling */
section[data-testid="stSidebar"] {
    background-color: #161b22;
    border-right: 1px solid #30363d;
}

/* Metric cards container */
.metric-card {
    background: linear-gradient(135deg, #161b22 0%, #21262d 100%);
    border: 1px solid #30363d;
    border-radius: 10px;
    padding: 16px 20px;
    margin-bottom: 12px;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
    transition: transform 0.2s ease, border-color 0.2s ease;
}

.metric-card:hover {
    transform: translateY(-2px);
    border-color: #58a6ff;
}

.metric-title {
    font-size: 0.82rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: #8b949e;
    margin-bottom: 6px;
}

.metric-value {
    font-size: 1.8rem;
    font-weight: 700;
    color: #f0f6fc;
}

.metric-subtitle {
    font-size: 0.75rem;
    color: #8b949e;
    margin-top: 4px;
}

/* Badges Status */
.badge {
    display: inline-block;
    padding: 4px 10px;
    border-radius: 20px;
    font-size: 0.75rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.04em;
}

.badge-accept {
    background-color: rgba(46, 160, 67, 0.2);
    color: #3fb950;
    border: 1px solid #2ea043;
}

.badge-reject {
    background-color: rgba(248, 81, 73, 0.2);
    color: #f85149;
    border: 1px solid #da3633;
}

.badge-revise {
    background-color: rgba(210, 153, 34, 0.2);
    color: #d29922;
    border: 1px solid #9e6a03;
}

.badge-info {
    background-color: rgba(56, 139, 253, 0.2);
    color: #58a6ff;
    border: 1px solid #1f6beb;
}

/* Agent Flow Badge */
.agent-pill {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 6px 14px;
    border-radius: 8px;
    font-size: 0.85rem;
    font-weight: 600;
    border: 1px solid #30363d;
    background-color: #161b22;
    color: #c9d1d9;
}

.agent-pill.active {
    border-color: #00f2fe;
    background: linear-gradient(135deg, rgba(0,242,254,0.15) 0%, rgba(4,93,233,0.15) 100%);
    color: #00f2fe;
    box-shadow: 0 0 10px rgba(0, 242, 254, 0.3);
}

/* Thinking accordion box */
.think-box {
    background-color: #0d1117;
    border-left: 3px solid #a371f7;
    border-radius: 4px;
    padding: 12px 16px;
    font-family: 'Consolas', 'Courier New', monospace;
    font-size: 0.85rem;
    color: #d2a8ff;
    white-space: pre-wrap;
    word-break: break-word;
    margin-top: 8px;
    margin-bottom: 12px;
}

/* Log output terminal style */
.log-terminal {
    background-color: #010409;
    border: 1px solid #30363d;
    border-radius: 8px;
    padding: 14px;
    font-family: 'JetBrains Mono', 'Fira Code', 'Consolas', monospace;
    font-size: 0.82rem;
    color: #7ee787;
    max-height: 380px;
    overflow-y: auto;
    white-space: pre-wrap;
}

/* Tabs styling */
button[data-baseweb="tab"] {
    font-weight: 600 !important;
    font-size: 0.95rem !important;
    padding: 10px 18px !important;
}

button[aria-selected="true"] {
    color: #58a6ff !important;
    border-bottom-color: #1f6beb !important;
}
</style>
"""


def apply_theme():
    """Injecte le thème CSS Dark Material Science dans la page Streamlit."""
    st.markdown(DARK_MATERIAL_CSS, unsafe_allow_html=True)


def render_metric_card(title: str, value: str, subtitle: str = "", border_color: str = "#30363d"):
    """Rend une carte KPI stylisée."""
    html = f"""
    <div class="metric-card" style="border-color: {border_color};">
        <div class="metric-title">{title}</div>
        <div class="metric-value">{value}</div>
        {"<div class='metric-subtitle'>" + subtitle + "</div>" if subtitle else ""}
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)


def render_status_badge(status: str) -> str:
    """Retourne le HTML d'un badge de statut formaté."""
    st_upper = str(status).upper()
    if st_upper in ["ACCEPT", "SUCCESS", "PASSED"]:
        cls = "badge-accept"
    elif st_upper in ["REJECT", "VETO", "FAILED", "ERROR"]:
        cls = "badge-reject"
    elif st_upper in ["REVISE", "NEEDS_DATA", "WARNING"]:
        cls = "badge-revise"
    else:
        cls = "badge-info"
    return f'<span class="badge {cls}">{st_upper}</span>'
