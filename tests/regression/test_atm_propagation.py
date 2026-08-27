"""Une atmosphere declaree vaut jusqu'a ce qu'une AUTRE soit nommee.

12 trous sur 5 papiers venaient de la meme cause : le marqueur existe dans le
papier mais pas dans la citation de l'etape. « The crucibles were heated in a
programmable box furnace IN AIR » vaut pour la chauffe ET le refroidissement.

LIMITE A NE PAS FRANCHIR : on ne propage pas les temperatures par ce moyen.
Chaque palier a la sienne, et propager inventerait des valeurs fausses.
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


def build(ops):
    rb = RouteBuilder(source_text="x", target="t", method_type="m")
    rb.operations = [dict(o) for o in ops]
    rb._propager_atmosphere()
    return sorted(rb.operations, key=lambda o: o["order"])


print("\n=== 1. cas reel crystal : l'air couvre le refroidissement ===")
r = build([
    {"type": "heating", "order": 1, "atmosphere": "air",
     "citation": "The crucibles were heated in a programmable box furnace in air"},
    {"type": "cooling", "order": 2, "citation": "cooled to 900 C at 8 C/h"},
])
ck("le refroidissement herite de l'air", r[1].get("atmosphere") == "air")
ck("  la preuve est conservee", r[1].get("atmosphere_citation"))
ck("  la propagation est tracee", r[1].get("atmosphere_source") == "propagee")

print("\n=== 2. propagation vers l'AVANT seulement ===")
r = build([
    {"type": "mixing", "order": 1, "citation": "powders were mixed"},
    {"type": "heating", "order": 2, "atmosphere": "air", "citation": "heated in air"},
])
ck("l'etape ANTERIEURE ne recoit rien", not r[0].get("atmosphere"))

print("\n=== 3. une nouvelle atmosphere remplace la precedente ===")
r = build([
    {"type": "heating", "order": 1, "atmosphere": "air", "citation": "heated in air"},
    {"type": "soak", "order": 2, "citation": "held for 12 h"},
    {"type": "heating", "order": 3, "atmosphere": "Ar", "citation": "heated under argon"},
    {"type": "cooling", "order": 4, "citation": "cooled to RT"},
])
ck("l'etape 2 herite de l'air", r[1].get("atmosphere") == "air")
ck("l'etape 4 herite de l'argon, pas de l'air", r[3].get("atmosphere") == "Ar")

print("\n=== 4. un LAVAGE rompt la continuite ===")
# Le produit quitte le four : l'atmosphere ne le suit pas.
r = build([
    {"type": "heating", "order": 1, "atmosphere": "air", "citation": "heated in air"},
    {"type": "washing", "order": 2, "citation": "washed with water"},
    {"type": "drying", "order": 3, "citation": "dried at 60 C"},
])
ck("le lavage ne recoit pas l'atmosphere", not r[1].get("atmosphere"))
ck("le sechage APRES lavage non plus", not r[2].get("atmosphere"))

print("\n=== 5. une atmosphere DEJA prouvee n'est jamais ecrasee ===")
r = build([
    {"type": "heating", "order": 1, "atmosphere": "air", "citation": "heated in air"},
    {"type": "heating", "order": 2, "atmosphere": "O2", "citation": "heated in flowing 02"},
])
ck("l'etape 2 garde son O2", r[1].get("atmosphere") == "O2")
ck("  et n'est pas marquee propagee", r[1].get("atmosphere_source") is None)

print("\n=== 6. sans atmosphere initiale, rien n'est cree ===")
r = build([
    {"type": "heating", "order": 1, "citation": "heated to 900 C"},
    {"type": "cooling", "order": 2, "citation": "cooled to RT"},
])
ck("aucune atmosphere inventee",
   not any(o.get("atmosphere") for o in r))

print("\n=== 7. LIMITE : les temperatures ne sont JAMAIS propagees ===")
r = build([
    {"type": "heating", "order": 1, "atmosphere": "air",
     "target_temperature_c": 1300, "citation": "heated in air at 1300 C"},
    {"type": "cooling", "order": 2, "citation": "cooled slowly"},
])
ck("l'atmosphere se propage", r[1].get("atmosphere") == "air")
ck("la TEMPERATURE ne se propage pas",
   r[1].get("target_temperature_c") is None)

print(f"\n{ok} OK / {fail} ECHECS")
sys.exit(1 if fail else 0)
