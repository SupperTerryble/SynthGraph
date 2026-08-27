from synthgraph.schemas.core import Precursor, RouteExtractionResult, MissingParameter
from synthgraph.schemas.synthesis import FluxGrowthSynthesis, GroundedFloat, get_extraction_model_for_method

def test_new_features():
    print("=== Test 1: Precursor avec qualitative_amount ===")
    p = Precursor(
        name="SrCl2",
        formula="SrCl2",
        role="flux",
        qualitative_amount="en excès par rapport aux précurseurs (10:1 en masse)"
    )
    print(p.model_dump_json(indent=2))
    
    print("\n=== Test 2: FluxGrowthSynthesis Schema ===")
    step = FluxGrowthSynthesis(
        step_number=1,
        flux_material="SrCl2",
        crucible_material="Pt",
        melting_temperature_celsius=GroundedFloat(value=1000.0, unit="C", source_quote="melted at 1000 °C", confidence=0.9),
        soak_time_h=GroundedFloat(value=2.0, unit="h", source_quote="held for 2 hours", confidence=0.9),
        cooling_rate_c_per_h=GroundedFloat(value=5.0, unit="C/h", source_quote="cooled at 5 °C/h", confidence=0.95)
    )
    print(step.model_dump_json(indent=2))
    
    print("\n=== Test 3: Factory (get_extraction_model_for_method) ===")
    DynamicModel = get_extraction_model_for_method("flux_growth", Precursor, MissingParameter)
    
    res = DynamicModel(
        reasoning="Test de la méthode dynamique flux_growth",
        route_id="route_1",
        target="La2CuO4",
        confidence=0.9,
        steps=[step],
        precursors=[p]
    )
    print("Modèle dynamique instancié avec succès !")
    print(res.model_dump_json(indent=2))

if __name__ == "__main__":
    test_new_features()
