"""
synthgraph/ui/components/tab_graph.py — Onglet 2: Explorateur de Graphes & Audit Stœchiométrique.

Visualise les graphes de synthèse extraits avec le maximum d'informations par nœud
et permet une inspection détaillée interactive au clic/sélection.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Any, List
import streamlit as st
from streamlit_agraph import agraph, Node, Edge, Config

from synthgraph.ui.components.styles import render_status_badge, render_metric_card

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
STEPS_DIR = PROJECT_ROOT / "logs" / "steps"


def render_tab_graph():
    """Affiche le module de visualisation de Graphe & Recettes."""
    st.subheader("🕸️ Explorateur de Graphes & Inspecteur de Nœuds")
    st.markdown(
        "Chaque nœud du graphe embarque le maximum d'informations extraites du PDF. "
        "Cliquez ou sélectionnez n'importe quel nœud pour inspecter sa fiche détaillée."
    )

    # 1. Sélection du fichier d'extraction / graphe
    step3_files = sorted(list(STEPS_DIR.glob("step3_extraction_*.json")), key=lambda p: p.stat().st_mtime, reverse=True)

    if not step3_files:
        st.info("Aucun fichier d'extraction trouvé dans logs/steps/. Lancez d'abord une extraction.")
        return

    file_options = [f.name for f in step3_files]
    selected_filename = st.selectbox("📂 Choisir une voie de synthèse à visualiser :", file_options, index=0)
    selected_file = STEPS_DIR / selected_filename

    try:
        with open(selected_file, "r", encoding="utf-8") as f:
            raw_data = json.load(f)
    except Exception as e:
        st.error(f"Erreur lors de la lecture du fichier : {e}")
        return

    # 2. Reconstitution Riche du Graphe depuis step3 / step6
    nodes_list, edges_list, node_details_map = _build_rich_graph_data(selected_filename, raw_data)

    # Filtres UI
    col_f1, col_f2, col_f3 = st.columns([1, 1, 1])
    with col_f1:
        show_missing = st.checkbox("Afficher Nœuds Paramètres Manquants", value=True)
    with col_f2:
        physics_enabled = st.checkbox("Activer la Physique de Graphe", value=True)
    with col_f3:
        st.caption(f"📊 {len(nodes_list)} Nœuds | {len(edges_list)} Arêtes")

    # Filtrage des nœuds
    filtered_nodes = [n for n in nodes_list if show_missing or n.color != "#e040fb"]
    filtered_node_ids = set(n.id for n in filtered_nodes)
    filtered_edges = [
        e for e in edges_list 
        if e.source in filtered_node_ids and getattr(e, 'to', None) in filtered_node_ids
    ]

    # Configuration agraph
    config = Config(
        width='100%',
        height=540,
        directed=True,
        physics=physics_enabled,
        hierarchical=False,
        nodeHighlightBehavior=True,
        highlightColor="#00f2fe",
        collapsible=False
    )

    col_graphtree, col_inspector = st.columns([3, 2])

    with col_graphtree:
        st.markdown("#### 🕸️ Schéma de la Voie de Synthèse (Cible, Précurseurs & Étapes)")
        if filtered_nodes:
            # Capturer le nœud cliqué via agraph
            clicked_node_id = agraph(nodes=filtered_nodes, edges=filtered_edges, config=config)
        else:
            clicked_node_id = None
            st.info("Aucun nœud à afficher.")

    with col_inspector:
        st.markdown("#### 🔍 Inspecteur de Contenu du Nœud")

        # Sélecteur de nœud interactif
        node_options = list(node_details_map.keys())
        default_index = 0
        if clicked_node_id and clicked_node_id in node_options:
            default_index = node_options.index(clicked_node_id)

        selected_node_id = st.selectbox(
            "🔍 Cliquer ou Sélectionner un nœud à inspecter :",
            node_options,
            index=default_index,
            help="Sélectionne un nœud pour afficher toutes les données physico-chimiques et citations extraites."
        )

        if selected_node_id in node_details_map:
            _render_node_details_card(node_details_map[selected_node_id])

    st.markdown("---")

    # 3. Bilan Stœchiométrique & Cypher
    col_b1, col_b2 = st.columns([1, 1])
    with col_b1:
        st.markdown("#### ⚖️ Audit du Bilan Élélementaire & Veto")
        _render_elemental_balance_audit(raw_data)
    with col_b2:
        st.markdown("#### 🗄️ Cypher Script Preview")
        _render_cypher_snippet()

    st.markdown("---")

    # 4. Bloc de Notes & Annotations du Chercheur (Uniques par Voie de Synthèse)
    route_key = selected_filename.replace("step3_extraction_", "").replace(".json", "")
    _render_route_notes(route_key)


NOTES_DIR = PROJECT_ROOT / "logs" / "notes"
NOTES_DIR.mkdir(exist_ok=True, parents=True)


def _render_route_notes(route_key: str):
    """Gère un bloc de notes Markdown uniques et éditables pour chaque voie de synthèse et permet de consulter les rapports d'audit globaux."""
    st.markdown("### 📝 Notes, Diagnostics & Rapports d'Audit Markdown")

    # Lister tous les fichiers .md dans logs/notes/
    all_note_files = sorted(list(NOTES_DIR.glob("*.md")), key=lambda p: p.name)
    note_names = [p.name for p in all_note_files]

    current_route_note_name = f"notes_{route_key}.md"
    if current_route_note_name not in note_names:
        note_names.insert(0, current_route_note_name)

    # Sélecteur de fichier de note
    selected_note_name = st.selectbox(
        "📂 Choisir le fichier de note / rapport à consulter ou éditer :",
        note_names,
        index=note_names.index(current_route_note_name) if current_route_note_name in note_names else 0,
        help="Permet de basculer entre les notes de la voie courante et les rapports d'audit globaux du corpus."
    )

    note_file = NOTES_DIR / selected_note_name

    default_template = (
        f"# Notes de Recherche — Voie de Synthèse : {route_key}\n\n"
        f"- **Matériau Cible** :\n"
        f"- **Remarques sur les Précurseurs** :\n"
        f"- **Validation en Laboratoire** :\n"
        f"- **Commentaires / Hypothèses** :\n"
    )

    current_content = default_template
    if note_file.exists():
        try:
            with open(note_file, "r", encoding="utf-8") as f:
                current_content = f.read()
        except Exception as e:
            st.error(f"Erreur de lecture du fichier de notes : {e}")

    session_key = f"note_area_{selected_note_name}"

    edited_notes = st.text_area(
        f"Éditeur Markdown (`logs/notes/{selected_note_name}`) :",
        value=current_content,
        height=220,
        key=session_key,
        help=f"Fichier actif : logs/notes/{selected_note_name}"
    )

    col_save, col_info = st.columns([1, 2])
    with col_save:
        if st.button(f"💾 Sauvegarder ({selected_note_name})", type="primary"):
            try:
                with open(note_file, "w", encoding="utf-8") as f:
                    f.write(edited_notes)
                st.success(f"✅ Fichier `logs/notes/{selected_note_name}` sauvegardé !")
            except Exception as e:
                st.error(f"Erreur lors de la sauvegarde : {e}")

    with col_info:
        st.caption(f"📁 Emplacement disque : `logs/notes/{selected_note_name}`")

    with st.expander("👁️ Aperçu du Rendu Markdown", expanded=True):
        st.markdown(edited_notes)


def _build_rich_graph_data(filename: str, raw_data: dict):
    """Reconstruit une représentation de graphe riche avec toutes les données physico-chimiques."""
    nodes = []
    edges = []
    node_details_map = {}

    color_map = {
        "Target": "#ff4b4b",
        "Precursor": "#00e676",
        "Operation": "#ffd600",
        "MissingParameter": "#e040fb"
    }

    pathways = raw_data.get("pathways", [])
    if not pathways and isinstance(raw_data, list):
        pathways = raw_data

    for p_idx, pw in enumerate(pathways):
        # 1. Target Node
        target = pw.get("target_material", {})
        t_name = target.get("name", target.get("formula", "Target"))
        t_id = f"target_{p_idx}_{t_name}"

        t_props = {
            "node_type": "Target Material",
            "name": t_name,
            "formula": target.get("formula", t_name),
            "role": "Cible Principale",
            "synthesis_route": pw.get("synthesis_route", "N/A"),
            "variant_id": pw.get("variant_id", "v1")
        }
        node_details_map[t_id] = t_props
        nodes.append(Node(
            id=t_id,
            label=f"🎯 Cible : {t_name}",
            title=_format_tooltip_html("Target Material", t_props),
            size=32,
            color=color_map["Target"]
        ))

        # 3. Operation Steps Nodes & Sequential Linking
        steps = pw.get("synthesis_steps", [])
        step_ids = []
        
        for s_idx, step in enumerate(steps):
            op_name = step.get("operation", step.get("type", f"Step_{s_idx}"))
            step_id = f"op_{p_idx}_{s_idx}_{op_name}"
            step_ids.append(step_id)

            temp_c = step.get("target_temperature_c", step.get("temperature_c", "N/A"))
            dur_h = step.get("duration_hours", "N/A")
            atmos = step.get("atmosphere", "N/A")

            op_props = {
                "node_type": "Operation Step",
                "order": step.get("order", s_idx + 1),
                "operation": op_name,
                "temperature_c": f"{temp_c} °C" if temp_c != "N/A" else "N/A",
                "duration_hours": f"{dur_h} h" if dur_h != "N/A" else "N/A",
                "atmosphere": atmos,
                "citation": step.get("citation", "Citation non extraite")
            }
            node_details_map[step_id] = op_props

            temp_str = f" ({temp_c}°C)" if temp_c != "N/A" else ""
            nodes.append(Node(
                id=step_id,
                label=f"⚗️ #{s_idx+1} {op_name}{temp_str}",
                title=_format_tooltip_html("Operation", op_props),
                size=22,
                color=color_map["Operation"]
            ))

        first_step_id = step_ids[0] if step_ids else t_id
        last_step_id = step_ids[-1] if step_ids else None

        # 2. Precursors Nodes (Connectés à la 1ère étape de réaction)
        precursors = pw.get("precursors", [])
        for prec_idx, prec in enumerate(precursors):
            p_name = prec.get("name", prec.get("formula", f"Precursor_{prec_idx}"))
            p_id = f"prec_{p_idx}_{prec_idx}_{p_name}"

            p_props = {
                "node_type": "Precursor",
                "name": p_name,
                "formula": prec.get("formula", p_name),
                "role": prec.get("role", "Reactant"),
                "amount": prec.get("amount", prec.get("amount_raw", "N/A")),
                "moles": prec.get("moles", "N/A"),
                "molar_ratio": prec.get("molar_ratio", "N/A"),
                "citation": prec.get("citation", "Citation non extraite")
            }
            node_details_map[p_id] = p_props

            amt_label = f" ({p_props['amount']})" if p_props['amount'] != "N/A" else ""
            nodes.append(Node(
                id=p_id,
                label=f"🧪 {p_name}{amt_label}",
                title=_format_tooltip_html("Precursor", p_props),
                size=24,
                color=color_map["Precursor"]
            ))

            # Précurseurs -> Première Étape de Réaction (ou Cible si 0 étape)
            edges.append(Edge(
                source=p_id,
                label="USED_IN",
                target=first_step_id,
                color="#00e676"
            ))

        # Chaînage séquentiel des étapes (Étape 1 -> Étape 2 -> ... -> Étape N)
        for idx in range(len(step_ids) - 1):
            edges.append(Edge(
                source=step_ids[idx],
                label="NEXT_STEP",
                target=step_ids[idx+1],
                color="#ffd600"
            ))

        # Dernière étape -> Matériau Cible
        if last_step_id:
            edges.append(Edge(
                source=last_step_id,
                label="PRODUCES",
                target=t_id,
                color="#ff4b4b"
            ))

        # 4. Missing Parameters Nodes
        missing = pw.get("missing_parameters", [])
        for m_idx, m_param in enumerate(missing):
            m_name = m_param.get("parameter_name", m_param.get("name", f"Missing_{m_idx}"))
            m_id = f"missing_{p_idx}_{m_idx}_{m_name}"

            m_props = {
                "node_type": "MissingParameter",
                "parameter_name": m_name,
                "severity": m_param.get("severity", "REQUIRED"),
                "reason": m_param.get("reason", "Inconnu non précisé dans le texte"),
                "unit": m_param.get("unit", "N/A")
            }
            node_details_map[m_id] = m_props

            nodes.append(Node(
                id=m_id,
                label=f"❓ Manquant: {m_name}",
                title=_format_tooltip_html("MissingParameter", m_props),
                size=18,
                color=color_map["MissingParameter"]
            ))

            # Relier le paramètre manquant à la dernière étape ou à la cible
            target_link = last_step_id or t_id
            edges.append(Edge(source=m_id, label="REQUIRES_CLARIFICATION", target=target_link, color="#e040fb"))

    return nodes, edges, node_details_map


def _format_tooltip_html(node_type: str, props: dict) -> str:
    """Formate l'info-bulle (tooltip) au survol d'un nœud."""
    lines = [f"【 {node_type} 】"]
    for k, v in props.items():
        if k != "node_type":
            lines.append(f"{k}: {v}")
    return "\n".join(lines)


def _render_node_details_card(props: dict):
    """Affiche la fiche détaillée complète du nœud sélectionné."""
    n_type = props.get("node_type", "Node")
    name = props.get("name", props.get("parameter_name", props.get("operation", "Nœud")))

    with st.container(border=True):
        st.markdown(f"### 📌 {name}")
        st.markdown(f"**Type :** `{n_type}`")

        # Informations selon le type de nœud
        if n_type == "Precursor":
            col1, col2 = st.columns(2)
            with col1:
                st.markdown(f"🧪 **Formule :** `{props.get('formula')}`")
                st.markdown(f"⚖️ **Rôle :** `{props.get('role')}`")
            with col2:
                st.markdown(f"📦 **Quantité :** `{props.get('amount')}`")
                st.markdown(f"🔬 **Moles :** `{props.get('moles')}`")

            st.markdown("💬 **Citation Exacte PDF (Grounding Quote) :**")
            st.info(f"« {props.get('citation')} »")

        elif n_type == "Operation Step":
            col1, col2 = st.columns(2)
            with col1:
                st.markdown(f"⚗️ **Opération :** `{props.get('operation')}`")
                st.markdown(f"🌡️ **Température :** `{props.get('temperature_c')}`")
            with col2:
                st.markdown(f"⏱️ **Durée :** `{props.get('duration_hours')}`")
                st.markdown(f"🌌 **Atmosphère :** `{props.get('atmosphere')}`")

            st.markdown("💬 **Citation Exacte PDF (Grounding Quote) :**")
            st.info(f"« {props.get('citation')} »")

        elif n_type == "MissingParameter":
            st.error(f"🚨 **Paramètre Manquant Requis :** `{props.get('parameter_name')}`")
            st.markdown(f"⚠️ **Sévérité :** `{props.get('severity')}` | **Unité attendue :** `{props.get('unit')}`")
            st.markdown(f"📝 **Raison :** {props.get('reason')}")

        elif n_type == "Target Material":
            st.success(f"🎯 **Matériau Cible :** `{props.get('formula')}`")
            st.markdown(f"Voie de synthèse : `{props.get('synthesis_route')}` | Variante: `{props.get('variant_id')}`")

        # Payload JSON Brut
        with st.expander("Consulter les métadonnées brutes du nœud (JSON)"):
            st.json(props)


def _render_elemental_balance_audit(raw_data: dict):
    """Rend un rapport d'audit stœchiométrique déterministe."""
    qa_status = raw_data.get("qa_status", raw_data.get("status", "ACCEPT"))
    st.markdown(f"**Statut QA / Veto :** {render_status_badge(qa_status)}", unsafe_allow_html=True)

    balance_report = raw_data.get("element_balance", {})
    if not balance_report:
        st.caption("Aucune anomalie majeure de conservation des éléments détectée.")
        return

    balanced = balance_report.get("is_balanced", True)
    if balanced:
        st.success("✅ Conservation des éléments validée (Bilan CONFORME).")
    else:
        st.error("⚠️ Veto déterministe ! Éléments non conservés.")
        missing_elems = balance_report.get("missing_elements", [])
        if missing_elems:
            st.write(f"Éléments manquants : `{', '.join(missing_elems)}`")


def _render_cypher_snippet():
    """Affiche le script Cypher récent."""
    cypher_files = list(PROJECT_ROOT.glob("logs/cypher_output_*.cypher"))
    if cypher_files:
        latest_cypher = max(cypher_files, key=lambda p: p.stat().st_mtime)
        try:
            with open(latest_cypher, "r", encoding="utf-8") as f:
                c_content = f.read()
            st.code(c_content[:1500] + ("\n..." if len(c_content) > 1500 else ""), language="cypher")
        except Exception as e:
            st.error(f"Erreur Cypher : {e}")
    else:
        st.caption("Aucun script Cypher disponible.")
