"""Le ratio se DEDUIT de la formule cible quand le texte dit « stoichiometric ».

DECISION DE TERRY (21/08) : « Deduction autorisee, sur preuve et tracee ».
Deduire un rapport d'une formule enoncee est une LECTURE, pas une invention —
c'est la meme famille que les deux inferences deja en place et testees
(`_infer_ratios_from_enumeration`, `_infer_ratios_from_amounts`).

Cas de reference, `broyage_na` : « Stoichiometric amounts of metallic sodium as
bulk and red phosphorus were filled into a jar ... to obtain Na3P particles ».
Aucune masse, aucune mole. Le rapport 3:1 est pourtant entierement determine par
la formule cible, elle-meme ecrite dans la phrase. Le pipeline rendait 0 % de
ratios sur ce papier, seul ecart d'un gold par ailleurs a l'egalite stricte.

TROIS CONDITIONS CUMULATIVES, sinon abstention :
  (a) la citation porte « stoichiometric » — la preuve que les proportions
      suivent la formule ;
  (b) la formule cible est enoncee dans la source ;
  (c) chaque precurseur apporte UN element identifiable de la cible.

TRACABILITE exigee par Terry : le ratio deduit porte `ratio_source`, pour qu'un
audit puisse toujours separer ce qui a ete LU de ce qui a ete CALCULE.
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


def ratios(cible, citation, formules):
    rb = RouteBuilder(source_text=citation, target=cible, method_type="X")
    for f in formules:
        rb.add_precursor(f, citation)
    rb._infer_ratios_from_target_formula()
    return {p["formula"]: p.get("molar_ratio") for p in rb.precursors}


NA3P = ("Stoichiometric amounts of metallic sodium as bulk and red phosphorus "
        "were ball-milled for 2 h to obtain Na3P particles.")

print("\n=== 1. cas reel broyage_na : Na3P ===")
r = ratios("Na3P", NA3P, ["Na", "P"])
ck("Na recoit 3", r.get("Na") == 3)
ck("P recoit 1", r.get("P") == 1)

print("\n=== 2. second cas propre du corpus : Sr2IrO4 ===")
SR = ("Stoichiometric amounts of SrCO3 and IrO2 were thoroughly mixed and "
      "heated to obtain Sr2IrO4.")
r = ratios("Sr2IrO4", SR, ["SrCO3", "IrO2"])
ck("SrCO3 recoit 2", r.get("SrCO3") == 2)
ck("IrO2 recoit 1", r.get("IrO2") == 1)

print("\n=== 3. TRACABILITE : le ratio deduit se distingue du ratio lu ===")
rb = RouteBuilder(source_text=NA3P, target="Na3P", method_type="X")
rb.add_precursor("Na", NA3P)
rb.add_precursor("P", NA3P)
rb._infer_ratios_from_target_formula()
ck("l'origine est enregistree",
   all(p.get("ratio_source") == "formule_cible" for p in rb.precursors))

print("\n=== 4. GARDE : sans le mot « stoichiometric », RIEN ===")
SANS = "Sodium and red phosphorus were ball-milled for 2 h to obtain Na3P."
r = ratios("Na3P", SANS, ["Na", "P"])
ck("aucun ratio deduit", r.get("Na") is None and r.get("P") is None)

print("\n=== 5. GARDE : un ratio DEJA connu n'est jamais ecrase ===")
rb = RouteBuilder(source_text=NA3P, target="Na3P", method_type="X")
rb.add_precursor("Na", NA3P)
rb.precursors[0]["molar_ratio"] = 7.0        # valeur lue ailleurs
rb.add_precursor("P", NA3P)
rb._infer_ratios_from_target_formula()
ck("le ratio lu est conserve", rb.precursors[0]["molar_ratio"] == 7.0)
ck("il n'est pas etiquete comme deduit",
   rb.precursors[0].get("ratio_source") != "formule_cible")

print("\n=== 6. GARDE : AMBIGUITE -> abstention complete ===")
# Deux precurseurs apportant le MEME element : impossible de repartir.
AMB = ("Stoichiometric amounts of SrO and SrCO3 and IrO2 were mixed to obtain "
       "Sr2IrO4.")
r = ratios("Sr2IrO4", AMB, ["SrO", "SrCO3", "IrO2"])
ck("aucun ratio n'est attribue", not any(v for v in r.values()))

print("\n=== 7. GARDE : une cible NON STOECHIOMETRIQUE ne se deduit pas ===")
# Le meme papier que broyage_na contient Na0.67[Fe0.5Mn0.5]O2.
NS = ("Stoichiometric amounts of Fe2O3 and MnO2 were mixed to obtain "
      "Na0.67[Fe0.5Mn0.5]O2.")
r = ratios("Na0.67[Fe0.5Mn0.5]O2", NS, ["Fe2O3", "MnO2"])
ck("abstention complete sur une cible a indices fractionnaires",
   all(v is None for v in r.values()))

print("\n=== 8. GARDE : un precurseur HORS cible bloque sa part ===")
# LiI et KI sont le BAIN de sels de selfondu_cosi, pas la stoechiometrie.
SEL = ("Stoichiometric amounts of Si and CoCl2 with LiI and KI were "
       "ball-milled to obtain CoSi.")
r = ratios("CoSi", SEL, ["Si", "CoCl2", "LiI", "KI"])
ck("Si et CoCl2 sont servis", r.get("Si") == 1 and r.get("CoCl2") == 1)
ck("LiI n'apporte aucun element de CoSi : rien", r.get("LiI") is None)
ck("KI non plus", r.get("KI") is None)

print("\n=== 9. PIEGE : l'OXYGENE n'identifie personne ===")
# Cible CuO. L'acetate de cuivre apporte Cu ; le carbonate d'ammonium apporte
# C, N, H et O — dont l'oxygene, present dans presque toutes les cibles. Le
# servir sur ce seul motif fabriquerait un rapport. On exige un element
# DISTINCTIF, et au moins DEUX precurseurs servis : un « 1 » solitaire sans son
# partenaire est trompeur, pas informatif.
CUO = ("mixing stoichiometric amounts of fresh aqueous copper acetate and "
       "ammonium carbonate to obtain CuO.")
r = ratios("CuO", CUO, ["Cu(CH3COO)2", "(NH4)2CO3"])
ck("abstention : un seul compose identifiable",
   all(v is None for v in r.values()))

print("\n=== 10. la cible est un LIBELLE, pas une formule ===")
# Defaut reel du 21/08 : AUCUNE cible de gold ne se decompose telle quelle —
# « Na3P (particules) », « nanoparticules de CoSi (coeur-coquille) », « MoS2
# (mono- et few-layer, sur graphene) ». Le mecanisme passait tous ses tests et
# ne se declenchait JAMAIS en production.
for libelle, attendu in (
        ("Na3P (particules)", {"Na": 3.0, "P": 1.0}),
        ("nanoparticules de CoSi (coeur-coquille)", {"Co": 1.0, "Si": 1.0}),
        ("MoS2 (mono- et few-layer, sur graphene)", {"Mo": 1.0, "S": 2.0}),
        ("Sr2IrO4", {"Sr": 2.0, "Ir": 1.0, "O": 4.0})):
    ck(f"« {libelle[:36]} »",
       RouteBuilder._formule_de_la_cible(libelle) == attendu)
ck("« particules fines » ne nomme aucun compose",
   RouteBuilder._formule_de_la_cible("particules fines") is None)
ck("« alliage Ni-Co » n'a pas de stoechiometrie",
   RouteBuilder._formule_de_la_cible("alliage Ni-Co (48 at% Co)") is None)

print("\n=== 11. le cas reel, avec le LIBELLE du gold ===")
r = ratios("Na3P (particules)", NA3P, ["Na", "P"])
ck("Na recoit 3 malgre le suffixe", r.get("Na") == 3)
ck("P recoit 1", r.get("P") == 1)

print("\n=== 12. fail-safe ===")
ck("cible vide", not any(ratios("", NA3P, ["Na", "P"]).values()))
ck("cible illisible", not any(ratios("!!!", NA3P, ["Na", "P"]).values()))
rb = RouteBuilder(source_text=NA3P, target="Na3P", method_type="X")
ck("aucun precurseur : ne plante pas",
   rb._infer_ratios_from_target_formula() == 0)

print(f"\n{ok} OK / {fail} ECHECS")
sys.exit(1 if fail else 0)
