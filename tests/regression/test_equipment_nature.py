"""`equipment` doit designer un CONTENANT ou un APPAREIL (hors ligne).

Cas reel `hydro_czts` : `equipment='room temperature'` etait accepte — la valeur
figure bien dans le texte, donc elle passait le controle d'ancrage, mais ce
n'est ni un contenant ni un appareil. Du bruit dans le graphe.
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


SRC = ("the obtained solution was transferred to an acid digestion bomb (50 ml). "
       "The hydrothermal synthesis was conducted in an electric oven. "
       "the bomb was cooled down naturally to room temperature. "
       "Powders were placed in a platinum crucible covered with a lid and heated "
       "in a programmable box furnace. The gel formed on the magnetic stirrer. "
       "dried in a muffle furnace in air. washed with ethanol. "
       "The components were added to a beaker filled with deionized water.")
CIT = "The hydrothermal synthesis was conducted in an electric oven."


def op(equip):
    rb = RouteBuilder(source_text=SRC, target="x", method_type="y")
    r = rb.add_operation("heating", CIT, equipment=equip)
    return rb.operations[0], r, rb


print("\n=== 1. les CONTENANTS sont acceptes ===")
for e in ("platinum crucible", "acid digestion bomb", "beaker"):
    st, _, _ = op(e)
    ck(f"« {e} » accepte", st.get("equipment") == e)

print("\n=== 2. les APPAREILS sont acceptes ===")
for e in ("electric oven", "muffle furnace", "magnetic stirrer",
          "programmable box furnace"):
    st, _, _ = op(e)
    ck(f"« {e} » accepte", st.get("equipment") == e)

print("\n=== 3. ce qui n'est NI l'un NI l'autre est refuse ===")
st, r, rb = op("room temperature")
ck("« room temperature » n'entre PAS dans le graphe", "equipment" not in st)
ck("le motif est explicite",
   any("ni contenant ni appareil" in x for x in rb.rejections))
ck("l'appel reste PARTIEL, pas rejete", r.get("partial") is True)

st, _, _ = op("ethanol")
ck("« ethanol » (present dans la source) est refuse", "equipment" not in st)

print("\n=== 4. non-regression : l'ancrage source reste exige ===")
st, _, rb = op("platinum boat")   # un contenant, mais ABSENT de cette source
ck("un contenant absent du texte est toujours refuse", "equipment" not in st)
ck("le motif distingue les deux causes",
   any("absent du texte source" in x for x in rb.rejections))

print("\n=== 5. non-regression : les autres champs passent ===")
rb = RouteBuilder(source_text=SRC, target="x", method_type="y")
rb.add_operation("heating", "Powders were placed in a platinum crucible covered "
                 "with a lid and heated in a programmable box furnace.",
                 equipment="platinum crucible")
ck("l'etape est bien creee", len(rb.operations) == 1)
ck("le creuset est conserve",
   rb.operations[0].get("equipment") == "platinum crucible")

print(f"\n{ok} OK / {fail} ECHECS")
sys.exit(1 if fail else 0)
