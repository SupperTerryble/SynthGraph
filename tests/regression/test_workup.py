"""Recuperation des etapes de traitement final depuis la source (hors ligne).

Cas reel `crystal` : le modele suit le TABLEAU des conditions et oublie la prose.
L'etape « crystals were separated from the residual flux by rinsing out with
distilled water » manquait — sans elle on recupere un bloc de SrCl2 fige et
aucun cristal. Rien n'est fabrique : l'etape nait d'une phrase REELLE du papier,
qui devient sa citation.
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


SRC = ("Powders of IrO2, SrCO3, and SrCl2 6H2O were thoroughly mixed and placed "
       "in a platinum crucible covered with a lid. The crucibles were heated in "
       "a programmable box furnace in air. After cooling, crystals were separated "
       "from the residual flux by rinsing out with distilled water.")


def build(ops):
    rb = RouteBuilder(source_text=SRC, target="Sr2IrO4", method_type="flux")
    rb.operations = list(ops)
    rb._order = len(ops)
    n = rb._recover_workup_steps()
    return rb, n


THERMIQUE = [{"type": "heating", "operation": "heating", "order": 1,
              "citation": "The crucibles were heated in a programmable box furnace in air",
              "target_temperature_c": 1300.0}]

print("\n=== 1. les etapes manquantes sont recuperees ===")
rb, n = build(THERMIQUE)
types = [o["type"] for o in rb.operations]
ck("2 etapes recuperees", n == 2)
ck("l'etape de separation existe", "separation" in types)
ck("l'etape de melange existe", "mixing" in types)

print("\n=== 2. chaque etape recuperee porte SA citation, tiree du papier ===")
for o in rb.operations:
    if o.get("citation_source") == "recuperation_deterministe":
        ck(f"citation de '{o['type']}' presente dans la source",
           o["citation"] in SRC)
        ck(f"  '{o['type']}' n'a AUCUN parametre numerique invente",
           not any(isinstance(v, (int, float)) and k != "order"
                   for k, v in o.items()))

print("\n=== 3. REGLE D'OR : rien n'est cree si le modele l'a deja declare ===")
rb, n = build(THERMIQUE + [
    {"type": "washing", "operation": "washing", "order": 2, "citation": "washed"},
    {"type": "grinding", "operation": "grinding", "order": 3, "citation": "ground"},
])
ck("aucune etape ajoutee", n == 0)

print("\n=== 4. source sans traitement final : abstention ===")
rb = RouteBuilder(source_text="The sample was heated to 1300 C for 24 h.",
                  target="x", method_type="y")
rb.operations = list(THERMIQUE)
ck("aucune etape inventee", rb._recover_workup_steps() == 0)

print("\n=== 5. une phrase SANS indice de contexte est ignoree ===")
rb = RouteBuilder(source_text="The detector was washed before calibration.",
                  target="x", method_type="y")
rb.operations = list(THERMIQUE)
ck("phrase de caracterisation ecartee", rb._recover_workup_steps() == 0)

print("\n=== 5bis. formulations elargies (cas reel cbd_mnse) ===")
# Ces deux phrases etaient ecartees par des motifs trop etroits : l'etape de
# filtration exigee par le gold etait perdue.
CBD = ("The mixture is filtered before being added to the chemical bath. "
       "The solution is mixed at 1000 rpm and is completed with distilled "
       "water to 100 mL.")
rb = RouteBuilder(source_text=CBD, target="MnSe", method_type="CBD")
rb.operations = [{"type": "heating", "operation": "heating", "order": 1,
                  "citation": "The mixture is heated at 80 C"}]
rb._order = 1
n = rb._recover_workup_steps()
types = [o["type"] for o in rb.operations]
ck("« The mixture is filtered » donne une separation", "separation" in types)
ck("« The solution is mixed at 1000 rpm » donne un melange", "mixing" in types)
ck("les deux citations viennent bien du texte",
   all(o["citation"] in CBD for o in rb.operations
       if o.get("citation_source") == "recuperation_deterministe"))

print("\n=== 6. source vide : abstention ===")
rb = RouteBuilder(source_text="", target="x", method_type="y")
ck("aucune etape sur source vide", rb._recover_workup_steps() == 0)

print(f"\n{ok} OK / {fail} ECHECS")
sys.exit(1 if fail else 0)
