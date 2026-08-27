"""Une meme citation ne decrit pas deux fois la meme operation.

Defaut trouve en RELISANT le document des voies (#21), invisible aux
pourcentages. Sur `broyage_na`, le pipeline emet DEUX etapes pour un seul
geste :

    1. grinding      duration_h = 2     « These solid materials were ball-milled
                                          for 2 h to obtain Na3P particles. »
    2. ball_milling  atmosphere = Ar    meme phrase

Un chimiste lirait deux broyages successifs. Et le papier est pourtant a
l'EGALITE STRICTE COMPLETE : les durees se dedoublonnent, l'atmosphere est
juste, la mesure ne voit rien. C'est tout l'interet du document — un defaut de
STRUCTURE que la comparaison de valeurs ne peut pas montrer.

La deduplication existait deja mais s'appuyait sur le type BRUT : « grinding »
et « ball_milling » different, donc pas de fusion. On la branche sur le type
CANONIQUE (table `SYNONYMS` du registre, deja utilisee ailleurs).

CE QU'IL NE FAUT PAS CASSER : « 900°C, 24 h; 1000°C, 60 h; 1100°C, 60 h » est
UNE phrase qui decrit TROIS paliers. La fusion ne doit avoir lieu que si aucun
parametre commun ne porte une valeur DIFFERENTE — regle deja en place, qui avait
fait tomber PhysRevB de 100 % a 33 % quand elle manquait.
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


CIT = ("These solid materials were ball-milled for 2 h to obtain Na3P "
       "particles under argon.")

print("\n=== 1. cas reel broyage_na : un seul geste, une seule etape ===")
rb = RouteBuilder(source_text=CIT, target="Na3P", method_type="mecanosynthese")
rb.add_operation("grinding", CIT)
rb.add_operation("ball_milling", CIT)
etapes = rb.to_pathways_dict()["pathways"][0]["synthesis_steps"]
ck("une seule etape de broyage", len(etapes) == 1)
if etapes:
    st = etapes[0]
    ck("elle porte la duree", st.get("duration_h") == 2.0)
    ck("et l'atmosphere", (st.get("atmosphere") or "").lower() in ("ar", "argon"))

print("\n=== 2. la fusion marche dans les deux sens ===")
rb = RouteBuilder(source_text=CIT, target="Na3P", method_type="mecanosynthese")
rb.add_operation("ball-milling", CIT)
rb.add_operation("grinding", CIT)
ck("« ball-milling » puis « grinding »",
   len(rb.to_pathways_dict()["pathways"][0]["synthesis_steps"]) == 1)

print("\n=== 3. GARDE : des valeurs DIFFERENTES ne fusionnent pas ===")
# Piege reel : « 900°C, 24 h; 1000°C, 60 h; 1100°C, 60 h » est UNE phrase pour
# TROIS paliers. Les fusionner avait fait tomber PhysRevB de 100 % a 33 %.
P = "Typical heating schedules were 900 C, 24 h; 1000 C, 60 h; and 1100 C, 60 h"
rb = RouteBuilder(source_text=P, target="Sr2IrO4", method_type="ceramique")
rb.add_operation("heating", P, temperature_c=900, duration_h=24)
rb.add_operation("heating", P, temperature_c=1000, duration_h=60)
rb.add_operation("heating", P, temperature_c=1100, duration_h=60)
st = rb.to_pathways_dict()["pathways"][0]["synthesis_steps"]
temps = {s.get("target_temperature_c") or s.get("temperature_c") for s in st}
ck("les trois paliers survivent", {900.0, 1000.0, 1100.0} <= temps)

print("\n=== 4. GARDE : deux FAMILLES differentes ne fusionnent pas ===")
C2 = "the powder was ground for 1 h and then heated to 900 C for 2 h"
rb = RouteBuilder(source_text=C2, target="X", method_type="Y")
rb.add_operation("grinding", C2)
rb.add_operation("heating", C2)
ck("un broyage et un chauffage restent distincts",
   len(rb.to_pathways_dict()["pathways"][0]["synthesis_steps"]) >= 2)

print("\n=== 5. GARDE : deux citations DIFFERENTES restent deux etapes ===")
rb = RouteBuilder(source_text=CIT + " The jar was then opened in a glove box.",
                  target="Na3P", method_type="mecanosynthese")
rb.add_operation("grinding", CIT)
rb.add_operation("ball_milling", "The jar was then opened in a glove box.")
ck("deux phrases -> deux etapes",
   len(rb.to_pathways_dict()["pathways"][0]["synthesis_steps"]) == 2)

print(f"\n{ok} OK / {fail} ECHECS")
sys.exit(1 if fail else 0)
