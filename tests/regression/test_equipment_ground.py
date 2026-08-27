"""Le contenant doit exister dans le TEXTE SOURCE.

Cas reel : apres durcissement du prompt (« creuset de platine, autoclave, bombe
de digestion, becher »), le modele a inscrit `equipment='becher'` sur
`hydro_czts` — papier ANGLAIS qui dit « acid digestion bomb ». Le mot vient du
PROMPT, pas du papier : fuite d'exemple, mode d'echec deja documente dans le
CLAUDE.md du projet.
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
       "The hydrothermal synthesis was conducted at 170 to 190 C for 6 to 16 h "
       "in an electric oven.")
CIT = "the obtained solution was transferred to an acid digestion bomb (50 ml)."


def op(equip):
    rb = RouteBuilder(source_text=SRC, target="CZTS", method_type="hydrothermale")
    r = rb.add_operation("heating", CIT, equipment=equip)
    return rb, r


print("\n=== 1. le contenant REEL du papier est conserve ===")
rb, _ = op("acid digestion bomb")
ck("« acid digestion bomb » accepte",
   rb.operations[0].get("equipment") == "acid digestion bomb")

rb, _ = op("electric oven")
ck("« electric oven » accepte (present ailleurs dans la source)",
   rb.operations[0].get("equipment") == "electric oven")

print("\n=== 2. REGLE D'OR : le mot venu du PROMPT est refuse ===")
for mot in ("bécher", "becher", "creuset de platine", "autoclave"):
    rb, r = op(mot)
    ck(f"« {mot} » n'entre pas dans le graphe",
       "equipment" not in rb.operations[0])

rb, r = op("bécher")
ck("le motif est explicite", any("absent du texte source" in x for x in rb.rejections))
ck("l'appel est signale PARTIEL", r.get("partial") is True)

print("\n=== 3. non-regression : les autres champs passent toujours ===")
rb, _ = op("acid digestion bomb")
CIT2 = ("The hydrothermal synthesis was conducted at 170 to 190 C for 6 to 16 h "
        "in an electric oven.")
rb2 = RouteBuilder(source_text=SRC, target="CZTS", method_type="h")
rb2.add_operation("heating", CIT2, temperature_c=170, equipment="electric oven")
st = rb2.operations[0]
ck("la temperature prouvee est conservee",
   st.get("target_temperature_c") == 170.0 or st.get("temperature_c") == 170.0)
ck("le contenant prouve est conserve", st.get("equipment") == "electric oven")

print(f"\n{ok} OK / {fail} ECHECS")
sys.exit(1 if fail else 0)
