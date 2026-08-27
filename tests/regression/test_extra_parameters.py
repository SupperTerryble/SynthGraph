"""Le champ LIBRE obeit a la regle d'or comme tous les autres.

Choix de Terry (20/08) : plutot que de promouvoir des colonnes nommees, ouvrir
`extra_parameters` a l'outil `add_operation` et laisser le modele declarer ce
que le papier porte. La mesure du corpus le justifie — le pH n'apparait que sur
2 papiers sur 8 mais y decide la phase obtenue, et aucune liste anticipee pour
un projet ne sur des iridates ne l'aurait contenu.

Le risque est evident : un champ libre serait la porte d'entree que tous les
autres garde-fous interdisent. Chaque valeur doit donc figurer dans la citation,
exactement comme une temperature.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from synthgraph.extraction.graph_tools import RouteBuilder, TOOL_SCHEMAS  # noqa: E402

ok = fail = 0


def ck(label, cond):
    global ok, fail
    if cond:
        ok += 1
        print(f"  OK    {label}")
    else:
        fail += 1
        print(f"  ECHEC {label}")


CIT = ("In order to adjust the pH value of the solution to 10, 2 mL of 8 % HCl "
       "were added, and the bath remained for 3 hours at 50 C.")


def run(extra, citation=CIT):
    rb = RouteBuilder(source_text=citation, target="MnSe", method_type="CBD")
    r = rb.add_operation("soak", citation, extra_parameters=extra)
    return rb.operations[0] if rb.operations else None, r, rb


print("\n=== 1. cas reel cbd_mnse : le pH du bain ===")
st, r, _ = run({"pH": "10"})
ck("le pH est conserve", (st or {}).get("extra_parameters", {}).get("pH") == "10")

print("\n=== 2. REGLE D'OR : une valeur absente de la citation est ecartee ===")
st, r, rb = run({"pH": "7"})
ck("un pH de 7 (absent) n'entre pas", "extra_parameters" not in (st or {}))
ck("le rejet est trace", any("absent de la citation" in x for x in rb.rejections))
ck("l'appel reste PARTIEL, pas rejete", r.get("partial") is True)

print("\n=== 3. tri au sein du meme appel ===")
st, _, _ = run({"pH": "10", "vitesse": "9999 rpm"})
gardes = (st or {}).get("extra_parameters", {})
ck("le pH prouve est garde", gardes.get("pH") == "10")
ck("la vitesse inventee est ecartee", "vitesse" not in gardes)

print("\n=== 4. valeurs non chiffrees : comparaison textuelle ===")
st, _, _ = run({"milieu": "8 % HCl"})
ck("« 8 % HCl » present dans la citation est garde",
   (st or {}).get("extra_parameters", {}).get("milieu") == "8 % HCl")
st, _, _ = run({"milieu": "acide nitrique"})
ck("un milieu absent est ecarte", "extra_parameters" not in (st or {}))

print("\n=== 5. entrees vides ignorees, sans faire echouer l'appel ===")
st, r, _ = run({"pH": "", "": "10"})
ck("l'etape est creee malgre tout", st is not None)
ck("aucun parametre vide enregistre", "extra_parameters" not in (st or {}))

print("\n=== 6. exposition au modele, pilotee par interrupteur ===")
# Le champ est RETIRE de l'interface par defaut depuis le 20/08 : sa mesure a
# degrade 4 papiers sur 7. La VALIDATION reste active pour qu'il puisse revenir
# sans perdre la regle d'or. `SYNTHGRAPH_EXTRA_PARAMS=1` le reexpose.
import os  # noqa: E402
op = next(t["function"] for t in TOOL_SCHEMAS if t["function"]["name"] == "add_operation")
props = op["parameters"]["properties"]
arme = os.environ.get("SYNTHGRAPH_EXTRA_PARAMS") == "1"
ck(f"exposition conforme a l'interrupteur (arme={arme})",
   ("extra_parameters" in props) == arme)
ck("  il n'est jamais REQUIS", "extra_parameters" not in op["parameters"]["required"])
ck("  la validation reste active quel que soit l'etat",
   run({"pH": "10"})[0].get("extra_parameters", {}).get("pH") == "10")

print("\n=== 7. non-regression : les champs connus passent toujours ===")
rb = RouteBuilder(source_text=CIT, target="MnSe", method_type="CBD")
rb.add_operation("soak", CIT, temperature_c=50, duration_h=3,
                 extra_parameters={"pH": "10"})
st = rb.operations[0]
ck("la temperature est conservee",
   st.get("target_temperature_c") == 50.0 or st.get("temperature_c") == 50.0)
ck("la duree est conservee", st.get("duration_h") == 3.0)
ck("le pH est conserve", st.get("extra_parameters", {}).get("pH") == "10")

print(f"\n{ok} OK / {fail} ECHECS")
sys.exit(1 if fail else 0)
