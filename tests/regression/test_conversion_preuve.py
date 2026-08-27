"""Le modele ne doit pas etre PUNI d'avoir bien converti.

Incoherence mesuree : la citation dit « heated to 750 °C in 40 min », le modele
declare `duration_h = 0.6667` — la conversion EXACTE — et le garde-fou la
refuse, parce que « 0.6667 » n'est pas ecrit. Une ligne plus bas, le
post-traitement `_DUREE_RE` lit « 40 min » et ecrit... 0.6667.

Le pipeline refusait donc au modele la valeur qu'il calcule lui-meme. Un modele
qui fait le travail correctement etait puni ; un modele qui laisse le champ vide
etait rattrape.

PORTEE MESUREE AVANT D'ECRIRE : 9 refus de ce type sur 5 papiers (cvd_mos2 x5,
prepara x2, hydro_czts, cbd_mnse). Ce n'est pas un cas isole — contrairement aux
pistes a 1 ou 2 cas ecartees le meme jour.

REGLE D'OR INTACTE : accepter une CONVERSION n'est pas accepter une valeur
ABSENTE. La duree source doit etre ECRITE dans la citation ; seule l'unite
change. Une valeur qui ne correspond a rien reste refusee.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from synthgraph.extraction.graph_tools import _num_in  # noqa: E402

ok = fail = 0


def ck(label, cond):
    global ok, fail
    if cond:
        ok += 1
        print(f"  OK    {label}")
    else:
        fail += 1
        print(f"  ECHEC {label}")


print("\n=== 1. cas reels du corpus : la conversion est acceptee ===")
for v, cit, quoi in (
        (0.6667, "the furnace was heated to 750 °C in 40 min", "40 min (cvd_mos2)"),
        (0.4167, "and kept for next 25 min", "25 min (cvd_mos2)"),
        (0.0333, "reaching 180 °C in 2 min", "2 min (cvd_mos2)"),
        (0.25, "a pure product being obtained upon heating for 15 min.", "15 min (prepara)"),
        (0.0833, "dispersed in 20 ml of deionized water for 5 min", "5 min (hydro_czts)"),
        (0.5, "with vigorous stirring for 30 min", "30 min (cbd_mnse)")):
    ck(f"{quoi} prouve {v} h", _num_in(v, cit, "duration_h"))

print("\n=== 2. l'ecriture DIRECTE marche toujours ===")
ck("« for 2 h » prouve 2 h", _num_in(2, "held at 900 C for 2 h", "duration_h"))
ck("« 24h dwell » prouve 24 h", _num_in(24, "1300 C (24h dwell)", "duration_h"))
ck("« 60 h » prouve 60 h", _num_in(60, "1000 C, 60 h", "duration_h"))

print("\n=== 3. REGLE D'OR : une valeur ABSENTE reste refusee ===")
ck("7 h n'est prouve par aucune duree",
   not _num_in(7, "the furnace was heated to 750 °C in 40 min", "duration_h"))
ck("0.5 h n'est pas prouve par « 40 min »",
   not _num_in(0.5, "heated to 750 °C in 40 min", "duration_h"))
ck("une citation sans duree ne prouve rien",
   not _num_in(2, "the powder was ground in a mortar", "duration_h"))

print("\n=== 4. les UNITES restent cloisonnees ===")
# Acquis du meme jour : « 20 Hz » ne prouve pas 20 °C, « 23 mm » non plus.
ck("« 20 Hz » ne prouve pas 20 °C",
   not _num_in(20, "ball-milled at 20 Hz", "temperature_c"))
ck("« 62.3 g » ne prouve pas 62,3 °C",
   not _num_in(62.3, "one steel ball of 62.3 g", "temperature_c"))
ck("« 40 min » ne prouve pas 40 °C",
   not _num_in(40, "heated in 40 min", "temperature_c"))

print("\n=== 5. les secondes aussi ===")
ck("« for 90 s » prouve 0,025 h", _num_in(0.025, "sonicated for 90 s", "duration_h"))

print("\n=== 6. tolerance d'ARRONDI, pas d'a-peu-pres ===")
ck("0.6667 accepte pour 40 min", _num_in(0.6667, "in 40 min", "duration_h"))
ck("0.67 accepte aussi (meme arrondi)", _num_in(0.67, "in 40 min", "duration_h"))
ck("0.7 REFUSE : ce n'est plus 40 min", not _num_in(0.7, "in 40 min", "duration_h"))

print(f"\n{ok} OK / {fail} ECHECS")
sys.exit(1 if fail else 0)
