"""Les voies extraites -> le graphe. Le maillon qui manquait.

CONSTAT du 22/08 : zero fichier .cypher dans tout l'arbre V5_TC. L'extraction
tool-calling produit des `logs/pathways_*.json` que RIEN ne convertit. Le
constructeur existe pourtant depuis la V4.4 (`step6_graph_architect`) et
consomme exactement la forme emise par `RouteBuilder.to_pathways_dict()`.

DEUX CHOIX QUI ENGAGENT LA FIDELITE, ecrits ici pour qu'ils se voient :

1. `qa_status = QA_SKIPPED`, `qa_confidence = null`. Le pipeline V5_TC n'a PAS
   de QA par debat. Ecrire ACCEPT ferait passer pour valide ce qui n'a jamais
   ete juge — une confiance fabriquee est une invention comme une autre.

2. Les voies sont GROUPEES PAR METHODE avant d'etre converties. Les dix voies de
   `crystal` sont dix echantillons d'une meme croissance en flux : elles sont
   bien des VARIANT_OF l'une de l'autre. Deux methodes differentes dans un meme
   papier ne le sont pas, et n'ont donc pas a etre reliees.
"""
import argparse
import glob
import json
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

from synthgraph.pipeline.runner import step6_graph_architect, render_cypher  # noqa: E402


def _slug(methode):
    garde = [c if (c.isalnum() or c == "_") else "_" for c in str(methode).lower()]
    return "".join(garde).strip("_")[:32] or "route"


def convertir(chemin_json, dossier_sortie):
    """Un JSON de voies -> un fichier .cypher. Rend un bilan chiffre."""
    donnees = json.loads(pathlib.Path(chemin_json).read_text(encoding="utf-8"))
    papier = donnees.get("paper") or pathlib.Path(chemin_json).stem
    voies = donnees.get("pathways") or []
    if not voies:
        return {"papier": papier, "voies": 0, "requetes": 0, "fichier": None}

    # Groupement par methode, en conservant l'ordre d'apparition.
    groupes = {}
    for v in voies:
        groupes.setdefault(str(v.get("synthesis_route") or "inconnue"), []).append(v)

    reference = {"source_file": papier, "title": papier, "doi": "N/A",
                 "authors": "Unknown", "year": None}

    requetes = []
    for idx, (methode, lot) in enumerate(groupes.items(), start=1):
        requetes += step6_graph_architect(
            extraction={"pathways": lot},
            context={}, validation=None, reference=reference, model="qwen3-8b",
            route={"route_id": f"R{idx}_{_slug(methode)}", "method_type": methode},
            missing_params=None,
            qa_status="QA_SKIPPED", qa_basis="extraction_tool_calling_v5tc",
        )

    sortie = pathlib.Path(dossier_sortie) / f"{papier}.cypher"
    lignes = [f"// {papier} — {len(voies)} voie(s), {len(groupes)} methode(s)",
              "// genere par tools/pathways_to_cypher.py — qa_status=QA_SKIPPED",
              ""]
    for r in requetes:
        lignes.append(render_cypher(r["query"], r["params"]))
    sortie.write_text("\n".join(lignes) + "\n", encoding="utf-8")

    return {"papier": papier, "voies": len(voies), "methodes": len(groupes),
            "requetes": len(requetes), "fichier": str(sortie),
            "parametrees": requetes}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--entree", default="logs/pathways_*.json")
    ap.add_argument("--sortie", default="logs/cypher")
    args = ap.parse_args()

    pathlib.Path(args.sortie).mkdir(parents=True, exist_ok=True)
    fichiers = sorted(glob.glob(args.entree))
    if not fichiers:
        print(f"aucun fichier pour {args.entree}")
        return 1

    total_r = total_v = 0
    for f in fichiers:
        b = convertir(f, args.sortie)
        total_r += b["requetes"]
        total_v += b["voies"]
        print(f"  {b['papier']:20s} {b['voies']:3d} voie(s) "
              f"{b.get('methodes', 0):2d} methode(s) -> {b['requetes']:4d} requetes")
    print(f"\n{len(fichiers)} papiers | {total_v} voies | {total_r} requetes "
          f"| ecrit dans {args.sortie}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
