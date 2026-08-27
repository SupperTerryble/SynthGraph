import json
import logging
import math
import re
from typing import Dict, Any, List, Optional

logger = logging.getLogger("SynthGraph.Validator")

# ==============================================================================
#  [V4.5/C1] BILAN ÉLÉMENTAIRE DÉTERMINISTE (zéro LLM, zéro VRAM)
#  Parseur de formules maison : parenthèses, hydrates (·6H2O), stœchiométries
#  décimales, notations dopage 'x' (présence seule). Remplace l'auto-déclaration
#  LLM de 'mass_balance_mathematically_verified'.
# ==============================================================================

ELEMENTS = {
    "H","He","Li","Be","B","C","N","O","F","Ne","Na","Mg","Al","Si","P","S","Cl","Ar",
    "K","Ca","Sc","Ti","V","Cr","Mn","Fe","Co","Ni","Cu","Zn","Ga","Ge","As","Se","Br","Kr",
    "Rb","Sr","Y","Zr","Nb","Mo","Tc","Ru","Rh","Pd","Ag","Cd","In","Sn","Sb","Te","I","Xe",
    "Cs","Ba","La","Ce","Pr","Nd","Pm","Sm","Eu","Gd","Tb","Dy","Ho","Er","Tm","Yb","Lu",
    "Hf","Ta","W","Re","Os","Ir","Pt","Au","Hg","Tl","Pb","Bi","Po","At","Rn",
    "Fr","Ra","Ac","Th","Pa","U","Np","Pu","Am","Cm","Bk","Cf","Es","Fm","Md","No","Lr",
    "Rf","Db","Sg","Bh","Hs","Mt","Ds","Rg","Cn","Nh","Fl","Mc","Lv","Ts","Og",
}

# Éléments qui peuvent légitimement venir de l'environnement (air, eau) —
# leur absence des précurseurs n'est PAS une erreur de bilan.
_ENVIRONMENT_ELEMENTS = {"O", "H", "N"}

_TOKEN_RE = re.compile(r"([A-Z][a-z]?)(\d*\.?\d*)|(\()|(\))(\d*\.?\d*)")


def parse_composition(formula: str) -> Dict[str, float]:
    """Parse une formule chimique en {élément: quantité approx}.

    Tolérant aux notations réelles des papiers : 'SrCl2·6H2O', '(NH4)2SO4',
    'Sr2Ir1-xRuxO4' (les quantités en 'x' comptent comme présence, qty>0).
    Renvoie {} si la formule est illisible. Les quantités servent d'indication ;
    la garantie déterministe porte sur la PRÉSENCE des éléments.

    [Étape A] Si le parsing direct échoue, tente une normalisation nom→formule
    (`normalize_compound_name`) avant de conclure à l'illisibilité — permet de
    parser les précurseurs en prose verbatim (« silicon nanoparticles »,
    « cobalt(II) chloride ») produits par certains extracteurs (NuExtract).
    """
    formula = _normalize_hydrate_dot(formula)
    direct = _parse_composition_raw(formula)
    if direct:
        return direct
    normalized = normalize_compound_name(formula)
    if normalized and normalized != formula:
        return _parse_composition_raw(normalized)
    return {}


# Un point suivi d'un coefficient puis d'une molécule d'hydratation est un
# SÉPARATEUR d'hydrate, jamais un décimal. Les papiers (et le modèle) écrivent
# couramment « Fe(NO3)2.9H2O » avec un point ASCII au lieu du point médian.
_HYDRATE_DOT_RE = re.compile(r"\.(?=\s*\d*\s*H2O\b)", re.IGNORECASE)


def _normalize_hydrate_dot(formula: str) -> str:
    """« Fe(NO3)2.9H2O » → « Fe(NO3)2·9H2O ».

    Sans cela le parseur lisait « 2.9 » comme un décimal : N=2,9 et O=9,7 au
    lieu de N=2, O=15, H=18. Le bilan élémentaire sert de VETO dans le pipeline
    (un bilan en échec force REJECT quoi que dise le LLM) : une stœchiométrie
    corrompue pouvait donc rejeter une extraction correcte, ou en valider une
    fausse. Trois précurseurs de `combu_ferrite` sont écrits ainsi.
    """
    if not formula or not isinstance(formula, str):
        return formula
    return _HYDRATE_DOT_RE.sub("·", formula)


def _parse_composition_raw(formula: str) -> Dict[str, float]:
    """Corps original de `parse_composition` (parsing direct, sans normalisation)."""
    if not formula or not isinstance(formula, str):
        return {}
    # Nettoyage : LaTeX résiduel, indices unicode, espaces
    f = formula.strip()
    f = re.sub(r"\\text\{([^}]*)\}", r"\1", f).replace("$", "")
    subs = str.maketrans("₀₁₂₃₄₅₆₇₈₉", "0123456789")
    f = f.translate(subs).replace(" ", "")
    # Notations dopage : '1-x', '2-2x', 'x' → remplacées par une quantité symbolique 1
    f = re.sub(r"\d*\.?\d*-\d*\.?\d*x", "1", f)
    f = re.sub(r"(?<=[A-Za-z)])x(?![aeg])", "1", f)  # 'Rux' → 'Ru1' (évite Xe/Xn faux positifs)

    total: Dict[str, float] = {}
    # Segments d'hydrates / adduits : SrCl2·6H2O → ['SrCl2', '6H2O']
    for segment in re.split(r"[·•⋅*]", f):
        m = re.match(r"^(\d+\.?\d*)(.+)$", segment)
        mult = float(m.group(1)) if m else 1.0
        body = m.group(2) if m else segment

        stack: List[Dict[str, float]] = [{}]
        i = 0
        while i < len(body):
            ch = body[i]
            if ch == "(" or ch == "[":
                stack.append({})
                i += 1
            elif ch == ")" or ch == "]":
                grp = stack.pop() if len(stack) > 1 else {}
                i += 1
                num = ""
                while i < len(body) and (body[i].isdigit() or body[i] == "."):
                    num += body[i]; i += 1
                k = float(num) if num else 1.0
                for el, q in grp.items():
                    stack[-1][el] = stack[-1].get(el, 0.0) + q * k
            elif ch.isupper():
                sym = ch
                if i + 1 < len(body) and body[i + 1].islower():
                    sym2 = body[i:i + 2]
                    if sym2 in ELEMENTS:
                        sym = sym2
                i += len(sym)
                if sym not in ELEMENTS:
                    return {}  # symbole inconnu → formule illisible, on ne devine pas
                num = ""
                while i < len(body) and (body[i].isdigit() or body[i] == "."):
                    num += body[i]; i += 1
                q = float(num) if num else 1.0
                stack[-1][sym] = stack[-1].get(sym, 0.0) + q
            else:
                return {}  # caractère inattendu → illisible
        merged = stack[0]
        for grp in stack[1:]:  # parenthèse non fermée : on garde la présence
            for el, q in grp.items():
                merged[el] = merged.get(el, 0.0) + q
        for el, q in merged.items():
            total[el] = total.get(el, 0.0) + q * mult
    return total


# ==============================================================================
#  [Étape A] NORMALISEUR NOM→FORMULE DÉTERMINISTE
#  Certains extracteurs (NuExtract, verbatim par construction) rendent les
#  précurseurs en prose : « silicon nanoparticles », « cobalt(II) chloride »,
#  « lithium iodide ». `parse_composition`/`molar_mass` attendent des formules
#  (Si, CoCl2, LiI). Règle d'or : dictionnaire FERMÉ + patterns génériques
#  UNIQUEMENT quand la valence est explicite dans le nom ou le sel est dans le
#  dico — jamais de devinette de valence. Introuvable/ambigu → None.
# ==============================================================================

# Noms d'éléments (anglais + quelques alias français usuels) → symbole.
ELEMENT_NAME_TO_SYMBOL: Dict[str, str] = {
    "hydrogen": "H", "hydrogène": "H",
    "lithium": "Li", "beryllium": "Be", "boron": "B", "bore": "B",
    "carbon": "C", "carbone": "C",
    "nitrogen": "N", "azote": "N",
    "oxygen": "O", "oxygène": "O",
    "fluorine": "F", "fluor": "F",
    "sodium": "Na", "magnesium": "Mg", "aluminum": "Al", "aluminium": "Al",
    "silicon": "Si", "silicium": "Si",
    "phosphorus": "P", "phosphore": "P",
    "sulfur": "S", "sulphur": "S", "soufre": "S",
    "chlorine": "Cl", "chlore": "Cl",
    "potassium": "K", "calcium": "Ca", "scandium": "Sc",
    "titanium": "Ti", "titane": "Ti",
    "vanadium": "V",
    "chromium": "Cr", "chrome": "Cr",
    "manganese": "Mn", "manganèse": "Mn",
    "iron": "Fe", "fer": "Fe",
    "cobalt": "Co",
    "nickel": "Ni",
    "copper": "Cu", "cuivre": "Cu",
    "zinc": "Zn",
    "gallium": "Ga", "germanium": "Ge",
    "arsenic": "As", "selenium": "Se", "sélénium": "Se",
    "bromine": "Br", "brome": "Br",
    "rubidium": "Rb",
    "strontium": "Sr",
    "yttrium": "Y",
    "zirconium": "Zr",
    "niobium": "Nb", "molybdenum": "Mo", "molybdène": "Mo",
    "ruthenium": "Ru", "ruthénium": "Ru",
    "rhodium": "Rh", "palladium": "Pd",
    "silver": "Ag", "argent": "Ag",
    "cadmium": "Cd", "indium": "In",
    "tin": "Sn", "étain": "Sn",
    "antimony": "Sb", "antimoine": "Sb",
    "tellurium": "Te", "tellure": "Te",
    "iodine": "I", "iode": "I",
    "cesium": "Cs", "caesium": "Cs",
    "barium": "Ba", "baryum": "Ba",
    "lanthanum": "La", "lanthane": "La",
    "cerium": "Ce", "cérium": "Ce",
    "praseodymium": "Pr", "neodymium": "Nd", "néodyme": "Nd",
    "samarium": "Sm", "europium": "Eu",
    "gadolinium": "Gd", "terbium": "Tb", "dysprosium": "Dy",
    "holmium": "Ho", "erbium": "Er", "thulium": "Tm",
    "ytterbium": "Yb", "lutetium": "Lu",
    "hafnium": "Hf", "tantalum": "Ta", "tantale": "Ta",
    "tungsten": "W", "wolfram": "W", "tungstène": "W",
    "rhenium": "Re", "rhénium": "Re", "osmium": "Os",
    "iridium": "Ir", "platinum": "Pt", "platine": "Pt",
    "gold": "Au",
    "mercury": "Hg", "mercure": "Hg",
    "thallium": "Tl", "lead": "Pb", "plomb": "Pb",
    "bismuth": "Bi",
    "thorium": "Th", "uranium": "U",
}

# Noms classiques (-ic/-ous) où la valence du cation est EXPLICITE dans le nom
# lui-même (pas une devinette : c'est la fonction grammaticale du suffixe).
CATION_VALENCE_ALIASES: Dict[str, tuple] = {
    "cupric": ("Cu", 2), "cuprous": ("Cu", 1),
    "ferric": ("Fe", 3), "ferrous": ("Fe", 2),
    "stannic": ("Sn", 4), "stannous": ("Sn", 2),
    "plumbic": ("Pb", 4), "plumbous": ("Pb", 2),
    "mercuric": ("Hg", 2), "mercurous": ("Hg", 1),
    "auric": ("Au", 3), "aurous": ("Au", 1),
}

# Anions courants : nom → (formule, charge absolue, polyatomique?).
# Polyatomique = entouré de parenthèses si le sous-indice final est > 1.
ANION_MAP: Dict[str, tuple] = {
    "chloride": ("Cl", 1, False),
    "bromide": ("Br", 1, False),
    "iodide": ("I", 1, False),
    "fluoride": ("F", 1, False),
    "oxide": ("O", 2, False),
    "hydroxide": ("OH", 1, True),
    "nitrate": ("NO3", 1, True),
    "sulfate": ("SO4", 2, True),
    "sulphate": ("SO4", 2, True),
    "carbonate": ("CO3", 2, True),
    "acetate": ("CH3COO", 1, True),
}

_ROMAN_VALENCE = {"I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6}

_HYDRATE_N = {
    "hemi": 0.5, "mono": 1, "di": 2, "tri": 3, "tetra": 4, "penta": 5,
    "hexa": 6, "hepta": 7, "octa": 8, "nona": 9, "deca": 10,
}

# Dictionnaire fermé de composés usuels de synthèse inorganique. Utilisé quand
# la valence du cation n'est PAS explicite dans le nom (ex. « zinc chloride »)
# mais que le sel est un cas connu et non ambigu.
COMPOUND_NAME_TO_FORMULA: Dict[str, str] = {
    "lithium iodide": "LiI", "potassium iodide": "KI", "sodium iodide": "NaI",
    "sodium hydroxide": "NaOH", "potassium hydroxide": "KOH", "lithium hydroxide": "LiOH",
    "zinc acetate": "Zn(CH3COO)2", "copper acetate": "Cu(CH3COO)2",
    "nickel acetate": "Ni(CH3COO)2", "lead acetate": "Pb(CH3COO)2",
    "sodium acetate": "NaCH3COO",
    "zinc chloride": "ZnCl2",
    "silver nitrate": "AgNO3", "silver chloride": "AgCl", "silver oxide": "Ag2O",
    "ammonium metavanadate": "NH4VO3", "ammonium nitrate": "NH4NO3",
    "ammonium chloride": "NH4Cl", "ammonium sulfate": "(NH4)2SO4",
    "ammonium carbonate": "(NH4)2CO3", "ammonium hydroxide": "NH4OH",
    "strontium carbonate": "SrCO3", "strontium oxide": "SrO",
    "strontium nitrate": "Sr(NO3)2", "strontium hydroxide": "Sr(OH)2",
    "strontium chloride": "SrCl2", "strontium sulfate": "SrSO4",
    # Iridium/ruthénium : le corpus de validation porte sur Sr2IrO4 et
    # Sr2Ir(1-x)RuxO4, or « iridium dioxide » n'était pas reconnu — un modèle
    # nommant les composés en toutes lettres était compté à tort comme muet.
    "iridium oxide": "IrO2", "iridium dioxide": "IrO2",
    "iridium(iv) oxide": "IrO2", "iridium tetraoxide": "IrO2",
    "ruthenium oxide": "RuO2", "ruthenium dioxide": "RuO2",
    "ruthenium(iv) oxide": "RuO2",
    "titanium tetraisopropoxide": "Ti(OC3H7)4",
    "titanium dioxide": "TiO2", "titanium oxide": "TiO2",
    "cerium nitrate": "Ce(NO3)3", "cerium oxide": "CeO2", "ceria": "CeO2",
    "cobalt chloride": "CoCl2", "cobalt nitrate": "Co(NO3)2", "cobalt oxide": "CoO",
    "manganese nitrate": "Mn(NO3)2", "manganese chloride": "MnCl2",
    "nickel nitrate": "Ni(NO3)2", "nickel chloride": "NiCl2", "nickel oxide": "NiO",
    "sodium carbonate": "Na2CO3", "potassium carbonate": "K2CO3",
    "sodium chloride": "NaCl", "potassium chloride": "KCl",
    "lithium carbonate": "Li2CO3", "lithium chloride": "LiCl", "lithium nitrate": "LiNO3",
    "sodium nitrate": "NaNO3", "potassium nitrate": "KNO3",
    "sodium sulfate": "Na2SO4", "potassium sulfate": "K2SO4",
    "calcium carbonate": "CaCO3", "calcium oxide": "CaO",
    "calcium hydroxide": "Ca(OH)2", "calcium nitrate": "Ca(NO3)2", "calcium chloride": "CaCl2",
    "barium carbonate": "BaCO3", "barium nitrate": "Ba(NO3)2",
    "barium oxide": "BaO", "barium hydroxide": "Ba(OH)2", "barium chloride": "BaCl2",
    "zinc oxide": "ZnO", "zinc nitrate": "Zn(NO3)2", "zinc sulfate": "ZnSO4",
    "copper nitrate": "Cu(NO3)2", "copper sulfate": "CuSO4", "copper chloride": "CuCl2",
    "copper oxide": "CuO", "cupric chloride": "CuCl2", "cuprous chloride": "CuCl",
    "ferric chloride": "FeCl3", "ferrous chloride": "FeCl2",
    "ferric nitrate": "Fe(NO3)3", "ferrous sulfate": "FeSO4",
    "ferric oxide": "Fe2O3", "ferrous oxide": "FeO",
    "stannous chloride": "SnCl2", "stannic chloride": "SnCl4", "tin oxide": "SnO2",
    "lead nitrate": "Pb(NO3)2", "lead chloride": "PbCl2",
    "silicon dioxide": "SiO2", "silica": "SiO2",
    "aluminum oxide": "Al2O3", "aluminium oxide": "Al2O3", "alumina": "Al2O3",
    "yttrium oxide": "Y2O3", "yttria": "Y2O3",
    "lanthanum oxide": "La2O3",
    "zirconium oxide": "ZrO2", "zirconia": "ZrO2",
    "vanadium pentoxide": "V2O5",
    "niobium oxide": "Nb2O5", "tantalum oxide": "Ta2O5",
    "molybdenum oxide": "MoO3", "tungsten oxide": "WO3",
    "gallium oxide": "Ga2O3", "indium oxide": "In2O3", "germanium oxide": "GeO2",
    "boron oxide": "B2O3", "boric acid": "H3BO3",
    "oxalic acid": "H2C2O4", "citric acid": "C6H8O7", "urea": "CH4N2O",
    # Organiques usuels de la chimie de solution. Sans eux, un papier qui les
    # nomme en toutes lettres — la norme hors ceramique — voyait ses reactifs
    # non reconcilies avec leur formule : mesure faussee ET validateur trop
    # strict. Constate sur `hydro_czts` (L-cysteine, EDTA tous deux correctement
    # extraits mais comptes absents) et `cbd_mnse` (triethanolamine).
    "l-cysteine": "C3H7NO2S", "cysteine": "C3H7NO2S",
    "edta": "C10H16N2O8",
    "ethylenediaminetetraacetic acid": "C10H16N2O8",
    "ascorbic acid": "C6H8O6", "l-ascorbic acid": "C6H8O6",
    # ACIDES MINERAUX ET BASES COURANTS — mesure du 21/08 : 16 noms usuels sur
    # 31 testes etaient absents, dont TOUS les acides mineraux. Consequence
    # constatee sur `electro_nico` : « nitric acid » et « ethylamine », pourtant
    # ecrits en toutes lettres dans la citation, ne pouvaient prouver aucune
    # formule — les deux reactifs de la premiere synthese du papier etaient
    # refuses a chaque tour, 8 refus sur 14 appels.
    "nitric acid": "HNO3", "hydrochloric acid": "HCl",
    "muriatic acid": "HCl", "sulfuric acid": "H2SO4",
    "sulphuric acid": "H2SO4", "phosphoric acid": "H3PO4",
    "hydrofluoric acid": "HF", "hydrobromic acid": "HBr",
    "acetic acid": "CH3COOH", "glacial acetic acid": "CH3COOH",
    "formic acid": "HCOOH", "perchloric acid": "HClO4",
    "ammonia": "NH3", "aqueous ammonia": "NH3", "ammonia solution": "NH3",
    "hydrogen peroxide": "H2O2", "hydrazine": "N2H4",
    "hydrazine hydrate": "N2H4",
    # ORGANIQUES ET ELEMENTS sous leur nom d'usage.
    "ethylamine": "C2H7N", "ethyl amine": "C2H7N",
    "glycerol": "C3H8O3", "glycerin": "C3H8O3",
    "toluene": "C7H8", "red phosphorus": "P", "white phosphorus": "P",
    "metallic sodium": "Na", "sodium metal": "Na",
    "molybdenum dioxide": "MoO2", "molybdenum trioxide": "MoO3",
    "triethanolamine": "C6H15NO3", "tea": "C6H15NO3",
    "starch": "C6H10O5",
    "ethanol": "C2H5OH", "ethyl alcohol": "C2H5OH", "ethyl-alcohol": "C2H5OH",
    "methanol": "CH3OH", "isopropanol": "C3H8O", "acetone": "C3H6O",
    "dioxane": "C4H8O2", "1,4-dioxane": "C4H8O2", "1-4 dioxane": "C4H8O2",
    "ethylene glycol": "C2H6O2", "glycine": "C2H5NO2",
    "polyvinylpyrrolidone": "C6H9NO", "pvp": "C6H9NO",
    "cetyltrimethylammonium bromide": "C19H42BrN", "ctab": "C19H42BrN",
    "ammonia carbonate": "(NH4)2CO3",
    # L'eau : solvant le plus frequent du corpus, absente du dictionnaire.
    "water": "H2O", "distilled water": "H2O", "deionized water": "H2O",
    "de-ionized water": "H2O", "deionised water": "H2O", "ultrapure water": "H2O",
    "eau": "H2O", "eau distillee": "H2O", "eau deionisee": "H2O",
}

_HYDRATE_SUFFIX_RE = re.compile(
    r"^(.+?)\s+(hemi|mono|di|tri|tetra|penta|hexa|hepta|octa|nona|deca)hydrate$")
_POWDER_NP_RE = re.compile(
    r"^(?:metallic\s+)?([a-z]+)\s+"
    r"(?:metal\s+powder|nanopowder|powder|nanoparticles?|metal)$")
_METALLIC_RE = re.compile(r"^metallic\s+([a-z]+)$")
_ROMAN_VALENCE_RE = re.compile(
    r"^([a-z]+)\s*\(\s*(i{1,3}|iv|vi|v)\s*\)\s+([a-z]+)$")
_CLASSICAL_ANION_RE = re.compile(r"^([a-z]+)\s+([a-z]+)$")


def _build_ionic_formula(cation_symbol: str, cation_valence: int,
                          anion_name: str) -> Optional[str]:
    """Construit une formule ionique (ex. Co + 2 + chloride → CoCl2) par
    équilibre de charge. Ne devine jamais l'anion : `anion_name` doit être
    dans `ANION_MAP`."""
    entry = ANION_MAP.get(anion_name)
    if not entry:
        return None
    anion_formula, anion_charge, polyatomic = entry
    g = math.gcd(int(cation_valence), int(anion_charge))
    cation_n = anion_charge // g
    anion_n = cation_valence // g
    cation_part = cation_symbol + (str(cation_n) if cation_n > 1 else "")
    if anion_n > 1:
        anion_part = f"({anion_formula}){anion_n}" if polyatomic else f"{anion_formula}{anion_n}"
    else:
        anion_part = anion_formula
    return cation_part + anion_part


def normalize_compound_name(name: str) -> Optional[str]:
    """Normalise un nom de composé en prose vers une formule chimique parsable.

    Ordre de résolution (fail-safe strict, jamais de devinette) :
      0. Déjà une formule valide (`parse_composition` la lit) → renvoyée telle quelle.
      1. Suffixe hydrate en toutes lettres (« ... dihydrate ») → normalise la
         base récursivement puis ajoute « ·nH2O ».
      2. Dictionnaire fermé (~90 composés usuels, valence non ambiguë).
      3. Nom d'élément seul (anglais/français).
      4. Motifs génériques « X metal powder » / « X powder » / « X nanoparticles »
         / « metallic X » → symbole de l'élément X.
      5. « élément(valence romaine) anion » ou « cation-classique anion »
         (cupric, ferrous, ...) → formule construite par équilibre de charge,
         UNIQUEMENT si la valence est explicite dans le nom.
      Sinon → None (introuvable ou ambigu, jamais de supposition).
    """
    if not name or not isinstance(name, str):
        return None
    raw = name.strip()
    if not raw:
        return None

    if _parse_composition_raw(raw):
        return raw

    low = re.sub(r"\s+", " ", raw.lower().strip())
    low = low.rstrip(".,;")

    m_hyd = _HYDRATE_SUFFIX_RE.match(low)
    if m_hyd:
        base, prefix = m_hyd.group(1), m_hyd.group(2)
        n = _HYDRATE_N[prefix]
        base_formula = normalize_compound_name(base)
        if base_formula:
            n_str = str(int(n)) if float(n) == int(n) else str(n)
            return f"{base_formula}·{n_str}H2O"
        return None

    if low in COMPOUND_NAME_TO_FORMULA:
        return COMPOUND_NAME_TO_FORMULA[low]

    if low in ELEMENT_NAME_TO_SYMBOL:
        return ELEMENT_NAME_TO_SYMBOL[low]

    m = _POWDER_NP_RE.match(low) or _METALLIC_RE.match(low)
    if m:
        elname = m.group(1)
        return ELEMENT_NAME_TO_SYMBOL.get(elname)

    m = _ROMAN_VALENCE_RE.match(low)
    if m:
        elname, roman, anion_name = m.group(1), m.group(2).upper(), m.group(3)
        cation_symbol = ELEMENT_NAME_TO_SYMBOL.get(elname)
        cation_valence = _ROMAN_VALENCE.get(roman)
        if cation_symbol and cation_valence:
            built = _build_ionic_formula(cation_symbol, cation_valence, anion_name)
            if built:
                return built

    m = _CLASSICAL_ANION_RE.match(low)
    if m and m.group(1) in CATION_VALENCE_ALIASES:
        cation_symbol, cation_valence = CATION_VALENCE_ALIASES[m.group(1)]
        built = _build_ionic_formula(cation_symbol, cation_valence, m.group(2))
        if built:
            return built

    return None


def element_balance_report(precursors: List[str], target: str,
                           flux_or_solvents: List[str] = None) -> Optional[Dict[str, Any]]:
    """Vérifie DÉTERMINISTIQUEMENT que chaque élément de la cible est fourni
    par au moins un précurseur (O/H/N exclus : atmosphère/eau).

    Returns None si la cible est illisible (on ne conclut pas sur du bruit OCR).
    Sinon : {"ok": bool, "missing_elements": [...], "unused_elements": [...],
             "detail": str résumé lisible pour le prompt du Thermodynamicien}.
    """
    target_comp = parse_composition(target)
    if not target_comp:
        logger.warning(f"[Stoich] Formule cible illisible : {target!r} — pas de verdict déterministe.")
        return None

    supplied: Dict[str, float] = {}
    parsed_precs, unparsed_precs = [], []
    for p in precursors or []:
        comp = parse_composition(p)
        if comp:
            parsed_precs.append(p)
            for el, q in comp.items():
                supplied[el] = supplied.get(el, 0.0) + q
        elif p:
            unparsed_precs.append(str(p))

    missing = sorted(set(target_comp) - set(supplied) - _ENVIRONMENT_ELEMENTS)
    unused = sorted(set(supplied) - set(target_comp) - _ENVIRONMENT_ELEMENTS - {"C", "Cl", "F", "S"})

    if unparsed_precs and missing:
        # Un précurseur illisible pourrait fournir l'élément 'manquant' → pas de veto aveugle
        ok, verdict = None, "INDÉTERMINÉ"
        detail = (f"Éléments {missing} non trouvés dans les précurseurs lisibles, mais "
                  f"{len(unparsed_precs)} précurseur(s) illisible(s) ({unparsed_precs[:3]}) "
                  f"pourraient les fournir. Vérification manuelle requise.")
    elif missing:
        ok, verdict = False, "ÉCHEC"
        detail = (f"BILAN ÉLÉMENTAIRE INCOMPLET : la cible {target} contient {missing} "
                  f"qu'AUCUN précurseur ({', '.join(parsed_precs) or 'aucun'}) ne fournit.")
    else:
        ok, verdict = True, "OK"
        detail = (f"Bilan élémentaire OK : tous les éléments de {target} "
                  f"(hors O/H/N environnementaux) sont fournis par les précurseurs.")
        if unused:
            detail += f" Éléments excédentaires (flux/volatils probables) : {unused}."

    return {"ok": ok, "verdict": verdict, "missing_elements": missing,
            "unused_elements": unused, "unparsed_precursors": unparsed_precs,
            "target_composition": target_comp, "detail": detail}

def compute_stoichiometry_report(precursors: List[str], target: str) -> str:
    """Utilise chempy pour vérifier si les précurseurs peuvent former la cible."""
    try:
        from chempy.util import parsing
        from chempy import Substance
    except ImportError:
        return "ERREUR: chempy non installé. Impossible de vérifier la stœchiométrie."

    try:
        # Nettoyage
        target_sub = Substance.from_formula(target)
        target_elements = target_sub.composition
        
        precursor_elements = {}
        for p in precursors:
            try:
                sub = Substance.from_formula(p)
                for el, count in sub.composition.items():
                    precursor_elements[el] = precursor_elements.get(el, 0) + count
            except:
                pass # Ignorer les formules illisibles
        
        missing = set(target_elements.keys()) - set(precursor_elements.keys())
        missing.discard(0) # Remove empty keys if any
        
        # Souvent l'oxygène vient de l'air
        missing.discard(8) # L'oxygène a le numéro atomique 8 dans chempy composition, ou on utilise les noms
        
        # Dans chempy, la composition utilise les numéros atomiques par défaut
        # On va simplifier en utilisant une extraction regex basique si chempy est trop strict
        
        if missing:
            return f"AVERTISSEMENT: Éléments possibles manquants {missing} pour former {target}."
        return "OK: Les précurseurs contiennent tous les éléments de base de la cible."
    except Exception as e:
        return f"ERREUR d'analyse stœchiométrique : {e}"

def classify_synthesis_method(text: str, current_method: str) -> str:
    """Arbre de décision déterministe pour classer la méthode."""
    text_lower = text.lower()
    
    # 1. Vérifier si c'est vraiment un Sol-Gel
    if "sol-gel" in current_method.lower():
        if not any(k in text_lower for k in ["gel", "citric acid", "sol ", "chelating"]):
            # Si on parle de broyage et cuisson, c'est solid-state
            if any(k in text_lower for k in ["mortar", "pestle", "grind", "pellet"]):
                return "solid-state"
            
    # 2. Vérifier si c'est un flux
    if "flux" in text_lower and any(k in text_lower for k in ["kcl", "nacl", "pbof2", "lif"]):
        return "flux_growth"
        
    return current_method

def classify_solvent(name: str, temp_c: float = None) -> str:
    """Dictionnaire des sels fondus pour différencier Flux et Solvant liquide."""
    fluxes = ["kcl", "nacl", "pbof2", "k2co3", "na2co3", "baocl2", "bif3", "lif"]
    name_lower = name.lower().strip()
    
    for f in fluxes:
        if f in name_lower:
            if temp_c and temp_c > 500:
                return "FLUX (Sel fondu)"
            
    if any(k in name_lower for k in ["water", "h2o", "ethanol", "methanol", "acid"]):
        return "SOLVENT (Liquide)"
        
    return "INCONNU"
