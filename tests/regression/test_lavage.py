"""Solvant et repetitions d'un lavage, recuperes de SA propre citation.

Les citations nomment le solvant — « washed with ethanol and distilled water »,
« washed with 30% and 80% ethanol » — mais le modele ne renseignait pas le champ
`solvent`, pourtant REQUIS pour un lavage. Trois etapes du corpus concernees.
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


def run(type_etape, citation):
    rb = RouteBuilder(source_text=citation, target="x", method_type="y")
    rb.operations = [{"type": type_etape, "operation": type_etape, "order": 1,
                      "citation": citation}]
    rb._recover_washing_details()
    return rb.operations[0]


print("\n=== 1. cas reels du corpus ===")
o = run("washing", "the gel precipitate was collected by centrifugation, "
                   "washed with ethanol and distilled water.")
ck("solvant recupere", o.get("solvent") == "ethanol and distilled water")

o = run("washing", "The precipitates were separated by filtration and washed "
                   "with deionized water and ethanol for three times.")
ck("solvant recupere", o.get("solvent") == "deionized water and ethanol")
ck("  « for three times » -> 3", o.get("repetitions") == 3)

o = run("washing", "The final product was filtrated and washed with 30% and "
                   "80% ethanol, followed by drying at 60C.")
ck("la CONCENTRATION est conservee", o.get("solvent") == "30% and 80% ethanol")

print("\n=== 2. sans solvant nomme : abstention ===")
o = run("separation", "The mixture is filtered before being added to the bath.")
ck("aucun solvant invente", not o.get("solvent"))

print("\n=== 3. formes de repetition ===")
for texte, attendu in (("washed with water twice.", 2),
                       ("washed with water three times.", 3),
                       ("washed with ethanol 5 times.", 5)):
    o = run("washing", texte)
    ck(f"« {texte.split('with ')[1][:22]} » -> {attendu}",
       o.get("repetitions") == attendu)

print("\n=== 4. une valeur DEJA presente n'est pas ecrasee ===")
rb = RouteBuilder(source_text="washed with ethanol.", target="x", method_type="y")
rb.operations = [{"type": "washing", "operation": "washing", "order": 1,
                  "citation": "washed with ethanol.", "solvent": "acetone",
                  "repetitions": 9}]
rb._recover_washing_details()
ck("le solvant existant est conserve", rb.operations[0]["solvent"] == "acetone")
ck("les repetitions existantes sont conservees",
   rb.operations[0]["repetitions"] == 9)

print("\n=== 5. les etapes NON concernees sont ignorees ===")
o = run("heating", "the sample was washed with ethanol before heating to 900C.")
ck("une chauffe ne recoit pas de solvant", not o.get("solvent"))

print("\n=== 6. fail-safe ===")
o = run("washing", "")
ck("citation vide : rien", not o.get("solvent") and not o.get("repetitions"))

print(f"\n{ok} OK / {fail} ECHECS")
sys.exit(1 if fail else 0)
