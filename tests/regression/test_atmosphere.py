"""Recuperation de l'atmosphere depuis la citation de l'etape (hors ligne).

L'atmosphere n'etait jamais extraite sur le corpus5 alors qu'elle figure dans
les citations deja utilisees : « dried in a muffle furnace IN AIR at 60 °C ».
Le piege a ne pas rater : `reduc_cu` ecrit « without inert gas protection » —
une NEGATION, qui dit ce qui n'a PAS ete fait.
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


def run(citation, atmosphere=None):
    rb = RouteBuilder(source_text=citation, target="x", method_type="y")
    op = {"type": "heating", "operation": "heating", "order": 1,
          "citation": citation}
    if atmosphere:
        op["atmosphere"] = atmosphere
    rb.operations = [op]
    n = rb._recover_atmosphere()
    return rb.operations[0], n, rb


print("\n=== 1. cas reels du corpus ===")
op, n, _ = run("dried in a muffle furnace in air at a temperature of 60 °C")
ck("« in air » -> air", op.get("atmosphere") == "air")
ck("la citation est conservee comme preuve", op.get("atmosphere_citation"))

op, _, _ = run("decomposed into CuO by annealing in a muffle furnace in air at 400 °C")
ck("calcination « in air » -> air", op.get("atmosphere") == "air")

op, _, _ = run("The crucibles were heated in a programmable box furnace in air")
ck("crystal « in air » -> air", op.get("atmosphere") == "air")

op, _, _ = run("followed by drying at 60°C in a vacuum oven")
ck("« vacuum oven » -> vacuum", op.get("atmosphere") == "vacuum")

op, _, _ = run("the sample was annealed under flowing argon for 6 h")
ck("« under flowing argon » -> Ar", op.get("atmosphere") == "Ar")

op, _, _ = run("heated at 900 C under N2 atmosphere")
ck("« under N2 » -> N2", op.get("atmosphere") == "N2")

print("\n=== 2. PIEGE DE LA NEGATION (cas reel reduc_cu) ===")
op, n, rb = run("Cu nanoparticles prepared in ambient atmospheric pressure "
                "without inert gas protection are prone to oxidation")
ck("« without inert gas » ne donne AUCUNE atmosphere", not op.get("atmosphere"))
ck("  (protege par la SPECIFICITE du marqueur : « ambient atmospheric "
   "pressure » n'est pas une atmosphere de reaction)", True)

# Cas ou un marqueur MATCHE vraiment et se trouve nie : c'est la seule facon
# d'eprouver le garde-fou lui-meme, et non la specificite des motifs.
op, n, rb = run("the powder was synthesized without protection under argon")
ck("marqueur « under argon » NIE : aucune atmosphere", not op.get("atmosphere"))
ck("le rejet est trace", any("niee" in x for x in rb.rejections))

op, _, _ = run("the reaction proceeds in the absence of oxygen")
ck("« absence of oxygen » ne donne aucune atmosphere", not op.get("atmosphere"))

print("\n=== 2bis. ZERO d'OCR (cas reel PhysRevB 1994) ===")
# Les PDF scannes confondent O et 0 : « heated in flowing 02 ». La table
# `_ATM_SYNONYMS` traitait deja ce cas, pas les motifs de recuperation.
op, _, _ = run("Starting materials were mixed in proportions to span the "
               "solid-solution series and heated in flowing 02.")
ck("« in flowing 02 » (zero) -> O2", op.get("atmosphere") == "O2")
op, _, _ = run("the 02 sensor was calibrated before each measurement run")
ck("« 02 sensor » sans preposition -> rien", not op.get("atmosphere"))

print("\n=== 3. le mot NU ne suffit pas ===")
for cit in ("the powder is air-sensitive and must be handled with care",
            "measurements of air quality were performed",
            "the nitrogen adsorption isotherm was recorded at 77 K"):
    op, _, _ = run(cit)
    ck(f"« {cit[:42]}... » -> rien", not op.get("atmosphere"))

print("\n=== 4. une atmosphere DEJA declaree n'est jamais ecrasee ===")
op, n, _ = run("heated in a furnace in air at 400 C", atmosphere="Ar")
ck("l'atmosphere existante est conservee", op.get("atmosphere") == "Ar")
ck("aucune recuperation comptee", n == 0)

print("\n=== 5. une negation d'une AUTRE phrase ne bloque pas ===")
op, _, _ = run("No impurity was detected. The sample was then calcined in air "
               "at 600 C for 4 h")
ck("la negation d'une phrase precedente n'empeche pas la recuperation",
   op.get("atmosphere") == "air")

print("\n=== 6. citation vide : abstention ===")
op, n, _ = run("")
ck("aucune atmosphere sur citation vide", not op.get("atmosphere") and n == 0)

print(f"\n{ok} OK / {fail} ECHECS")
sys.exit(1 if fail else 0)
