#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Puis-je REFAIRE la synthese au laboratoire avec ce qui a ete extrait ?

Les 9 criteres de `compare_tc_gold.py` mesurent la fidelite au gold sur les
precurseurs, les ratios et les valeurs thermiques. Un papier peut les satisfaire
a 100 % et rester INFAISABLE : `crystal` obtient 100 % partout alors que le
creuset de platine et le rincage final — sans lesquels on obtient un bloc de
SrCl2 fige et aucun cristal — n'apparaissent nulle part dans l'extraction.

Cet audit pose donc la question du chimiste, pas celle du comparateur : les six
elements ci-dessous suffisent-ils a reproduire la synthese ? Ce qui n'est pas
mesure n'est jamais corrige, d'ou cet outil separe.

Usage :
    python tools/audit_reproductibilite.py                    # les 3 iridates
    python tools/audit_reproductibilite.py --gold data/gold/gold_corpus5.json \
        --papers hydro_czts,solgel_cuo,combu_ferrite,cbd_mnse,reduc_cu
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))   # import du package depuis tools/

# Contenants : leur absence est bloquante. Un flux de SrCl2 a 1300 °C detruit un
# creuset d'alumine ; un hydrothermal sans autoclave ne monte pas en pression.
_VESSEL = re.compile(
    r"\b(platinum|alumina|al2o3|quartz|zirconia|graphite|teflon|ptfe|glassy carbon)?\s*"
    r"(crucibles?|autoclaves?|digestion bombs?|ampoules?|beakers?|boats?|vials?)\b",
    re.I)

# Le papier porte-t-il l'information ? Sert a separer un trou RATTRAPABLE
# (present dans la source, manque par le pipeline) d'un trou INCOMBLABLE (la
# source ne le donne pas). Un parametre absent de cette table n'est pas jugeable
# et compte comme rattrapable — on prefere signaler a tort que de masquer.
_PREUVE_PARAM = {
    "method": r"\b(mortar|pestle|ball[ -]mill\w*|planetary mill|magnetic stirr\w*|"
              r"ultrasonic\w*|grinder|hand[ -]ground|vortex)\b",
    "atmosphere": r"\b(?:in|under)\s+(?:an?\s+|the\s+)?(?:static\s+|flowing\s+|"
                  r"synthetic\s+|dry\s+|ambient\s+)?(air|argon|ar|n2|nitrogen|"
                  r"o2|02|oxygen|vacuum|h2|hydrogen)\b",
    "solvent": r"\b(dissolved|dispersed|suspended)\s+in\b|\bsolvent\b",
    "repetitions": r"\b(twice|three times|thrice|\d+\s*times|repeated\w*)\b",
    "speed_rpm": r"\b\d+\s*rpm\b",
    "duration_h": r"\b\d+(?:[.,]\d+)?\s*(?:h\b|hr\b|hours?\b|min\b|minutes?\b)",
    # MANQUAIT : sans motif, l'audit tombait dans « on ne sait pas juger » et
    # comptait la temperature comme PRESENTE dans le papier. Le libelle mentait
    # — 2 « actionnables » de `crystal` etaient en fait 2 non-jugeables.
    # Six ecritures du degre, comme partout dans ce corpus.
    "temperature_c": r"-?\d+(?:[.,]\d+)?\s*(?:°|˚|◦|º|')?\s*[CK]\b|\d+\s*℃",
    "target_temperature_c": r"-?\d+(?:[.,]\d+)?\s*(?:°|˚|◦|º|')?\s*[CK]\b|\d+\s*℃",
    "cooling_rate_c_per_h": r"\b\d+(?:[.,]\d+)?\s*(?:°|º|◦)?\s*C\s*/\s*(?:h|min)\b",
    "ramp_rate_c_per_h": r"\b\d+(?:[.,]\d+)?\s*(?:°|º|◦)?\s*C\s*/\s*(?:h|min)\b",
}

_NON_THERMIQUE = {
    "melange":    ("mixing", "grinding"),
    "separation": ("washing", "filtration", "separation", "centrifugation"),
    "sechage":    ("drying",),
}


def _steps(pw: dict) -> list[dict]:
    return pw.get("synthesis_steps", []) or []


def audit(key: str, gold: dict, data: dict, source: str) -> dict:
    pws = data.get("pathways", []) or []
    steps = [st for pw in pws for st in _steps(pw)]
    precs = [p for pw in pws for p in pw.get("precursors", []) or []]
    types = {(st.get("type") or "").lower() for st in steps}

    manques: list[str] = []

    # 1. tous les reactifs du gold
    # Comparer les CHAINES fait echouer « L-cysteine » face a « C3H7NO2S » : on
    # aligne l'audit sur la composition elementaire, comme le validateur et le
    # comparateur. Sans cela l'audit crie au reactif manquant sur une extraction
    # correcte, et ses alertes deviennent inexploitables.
    from synthgraph.extraction.graph_tools import _composition_key
    got = {re.sub(r"[^a-z0-9]", "", (p.get("formula") or "").lower()) for p in precs}
    got_keys = {k for k in (_composition_key(p.get("formula") or "") for p in precs) if k}
    absents = []
    for gp in gold["precursors"]:
        f = re.sub(r"[^a-z0-9]", "", gp["formula"].lower())
        core = re.sub(r"[^a-z0-9]", "", gp["formula"].split("·")[0].lower())
        gk = _composition_key(gp["formula"])
        if (gk and gk in got_keys):
            continue
        if not any(f == x or (core and (x.startswith(core) or core.startswith(x)))
                   for x in got if x):
            absents.append(gp["formula"])
    if absents:
        manques.append(f"reactifs absents : {', '.join(absents)}")

    # 2. de quoi peser : un ratio molaire ou une quantite ecrite
    if precs and not any(p.get("molar_ratio") is not None or p.get("amount") for p in precs):
        manques.append("aucune proportion ni quantite : impossible de peser")

    # 3. sequence thermique exploitable — le normaliseur repartit la temperature
    # sur plusieurs cles (`target_`, `max_`, `min_`, ou `temperature_c` nu) :
    # n'en regarder qu'une declarait « aucune temperature » a tort.
    _T = ("target_temperature_c", "temperature_c", "max_temperature_c",
          "min_temperature_c")
    if not any(st.get(k) is not None for st in steps for k in _T):
        manques.append("aucune temperature")
    if not any(st.get("duration_h") is not None for st in steps):
        manques.append("aucune duree de palier")

    # 4. atmosphere — reclamer ce que le PAPIER ne dit pas est une fausse alerte.
    # Trois golds du corpus5 portaient une atmosphere INFEREE (« air » deduit du
    # procede) ; corriges le 20/08, ils declarent desormais l'absence de mention.
    # Le pipeline a raison de s'abstenir : deviner violerait la regle d'or.
    _ATM_INCONNUE = ("non precisee", "non précisée", "autogene", "autogène",
                     "inconnue", "not stated")
    atm_gold = (gold.get("atmosphere") or "").lower()
    if not any(st.get("atmosphere") for st in steps):
        if not any(m in atm_gold for m in _ATM_INCONNUE):
            manques.append("atmosphere jamais precisee")

    # 5. contenant — depuis le 20/08 il est attribue OPERATION PAR OPERATION
    # dans le champ `vessel` (avec `vessel_citation` comme preuve). On regarde
    # les deux : `equipment` reste rempli quand le modele l'a lui-meme cite.
    # `vessel_name` survit dans `other_parameters` (voir graph_tools) ; on
    # regarde aussi `equipment`, rempli quand le modele cite lui-meme l'objet.
    vessel_extrait = any(
        st.get("vessel_name") or (st.get("other_parameters") or {}).get("vessel_name")
        or _VESSEL.search(str(st.get("equipment") or ""))
        for st in steps)
    # Retenir la mention la PLUS SPECIFIQUE : « platinum crucible » plutot que
    # « vial », sinon l'outil signale un contenant anodin croise plus tot dans
    # le texte et masque celui qui compte reellement. Bornes de mots exigees :
    # sans elles, « Vial » matchait dans « VialTweeter », un sonicateur de
    # marque, et l'audit reclamait un contenant que le papier n'a pas.
    # Le contenant doit RECEVOIR la matiere : sans verbe de transfert, l'audit
    # reclamait le « glass vial » ou `reduc_cu` STOCKE ses nanoparticules apres
    # synthese. On reutilise le detecteur de l'extracteur pour que l'audit et le
    # pipeline jugent sur le meme critere.
    from synthgraph.extraction.graph_tools import RouteBuilder
    trouves = [" ".join(m.group(1).split())
               for m in RouteBuilder._VESSEL_TRANSFER.finditer(source)]
    vessel_source = max(trouves, key=lambda t: (len(t.split()) > 1, len(t)), default=None)
    # Distinguer les deux causes : un contenant NOMME dans le papier mais non
    # extrait est un defaut du pipeline ; un papier qui n'en nomme aucun est une
    # limite de la SOURCE, que le pipeline ne peut pas combler sans inventer.
    # Confondre les deux ferait chercher un bug la ou il n'y en a pas.
    if not vessel_extrait:
        if vessel_source:
            manques.append(f"contenant non extrait (present dans le papier : "
                           f"« {vessel_source} »)")
        else:
            manques.append("aucun contenant nomme dans le papier "
                           "(limite de la source, pas du pipeline)")

    # 6. etapes non thermiques — reprocher une etape que le PAPIER ne decrit pas
    # est une fausse alerte : `crystal` ne mentionne aucun sechage, et le gold
    # n'en exige aucun. On n'alerte que si la source en porte la trace.
    _PREUVE = {
        "melange": r"\b(mixed|mixing|ground|grinding|milled|milling)\b",
        "separation": r"\b(washed|washing|rins(?:ed|ing)|separated|filtrat|"
                      r"filter(?:ed|ing)|centrifug)\b",
        "sechage": r"\b(dried|drying)\b",
    }
    for label, cands in _NON_THERMIQUE.items():
        if types & set(cands):
            continue
        attendu = gold.get("washing") if label == "separation" else None
        if label == "separation" and attendu:
            manques.append(f"etape de {label} absente (le gold exige : {attendu})")
        elif label != "separation" and re.search(_PREUVE[label], source, re.I):
            manques.append(f"etape de {label} absente (decrite dans le papier)")

    # 7. Les TROUS REQUIS declares par le graphe lui-meme.
    # Sans ce critere, l'audit declarait `crystal` REFAISABLE pendant que le
    # graphe portait 18 trous « required » sur ce meme papier : deux definitions
    # de la reproductibilite coexistaient sans se parler. Celle du graphe fait
    # foi — c'est elle qui liste ce qu'un chimiste ne saurait pas faire.
    from collections import Counter
    # Les trous sont collectes AVEC LEUR VOIE. Chaque voie renumerote ses
    # etapes a partir de 1 : sur `crystal` et ses DIX voies, une table indexee
    # par `order` seul melangeait les citations d'une voie a l'autre, et le
    # comptage des parametres « directement actionnables » etait bati sur des
    # cles qui se telescopaient. Defaut introduit le 22/08 et trouve en
    # essayant de REJOUER le resultat — le chiffre annonce etait introuvable.
    requis = [(pw, m) for pw in pws for m in (pw.get("missing_parameters") or [])
              if m.get("severity") == "required"]
    if requis:
        # Tous les trous ne se valent pas. Certains sont RATTRAPABLES — le
        # papier porte l'information et le pipeline l'a manquee ; d'autres sont
        # INCOMBLABLES — la source ne la donne pas, et aucune amelioration ne
        # les fermera. Six papiers sur huit ne nomment AUCUNE methode de
        # melange : sans cette distinction, on chasserait un bug inexistant.
        rattrapables, incomblables, ailleurs = Counter(), Counter(), Counter()
        nonjugeables = Counter()
        cit_par_voie = {id(pw): {st.get("order"): (st.get("citation") or "")
                                 for st in _steps(pw)} for pw in pws}
        for pw_m, m in requis:
            p = m["parameter"]
            if p == "vessel":
                # Le contenant a deja son detecteur, qui exige un verbe de
                # transfert. S'en remettre a la table generique le classait
                # « rattrapable » sur des papiers ou l'audit venait pourtant de
                # dire qu'aucun contenant n'est nomme : deux verdicts opposes
                # dans le meme rapport.
                (rattrapables if vessel_source else incomblables)[p] += 1
                continue
            motif = _PREUVE_PARAM.get(p)
            if motif is None:
                # Ne PAS compter comme rattrapable : l'absence de motif est une
                # limite de l'AUDIT, pas un constat sur le papier. Un defaut par
                # defaut ne doit jamais se faire passer pour un resultat.
                nonjugeables[p] += 1
            elif re.search(motif, source, re.I):
                # DEUX GRANULARITES. Chercher le motif dans TOUT le papier
                # surestime le rattrapable : la table de `crystal` porte
                # « 24h dwell » pour CERTAINS echantillons, ce qui faisait
                # classer rattrapables les durees de `Sr214#1`, dont la ligne
                # n'en porte AUCUNE. Mesure du 22/08 : les 8 parametres juges
                # rattrapables n'avaient RIEN dans la citation de leur propre
                # etape — l'audit envoyait chasser des fantomes.
                # On distingue donc ce qui est DIRECTEMENT actionnable (la
                # citation de l'etape le porte) de ce qui demanderait un
                # mecanisme inter-phrases (l'atmosphere et la condition
                # optimale sont legitimement prouvees ailleurs).
                cit_etape = cit_par_voie.get(id(pw_m), {}).get(
                    m.get("step_order"), "")
                if re.search(motif, cit_etape, re.I):
                    rattrapables[p] += 1
                else:
                    ailleurs[p] += 1
            else:
                incomblables[p] += 1
        if rattrapables:
            d = ", ".join(f"{p} x{n}" for p, n in rattrapables.most_common(5))
            manques.append(f"{sum(rattrapables.values())} parametre(s) REQUIS "
                           f"manquant(s), presents dans le papier : {d}")
        if nonjugeables:
            d = ", ".join(f"{p} x{n}" for p, n in nonjugeables.most_common(5))
            manques.append(f"{sum(nonjugeables.values())} parametre(s) REQUIS "
                           f"que l'audit NE SAIT PAS juger : {d} "
                           f"(ajouter un motif a _PREUVE_PARAM)")
        if ailleurs:
            d = ", ".join(f"{p} x{n}" for p, n in ailleurs.most_common(5))
            manques.append(f"{sum(ailleurs.values())} parametre(s) REQUIS "
                           f"presents AILLEURS dans le papier mais pas dans la "
                           f"citation de l'etape : {d} "
                           f"(demande un mecanisme inter-phrases)")
        if incomblables:
            d = ", ".join(f"{p} x{n}" for p, n in incomblables.most_common(5))
            manques.append(f"{sum(incomblables.values())} parametre(s) REQUIS "
                           f"que le PAPIER ne donne pas : {d} "
                           f"(limite de la source)")

    return {"voies": len(pws), "etapes": len(steps), "types": sorted(types),
            "trous_requis": len(requis),
            "manques": manques, "refaisable": not manques}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gold", type=Path, default=ROOT / "data" / "gold" / "gold_sr2iro4.json")
    ap.add_argument("--papers", default="crystal,physrev,prepara")
    ap.add_argument("--model", default="Qwen3")
    a = ap.parse_args()

    gold_all = json.loads(a.gold.read_text(encoding="utf-8"))
    # le gold des iridates est indexe par TITRE, celui du corpus5 par cle
    TITRES = {
        "crystal": "Crystal growth and intrinsic magnetic behaviour of Sr2IrO4",
        "physrev": "PhysRevB.49.11890",
        "prepara": "the-preparation-of-a-strontium-iridium-oxide-sr2iro41-2 (1)",
    }

    rapport = {}
    for key in [k.strip() for k in a.papers.split(",")]:
        gold = gold_all.get(TITRES.get(key, key))
        pw_file = ROOT / "logs" / f"pathways_{a.model}_{key}.json"
        if not gold or not pw_file.exists():
            print(f"\n### {key} — donnees absentes")
            continue
        source = (ROOT / "logs" / f"odl_{key}.txt")
        source = source.read_text(encoding="utf-8") if source.exists() else ""
        r = audit(key, gold, json.loads(pw_file.read_text(encoding="utf-8")), source)
        rapport[key] = r

        verdict = "REFAISABLE" if r["refaisable"] else "NON REFAISABLE"
        print(f"\n### {key} — {verdict}")
        print(f"    {r['voies']} voie(s), {r['etapes']} etape(s), types : {', '.join(r['types']) or 'aucun'}")
        for m in r["manques"]:
            print(f"    - {m}")

    out = ROOT / "logs" / f"audit_reproductibilite_{a.gold.stem}.json"
    out.write_text(json.dumps(rapport, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\necrit : {out.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
