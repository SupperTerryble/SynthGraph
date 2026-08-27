"""Contenant attribue OPERATION PAR OPERATION (choix de Terry, 20/08).

Principe chimique : un contenant nomme lors d'un TRANSFERT vaut pour les
operations suivantes jusqu'au transfert suivant. Les deux fausses pistes reelles
a ne pas rater : « VialTweeter » (sonicateur de marque, `vial` dans un mot) et
« stored in glass vial for further analysis » (stockage APRES synthese).
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from synthgraph.extraction.graph_tools import RouteBuilder  # noqa: E402

ok = fail = 0


def ck(label, cond):
    global ok, fail
    if cond:
        ok += 1
        print(f"  OK    {label}")
    else:
        fail += 1
        print(f"  ECHEC {label}")


def build(src, citations):
    rb = RouteBuilder(source_text=src, target="x", method_type="y")
    rb.operations = [{"type": "heating", "operation": "heating", "order": i,
                      "citation": c} for i, c in enumerate(citations, 1)]
    n = rb._recover_vessel_per_step()
    return rb.operations, n


print("\n=== 1. cas reel crystal : le creuset couvre les etapes suivantes ===")
SRC = ("Powders of IrO2, SrCO3, and SrCl2 6H2O were thoroughly mixed and placed "
       "in a platinum crucible covered with a lid. The crucibles were heated in "
       "a programmable box furnace in air. After cooling, crystals were "
       "separated from the residual flux by rinsing out with distilled water.")
ops, n = build(SRC, ["The crucibles were heated in a programmable box furnace in air",
                     "After cooling, crystals were separated from the residual flux"])
ck("2 operations recoivent un contenant", n == 2)
ck("le contenant est le creuset de platine",
   all("platinum crucible" in (o.get("vessel_name") or "") for o in ops))
ck("la phrase de preuve est conservee", all(o.get("vessel_citation") for o in ops))
ck("la preuve vient bien du texte",
   all(o["vessel_citation"] in SRC for o in ops))

print("\n=== 2. cas reel hydro_czts : transfert vers la bombe ===")
SRC2 = ("2 mmol CuCl2 were dispersed in 20 ml of deionized water for 5 min under "
        "constant stirring, and then the obtained solution was transferred to an "
        "acid digestion bomb (50 ml). The hydrothermal synthesis was conducted at "
        "170 to 190 C for 6 to 16 h in an electric oven.")
ops, n = build(SRC2, ["The hydrothermal synthesis was conducted at 170 to 190 C"])
ck("l'etape herite de la bombe de digestion",
   "digestion bomb" in (ops[0].get("vessel_name") or ""))

print("\n=== 3. PIEGE : « VialTweeter » n'est pas un contenant ===")
SRC3 = ("the nanopowder was dispersed in a water-based solution and "
        "ultra-sonicated (UP200ST with VialTweeter, hielscher) to disrupt the "
        "agglomerates. The precursor was calcined at 400 C for 4 h.")
ops, n = build(SRC3, ["The precursor was calcined at 400 C for 4 h"])
ck("aucun contenant attribue", n == 0 and not ops[0].get("vessel_name"))

print("\n=== 4. PIEGE : le flacon de STOCKAGE apres synthese ===")
SRC4 = ("the precipitates were dried at room temperature. After drying, "
        "nanoparticles were stored in glass vial for further analysis.")
ops, n = build(SRC4, ["the precipitates were dried at room temperature"])
ck("le flacon de stockage n'est pas attribue", n == 0)

print("\n=== 5. un NOUVEAU transfert remplace le contenant precedent ===")
SRC5 = ("The powder was placed in an alumina crucible and calcined at 600 C. "
        "The product was then transferred to a platinum crucible and melted at "
        "1300 C.")
ops, n = build(SRC5, ["The powder was placed in an alumina crucible and calcined at 600 C",
                      "The product was then transferred to a platinum crucible and melted"])
ck("etape 1 : creuset d'alumine", "alumina" in (ops[0].get("vessel_name") or ""))
ck("etape 2 : creuset de platine", "platinum" in (ops[1].get("vessel_name") or ""))

print("\n=== 5bis. contenant decrit APRES les etapes (cas reel prepara 1957) ===")
# Ce papier decrit ses nacelles apres coup : la phrase arrive plus loin dans le
# texte que toutes les etapes. Un seul contenant nomme => aucune ambiguite.
SRC6 = ("Strontium-iridium oxide is obtained by the reaction between iridium "
        "metal powder and strontium oxide at 1200 degrees. The reaction occurs "
        "rapidly compared with most solid phase reactions. This procedure was "
        "carried out in platinum or zirconium silicate combustion boats.")
ops, n = build(SRC6, ["Strontium-iridium oxide is obtained by the reaction between "
                      "iridium metal powder and strontium oxide at 1200 degrees"])
ck("l'etape herite du contenant unique du papier",
   "boats" in (ops[0].get("vessel_name") or ""))

print("\n=== 5ter. DEUX contenants et aucun transfert prealable : abstention ===")
SRC7 = ("The oxide was obtained at 1200 degrees by direct reaction. "
        "Some runs were carried out in a platinum crucible. "
        "Other runs were performed in an alumina boat.")
ops, n = build(SRC7, ["The oxide was obtained at 1200 degrees by direct reaction"])
ck("ambigu : aucun contenant attribue", n == 0 and not ops[0].get("vessel_name"))

print("\n=== 5quater. une SEPARATION sort la matiere du recipient ===")
# Cas reel hydro_czts : le produit est filtre puis lave, donc il n'est plus dans
# la bombe quand il seche a l'etuve. Propager donnait « sechage a l'etuve sous
# vide, contenant = acid digestion bomb » — contradiction visible.
SRC8 = ("the obtained solution was transferred to an acid digestion bomb. "
        "The hydrothermal synthesis was conducted at 180 C for 12 h. "
        "The final product was filtrated and washed with ethanol. "
        "followed by drying at 60 C in a vacuum oven.")
rb = RouteBuilder(source_text=SRC8, target="CZTS", method_type="hydrothermale")
rb.operations = [
    {"type": "heating", "operation": "heating", "order": 1,
     "citation": "The hydrothermal synthesis was conducted at 180 C for 12 h"},
    {"type": "washing", "operation": "washing", "order": 2,
     "citation": "The final product was filtrated and washed with ethanol"},
    {"type": "drying", "operation": "drying", "order": 3,
     "citation": "followed by drying at 60 C in a vacuum oven"},
]
rb._recover_vessel_per_step()
ck("la chauffe garde la bombe",
   "digestion bomb" in (rb.operations[0].get("vessel_name") or ""))
ck("le SECHAGE, apres filtration, n'est plus dans la bombe",
   not rb.operations[2].get("vessel_name"))

print("\n=== 6. fail-safe ===")
ops, n = build("The sample was heated to 1300 C.", ["The sample was heated to 1300 C"])
ck("aucun transfert dans la source : rien", n == 0)
ops, n = build(SRC, ["une citation absente de la source"])
ck("citation introuvable dans la source : rien", n == 0)
rb = RouteBuilder(source_text="", target="x", method_type="y")
ck("source vide : rien", rb._recover_vessel_per_step() == 0)

print("\n=== 7. un contenant DEJA present n'est jamais ecrase ===")
rb = RouteBuilder(source_text=SRC, target="x", method_type="y")
rb.operations = [{"type": "heating", "operation": "heating", "order": 1,
                  "citation": "The crucibles were heated in a programmable box furnace",
                  "vessel_name": "creuset fourni par le modele"}]
rb._recover_vessel_per_step()
ck("la valeur existante est conservee",
   rb.operations[0]["vessel_name"] == "creuset fourni par le modele")

print(f"\n{ok} OK / {fail} ECHECS")
sys.exit(1 if fail else 0)
