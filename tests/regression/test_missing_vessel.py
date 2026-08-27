"""Un contenant absent doit etre DECLARE, jamais passe sous silence.

Demande de Terry (20/08). Sans cela, un chimiste ne distingue pas « aucun
recipient necessaire » de « on n'a pas su le trouver ». La regle du projet est
explicite : « un trou n'est jamais comble, il est declare ».
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


def trous(rb):
    return rb.to_pathways_dict()["pathways"][0]["missing_parameters"]


def vessel_trous(rb):
    return [t for t in trous(rb) if t.get("parameter") == "vessel"]


print("\n=== 1. sans contenant, le trou est DECLARE ===")
SRC = "The sample was heated at 1300 C for 24 h in a programmable box furnace."
rb = RouteBuilder(source_text=SRC, target="x", method_type="y")
rb.add_precursor("SrCO3", "The sample was heated at 1300 C for 24 h", )
rb.add_operation("heating", SRC, temperature_c=1300)
t = vessel_trous(rb)
ck("un trou 'vessel' est present", len(t) == 1)
ck("  severite 'required' pour une chauffe", t and t[0]["severity"] == "required")
ck("  le trou porte le rang de l'etape", t and t[0].get("step_order") is not None)
ck("  le trou porte le type d'etape", t and t[0].get("step_type") == "heating")

print("\n=== 2. avec contenant, AUCUN trou ===")
SRC2 = ("Powders were placed in a platinum crucible covered with a lid. "
        "The crucibles were heated at 1300 C for 24 h.")
rb = RouteBuilder(source_text=SRC2, target="x", method_type="y")
rb.add_precursor("SrCO3", "Powders were placed in a platinum crucible covered with a lid")
rb.add_operation("heating", "The crucibles were heated at 1300 C for 24 h",
                 temperature_c=1300)
ck("aucun trou de contenant", not vessel_trous(rb))

print("\n=== 3. le modele a cite le contenant lui-meme : aucun trou ===")
rb = RouteBuilder(source_text=SRC2, target="x", method_type="y")
rb.add_precursor("SrCO3", "Powders were placed in a platinum crucible covered with a lid")
rb.add_operation("heating", "The crucibles were heated at 1300 C for 24 h",
                 temperature_c=1300, equipment="platinum crucible")
ck("aucun trou quand `equipment` porte un contenant", not vessel_trous(rb))

print("\n=== 4. severite selon le type d'operation ===")
SRC3 = "The precipitate was dried at room temperature after filtration."
rb = RouteBuilder(source_text=SRC3, target="x", method_type="y")
rb.add_precursor("SrCO3", "The precipitate was dried at room temperature after filtration")
rb.add_operation("drying", SRC3)
t = vessel_trous(rb)
ck("un sechage donne un trou 'recommended'",
   t and t[0]["severity"] == "recommended")

print("\n=== 5. les trous EXISTANTS ne sont pas perdus ===")
rb = RouteBuilder(source_text=SRC, target="x", method_type="y")
rb.add_precursor("SrCO3", "The sample was heated at 1300 C for 24 h")
rb.add_operation("heating", SRC, temperature_c=1300)
tous = trous(rb)
ck("d'autres trous que 'vessel' subsistent",
   any(x.get("parameter") != "vessel" for x in tous))
ck("la structure est homogene",
   all({"step_order", "step_type", "parameter", "severity"} <= set(x)
       for x in tous))

print(f"\n{ok} OK / {fail} ECHECS")
sys.exit(1 if fail else 0)
