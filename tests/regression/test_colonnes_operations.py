"""Une operation non thermique a droit a sa TEMPERATURE, et a ses consignes.

DECISION DE TERRY (21/08) : « Ajouter des colonnes nommees au schema ».

Mesure du 21/08 : seules `heating`, `cooling`, `soak`, `drying`, `dissolution`
et les procedes thermiques portaient une temperature. `mixing`, `grinding`,
`ball_milling`, `electrodeposition` et `washing` la PERDAIENT au normaliseur.

Ce n'etait pas un defaut d'extraction mais de SCHEMA, et il coutait quatre
temperatures du corpus :

  electro_nico   -10 °C et 70 °C sous agitation (`mixing`), 60 °C de depot
                 (`electrodeposition`) — les trois du gold. Les 0 % affiches
                 sur ce papier etaient un artefact, pas un echec du modele.
  combu_ferrite  65 °C, « gel formation on the magnetic stirrer » (`mixing`).

Deux familles nouvelles apportent aussi des consignes que rien ne portait : le
POTENTIEL impose d'une electrodeposition (le papier montre que -1,1 / -1,2 /
-1,3 V donnent 11, 23 et 48 at% de cobalt) et la FREQUENCE d'un broyage.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from synthgraph.schemas.step_schema import (  # noqa: E402
    STEP_PARAMETERS, normalize_steps)

ok = fail = 0


def ck(label, cond):
    global ok, fail
    if cond:
        ok += 1
        print(f"  OK    {label}")
    else:
        fail += 1
        print(f"  ECHEC {label}")


def passe(step_type, **champs):
    ops = [{"type": step_type, "operation": step_type, "order": 1,
            "citation": "x", **champs}]
    n, _ = normalize_steps(ops)
    return n[0]


def temp(step_type, valeur=70.0):
    st = passe(step_type, temperature_c=valeur)
    return st.get("temperature_c", st.get("target_temperature_c"))


print("\n=== 1. les operations qui la perdaient la conservent ===")
for t in ("mixing", "grinding", "ball_milling", "electrodeposition", "washing"):
    ck(f"« {t} » garde sa temperature", temp(t) == 70.0)

print("\n=== 2. cas reels du corpus ===")
ck("electro_nico : agitation a -10 °C", temp("mixing", -10.0) == -10.0)
ck("electro_nico : agitation a 70 °C", temp("mixing", 70.0) == 70.0)
ck("electro_nico : depot a 60 °C", temp("electrodeposition", 60.0) == 60.0)
ck("combu_ferrite : gel sur agitateur a 65 °C", temp("mixing", 65.0) == 65.0)

print("\n=== 3. non-regression : les thermiques n'ont pas bouge ===")
for t in ("heating", "cooling", "soak", "drying", "dissolution", "calcination",
          "sintering", "annealing", "hydrothermal", "cvd"):
    ck(f"« {t} »", temp(t) == 70.0)

print("\n=== 4. LE POTENTIEL, consigne de l'electrodeposition ===")
# `voltage_v` EXISTAIT deja au schema : on ne cree pas de doublon.
st = passe("electrodeposition", voltage_v=-1.3, reference_electrode="Ag/Ag+")
ck("le potentiel est conserve", st.get("voltage_v") == -1.3)
ck("l'electrode de reference aussi", st.get("reference_electrode") == "Ag/Ag+")
# Sans elle le potentiel ne veut rien dire : -1,3 V/Ag/Ag+ n'est pas -1,3 V/ECS.
ck("les deux colonnes existent au schema",
   {"voltage_v", "reference_electrode"}
   <= set(STEP_PARAMETERS["electrodeposition"]["optional"])
   | set(STEP_PARAMETERS["electrodeposition"]["required"]))

print("\n=== 5. LA FREQUENCE, consigne de la mecanosynthese ===")
ck("ball_milling : 20 Hz", passe("ball_milling", frequency_hz=20).get("frequency_hz") == 20)
ck("grinding : 20 Hz", passe("grinding", frequency_hz=20).get("frequency_hz") == 20)
ck("la charge de billes existait deja",
   "ball_to_powder_ratio" in STEP_PARAMETERS["ball_milling"]["optional"])

print("\n=== 6. le schema ne s'ouvre PAS a n'importe quoi ===")
# Une colonne inconnue reste ecartee : le registre est strict, c'est ce qui
# empeche le modele d'inventer des champs.
ck("une colonne inventee n'entre pas",
   passe("mixing", couleur_du_becher="bleu").get("couleur_du_becher") is None)
# REVISE le 21/08 : j'avais decide que le fourre-tout ne porterait aucune
# temperature. La mesure l'a dementi — le 65 °C de combu_ferrite y etait, et
# etait jete. Une valeur PROUVEE par sa citation ne doit jamais disparaitre
# parce que l'etape est mal classee.
ck("« generic » conserve une valeur prouvee", temp("generic") == 70.0)
ck("  et sa duree", passe("generic", duration_h=3.0).get("duration_h") == 3.0)

print(f"\n{ok} OK / {fail} ECHECS")
sys.exit(1 if fail else 0)
