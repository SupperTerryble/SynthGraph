#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tools/compare_tc_gold.py — V5_TC : extraction tool-calling COMPLÈTE vs gold

Contrairement au test de faisabilité (1 échantillon, 1 papier, mécanique seule),
ce script fait le travail réel :
  - texte de chaque papier (opendataloader, avec cache)
  - détection des échantillons décrits
  - UNE boucle agentique par échantillon (≈10 extractions pour le papier 1)
  - confrontation à `data/gold/gold_sr2iro4.json`

Mesure ce qui compte pour un chimiste : les précurseurs sont-ils tous là (le
FLUX compris, dont l'omission rend la recette irréalisable), les températures
des tableaux sont-elles récupérées, l'atmosphère est-elle juste, et les valeurs
sont-elles ADOSSÉES à une citation qui les prouve.

Usage :
    python tools/compare_tc_gold.py --model Qwen2.5-7B-Instruct-Q4_K_M.gguf
    python tools/compare_tc_gold.py --model <x>.gguf --papers crystal --table-block
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

MODELS_DIR = Path(os.environ.get("MODELS_DIR", "models"))
GOLD = ROOT / "data" / "gold" / "gold_sr2iro4.json"
PDF_DIR = ROOT / "data" / "bench_night"

PAPERS = {
    "crystal": "Crystal growth and intrinsic magnetic behaviour of Sr2IrO4",
    "physrev": "PhysRevB.49.11890",
    "prepara": "the-preparation-of-a-strontium-iridium-oxide-sr2iro41-2 (1)",
}


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())


def _variants(s: str) -> set[str]:
    """Écritures équivalentes d'un composé, formule ET nom en toutes lettres.

    Sans cela la mesure est biaisée : un modèle extrayant « strontium carbonate »
    au lieu de « SrCO3 » était compté 0 % alors que l'extraction est correcte.
    On réutilise le normaliseur déterministe de l'Étape A plutôt que d'inventer
    une table de correspondance parallèle.
    """
    out = {_norm(s)}
    if not s:
        return out
    try:
        from synthgraph.validation.deterministic import normalize_compound_name
        f = normalize_compound_name(s)
        if f:
            out.add(_norm(f))
    except Exception:  # noqa: BLE001 — la mesure ne doit jamais planter
        pass
    return {v for v in out if v}


def paper_text(key: str) -> str:
    """Texte du papier (cache si disponible — l'extraction ODL est lente)."""
    cache = ROOT / "logs" / f"odl_{key}.txt"
    if cache.exists():
        return cache.read_text(encoding="utf-8")
    pdf = next((p for p in PDF_DIR.glob("*.pdf") if key in p.stem.lower()), None)
    if not pdf:
        return ""
    from synthgraph.rag.pdf_parser import parse_pdf_for_vision
    t = parse_pdf_for_vision(str(pdf), str(ROOT / "logs" / "img_tmp"))
    cache.write_text(t, encoding="utf-8")
    return t


def focused(full: str, target: str, method: str) -> str:
    from synthgraph.pipeline.runner import _build_focused_text

    class _Rag:
        def query(self, *a, **k): return ""

    return _build_focused_text(full, _Rag(), target, method)


def compare(gold: dict, pathways: list[dict]) -> dict:
    """Confronte les voies extraites à la référence annotée."""
    got_forms, got_names = set(), set()
    got_all_raw: set[str] = set()   # écritures BRUTES, pour l'équivalence élémentaire
    temps, ramps, durations, atms = set(), set(), set(), set()
    n_cited = n_total = 0
    # Ratios molaires : SANS EUX AUCUNE SYNTHÈSE N'EST REFAISABLE. Le gold porte
    # « IrO2 : SrCO3 : SrCl2 = 1 : 2 : 7 » ; connaître les réactifs sans leurs
    # proportions ne permet pas de peser. Ils n'étaient pas vérifiés du tout.
    got_ratios: dict[str, float] = {}
    per_pathway_ratios: dict[str, dict[str, float]] = {}

    for pw in pathways:
        pw_key = str(pw.get("variant_id") or id(pw))
        for p in pw.get("precursors", []):
            got_forms |= _variants(p.get("formula"))
            got_names |= _variants(p.get("name"))
            got_all_raw |= {x for x in (p.get("formula"), p.get("name")) if x}
            if p.get("molar_ratio") is not None:
                # Ratios collectés PAR VOIE : les agréger serait faux, car un
                # papier décrit plusieurs phases aux proportions différentes
                # (Sr2IrO4 = 1:2:7, Sr3Ir2O7 = 2:3:7). Mélanger les voies
                # faisait apparaître « IrO2: 2 au lieu de 1 » alors que le
                # modèle avait attribué le bon ratio à la bonne recette.
                for v in _variants(p.get("formula")) | _variants(p.get("name")):
                    if v:
                        per_pathway_ratios.setdefault(pw_key, {})[v] = float(p["molar_ratio"])
                        got_ratios.setdefault(v, float(p["molar_ratio"]))
        for st in pw.get("synthesis_steps", []):
            # Certaines valeurs sont prouvées par une AUTRE phrase que la
            # citation principale — c'est le dispositif déjà en place pour
            # `atmosphere_citation`. La condition retenue (« Pure kesterite ...
            # à 180 °C pour 12 h ») est de celles-là : l'étape cite la PLAGE,
            # l'optimum vient d'ailleurs. Ne regarder que `citation` faisait
            # tomber la traçabilité de 100 % à 71,4 % sur des valeurs pourtant
            # prouvées — la métrique aurait accusé une extraction correcte.
            _op = st.get("other_parameters") or {}
            cit = " ".join(str(x) for x in (
                st.get("citation"), st.get("condition_citation"),
                st.get("atmosphere_citation"), _op.get("condition_citation"),
                _op.get("atmosphere_citation"), _op.get("vessel_citation"))
                if x)
            for k, v in st.items():
                if not isinstance(v, (int, float)) or isinstance(v, bool):
                    continue
                if "temperature" in k:
                    temps.add(float(v))
                elif "duration" in k:
                    durations.add(float(v))
                elif "rate" in k:
                    ramps.add(float(v))
                else:
                    continue
                # La valeur est-elle prouvée par la citation qui l'accompagne ?
                n_total += 1
                # Une durée notée « 30 min » dans le papier est stockée 0,5 h
                # après conversion déterministe : chercher « 0.5 » littéralement
                # la déclarait non prouvée alors qu'elle l'est. On accepte donc
                # aussi l'équivalent en minutes pour les durées.
                formes = [f"{float(v):g}"]
                if "duration" in k:
                    # ARRONDI : « 5 min » est stocke 5/60 = 0,08333 h, et le
                    # retour en minutes donne 4,998 — qui ne correspond plus a
                    # « 5 ». La valeur etait declaree non prouvee alors que sa
                    # citation dit « for 5 min under constant stirring ».
                    mn = float(v) * 60
                    formes.append(f"{mn:g}")
                    if abs(mn - round(mn)) < 0.01:
                        formes.append(f"{round(mn):g}")
                if any(re.search(rf"(?<![\d.]){re.escape(f)}(?![\d])", cit)
                       for f in formes):
                    n_cited += 1
            if st.get("atmosphere"):
                atms.add(str(st["atmosphere"]).lower())

    # --- précurseurs (le flux est éliminatoire) ---
    # Deux écritures d'un même corps ne se ressemblent pas toujours :
    # `Cu(C2H3O2)2` (modèle) et `Cu(CH3COO)2` (gold) désignent l'acétate de
    # cuivre. Comparer les CHAÎNES faisait échouer une extraction parfaite.
    # On compare donc aussi la composition élémentaire, comme le fait déjà le
    # validateur — c'est la mesure qui doit s'aligner sur la chimie.
    from synthgraph.extraction.graph_tools import _composition_key
    got_keys = {k for k in (_composition_key(f) for f in got_all_raw) if k}

    def correspond(gold_formule, ecriture):
        """Cette ECRITURE du pipeline designe-t-elle CE compose du gold ?

        UN SEUL predicat pour les deux cotes de la mesure. Il etait duplique et
        les deux copies avaient diverge : `SrCl2` face au gold `SrCl2 6H2O`
        etait compte TROUVE (cote manquants, qui tolere le noyau anhydre) et
        SIMULTANEMENT en trop (cote hors gold, qui comparait les compositions).
        Les deux ne peuvent pas etre vrais, et l'egalite stricte sur les
        precurseurs devenait inatteignable des que le modele laisse tomber un
        hydrate — ce qu'il fait couramment.

        La comparaison reste DIRECTIONNELLE : on cherche le noyau du GOLD dans
        l'ecriture du pipeline, jamais l'inverse. Sans quoi un pipeline qui
        n'extrait que « Sr » face a un gold « SrCO3 » cesserait d'etre signale.
        """
        # L'ECRITURE recue est BRUTE : `_variants` la normalise ici, et
        # `_composition_key` a besoin de la forme non normalisee pour parser
        # (`Cu(C2H3O2)2` devient `cuc2h3o22`, qui ne se decompose plus). Faire
        # entrer des chaines deja normalisees tuait la branche elementaire et
        # faisait retomber `solgel_cuo` de 100 % a 50 % de precurseurs.
        vg, ve = _variants(gold_formule), _variants(ecriture)
        if vg & ve:
            return True
        noyau = _norm(gold_formule.split("·")[0])
        if noyau and any(noyau in e for e in ve if e):
            return True
        kg, ke = _composition_key(gold_formule), _composition_key(ecriture)
        return bool(kg and ke and kg == ke)

    # Un solvant de LAVAGE vit sur l'ETAPE, pas dans les precurseurs — c'est un
    # partage DELIBERE du projet (`_recover_solvents` exclut les phrases de
    # lavage, il vise le solvant de REACTION). Le gold, lui, liste ce qu'un
    # chimiste releve, et un chimiste note le methanol. Sur `selfondu_cosi` la
    # mesure declarait donc CH3OH MANQUANT — precurseurs 80 % — alors que
    # l'etape de lavage portait bien `solvent='methanol'`, 7 repetitions.
    # L'information etait la ; c'est la mesure qui ne regardait qu'un endroit.
    solvants_d_etape = {st.get("solvent") for pw in pathways
                        for st in (pw.get("synthesis_steps") or [])
                        if st.get("solvent")}

    found, missing, flux_missing = [], [], []
    for gp in gold["precursors"]:
        gf = _norm(gp["formula"])
        core = _norm(gp["formula"].split("·")[0])
        hit = any(correspond(gp["formula"], e) for e in got_all_raw)
        # GARDE : seul un precurseur de role « solvent » peut etre satisfait
        # par une etape. Sans elle, le solvant d'un lavage crediterait un
        # REACTIF manquant et la mesure absoudrait une extraction incomplete.
        if not hit and (gp.get("role") or "").lower() == "solvent":
            hit = any(correspond(gp["formula"], e) for e in solvants_d_etape)
        (found if hit else missing).append(gp["formula"])
        if not hit and gp.get("role") == "flux":
            flux_missing.append(gp["formula"])

    # Séparer températures et durées par le seuil 100 ne vaut que pour les
    # iridates, où toute température dépasse 100 °C et toute durée reste sous
    # 100 h. Hors de ce corpus l'heuristique ment : un séchage à 60 °C devenait
    # « 60 h ». Un gold qui déclare explicitement `durations_h` fait donc foi,
    # et TOUTES ses key_values sont alors des températures.
    explicit_dur = gold.get("durations_h") is not None
    gold_T = {float(x) for x in gold.get("key_values", [])
              if explicit_dur or float(x) > 100}
    # Une rampe citée « 5 °C/min » est enregistrée telle quelle par l'extracteur.
    # Compter les deux écritures évite de sanctionner une extraction correcte
    # pour une question d'unité.
    gold_R = {float(x) for x in gold.get("ramp_rates_c_per_h", [])}
    gold_R |= {float(x) for x in gold.get("ramp_rates_c_per_min", [])}
    atm_exp = (gold.get("atmosphere") or "").lower()
    atm_key = "o2" if "o2" in atm_exp else ("air" if "air" in atm_exp else atm_exp)
    # Un gold qui declare l'atmosphere ABSENTE du texte ne fournit aucune
    # reference : on ne peut pas mesurer une fidelite a rien. Le critere devient
    # non applicable, sinon `hydro_czts` etait compte en echec pour avoir
    # correctement extrait « vacuum oven » de son etape de sechage.
    atm_inconnue = any(m in atm_exp for m in
                       ("non precisee", "non précisée", "autogene", "autogène",
                        "inconnue", "not stated"))

    def pct(a, b): return round(100.0 * a / b, 1) if b else None

    # --- ratios molaires : correct, faux, ou absent ? ---
    # On évalue CHAQUE voie contre le gold et on retient la MEILLEURE : le gold
    # décrit la recette de référence, les autres voies sont d'autres phases aux
    # proportions légitimement différentes. Une seule voie doit correspondre.
    n_ratio_gold = sum(1 for p in gold["precursors"] if p.get("molar_ratio") is not None)

    def _score(table: dict[str, float]):
        ok, bad, missing = [], [], []
        for gp in gold["precursors"]:
            exp = gp.get("molar_ratio")
            if exp is None:
                continue
            # Rapprocher l'hydrate de sa forme anhydre : le gold dit
            # « SrCl2·6H2O », l'en-tête du tableau dit « SrCl2 ». Même composé —
            # sans cela un ratio correct était compté absent.
            cands = set(_variants(gp["formula"]))
            cands |= _variants(gp["formula"].split("·")[0])
            got = next((table[v] for v in cands if v in table), None)
            if got is None:
                core = _norm(gp["formula"].split("·")[0])
                got = next((val for k, val in table.items()
                            if core and (k.startswith(core) or core.startswith(k))), None)
            if got is None:
                missing.append(gp["formula"])
            elif abs(got - float(exp)) < 0.01:
                ok.append(gp["formula"])
            else:
                bad.append(f"{gp['formula']}: {got:g} au lieu de {float(exp):g}")
        return ok, bad, missing

    ratio_ok, ratio_bad, ratio_missing = _score(got_ratios)
    for table in per_pathway_ratios.values():
        o, b, m = _score(table)
        # meilleure voie = le plus de ratios justes, puis le moins de faux
        if (len(o), -len(b)) > (len(ratio_ok), -len(ratio_bad)):
            ratio_ok, ratio_bad, ratio_missing = o, b, m

    # --- durées de palier (24 h, 100 h, 12 h, 36 h…) extraites du gold ---
    gold_dur = set()
    for s in gold.get("thermal_sequences", []):
        for m in re.finditer(r"\((\d+(?:\.\d+)?)\s*h", s.get("seq", "")):
            gold_dur.add(float(m.group(1)))
    if explicit_dur:
        gold_dur |= {float(v) for v in gold["durations_h"]}
    else:
        for v in gold.get("key_values", []):
            if float(v) <= 100:      # heuristique legacy, iridates uniquement
                gold_dur.add(float(v))

    return {
        "molar_ratios_pct": pct(len(ratio_ok), n_ratio_gold),
        "ratios_ok": ratio_ok,
        "ratios_FAUX": ratio_bad,
        "ratios_absents": ratio_missing,
        "durations_pct": pct(len(gold_dur & durations), len(gold_dur)),
        "durations_missing": sorted(gold_dur - durations),
        "precursors_pct": pct(len(found), len(gold["precursors"])),
        "precursors_missing": missing,
        "FLUX_MANQUANT": flux_missing,
        "temperatures_pct": pct(len(gold_T & temps), len(gold_T)),
        "temperatures_missing": sorted(gold_T - temps),
        "temperatures_hors_gold": sorted({t for t in temps if t > 100} - gold_T),
        "ramps_found": sorted(gold_R & ramps),
        "ramps_missing": sorted(gold_R - ramps),
        "atmosphere_ok": (None if atm_inconnue else
                          (any(atm_key in a or a in atm_key for a in atms)
                           if atms else False)),
        "atmospheres": sorted(atms),
        "values_proved_by_citation_pct": pct(n_cited, n_total),
        "n_values": n_total,
        # ── ÉGALITÉ STRICTE (exigence de Terry, 20/08) ────────────────────
        # La mesure ne rapportait que ce qui MANQUE, jamais ce qui est EN TROP :
        # un papier pouvait afficher 100 % partout en ayant extrait des valeurs
        # absentes du gold, restées invisibles. Un gold est atteint quand les
        # deux ensembles sont IDENTIQUES — mêmes valeurs, même nombre.
        "durations_hors_gold": sorted(durations - gold_dur),
        "ramps_hors_gold": sorted(ramps - gold_R),
        # Comparer les CHAINES ferait passer pour « en trop » les mêmes composés
        # écrits autrement : `EDTA` face à `C10H16N2O8`, `deionized water` face
        # à `H2O`, `Fe(NO3)2.9H2O` face au point médian. On compare donc les
        # compositions, comme partout ailleurs dans le projet.
        # Les composés qualifiés « usage: lavage » ne sont pas des réactifs de
        # la synthèse : ils ne comptent donc pas comme valeurs en trop. Leur
        # solvant figure de toute façon sur l'étape de lavage.
        "precursors_hors_gold": sorted(
            {p["formula"] for pw in pathways
             for p in (pw.get("precursors") or [])
             if p.get("formula") and p.get("usage") != "lavage"
             and not any(correspond(g["formula"], p["formula"])
                         for g in gold["precursors"])}),
        "egalite_stricte": {
            "temperatures": sorted(gold_T) == sorted(temps & gold_T)
                            and not ({t for t in temps if t > 100} - gold_T),
            "durations": gold_dur == durations,
            "ramps": gold_R == ramps,
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--papers", default="crystal,physrev,prepara")
    ap.add_argument("--table-block", action="store_true",
                    help="injecte les lignes de tableau sous un intitulé explicite")
    ap.add_argument("--n-gpu-layers", type=int, default=-1)
    ap.add_argument("--n-ctx", type=int, default=16384,
                    help="fenêtre de contexte ; 8192 déborde dès le 3e tour "
                         "quand le mode raisonnement est actif")
    ap.add_argument("--out", type=Path, default=ROOT / "logs" / "tc_vs_gold.json")
    ap.add_argument("--gold", type=Path, default=GOLD,
                    help="fichier gold ; les cles du corpus5 sont deja les cles "
                         "de papier, aucun mapping de titre n'est necessaire")
    a = ap.parse_args()

    from llama_cpp import Llama
    from synthgraph.agents.extractor_toolcalling import extract_all_samples

    path = MODELS_DIR / a.model
    if not path.exists():
        print(f"GGUF absent : {path}")
        return 1

    gold_all = json.loads(a.gold.read_text(encoding="utf-8"))
    print(f"modele : {a.model} | bloc tableaux : {a.table_block}")
    t0 = time.time()

    # Un modèle dont le template GÈRE DÉJÀ les outils (Qwen2.5, Qwen3, Qwen3.5)
    # doit garder son format natif : forcer 'chatml-function-calling' l'écrase et
    # tronque l'appel ('functions.add_precursor:' au lieu d'un tool_call). Seuls
    # les modèles sans support natif (Llama-3.1) ont besoin de l'adaptateur.
    probe = Llama(model_path=str(path), n_ctx=512, n_gpu_layers=0, verbose=False)
    native = "tool_call" in (probe.metadata or {}).get("tokenizer.chat_template", "")
    del probe
    print(f"template natif avec outils : {native} → "
          f"{'format natif conservé' if native else 'adaptateur chatml-function-calling'}")

    kw = {"model_path": str(path), "n_ctx": a.n_ctx,
          "n_gpu_layers": a.n_gpu_layers, "verbose": False}
    if not native:
        kw["chat_format"] = "chatml-function-calling"
    llm = Llama(**kw)
    print(f"charge en {time.time()-t0:.0f}s\n")

    results = {}
    for key in [k.strip() for k in a.papers.split(",")]:
        gold_key = PAPERS.get(key, key)
        gold = gold_all.get(gold_key)
        if not gold:
            # Saut SILENCIEUX auparavant : `--papers hydro_czts` sans le gold du
            # corpus5 faisait disparaitre le papier sans un mot, et le run
            # semblait reussi. Une faute de frappe passait de meme inapercue.
            print(f"!! {key} IGNORE : absent de {a.gold.name} — mauvais fichier "
                  f"gold ? (disponibles : {', '.join(sorted(gold_all)[:4])}...)",
                  flush=True)
            continue
        full = paper_text(key)
        if not full:
            print(f"[{key}] texte introuvable"); continue
        foc = focused(full, gold.get("target", ""), gold.get("method_type", ""))

        print(f"{'='*74}\n### {key} — {gold.get('method_type')}\n{'='*74}", flush=True)
        # La remise a zero du contexte vit au seuil de l'extraction
        # (`_contexte_vierge`), pas ici : le defaut touchait AUSSI le
        # pipeline de production, pas seulement cet outil de mesure.
        t1 = time.time()
        # Le texte COMPLET accompagne le focalise : la focalisation reduit
        # `hydro_czts` de 30 000 a 8 500 caracteres et ecarte la phrase
        # « Pure kesterite ... a 180 °C pour 12 h », dont un chimiste a besoin.
        out = extract_all_samples(llm, foc, gold.get("target", ""),
                                  gold.get("method_type", ""), route_id=key,
                                  full_text=full,
                                  with_table_block=a.table_block)
        st = out.get("tool_stats", {})
        cmp = compare(gold, out.get("pathways", []))
        cmp["_stats"] = {k: st.get(k) for k in
                         ("samples_detected", "samples_extracted", "tool_calls",
                          "accepted", "refused", "seconds")}
        cmp["_wall_s"] = round(time.time() - t1, 1)
        results[key] = cmp

        # Sauvegarder les VOIES EXTRAITES, pas seulement les métriques : sans
        # elles impossible de relire ce que le modèle a produit, donc impossible
        # de juger si une synthèse est refaisable ou de rédiger un rapport.
        # Le nom du modele est un CHEMIN : « ../models/Qwen3-8B-... » donnait
        # « logs/pathways_../models/Qwen3_x.json », et le run plantait a
        # l'ECRITURE, apres 93 s de GPU deja depenses. On ne garde que le nom.
        _marque = pathlib.Path(a.model).stem.split('-')[0]
        pw_path = a.out.parent / f"pathways_{_marque}_{key}.json"
        pw_path.write_text(json.dumps(
            {"paper": gold_key, "pathways": out.get("pathways", []),
             "tool_stats": st, "rejections": out.get("rejections", [])[:40]},
            ensure_ascii=False, indent=2), encoding="utf-8")

        print(f"  echantillons : {st.get('samples_detected','-')} detectes / "
              f"{st.get('samples_extracted','-')} extraits | "
              f"{st.get('tool_calls','-')} appels ({st.get('accepted','-')} acceptes) | "
              f"{cmp['_wall_s']}s")
        print(f"  precurseurs  : {cmp['precursors_pct']}%"
              + (f"  MANQUANTS {cmp['precursors_missing']}" if cmp['precursors_missing'] else ""))
        print(f"  RATIOS molaires : {cmp['molar_ratios_pct']}%"
              + (f"  absents {cmp['ratios_absents']}" if cmp['ratios_absents'] else "")
              + (f"  /!\\ FAUX {cmp['ratios_FAUX']}" if cmp['ratios_FAUX'] else ""))
        print(f"  durees       : {cmp['durations_pct']}%"
              + (f"  manquantes {cmp['durations_missing']}" if cmp['durations_missing'] else ""))
        if cmp["FLUX_MANQUANT"]:
            print(f"    /!\\ FLUX MANQUANT {cmp['FLUX_MANQUANT']} — recette irrealisable")
        print(f"  temperatures : {cmp['temperatures_pct']}%"
              + (f"  manquantes {cmp['temperatures_missing']}" if cmp['temperatures_missing'] else ""))
        if cmp["temperatures_hors_gold"]:
            print(f"    /!\\ hors gold : {cmp['temperatures_hors_gold']}")
        print(f"  rampes       : trouvees {cmp['ramps_found']} manquantes {cmp['ramps_missing']}")
        # Les valeurs EN TROP etaient calculees puis jamais affichees : un papier
        # pouvait afficher 100 % partout en ayant extrait des valeurs absentes
        # du gold. Un gold est atteint quand les deux ensembles COINCIDENT.
        for etiq, cle in (("temperatures", "temperatures_hors_gold"),
                          ("durees", "durations_hors_gold"),
                          ("rampes", "ramps_hors_gold"),
                          ("precurseurs", "precursors_hors_gold")):
            if cmp.get(cle):
                print(f"  !! {etiq} HORS GOLD : {cmp[cle]}")
        eg = cmp.get("egalite_stricte") or {}
        exact = [k for k, v in eg.items() if v]
        rate = [k for k, v in eg.items() if not v]
        print(f"  EGALITE STRICTE : {', '.join(exact) if exact else 'aucune'}"
              + (f"  |  ecart sur : {', '.join(rate)}" if rate else ""))
        _a = cmp['atmosphere_ok']
        print(f"  atmosphere   : {cmp['atmospheres']} "
              f"[{'n/a — non precisee dans le gold' if _a is None else ('OK' if _a else 'KO')}]")
        print(f"  valeurs PROUVEES par leur citation : "
              f"{cmp['values_proved_by_citation_pct']}% ({cmp['n_values']} valeurs)")

    a.out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n→ {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
