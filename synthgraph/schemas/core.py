"""
schemas.py — SynthGraph V4.3 Antigravity
Schémas Pydantic V2 pour tous les agents du pipeline.

MÉCANISMES ANTI-HALLUCINATION :
  1. SynthesisRouteList : sortie du Splitter pour identifier et isoler les voies
  2. GlobalContext (V4.3 NOUVEAU) : variables communes à toute l'étude, injectées
     dans chaque AgentExtracteur pour éviter la 'Vision Tunnel'.
  3. MissingParameter : déclaration explicite des données absentes du texte
  4. VetoDecision : droit de veto structuré pour le Défenseur (ABSENT_FROM_TEXT)
  5. RouteExtractionResult : extraction scopée à une seule route
  6. GraphModel enrichi : support SynthesisProtocol + MISSING_PARAMETER nodes
"""

from typing import List, Optional, Literal, Dict
from enum import Enum
from pydantic import BaseModel, Field, model_validator

from synthgraph.schemas.synthesis import SynthesisStep, MethodType



# =============================================================================
#  Schéma V4.3 — Contexte Global (Anti-Vision-Tunnel)
# =============================================================================

class GlobalContext(BaseModel):
    """Variables communes à toute l'étude, partagées entre toutes les routes.

    Ce bloc est extrait une seule fois par le RouteSplitter (Agent Stratège) à partir
    du texte global de l'article (abstract, introduction, conclusion), puis injecté
    dans le System Prompt de chaque AgentExtracteur.

    Objectif : éviter la 'Vision Tunnel' — chaque extracteur ne voit que son chunk
    local, mais peut rater des informations communes déclarées une seule fois dans
    le papier (ex: plage de dopage, objectif de l'étude, conditions communes).
    """
    goal: str = Field(
        default="",
        description=(
            "Objectif scientifique global de l'étude (ex: 'optimiser la photocatalyse "
            "par dopage au nitrogen'). Extrait de l'abstract ou introduction."
        )
    )
    target_material_global: str = Field(
        default="",
        description="Matériau final visé par l'ensemble de l'étude (ex: 'TiO2 anatase dopé N')"
    )
    doping_elements: List[str] = Field(
        default_factory=list,
        description="Éléments dopants communs à toutes les routes (ex: ['N', 'Fe', 'Cu'])"
    )
    doping_range: str = Field(
        default="",
        description=(
            "Plage de concentration de dopage couverte par l'étude (ex: '0.5-5 mol%'). "
            "Souvent déclarée une seule fois pour toutes les routes."
        )
    )
    common_atmosphere: str = Field(
        default="",
        description="Atmosphère commune à toutes les synthèses si non précisée par route (ex: 'air', 'N2')"
    )
    common_conditions: List[str] = Field(
        default_factory=list,
        description=(
            "Conditions opératoires identiques pour toutes les routes "
            "(ex: ['vitesse d\'agitation = 300 rpm', 'pH = 7', 'solvant = éthanol anhydre'])"
        )
    )
    characterization_techniques: List[str] = Field(
        default_factory=list,
        description="Techniques de caractérisation communes (XRD, SEM, TEM, BET…)"
    )
    extra_global_vars: dict = Field(
        default_factory=dict,
        description=(
            "Autres variables globales non couvertes ci-dessus (clé-valeur libre). "
            "Ex: {'calcination_gas_flow': '100 sccm', 'washing_solvent': 'deionized water'}"
        )
    )


class SynthesisRoute(BaseModel):
    """Une voie de synthèse distincte identifiée dans le papier."""
    route_id: str = Field(description="Identifiant unique de la route (ex: route_1, route_2)")
    method_type: MethodType = Field(description="Type de méthode de synthèse identifié")
    method_confidence: float = Field(
        ge=0.0, le=1.0,
        description="Confiance dans la classification de la méthode (0.0 à 1.0)"
    )
    relevant_text_chunk: str = Field(
        description=(
            "Extrait du texte source décrivant cette voie de synthèse spécifique. "
            "Ce chunk sera utilisé comme contexte RAG isolé pour l'extraction."
        )
    )
    page_numbers: List[int] = Field(
        default_factory=list,
        description="Numéros de page où cette voie est décrite"
    )


class PathwayDefinition(BaseModel):
    """Définition d'une voie de synthèse extraite avec délimitation textuelle."""
    pathway_id: str = Field(description="Identifiant unique (ex: R1, R2)")
    method_name: str = Field(description="Nom exact de la méthode utilisée (non contraint à une liste)")
    start_quote: str = Field(
        description="Une courte citation (5 à 10 mots) marquant le DEBUT EXACT de l'explication de cette synthèse dans le texte brut."
    )
    end_quote: str = Field(
        description="Une courte citation (5 à 10 mots) marquant la FIN EXACTE de l'explication de cette synthèse dans le texte brut."
    )


class SynthesisStrategy(BaseModel):
    """Sortie de l'Agent Stratège V4.3 : intention, contexte global et voies isolées."""
    paper_title: str = Field(default="Unknown Title", description="Titre complet du document")
    paper_authors: str = Field(default="Unknown Authors", description="Auteurs du document")
    paper_year: int = Field(default=2024, description="Année de publication du document")
    paper_doi: str = Field(default="N/A", description="DOI du document si trouvé (ex: 10.1016/...)")
    intent: str = Field(
        description="L'objectif global du papier (ex: 'dopage', 'nouvelle_synthese', 'comparaison')"
    )
    global_context: GlobalContext = Field(
        default_factory=GlobalContext,
        description="Contexte global de l'étude : variables communes à TOUTES les routes."
    )
    pathways: List[PathwayDefinition] = Field(
        description="Liste des protocoles/voies de synthèse détectés avec leurs délimitations."
    )


class SynthesisRouteList(BaseModel):
    """[OBSOLETE V4.2] Ancienne sortie du route splitter."""
    reasoning: str = Field(description="Réflexion pas-à-pas")
    global_context: GlobalContext = Field(default_factory=GlobalContext)
    total_routes_found: int = Field(ge=1)
    routes: List[SynthesisRoute] = Field(description="Liste des voies de synthèse")
    has_comparison_study: bool = Field(default=False)


# =============================================================================
#  Schéma — Paramètres Manquants (Grounding)
# =============================================================================

class MissingParameter(BaseModel):
    """Paramètre attendu mais absent du texte source.
    
    Utilisé pour signaler explicitement qu'une donnée n'a pas été trouvée,
    plutôt que de laisser le LLM halluciner une valeur.
    """
    parameter_name: str = Field(description="Nom du paramètre manquant (ex: atmosphere, rampe_montee)")
    expected_location: str = Field(
        description="Où on s'attendrait à trouver cette info (ex: section expérimentale, tableau 1)"
    )
    search_attempted: bool = Field(
        default=True,
        description="True si une recherche dans le texte a été effectuée"
    )
    reason_missing: Literal[
        "not_mentioned",
        "ambiguous",
        "refers_to_other_route",
        "behind_paywall",
        "in_supplementary_materials"
    ] = Field(description="Raison pour laquelle le paramètre est manquant")


class GroundingStats(BaseModel):
    """Statistiques de traçabilité pour une extraction."""
    total_grounded_fields: int = Field(description="Nombre total de champs GroundedFloat dans le schéma")
    fields_with_values: int = Field(description="Nombre de champs ayant une valeur non-null")
    fields_with_quotes: int = Field(description="Nombre de champs ayant une source_quote")
    grounding_ratio: float = Field(
        ge=0.0, le=1.0,
        description="Ratio fields_with_quotes / fields_with_values (1.0 = parfait)"
    )


# =============================================================================
#  Schéma — Agent Orchestrateur
# =============================================================================

class MacroMethodEnum(str, Enum):
    SOLID_STATE = "solid_state"
    FLUX_METHOD = "flux_method"
    SOL_GEL = "sol_gel"
    HYDROTHERMAL = "hydrothermal"
    CRYSTAL_GROWTH = "crystal_growth"
    THIN_FILM = "thin_film"
    HYBRID = "hybrid"

class ExtractionDirective(BaseModel):
    pathway_id: str = Field(description="Identifiant unique pour cette extraction (ex: R1, R2)")
    target_material: str = Field(description="Nom et formule chimique ciblée (incluant les dopants si applicable)")
    starting_materials: List[str] = Field(default_factory=list, description="Liste des précurseurs (matériaux de départ) identifiés pour cette méthode")
    macro_method: MacroMethodEnum = Field(description="La grande famille de synthèse (ex: flux_method, solid_state, hybrid)")
    method_justification: str = Field(description="Justification scientifique du choix de la méthode (basée sur l'outil ou le texte)")
    mission_summary: str = Field(description="Une phrase résumant l'objectif de cette extraction pour l'agent extracteur")
    key_directives: List[str] = Field(description="Liste de 3 points d'attention stricts que l'Extracteur devra absolument chercher")

class OrchestratorPlan(BaseModel):
    reasoning: str = Field(description="Réflexion pas-à-pas avant de définir le plan d'extraction.")
    extraction_directives: List[ExtractionDirective] = Field(description="Ordres de mission d'extraction (Pathways) générés pour l'Extracteur")
    confidence: float = Field(ge=0.0, le=1.0, description="Confiance de l'agent (0.0 à 1.0)")


# =============================================================================
#  Schéma — Agent Extracteur
# =============================================================================

class Precursor(BaseModel):
    name: str = Field(description="Nom commun ou IUPAC du précurseur")
    formula: str = Field(description="Formule chimique")
    amount: Optional[float] = Field(default=None, description="Valeur de la quantité")
    unit: Optional[Literal["g", "mg", "kg", "mmol", "mol", "mL", "L", "molar_ratio"]] = Field(default=None, description="Unité (utiliser 'molar_ratio' pour la stœchiométrie relative)")
    qualitative_amount: Optional[str] = Field(default=None, description="Si la quantité ou le ratio exact n'est pas un nombre, mais est décrit de manière textuelle (ex: 'en excès', 'pour couvrir la solution solide'), extrais la citation exacte ici.")
    solvent: Optional[str] = Field(default=None, description="Solvant utilisé pour ce précurseur")
    role: Optional[str] = Field(default="precursor", description="Rôle (ex: chelating agent, solvent, precursor)")


class RouteExtractionResult(BaseModel):
    """Extraction scopée à UNE SEULE voie de synthèse.
    
    Remplace l'ancien ExtractionResult monolithique. Chaque route
    identifiée par le Splitter produit un RouteExtractionResult isolé.
    """
    reasoning: str = Field(description="Réflexion pas-à-pas pour extraire les entités chimiques et opérations.")
    route_id: str = Field(description="ID de la route (doit correspondre à SynthesisRoute.route_id)")
    method_type: MethodType = Field(description="Type de méthode (doit correspondre à SynthesisRoute.method_type)")
    target: str = Field(description="Le matériau final visé")
    precursors: List[Precursor] = Field(description="Liste des précurseurs et réactifs utilisés")
    steps: List[SynthesisStep] = Field(description="Séquence chronologique des opérations de synthèse")
    confidence: float = Field(ge=0.0, le=1.0)
    missing_parameters: List[MissingParameter] = Field(
        default_factory=list,
        description="Paramètres attendus mais absents du texte source"
    )
    needs_vision_clarification: bool = Field(
        default=False,
        description="True si l'agent a besoin que l'agent de vision regarde les figures"
    )
    method_overridden: bool = Field(
        default=False,
        description="True si la classification de la méthode a été corrigée par l'Agent Exécuteur."
    )
    stoichiometry_verified: bool = Field(
        default=False,
        description="True si la stœchiométrie a été validée par l'Agent Exécuteur."
    )
    vision_questions: List[str] = Field(
        default_factory=list,
        description="Questions spécifiques à poser à l'agent de vision"
    )
    needs_additional_text: bool = Field(
        default=False,
        description="True s'il manque des informations nécessitant une recherche sémantique"
    )
    text_search_queries: List[str] = Field(
        default_factory=list,
        description="Requêtes de recherche sémantique si needs_additional_text est True"
    )


# Rétrocompatibilité : alias vers le nouveau schéma
ExtractionResult = RouteExtractionResult


# =============================================================================
#  Schéma — Agent Contextuel (Matière Noire)
# =============================================================================

class FailureVariant(BaseModel):
    variant_id: str = Field(description="ID généré pour cette expérience échouée (ex: TiO2_350C)")
    description: str = Field(description="Ce qui a échoué (ex: calcination à 350C insuffisante)")
    condition: str = Field(description="Type de condition sous-optimale (temperature_too_low, missing_reagent)")
    confidence: float = Field(ge=0.0, le=1.0)


class ContextualAnalysis(BaseModel):
    reasoning: str = Field(description="Réflexion pas-à-pas pour déduire le contexte implicite.")
    needs_extractor_clarification: bool = Field(
        default=False,
        description="True si l'agent Extracteur doit revérifier le texte brut"
    )
    extractor_questions: List[str] = Field(
        default_factory=list,
        description="Questions spécifiques à poser à l'agent Extracteur"
    )
    implicit_atmosphere: str = Field(description="Atmosphère non-dite mais déduite du contexte")
    optimization_hints: List[str] = Field(description="Indices que des optimisations ont eu lieu")
    dark_matter: List[FailureVariant] = Field(description="Liste des expériences échouées inférées (la matière noire)")
    tacit_knowledge: List[str] = Field(description="Connaissances tacites déduites (conventions du domaine)")
    contextual_confidence: float = Field(ge=0.0, le=1.0)


class ExtractorClarification(BaseModel):
    reasoning: str = Field(description="Réflexion pas-à-pas pour répondre aux questions du Contextuel.")
    answers: List[str] = Field(description="Réponses claires et directes aux questions posées par l'Agent Contextuel")


# =============================================================================
#  Schéma — Agent Thermodynamicien (Débat)
# =============================================================================

class BibleQuery(BaseModel):
    query: str = Field(description="La question à poser à la base de littérature")

class DebateValidation(BaseModel):
    reasoning: str = Field(description="Réflexion pas-à-pas pour critiquer l'extraction.")
    bible_justification: Optional[str] = Field(default=None, description="La loi thermodynamique ou le principe tiré de la Bible justifiant cette analyse.")
    equation: Optional[str] = Field(default=None, description="Équation chimique globale de la réaction, ex: 2SrCO3 + IrO2 -> Sr2IrO4 + 2CO2")
    temp_risks: List[str] = Field(description="Risques liés aux températures (ex: évaporation, explosion)")
    atmosphere_ok: bool = Field(description="L'atmosphère est-elle compatible avec la chimie ?")
    issues: List[str] = Field(description="Problèmes soulevés nécessitant résolution")
    audit_checklist: Dict[str, bool] = Field(
        description="Checklist d'audit obligatoire: mass_balance_mathematically_verified, temperature_matches_phase_diagram, all_precursors_accounted_for"
    )
    recommendation: str = Field(description="'ACCEPT' ou 'REJECT' ou 'NEEDS_DATA'")
    overall_confidence: float = Field(ge=0.0, le=1.0)

    @model_validator(mode='after')
    def validate_stoichiometry_chempy(self):
        if not self.equation:
            return self
        try:
            import chempy
            import re
            eq_str = self.equation.replace('=', '->').replace("'", "").replace('"', "")
            if '->' not in eq_str:
                return self
            lhs_str, rhs_str = eq_str.split('->', 1)
            def get_atoms(side_str):
                atoms = {}
                parts = side_str.replace('+', ' ').split()
                for p in parts:
                    match = re.match(r'^(\d*)([A-Z][A-Za-z0-9\(\)\[\]]*)$', p.strip())
                    if match:
                        coef_str, form = match.groups()
                        coef = int(coef_str) if coef_str else 1
                        try:
                            comp = chempy.Substance.from_formula(form).composition
                            for atom, count in comp.items():
                                atoms[atom] = atoms.get(atom, 0) + count * coef
                        except Exception:
                            pass
                return atoms
            lhs_atoms = get_atoms(lhs_str)
            rhs_atoms = get_atoms(rhs_str)
            if lhs_atoms and rhs_atoms:
                if lhs_atoms != rhs_atoms:
                    raise ValueError(f"Déséquilibre de masse détecté en Python: Réactifs {lhs_atoms} != Produits {rhs_atoms}. Corrige l'équation.")
        except ImportError:
            pass
        return self


class ContextualReply(BaseModel):
    reasoning: str = Field(description="Réflexion pas-à-pas pour répondre aux critiques du Thermodynamicien.")
    resolution: List[str] = Field(description="Réponse et résolution aux problèmes soulevés")
    additional_tacit: List[str] = Field(description="Nouvelles connaissances tacites invoquées pour justifier")
    audit_checklist: Dict[str, bool] = Field(
        description="Checklist d'audit obligatoire: mass_balance_mathematically_verified, temperature_matches_phase_diagram, all_precursors_accounted_for"
    )
    recommendation: str = Field(description="'ACCEPT' ou 'REJECT' ou 'REQUIRES_CLARIFICATION'")
    contextual_confidence: float = Field(ge=0.0, le=1.0)


# =============================================================================
#  Schéma — Architecte Graphe (Cypher Méta-Modèle enrichi)
# =============================================================================

class NodeEntity(BaseModel):
    """Nœud du graphe Neo4j.
    
    Labels supportés : Material, Operation, Reference, Precursor,
    SynthesisProtocol (NOUVEAU), MissingParameter (NOUVEAU), Failure.
    """
    entity_id: str = Field(description="ID unique local (ex: ref1, ttip1, op1, protocol_flux_1)")
    label: str = Field(
        description=(
            "Label Neo4j. Utiliser 'SynthesisProtocol' pour les nœuds conteneurs de recette, "
            "'MissingParameter' pour les données absentes du texte."
        )
    )
    properties: dict = Field(description="Dictionnaire clé-valeur des propriétés")
    protocol_id: Optional[str] = Field(
        None,
        description="ID du SynthesisProtocol parent (pour lier les étapes à leur recette)"
    )


class EdgeRelation(BaseModel):
    """Relation du graphe Neo4j.
    
    Types supportés : PRODUCES, UNDERGOES, HAS_VARIANT,
    SYNTHESIZED_VIA (NOUVEAU), HAS_STEP (NOUVEAU), REQUIRES_CLARIFICATION (NOUVEAU).
    """
    source_id: str = Field(description="ID du nœud source")
    target_id: str = Field(description="ID du nœud cible")
    type: str = Field(
        description=(
            "Type de relation Neo4j. "
            "Utiliser 'SYNTHESIZED_VIA' pour Material→SynthesisProtocol, "
            "'HAS_STEP' pour SynthesisProtocol→Operation (avec propriété order), "
            "'REQUIRES_CLARIFICATION' pour Operation→MissingParameter."
        )
    )
    properties: dict = Field(default_factory=dict, description="Propriétés optionnelles de la relation")


class GraphModel(BaseModel):
    reasoning: str = Field(description="Réflexion pas-à-pas pour la traduction en nœuds et relations.")
    nodes: List[NodeEntity] = Field(description="Liste des nœuds du graphe")
    edges: List[EdgeRelation] = Field(description="Liste des arêtes reliant les nœuds")


# =============================================================================
#  Schéma — Audit Red Team + Droit de Veto
# =============================================================================

class RedTeamAudit(BaseModel):
    reasoning: str = Field(description="Réflexion pas-à-pas pour trouver les failles dans la synthèse.")
    critical_questions: List[str] = Field(
        description="Questions critiques soulevant les failles ou incohérences de la synthèse."
    )


class VetoDecision(BaseModel):
    """Décision structurée du Défenseur face à une question de la Red Team.
    
    Le Défenseur DOIT utiliser ABSENT_FROM_TEXT plutôt que d'inventer une valeur
    quand l'information n'est pas dans le texte source.
    """
    question_id: int = Field(description="Index de la question Red Team (0-based)")
    decision: Literal["CONFIRMED", "ABSENT_FROM_TEXT", "AMBIGUOUS"] = Field(
        description=(
            "CONFIRMED = l'info est dans le texte et correcte. "
            "ABSENT_FROM_TEXT = l'info n'est PAS dans le texte, NE PAS inventer. "
            "AMBIGUOUS = le texte est ambigu, nécessite clarification humaine."
        )
    )
    justification: str = Field(
        description="Explication de la décision, avec référence au texte si possible"
    )
    source_quote: Optional[str] = Field(
        None,
        description="Citation exacte du texte source (obligatoire si decision=CONFIRMED)"
    )


class ContextualAuditReply(BaseModel):
    """Réponse du Défenseur à la Red Team avec droit de veto structuré.
    
    Remplace l'ancien schéma avec 'answers: List[str]' par des VetoDecisions
    structurées qui forcent le Défenseur à déclarer explicitement quand
    une information est absente du texte.
    """
    reasoning: str = Field(description="Réflexion pas-à-pas pour répondre à la Red Team.")
    veto_decisions: List[VetoDecision] = Field(
        description="Décisions structurées pour chaque question de la Red Team"
    )
    corrected_synthesis: dict = Field(
        description="La synthèse finale corrigée après l'audit"
    )
    parameters_declared_missing: List[MissingParameter] = Field(
        default_factory=list,
        description="Paramètres explicitement déclarés absents du texte suite à l'audit"
    )
