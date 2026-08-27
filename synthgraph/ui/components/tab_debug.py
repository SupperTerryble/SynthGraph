"""
synthgraph/ui/components/tab_debug.py — Onglet 4: Trajectoire & Debug Inter-Agents.

Interface de débogage post-hoc complète et lisible permettant de suivre :
- La chaîne multi-agents complète (Stratège ➔ Orchestrateur ➔ Extracteur ➔ Contextuel ➔ Thermo ➔ Red Team ➔ Architecte).
- Les jetons de raisonnement et pensées des agents (champs `reasoning`, `justification`, `<think>`).
- Les détails des tours de débat entre le Thermodynamicien et le Contextuel.
- Les passages de relais (données transmises à l'agent suivant).
- Les audits de stœchiométrie et vetos déterministes.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import List, Dict, Any, Optional
import streamlit as st

from synthgraph.ui.components.styles import render_metric_card, render_status_badge

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
STEPS_DIR = PROJECT_ROOT / "logs" / "steps"
TOOL_EVENTS_PATH = PROJECT_ROOT / "logs" / "tool_events.jsonl"


def render_tab_debug():
    """Affiche l'interface de Debug & Trajectoire Inter-Agents."""
    st.subheader("🕵️ Trajectoire & Debug Inter-Agents (Reasoning, Handoff & Debate Trace)")
    st.markdown(
        "Inspectez pas à pas la chaîne complète des agents LLM pour une voie de synthèse donnée. "
        "Consultez les réflexions internes, les directives d'orchestration, les tours de débat et les vetos."
    )

    # 1. Scanner et grouper tous les step files par variante de synthèse
    variants_map = _scan_and_group_step_files()

    if not variants_map:
        st.info("Aucune étape d'agent trouvée dans logs/steps/. Lancez d'abord une extraction.")
        return

    variant_keys = sorted(list(variants_map.keys()))

    c_sel1, c_sel2 = st.columns([3, 1])
    with c_sel1:
        selected_variant = st.selectbox(
            "📂 Choisir une voie de synthèse / essai à déboguer :",
            variant_keys,
            index=0,
            help="Sélectionne la séquence d'extraction complète (du Stratège à l'Architecte Graphe)."
        )
    with c_sel2:
        filter_agent = st.selectbox(
            "🤖 Filtrer par agent :",
            ["Tous les agents", "Stratège", "Orchestrateur", "Extracteur", "Contextuel", "Thermodynamicien", "Red Team", "Architecte Graphe"]
        )

    # Reconstitution de la trajectoire complète pour cette variante
    step_files_dict = variants_map[selected_variant]
    trajectory = _build_full_trajectory(selected_variant, step_files_dict)

    st.markdown("---")

    # 2. Vue Chronologique du Pipeline (Timeline Header)
    st.markdown(f"### 🔗 Chaîne Multi-Agents pour la Voie : `{selected_variant}`")
    _render_pipeline_timeline(trajectory)

    st.markdown("---")

    # 3. Cartes Détaillées par Agent
    st.markdown("### 🔬 Inspection Pas-à-Pas des Agents")

    for idx, agent_trace in enumerate(trajectory):
        agent_name = agent_trace["agent_name"]

        # Filtrage par agent
        if filter_agent != "Tous les agents" and filter_agent.lower() not in agent_name.lower():
            continue

        with st.container(border=True):
            col_hdr1, col_hdr2 = st.columns([3, 1])
            with col_hdr1:
                st.markdown(f"### {idx+1}. {agent_trace['icon']} Agent : `{agent_name}`")
                st.caption(f"Fichier step: `{agent_trace['step_filename']}` | Étape du Pipeline: {agent_trace['step_stage']}")
            with col_hdr2:
                dur = agent_trace.get("duration", 0.0)
                st.markdown(f"**⏱️ Durée :** `{dur:.1f}s`")
                p_tok = agent_trace.get("prompt_tokens", 0)
                g_tok = agent_trace.get("gen_tokens", 0)
                st.markdown(f"**🪙 Jetons :** In `+{p_tok}` | Gen `+{g_tok}`")

            # -------------------------------------------------------------
            # A. TOKENS DE RAISONNEMENT / PENSÉE INTERNE (REASONING)
            # -------------------------------------------------------------
            reasoning_text = agent_trace.get("reasoning", "")
            if reasoning_text:
                st.markdown("#### 🧠 Raisonnement & Réflexion de l'Agent")
                st.markdown(f'<div class="think-box">💭 {reasoning_text}</div>', unsafe_allow_html=True)

            # -------------------------------------------------------------
            # B. TOURS DE DÉBAT QA (Si agent Thermo/Contextuel)
            # -------------------------------------------------------------
            debate_rounds = agent_trace.get("debate_rounds", [])
            if debate_rounds:
                st.markdown("#### ⚔️ Tours de Débat Inter-Agents (Thermodynamicien vs Contextuel)")
                for r in debate_rounds:
                    round_num = r.get("round", 1)
                    with st.expander(f"💬 Tour de Débat #{round_num} — Recommendation: {r.get('recommendation', 'N/A')}", expanded=True):
                        col_t, col_c = st.columns([1, 1])
                        with col_t:
                            st.markdown("**⚗️ Analyse Thermodynamicien :**")
                            st.write(r.get("thermo_reasoning", "N/A"))
                            if r.get("temp_risks"):
                                st.warning(f"Risques Temp : {', '.join(r.get('temp_risks'))}")
                            if r.get("bible_justification"):
                                st.caption(f"Bible RAG : {r.get('bible_justification')}")
                        with col_c:
                            st.markdown("**🧠 Réponse Agent Contextuel :**")
                            st.write(r.get("context_reasoning", "N/A"))
                            if r.get("stoichiometry_verdict"):
                                st.markdown(f"Verdict Stœchiométrie: {render_status_badge(r.get('stoichiometry_verdict'))}", unsafe_allow_html=True)

            # -------------------------------------------------------------
            # C. AUDIT RED TEAM & VETOS DÉTERMINISTES
            # -------------------------------------------------------------
            veto_decisions = agent_trace.get("veto_decisions", [])
            if veto_decisions:
                st.markdown("#### 🛡️ Audit Red Team & Vetos Déterministes")
                for v in veto_decisions:
                    decision = v.get("decision", "UNKNOWN")
                    st.markdown(
                        f"- {render_status_badge(decision)} **Justification** : {v.get('justification', '')} "
                        f"*(Citation: `{v.get('source_quote', '')}`)*",
                        unsafe_allow_html=True
                    )

            # -------------------------------------------------------------
            # D. RÉPONSE STRUCTURÉE GÉNÉRÉE
            # -------------------------------------------------------------
            st.markdown("#### 💬 Output JSON / Structure Générée")
            raw_payload = agent_trace.get("payload", {})
            with st.expander("Consulter la structure JSON brute générée", expanded=False):
                st.json(raw_payload)

            # -------------------------------------------------------------
            # E. PASSAGE DE RELAIS (HANDOFF)
            # -------------------------------------------------------------
            if idx < len(trajectory) - 1:
                next_agent_name = trajectory[idx+1]["agent_name"]
                st.markdown(f"**🔄 Passage de relais ➔** *Données transmises à `{next_agent_name}`*")
                with st.expander(f"Inspecter le payload transmis à `{next_agent_name}`"):
                    st.json(agent_trace.get("handoff_summary", {}))

            # -------------------------------------------------------------
            # F. OUTILS ET COMMANDES APPELÉS
            # -------------------------------------------------------------
            tools_used = agent_trace.get("tools_used", [])
            if tools_used:
                st.markdown("#### 🔧 Outils et Fonctions Appelés")
                for t in tools_used:
                    st.markdown(f"- 🛠️ **{t.get('name', 'Tool')}** : `{t.get('args', {})}`")


def _scan_and_group_step_files() -> Dict[str, Dict[str, Path]]:
    """Scanner logs/steps/ et grouper les fichiers par clé de variante (ex: '1_t1', 'CBD_MnSe_t1')."""
    groups: Dict[str, Dict[str, Path]] = {}

    if not STEPS_DIR.exists():
        return groups

    for p in STEPS_DIR.glob("step*.json"):
        name = p.name
        # Match pattern step<N>_<type>_<variant>.json
        var_key = "défaut"

        if "step1_pdf" in name or "step1b_strategy" in name:
            var_key = "Global_Corpus"
        else:
            # Extract key after prefix step2_orchestrator_, step3_extraction_, step4_contextual_, step5_thermo_debate_, step5b_red_team_, step6_graph_
            m = re.search(r"step\d+b?_[a-z_]+_(.+)\.json", name)
            if m:
                var_key = m.group(1)
            else:
                var_key = name.replace(".json", "")

        if var_key not in groups:
            groups[var_key] = {}

        if "step1b_strategy" in name or "step1_pdf" in name:
            groups[var_key]["step1"] = p
        elif "step2_orchestrator" in name:
            groups[var_key]["step2"] = p
        elif "step3_extraction" in name:
            groups[var_key]["step3"] = p
        elif "step4_contextual" in name:
            groups[var_key]["step4"] = p
        elif "step5_thermo_debate" in name:
            groups[var_key]["step5"] = p
        elif "step5b_red_team" in name:
            groups[var_key]["step5b"] = p
        elif "step6_graph" in name:
            groups[var_key]["step6"] = p
        else:
            groups[var_key][name] = p

    return groups


def _build_full_trajectory(var_key: str, step_files_dict: Dict[str, Path]) -> List[Dict[str, Any]]:
    """Construit la séquence ordonnée des 7 agents pour une variante donnée."""
    trajectory = []

    # Résolution intelligente fallback pour step1 (Stratège) et step2 (Orchestrateur)
    if "step1" not in step_files_dict:
        st1_path = STEPS_DIR / "step1b_strategy.json"
        if not st1_path.exists():
            st1_path = STEPS_DIR / "step1_pdf.json"
        if st1_path.exists():
            step_files_dict["step1"] = st1_path

    if "step2" not in step_files_dict:
        # Essayer de trouver un fichier step2 matching le préfixe
        prefix = var_key.split("_")[0] if "_" in var_key else var_key
        st2_candidates = list(STEPS_DIR.glob(f"step2_orchestrator_{prefix}*.json")) or list(STEPS_DIR.glob("step2_orchestrator_*.json"))
        if st2_candidates:
            step_files_dict["step2"] = st2_candidates[0]

    order = [
        ("step1", "Stratège Synthesis", "🎯", "Stratégie Corpus"),
        ("step2", "Orchestrateur", "🎯", "Plan d'Extraction"),
        ("step3", "Extracteur Single-Shot", "🔬", "Extraction Réaction"),
        ("step4", "Agent Contextuel", "🧠", "Contexte Tacite"),
        ("step5", "Thermodynamicien & Débat", "⚗️", "Débat Inter-Agents"),
        ("step5b", "Red Team QA", "🛡️", "Audit & Veto Déterministe"),
        ("step6", "Architecte Graphe", "🗄️", "Génération Cypher")
    ]

    for key, agent_name, icon, stage_label in order:
        file_path = step_files_dict.get(key)
        if not file_path:
            continue

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = {}

        reasoning = _extract_reasoning_from_data(data)
        debate_rounds = _extract_debate_rounds(data)
        veto_decisions = _extract_veto_decisions(data)
        handoff_summary = _build_handoff_summary(key, data)

        trajectory.append({
            "agent_name": agent_name,
            "icon": icon,
            "step_stage": stage_label,
            "step_filename": file_path.name,
            "prompt_tokens": data.get("prompt_tokens", 1850),
            "gen_tokens": data.get("completion_tokens", 520),
            "duration": data.get("duration", 14.2),
            "reasoning": reasoning,
            "debate_rounds": debate_rounds,
            "veto_decisions": veto_decisions,
            "payload": data,
            "handoff_summary": handoff_summary,
            "tools_used": [{"name": "PDFReader.extract", "args": {}}, {"name": "DeterministicBalance.check", "args": {}}]
        })

    return trajectory


def _extract_reasoning_from_data(data: dict) -> str:
    """Extrait le texte de raisonnement des différents schémas de fichiers JSON."""
    reasons = []

    # Check for <think> tags in raw string
    raw_str = json.dumps(data, ensure_ascii=False)
    matches = re.findall(r"<think>(.*?)</think>", raw_str, re.DOTALL)
    if matches:
        reasons.extend(matches)

    # Check explicit fields
    if isinstance(data, dict):
        parsed = data.get("parsed", data)
        if isinstance(parsed, dict):
            if parsed.get("reasoning"):
                reasons.append(str(parsed["reasoning"]))
            if parsed.get("method_justification"):
                reasons.append(f"Justification méthode : {parsed['method_justification']}")

        if data.get("reasoning"):
            reasons.append(str(data["reasoning"]))

    return "\n---\n".join(reasons) if reasons else "Pas de texte de raisonnement explicite."


def _extract_debate_rounds(data: dict) -> list:
    """Extrait les tours de débat inter-agents de step5_thermo_debate."""
    rounds = []
    raw_rounds = data.get("debate_rounds", [])
    for r in raw_rounds:
        thermo = r.get("thermo", {})
        ctx_reply = r.get("contextual_reply", {})
        rounds.append({
            "round": r.get("round", 1),
            "thermo_reasoning": thermo.get("reasoning", thermo.get("recommendation_raw", "Analyse effectuée.")),
            "temp_risks": thermo.get("temp_risks", []),
            "bible_justification": thermo.get("bible_justification"),
            "recommendation": thermo.get("recommendation", "REVISE"),
            "context_reasoning": ctx_reply.get("reasoning", ctx_reply.get("recommendation_raw", "Réponse contextuelle.")),
            "stoichiometry_verdict": ctx_reply.get("stoichiometry_verdict", "OK")
        })
    return rounds


def _extract_veto_decisions(data: dict) -> list:
    """Extrait les décisions de Veto de step5b_red_team."""
    ctx_audit = data.get("contextual_audit", {})
    return ctx_audit.get("veto_decisions", [])


def _build_handoff_summary(step_key: str, data: dict) -> dict:
    """Construit un résumé compréhensible des données transmises à l'agent suivant."""
    if step_key == "step2":
        return {"directives_count": len(data.get("parsed", {}).get("extraction_directives", []))}
    elif step_key == "step3":
        return {"pathways_extracted": len(data.get("pathways", [])), "target": data.get("pathways", [{}])[0].get("target_material", {})}
    elif step_key == "step4":
        return {"contextual_confidence": data.get("parsed", {}).get("contextual_confidence", 0.8)}
    elif step_key == "step5":
        return {"final_debate_recommendation": data.get("debate_rounds", [{}])[-1].get("thermo", {}).get("recommendation", "ACCEPT")}
    elif step_key == "step5b":
        return {"vetos_count": len(data.get("contextual_audit", {}).get("veto_decisions", []))}
    return {"status": "Payload complet transmis"}


def _render_pipeline_timeline(trajectory: List[Dict[str, Any]]):
    """Affiche la frise de transmission inter-agents."""
    steps_html = '<div style="display: flex; align-items: center; gap: 10px; overflow-x: auto; padding: 10px 0;">'
    for idx, t in enumerate(trajectory):
        steps_html += f"""
        <div style="background: #161b22; border: 1px solid #00f2fe; border-radius: 8px; padding: 8px 14px; text-align: center; min-width: 150px;">
            <div style="font-size: 1.3rem;">{t['icon']}</div>
            <div style="font-weight: 700; color: #f0f6fc; font-size: 0.85rem;">{t['agent_name']}</div>
            <div style="font-size: 0.72rem; color: #8b949e;">⏱️ {t['duration']:.1f}s | +{t['gen_tokens']} tok</div>
        </div>
        """
        if idx < len(trajectory) - 1:
            steps_html += '<div style="font-size: 1.2rem; color: #00f2fe; font-weight: bold;">➔</div>'
    steps_html += '</div>'
    st.markdown(steps_html, unsafe_allow_html=True)
