"""Tests offline des outils de construction (V5_TC), sans GPU."""
import pathlib
import sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from synthgraph.extraction.graph_tools import RouteBuilder, TOOL_SCHEMAS, TOOL_NAMES

ok = fail = 0
def check(label, cond, detail=""):
    global ok, fail
    if cond: ok += 1; print(f"  PASS  {label}")
    else:    fail += 1; print(f"  FAIL  {label}  {detail}")

SRC = """Powders of IrO2, SrCO3, and SrCl2 6H2O were thoroughly mixed in a molar ratio
of 1 : 2 : 7 and placed in a platinum crucible covered with a lid. The crucibles were
heated in a programmable box furnace in air then cooled to room temperature.
- Sr214#1 1 : 2 : 7 1300 C -> (8 C/h) 900 C -> RT
- Sr214/Sr327#1 1 : 2 : 7 1150 C (12 h dwell) -> (5 C/h) 880 C -> RT
Crystals were separated from the residual flux by rinsing with distilled water."""

print("=== precurseurs ===")
b = RouteBuilder(SRC, "Sr2IrO4", "flux")
r = b.add_precursor("IrO2", "Powders of IrO2, SrCO3, and SrCl2 6H2O were thoroughly mixed in a molar ratio")
check("precurseur valide accepte", r["ok"], r["message"])

r = b.add_precursor("TiO2", "Powders of IrO2, SrCO3, and SrCl2 6H2O were thoroughly mixed in a molar ratio")
check("precurseur ABSENT du texte refuse", not r["ok"], r["message"])
check("  message actionnable", "n'apparait pas" in r["message"])

r = b.add_precursor("SrCO3", "The crucibles were heated in a programmable box furnace in air")
check("citation ne nommant pas le compose refusee", not r["ok"], r["message"])

r = b.add_precursor("IrO2", "Powders of IrO2 were mixed with something invented here")
check("citation INVENTEE refusee", not r["ok"], r["message"])
check("  message exige une copie exacte", "COPIER" in r["message"] or "existe pas" in r["message"])

r = b.add_precursor("SrCl2", "Powders of IrO2, SrCO3, and SrCl2 6H2O were thoroughly mixed in a molar ratio",
                    molar_ratio=7, role="flux")
# Contrat change le 19/08 : un ratio non prouve n'emporte plus le PRECURSEUR.
# L'invariant qui compte reste verifie juste en dessous — le ratio 7, absent de
# la citation, ne doit sous aucun pretexte etre enregistre.
check("precurseur conserve malgre le ratio non prouve", r["ok"], r["message"])
check("  appel signale PARTIEL", r.get("partial") is True)
check("  ratio 7 NON enregistre (regle d'or)",
      all(p.get("molar_ratio") != 7 for p in b.precursors))

# La phrase reelle porte A LA FOIS le compose et le ratio -> doit etre acceptee.
# (Exigence volontairement stricte : la preuve doit tenir dans UNE citation.)
r = b.add_precursor("SrCl2",
                    "Powders of IrO2, SrCO3, and SrCl2 6H2O were thoroughly mixed in a molar ratio\nof 1 : 2 : 7",
                    molar_ratio=7, role="flux")
check("ratio 7 accepte quand la citation porte compose ET ratio", r["ok"], r["message"])

print("\n=== operations ===")
r = b.add_operation("heating", "- Sr214#1 1 : 2 : 7 1300 C -> (8 C/h) 900 C -> RT",
                    temperature_c=1300)
check("temperature prouvee par la LIGNE DE TABLEAU acceptee", r["ok"], r["message"])

r = b.add_operation("heating", "The crucibles were heated in a programmable box furnace in air",
                    temperature_c=1300)
check("acceptation PARTIELLE (etape gardee, valeur ecartee)", r["ok"], r["message"])
check("  valeur non prouvee ABSENTE de l'etape",
      b.operations[-1].get("temperature_c") is None, b.operations[-1])
check("  message dit quelle valeur est ecartee", "1300" in r["message"])
check("  message suggere la ligne de tableau", "tableau" in r["message"].lower())

r = b.add_operation("cooling", "- Sr214#1 1 : 2 : 7 1300 C -> (8 C/h) 900 C -> RT",
                    cooling_rate_c_per_h=8)
check("vitesse acceptee (notation C/h presente)", r["ok"], r["message"])

r = b.add_operation("cooling", "Crystals were separated from the residual flux by rinsing with distilled water",
                    cooling_rate_c_per_h=8)
check("vitesse ecartee si aucune notation de taux",
      b.operations[-1].get("cooling_rate_c_per_h") is None, b.operations[-1])

print("\n=== finalisation ===")
b2 = RouteBuilder(SRC, "Sr2IrO4", "flux")
r = b2.finalize_route()
check("finalize refuse sans precurseur", not r["ok"], r["message"])
b2.add_precursor("IrO2", "Powders of IrO2, SrCO3, and SrCl2 6H2O were thoroughly mixed in a molar ratio")
r = b2.finalize_route()
check("finalize refuse sans operation", not r["ok"], r["message"])
b2.add_operation("mixing", "Powders of IrO2, SrCO3, and SrCl2 6H2O were thoroughly mixed in a molar ratio")
r = b2.finalize_route(sample_id="Sr214#1")
check("finalize accepte quand tout est la", r["ok"], r["message"])
check("  marque finalise", b2.finalized)

print("\n=== export pipeline ===")
d = b.to_pathways_dict()
pw = d["pathways"][0]
check("structure pathways produite", "synthesis_steps" in pw and "precursors" in pw)
check("etapes normalisees", len(pw["synthesis_steps"]) >= 2, f"n={len(pw['synthesis_steps'])}")
check("rejets traces", len(b.rejections) >= 4, f"n={len(b.rejections)}")
check("sample_id -> variant_id", b2.to_pathways_dict()["pathways"][0]["variant_id"] == "Sr214#1")

print("\n=== schemas ===")
check("3 outils exposes", len(TOOL_SCHEMAS) == 3, f"n={len(TOOL_SCHEMAS)}")
check("noms connus", TOOL_NAMES == {"add_precursor", "add_operation", "finalize_route"})

print(f"\nTOTAL {ok} PASS / {fail} FAIL")

print("\n=== citations abregees par ellipse ===")
b3 = RouteBuilder(SRC, "Sr2IrO4", "flux")
# cas REEL du test de faisabilite : le modele coupe avec …
r = b3.add_precursor("IrO2", "Powders of IrO2, SrCO3, and SrCl2 … placed in a platinum crucible covered with a lid")
check("citation abregee par … acceptee", r["ok"], r["message"])

r = b3.add_precursor("SrCO3", "Powders of IrO2 … totalement invente ici voila")
check("ellipse avec fragment INVENTE refusee", not r["ok"], r["message"])

r = b3.add_precursor("SrCO3", "Powders of IrO2 … a")
check("fragment trop court refuse", not r["ok"], r["message"])

# l'ordre du texte doit etre respecte (anti-recombinaison)
r = b3.add_precursor("SrCO3", "placed in a platinum crucible … Powders of IrO2, SrCO3")
check("fragments dans le DESORDRE refuses", not r["ok"], r["message"])

print(f"\nTOTAL FINAL {ok} PASS / {fail} FAIL")
