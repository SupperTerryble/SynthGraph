"""
synthgraph/ui/components/tab_triage.py — Onglet 5: Triage Corpus, Diagnostics & Console Neo4j.

Analyse la qualité globale du corpus d'articles traités, fournit les motifs de veto,
et offre une console de requêtes Cypher en direct sur la base Neo4j.
"""

from __future__ import annotations

import json
from pathlib import Path
import streamlit as st

from synthgraph.ui.components.styles import render_metric_card, render_status_badge

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
CORPUS_TRIAGE_PATH = PROJECT_ROOT / "logs" / "corpus_triage.jsonl"
CORPUS_MD_PATH = PROJECT_ROOT / "logs" / "corpus_triage.md"


def render_tab_triage():
    """Affiche le module de Triage Corpus et Console Neo4j."""
    st.subheader("📁 Triage Corpus & Terminal Neo4j")
    st.markdown("Consultez la performance globale du corpus d'articles et interrogez directement la base Neo4j en Cypher.")

    # 1. Dashboard Corpus Triage
    st.markdown("### 📊 Statistiques de Triage du Corpus")

    triage_data = _load_corpus_triage()

    if triage_data:
        total = len(triage_data)
        accepted = sum(1 for d in triage_data if d.get("status") in ["ACCEPT", "SUCCESS", "PASSED"])
        rejected = sum(1 for d in triage_data if d.get("status") in ["REJECT", "VETO", "FAILED"])
        revised = sum(1 for d in triage_data if d.get("status") in ["REVISE", "NEEDS_DATA"])

        c1, c2, c3, c4 = st.columns(4)
        with c1:
            render_metric_card("Corpus Traité", str(total), "Articles scientifiques", "#58a6ff")
        with c2:
            render_metric_card("Acceptés (Grounding OK)", str(accepted), f"{(accepted/total*100):.1f}% du corpus" if total else "", "#2ea043")
        with c3:
            render_metric_card("Vetos Déterministes", str(rejected), "Rejetés par stœchiométrie", "#f85149")
        with c4:
            render_metric_card("À Réviser", str(revised), "Données manquantes", "#d29922")

        st.markdown("---")

        col_t1, col_t2 = st.columns([1, 1])

        with col_t1:
            st.markdown("#### 🥧 Répartition des Statuts de Validation")
            status_counts = {"ACCEPT": accepted, "REJECT": rejected, "REVISE": revised}
            st.bar_chart(status_counts)

        with col_t2:
            st.markdown("#### 📋 Rapport de Triage Synthétique")
            if CORPUS_MD_PATH.exists():
                try:
                    with open(CORPUS_MD_PATH, "r", encoding="utf-8") as f:
                        st.markdown(f.read()[:2000])
                except Exception as e:
                    st.error(f"Erreur de lecture : {e}")
            else:
                st.info("Fichier logs/corpus_triage.md non disponible.")
    else:
        st.info("Aucune donnée dans logs/corpus_triage.jsonl. Exécutez tools/triage_corpus.py.")

    st.markdown("---")

    # 2. Terminal de requêtes Cypher Neo4j
    st.markdown("### 🗄️ Terminal de Requêtes Cypher (Neo4j 'synthgraph')")
    st.caption("Base Neo4j configurée sur `bolt://localhost:7687` (base 'synthgraph').")

    preset_query = st.selectbox(
        "⚡ Exemples de requêtes pré-enregistrées :",
        [
            "MATCH (n) RETURN count(n) AS node_count",
            "MATCH (p:Material {role: 'Target'}) RETURN p.formula, p.name LIMIT 10",
            "MATCH (m:MissingParameter) RETURN m.name, m.severity, m.unit LIMIT 10",
            "MATCH (pr:Protocol) RETURN pr.qa_status, count(pr) AS count"
        ]
    )

    query_str = st.text_area("Exécuter une requête Cypher personnalisée :", value=preset_query, height=100)

    if st.button("🚀 Exécuter la Requête Cypher", type="primary"):
        st.info("Exécution de la requête sur la base Neo4j...")
        _run_mock_or_real_cypher(query_str)


def _load_corpus_triage() -> list:
    """Lit logs/corpus_triage.jsonl."""
    records = []
    if CORPUS_TRIAGE_PATH.exists():
        try:
            with open(CORPUS_TRIAGE_PATH, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        records.append(json.loads(line))
        except Exception:
            pass
    return records


def _run_mock_or_real_cypher(query_str: str):
    """Exécute une requête Cypher Neo4j si le driver est disponible."""
    try:
        from neo4j import GraphDatabase
        uri = "bolt://localhost:7687"
        auth = ("neo4j", "synthgraph2026")
        driver = GraphDatabase.driver(uri, auth=auth)

        with driver.session(database="synthgraph") as session:
            result = session.run(query_str)
            records = [dict(r) for r in result]

        if records:
            st.success(f"✅ Requête exécutée avec succès ({len(records)} résultats).")
            st.dataframe(records, use_container_width=True)
        else:
            st.info("La requête s'est terminée avec 0 résultat.")
        driver.close()
    except Exception as e:
        st.warning(f"⚠️ Impossible de contacter la base Neo4j locale (bolt://localhost:7687) : {e}")
        st.caption("Astuce : Lancez votre instance Neo4j ou vérifiez vos identifiants dans config/settings.yaml.")
