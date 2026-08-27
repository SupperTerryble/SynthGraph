"""L'origine d'une valeur d'etape doit survivre jusqu'a la voie finale.

Exigence de Terry, posee le 21/08 pour les ratios : « un audit doit toujours
pouvoir separer ce qui a ete LU de ce qui a ete CALCULE ». Elle etait tenue pour
les precurseurs — `ratio_source=formule_cible` figure bien dans la voie — et
PERDUE pour les etapes : le normaliseur ne conserve que les colonnes du
registre, donc `duration_h_source`, `temperature_c_source` et `frequency_hz_source`
etaient effaces en silence.

`other_parameters` fait partie des cles STRUCTURELLES preservees : les marqueurs
y sont routes, plutot que d'ajouter une colonne `_source` a chacun des
vingt-huit types d'operation.
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


def voie(paires, source):
    rb = RouteBuilder(source_text=source, target="CoSi", method_type="X")
    for typ, cit in paires:
        rb.add_operation(typ, cit)
    return rb.to_pathways_dict()["pathways"][0]["synthesis_steps"]


SRC = ("the mixture was ball-milled during 2 min at 20 Hz and then heated to "
       "750 C in 40 min and kept for next 25 min")
steps = voie([("ball-milling", "the mixture was ball-milled during 2 min at 20 Hz"),
              ("heating", "and then heated to 750 C in 40 min")], SRC)
par_type = {s.get("type"): s for s in steps}

print("\n=== 1. les valeurs recuperees portent leur origine ===")
broyage = (par_type.get("grinding") or {}).get("other_parameters") or {}
ck("la duree du broyage est tracee",
   broyage.get("duration_h_source") == "citation_regex")
ck("sa frequence aussi", broyage.get("frequency_hz_source") == "citation_regex")
chauffe = (par_type.get("heating") or {}).get("other_parameters") or {}
ck("la temperature du chauffage est tracee",
   chauffe.get("temperature_c_source") == "citation_regex")

print("\n=== 2. MONTEE et PALIER restent distinguables ===")
# « in 40 min » est un temps pour ATTEINDRE la consigne, « for 25 min » un
# palier. Les deux sont des durees ; seule l'origine les separe.
ck("une montee est marquee comme telle",
   chauffe.get("duration_h_source") == "citation_regex_montee")
s2 = voie([("heating", "and kept for next 25 min")], "and kept for next 25 min")
pal = (s2[0].get("other_parameters") or {})
ck("un palier ne l'est pas",
   pal.get("duration_h_source") == "citation_regex")

print("\n=== 3. la valeur elle-meme est bien la ===")
ck("frequence conservee", (par_type.get("grinding") or {}).get("frequency_hz") == 20.0)
ck("temperature conservee",
   (par_type.get("heating") or {}).get("target_temperature_c") == 750.0)

print("\n=== 4. une valeur DECLAREE par le modele n'est pas marquee ===")
# Sans quoi le marqueur ne distinguerait plus rien.
rb = RouteBuilder(source_text="held at 900 C for 12 h", target="X", method_type="Y")
rb.add_operation("heating", "held at 900 C for 12 h", temperature_c=900, duration_h=12)
op = rb.to_pathways_dict()["pathways"][0]["synthesis_steps"][0]
autres = op.get("other_parameters") or {}
ck("aucune origine de temperature", "temperature_c_source" not in autres)
ck("aucune origine de duree", "duration_h_source" not in autres)
ck("mais les valeurs sont la",
   op.get("target_temperature_c") == 900.0 and op.get("duration_h") == 12.0)

print("\n=== 5. les marqueurs deja presents ne sont pas ecrases ===")
ck("le contenant manquant reste signale",
   "_missing_vessel" in ((par_type.get("heating") or {}).get("other_parameters") or {}))

print(f"\n{ok} OK / {fail} ECHECS")
sys.exit(1 if fail else 0)
