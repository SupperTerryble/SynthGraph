"""La condition RETENUE, quand le modele n'a cite que la plage exploree.

Cas reel `hydro_czts` : « conducted at 170°C to 190°C for 6 to 16 h » dit ce qui
a ete TESTE ; une autre phrase dit ce qui a MARCHE — « Pure kesterite Cu2ZnSnS4
has been synthesized at 180°C for 12 h ». Un chimiste doit refaire l'optimum,
pas une borne de la plage.

Fail-safe strict : on n'agit que sur une etape portant deja une PLAGE, et
seulement si les deux valeurs tombent DEDANS.
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


PLAGE = {"type": "heating", "operation": "heating", "order": 1,
         "citation": "conducted at 170 to 190 C for 6 to 16 h",
         "target_temperature_c": 170.0, "duration_h": 16.0,
         "min_temperature_c": 170.0, "max_temperature_c": 190.0,
         "min_duration_h": 6.0, "max_duration_h": 16.0}


def run(src, etape=None):
    rb = RouteBuilder(source_text=src, target="CZTS", method_type="hydro")
    rb.operations = [dict(etape or PLAGE)]
    n = rb._recover_condition_optimale()
    return rb.operations[0], n


print("\n=== 1. cas reel hydro_czts ===")
SRC = ("The hydrothermal synthesis was conducted at 170 to 190 C for 6 to 16 h. "
       "Pure kesterite Cu2ZnSnS4 has been synthesized at 180 C for 12 h from "
       "the reaction system containing 2 mmol of EDTA.")
o, n = run(SRC)
ck("la temperature retenue est 180", o.get("target_temperature_c") == 180.0)
ck("la duree retenue est 12", o.get("duration_h") == 12.0)
ck("la preuve est conservee", "180" in (o.get("condition_citation") or ""))
ck("la provenance est tracee", o.get("condition_source") == "optimum_du_papier")
ck("les bornes de la plage sont intactes",
   o["min_temperature_c"] == 170.0 and o["max_duration_h"] == 16.0)

print("\n=== 2. REGLE D'OR : hors de la plage, on s'abstient ===")
o, n = run("Pure product has been synthesized at 900 C for 2 h.")
ck("900 C hors de 170-190 : aucun changement",
   n == 0 and o["target_temperature_c"] == 170.0)
o, n = run("Pure product has been synthesized at 180 C for 40 h.")
ck("40 h hors de 6-16 : aucun changement", n == 0 and o["duration_h"] == 16.0)

print("\n=== 3. sans marqueur d'optimalite, rien ===")
o, n = run("The mixture was stirred at 180 C for 12 h before cooling.")
ck("une phrase quelconque n'est pas prise pour la recette", n == 0)

print("\n=== 4. sans PLAGE sur l'etape, rien ===")
sans = {"type": "heating", "operation": "heating", "order": 1,
        "citation": "heated at 170 C", "target_temperature_c": 170.0}
o, n = run(SRC, etape=sans)
ck("une etape sans bornes n'est pas modifiee",
   n == 0 and o["target_temperature_c"] == 170.0)

print("\n=== 5. fail-safe ===")
o, n = run("")
ck("source vide : rien", n == 0)
o, n = run("The synthesis was performed successfully.")
ck("phrase sans valeurs : rien", n == 0)

print(f"\n{ok} OK / {fail} ECHECS")
sys.exit(1 if fail else 0)
