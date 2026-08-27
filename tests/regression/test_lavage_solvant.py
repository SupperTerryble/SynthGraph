"""Le champ `solvent` d'un lavage ne doit contenir QUE le solvant.

Mesure offline du 21/08 sur `_recover_washing_details` — defaut PREEXISTANT,
non introduit par les correctifs de cette nuit :

    « washed with ethanol three times and dried »
        -> solvent = "ethanol three times"
    « washed with deionized water twice before drying »
        -> solvent = "deionized water twice be"      (tronque en plein mot)
    « washed IN methanol BY seven cycles of centrifugation »   (selfondu_cosi)
        -> NI solvant NI repetitions

Le motif capturait jusqu'a un delimiteur (`for|to|then|and dried|,.;`) ; ni
« three times », ni « twice », ni « before drying » n'en sont, donc ils etaient
avales. Les REPETITIONS, elles, etaient bien lues (3 et 2) : seule la capture
du solvant debordait.

`solvent` est REQUIS pour un lavage au registre d'etapes. Une valeur polluee y
est pire qu'un trou declare : elle passe pour une donnee.
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


def lavage(citation):
    rb = RouteBuilder(source_text=citation, target="X", method_type="Y")
    rb.operations = [{"type": "washing", "operation": "washing", "order": 1,
                      "citation": citation}]
    rb._recover_washing_details()
    op = rb.operations[0]
    return op.get("solvent"), op.get("repetitions")


print("\n=== 1. la capture s'arrete AVANT le quantificateur ===")
s, r = lavage("The precipitate was washed with ethanol three times and dried")
ck("solvant = « ethanol »", s == "ethanol")
ck("repetitions = 3", r == 3)
s, r = lavage("washed with deionized water twice before drying")
ck("solvant = « deionized water »", s == "deionized water")
ck("repetitions = 2", r == 2)

print("\n=== 2. cas reel selfondu_cosi : « washed IN ... BY N cycles » ===")
s, r = lavage("The as-prepared mixture was washed in methanol by seven cycles "
              "of centrifugation/redispersion")
ck("solvant = « methanol »", s == "methanol")
ck("sept cycles valent sept repetitions", r == 7)

print("\n=== 3. autres tournures d'introduction ===")
s, _ = lavage("the powder was rinsed using distilled water and dried")
ck("« rinsed using »", s == "distilled water")
s, _ = lavage("washed out with acetone.")
ck("« washed out with »", s == "acetone")

print("\n=== 4. non-regression : les captures deja justes le restent ===")
s, _ = lavage("The final product was washed with ethanol and distilled water.")
ck("deux solvants cites restent entiers", s == "ethanol and distilled water")
s, _ = lavage("crystals were rinsed with 30% and 80% ethanol, followed by drying")
ck("« 30% and 80% ethanol »", s == "30% and 80% ethanol")
s, _ = lavage("washed with distilled water for 10 min")
ck("« for » delimite toujours", s == "distilled water")

print("\n=== 5. les repetitions, inchangees ===")
for cit, att in (("washed with water once", 1), ("rinsed with ethanol twice", 2),
                 ("washed with acetone thrice", 3),
                 ("washed with water four times", 4),
                 ("rinsed with ethanol 5 times", 5)):
    ck(f"« {cit[-14:]} » -> {att}", lavage(cit)[1] == att)

print("\n=== 6. REGLE D'OR : rien n'est invente ===")
s, r = lavage("the product was collected and dried under vacuum")
ck("aucun lavage cite : pas de solvant", s is None)
ck("  ni de repetitions", r is None)
s, r = lavage("washed with ethanol")
ck("un lavage sans compte ne recoit pas de repetitions", r is None)
ck("  mais son solvant est lu", s == "ethanol")
ck("citation vide", lavage("")[0] is None)

print("\n=== 7. une valeur DEJA presente n'est jamais ecrasee ===")
rb = RouteBuilder(source_text="washed with ethanol three times",
                  target="X", method_type="Y")
rb.operations = [{"type": "washing", "operation": "washing", "order": 1,
                  "citation": "washed with ethanol three times",
                  "solvent": "methanol", "repetitions": 9}]
rb._recover_washing_details()
ck("le solvant declare est conserve", rb.operations[0]["solvent"] == "methanol")
ck("les repetitions declarees aussi", rb.operations[0]["repetitions"] == 9)

print(f"\n{ok} OK / {fail} ECHECS")
sys.exit(1 if fail else 0)
