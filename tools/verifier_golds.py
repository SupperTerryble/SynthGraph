#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""QUATRE verifications independantes de chaque gold, avant toute conclusion.

Un gold faux ne se voit pas : il fausse la mesure en silence, et le pipeline
est accuse — ou absout — a tort. Mes annotations manuelles se sont trompees SIX
fois sur ce corpus, toujours dans le meme sens :

  1-3. trois ATMOSPHERES inferees (« air » deduit du procede) ;
  4.   une RAMPE convertie (5 °C/min ecrit 300 °C/h), rendant l'egalite stricte
       inatteignable ;
  5.   une DUREE oubliee (5 min de dispersion sur hydro_czts) ;
  6.   des MILLIMOLES ecrites dans un champ de rapport molaire, alors que le
       papier enonce « molar ratio LiI:KI 0.63:0.37 ».

Aucune de ces six n'aurait ete prise par une seule verification : la 1 est un
probleme d'attribution, la 4 de coherence, la 5 de completude, la 6 de sens.
D'ou quatre passes qui attaquent le gold sous quatre angles distincts.

  PASSE 1 — SOURCAGE     tout ce que le gold affirme est-il ECRIT dans le texte ?
  PASSE 2 — COMPLETUDE   le texte porte-t-il des valeurs que le gold a OUBLIEES ?
  PASSE 3 — ATTRIBUTION  chaque valeur appartient-elle bien a CETTE synthese ?
  PASSE 4 — COHERENCE    le gold se contredit-il lui-meme ?

Les passes 2 et 3 rendent des SIGNALEMENTS, pas des verdicts : elles designent
ce qu'un humain doit relire. Les passes 1 et 4 rendent des ERREURS.

Usage :
    python tools/verifier_golds.py                # les trois fichiers de golds
    python tools/verifier_golds.py --gold data/gold/gold_corpus9.json
    python tools/verifier_golds.py --papier cvd_mos2
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from synthgraph.extraction.graph_tools import (  # noqa: E402
    RouteBuilder, _composition_key, _norm_words)
from synthgraph.validation.deterministic import (  # noqa: E402
    parse_composition)

GOLDS = ("gold_sr2iro4.json", "gold_corpus5.json", "gold_corpus9.json")

# Les cles du gold des iridates sont des TITRES ; les autres sont deja des cles.
TITRE_VERS_CLE = {
    "Crystal growth and intrinsic magnetic behaviour of Sr2IrO4": "crystal",
    "PhysRevB.49.11890": "physrev",
    "the-preparation-of-a-strontium-iridium-oxide-sr2iro41-2 (1)": "prepara",
}

# Une phrase de CARACTERISATION n'enonce pas une consigne de synthese.
NON_SYNTHESE = re.compile(
    r"\b(tem|hrtem|stem|sem|fesem|xrd|dls|bet|ftir|raman|edx|eds|xps|nmr|"
    r"spectr\w*|isotherm|adsorption|diffract\w*|microscop\w*|measurement|"
    r"measured|analys\w*|characteriz\w*|voltammetr\w*|potentiostat|"
    r"conductimeter|densimeter|viscometer|calibrat\w*)\b", re.I)
# Un verbe operatoire : sans lui, une phrase qui porte un nombre n'est pas
# forcement une consigne (legende de figure, discussion, reference).
VERBE_OPERATOIRE = re.compile(
    r"\b(heat\w*|calcin\w*|anneal\w*|sinter\w*|cool\w*|dry\w*|dried|mix\w*|"
    r"grind\w*|ground|mill\w*|stir\w*|dissolv\w*|disperse\w*|add\w*|wash\w*|"
    r"filtrat\w*|centrifug\w*|prepar\w*|synthesiz\w*|react\w*|hold|held|kept|"
    r"maintain\w*|soak\w*|deposit\w*|electrodeposit\w*|treat\w*|placed|loaded|"
    r"transferr\w*|sealed|evacuat\w*|remain\w*|stood|stand\w*|left|"
    r"allowed|aged|ageing|aging|immers\w*|bubbl\w*|purg\w*|sonicat\w*)\b", re.I)

# Un TABLEAU n'a pas de verbe et reste une source de PREMIER RANG dans ce
# projet : les huit sequences thermiques de `crystal` ne vivent que dans sa
# table (« Sr214#1  1 : 2 : 7  1300 ... »). Sans cette reconnaissance, la passe
# d'attribution accuse un gold JUSTE de citer hors contexte operatoire.
LIGNE_DE_TABLE = re.compile(r"\d\s*:\s*\d|\b(?:sample|echantillon|sequence|"
                            r"furnace\s+sequence|run)\b", re.I)


def _operatoire(ph: str) -> bool:
    """Phrase de consigne, ou ligne de tableau de conditions."""
    if NON_SYNTHESE.search(ph):
        return False
    if VERBE_OPERATOIRE.search(ph):
        return True
    return bool(LIGNE_DE_TABLE.search(ph) and len(re.findall(r"\d+", ph)) >= 3)


# Les golds sont annotes en FRANCAIS sur des textes ANGLAIS : « four a moufle »
# face a « muffle furnace », « becher » face a « beaker ». Sans ce pont, le
# controle du contenant signale tous les golds justes.
VESSEL_FR_EN = {
    "creuset": "crucible", "four": "furnace", "moufle": "muffle",
    "becher": "beaker", "bocal": "jar", "jarre": "jar", "nacelle": "boat",
    "ballon": "flask", "ampoule": "ampoule", "tube": "tube",
    "autoclave": "autoclave", "bombe": "bomb", "etuve": "oven",
    "mortier": "mortar", "cellule": "cell", "cuve": "vessel",
    "platine": "platinum", "quartz": "quartz", "acier": "steel",
    "verre": "glass", "alumine": "alumina", "silice": "silica",
    "teflon": "teflon", "zirconium": "zirconium", "argent": "silver",
}

# Le « C » nu apres un nombre est admis (les PDF perdent souvent le degre),
# mais « discharged at 0.15 C » est un REGIME de batterie, pas une temperature —
# constate sur broyage_na. Le degre explicite, lui, reste sur.
TEMP = re.compile(r"(-?\d+(?:[.,]\d+)?)\s*(?:°\s*C|℃|\bdeg\s*C\b|(?<=\d)\s?C\b)"
                  r"(?!\s*(?:/|per\s)\s*(?:min|h|s|sec)|\s*min\s*-?\s*1)")
REGIME_BATTERIE = re.compile(
    r"\b(discharg\w*|charg\w*|C-rate|cycling|capacit\w*|coulombic)\b", re.I)
# Une entree de BIBLIOGRAPHIE porte des verbes et des nombres sans etre une
# consigne : « A density functional theory study of ... » a ete signale sur
# cvd_mos2 pour un « 2 h » qui n'existe pas dans le protocole.
REFERENCE = re.compile(
    r"\b(et\s+al\.|doi|arxiv|J\.\s*Am\.|Phys\.\s*Rev|Nat\.\s*Mater|"
    r"Adv\.\s*Mater|Chem\.\s*(?:Soc|Mater|Commun)|"
    r"a\s+(?:density\s+functional|first[- ]principles)\s+\w+\s+study)\b", re.I)
DUREE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(min\b|mins\b|minutes?\b|h\b|hrs?\b|"
                   r"hours?\b)", re.I)


class Rapport:
    def __init__(self):
        self.erreurs: list[str] = []
        self.signalements: list[str] = []
        self.n_ok = 0

    def erreur(self, papier, passe, msg):
        self.erreurs.append(f"[{papier}] P{passe} ERREUR : {msg}")

    def signale(self, papier, passe, msg):
        self.signalements.append(f"[{papier}] P{passe} a relire : {msg}")

    def ok(self):
        self.n_ok += 1


def texte_source(cle: str) -> str:
    f = ROOT / "logs" / f"odl_{cle}.txt"
    return f.read_text(encoding="utf-8") if f.exists() else ""


def phrases(txt: str) -> list[str]:
    return [" ".join(p.split()) for p in re.split(r"(?<=[.;])\s+", txt)]


def _valeurs(gold: dict, champ: str) -> list[float]:
    out = []
    for v in gold.get(champ) or []:
        try:
            out.append(float(v))
        except (TypeError, ValueError):
            pass
    return out


def _ecritures(v: float, duree: bool) -> list[str]:
    """Ecritures admissibles d'une valeur : la sienne, et en minutes si duree."""
    formes = [f"{v:g}"]
    if duree:
        mn = v * 60
        formes.append(f"{mn:g}")
        if abs(mn - round(mn)) < 0.01:
            formes.append(f"{round(mn):g}")
    return formes


def _present(txt: str, ecriture: str) -> bool:
    return bool(re.search(rf"(?<![\d.]){re.escape(ecriture)}(?![\d])", txt))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--gold", type=Path, action="append",
                    help="fichier de gold (repetable) ; defaut : les trois")
    ap.add_argument("--papier", help="ne verifier qu'un papier")
    ap.add_argument("--json", type=Path, help="ecrire le rapport en JSON")
    a = ap.parse_args()

    fichiers = a.gold or [ROOT / "data" / "gold" / g for g in GOLDS]
    rap = Rapport()
    vus = 0

    from tools.verifier_golds_passes import (
        passe1_sourcage, passe2_completude, passe3_attribution, passe4_coherence)

    for f in fichiers:
        data = json.loads(Path(f).read_text(encoding="utf-8"))
        for titre, gold in data.items():
            if titre.startswith("_"):
                continue
            cle = TITRE_VERS_CLE.get(titre, titre)
            if a.papier and cle != a.papier:
                continue
            txt = texte_source(cle)
            if not txt:
                rap.erreur(cle, 0, f"texte source absent (logs/odl_{cle}.txt) — "
                                   f"gold INVERIFIABLE")
                continue
            vus += 1
            rb = RouteBuilder(source_text=txt, target=gold.get("target", ""),
                              method_type=gold.get("method_type", ""))
            passe1_sourcage(cle, gold, txt, rb, rap)
            passe2_completude(cle, gold, txt, rap)
            passe3_attribution(cle, gold, txt, rap)
            passe4_coherence(cle, gold, txt, rap)

    print(f"\n{'=' * 74}\n{vus} gold(s) passes aux QUATRE verifications\n{'=' * 74}")
    if rap.erreurs:
        print(f"\n### {len(rap.erreurs)} ERREUR(S) — le gold affirme du faux\n")
        for e in rap.erreurs:
            print(f"  {e}")
    if rap.signalements:
        print(f"\n### {len(rap.signalements)} SIGNALEMENT(S) — a relire a la main\n")
        for s in rap.signalements:
            print(f"  {s}")
    print(f"\n{rap.n_ok} controles passes | {len(rap.erreurs)} erreurs | "
          f"{len(rap.signalements)} signalements")

    if a.json:
        a.json.write_text(json.dumps(
            {"controles_ok": rap.n_ok, "erreurs": rap.erreurs,
             "signalements": rap.signalements}, ensure_ascii=False, indent=2),
            encoding="utf-8")
        print(f"-> {a.json}")
    return 1 if rap.erreurs else 0


if __name__ == "__main__":
    sys.exit(main())
