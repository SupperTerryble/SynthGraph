"""Le CABLAGE entre les couches tient-il ? (aucun modele charge)

Les autres suites testent les MECANISMES en appelant `RouteBuilder`
directement. Aucune ne testait la chaine reelle
`compare_tc_gold` -> `extract_all_samples` -> `extract_with_tools` -> `RouteBuilder`.

Consequence, le 20/08 : `full_text` insere AU MILIEU d'une signature
positionnelle a fait atterrir `method_type` dessus. Les 24 suites passaient au
vert et le run des iridates est mort sur un TypeError apres 20 minutes de GPU.
Ce test vaut quelques millisecondes.
"""
import inspect
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from synthgraph.agents import extractor_toolcalling as ext  # noqa: E402
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


print("\n=== 1. l'ordre des parametres POSITIONNELS est stable ===")
# Le comparateur appelle : extract_all_samples(llm, texte, target, method_type, ...)
attendu = ["llm", "source_text", "target", "method_type"]
reel = list(inspect.signature(ext.extract_all_samples).parameters)[:4]
ck(f"extract_all_samples commence par {attendu}", reel == attendu)

attendu2 = ["llm", "source_text", "target", "method_type"]
reel2 = list(inspect.signature(ext.extract_with_tools).parameters)[:4]
ck(f"extract_with_tools commence par {attendu2}", reel2 == attendu2)

print("\n=== 2. les parametres ajoutes sont en FIN de signature ===")
for f, nom in ((ext.extract_all_samples, "extract_all_samples"),
               (ext.extract_with_tools, "extract_with_tools")):
    params = list(inspect.signature(f).parameters)
    ck(f"{nom} : `full_text` present", "full_text" in params)
    ck(f"  et apres les parametres historiques",
       params.index("full_text") >= 4)

print("\n=== 3. le RouteBuilder accepte ce que l'extracteur lui passe ===")
p = inspect.signature(RouteBuilder.__init__).parameters
ck("RouteBuilder accepte `full_text`", "full_text" in p)
ck("  en parametre nomme optionnel", p["full_text"].default == "")

print("\n=== 4. l'appel du comparateur est valide (sans charger de modele) ===")
# On reproduit l'appel EXACT du comparateur avec un llm factice : il doit
# echouer sur le modele, jamais sur la signature.
src = inspect.getsource(ext.extract_all_samples)
ck("extract_all_samples transmet full_text a extract_with_tools",
   "full_text=" in src)

try:
    ext.extract_all_samples(None, "texte court", "cible", "methode",
                            route_id="r", full_text="texte complet")
    passe = True
except TypeError as e:
    passe = "argument" not in str(e).lower()
except Exception:
    passe = True          # toute autre erreur = la signature a ete acceptee
ck("l'appel du comparateur ne leve aucun TypeError de signature", passe)

print(f"\n{ok} OK / {fail} ECHECS")
sys.exit(1 if fail else 0)
