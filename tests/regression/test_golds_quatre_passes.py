"""Les golds passent les QUATRE verifications a chaque execution de la suite.

Un gold faux ne se voit pas : il fausse la mesure en silence et le pipeline est
accuse — ou absout — a tort. SEPT erreurs d'annotation ont ete commises sur ce
corpus, toutes dans le sens de l'indulgence :

  1-3. trois ATMOSPHERES inferees (« air » deduit du procede) ;
  4.   une RAMPE convertie (5 par minute ecrit 300 par heure) ;
  5.   une DUREE oubliee (5 min de dispersion, hydro_czts) ;
  6.   des MILLIMOLES dans un champ de rapport molaire (selfondu_cosi) ;
  7.   un CONTENANT infere (« becher » deduit de « vigorous stirring »,
       reduc_cu) — celle-ci prise par la passe 4 le 21/08.

Aucune n'aurait ete prise par une seule verification. Ce test refuse toute
ERREUR ; les SIGNALEMENTS, eux, demandent un jugement humain et ne font pas
echouer la suite — mais leur nombre est affiche pour qu'une derive se voie.
"""
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

r = subprocess.run(
    [sys.executable, str(ROOT / "tools" / "verifier_golds.py")],
    capture_output=True, text=True, encoding="utf-8", errors="replace",
    cwd=str(ROOT))
sortie = (r.stdout or "") + (r.stderr or "")

erreurs = [l for l in sortie.splitlines() if " ERREUR : " in l]
bilan = [l for l in sortie.splitlines() if "controles passes" in l]

for l in erreurs:
    print(f"  ECHEC {l.strip()}")
if bilan:
    print(f"  {bilan[0].strip()}")

n_ok = 0
if bilan:
    try:
        n_ok = int(bilan[0].split()[0])
    except (ValueError, IndexError):
        n_ok = 0
if not bilan:
    print("  ECHEC le verificateur n'a rendu aucun bilan")

print(f"\n{n_ok} OK / {len(erreurs) if bilan else 1} ECHECS")
sys.exit(1 if (erreurs or not bilan) else 0)
