"""CHAQUE valeur du gold existe-t-elle dans le papier ?

Un gold qui contient ce que la source n'enonce pas viole la meme regle d'or que
l'extraction — et fausse la mesure sans qu'on le voie. Deux erreurs de ce type
ont ete commises et corrigees le 20/08 :

  - trois ATMOSPHERES inferees (« air » deduit du procede) sur combu_ferrite,
    cbd_mnse et reduc_cu : indulgence, un pipeline qui devine aurait « reussi » ;
  - une RAMPE convertie (5 °C/min ecrit 300 °C/h) sur combu_ferrite : l'egalite
    stricte exigeait alors les DEUX ecritures, donc devenait inatteignable.

La seconde est passee parce que le verificateur d'origine ne controlait pas le
champ `ramp_rates_c_per_h`. Ce test parcourt donc TOUS les champs numeriques,
sans liste a maintenir a la main.
"""
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
ROOT = pathlib.Path(__file__).resolve().parents[2]

ok = fail = 0


def ck(label, cond):
    global ok, fail
    if cond:
        ok += 1
    else:
        fail += 1
        print(f"  ECHEC {label}")


_LIG = {ord(k): v for k, v in {"ﬀ": "ff", "ﬁ": "fi", "ﬂ": "fl",
                               "ﬃ": "ffi", "ﬄ": "ffl"}.items()}


def norm(s):
    s = (s or "").translate(_LIG).lower()
    s = re.sub(r"-\s+", "", s)
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", s)).strip()


import json  # noqa: E402

GOLDS = {
    "gold_corpus5.json": None,          # clés = clés de papier
    "gold_corpus9.json": None,
    "gold_sr2iro4.json": {
        "Crystal growth and intrinsic magnetic behaviour of Sr2IrO4": "crystal",
        "PhysRevB.49.11890": "physrev",
        "the-preparation-of-a-strontium-iridium-oxide-sr2iro41-2 (1)": "prepara",
    },
}

# Tout champ dont le nom annonce des valeurs numeriques. Parcourir la structure
# plutot qu'une liste figee : c'est l'oubli de `ramp_rates_c_per_h` dans le
# verificateur d'origine qui a laisse passer la conversion inventee.
_NUM = re.compile(r"(key_values|durations?_h|ramp_rates?|temperatures?|ph_values)")

for fichier, mapping in GOLDS.items():
    data = json.loads((ROOT / "data" / "gold" / fichier).read_text(encoding="utf-8"))
    for titre, g in data.items():
        cle = (mapping or {}).get(titre, titre)
        src_f = ROOT / "logs" / f"odl_{cle}.txt"
        if not src_f.exists():
            continue
        txt = src_f.read_text(encoding="utf-8")
        n = norm(txt)

        for champ, valeurs in g.items():
            if not _NUM.search(champ) or not isinstance(valeurs, list):
                continue
            for v in valeurs:
                try:
                    f = f"{float(v):g}"
                except (TypeError, ValueError):
                    continue
                # Une duree de 0,25 h est ecrite « 15 min » dans le papier : la
                # valeur EST sourcee, dans une autre unite. Le pipeline fait
                # deja cette conversion (`_value_in_minutes`), le verificateur
                # doit l'admettre aussi.
                formes = [f]
                if "duration" in champ or "key_values" in champ:
                    # ARRONDI : « 5 min » vaut 5/60 = 0,08333 h, et le retour en
                    # minutes donne 4,998 — qui ne correspond plus a « 5 ». Meme
                    # correctif que dans le comparateur : les deux mecanismes
                    # doivent tolerer la meme chose, sinon l'un accuse ce que
                    # l'autre accepte.
                    mn = float(v) * 60
                    formes.append(f"{mn:g}")
                    if abs(mn - round(mn)) < 0.01:
                        formes.append(f"{round(mn):g}")
                ck(f"{cle}: {champ}={f} absent du papier",
                   any(re.search(rf"(?<![\d.]){re.escape(x)}(?![\d])", txt)
                       for x in formes))

        # Les citations sont comparees avec la normalisation DU PIPELINE, qui
        # replie les confusables d'OCR : PhysRevB (1994) ecrit « Ir02 » et
        # « Ru02 » avec des zeros la ou le gold porte « IrO2 »/« RuO2 ».
        # Meme tolerance que le pipeline, et pour les memes raisons reelles :
        # confusables d'OCR (« Ir02 » pour IrO2) et surtout SAUT DE COLONNE —
        # PhysRevB est sur deux colonnes, et « were mixed in proportions to »
        # y est suivi d'un fragment de l'autre colonne. La couverture gloutonne
        # retrouve la phrase par fragments pris dans l'ordre.
        from synthgraph.extraction.graph_tools import RouteBuilder, _norm_words
        rb = RouteBuilder(source_text=txt, target="x", method_type="y")
        n_pipeline = _norm_words(txt)
        for c in g.get("citations", []):
            ck(f"{cle}: citation absente — {c[:55]}",
               norm(c) in n or _norm_words(c) in n_pipeline
               or rb._greedy_cover(_norm_words(c)))

print(f"\n{ok} OK / {fail} ECHECS  (valeurs du gold verifiees dans les sources)")
sys.exit(1 if fail else 0)
