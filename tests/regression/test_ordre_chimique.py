"""Une recette commence par la PREPARATION, jamais par le four.

Trouve par l'audit de REFAISABILITE, pas par la comparaison au gold : `crystal`
obtient 100 % en precurseurs, ratios et durees, et pourtant ses dix voies sont
INEXECUTABLES — elles commencent par « heating » et placent en DERNIER
« Powders of IrO2, SrCO3 and SrCl2 · 6H2O were thoroughly mixed and placed in a
platinum crucible ». On melange les poudres AVANT de les enfourner.

Cause : l'ordre suit la lecture du papier, et le modele a cite la ligne du
TABLEAU (le programme thermique) avant la phrase des Methods.

Effet de bord mesure : l'atmosphere « in air », portee par cette etape de
melange placee en dernier, ne propageait vers RIEN — la propagation ne va que
vers l'avant. D'ou 8 atmospheres manquantes sur ce seul papier.

MESURE AVANT D'ECRIRE : 12 voies sur 3 papiers (les 10 de `crystal`, plus
`cbd_mnse` et `prepara`) commencent par une etape thermique avec leur
preparation en dernier.

PIEGE A NE PAS ROUVRIR : `physrev` decrit « 900°C, 24 h; 1000°C, 60 h; 1100°C,
60 h, with many INTERMEDIATE grindings ». Un broyage entre deux paliers est
REEL et doit rester ou il est. La regle ne deplace donc QU'UNE etape, et
seulement quand AUCUNE preparation ne precede le premier traitement thermique.
Sur `prepara` (`heating, grinding, heating, cooling, mixing`), le broyage
intermediaire ne bouge pas ; seul le melange final remonte.
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


def sequence(paires, source=""):
    rb = RouteBuilder(source_text=source or " ".join(c for _, c in paires),
                      target="Sr2IrO4", method_type="flux")
    for typ, cit in paires:
        rb.add_operation(typ, cit)
    st = rb.to_pathways_dict()["pathways"][0]["synthesis_steps"]
    return [(s.get("type") or "").lower() for s in
            sorted(st, key=lambda x: x.get("order") or 0)]


MELANGE = ("Powders of IrO2, SrCO3, and SrCl2 · 6H2O were thoroughly mixed and "
           "placed in a platinum crucible covered with a lid.")
CHAUFFE = "Sr214#1 1 : 2 : 7 1300 C to 900 C then to room temperature"
SEPAR = "After cooling, crystals were separated from the residual flux by rinsing"

print("\n=== 1. cas reel crystal : le melange remonte en tete ===")
seq = sequence([("heating", CHAUFFE), ("separation", SEPAR), ("mixing", MELANGE)])
ck("la preparation est PREMIERE", seq and seq[0] == "mixing")
ck("la separation reste APRES le chauffage",
   "separation" in seq and seq.index("separation") > seq.index("heating"))

print("\n=== 2. PIEGE : un broyage INTERMEDIAIRE ne bouge pas ===")
# physrev : « with many intermediate grindings » entre les paliers.
P1 = "Typical heating schedules were 900 C, 24 h with many intermediate grindings"
P2 = "then 1000 C, 60 h with many intermediate grindings"
seq = sequence([("mixing", "Starting materials SrCO3, IrO2 and RuO2 were mixed"),
                ("heating", P1), ("grinding", P2), ("heating", P2)])
ck("le melange reste premier", seq[0] == "mixing")
ck("le broyage reste ENTRE les deux paliers",
   seq.count("heating") == 2 and 0 < seq.index("grinding") < len(seq) - 1)

print("\n=== 3. une sequence DEJA correcte n'est pas touchee ===")
seq = sequence([("mixing", MELANGE), ("heating", CHAUFFE), ("separation", SEPAR)])
ck("l'ordre est conserve", seq == ["mixing", "heating", "separation"])

print("\n=== 4. une seule etape est deplacee ===")
seq = sequence([("heating", CHAUFFE), ("grinding", "the powder was reground"),
                ("mixing", MELANGE)])
ck("le melange remonte", seq[0] == "mixing")
ck("le rebroyage reste apres le chauffage",
   seq.index("grinding") > seq.index("heating"))

print("\n=== 5. sans etape thermique, rien ne bouge ===")
seq = sequence([("grinding", "the solids were ball-milled for 2 h"),
                ("washing", "washed with ethanol")])
ck("sequence inchangee", seq == ["grinding", "washing"])

print("\n=== 6. l'ATMOSPHERE peut alors se propager ===")
# C'est l'effet de bord qui coutait 8 atmospheres a `crystal` : portee par la
# derniere etape, elle ne propageait vers rien.
AIR = ("Powders were thoroughly mixed and placed in a platinum crucible, then "
       "heated in a programmable box furnace in air.")
CHAUF = "Sr214#1 1300 C to 900 C"
# La source doit porter LES DEUX citations, sinon le chauffage est refuse a
# juste titre et le test ne mesure rien.
rb = RouteBuilder(source_text=AIR + " " + CHAUF, target="Sr2IrO4",
                  method_type="flux")
rb.add_operation("heating", CHAUF)
rb.add_operation("mixing", AIR)
st = rb.to_pathways_dict()["pathways"][0]["synthesis_steps"]
par = {(s.get("type") or "").lower(): s.get("atmosphere") for s in st}
ck("le melange porte l'air", par.get("mixing") == "air")
ck("le chauffage en herite", par.get("heating") == "air")

print(f"\n{ok} OK / {fail} ECHECS")
sys.exit(1 if fail else 0)
