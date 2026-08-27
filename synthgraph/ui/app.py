import os
import sys
import json
import time
import subprocess
from pathlib import Path
# Racine du projet (synthgraph/ui/app.py -> remonter de 3 niveaux)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
import streamlit as st
from streamlit_agraph import agraph, Node, Edge, Config

# Configuration de la page
st.set_page_config(page_title="SynthGraph", page_icon="🧪", layout="wide")

# Chemins
UPLOAD_DIR = Path("data")
UPLOAD_DIR.mkdir(exist_ok=True)
UPLOAD_PATH = UPLOAD_DIR / "uploaded_paper.pdf"
EXEC_LOG_PATH = Path("logs/execution_log.md")
GRAPH_DATA_PATH = Path("logs/steps/step6_graph.json")

# Titre
st.title("🧪 SynthGraph — Extraction Multi-Agents V2")
st.markdown("*Une preuve de concept (PoC) propulsée par des LLMs locaux (Ollama) pour modéliser des graphes de synthèse en science des matériaux à partir de la littérature.*")

# =====================================================================
# SIDEBAR (Configuration & Upload)
# =====================================================================
with st.sidebar:
    st.header("⚙️ Configuration")
    
    uploaded_file = st.file_uploader("Importer un article (PDF)", type=["pdf"])
    
    st.markdown("---")
    use_marker = st.checkbox("Utiliser Marker-pdf (Vision avancée)", value=False, help="Requis PyTorch. Convertit le PDF en conservant les tableaux, au lieu de récupérer du texte brut.")
    
    start_btn = st.button("🚀 Démarrer l'Extraction", type="primary", use_container_width=True)

# =====================================================================
# FONCTIONS UTILITAIRES
# =====================================================================
def get_log_content() -> str:
    """Lit le log d'exécution en temps réel."""
    if EXEC_LOG_PATH.exists():
        with open(EXEC_LOG_PATH, "r", encoding="utf-8") as f:
            return f.read()
    return "En attente du démarrage du log..."

def render_graph():
    """Charge les données du graphe JSON et le rend via agraph."""
    if not GRAPH_DATA_PATH.exists():
        st.warning("Aucune donnée de graphe trouvée (step6_graph.json).")
        return
        
    try:
        with open(GRAPH_DATA_PATH, "r", encoding="utf-8") as f:
            graph_data = json.load(f)
            data = graph_data.get("data", {})
    except Exception as e:
        st.error(f"Erreur lecture graphe: {e}")
        return

    nodes = []
    edges = []
    
    # Custom colors & icons
    color_map = {
        "Material": "#2B5B84",
        "Target": "#FF4B4B",
        "Precursor": "#2B845C",
        "Operation": "#F0A30A",
        "Reference": "#5A5A5A",
        "Failure": "#8B0000"
    }

    # Charger les Nœuds
    for n in data.get("nodes", []):
        label = n.get("label", "Node")
        props = n.get("properties", {})
        title = props.get("name", props.get("formula", props.get("type", n.get("entity_id"))))
        
        # Color based on label
        node_color = color_map.get(label, "#333333")
        if label == "Material" and props.get("role") == "Target":
            node_color = color_map["Target"]
            
        nodes.append(Node(
            id=n.get("entity_id"),
            label=str(title)[:20],
            title=json.dumps(props, indent=2), # Tooltip interactif
            size=25,
            color=node_color
        ))
        
    # Charger les Arêtes
    for e in data.get("edges", []):
        edges.append(Edge(
            source=e.get("source_id"),
            label=e.get("type"),
            target=e.get("target_id"),
            color="#A0A0A0"
        ))

    # Configuration du graphe
    config = Config(
        width='100%',
        height=500,
        directed=True,
        physics=True,
        hierarchical=False,
        nodeHighlightBehavior=True,
        highlightColor="#F7A7A6",
        collapsible=False
    )

    st.subheader("🕸️ Graphe Extrait (Cypher Schema)")
    agraph(nodes=nodes, edges=edges, config=config)


def render_agent_graph(active_step="Débat inter-agents", agent_tokens=None):
    """Affiche le graphe d'interaction inter-agents en live."""
    if agent_tokens is None:
        agent_tokens = {}
    
    nodes = []
    edges = []
    
    # Mapping step to active nodes
    active_map = {
        "Lecture PDF": ["pdf"],
        "Indexation RAG": ["pdf", "orchestrator"],
        "Orchestrateur": ["orchestrator"],
        "Extracteur": ["extractor"],
        "Contextuel": ["contextual"],
        "Débat inter-agents": ["thermo", "contextual"],
        "Architecte Graphe": ["graph_architect"],
        "Terminé": ["pdf", "orchestrator", "extractor", "contextual", "thermo", "graph_architect"]
    }
    
    active_nodes = active_map.get(active_step, [])
    
    # Colors
    color_active = "#2ECC71" # Green
    color_normal = "#34495E" # Slate Gray
    
    agent_nodes = [
        {"id": "pdf", "label": "📄 PDF Source", "step_key": "Lecture PDF", "x": -250, "y": 0},
        {"id": "orchestrator", "label": "🎯 Orchestrateur", "step_key": "Orchestrateur", "x": -100, "y": 0},
        {"id": "extractor", "label": "🔬 Extracteur", "step_key": "Extracteur", "x": 50, "y": -100},
        {"id": "contextual", "label": "🧠 Contextuel", "step_key": "Contextuel", "x": 50, "y": 100},
        {"id": "thermo", "label": "⚗️ Thermodynamicien", "step_key": "Débat inter-agents", "x": 200, "y": 100},
        {"id": "graph_architect", "label": "🗄️ Architecte Graphe", "step_key": "Architecte Graphe", "x": 350, "y": 0}
    ]
    
    for a in agent_nodes:
        is_active = a["id"] in active_nodes
        
        # Build label with tokens
        base_label = a["label"]
        tokens = agent_tokens.get(a["step_key"])
        if tokens:
            t_gen = tokens.get("generated", 0)
            t_prm = tokens.get("prompt", 0)
            if t_gen > 0 or t_prm > 0:
                base_label += f"\n🪙 {t_gen} | 📥 {t_prm}"
                
        nodes.append(Node(
            id=a["id"],
            label=base_label,
            size=30 if is_active else 20,
            color=color_active if is_active else color_normal,
            font={'color': 'white' if is_active else '#A0A0A0'},
            x=a["x"],
            y=a["y"],
            fixed=True
        ))
        
    # Edges mapping
    raw_edges = [
        ("pdf", "orchestrator", "Texte brut"),
        ("orchestrator", "extractor", "Plan d'extraction"),
        ("extractor", "contextual", "Extraction brute"),
        ("contextual", "thermo", "Contexte & Matière noire"),
        ("thermo", "contextual", "Débat (Critiques)"),
        ("contextual", "thermo", "Débat (Résolutions)"),
        ("thermo", "graph_architect", "Extraction validée")
    ]
    
    for src, dst, label in raw_edges:
        # Determine if edge is active
        edge_active = False
        if active_step == "Lecture PDF" and src == "pdf" and dst == "orchestrator":
            edge_active = True
        elif active_step == "Indexation RAG" and src == "pdf" and dst == "orchestrator":
            edge_active = True
        elif active_step == "Orchestrateur" and src == "orchestrator" and dst == "extractor":
            edge_active = True
        elif active_step == "Extracteur" and src == "extractor" and dst == "contextual":
            edge_active = True
        elif active_step == "Contextuel" and src == "contextual" and dst == "thermo":
            edge_active = True
        elif active_step == "Débat inter-agents" and ((src == "thermo" and dst == "contextual") or (src == "contextual" and dst == "thermo")):
            edge_active = True
        elif active_step == "Architecte Graphe" and src == "thermo" and dst == "graph_architect":
            edge_active = True
            
        edges.append(Edge(
            source=src,
            target=dst,
            label=label,
            color="#E74C3C" if edge_active else "#7F8C8D", # Red if active, gray otherwise
            width=3 if edge_active else 1
        ))
        
    config = Config(
        width='100%',
        height=350,
        directed=True,
        physics=True,
        hierarchical=False,
        nodeHighlightBehavior=True,
        highlightColor="#2ECC71",
        collapsible=False
    )
    
    agraph(nodes=nodes, edges=edges, config=config)


def render_timeline_cards(status_data, demo_step=None):
    """Affiche les étapes sous forme de frise chronologique (timeline cards) HTML/CSS."""
    # On récupère l'étape courante
    current_step = demo_step if demo_step else status_data.get("step", "Démarrage")
    
    # Définition des étapes du pipeline dans l'ordre chronologique
    steps = [
        {"id": "Lecture PDF", "name": "📖 Lecture PDF & OCR", "desc": "Lecture du PDF et conversion en Markdown (via PyMuPDF, Marker ou Nougat)."},
        {"id": "Indexation RAG", "name": "🧬 Indexation RAG", "desc": "Vectorisation et indexation des chunks dans ChromaDB pour la recherche sémantique."},
        {"id": "Orchestrateur", "name": "🎯 Orchestrateur", "desc": "Génération du plan d'extraction structurée (JSON) basé sur le sommaire."},
        {"id": "Extracteur", "name": "🔬 Extracteur", "desc": "Extraction des paramètres cinétiques (T°, durées) et appel de l'agent Vision."},
        {"id": "Contextuel", "name": "🧠 Agent Contextuel", "desc": "Identification des atmosphères implicites et variantes expérimentales échouées."},
        {"id": "Débat inter-agents", "name": "🗣️ Débat inter-agents", "desc": "Débat critique bilatéral entre le Thermodynamicien (validation) et le Contextuel (objections)."},
        {"id": "Architecte Graphe", "name": "🗄️ Architecte Graphe", "desc": "Modélisation des entités et relations, et génération des requêtes Cypher Neo4j."},
        {"id": "Terminé", "name": "🎉 Terminé", "desc": "Pipeline complété avec succès ! Requêtes Cypher prêtes."}
    ]
    
    html = []
    html.append("""
<style>
.timeline-container {
    border-left: 2px dashed #30363d;
    margin-left: 15px;
    padding-left: 20px;
    position: relative;
}
.timeline-item {
    margin-bottom: 15px;
    position: relative;
}
.timeline-dot {
    position: absolute;
    left: -30px;
    top: 5px;
    width: 16px;
    height: 16px;
    border-radius: 50%;
    background-color: #30363d;
    border: 3px solid #0d1117;
}
.timeline-dot.active {
    background-color: #2ecc71;
    box-shadow: 0 0 8px #2ecc71;
    animation: pulse-active 1.5s infinite;
}
.timeline-dot.completed {
    background-color: #3498db;
}
.timeline-card {
    background-color: #161b22;
    border: 1px solid #30363d;
    border-radius: 6px;
    padding: 8px 14px;
    color: #8b949e;
    transition: all 0.2s ease;
}
.timeline-card.active {
    border-color: #2ecc71;
    background-color: #1f2937;
    box-shadow: 0 0 6px rgba(46, 204, 113, 0.15);
}
.timeline-header {
    font-weight: 700;
    color: #8b949e;
    margin-bottom: 2px;
    font-size: 0.95em;
    display: flex;
    justify-content: space-between;
}
.timeline-header.active {
    color: #2ecc71;
}
.timeline-header.completed {
    color: #3498db;
}
.timeline-body {
    font-size: 0.82em;
    line-height: 1.3;
    color: #8b949e;
}
.timeline-card.active .timeline-body {
    color: #e6edf3;
}
@keyframes pulse-active {
    0% { transform: scale(1); box-shadow: 0 0 0 0 rgba(46, 204, 113, 0.7); }
    70% { transform: scale(1.1); box-shadow: 0 0 0 5px rgba(46, 204, 113, 0); }
    100% { transform: scale(1); box-shadow: 0 0 0 0 rgba(46, 204, 113, 0); }
}
</style>
<div class="timeline-container">
""")

    current_index = -1
    for i, s in enumerate(steps):
        if s["id"] == current_step:
            current_index = i
            break
            
    if current_step == "Terminé":
        current_index = len(steps) - 1

    for i, s in enumerate(steps):
        is_active = (i == current_index)
        is_completed = (i < current_index)
        
        dot_class = "timeline-dot"
        card_class = "timeline-card"
        header_class = "timeline-header"
        badge = ""
        
        if is_active:
            dot_class += " active"
            card_class += " active"
            header_class += " active"
            badge = "<span style='font-size:0.75em; background:#2ecc71; color:#0e1117; padding:1px 4px; border-radius:3px; font-weight:bold;'>EN COURS</span>"
        elif is_completed:
            dot_class += " completed"
            header_class += " completed"
            badge = "<span style='font-size:0.75em; background:#3498db; color:white; padding:1px 4px; border-radius:3px; font-weight:bold;'>REMPLI</span>"
            
        html.append(f"""<div class="timeline-item">
<div class="{dot_class}"></div>
<div class="{card_class}">
<div class="{header_class}">
<span>{s['name']}</span>
{badge}
</div>
<div class="timeline-body">{s['desc']}</div>
</div>
</div>""")
        
    html.append("</div>")
    st.markdown("".join(html), unsafe_allow_html=True)


# =====================================================================
# LOGIQUE PRINCIPALE (ONGLETS ET GRAPHE D'AGENTS)
# =====================================================================
tab1, tab2, tab3 = st.tabs(["🧪 Pipeline & Extraction", "🌐 Réseau d'Agents (Démo)", "🕸️ Graphe de Matériaux"])

with tab1:
    if start_btn:
        if not uploaded_file:
            st.error("Veuillez importer un fichier PDF d'abord.")
        else:
            # 1. Sauvegarder le fichier importé
            with open(UPLOAD_PATH, "wb") as f:
                f.write(uploaded_file.getbuffer())
            st.success(f"Fichier `{uploaded_file.name}` prêt.")

            # 2. Vider les anciens logs
            if EXEC_LOG_PATH.exists(): EXEC_LOG_PATH.unlink()
            if GRAPH_DATA_PATH.exists(): GRAPH_DATA_PATH.unlink()

            # 3. Lancer le pipeline complet
            cmd = ["python", "run.py", "--input", str(UPLOAD_PATH), "--provider", "llama-server", "--use-nougat"]
            if use_marker:
                cmd.append("--use-marker")

            st.info("Agent Orchestrateur : Initialisation du Pipeline Llama 3 en cours...")
            
            # Interface de Live Logging
            status_container = st.empty()
            log_container = st.empty()
            
            # Lancement en tâche de fond
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            
            from synthgraph.utils.status import get_status
            
            with st.spinner("🤖 Essaim d'agents en cours d'exécution (peut prendre plusieurs minutes)..."):
                # Boucle tant que le process n'est pas terminé
                while process.poll() is None:
                    current_log = get_log_content()
                    status_data = get_status()
                    
                    with status_container.container():
                        # 1. Barre de progression & Statut courant
                        current_step = status_data.get("step", "Démarrage")
                        st.markdown(f"### ⚙️ Étape active : **{current_step}**")
                        
                        # Layout en colonnes
                        col_t, col_g = st.columns([2, 3])
                        with col_t:
                            render_timeline_cards(status_data)
                        with col_g:
                            render_agent_graph(current_step, status_data.get("agent_tokens", {}))
                        
                        # 2. Section Nougat Status
                        nougat_status = status_data.get("nougat_status", "idle")
                        if nougat_status == "processing":
                            st.info("🧬 **Traitement OCR avancé par Nougat en cours...** (Cela peut prendre 1 à 2 minutes)")
                        elif nougat_status == "completed":
                            st.success("🧬 **Extraction de la structure par Nougat terminée avec succès !**")
                        elif nougat_status == "error":
                            st.error("🧬 **Échec de l'extraction par Nougat** (Fallback PyMuPDF utilisé)")
                        
                        # 3. Métriques Tokens
                        col1, col2 = st.columns(2)
                        col1.metric("🪙 Tokens Générés (Réponse)", f"{status_data.get('tokens_generated', 0):,}")
                        col2.metric("📥 Tokens Prompt (Entrée)", f"{status_data.get('tokens_prompt', 0):,}")
                        
                        # 4. Affichage des débats d'agents si existants
                        debate_msgs = status_data.get("debate_messages", [])
                        if debate_msgs:
                            st.markdown("#### 🗣️ Débat en direct entre Agents")
                            for msg in debate_msgs:
                                agent = msg.get("agent")
                                rnd = msg.get("round", 1)
                                if agent == "Thermodynamicien":
                                    with st.chat_message("assistant", avatar="⚗️"):
                                        st.markdown(f"**Thermodynamicien (Round {rnd})**")
                                        st.markdown(f"*Recommandation:* {msg.get('recommendation')}")
                                        if msg.get("issues"):
                                            st.markdown(f"⚠️ *Problèmes:* {', '.join(msg.get('issues'))}")
                                        if msg.get("temp_risks"):
                                            st.markdown(f"🔥 *Risques T°:* {', '.join(msg.get('temp_risks'))}")
                                        st.caption(f"Score de confiance: {msg.get('confidence', 0.8):.2f}")
                                elif agent == "Contextuel":
                                    with st.chat_message("user", avatar="🧠"):
                                        st.markdown(f"**Contextuel (Round {rnd})**")
                                        st.markdown(f"*Recommendation:* {msg.get('recommendation')}")
                                        if msg.get("resolution"):
                                            st.markdown(f"💡 *Résolutions:* {', '.join(msg.get('resolution'))}")
                                        st.caption(f"Score de confiance: {msg.get('confidence', 0.8):.2f}")
                                        
                    with log_container.container():
                        st.markdown("### 📜 Console des Agents")
                        st.markdown(current_log)
                        
                    time.sleep(2) # Refresh rate

                # Traitement terminé. Vérification des erreurs
                if process.returncode != 0:
                    st.error(f"Le pipeline s'est arrêté avec le code d'erreur {process.returncode}.")
                else:
                    st.success("🎉 Extraction et validation terminées avec succès !")
                    st.balloons()
                
                # Affichage final des métriques et débats
                status_data = get_status()
                with status_container.container():
                    st.markdown(f"### ⚙️ Étape finale : **{status_data.get('step', 'Terminé')}**")
                    
                    # Layout en colonnes
                    col_t, col_g = st.columns([2, 3])
                    with col_t:
                        render_timeline_cards(status_data)
                    with col_g:
                        render_agent_graph(status_data.get('step', 'Terminé'), status_data.get("agent_tokens", {}))
                    
                    # Section Nougat Status
                    nougat_status = status_data.get("nougat_status", "idle")
                    if nougat_status == "completed":
                        st.success("🧬 **Extraction de la structure par Nougat terminée avec succès !**")
                    elif nougat_status == "error":
                        st.warning("🧬 **Extraction par Nougat en échec** (Fallback PyMuPDF utilisé)")
                    
                    # Métriques Tokens
                    col1, col2 = st.columns(2)
                    col1.metric("🪙 Tokens Générés (Total)", f"{status_data.get('tokens_generated', 0):,}")
                    col2.metric("📥 Tokens Prompt (Total)", f"{status_data.get('tokens_prompt', 0):,}")
                    
                    # Affichage des débats d'agents si existants
                    debate_msgs = status_data.get("debate_messages", [])
                    if debate_msgs:
                        st.markdown("#### 🗣️ Débat inter-agents finalisé")
                        for msg in debate_msgs:
                            agent = msg.get("agent")
                            rnd = msg.get("round", 1)
                            if agent == "Thermodynamicien":
                                with st.chat_message("assistant", avatar="⚗️"):
                                    st.markdown(f"**Thermodynamicien (Round {rnd})**")
                                    st.markdown(f"*Recommandation:* {msg.get('recommendation')}")
                                    if msg.get("issues"):
                                        st.markdown(f"⚠️ *Problèmes:* {', '.join(msg.get('issues'))}")
                                    if msg.get("temp_risks"):
                                        st.markdown(f"🔥 *Risques T°:* {', '.join(msg.get('temp_risks'))}")
                                    st.caption(f"Score de confiance: {msg.get('confidence', 0.8):.2f}")
                            elif agent == "Contextuel":
                                with st.chat_message("user", avatar="🧠"):
                                    st.markdown(f"**Contextuel (Round {rnd})**")
                                    st.markdown(f"*Recommendation:* {msg.get('recommendation')}")
                                    if msg.get("resolution"):
                                        st.markdown(f"💡 *Résolutions:* {', '.join(msg.get('resolution'))}")
                                    st.caption(f"Score de confiance: {msg.get('confidence', 0.8):.2f}")

                # Update finale du log container
                with log_container.container():
                    st.markdown("### 📜 Journal Complet")
                    st.markdown(get_log_content())

    else:
        from synthgraph.utils.status import get_status
        status_data = get_status()
        if status_data.get("tokens_generated", 0) > 0:
            st.markdown("### 📊 Statistiques de la dernière exécution")
            col1, col2, col3 = st.columns(3)
            col1.metric("📄 Fichier", status_data.get("current_paper", "N/A"))
            col2.metric("🪙 Tokens Générés", f"{status_data.get('tokens_generated', 0):,}")
            col3.metric("📥 Tokens Prompt", f"{status_data.get('tokens_prompt', 0):,}")
            
            # Layout en colonnes
            col_t, col_g = st.columns([2, 3])
            with col_t:
                render_timeline_cards(status_data)
            with col_g:
                render_agent_graph(status_data.get('step', 'Terminé'), status_data.get("agent_tokens", {}))
            
            debate_msgs = status_data.get("debate_messages", [])
            if debate_msgs:
                with st.expander("🗣️ Voir le débat de la dernière exécution"):
                    for msg in debate_msgs:
                        agent = msg.get("agent")
                        rnd = msg.get("round", 1)
                        if agent == "Thermodynamicien":
                            with st.chat_message("assistant", avatar="⚗️"):
                                st.markdown(f"**Thermodynamicien (Round {rnd})**")
                                st.markdown(f"*Recommandation:* {msg.get('recommendation')}")
                                if msg.get("issues"):
                                    st.markdown(f"⚠️ *Problèmes:* {', '.join(msg.get('issues'))}")
                                if msg.get("temp_risks"):
                                    st.markdown(f"🔥 *Risques T°:* {', '.join(msg.get('temp_risks'))}")
                                st.caption(f"Score de confiance: {msg.get('confidence', 0.8):.2f}")
                        elif agent == "Contextuel":
                            with st.chat_message("user", avatar="🧠"):
                                st.markdown(f"**Contextuel (Round {rnd})**")
                                st.markdown(f"*Recommendation:* {msg.get('recommendation')}")
                                if msg.get("resolution"):
                                    st.markdown(f"💡 *Résolutions:* {', '.join(msg.get('resolution'))}")
                                st.caption(f"Score de confiance: {msg.get('confidence', 0.8):.2f}")
        else:
            st.info("👈 Importez un PDF à gauche et cliquez sur Démarrer pour lancer l'extraction.")

with tab2:
    st.markdown("### 🌐 Réseau de Discussion des Agents (Simulateur / Démo)")
    st.markdown("Ce graphe modélise les flux de données et la communication entre les différents agents du système SynthGraph.")
    
    simulated_step = st.selectbox(
        "Sélectionnez l'étape du pipeline à tester / simuler :",
        ["Lecture PDF", "Indexation RAG", "Orchestrateur", "Extracteur", "Contextuel", "Débat inter-agents", "Architecte Graphe", "Terminé"],
        index=5
    )
    
    from synthgraph.utils.status import get_status
    # Layout en colonnes
    col_t, col_g = st.columns([2, 3])
    with col_t:
        render_timeline_cards(get_status(), simulated_step)
    with col_g:
        render_agent_graph(simulated_step, get_status().get("agent_tokens", {}))
    
    st.info("💡 Les nœuds s'activent (deviennent verts) et les relations s'allument (deviennent rouges) en fonction de l'étape active. Les flèches modélisent les entrées-sorties des agents.")

with tab3:
    if GRAPH_DATA_PATH.exists():
        render_graph()
    else:
        st.warning("Aucun graphe extrait disponible. Veuillez lancer le pipeline sur un papier d'abord.")

