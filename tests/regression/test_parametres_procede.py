"""Frequence de broyage et potentiel de depot, depuis la citation.

Colonnes ajoutees au registre le 21/08 sur decision de Terry, mais que RIEN ne
remplissait — une colonne inatteignable ne vaut pas mieux qu'une colonne
absente. Recuperation DETERMINISTE, comme la concentration et le pH : deux
mesures ont etabli que tout ajout a l'interface du MODELE se paie ailleurs.

CIBLE REELLE MESUREE : `selfondu_cosi` a DEUX etapes dont la citation porte
« ball-milled during 2 min at 20 Hz » (Retsch MM400). Le regime en tours/min ne
couvre pas un broyeur vibrant.

Le POTENTIEL, lui, n'a aujourd'hui aucune cible : le modele ne cree pas d'etape
d'electrodeposition sur `electro_nico`. Le mecanisme est ecrit et teste pour le
jour ou elle apparaitra, mais il ne doit PAS etre compte comme un gain.

PIEGE central, deja documente dans le gold : les potentiels -0,50 / -0,59 /
-0,94 V du papier sont releves en VOLTAMMETRIE CYCLIQUE — de la caracterisation,
pas des consignes. D'ou la restriction aux etapes d'electrodeposition.
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


def proc(step_type, citation, **champs):
    rb = RouteBuilder(source_text=citation, target="X", method_type="Y")
    rb.operations = [{"type": step_type, "operation": step_type, "order": 1,
                      "citation": citation, **champs}]
    rb._recover_parametres_procede()
    return rb.operations[0]


print("\n=== 1. cas reel selfondu_cosi : 20 Hz ===")
CIT = ("63.2 mg Si nanoparticles, 194.8 mg CoCl2, 2.9 g LiI and 2.1 g KI were "
       "ball-milled during 2 min at 20 Hz (Retsch MM400 ball mill airtight vial "
       "of 50 mL, filled with one steel ball of 62.3 g)")
ck("un broyage a billes recoit 20 Hz",
   proc("ball_milling", CIT).get("frequency_hz") == 20.0)
ck("un broyage au mortier aussi", proc("grinding", CIT).get("frequency_hz") == 20.0)
ck("l'origine est tracee",
   proc("ball_milling", CIT).get("frequency_hz_source") == "citation_regex")

print("\n=== 1bis. le type BRUT du modele, pas le type normalise ===")
# Defaut qui a rendu le mecanisme INERTE au premier run : le modele ecrit le
# type comme le papier — « were ball-milled », donc « ball-milling » avec un
# TRAIT D'UNION. Mes tests, eux, etaient ecrits sur les types DEJA normalises
# (« ball_milling »), et passaient donc tous. Le post-traitement s'execute AVANT
# la normalisation : il voit le brut. On passe desormais par la table SYNONYMS
# du registre, source unique de cette taxonomie.
for brut in ("ball milling", "ball-milling", "ball_milling", "milling",
             "grinding", "broyage"):
    ck(f"« {brut} » reconnu comme broyage",
       proc(brut, CIT).get("frequency_hz") == 20.0)

print("\n=== 2. GARDE : la frequence n'appartient qu'au BROYAGE ===")
ck("un chauffage ne la prend pas",
   proc("heating", "annealed at 20 Hz somewhere").get("frequency_hz") is None)
ck("un lavage non plus",
   proc("washing", "washed at 20 Hz").get("frequency_hz") is None)

print("\n=== 3. GARDE : les kHz sont une AUTRE grandeur ===")
# 40 kHz est la frequence d'un bain a ultrasons — sa propre colonne.
ck("« 40 kHz » n'entre pas en Hz",
   proc("ball_milling", "milled in a 40 kHz bath").get("frequency_hz") is None)

print("\n=== 4. PIEGES de la citation reelle ===")
# « 62.3 g », « 50 mL », « 2 min » cohabitent avec « 20 Hz » : seul le Hz compte.
st = proc("ball_milling", CIT)
ck("la masse de bille n'est pas une frequence", st.get("frequency_hz") == 20.0)
ck("aucune autre colonne n'est inventee",
   st.get("voltage_v") is None and st.get("reference_electrode") is None)

print("\n=== 5. POTENTIEL : seulement sur une electrodeposition ===")
DEP = ("the electrodeposition was carried out at -1.3 V/Ag/Ag+ during 2 hours "
       "at 60 C")
st = proc("electrodeposition", DEP)
ck("le potentiel est lu", st.get("voltage_v") == -1.3)
ck("l'electrode de reference aussi", st.get("reference_electrode") == "Ag/Ag+")
CV = ("the oxidation of Co to Co+ appears at -0.59 V/Ag/Ag+ in cyclic "
      "voltammetry")
ck("un potentiel de VOLTAMMETRIE sur une autre etape ne passe pas",
   proc("generic", CV).get("voltage_v") is None)
ck("meme sur une electrodeposition, la voltammetrie est ecartee",
   proc("electrodeposition", CV).get("voltage_v") is None)

print("\n=== 6. « vs SCE » est une autre reference ===")
st = proc("electrodeposition", "deposited at -0.8 V vs SCE for 1 h")
ck("le potentiel est lu", st.get("voltage_v") == -0.8)
ck("la reference est SCE", (st.get("reference_electrode") or "").upper() == "SCE")

print("\n=== 7. une valeur DEJA presente n'est pas ecrasee ===")
st = proc("ball_milling", CIT, frequency_hz=99.0)
ck("la frequence declaree est conservee", st.get("frequency_hz") == 99.0)

print("\n=== 8. REGLE D'OR : rien sans preuve ===")
ck("citation sans frequence",
   proc("ball_milling", "the powders were milled for 2 h").get("frequency_hz") is None)
ck("citation sans potentiel",
   proc("electrodeposition", "the film was deposited on FTO").get("voltage_v") is None)
ck("citation vide", proc("ball_milling", "").get("frequency_hz") is None)

print(f"\n{ok} OK / {fail} ECHECS")
sys.exit(1 if fail else 0)
