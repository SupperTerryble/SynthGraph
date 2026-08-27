#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
synthgraph/agents/extractor_toolcalling.py — SynthGraph V5 (architecture bis)

Extracteur AGENTIQUE : le modèle construit la voie de synthèse tour par tour,
en appelant des outils, au lieu de produire un JSON d'un bloc.

Intérêt (mandat Terry) : chaque valeur numérique entre dans le graphe par un
appel qui la REFUSE si sa citation ne la prouve pas, et le refus est renvoyé au
modèle en langage clair pour qu'il se corrige au tour suivant. Le single-shot
n'offre pas cette boucle : il faut tout revalider après coup, et 22,6 % seulement
des valeurs s'y trouvaient justifiées.

Les trois verrous identifiés dans `logs/notes/tool_calling_architecture_analysis.md`
sont traités explicitement ici :
  1. LATENCE          → plafond de tours, arrêt dès finalize_route
  2. DÉRIVE DE CONTEXTE → détection de boucle (appel identique répété), rappel
                          de l'objectif injecté quand le modèle s'égare, clôture
                          forcée si le plafond est atteint
  3. FORMAT INSTABLE   → `chat_format="chatml-function-calling"` (vérifié
                          indispensable : sans lui, Llama-3.1-8B répond en texte
                          libre et n'émet AUCUN tool_call), noms d'outils inconnus
                          rejetés avec la liste des noms valides

Aucun appel n'est jamais fait au hasard : un outil inconnu ou un argument
illisible produit un message d'erreur exploitable, jamais une valeur devinée.
"""

from __future__ import annotations

import json
import os
import logging
import re
import time
from typing import Any, Optional

from synthgraph.extraction.graph_tools import RouteBuilder, TOOL_SCHEMAS, TOOL_NAMES

logger = logging.getLogger("SynthGraph.ExtractorTC")

# Un papier demande ~10-14 tours à la granularité retenue. 28 laisse de la marge
# pour les corrections après refus, sans laisser une boucle courir indéfiniment.
MAX_TURNS = 28
# Au-delà, on considère que le modèle tourne en rond sur le même appel.
MAX_IDENTICAL_CALLS = 3
# Messages récents conservés lors de l'élagage (hors consigne initiale).
_HISTORY_KEEP = 6
# Seuil déclenchant l'élagage. Sous ce budget, l'historique complet est gardé :
# le contexte aide l'agent, et seuls les modèles à raisonnement le saturent.
# 9000 était trop bas : avec n_ctx=16384 l'élagage se déclenchait bien avant tout
# risque de débordement, et faisait perdre du contexte aux modèles à raisonnement
# (Qwen2.5-7B : 62,5 % → 25 % ; Qwen3.5-9B : 87,5 % → 37,5 %). On ne coupe plus
# qu'au seuil où la fenêtre est réellement menacée.
_TRIM_ABOVE_TOKENS = 13500

SYSTEM_PROMPT = """Tu es un chimiste des matériaux. Tu construis une voie de synthèse
en appelant des outils, un appel à la fois.

RÈGLE ABSOLUE : tu n'inventes RIEN. Chaque valeur que tu enregistres doit être
écrite noir sur blanc dans le texte fourni. Si une information manque, tu ne
l'ajoutes pas — un trou est acceptable, une invention ne l'est jamais.

CITATIONS : chaque appel exige une citation COPIÉE MOT POUR MOT du texte, jamais
reformulée. Les conditions de synthèse sont souvent dans des LIGNES DE TABLEAU
(par exemple « Sr214#1 1 : 2 : 7 1300 C -> (8 C/h) 900 C -> RT ») : cite la ligne
entière, c'est elle qui prouve les valeurs.

MÉTHODE :
1. add_precursor pour CHAQUE réactif, solvant ou flux (un appel par composé).
   Un flux est un composé en large excès servant de milieu de croissance.
2. add_operation pour CHAQUE étape, avec tous ses paramètres et sa citation.
   Renseigne `equipment` avec le CONTENANT quand le texte le nomme (creuset de
   platine, autoclave, bombe de digestion, bécher) : sans lui la synthèse n'est
   pas refaisable.
3. finalize_route UNE SEULE FOIS quand tout est enregistré.

[Un paragraphe « exhaustivité des étapes » a été essayé le 19/08 pour récupérer
 la durée manquante de `prepara`. Résultat MESURÉ : durées 0 % → 100 %, mais
 précurseurs 100 % → 20 %, températures 100 % → 0 %, traçabilité 100 % → 0 %.
 Allonger la consigne détourne le modèle de sa tâche principale. Retiré.
 → Les manques doivent être comblés par du POST-TRAITEMENT DÉTERMINISTE
   (ratios depuis l'en-tête de tableau, durée depuis la citation), pas en
   chargeant le prompt.]

Si un outil refuse ton appel, LIS le message : il dit précisément ce qui ne va
pas. Corrige et rappelle l'outil. Ne répète jamais un appel identique."""


def _tool_result_msg(call_id: str, name: str, payload: dict) -> dict:
    return {"role": "tool", "tool_call_id": call_id, "name": name,
            "content": json.dumps(payload, ensure_ascii=False)}


# ══════════════════════════════════════════════════════════════════════════
# APPELS D'OUTILS AU FORMAT NATIF QWEN3 — <tool_call>{...}</tool_call>
#
# Diagnostic du 18/08/2026 : Qwen3 avait été déclaré « incapable de
# tool-calling » après deux campagnes. C'était FAUX — il émet des appels
# parfaitement formés, mais dans SES balises natives, que llama-cpp ne remonte
# pas dans `message["tool_calls"]` (il les laisse dans le contenu texte).
# Observé tel quel :
#     <think>\n\n</think>\n\n<tool_call>
#     {"name": "add_precursor", "arguments": {"formula": "IrO2", ...}}
#     </tool_call>
# On les récupère donc en repli. Le bloc <think> est conservé (choix de Terry :
# le raisonnement peut améliorer la qualité) mais retiré avant parsing, et
# `max_tokens` est relevé pour qu'il ne dévore pas la place de l'appel.
# ══════════════════════════════════════════════════════════════════════════

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_NATIVE_CALL_RE = re.compile(r"<tool_call>\s*(\{.*?\})\s*</tool_call>",
                             re.DOTALL | re.IGNORECASE)


def _strip_think(content: str) -> str:
    """Retire les blocs de raisonnement, y compris un <think> non refermé
    (troncature par max_tokens) qui masquerait tout le reste."""
    if not content:
        return ""
    cleaned = _THINK_RE.sub("", content)
    # Balise fermante ORPHELINE : Qwen3.6 raisonne en texte brut puis ferme par
    # </think> sans jamais avoir ouvert. Tout ce qui précède est du raisonnement…
    # SAUF si l'appel a déjà été émis AVANT ce </think> : couper aveuglément
    # détruisait alors l'appel lui-même. Régression mesurée sur Qwen3.5-9B
    # (températures 87,5 % → 37,5 %). On ne coupe donc que si l'appel est bien
    # dans la partie qui suit.
    if "</think>" in cleaned and "<think>" not in cleaned:
        after = cleaned.split("</think>", 1)[1]
        if "<tool_call>" in after or "<function=" in after:
            cleaned = after
    # Ouverture sans fermeture : troncature par max_tokens, rien d'exploitable.
    if "<think>" in cleaned and "</think>" not in cleaned:
        cleaned = cleaned.split("<think>")[0]
    return cleaned.strip()


# Variante XML du même format, employée par Qwen3.6 (MoE) :
#     <tool_call>
#     <function=add_precursor>
#     <parameter=formula>\nIrO2\n</parameter>
#     <parameter=citation>\n...\n</parameter>
#     </function>
#     </tool_call>
# Sans ce parser, le modèle produisait des appels PARFAITS comptés comme « 0
# appel » — ~1 h de GPU consommée pour rien avant que l'inspection des tokens
# bruts ne révèle la vraie cause.
_XML_FUNC_RE = re.compile(r"<function=([A-Za-z_]\w*)>(.*?)</function>", re.DOTALL)
_XML_PARAM_RE = re.compile(r"<parameter=([A-Za-z_]\w*)>(.*?)</parameter>", re.DOTALL)


def _extract_xml_tool_calls(content: str, turn: int) -> list[dict]:
    """Parse la variante XML de <tool_call>."""
    calls: list[dict] = []
    for i, m in enumerate(_XML_FUNC_RE.finditer(_strip_think(content))):
        name = m.group(1)
        args = {k: v.strip() for k, v in _XML_PARAM_RE.findall(m.group(2))}
        # Les nombres arrivent en texte : on les convertit pour que la
        # validation numérique des outils s'applique normalement.
        for k, v in list(args.items()):
            try:
                args[k] = float(v) if "." in v else int(v)
            except (TypeError, ValueError):
                pass
        calls.append({
            "id": f"xml_{turn}_{i}",
            "type": "function",
            "function": {"name": name,
                         "arguments": json.dumps(args, ensure_ascii=False)},
        })
    return calls


def _extract_native_tool_calls(content: str, turn: int) -> list[dict]:
    """Convertit les <tool_call> natifs au format OpenAI attendu par la boucle."""
    calls: list[dict] = []
    for i, m in enumerate(_NATIVE_CALL_RE.finditer(_strip_think(content))):
        try:
            payload = json.loads(m.group(1))
        except json.JSONDecodeError:
            continue
        name = payload.get("name")
        if not name:
            continue
        args = payload.get("arguments", {})
        calls.append({
            "id": f"native_{turn}_{i}",
            "type": "function",
            "function": {"name": name,
                         "arguments": args if isinstance(args, str)
                         else json.dumps(args, ensure_ascii=False)},
        })
    # Repli sur la variante XML si aucun appel JSON n'a été trouvé.
    return calls or _extract_xml_tool_calls(content, turn)


def _contexte_vierge(llm) -> None:
    """Un papier ne doit RIEN heriter de celui d'avant.

    Le moteur est un SINGLETON in-process (contrainte architecturale) : le meme
    objet `Llama` sert tous les papiers d'un lot, et son cache de prefixe leur
    survit. Mesure du 22/08, trois runs :

        reduc_cu SEUL, deux fois        -> 6 etapes, 21 appels (identiques)
        reduc_cu APRES combu_ferrite    -> 7 etapes, 12 appels

    Le moteur est deterministe : deux runs isoles ne divergent en RIEN. C'est le
    CONTEXTE HERITE qui deplace le resultat — et une extraction qui depend de
    l'ordre du lot ne mesure plus le papier.

    Le defaut ne touchait pas que l'outil de mesure : `run.py --input data/`
    enchaine lui aussi les papiers sur un moteur unique. La remise a zero vit
    donc ICI, au seuil de l'extraction, et non chez un appelant.

    `hasattr` parce que les tests injectent des stubs qui n'ont pas cette API.
    """
    if hasattr(llm, "reset"):
        try:
            llm.reset()
        except Exception:  # noqa: BLE001
            pass


def extract_all_samples(llm, source_text: str, target: str = "",
                        method_type: str = "", route_id: str = "r1",
                        max_samples: int = 12, with_table_block: bool = False,
                        max_turns: int = MAX_TURNS,
                        full_text: str = "") -> dict:
    """Une extraction COURTE par échantillon décrit dans le papier.

    Le papier « Crystal growth » décrit dix expériences donnant des phases
    différentes ; n'en extraire qu'une perd neuf protocoles et cinq températures.
    Plutôt que d'exiger du modèle une quarantaine de tours d'affilée — instables
    au-delà de 6-7 d'après la note d'audit — on détecte les échantillons par le
    code, puis on lance une boucle brève et ciblée pour chacun.

    Args:
        with_table_block: injecte les lignes de tableau sous un intitulé
            explicite. Repli à activer si le modèle cite la prose au lieu des
            tableaux et voit donc ses valeurs écartées faute de preuve.
    """
    _contexte_vierge(llm)
    from synthgraph.extraction.sample_detect import detect_samples, table_rows_block

    samples = detect_samples(source_text, max_samples=max_samples)
    # INSTRUMENTATION DE MESURE, jamais active en production. #50 demande si un
    # echantillon herite du precedent : la remise a zero de #48 est faite PAR
    # PAPIER, or les dix echantillons de `crystal` enchainent leurs boucles sur
    # le meme contexte. Inverser l'ordre et comparer voie par voie (par
    # sample_id, pas par position) repond a la question sans toucher au reste.
    if os.environ.get("SG_SAMPLES_REVERSE") == "1" and samples:
        samples = list(reversed(samples))
        logger.info(f"  [mesure] ordre des echantillons INVERSE ({len(samples)})")
    context = source_text + (table_rows_block(source_text) if with_table_block else "")

    if not samples:
        return extract_with_tools(llm, context, target, method_type,
                                  full_text=full_text or source_text,
                                  route_id=route_id, max_turns=max_turns)

    pathways: list[dict] = []
    all_rejections: list[str] = []
    agg = {"samples_detected": len(samples), "samples_extracted": 0,
           "turns": 0, "tool_calls": 0, "accepted": 0, "refused": 0,
           "unknown_tool": 0, "loop_breaks": 0, "seconds": 0.0, "per_sample": []}

    for s in samples:
        sid = s["sample_id"]
        logger.info(f"[TC] échantillon {sid}")
        # La ligne de l'échantillon est rappelée en tête : c'est elle qui porte
        # les conditions, et elle devient la citation attendue.
        focused = (f"Conditions de l'échantillon {sid} :\n{s['line']}\n\n"
                   f"Contexte complet :\n{context}")
        out = extract_with_tools(llm, focused, target, method_type,
                                 full_text=full_text or source_text,
                                 route_id=f"{route_id}_{sid}", sample_hint=sid,
                                 max_turns=max_turns)
        st = out.get("tool_stats", {})
        for k in ("turns", "tool_calls", "accepted", "refused",
                  "unknown_tool", "loop_breaks", "seconds"):
            agg[k] += st.get(k, 0)
        agg["per_sample"].append({"sample_id": sid, "stops": st.get("stop_reason"),
                                  "steps": len(out["pathways"][0]["synthesis_steps"])
                                  if out.get("pathways") else 0})
        all_rejections.extend(out.get("rejections", []))
        for pw in out.get("pathways", []):
            pw["variant_id"] = sid          # une voie = un échantillon
            pathways.append(pw)
            agg["samples_extracted"] += 1

    agg["seconds"] = round(agg["seconds"], 1)
    logger.info(f"[TC] {agg['samples_extracted']}/{agg['samples_detected']} échantillons "
                f"extraits | {agg['tool_calls']} appels | {agg['seconds']}s")

    return {
        "pathways": pathways,
        "reasoning": "",
        "confidence": 0.8 if pathways else 0.3,
        "route_id": route_id,
        "method_type": method_type,
        "extraction_notes": (f"tool-calling multi-échantillons "
                             f"({agg['samples_extracted']}/{agg['samples_detected']} voies, "
                             f"{agg['accepted']} appels acceptés)"),
        "tool_stats": agg,
        "rejections": all_rejections,
    }


def extract_with_tools(llm, source_text: str, target: str = "", method_type: str = "",
                       route_id: str = "r1", sample_hint: str = "",
                       max_turns: int = MAX_TURNS,
                       max_no_tool: int = 2, full_text: str = "") -> dict:
    """Construit une voie de synthèse par appels d'outils successifs.

    Args:
        llm: instance Llama chargée avec chat_format='chatml-function-calling'.
        source_text: texte focalisé (doit contenir les lignes de tableau).
        sample_hint: identifiant d'échantillon à cibler (ex. 'Sr214#1'), pour
            extraire une séquence précise quand le papier en décrit plusieurs.

    Returns:
        dict au format `pathways` du pipeline, enrichi de statistiques d'exécution.
    """
    # Le texte COMPLET accompagne le focalise : certaines recuperations
    # deterministes ont besoin du papier entier (cf. RouteBuilder).
    builder = RouteBuilder(source_text, target, method_type, route_id,
                           full_text=full_text)

    consigne = (f"Texte source :\n\n{source_text}\n\n"
                f"Matériau visé : {target or 'à déterminer'}\n"
                f"Méthode : {method_type or 'à déterminer'}\n")
    if sample_hint:
        consigne += (f"\nExtrais UNIQUEMENT la voie de l'échantillon « {sample_hint} ». "
                     f"Ignore les autres échantillons du papier.\n")
    consigne += "\nCommence par enregistrer les précurseurs."

    messages: list[dict] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": consigne},
    ]

    # `accepted` seul est trompeur : une opération dont TOUS les paramètres sont
    # écartés est « acceptée » sans rien apporter. On sépare donc :
    #   productive = au moins une donnée est entrée
    #   empty      = étape créée, aucun paramètre retenu
    stats = {"turns": 0, "tool_calls": 0, "accepted": 0, "productive": 0,
             "empty": 0, "refused": 0, "unknown_tool": 0, "no_tool_call": 0,
             "loop_breaks": 0, "seconds": 0.0, "finalized": False,
             "stop_reason": "", "history_trims": 0}
    seen_calls: dict[str, int] = {}
    t_start = time.time()

    for turn in range(1, max_turns + 1):
        stats["turns"] = turn

        # ── Élagage de l'historique ────────────────────────────────────────
        # Avec le mode raisonnement actif, chaque tour ajoute plusieurs
        # centaines de tokens ; l'historique dépassait la fenêtre dès le 3e-4e
        # tour (« Requested tokens (8715) exceed context window of 8192 ») et
        # l'extraction s'arrêtait — les précurseurs n'étaient jamais atteints.
        # On conserve la consigne (2 premiers messages) et les échanges
        # récents : le RouteBuilder porte déjà l'état, l'historique ancien
        # n'est utile qu'au contexte immédiat de correction.
        # Élagage CONDITIONNEL : uniquement quand l'historique menace vraiment
        # la fenêtre. Élaguer systématiquement pénalise les modèles SANS mode
        # raisonnement, qui ne débordent jamais : mesuré sur Qwen2.5-7B, les
        # températures tombaient de 62,5 % à 25 % et les valeurs de 55 à 27,
        # faute de contexte. On n'élague donc qu'au-delà d'un budget estimé
        # (~4 caractères par token, marge de sécurité incluse).
        approx_tokens = sum(len(str(m.get("content") or "")) for m in messages) // 4
        if approx_tokens > _TRIM_ABOVE_TOKENS and len(messages) > _HISTORY_KEEP + 2:
            messages = messages[:2] + messages[-_HISTORY_KEEP:]
            stats["history_trims"] += 1
            logger.info(f"[TC] historique élagué (~{approx_tokens} tokens estimés)")

        try:
            # max_tokens généreux : avec le mode raisonnement actif, le bloc
            # <think> peut consommer plusieurs centaines de tokens AVANT
            # l'appel d'outil. À 768, Qwen3 était coupé en plein raisonnement
            # et n'émettait jamais son <tool_call>.
            resp = llm.create_chat_completion(
                messages=messages, tools=TOOL_SCHEMAS, tool_choice="auto",
                # 2048 tronquait le modèle EN PLEIN RAISONNEMENT
                # (`finish=length`, 7052 caractères générés sans appel) : il
                # rattrapait au tour suivant en perdant des valeurs. La qualité
                # prime sur la vitesse — on lui laisse la place de conclure.
                temperature=0.0, max_tokens=4096,
            )
        except Exception as e:  # noqa: BLE001 — un échec d'inférence ne doit pas tuer le papier
            logger.error(f"[TC] échec d'inférence au tour {turn} : {type(e).__name__}: {e}")
            stats["stop_reason"] = f"inference_error:{type(e).__name__}"
            break

        msg = resp["choices"][0]["message"]
        calls = msg.get("tool_calls") or []

        # Repli format natif : llama-cpp ne remonte pas les <tool_call> de
        # Qwen3 — sans ce repli le modèle paraît muet alors qu'il répond bien.
        if not calls:
            calls = _extract_native_tool_calls(msg.get("content") or "", turn)
            if calls:
                stats["native_calls"] = stats.get("native_calls", 0) + len(calls)
                logger.info(f"[TC] {len(calls)} appel(s) récupéré(s) au format natif "
                            f"<tool_call> (tour {turn})")
        # Les arguments doivent être réinjectés en OBJET, pas en chaîne JSON :
        # le template de Qwen3.8-27B refuse la chaîne (« Tool call arguments …
        # were passed as a JSON string »), ce qui tuait l'inférence au 2e tour.
        # Les templates plus permissifs acceptent les deux formes.
        if calls:
            replay = []
            for c in calls:
                fn = dict(c.get("function") or {})
                a = fn.get("arguments")
                if isinstance(a, str):
                    try:
                        fn["arguments"] = json.loads(a)
                    except (json.JSONDecodeError, TypeError, ValueError):
                        fn["arguments"] = {}
                replay.append({**c, "function": fn})
            messages.append({"role": "assistant",
                             "content": msg.get("content") or "",
                             "tool_calls": replay})
        else:
            messages.append({"role": "assistant", "content": msg.get("content") or ""})

        # ── Verrou 2 : le modèle a cessé d'appeler des outils ───────────────
        if not calls:
            stats["no_tool_call"] += 1
            # Journaliser CE QUE LE MODÈLE A PRODUIT. Sans cette trace, un
            # « 0 appel » est indiagnosticable : on ne sait pas s'il refuse
            # d'agir, s'il emploie un 7e format, ou s'il a été tronqué en plein
            # raisonnement. Trois heures de GPU ont été perdues faute de l'avoir.
            _raw = msg.get("content") or ""
            _fin = (resp.get("choices") or [{}])[0].get("finish_reason")
            logger.warning(
                f"[TC] AUCUN appel au tour {turn} | finish={_fin} | "
                f"{len(_raw)} car. générés | contient <tool_call>="
                f"{'<tool_call>' in _raw} <function=={'<function=' in _raw} "
                f"| fin du texte : {_raw[-200:]!r}")
            if builder.precursors and builder.operations:
                # Il a probablement fini sans le dire : on clôt proprement.
                builder.finalize_route()
                stats["stop_reason"] = "no_tool_call_autofinalize"
                logger.info(f"[TC] tour {turn} : plus d'appel d'outil — clôture automatique")
                break
            # Seuil paramétrable : il PÈSE sur le verdict de faisabilité.
            # À 2, les Qwen3 étaient déclarés en échec après deux tours muets ;
            # un seuil plus large leur laisse une chance de se reprendre. Le
            # résultat doit toujours être lu avec la valeur employée.
            if stats["no_tool_call"] >= max_no_tool:
                stats["stop_reason"] = f"no_tool_call_x{max_no_tool}"
                break
            messages.append({"role": "user", "content":
                             "Tu dois utiliser les outils, pas repondre en texte. "
                             "Appelle add_precursor, add_operation ou finalize_route "
                             "avec une citation COPIEE du texte."})
            continue

        for call in calls:
            stats["tool_calls"] += 1
            fn = call.get("function") or {}
            name = fn.get("name") or ""
            call_id = call.get("id") or f"call_{turn}"

            # ── Verrou 3 : nom d'outil halluciné ────────────────────────────
            if name not in TOOL_NAMES:
                stats["unknown_tool"] += 1
                logger.warning(f"[TC] outil inconnu '{name}' au tour {turn}")
                messages.append(_tool_result_msg(call_id, name or "unknown", {
                    "ok": False,
                    "message": (f"REFUSE : l'outil '{name}' n'existe pas. "
                                f"Outils disponibles : {', '.join(sorted(TOOL_NAMES))}.")}))
                continue

            raw_args = fn.get("arguments") or "{}"
            try:
                args = json.loads(raw_args) if isinstance(raw_args, str) else dict(raw_args)
            except (json.JSONDecodeError, TypeError, ValueError):
                messages.append(_tool_result_msg(call_id, name, {
                    "ok": False,
                    "message": "REFUSE : arguments illisibles. Renvoie un JSON valide."}))
                stats["refused"] += 1
                continue

            # ── Verrou 2 : boucle sur un appel identique ────────────────────
            sig = f"{name}:{json.dumps(args, sort_keys=True, ensure_ascii=False)}"
            seen_calls[sig] = seen_calls.get(sig, 0) + 1
            if seen_calls[sig] > MAX_IDENTICAL_CALLS:
                stats["loop_breaks"] += 1
                logger.warning(f"[TC] boucle détectée sur {name} (tour {turn}) — arrêt")
                stats["stop_reason"] = "loop_detected"
                messages.append(_tool_result_msg(call_id, name, {
                    "ok": False, "message": "REFUSE : appel déjà tenté. Passe à la suite."}))
                break

            # ── Exécution ───────────────────────────────────────────────────
            try:
                if name == "add_precursor":
                    result = builder.add_precursor(**args)
                elif name == "add_operation":
                    st = args.pop("step_type", None)
                    cit = args.pop("citation", None)
                    result = builder.add_operation(st, cit, **args)
                else:
                    result = builder.finalize_route(**args)
            except TypeError as e:
                result = {"ok": False,
                          "message": f"REFUSE : arguments invalides ({e}). "
                                     f"Vérifie les noms de paramètres."}

            if result.get("ok"):
                stats["accepted"] += 1
                # Un add_operation sans aucun paramètre retenu ne fait
                # qu'ajouter une étape vide : ce n'est pas une réussite.
                if name == "add_operation" and not result.get("kept"):
                    stats["empty"] += 1
                else:
                    stats["productive"] += 1
            else:
                stats["refused"] += 1
            messages.append(_tool_result_msg(call_id, name, result))

            if name == "finalize_route" and result.get("ok"):
                stats["finalized"] = True
                stats["stop_reason"] = "finalized"
                break

        if stats["finalized"] or stats["stop_reason"] in ("loop_detected",):
            break
    else:
        # ── Verrou 1 : plafond atteint ─────────────────────────────────────
        stats["stop_reason"] = "max_turns"
        logger.warning(f"[TC] plafond de {max_turns} tours atteint sans finalize_route")

    # Clôture forcée : on garde ce qui a été validé plutôt que de tout perdre.
    if not builder.finalized and builder.precursors and builder.operations:
        builder.finalize_route()
        logger.info("[TC] clôture forcée — la voie partielle est conservée")

    stats["seconds"] = round(time.time() - t_start, 1)
    out = builder.to_pathways_dict()
    out["tool_stats"] = stats
    out["rejections"] = builder.rejections

    logger.info(f"[TC] {stats['turns']} tours | {stats['tool_calls']} appels "
                f"({stats['accepted']} acceptés, {stats['refused']} refusés, "
                f"{stats['unknown_tool']} outils inconnus) | "
                f"{stats['seconds']}s | fin: {stats['stop_reason']}")
    return out
