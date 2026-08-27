"""Une variante VUE mais non extraite doit etre DECLAREE, pas tue.

Mesure du 21/08 sur `selfondu_cosi` : le modele retient 300 °C d'une phrase qui
en enonce DEUX — « pre-heated to the reaction temperature 300 and 400 °C for
core-shell and homogenous nanoparticles, RESPECTIVELY ». Ce n'est pas une
invention (le 300 est reel, bien attache a sa phrase) : c'est une recette
PARTIELLE presentee comme complete. Plus insidieux qu'une valeur fausse — un
chimiste croit qu'il n'y a qu'une synthese.

MESURE AVANT DECISION : 9 phrases du corpus portent une unite partagee, mais une
SEULE est operatoire avec « respectively ». Les quatre de `broyage_na` sont des
plages de cyclage de batterie. Scinder les voies — changement de representation,
avec le piege des trois pH de `cbd_mnse` en embuscade — ne se justifie pas pour
un cas. On DECLARE le trou, ce qui est la reponse du projet a tout ce qui
manque : une recette partielle SILENCIEUSE est un trou cache.

PIEGE A NE PAS ROUVRIR : « adjust the pH to 10, 9, 8 » n'a ni « respectively »
ni produit nomme en face de chaque valeur — l'abstention y est correcte, et
aucune declaration n'a lieu.
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


def voie(citation, **champs):
    """Voie complete : on lit les trous la ou le projet les assemble."""
    rb = RouteBuilder(source_text=citation, target="CoSi", method_type="sels fondus")
    rb.add_operation("heating", citation, **champs)
    return rb.to_pathways_dict()["pathways"][0]


def variantes(pw):
    return [m for m in pw.get("missing_parameters", [])
            if "variante" in str(m.get("parameter", ""))]


CAS = ("A vertical furnace was pre-heated to the reaction temperature 300 and "
       "400 °C for core-shell and homogenous nanoparticles, respectively.")

print("\n=== 1. cas reel selfondu_cosi ===")
pw = voie(CAS, temperature_c=300)
v = variantes(pw)
ck("un trou de variante est declare", len(v) == 1)
if v:
    ck("il nomme la valeur NON extraite", "400" in str(v[0]))
    ck("il est RECOMMANDE, pas requis", v[0].get("severity") == "recommended")
    ck("il pointe l'etape", v[0].get("step_order") is not None)

print("\n=== 2. la valeur retenue reste intacte ===")
st = pw["synthesis_steps"][0]
ck("300 °C n'est pas efface",
   (st.get("temperature_c") or st.get("target_temperature_c")) == 300.0)

print("\n=== 3. GARDE : sans « respectively », rien n'est declare ===")
PH = ("In order to adjust the pH value of the solution to 10, 9, 8; 2, 4 and "
      "8 mL of 8 % HCl were added to the solutions.")
ck("les trois pH de cbd_mnse ne declarent rien", not variantes(voie(PH)))
CYC = "The cells were tested electrochemically between 1.5 and 4.3 V."
ck("une plage de cyclage non plus", not variantes(voie(CYC)))

print("\n=== 4. GARDE : si le modele n'a RIEN retenu, rien a declarer ===")
ck("aucune valeur sur l'etape", not variantes(voie(CAS)))

print("\n=== 5. GARDE : une valeur ETRANGERE a l'enumeration ne compte pas ===")
ck("750 °C ne vient pas de « 300 and 400 »",
   not variantes(voie(CAS, temperature_c=750)))

print("\n=== 6. fail-safe ===")
ck("citation sans enumeration",
   not variantes(voie("the sample was heated at 300 °C for 2 h", temperature_c=300)))

print(f"\n{ok} OK / {fail} ECHECS")
sys.exit(1 if fail else 0)
