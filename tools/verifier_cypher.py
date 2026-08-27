"""La conversion vers le graphe ne doit ni PERDRE ni INVENTER.

Un convertisseur silencieux est le pire endroit pour une perte : le JSON reste
juste, le graphe est faux, et rien ne le signale. Trois controles independants,
tous derives des DONNEES et non d'une liste ecrite a la main.

  A. COMPLETUDE   chaque precurseur et chaque etape du JSON a son noeud.
  B. NON-INVENTION chaque valeur numerique du Cypher existe dans le JSON source.
  C. COLLISION    aucun identifiant partage entre deux papiers (garde-fou N1).
  D. ATTRIBUTION  chaque valeur est portee par l'etape qui la cite.
"""
import glob
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from tools.pathways_to_cypher import convertir  # noqa: E402

erreurs = []
signalements = []


def err(msg):
    erreurs.append(msg)
    print(f"  ERREUR  {msg}")


def sig(msg):
    signalements.append(msg)
    print(f"  signal  {msg}")


def nombres(obj, acc=None):
    """Tous les nombres presents quelque part dans une structure."""
    acc = set() if acc is None else acc
    if isinstance(obj, bool):
        return acc
    if isinstance(obj, (int, float)):
        acc.add(round(float(obj), 6))
    elif isinstance(obj, dict):
        for v in obj.values():
            nombres(v, acc)
    elif isinstance(obj, list):
        for v in obj:
            nombres(v, acc)
    return acc


def main():
    fichiers = sorted(glob.glob("logs/pathways_*.json"))
    ids_par_papier = {}
    total_ctrl = 0

    for f in fichiers:
        donnees = json.loads(pathlib.Path(f).read_text(encoding="utf-8"))
        papier = donnees.get("paper") or pathlib.Path(f).stem
        voies = donnees.get("pathways") or []
        if not voies:
            continue
        bilan = convertir(f, "logs/cypher")
        requetes = bilan["parametrees"]

        # ---- A. COMPLETUDE -------------------------------------------------
        att_prec = sum(len(v.get("precursors") or []) for v in voies)
        att_ops = sum(len(v.get("synthesis_steps") or []) for v in voies)
        vus_prec = sum(1 for r in requetes if "USED_IN" in r["query"])
        vus_ops = sum(1 for r in requetes if "HAS_STEP" in r["query"])
        total_ctrl += 2
        if vus_prec != att_prec:
            err(f"{papier} : {att_prec} precurseurs attendus, {vus_prec} relies")
        if vus_ops != att_ops:
            err(f"{papier} : {att_ops} etapes attendues, {vus_ops} reliees")

        # chaque NOM de precurseur doit se retrouver dans un parametre
        textes = json.dumps([r["params"] for r in requetes], ensure_ascii=False)
        for v in voies:
            for p in v.get("precursors") or []:
                nom = (p.get("name") or p.get("formula") or "").strip()
                total_ctrl += 1
                if nom and nom not in textes:
                    err(f"{papier} : precurseur PERDU « {nom} »")

        # ---- B. NON-INVENTION ----------------------------------------------
        source = nombres(donnees)
        # `order` est engendre par la conversion : il est legitime et borne.
        legitimes = source | {float(i) for i in range(0, att_ops + 2)}
        for r in requetes:
            for cle, val in (r["params"] or {}).items():
                for n in nombres(val):
                    total_ctrl += 1
                    if n not in legitimes:
                        err(f"{papier} : valeur INVENTEE {n} sous « {cle} »")


        # ---- D. ATTRIBUTION : la bonne valeur sur la BONNE etape --------------
        # Le controle B ne voit qu'un ensemble : une valeur du bon papier mais de
        # la MAUVAISE etape y passerait. On rattache donc chaque noeud Operation
        # a son etape source par la CITATION, puis on compare valeur par valeur.
        etapes = [e for v in voies for e in (v.get("synthesis_steps") or [])]
        for r in requetes:
            props = (r["params"] or {}).get("props")
            if not (isinstance(props, dict) and "step_type" in props):
                continue
            cit = props.get("citation")
            src = [e for e in etapes if e.get("citation") == cit]
            if not src:
                sig(f"{papier} : operation sans etape source (citation absente)")
                continue
            # valeurs numeriques admises pour CETTE etape (toutes ses variantes
            # de citation confondues, plus l'ordre qui est engendre).
            adm = set()
            for e in src:
                adm |= nombres(e)
            adm |= {float(props.get("order") or 0)}
            for cle, val in props.items():
                if cle == "order":
                    continue
                for n in nombres(val):
                    total_ctrl += 1
                    if n not in adm:
                        err(f"{papier} : {n} sous « {cle} » ABSENT de son etape "
                            f"source (ordre {props.get('order')})")

        # ---- C. COLLISION ---------------------------------------------------
        ids = set()
        for r in requetes:
            for cle in ("eid", "pid", "mpid", "protocol_id", "entity_id"):
                if cle in (r["params"] or {}):
                    ids.add(str(r["params"][cle]))
        ids_par_papier[papier] = ids

        print(f"  OK      {papier:22s} {att_prec:3d} prec {att_ops:3d} etapes "
              f"{len(requetes):4d} requetes {len(ids):3d} ids")

    # collisions inter-papiers
    papiers = list(ids_par_papier)
    for i, a in enumerate(papiers):
        for b in papiers[i + 1:]:
            total_ctrl += 1
            commun = ids_par_papier[a] & ids_par_papier[b]
            if commun:
                err(f"COLLISION {a} / {b} : {sorted(commun)[:3]}")

    print(f"\n{total_ctrl} controles | {len(erreurs)} erreurs | "
          f"{len(signalements)} signalements")
    return 1 if erreurs else 0


if __name__ == "__main__":
    sys.exit(main())
