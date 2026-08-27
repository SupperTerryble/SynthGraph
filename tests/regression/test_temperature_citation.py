"""La TEMPERATURE ecrite dans la citation doit etre lue, comme la duree.

ASYMETRIE constatee le 21/08 : `add_operation` recupere la duree ecrite dans la
citation quand le modele omet le champ, mais rien n'existait pour la
temperature. Cas mesure sur `electro_nico`, etape 1 :

    « Solutions of 0.25 M NiCl2 + 0.25 M CoCl2 in EAN were prepared by mixing
      the different compounds under stirring at 70°C for 24 h after weighing »

    duration_h = 24.0  (recuperee)      target_temperature_c = None

Les deux valeurs sont dans la MEME phrase, a quatre mots l'une de l'autre. Seule
celle qui avait un mecanisme etait retrouvee. La temperature est l'axe le plus
faible du corpus : 0 % sur deux papiers, 66,7 % sur deux autres.

REGLE D'OR : la citation doit porter UNE SEULE temperature distincte. Deux, ce
sont deux etapes — on ne peut pas dire laquelle appartient a celle-ci, donc on
s'abstient. Meme raisonnement que pour les trois pH de `cbd_mnse`.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
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


def temp(citation, step_type="heating"):
    rb = RouteBuilder(source_text=citation, target="X", method_type="Y")
    rb.add_operation(step_type, citation)
    if not rb.operations:
        return None
    st = rb.operations[0]
    return st.get("temperature_c", st.get("target_temperature_c"))


print("\n=== 1. cas reels du corpus ===")
ck("electro_nico : « under stirring at 70°C for 24 h »",
   temp("the different compounds were mixed under stirring at 70°C for 24 h "
        "after weighing", "mixing") == 70.0)
ck("combu_ferrite : « on the magnetic stirrer at 65°C »",
   temp("The solution was allowed for gel formation on the magnetic stirrer "
        "at 65°C with constant stirring", "mixing") == 65.0)
ck("cbd_mnse : « remained for 3 hours at 50 ºC »",
   temp("The bath remained for 3 hours at 50 ºC", "soak") == 50.0)
ck("electro_nico : la NEGATIVE « (T = -10°C) »",
   temp("the acid was added drop by drop under stirring at a controlled "
        "temperature (T = -10°C)", "mixing") == -10.0)

print("\n=== 2. ecritures du degre malmenees par l'OCR ===")
ck("« 1300 ◦C » (anneau, crystal)", temp("the crucible was heated to 1300 ◦C") == 1300.0)
ck("« 180 ℃ » (caractere unique)", temp("heated at 180 ℃ for 12 h") == 180.0)
ck("« 900 C » (degre perdu)", temp("calcined at 900 C in air") == 900.0)

print("\n=== 3. REGLE D'OR : deux temperatures -> ABSTENTION ===")
# selfondu_cosi : « pre-heated to the reaction temperature 300 and 400 °C for
# core-shell and homogenous nanoparticles » = DEUX syntheses distinctes.
ck("« 300 and 400 °C » ne donne rien",
   temp("A vertical furnace was pre-heated to the reaction temperature 300 "
        "and 400 °C for core-shell and homogenous nanoparticles") is None)
ck("« heated to 300 °C ... then to 750 °C » ne donne rien",
   temp("the furnace was firstly heated to 300 °C for 10 min and then heated "
        "to 750 °C in 40 min") is None)
ck("la MEME temperature deux fois n'est pas une ambiguite",
   temp("held at 900 °C, reground, and reheated at 900 °C") == 900.0)

print("\n=== 4. REGLE D'OR : « room temperature » n'est PAS 25 °C ===")
# Le modele a deja tente `temperature_c=25` sur selfondu_cosi et la garde l'a
# refuse. Le rattrapage ne doit surtout pas faire entrer par la fenetre ce qui
# a ete refuse a la porte.
ck("« cooled down to room temperature »",
   temp("the hot quartz tube was taken out and cooled down to room "
        "temperature under vacuum", "cooling") is None)
ck("« at ambient temperature »",
   temp("the mixture was stirred at ambient temperature", "mixing") is None)

print("\n=== 5. PIEGES d'unites : un nombre voisin n'est pas une temperature ===")
ck("« 80 nm » ne donne rien", temp("FTO glass of 80 nm thickness was used") is None)
ck("« 0.2 cm2 » non plus", temp("an electrode of 0.2 cm2 surface area") is None)
ck("« 5 degree/min » est une RAMPE, pas un palier",
   temp("XRD was recorded with a scan rate of 5 degree/min") is None)
ck("« 20 Hz » non plus", temp("the mixture was milled at 20 Hz") is None)

print("\n=== 6. un APPAREIL de marque n'impose pas sa temperature ===")
# « (Freeze Dryer -86℃, OPERON CO., LTD.) » designe le materiel, pas la
# consigne : le -86 est la caracteristique du lyophilisateur.
ck("« (Freeze Dryer -86℃, OPERON CO., LTD.) »",
   temp("The purification was performed by lyophilization (Freeze Dryer "
        "-86℃, OPERON CO., LTD.)", "drying") is None)

print("\n=== 7. fail-safe et non-regression ===")
ck("citation sans temperature", temp("the powder was ground in a mortar") is None)
ck("citation vide", temp("") is None)
rb = RouteBuilder(source_text="held at 900 °C for 12 h", target="X", method_type="Y")
rb.add_operation("heating", "held at 900 °C for 12 h", temperature_c=900)
st = rb.operations[0]
ck("une temperature FOURNIE par le modele est conservee",
   (st.get("temperature_c") or st.get("target_temperature_c")) == 900.0)
ck("et la duree l'est aussi", st.get("duration_h") == 12.0)

print(f"\n{ok} OK / {fail} ECHECS")
sys.exit(1 if fail else 0)
