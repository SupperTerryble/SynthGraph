"""Un compose ne peut pas etre TROUVE et EN TROP en meme temps.

Mesure du 21/08 sur `crystal` : le pipeline rend `SrCl2` la ou le gold porte
`SrCl2·6H2O`. Le comparateur affichait « precurseurs 100 % » ET « HORS GOLD :
['SrCl2'] ». Les deux ne peuvent pas etre vrais.

Cause : le predicat de correspondance existait en DEUX exemplaires qui avaient
diverge — le cote « manquants » tolerait le noyau anhydre, le cote « hors gold »
comparait les compositions, et un hydrate n'a pas la composition de son sel.
L'egalite stricte sur les precurseurs devenait inatteignable des que le modele
laisse tomber un hydrate, ce qu'il fait couramment.

Il n'y a plus qu'UN predicat. Ce test verrouille sa symetrie ET le fait qu'il
n'ait pas ete elargi au point de ne plus rien signaler : la comparaison reste
DIRECTIONNELLE (on cherche le noyau du gold dans l'ecriture du pipeline, jamais
l'inverse), sans quoi un pipeline qui n'extrait que « Sr » face a un gold
« SrCO3 » cesserait d'etre pris en defaut.
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
    "target": "Sr2IrO4",
    "precursors": [
        {"formula": "IrO2", "molar_ratio": 1, "role": "reactant"},
        {"formula": "SrCO3", "molar_ratio": 2, "role": "reactant"},
        {"formula": "SrCl2·6H2O", "molar_ratio": 7, "role": "flux"},
    ],
    "key_values": [], "durations_h": [], "ramp_rates_c_per_h": [],
    "citations": [], "atmosphere": "",
}


def mesure(formules):
    pw = [{"precursors": [{"formula": f} for f in formules],
           "synthesis_steps": []}]
    c = compare(GOLD, pw)
    return c["precursors_pct"], c["precursors_hors_gold"], c["precursors_missing"]


print("\n=== 1. cas reel : l'hydrate perdu par le modele ===")
pct, extra, miss = mesure(["IrO2", "SrCO3", "SrCl2"])
ck("les trois precurseurs sont trouves", pct == 100.0)
ck("SrCl2 n'est PAS signale en trop", extra == [])
ck("aucun manquant", miss == [])

print("\n=== 2. l'ecriture exacte du gold donne le meme verdict ===")
pct, extra, miss = mesure(["IrO2", "SrCO3", "SrCl2·6H2O"])
ck("100 % trouves", pct == 100.0)
ck("rien en trop", extra == [])

print("\n=== 3. LA GARDE TIENT : un compose FAUX reste signale ===")
pct, extra, miss = mesure(["IrO2", "SrCO3", "NaCl"])
ck("le taux chute", pct is not None and pct < 100.0)
ck("NaCl est signale en trop", extra == ["NaCl"])
ck("le flux est declare manquant", miss == ["SrCl2·6H2O"])

print("\n=== 4. DIRECTIONNEL : un fragment du gold ne suffit pas ===")
# « Sr » face a « SrCO3 » : le noyau du GOLD n'est pas dans « Sr », donc le
# pipeline est bien pris en defaut. L'inverse aurait tout absous.
pct, extra, miss = mesure(["IrO2", "Sr", "SrCl2·6H2O"])
ck("« Sr » ne passe pas pour SrCO3", "SrCO3" in miss)
ck("et il est signale en trop", "Sr" in extra)

print("\n=== 5. les equivalences deja acquises tiennent ===")
G2 = dict(GOLD, precursors=[{"formula": "Cu(CH3COO)2", "role": "reactant"}])
c = compare(G2, [{"precursors": [{"formula": "copper acetate"}],
                  "synthesis_steps": []}])
ck("« copper acetate » vaut Cu(CH3COO)2", c["precursors_pct"] == 100.0)
ck("et n'est pas en trop", c["precursors_hors_gold"] == [])

print("\n=== 6. un solvant de LAVAGE n'est jamais compte en trop ===")
c = compare(GOLD, [{"precursors": [{"formula": "IrO2"}, {"formula": "SrCO3"},
                                   {"formula": "SrCl2·6H2O"},
                                   {"formula": "C2H5OH", "usage": "lavage"}],
                    "synthesis_steps": []}])
ck("l'ethanol de lavage est ignore", c["precursors_hors_gold"] == [])

print(f"\n{ok} OK / {fail} ECHECS")
sys.exit(1 if fail else 0)
