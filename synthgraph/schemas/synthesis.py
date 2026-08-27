"""
synthesis_schemas.py — SynthGraph
Schémas Pydantic V2 pour les 10 méthodes de synthèse + fallback générique.

MÉCANISMES ANTI-HALLUCINATION :
  1. GroundedFloat : traçabilité obligatoire (value + source_quote) pour les paramètres critiques
  2. BaseSynthesisStep : classe de base avec discriminator `methode` pour héritage propre
  3. Discriminated Union : le LLM ne voit QUE les champs de la méthode détectée par le Splitter
  4. get_extraction_model_for_method() : factory de schémas dynamiques par route
"""

from __future__ import annotations

from typing import List, Optional, Union, Literal, Annotated
from pydantic import BaseModel, Field, model_validator, create_model, ValidationInfo
from enum import Enum


# =============================================================================
# TRAÇABILITÉ OBLIGATOIRE (Grounding)
# =============================================================================

class GroundedFloat(BaseModel):
    """Valeur numérique avec citation obligatoire du texte source.
    
    Le LLM DOIT fournir source_quote quand value n'est pas None.
    Si aucun extrait du texte ne justifie la valeur, value DOIT être None.
    """
    value: Optional[float] = None
    unit: str = ""
    source_quote: Optional[str] = Field(
        None,
        description=(
            "Extrait EXACT du texte source justifiant cette valeur. "
            "Si aucune citation n'est trouvée dans le texte, value DOIT être None."
        )
    )
    confidence: float = Field(0.0, ge=0.0, le=1.0, description="Confiance dans cette valeur (0.0 = aucune, 1.0 = certaine)")

    @model_validator(mode='after')
    def quote_required_if_value(self):
        """Empêche structurellement le LLM de fournir une valeur sans citation."""
        if self.value is not None and not self.source_quote:
            raise ValueError(
                f"source_quote est OBLIGATOIRE quand value n'est pas None (value={self.value}). "
                f"Copie l'extrait exact du texte ou mets value à null."
            )
        return self


class GroundedStr(BaseModel):
    """Valeur textuelle avec citation obligatoire du texte source."""
    value: Optional[str] = None
    source_quote: Optional[str] = Field(
        None,
        description="Extrait EXACT du texte source justifiant cette valeur."
    )
    confidence: float = Field(0.0, ge=0.0, le=1.0)

    @model_validator(mode='after')
    def quote_required_if_value(self):
        if self.value is not None and not self.source_quote:
            raise ValueError(
                f"source_quote est OBLIGATOIRE quand value n'est pas None (value='{self.value}'). "
                f"Copie l'extrait exact du texte ou mets value à null."
            )
        return self


# =============================================================================
# TYPES DE MÉTHODES ET CLASSE DE BASE
# =============================================================================

MethodType = Literal[
    "pvd_pulverisation_cathodique",
    "cvd_chemical_vapor_deposition",
    "sol_gel",
    "hydrothermale_solvothermale",
    "co_precipitation",
    "pechini_sol_gel_polymerique",
    "solution_combustion_synthesis",
    "voie_solide_ceramique",
    "spray_pyrolysis",
    "flux_growth",
    "operation_generique"
]


class BaseSynthesisStep(BaseModel):
    """Classe de base pour toutes les étapes de synthèse.
    
    Chaque sous-classe DOIT définir un champ `methode: Literal[...]`
    qui sert de discriminator pour les unions discriminées Pydantic V2.
    """
    step_number: Optional[int] = Field(None, description="Ordre chronologique de l'étape dans le protocole")


# =============================================================================
# 1. PVD (Pulvérisation Cathodique)
# =============================================================================

class PVDVide(BaseModel):
    pression_base_mbar: Optional[GroundedFloat] = None
    pression_travail_mbar: Optional[GroundedFloat] = None
    temperature_enceinte_celsius: Optional[GroundedFloat] = None

class PVDGaz(BaseModel):
    plasmagene_nature: Optional[str] = ""
    plasmagene_debit_sccm: Optional[GroundedFloat] = None
    reactif_nature: Optional[str] = ""
    reactif_debit_sccm: Optional[GroundedFloat] = None
    reactif_pression_partielle: Optional[GroundedFloat] = None

class PVDEnceinteAtmosphere(BaseModel):
    vide: Optional[PVDVide] = None
    gaz: Optional[PVDGaz] = None

class PVDConfigurationGeometrique(BaseModel):
    type: Optional[str] = "confocal_ou_planaire"
    distance_cible_substrat_mm: Optional[float] = None

class PVDParametresAlimentation(BaseModel):
    puissance_w: Optional[float] = None
    courant_a: Optional[float] = None
    tension_v: Optional[float] = None
    frequence_hz: Optional[float] = None
    temps_inversion_us: Optional[float] = None
    largeur_impulsion_us: Optional[float] = None
    courant_crete_a: Optional[float] = None

class PVDSource(BaseModel):
    port_id: Optional[int] = None
    cible_materiau: Optional[str] = ""
    cible_etat_usure_pourcentage: Optional[float] = None
    alimentation_type: Optional[str] = ""
    parametres_alimentation: Optional[PVDParametresAlimentation] = None

class PVDConditionnementInSitu(BaseModel):
    temps_decapage_ionique_s: Optional[GroundedFloat] = None
    tension_decapage_v: Optional[float] = None

class PVDCinematique(BaseModel):
    vitesse_rotation_rpm: Optional[float] = None
    angle_inclinaison_deg: Optional[float] = None

class PVDConditionsDepot(BaseModel):
    temperature_consigne_celsius: Optional[GroundedFloat] = None
    tension_polarisation_bias_v: Optional[float] = None
    type_bias: Optional[str] = ""

class PVDSubstrat(BaseModel):
    materiau: Optional[str] = ""
    orientation_cristallographique: Optional[str] = ""
    conditionnement_in_situ: Optional[PVDConditionnementInSitu] = None
    cinematique: Optional[PVDCinematique] = None
    conditions_depot: Optional[PVDConditionsDepot] = None

class PVDChronologie(BaseModel):
    temps_pre_pulverisation_s: Optional[GroundedFloat] = None
    temps_depot_effectif_s: Optional[GroundedFloat] = None

class PVDSynthesis(BaseSynthesisStep):
    methode: Literal["pvd_pulverisation_cathodique"] = "pvd_pulverisation_cathodique"
    enceinte_et_atmosphere: Optional[PVDEnceinteAtmosphere] = None
    configuration_geometrique: Optional[PVDConfigurationGeometrique] = None
    sources: List[PVDSource] = Field(default_factory=list)
    substrat: Optional[PVDSubstrat] = None
    chronologie: Optional[PVDChronologie] = None


# =============================================================================
# 2. CVD (Chemical Vapor Deposition)
# =============================================================================

class CVDPrecurseur(BaseModel):
    nature_chimique: Optional[str] = ""
    temperature_vaporisateur_celsius: Optional[GroundedFloat] = None
    debit_gaz_porteur_sccm: Optional[GroundedFloat] = None
    pression_bulleur_mbar: Optional[GroundedFloat] = None

class CVDGazReactifDirect(BaseModel):
    nature_chimique: Optional[str] = ""
    debit_sccm: Optional[GroundedFloat] = None

class CVDReactifs(BaseModel):
    precurseurs: List[CVDPrecurseur] = Field(default_factory=list)
    gaz_reactifs_directs: List[CVDGazReactifDirect] = Field(default_factory=list)

class CVDActivationPlasma(BaseModel):
    utilise: bool = False
    type_source: Optional[str] = ""
    puissance_w: Optional[float] = None
    frequence_hz: Optional[float] = None

class CVDChambreReaction(BaseModel):
    pression_totale_travail_mbar: Optional[GroundedFloat] = None
    temperature_parois_celsius: Optional[GroundedFloat] = None
    activation_plasma: Optional[CVDActivationPlasma] = None

class CVDSubstrat(BaseModel):
    nature: Optional[str] = ""
    temperature_suscepteur_celsius: Optional[GroundedFloat] = None
    vitesse_rotation_rpm: Optional[float] = None

class CVDSequenceALD(BaseModel):
    temps_injection_a_s: Optional[GroundedFloat] = None
    temps_purge_1_s: Optional[GroundedFloat] = None
    temps_injection_b_s: Optional[GroundedFloat] = None
    temps_purge_2_s: Optional[GroundedFloat] = None

class CVDCycles(BaseModel):
    cyclique: bool = False
    nombre_cycles_total: Optional[int] = None
    sequence: Optional[CVDSequenceALD] = None

class CVDSynthesis(BaseSynthesisStep):
    methode: Literal["cvd_chemical_vapor_deposition"] = "cvd_chemical_vapor_deposition"
    reactifs: Optional[CVDReactifs] = None
    chambre_reaction: Optional[CVDChambreReaction] = None
    substrat: Optional[CVDSubstrat] = None
    cycles_ald_cvd: Optional[CVDCycles] = None


# =============================================================================
# 3. Sol-Gel
# =============================================================================

class SGPrecurseur(BaseModel):
    nature_chimique: Optional[str] = ""
    concentration_mol_l: Optional[float] = None

class SGSolvant(BaseModel):
    nature_chimique: Optional[str] = ""
    volume_ml: Optional[float] = None

class SGCatalyseur(BaseModel):
    nature: Optional[str] = ""
    ph_cible: Optional[float] = None

class SGAdditif(BaseModel):
    nature_chimique: Optional[str] = ""
    role: Optional[str] = ""

class SGComposition(BaseModel):
    precurseurs: List[SGPrecurseur] = Field(default_factory=list)
    solvant: Optional[SGSolvant] = None
    catalyseur: Optional[SGCatalyseur] = None
    additifs: List[SGAdditif] = Field(default_factory=list)

class SGConditionsMelange(BaseModel):
    temperature_bain_celsius: Optional[GroundedFloat] = None
    vitesse_agitation_rpm: Optional[float] = None
    temps_ajout_min: Optional[GroundedFloat] = None
    ratio_hydrolyse: Optional[float] = None

class SGVieillissement(BaseModel):
    duree_h: Optional[GroundedFloat] = None
    temperature_celsius: Optional[GroundedFloat] = None

class SGParametresDepot(BaseModel):
    vitesse_retrait_mm_s: Optional[float] = None
    vitesse_rotation_rpm: Optional[float] = None
    temps_immersion_s: Optional[GroundedFloat] = None

class SGDepot(BaseModel):
    methode: Optional[str] = "dip_coating_ou_spin_coating"
    parametres_specifiques: Optional[SGParametresDepot] = None

class SGMaturationMiseEnForme(BaseModel):
    vieillissement: Optional[SGVieillissement] = None
    depot: Optional[SGDepot] = None

class SGTraitementThermiqueSechage(BaseModel):
    temperature_celsius: Optional[GroundedFloat] = None
    duree_h: Optional[GroundedFloat] = None
    atmosphere: Optional[str] = ""

class SGTraitementThermiqueCalcination(BaseModel):
    temperature_palier_celsius: Optional[GroundedFloat] = None
    rampe_montee_c_min: Optional[GroundedFloat] = None
    duree_palier_h: Optional[GroundedFloat] = None
    atmosphere: Optional[str] = ""

class SGTraitementThermique(BaseModel):
    sechage: Optional[SGTraitementThermiqueSechage] = None
    calcination: Optional[SGTraitementThermiqueCalcination] = None

class SolGelSynthesis(BaseSynthesisStep):
    methode: Literal["sol_gel"] = "sol_gel"
    composition: Optional[SGComposition] = None
    conditions_melange: Optional[SGConditionsMelange] = None
    maturation_mise_en_forme: Optional[SGMaturationMiseEnForme] = None
    traitements_thermiques: Optional[SGTraitementThermique] = None


# =============================================================================
# 4. Hydrothermale / Solvothermale
# =============================================================================

class HydroPrecurseur(BaseModel):
    nature_chimique: Optional[str] = ""
    masse_g: Optional[float] = None
    concentration_mol_l: Optional[float] = None

class HydroSolvant(BaseModel):
    nature_chimique: Optional[str] = ""
    volume_total_ml: Optional[float] = None

class HydroAdditif(BaseModel):
    nature_chimique: Optional[str] = ""
    concentration_mol_l: Optional[float] = None
    ph_initial: Optional[float] = None

class HydroReactifs(BaseModel):
    precurseurs: List[HydroPrecurseur] = Field(default_factory=list)
    solvant: Optional[HydroSolvant] = None
    additifs: List[HydroAdditif] = Field(default_factory=list)

class HydroReacteur(BaseModel):
    nature_chemise: Optional[str] = ""
    volume_total_chemise_ml: Optional[float] = None
    taux_remplissage_pourcentage: Optional[float] = None

class HydroTraitementThermique(BaseModel):
    rampe_chauffage_c_min: Optional[GroundedFloat] = None
    temperature_consigne_celsius: Optional[GroundedFloat] = None
    duree_maintien_h: Optional[GroundedFloat] = None
    mode_refroidissement: Optional[str] = ""
    rampe_descente_c_min: Optional[GroundedFloat] = None

class HydroLavage(BaseModel):
    solvants: List[str] = Field(default_factory=list)
    nombre_cycles_centrifugation: Optional[int] = None
    vitesse_centrifugation_rpm: Optional[float] = None

class HydroSechage(BaseModel):
    temperature_celsius: Optional[GroundedFloat] = None
    duree_h: Optional[GroundedFloat] = None
    environnement: Optional[str] = ""

class HydroPostTraitement(BaseModel):
    lavage: Optional[HydroLavage] = None
    sechage_poudre: Optional[HydroSechage] = None

class HydrothermalSynthesis(BaseSynthesisStep):
    methode: Literal["hydrothermale_solvothermale"] = "hydrothermale_solvothermale"
    reactifs: Optional[HydroReactifs] = None
    reacteur: Optional[HydroReacteur] = None
    traitement_thermique: Optional[HydroTraitementThermique] = None
    post_traitement: Optional[HydroPostTraitement] = None


# =============================================================================
# 5. Co-précipitation
# =============================================================================

class CoprecipPrecurseur(BaseModel):
    nature_chimique: Optional[str] = ""
    concentration_mol_l: Optional[float] = None

class CoprecipAgent(BaseModel):
    nature_chimique: Optional[str] = ""
    concentration_mol_l: Optional[float] = None

class CoprecipReactifs(BaseModel):
    precurseurs_cations: List[CoprecipPrecurseur] = Field(default_factory=list)
    agent_precipitant: Optional[CoprecipAgent] = None

class CoprecipConditions(BaseModel):
    mode_ajout: Optional[str] = ""
    vitesse_ajout_ml_min: Optional[float] = None
    temperature_milieu_celsius: Optional[GroundedFloat] = None
    vitesse_agitation_rpm: Optional[float] = None
    ph_consigne: Optional[float] = None

class CoprecipMaturation(BaseModel):
    temps_maintien_h: Optional[GroundedFloat] = None
    temperature_celsius: Optional[GroundedFloat] = None

class CoprecipSechage(BaseModel):
    temperature_celsius: Optional[GroundedFloat] = None
    duree_h: Optional[GroundedFloat] = None

class CoprecipCalcination(BaseModel):
    rampe_montee_c_min: Optional[GroundedFloat] = None
    temperature_palier_celsius: Optional[GroundedFloat] = None
    duree_palier_h: Optional[GroundedFloat] = None
    atmosphere: Optional[str] = ""

class CoprecipRecuperation(BaseModel):
    methode_separation: Optional[str] = ""
    solvants_lavage: List[str] = Field(default_factory=list)
    critere_arret_lavage: Optional[str] = ""
    sechage: Optional[CoprecipSechage] = None
    calcination: Optional[CoprecipCalcination] = None

class CoprecipitationSynthesis(BaseSynthesisStep):
    methode: Literal["co_precipitation"] = "co_precipitation"
    reactifs: Optional[CoprecipReactifs] = None
    conditions_precipitation: Optional[CoprecipConditions] = None
    maturation: Optional[CoprecipMaturation] = None
    recuperation_et_traitements: Optional[CoprecipRecuperation] = None


# =============================================================================
# 6. Pechini (Sol-Gel Polymérique)
# =============================================================================

class PechiniAgent(BaseModel):
    nature: Optional[str] = "acide_citrique"
    ratio_molaire_chelatant_cations: Optional[float] = None

class PechiniReticulant(BaseModel):
    nature: Optional[str] = "ethylene_glycol"
    ratio_molaire_chelatant_reticulant: Optional[float] = None

class PechiniFormulation(BaseModel):
    precurseurs_metalliques: List[str] = Field(default_factory=list)
    agent_chelatant: Optional[PechiniAgent] = None
    agent_reticulant: Optional[PechiniReticulant] = None

class PechiniChelation(BaseModel):
    temperature_bain_celsius: Optional[GroundedFloat] = None
    duree_agitation_h: Optional[GroundedFloat] = None

class PechiniEsterification(BaseModel):
    temperature_celsius: Optional[GroundedFloat] = None
    duree_h: Optional[GroundedFloat] = None

class PechiniConditions(BaseModel):
    chelation: Optional[PechiniChelation] = None
    esterification: Optional[PechiniEsterification] = None

class PechiniPyrolyse(BaseModel):
    temperature_celsius: Optional[GroundedFloat] = None
    duree_h: Optional[GroundedFloat] = None

class PechiniCalcination(BaseModel):
    rampe_montee_c_min: Optional[GroundedFloat] = None
    temperature_palier_celsius: Optional[GroundedFloat] = None
    duree_palier_h: Optional[GroundedFloat] = None
    atmosphere: Optional[str] = ""

class PechiniTraitementsThermiques(BaseModel):
    pyrolyse_charring: Optional[PechiniPyrolyse] = None
    calcination: Optional[PechiniCalcination] = None

class PechiniSynthesis(BaseSynthesisStep):
    methode: Literal["pechini_sol_gel_polymerique"] = "pechini_sol_gel_polymerique"
    formulation: Optional[PechiniFormulation] = None
    conditions_synthese: Optional[PechiniConditions] = None
    traitements_thermiques: Optional[PechiniTraitementsThermiques] = None


# =============================================================================
# 7. Solution Combustion Synthesis
# =============================================================================

class CombustReducteur(BaseModel):
    nature_chimique: Optional[str] = ""

class CombustReactifs(BaseModel):
    precurseurs_oxydants: List[str] = Field(default_factory=list)
    combustible_reducteur: Optional[CombustReducteur] = None

class CombustParametres(BaseModel):
    ratio_molaire_oxydant_reducteur_phi: Optional[float] = None
    valence_totale_oxydants: Optional[float] = None
    valence_totale_reducteurs: Optional[float] = None

class CombustConditions(BaseModel):
    temperature_deshydratation_celsius: Optional[GroundedFloat] = None
    temperature_four_prechauffe_celsius: Optional[GroundedFloat] = None
    temps_auto_ignition_s: Optional[GroundedFloat] = None
    temperature_flamme_estimee_celsius: Optional[GroundedFloat] = None

class CombustCalcination(BaseModel):
    rampe_montee_c_min: Optional[GroundedFloat] = None
    temperature_palier_celsius: Optional[GroundedFloat] = None
    duree_palier_h: Optional[GroundedFloat] = None
    atmosphere: Optional[str] = ""

class CombustTraitements(BaseModel):
    calcination_post_combustion: Optional[CombustCalcination] = None

class CombustionSynthesis(BaseSynthesisStep):
    methode: Literal["solution_combustion_synthesis"] = "solution_combustion_synthesis"
    reactifs: Optional[CombustReactifs] = None
    parametres_thermodynamiques: Optional[CombustParametres] = None
    conditions_reaction: Optional[CombustConditions] = None
    traitements_thermiques: Optional[CombustTraitements] = None


# =============================================================================
# 8. Voie Solide Céramique
# =============================================================================

class SolideMatierePremiere(BaseModel):
    nature_chimique: Optional[str] = ""
    purete_pourcentage: Optional[float] = None
    granulometrie_initiale_d50_um: Optional[float] = None
    masse_pese_g: Optional[float] = None

class SolideBroyage(BaseModel):
    type_broyeur: Optional[str] = ""
    materiau_jarres_billes: Optional[str] = ""
    diametre_billes_mm: Optional[float] = None
    milieu: Optional[str] = ""
    ratio_massique_billes_poudre: Optional[float] = None
    vitesse_rotation_rpm: Optional[float] = None
    temps_broyage_h: Optional[GroundedFloat] = None

class SolideLiant(BaseModel):
    nature: Optional[str] = ""
    pourcentage_massique: Optional[float] = None

class SolideCompression(BaseModel):
    type: Optional[str] = ""
    pression_appliquee_mpa: Optional[GroundedFloat] = None
    temps_maintien_s: Optional[GroundedFloat] = None

class SolideMiseEnForme(BaseModel):
    liant: Optional[SolideLiant] = None
    compression: Optional[SolideCompression] = None

class SolideDeliantage(BaseModel):
    rampe_montee_c_min: Optional[GroundedFloat] = None
    temperature_celsius: Optional[GroundedFloat] = None
    duree_h: Optional[GroundedFloat] = None

class SolideFrittage(BaseModel):
    rampe_montee_c_min: Optional[GroundedFloat] = None
    temperature_palier_celsius: Optional[GroundedFloat] = None
    duree_palier_h: Optional[GroundedFloat] = None
    rampe_refroidissement_c_min: Optional[GroundedFloat] = None
    atmosphere: Optional[str] = ""

class SolideTraitements(BaseModel):
    deliantage: Optional[SolideDeliantage] = None
    frittage: Optional[SolideFrittage] = None

class SolidStateSynthesis(BaseSynthesisStep):
    methode: Literal["voie_solide_ceramique"] = "voie_solide_ceramique"
    matieres_premieres: List[SolideMatierePremiere] = Field(default_factory=list)
    broyage_melange: Optional[SolideBroyage] = None
    mise_en_forme: Optional[SolideMiseEnForme] = None
    traitements_thermiques: Optional[SolideTraitements] = None


# =============================================================================
# 9. Spray Pyrolysis
# =============================================================================

class SpraySolution(BaseModel):
    precurseurs: List[str] = Field(default_factory=list)
    solvant: Optional[str] = ""

class SprayAtomiseur(BaseModel):
    type: Optional[str] = ""
    frequence_khz: Optional[float] = None

class SprayTransport(BaseModel):
    gaz_porteur: Optional[str] = ""
    debit_gaz_l_min: Optional[GroundedFloat] = None

class SprayGeneration(BaseModel):
    atomiseur: Optional[SprayAtomiseur] = None
    transport: Optional[SprayTransport] = None

class SprayGeometrie(BaseModel):
    diametre_tube_mm: Optional[float] = None
    longueur_tube_mm: Optional[float] = None

class SprayProfil(BaseModel):
    temperature_zone_1_evaporation_celsius: Optional[GroundedFloat] = None
    temperature_zone_2_decomposition_celsius: Optional[GroundedFloat] = None
    temperature_zone_3_cristallisation_celsius: Optional[GroundedFloat] = None

class SprayReacteur(BaseModel):
    geometrie: Optional[SprayGeometrie] = None
    profil_thermique: Optional[SprayProfil] = None

class SprayRecuperation(BaseModel):
    type_filtre_cyclone: Optional[str] = ""
    temperature_collecteur_celsius: Optional[GroundedFloat] = None

class SprayPyrolysisSynthesis(BaseSynthesisStep):
    methode: Literal["spray_pyrolysis"] = "spray_pyrolysis"
    solution_initiale: Optional[SpraySolution] = None
    generation_aerosol: Optional[SprayGeneration] = None
    reacteur_four_tubulaire: Optional[SprayReacteur] = None
    recuperation: Optional[SprayRecuperation] = None


# =============================================================================
# 10. Flux Growth (Croissance par Flux)
# =============================================================================

class FluxGrowthSynthesis(BaseSynthesisStep):
    """Synthèse par croissance cristalline en flux fondant (Flux Growth)."""
    methode: Literal["flux_growth"] = "flux_growth"
    flux_material: Optional[str] = Field(default=None, description="Solvant / flux utilisé (ex: SrCl2, PbO)")
    crucible_material: Optional[str] = Field(default=None, description="Creuset utilisé (ex: Pt, Alumina)")
    melting_temperature_celsius: Optional[GroundedFloat] = Field(default=None, description="Température de fusion / trempage dans le flux")
    soak_time_h: Optional[GroundedFloat] = Field(default=None, description="Temps de trempage (soak time) en heures")
    cooling_rate_c_per_h: Optional[GroundedFloat] = Field(default=None, description="Vitesse de refroidissement en °C/h")


# =============================================================================
# Fallback / Méthode Générique
# =============================================================================

class GenericOperation(BaseSynthesisStep):
    methode: Literal["operation_generique"] = "operation_generique"
    type: str = Field(description="Type d'opération (ex: Dissolution, Calcination, Hydrolysis, Grinding, Milling)")
    description: str = Field(description="Description très courte de l'étape")
    temperature_C: Optional[GroundedFloat] = Field(default=None, description="Température en Celsius")
    duration_min: Optional[GroundedFloat] = Field(default=None, description="Durée en minutes")
    atmosphere: Optional[str] = Field(default="air", description="Atmosphère (N2, Ar, air, O2)")
    equipment: Optional[str] = Field(default=None, description="Équipement (ex: four à moufle, autoclave)")


# =============================================================================
# TYPE POLYMORPHE GLOBAL (Union Discriminée par `methode`)
# =============================================================================

SynthesisStep = Annotated[
    Union[
        PVDSynthesis,
        CVDSynthesis,
        SolGelSynthesis,
        HydrothermalSynthesis,
        CoprecipitationSynthesis,
        PechiniSynthesis,
        CombustionSynthesis,
        SolidStateSynthesis,
        SprayPyrolysisSynthesis,
        FluxGrowthSynthesis,
        GenericOperation,
    ],
    Field(discriminator="methode")
]


# =============================================================================
# REGISTRE DES MÉTHODES & FACTORY DE SCHÉMAS DYNAMIQUES
# =============================================================================

METHOD_REGISTRY: dict[str, type[BaseSynthesisStep]] = {
    "pvd_pulverisation_cathodique": PVDSynthesis,
    "cvd_chemical_vapor_deposition": CVDSynthesis,
    "sol_gel": SolGelSynthesis,
    "hydrothermale_solvothermale": HydrothermalSynthesis,
    "co_precipitation": CoprecipitationSynthesis,
    "pechini_sol_gel_polymerique": PechiniSynthesis,
    "solution_combustion_synthesis": CombustionSynthesis,
    "voie_solide_ceramique": SolidStateSynthesis,
    "spray_pyrolysis": SprayPyrolysisSynthesis,
    "flux_growth": FluxGrowthSynthesis,
    "operation_generique": GenericOperation,
}


def get_method_class(method_type: str) -> type[BaseSynthesisStep]:
    """Retourne la classe Pydantic pour un type de méthode donné."""
    if method_type not in METHOD_REGISTRY:
        raise ValueError(
            f"Méthode inconnue : '{method_type}'. "
            f"Méthodes supportées : {list(METHOD_REGISTRY.keys())}"
        )
    return METHOD_REGISTRY[method_type]


def get_extraction_model_for_method(method_type: str, precursor_model=None, missing_param_model=None):
    """Factory : crée dynamiquement un modèle d'extraction contraint à UNE SEULE méthode.
    
    Le JSON schema généré par Pydantic ne contiendra QUE les champs de la méthode
    spécifiée, empêchant structurellement le LLM de remplir des champs d'autres méthodes.
    
    Args:
        method_type: Clé du METHOD_REGISTRY (ex: "flux_growth")
        precursor_model: Modèle Precursor (injecté pour éviter import circulaire)
        missing_param_model: Modèle MissingParameter (injecté pour éviter import circulaire)
    
    Returns:
        Classe Pydantic dynamique avec steps contraints au sous-type spécifique
    """
    specific_class = METHOD_REGISTRY.get(method_type)
    if not specific_class:
        return None  # L'appelant utilisera le schéma complet en fallback

    # Construction des champs du modèle dynamique
    fields = {
        "reasoning": (str, Field(description="Réflexion pas-à-pas pour extraire les entités chimiques et opérations.")),
        "route_id": (str, Field(description="ID de la route de synthèse (ex: route_1)")),
        "target": (str, Field(description="Le matériau final visé")),
        "steps": (
            List[Union[specific_class, GenericOperation]],
            Field(description="Séquence chronologique des opérations de synthèse")
        ),
        "confidence": (float, Field(ge=0.0, le=1.0)),
    }

    # Ajouter les champs optionnels si les modèles sont fournis
    if precursor_model:
        fields["precursors"] = (
            List[precursor_model],
            Field(description="Liste des précurseurs et réactifs utilisés")
        )
    if missing_param_model:
        fields["missing_parameters"] = (
            List[missing_param_model],
            Field(default_factory=list, description="Paramètres absents du texte source")
        )

    return create_model(
        f"ExtractionResult_{method_type}",
        **fields
    )

# =============================================================================
# MULTI-PATHWAY EXTRACTION MODELS (V4)
# =============================================================================

class Solvent(BaseModel):
    name: str = Field(default="", description="Nom du solvant. Si sel inorganique fondu à haute temp (ex: KCl), le considérer comme flux.")
    is_flux: bool = Field(default=False, description="True si c'est un flux inorganique (sel fondu)")
    volume_mL: Optional[float] = None

class StepTemplate(BaseModel):
    step_number: int
    operation: str = Field(description="Type d'opération (ex: Mélange, Chauffage, Broyage, Calcination)")
    description: str = Field(description="Description textuelle de ce qu'il se passe dans cette étape")
    raw_text: str = Field(description="Extrait exact du texte justifiant cette étape")

    @model_validator(mode='after')
    def check_raw_text_verbatim(self, info: ValidationInfo):
        if info.context and "chunk_text" in info.context:
            chunk_text = info.context["chunk_text"]
            if self.raw_text and self.raw_text not in chunk_text:
                raise ValueError(f"Erreur: le raw_text invente des mots. Utilisez un copier-coller exact.")
        return self

class PathwayTemplate(BaseModel):
    target_material: dict = {}
    synthesis_route: str = ""
    synthesis_steps: List[StepTemplate] = []

    @model_validator(mode='after')
    def check_mechanical_operations(self) -> 'PathwayTemplate':
        mechanical_keywords = ["grind", "mill", "mix", "pellet", "broy", "mélang", "pastill"]
        raw_texts = set(step.raw_text for step in self.synthesis_steps if step.raw_text)
        
        for raw in raw_texts:
            if any(k in raw.lower() for k in mechanical_keywords):
                has_mech_op = any(
                    any(k in s.operation.lower() for k in mechanical_keywords)
                    for s in self.synthesis_steps if s.raw_text == raw
                )
                if not has_mech_op:
                    raise ValueError(
                        f"Le texte source '{raw}' mentionne une opération mécanique (broyage, mixage, etc.) "
                        "mais aucune étape correspondante (ex: operation='Grinding') n'a été extraite pour cette séquence. "
                        "Veuillez ajouter une étape distincte pour cette opération mécanique."
                    )
        return self

class MultiPathwayTemplate(BaseModel):
    pathways: List[PathwayTemplate] = []
    confidence: float = 0.0
    extraction_notes: str = ""

class PrecursorUnit(str, Enum):
    MOL = 'mol'
    G = 'g'
    MG = 'mg'
    ML = 'ml'
    NOT_SPECIFIED = 'Not specified'

class PrecursorData(BaseModel):
    name: str = Field(..., description="Nom du précurseur (ex: SrO, IrO2)")
    amount: Optional[float] = Field(None, description="Valeur numérique de la quantité")
    unit: Optional[PrecursorUnit] = Field(default=PrecursorUnit.NOT_SPECIFIED, description="Unité de mesure")

class PathwayData(BaseModel):
    target_material: dict = {}
    concentration_or_variant: Optional[str] = None
    synthesis_route: str = ""
    precursors: List[PrecursorData] = []
    solvents: List[Solvent] = []
    synthesis_steps: list = []
    byproducts: list = []
    yield_percent: Optional[float] = None

    @model_validator(mode='after')
    def check_temperature_vs_solvents(self) -> 'PathwayData':
        liquid_solvents = {"water", "eau", "h2o", "ethanol", "methanol", "isopropanol", "tms", "toluène", "toluene", "acetone"}
        has_liquid = False
        for s in self.solvents:
            s_name = (s.name or "").lower()
            if s_name in liquid_solvents or "acid" in s_name or "alcool" in s_name or "alcohol" in s_name:
                has_liquid = True
                break
                
        if has_liquid:
            for step in self.synthesis_steps:
                temp = step.get("temperature_C")
                op = step.get("operation", "").lower()
                if temp is not None and temp > 300:
                    if not any(k in op for k in ["calcination", "séchage", "drying", "annealing", "recuit"]):
                        raise ValueError(
                            f"Température invalide ({temp}°C) pour l'opération '{op}' en présence de solvants liquides. "
                            "Si c'est une réaction en phase liquide, la température ne peut pas dépasser 300°C sans équipement de très haute pression."
                        )
        return self

class MultiPathwayData(BaseModel):
    pathways: List[PathwayData] = []
    needs_vision_clarification: bool = False
    needs_additional_text: bool = False
    confidence: float = 0.0
    extraction_notes: str = ""
