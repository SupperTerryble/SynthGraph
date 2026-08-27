"""Une valeur prouvee par une AUTRE phrase compte comme prouvee.

Toutes les valeurs ne sont pas justifiees par la citation principale de leur
etape. Le projet a deja `atmosphere_citation` pour ce cas ; s'y sont ajoutes
`condition_citation` (la condition retenue : l'etape cite la PLAGE, l'optimum
vient d'ailleurs) et `vessel_citation`.

Le 20/08, le controle de tracabilite ne regardait que `citation` : l'ajout de
la condition optimale a fait tomber `hydro_czts` de 100 % a 71,4 % sur des
valeurs POURTANT prouvees. La metrique accusait une extraction correcte — et
c'est la metrique non negociable du projet.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from tools.compare_tc_gold import compare  # noqa: E402

ok = fail = 0


def ck(label, cond):
    global ok, fail
    if cond:
        ok += 1
        print(f"  OK    {label}")
    else:
        fail += 1
        print(f"  ECHEC {label}")


GOLD = {"precursors": [{"formula": "CuCl2", "molar_ratio": None}],
        "key_values": [180], "durations_h": [12], "ramp_rates_c_per_h": [],
        "atmosphere": "air", "thermal_sequences": []}


def voie(step):
    return [{"precursors": [], "synthesis_steps": [step]}]


print("\n=== 1. cas reel : l'optimum prouve par condition_citation ===")
st = {"type": "heating", "order": 1,
      "citation": "conducted at 170 to 190 C for 6 to 16 h",
      "target_temperature_c": 180.0, "duration_h": 12.0,
      "condition_citation": "Pure kesterite has been synthesized at 180 C for 12 h"}
c = compare(GOLD, voie(st))
ck("les 2 valeurs sont comptees prouvees",
   c["values_proved_by_citation_pct"] == 100.0)

print("\n=== 2. la meme etape SANS la citation annexe ===")
st2 = dict(st)
del st2["condition_citation"]
c = compare(GOLD, voie(st2))
ck("sans preuve, la tracabilite chute",
   c["values_proved_by_citation_pct"] < 100.0)

print("\n=== 3. citation annexe rangee dans other_parameters ===")
st3 = {"type": "heating", "order": 1,
       "citation": "conducted at 170 to 190 C for 6 to 16 h",
       "target_temperature_c": 180.0, "duration_h": 12.0,
       "other_parameters": {
           "condition_citation": "Pure kesterite synthesized at 180 C for 12 h"}}
c = compare(GOLD, voie(st3))
ck("la preuve y est trouvee aussi",
   c["values_proved_by_citation_pct"] == 100.0)

print("\n=== 4. REGLE D'OR : une valeur ABSENTE de toute citation reste non prouvee ===")
st4 = {"type": "heating", "order": 1,
       "citation": "conducted at 170 to 190 C for 6 to 16 h",
       "target_temperature_c": 999.0,
       "condition_citation": "Pure kesterite has been synthesized at 180 C for 12 h"}
c = compare(GOLD, voie(st4))
ck("999 n'est prouve par aucune des deux phrases",
   c["values_proved_by_citation_pct"] == 0.0)

print("\n=== 5. l'atmosphere garde son dispositif d'origine ===")
st5 = {"type": "heating", "order": 1, "citation": "heated for 12 h",
       "target_temperature_c": 180.0, "atmosphere": "air",
       "atmosphere_citation": "The crucibles were heated in air at 180 C"}
c = compare(GOLD, voie(st5))
ck("la temperature prouvee par atmosphere_citation compte",
   c["values_proved_by_citation_pct"] == 100.0)

print(f"\n{ok} OK / {fail} ECHECS")
sys.exit(1 if fail else 0)
