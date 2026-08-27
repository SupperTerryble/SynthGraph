"""Un solvant porte par l'ETAPE compte comme extrait.

Mesure du 21/08 sur `selfondu_cosi` : le gold attend `CH3OH` (methanol) et la
mesure le declarait MANQUANT — precurseurs 80 %. Or le pipeline l'avait bien
capture : l'etape de lavage porte `solvent='methanol'` avec 7 repetitions.

L'information etait la ; c'est la MESURE qui ne la voyait pas. Meme angle mort
que l'asymetrie `SrCl2` corrigee plus tot : un compose etait compte TROUVE et
EN TROP simultanement parce que deux predicats avaient diverge.

Le partage est DELIBERE dans ce projet : `_recover_solvents` exclut les phrases
de lavage (il vise le solvant de REACTION), et le solvant de lavage vit sur
l'etape. Le gold, lui, liste ce qu'un chimiste releve — et un chimiste note le
methanol. La mesure doit donc regarder AUX DEUX ENDROITS.

GARDE : seul un precurseur de role « solvent » peut etre satisfait ainsi. Sans
cela le solvant d'un lavage crediterait un REACTIF manquant, et la mesure
absoudrait une extraction incomplete.
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


GOLD = {
    "target": "CoSi",
    "precursors": [
        {"formula": "Si", "role": "reactant"},
        {"formula": "CoCl2", "role": "reactant"},
        {"formula": "CH3OH", "role": "solvent"},
    ],
    "key_values": [], "durations_h": [], "ramp_rates_c_per_h": [],
    "citations": [], "atmosphere": "",
}


def mesure(precurseurs, etapes):
    pw = [{"precursors": [{"formula": f, "role": r} for f, r in precurseurs],
           "synthesis_steps": etapes}]
    c = compare(GOLD, pw)
    return c["precursors_pct"], c["precursors_missing"]


LAVAGE = [{"type": "washing", "operation": "washing", "order": 1,
           "citation": "washed in methanol by seven cycles",
           "solvent": "methanol", "repetitions": 7}]

print("\n=== 1. cas reel selfondu_cosi ===")
pct, manque = mesure([("Si", "reactant"), ("CoCl2", "reactant")], LAVAGE)
ck("le methanol de l'etape est credite", "CH3OH" not in manque)
ck("les trois precurseurs sont comptes", pct == 100.0)

print("\n=== 2. le nom en toutes lettres suffit ===")
# L'etape porte « methanol », le gold porte CH3OH : meme equivalence que
# partout ailleurs dans le projet.
pct, _ = mesure([("Si", "reactant"), ("CoCl2", "reactant")],
                [dict(LAVAGE[0], solvent="CH3OH")])
ck("la formule aussi", pct == 100.0)

print("\n=== 3. GARDE : un REACTIF ne se satisfait pas d'un solvant d'etape ===")
G2 = dict(GOLD, precursors=[{"formula": "Si", "role": "reactant"},
                            {"formula": "CH3OH", "role": "reactant"}])
c = compare(G2, [{"precursors": [{"formula": "Si"}], "synthesis_steps": LAVAGE}])
ck("le methanol reste MANQUANT s'il est declare reactant",
   "CH3OH" in c["precursors_missing"])

print("\n=== 4. GARDE : sans etape de lavage, rien n'est credite ===")
pct, manque = mesure([("Si", "reactant"), ("CoCl2", "reactant")], [])
ck("le methanol manque", "CH3OH" in manque)
pct, manque = mesure([("Si", "reactant"), ("CoCl2", "reactant")],
                     [dict(LAVAGE[0], solvent=None)])
ck("une etape sans solvant ne credite rien", "CH3OH" in manque)

print("\n=== 5. GARDE : un solvant DIFFERENT ne credite pas ===")
pct, manque = mesure([("Si", "reactant"), ("CoCl2", "reactant")],
                     [dict(LAVAGE[0], solvent="ethanol")])
ck("l'ethanol ne vaut pas le methanol", "CH3OH" in manque)

print("\n=== 6. non-regression : le precurseur declare reste prioritaire ===")
pct, manque = mesure([("Si", "reactant"), ("CoCl2", "reactant"),
                      ("CH3OH", "solvent")], LAVAGE)
ck("100 % quand il est aussi precurseur", pct == 100.0)
ck("et il n'est pas compte en trop",
   not compare(GOLD, [{"precursors": [{"formula": "Si"}, {"formula": "CoCl2"},
                                      {"formula": "CH3OH"}],
                       "synthesis_steps": LAVAGE}])["precursors_hors_gold"])

print(f"\n{ok} OK / {fail} ECHECS")
sys.exit(1 if fail else 0)
