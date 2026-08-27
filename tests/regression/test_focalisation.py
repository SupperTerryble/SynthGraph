"""La focalisation ne doit pas COUPER les consignes de la methode cible.

Mesure du 21/08 : `_build_focused_text` reduit `electro_nico` de 54 301 a
8 500 caracteres (16 %) en choisissant UNE fenetre contigue autour de la
section experimentale. Or ce papier donne ses conditions de depot dans la
DISCUSSION :

    « at the same temperature (60℃), ion concentration ... and the duration of
      electrodeposition (2 hours) »
    « corresponding to a potential of -1.1, -1.2, and -1.3 V/Ag/Ag+ »

Aucune de ces phrases n'atteignait le modele. Il a extrait tout ce qu'on lui a
donne — 12 appels, 11 acceptes — puis cloture. Le defaut n'etait NI le modele NI
le prompt : son entree etait tronquee avant les valeurs.

Ce test tourne sur les TEXTES REELS du corpus, pas sur des chaines fabriquees :
c'est la seule facon de voir qu'une fenetre coupe au mauvais endroit.
"""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
ROOT = pathlib.Path(__file__).resolve().parents[2]
from tools.compare_tc_gold import focused, paper_text  # noqa: E402

ok = fail = 0


def ck(label, cond):
    global ok, fail
    if cond:
        ok += 1
        print(f"  OK    {label}")
    else:
        fail += 1
        print(f"  ECHEC {label}")


def focalise(cle, fichier):
    g = json.loads((ROOT / "data" / "gold" / fichier).read_text(encoding="utf-8"))
    for titre, gold in g.items():
        if titre.startswith("_"):
            continue
        # Le gold des iridates est indexe par TITRE (« PhysRevB.49.11890 »,
        # « Crystal growth and... ») : comparaison insensible a la casse.
        if titre == cle or cle.lower() in titre.lower():
            return focused(paper_text(cle), gold.get("target", ""),
                           gold.get("method_type", ""))
    return ""


print("\n=== 1. cas reel electro_nico : les conditions de depot ===")
foc = focalise("electro_nico", "gold_corpus9.json")
ck("le texte focalise existe", len(foc) > 1000)
# On cherche la PHRASE, jamais le nombre seul : chercher « 60 » matche « 60 % »
# et « 1960 ». C'est ainsi que j'avais conclu a tort que le texte etait complet.
ck("« temperature (60℃) » est present", "temperature (60" in foc)
ck("« -1.3 V » est present", "-1.3 V" in foc)
# PAS exige : « as shown in Figure 3b for a 1 hour deposit at 60°C » ne NOMME
# pas le procede. Relacher cette exigence ferait entrer du bruit sur les onze
# autres papiers pour un gain nul — le 60 °C arrive par la phrase precedente.
ck("le 60 °C arrive par la phrase qui nomme le procede",
   "temperature (60" in foc and "electrodeposition (2 hours)" in foc)

print("\n=== 2. le plafond de contexte est TENU ===")
ck("au plus 8500 caracteres", len(foc) <= 8500)

print("\n=== 3. NON-REGRESSION : les autres papiers gardent leur recette ===")
for cle, fichier, phrases in (
        ("hydro_czts", "gold_corpus5.json",
         ["2 mmol CuCl2", "acid digestion bomb"]),
        ("cvd_mos2", "gold_corpus9.json",
         ["heated to 750", "1 mg of MoO2"]),
        ("selfondu_cosi", "gold_corpus9.json",
         ["63.2 mg Si nanoparticles", "6 hours of thermal treatment"]),
        ("broyage_na", "gold_corpus9.json",
         ["Stoichiometric amounts of metallic sodium"]),
        ("combu_ferrite", "gold_corpus5.json", ["annealed at 200"]),
        ("cbd_mnse", "gold_corpus5.json", ["8 % HCl"]),
        ("solgel_cuo", "gold_corpus5.json",
         ["copper acetate", "ammonium carbonate"]),
        ("reduc_cu", "gold_corpus5.json", ["ascorbic acid"]),
        ("crystal", "gold_sr2iro4.json", ["platinum crucible"]),
        ("physrev", "gold_sr2iro4.json", ["SrCO3"]),
        ("prepara", "gold_sr2iro4.json", ["iridium metal powder"]),
):
    f = focalise(cle, fichier)
    ck(f"{cle} : texte focalise non vide", len(f) > 500)
    ck(f"{cle} : plafond tenu", len(f) <= 8500)
    for ph in phrases:
        ck(f"{cle} : « {ph[:30]} » conserve", ph in f)

print(f"\n{ok} OK / {fail} ECHECS")
sys.exit(1 if fail else 0)
