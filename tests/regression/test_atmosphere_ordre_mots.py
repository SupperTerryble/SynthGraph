"""L'atmosphere doit se lire quel que soit l'ORDRE DES MOTS.

Mesure du corpus9 (20/08) : tous les motifs de `_ATM_MARKERS` exigent le gaz
APRES « in/under ». Des que la phrase l'enonce en SUJET, l'atmosphere est
perdue — et avec elle la seule mention du papier :

  cvd_mos2      « argon (99.999%) was used as the carrier gas »
  electro_nico  « argon was bubbled in the electrolyte for 15 minutes »

Deux papiers sur quatre perdaient ainsi toute leur atmosphere pour une seule
raison de syntaxe. Deux autres tournures manquaient pour des causes distinctes :
le qualificatif de « under DYNAMIC vacuum » (l'etape de reaction de 6 h de
selfondu_cosi) et la boite a gants, qui ne nomme aucun gaz.

REGLE D'OR : elargir la reconnaissance ne doit JAMAIS elargir l'invention. Les
cas negatifs de ce fichier comptent autant que les positifs — une negation
(« without argon ») et une boite a gants sans gaz nomme ne doivent rien donner.
"""
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from synthgraph.extraction.graph_tools import RouteBuilder as R  # noqa: E402

ok = fail = 0


def ck(label, cond):
    global ok, fail
    if cond:
        ok += 1
        print(f"  OK    {label}")
    else:
        fail += 1
        print(f"  ECHEC {label}")


def detect(citation):
    """Meme logique que `_recover_atmosphere` : premier motif, sauf negation."""
    for pat, val in R._ATM_MARKERS:
        m = re.search(pat, citation, re.I)
        if m and not R._ATM_NEGATION.search(citation[max(0, m.start() - 40):m.start()]):
            return val
    return None


print("\n=== 1. ORDRE INVERSE : le gaz est SUJET (cas reels du corpus9) ===")
ck("cvd_mos2 : « argon (99.999%) was used as the carrier gas »",
   detect("argon (99.999%) was used as the carrier gas, with an optimized "
          "flow rate of 200 standard-state cubic centimeter per minute") == "Ar")
ck("electro_nico : « argon was bubbled in the electrolyte »",
   detect("Before electrochemical measurements, argon was bubbled in the "
          "electrolyte for 15 minutes.") == "Ar")
ck("« Ar was introduced as carrier gas »",
   detect("Ar was introduced as carrier gas") == "Ar")
ck("« N2 was purged through the reactor »",
   detect("N2 was purged through the reactor before heating") == "N2")

print("\n=== 2. l'ordre DIRECT continue de passer (non-regression) ===")
ck("« under flowing argon »", detect("the sample was heated under flowing argon") == "Ar")
ck("« in air »", detect("calcined in air at 900 C") == "air")
ck("« in flowing 02 » (zero d'OCR, PhysRevB)",
   detect("heated in flowing 02 for 12 h") == "O2")

print("\n=== 3. VIDE : un qualificatif ne doit pas faire perdre l'atmosphere ===")
ck("selfondu_cosi : « under dynamic vacuum (10-3 mbar) »",
   detect("followed by 6 hours of thermal treatment under dynamic vacuum "
          "(10-3 mbar)") == "vacuum")
ck("« under primary vacuum »", detect("dried under primary vacuum") == "vacuum")
ck("« evacuated under vacuum » (deja acquis)",
   detect("the quartz tube was evacuated under vacuum") == "vacuum")

print("\n=== 4. REGLE D'OR : une negation ne donne RIEN ===")
ck("« without argon protection »",
   detect("the reaction was run without argon protection") is None)
ck("« in the absence of flowing N2 »",
   detect("performed in the absence of flowing N2") is None)
ck("« air-sensitive » n'est pas une atmosphere",
   detect("the air-sensitive powder was stored in a bottle") is None)

print("\n=== 5. REGLE D'OR : la boite a gants ne NOMME aucun gaz ===")
# Sans nom de gaz, deduire « inerte » serait une invention. C'est un trou a
# declarer, pas une valeur. broyage_na ne passe que parce que « Ar-filled »
# nomme l'argon — pas parce que « glove box » vaudrait quelque chose.
ck("« performed in the glove box » seul : aucune atmosphere",
   detect("All alloys electroplating were performed in the glove box") is None)
ck("« in an Ar-filled glove box » : l'argon EST nomme",
   detect("filled into a jar in an Ar-filled glove box") == "Ar")

print("\n=== 6. fail-safe ===")
ck("citation vide", detect("") is None)
ck("citation sans atmosphere", detect("ball-milled for 2 h at 20 Hz") is None)

print(f"\n{ok} OK / {fail} ECHECS")
sys.exit(1 if fail else 0)
