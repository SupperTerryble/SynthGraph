"""Une valeur doit etre prouvee AVEC SON UNITE, pas par un nombre qui traine.

DEFAUT LE PLUS GRAVE trouve le 21/08 : le controle anti-invention n'examinait
que le NOMBRE. Sur une citation reelle de `selfondu_cosi` — « ball-milled during
2 min at 20 Hz (Retsch MM400, one steel ball of 62.3 g with a diameter of
23 mm) » :

    temperature_c = 20    ACCEPTE, prouve par « 20 Hz »
    temperature_c = 23    ACCEPTE, prouve par « 23 mm »
    temperature_c = 62.3  ACCEPTE, prouve par « 62.3 g »

Ce n'est pas theorique : le run du 21/08 a pose « 20 °C » sur un broyage a
partir de « 20 Hz ». Un diametre de bille prouvait une temperature. C'est la
REGLE D'OR du projet qui etait franchie.

FAISABILITE MESUREE AVANT D'ECRIRE : sur les 74 valeurs retenues des 12 papiers,
60 portaient deja une unite compatible. Les 14 autres n'etaient pas des valeurs
sans unite — c'etait le motif de mesure qui etait trop etroit. Ce test couvre
CHACUNE de ces ecritures reelles, parce qu'un durcissement qui les refuserait
casserait des extractions justes.
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


def retenu(citation, **champs):
    rb = RouteBuilder(source_text=citation, target="X", method_type="Y")
    rb.add_operation("heating", citation, **champs)
    if not rb.operations:
        return None
    st = rb.operations[0]
    for k in champs:
        return st.get(k, st.get("target_temperature_c"))
    return None


BROYAGE = ("the mixture was ball-milled during 2 min at 20 Hz (Retsch MM400, "
           "one steel ball of 62.3 g with a diameter of 23 mm)")

print("\n=== 1. LE DEFAUT : un nombre d'une AUTRE grandeur ne prouve rien ===")
ck("« 20 Hz » ne prouve pas 20 °C", retenu(BROYAGE, temperature_c=20) is None)
ck("« 23 mm » ne prouve pas 23 °C", retenu(BROYAGE, temperature_c=23) is None)
ck("« 62.3 g » ne prouve pas 62,3 °C", retenu(BROYAGE, temperature_c=62.3) is None)
ck("« 2 min » ne prouve pas 2 °C", retenu(BROYAGE, temperature_c=2) is None)

print("\n=== 2. les ECRITURES REELLES du corpus passent toujours ===")
for cit, v, quoi in (
        ("Sr214#1 1 : 2 : 7 1300◦C → (8◦C/h) 900◦C → RT", 1300, "◦C (anneau)"),
        ("Typical heating schedules were 900'C, 24 h; 1000'C, 60 h", 900, "'C (apostrophe OCR)"),
        ("obtained readily by the reaction at 1200° in air", 1200, "° sans le C"),
        ("heated at 180 ℃ for 12 h", 180, "℃ (caractere unique)"),
        ("The bath remained for 3 hours at 50 ºC", 50, "ºC (ordinal)"),
        ("calcined at 900 C in air", 900, "C (degre perdu)"),
        ("the furnace was heated to 750 °C in 40 min", 750, "°C standard")):
    ck(f"{quoi} -> {v}", retenu(cit, temperature_c=v) == float(v))

print("\n=== 3. les DUREES, y compris collees ===")
ck("« 24h dwell » (sans espace)",
   retenu("Sr214#3 1300◦C (24h dwell) → (8◦C/h) 1100◦C", duration_h=24) == 24.0)
ck("« for 2 h »", retenu("held at 900 C for 2 h", duration_h=2) == 2.0)
ck("« 60 h »", retenu("1000'C, 60 h; and 1100'C, 60 h", duration_h=60) == 60.0)

print("\n=== 4. CONVERSION acceptee — le modele n'est plus puni d'avoir bien fait ===")
# Defaut jumeau (#43) : le pipeline REFUSAIT au modele la conversion qu'il
# calcule lui-meme une ligne plus bas.
ck("« in 40 min » prouve 0,6667 h",
   retenu("the furnace was heated to 750 C in 40 min", duration_h=0.6667) == 0.6667)
ck("« for 5 min » prouve 0,0833 h",
   retenu("dispersed in water for 5 min", duration_h=0.0833) == 0.0833)
ck("« 15 min » prouve 0,25 h",
   retenu("heating for 15 min. at 1000 C", duration_h=0.25) == 0.25)

print("\n=== 5. les autres grandeurs ===")
ck("« 20 Hz » prouve bien 20 Hz",
   retenu(BROYAGE, frequency_hz=20) == 20.0)
ck("« -1.3 V/Ag/Ag+ » prouve -1,3 V",
   retenu("deposited at -1.3 V/Ag/Ag+ for 2 h", voltage_v=-1.3) == -1.3)

print("\n=== 6. REGLE D'OR : une valeur ABSENTE reste refusee ===")
ck("900 °C absent de la citation",
   retenu("the powder was ground in a mortar", temperature_c=900) is None)
ck("une duree absente", retenu("calcined at 900 C", duration_h=7) is None)
ck("citation sans aucun nombre",
   retenu("the sample was cooled naturally", temperature_c=25) is None)

print(f"\n{ok} OK / {fail} ECHECS")
sys.exit(1 if fail else 0)
