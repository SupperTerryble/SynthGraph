from synthgraph.schemas.core import ExtractionResult, Precursor
from synthgraph.schemas.synthesis import PVDSynthesis, PVDEnceinteAtmosphere, PVDVide, GenericOperation
import json

def run_test():
    try:
        from synthgraph.schemas.synthesis import GroundedFloat
        step1 = PVDSynthesis(
            step_number=1,
            enceinte_et_atmosphere=PVDEnceinteAtmosphere(
                vide=PVDVide(
                    pression_base_mbar=GroundedFloat(value=1e-6, unit="mbar", source_quote="base pressure of 10-6 mbar", confidence=1.0),
                    temperature_enceinte_celsius=GroundedFloat(value=25.0, unit="C", source_quote="at room temperature", confidence=1.0)
                )
            )
        )
        
        # Création d'une étape Générique
        step2 = GenericOperation(
            step_number=2,
            type="Recuit",
            description="Recuit sous vide post-dépôt",
            temperature_C=GroundedFloat(value=400.0, unit="C", source_quote="annealed at 400 °C", confidence=1.0),
            duration_min=GroundedFloat(value=120.0, unit="min", source_quote="for 2 h", confidence=1.0)
        )
        
        # Création du résultat global
        result = ExtractionResult(
            reasoning="Extraction d'un film mince de TiO2 déposé par PVD.",
            route_id="route_1",
            method_type="pvd_pulverisation_cathodique",
            target="TiO2 Thin Film",
            precursors=[
                Precursor(name="Ti Target", formula="Ti", role="cible PVD")
            ],
            steps=[step1, step2],
            confidence=0.95
        )
        
        # Affichage du JSON validé
        print("Test réussi ! Voici le JSON généré par les nouveaux schémas :")
        print(result.model_dump_json(indent=2))
        
    except Exception as e:
        print("Erreur lors du test :", str(e))

if __name__ == "__main__":
    run_test()
