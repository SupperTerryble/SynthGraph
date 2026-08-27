"""Le message d'outil ne doit compter QUE ce que le MODELE a fourni.

Mesure du 21/08, en trois temps :

  1. Trois runs strictement identiques donnent des resultats IDENTIQUES —
     le moteur est deterministe (`temperature=0.0`).
  2. Pourtant `solgel_cuo` divergeait entre deux runs a texte focalise
     identique. La cause ne pouvait donc etre que le DIALOGUE.
  3. Et en effet : le message renvoye annonce « N parametre(s) valide(s) », et
     ce N incluait les valeurs recuperees APRES COUP par les post-traitements.

Le modele lisait donc un compte gonfle — « 4 parametre(s) valide(s) » alors
qu'il n'en avait fourni AUCUN — et pire, le compte DESCENDAIT quand il
fournissait correctement la temperature. Message inversement informatif.

Consequence : un post-traitement deterministe, cense ne rien couter, deplacait
la trajectoire du modele au tour suivant. C'est ce qui rendait les correctifs
inattribuables d'un run a l'autre.

Le compte ne porte plus que sur les valeurs VENUES DU MODELE. Les valeurs
recuperees restent dans l'etape — elles sont juste invisibles au dialogue.
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


CIT = "the furnace was heated to 750 C in 40 min under flowing argon"


def appel(**kw):
    rb = RouteBuilder(source_text=CIT, target="X", method_type="Y")
    r = rb.add_operation("heating", CIT, **kw)
    return r, rb.operations[0]


print("\n=== 1. le modele ne fournit RIEN ===")
r, st = appel()
ck("le message annonce 0 parametre", "0 parametre" in r["message"])
ck("mais la duree est bien recuperee", st.get("duration_h") == 0.6667)
ck("et la temperature aussi", st.get("temperature_c") == 750.0)

print("\n=== 2. le modele fournit la temperature ===")
r, st = appel(temperature_c=750)
ck("le message en compte 1", "1 parametre" in r["message"])
ck("la temperature n'est PAS marquee comme recuperee",
   st.get("temperature_c_source") is None)

print("\n=== 3. le modele fournit tout ===")
# Citation en HEURES : « 40 min » ferait declarer 0.6667 h au modele, valeur
# que le garde-fou REFUSE parce qu'elle n'est pas ecrite telle quelle — alors
# que le post-traitement calcule exactement la meme. Incoherence reelle,
# distincte de la neutralite testee ici (voir la tache dediee).
H = "the sample was held at 900 C for 2 h under flowing argon"
rb = RouteBuilder(source_text=H, target="X", method_type="Y")
r = rb.add_operation("heating", H, temperature_c=900, duration_h=2)
ck("le message en compte 2", "2 parametre" in r["message"])

print("\n=== 4. NEUTRALITE : le compte ne bouge pas avec les recuperations ===")
# C'est la propriete qui manquait : deux appels identiques cote MODELE doivent
# rendre le meme message, quelles que soient les valeurs recuperees derriere.
SANS = "the powder was placed in a platinum crucible"
r1, _ = appel()
r2, _ = appel()
ck("deux appels identiques -> meme message", r1["message"] == r2["message"])
rb = RouteBuilder(source_text=SANS, target="X", method_type="Y")
r3 = rb.add_operation("heating", SANS)
ck("une citation sans valeur annonce 0 aussi", "0 parametre" in r3["message"])

print("\n=== 5. les valeurs recuperees restent dans l'etape ===")
# Invisibles au dialogue, mais bien presentes dans le graphe : c'est tout
# l'interet du post-traitement.
r, st = appel()
ck("duration_h present", st.get("duration_h") is not None)
ck("son origine est tracee", st.get("duration_h_source") == "citation_regex_montee")
ck("temperature_c present", st.get("temperature_c") is not None)

print("\n=== 6. le refus partiel reste lisible ===")
rb = RouteBuilder(source_text=CIT, target="X", method_type="Y")
r = rb.add_operation("heating", CIT, temperature_c=999)
ck("une valeur non prouvee est signalee", "ECARTES" in r["message"])
ck("l'appel reste partiel", r.get("partial") is True)

print(f"\n{ok} OK / {fail} ECHECS")
sys.exit(1 if fail else 0)
