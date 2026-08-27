"""UN geste ne doit pas devenir TROIS etapes.

`combu_ferrite` sort trois calcinations (600 C, 4 h) citant la meme phrase : un
chimiste lisant ce graphe calcinerait 12 h au lieu de 4. La metrique ne peut pas
le voir — le gold n'enregistre pas de liste d'etapes, seulement des valeurs, et
une calcination triplee fournit trois fois les memes.

Les cas sont charges depuis `logs/pathways_*.json`, pas fabriques : neuf des
quatorze etapes qui partagent une citation sont CORRECTES, et c'est contre
elles que la regle doit tenir.
"""
import glob
import json
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


# Les `logs/pathways_*.json` sont ECRASES a chaque run : un test qui en depend
# se met a mentir des la mesure suivante. Le mien l'a fait — trois assertions
# tombees parce qu'un run avait remplace les artefacts sous ses pieds. On lit
# donc l'ARCHIVE, figee, exactement comme le CLAUDE.md le demande.
ARCHIVE = "logs/baseline_20260822"


def voies(nom):
    for rep in (ARCHIVE, "logs"):
        f = pathlib.Path(rep) / f"pathways_Qwen3_{nom}.json"
        if f.exists():
            return json.loads(f.read_text(encoding="utf-8"))["pathways"]
    return None


def apres_fusion(etapes):
    """Rejoue la fusion sur des etapes REELLES et rend la liste restante."""
    rb = RouteBuilder(source_text="", target="X", method_type="Y")
    rb.operations = [dict(e) for e in etapes]
    rb._fusionner_gestes_dupliques()
    return rb.operations


def types(etapes):
    return [(e.get("type") or e.get("operation") or "") for e in etapes]


print("\n=== 1. cas reel combu_ferrite : trois calcinations pour une ===")
v = voies("combu_ferrite")
if v is None:
    print("  (donnees absentes — test ignore)")
else:
    av = v[0]["synthesis_steps"]
    ap = apres_fusion(av)
    ck("les trois calcinations n'en font plus qu'une",
       types(av).count("calcination") == 3 and types(ap).count("calcination") == 1)
    ck("aucune autre etape n'est perdue", len(ap) == len(av) - 2)
    ck("la calcination gardee porte bien ses valeurs",
       any(e.get("temperature_c") == 600.0 and e.get("duration_h") == 4.0
           for e in ap if (e.get("type") or "") == "calcination"))
    ck("les ordres sont renumerotes sans trou",
       [e["order"] for e in ap] == list(range(1, len(ap) + 1)))

print("\n=== 2. PIEGE physrev : trois paliers REELS ne fusionnent pas ===")
# 900 / 1000 / 1100 C, 24 / 60 / 60 h sur la MEME citation. Le CLAUDE.md exige
# de les preserver : c'est une recette sequentielle, pas des variantes. Ce qui
# les protege n'est pas leur type — identique — mais leurs VALEURS distinctes.
v = voies("physrev")
if v is None:
    print("  (donnees absentes — test ignore)")
else:
    av = v[0]["synthesis_steps"]
    ap = apres_fusion(av)
    ck("les trois chauffages restent trois",
       types(av).count("heating") == 3 and types(ap).count("heating") == 3)
    ck("aucune etape n'est absorbee", len(ap) == len(av))
    ck("les trois temperatures survivent",
       {e.get("target_temperature_c") for e in ap
        if (e.get("type") or "") == "heating"} == {900.0, 1000.0, 1100.0})

print("\n=== 3. PIEGE crystal : chauffage ET refroidissement, meme ligne ===")
# « 1300C -> (8C/h) 900C -> RT » decrit deux gestes. Types differents : intouches.
v = voies("crystal")
if v is None:
    print("  (donnees absentes — test ignore)")
else:
    total_av = sum(len(pw["synthesis_steps"]) for pw in v)
    total_ap = sum(len(apres_fusion(pw["synthesis_steps"])) for pw in v)
    ck(f"les {total_av} etapes des 10 voies sont conservees", total_ap == total_av)

print("\n=== 4. cas reel reduc_cu : une etape generic fantome ===")
# « allowed to settle overnight » est deja contenu dans la citation du
# refroidissement, et n'affirme meme pas de quel geste il s'agit.
v = voies("reduc_cu")
if v is None:
    print("  (donnees absentes — test ignore)")
else:
    av = v[0]["synthesis_steps"]
    ap = apres_fusion(av)
    ck("le generic fantome disparait", len(ap) == len(av) - 1)
    ck("le refroidissement, lui, reste", "cooling" in types(ap))

print("\n=== 5. REGLE : une valeur PROPRE interdit l'absorption ===")
BASE = "The powder was heated at 600 C for 4 h and then cooled."
COURT = "heated at 600 C for 4 h"
ap = apres_fusion([
    {"type": "heating", "order": 1, "citation": COURT,
     "temperature_c": 600.0, "duration_h": 4.0, "atmosphere": "Ar"},
    {"type": "heating", "order": 2, "citation": BASE,
     "temperature_c": 600.0, "duration_h": 4.0},
])
ck("l'atmosphere propre a la premiere la protege", len(ap) == 2)
ap = apres_fusion([
    {"type": "heating", "order": 1, "citation": COURT,
     "temperature_c": 600.0, "duration_h": 4.0},
    {"type": "heating", "order": 2, "citation": BASE,
     "temperature_c": 600.0, "duration_h": 4.0, "atmosphere": "Ar"},
])
ck("sans valeur propre, elle est absorbee", len(ap) == 1)

print("\n=== 6. REGLE : deux citations EGALES ne s'annulent pas ===")
# Chacune est contenue dans l'autre : sans garde, les DEUX disparaitraient.
ap = apres_fusion([
    {"type": "grinding", "order": 1, "citation": "the powder was reground"},
    {"type": "grinding", "order": 2, "citation": "the powder was reground"},
])
ck("il en reste exactement une", len(ap) == 1)

print("\n=== 7. REGLE D'OR : sans citation, on ne touche a rien ===")
ap = apres_fusion([{"type": "heating", "order": 1, "citation": ""},
                   {"type": "heating", "order": 2, "citation": ""}])
ck("deux etapes sans citation sont conservees", len(ap) == 2)
ap = apres_fusion([{"type": "heating", "order": 1, "citation": "chauffe a 600 C"}])
ck("une seule etape reste une", len(ap) == 1)

print("\n=== 8. INVARIANT sur TOUT le corpus : rien n'est invente ===")
# La fusion ne doit RETIRER que des etapes, jamais changer une valeur.
total_perdu = 0
for f in sorted(glob.glob(f"{ARCHIVE}/pathways_*.json")):
    d = json.loads(pathlib.Path(f).read_text(encoding="utf-8"))
    for pw in d.get("pathways") or []:
        av = pw.get("synthesis_steps") or []
        ap = apres_fusion(av)
        total_perdu += len(av) - len(ap)
        vals_av = {json.dumps(RouteBuilder._valeurs_mesurees(e), sort_keys=True,
                              ensure_ascii=False) for e in av}
        vals_ap = {json.dumps(RouteBuilder._valeurs_mesurees(e), sort_keys=True,
                              ensure_ascii=False) for e in ap}
        ck_local = vals_ap <= vals_av
        if not ck_local:
            ck(f"{d.get('paper')} : valeur INVENTEE par la fusion", False)
ck("aucune valeur inventee sur les 12 papiers", True)
ck(f"{total_perdu} etapes absorbees sur tout le corpus", total_perdu == 3)

print(f"\n{ok} OK / {fail} ECHECS")
sys.exit(1 if fail else 0)
