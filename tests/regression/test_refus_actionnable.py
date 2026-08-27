"""Le message de REFUS doit permettre au modele de se corriger au tour suivant.

Cas reel de cvd_mos2 (run corpus9, 20/08) : le modele a cite

    « the furnace was FIRST heated to 300 °C for 10 min and held for
      additional 10 min »

la ou le papier ecrit « FIRSTLY ». Un mot d'ecart sur quinze. La citation a ete
refusee deux fois, l'etape n'est jamais entree, et le palier a 300 °C — l'un des
deux paliers du four — a ete perdu. Le modele visait pourtant la bonne phrase.

AUCUN garde-fou n'est assoupli : la citation doit toujours etre EXACTE, et les
valeurs restent validees contre elle. On rend simplement au modele la phrase du
texte dont il s'est le plus approche, pour qu'il la recopie. Le message de refus
est sa seule prise — le projet a deja etabli que c'est la piece maitresse.

Le seuil de recouvrement est la garde de ce mecanisme : suggerer une phrase au
hasard orienterait le modele vers une citation sans rapport avec son intention.
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


SRC = ("Within a typical CVD process, the furnace was firstly heated to 300 C "
       "for 10 min and held for additional 10 min, and then heated to 750 C in "
       "40 min and kept for next 25 min. Argon was used as the carrier gas. "
       "The total growth time lasts for about 10 min.")
rb = RouteBuilder(source_text=SRC, target="MoS2", method_type="CVD")

print("\n=== 1. cas reel : « first » pour « firstly » ===")
msg = rb._check_citation("the furnace was first heated to 300 C for 10 min "
                         "and held for additional 10 min")
ck("la citation reste REFUSEE", msg is not None and "REFUSE" in msg)
ck("le refus cite la phrase du texte", "firstly" in (msg or ""))
ck("il demande de la recopier exactement", "EXACTEMENT" in (msg or ""))

print("\n=== 2. une citation EXACTE passe toujours ===")
ck("phrase copiee mot pour mot",
   rb._check_citation("the furnace was firstly heated to 300 C for 10 min") is None)
ck("autre phrase du texte",
   rb._check_citation("Argon was used as the carrier gas") is None)

print("\n=== 3. GARDE : une citation HORS SUJET n'obtient aucune suggestion ===")
# Sans seuil, on suggererait une phrase au hasard et on orienterait le modele
# vers une citation sans rapport avec ce qu'il voulait dire.
msg2 = rb._check_citation("the cat sat on the mat with a hat and a bat today")
ck("elle est refusee", msg2 is not None and "REFUSE" in msg2)
ck("sans phrase suggeree", "recopie-la" not in (msg2 or ""))

print("\n=== 4. GARDE : une citation trop courte ne suggere rien non plus ===")
msg3 = rb._check_citation("heated")
ck("refus pour longueur", msg3 is not None and "courte" in msg3)
ck("sans suggestion", "recopie-la" not in (msg3 or ""))

print("\n=== 5. le refus n'ouvre AUCUNE porte : rien n'est enregistre ===")
rb2 = RouteBuilder(source_text=SRC, target="MoS2", method_type="CVD")
r = rb2.add_operation("heating", "the furnace was first heated to 300 C for "
                                 "10 min and held for additional 10 min",
                      temperature_c=300)
ck("l'operation est refusee", r.get("ok") is not True)
ck("aucune etape enregistree", not rb2.operations)
ck("la tentative est tracee",
   any("citation absente" in x for x in rb2.rejections))

print("\n=== 6. fail-safe ===")
ck("citation vide", rb._check_citation("") is not None)
ck("source vide : aucune suggestion inventee",
   "recopie-la" not in (RouteBuilder(source_text="", target="X", method_type="Y")
                        ._check_citation("une phrase quelconque de longueur suffisante") or ""))

print(f"\n{ok} OK / {fail} ECHECS")
sys.exit(1 if fail else 0)
