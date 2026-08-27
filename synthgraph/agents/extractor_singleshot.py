"""
synthgraph/agents/extractor_singleshot.py — SynthGraph V4.4

Extracteur "single-shot" : UNE génération contrainte par un schéma PLAT et
grammaire-friendly, au lieu de la boucle de tool-calling (fragile sur un 8B) et
des schémas par-méthode à `GroundedFloat` imbriqués (grammaire GBNF trop lente).

Le schéma plat garde tout le détail utile (température, durée, rampe, atmosphère,
équipement, ratios, citations) tout en produisant une grammaire simple → rapide.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, AliasChoices, ConfigDict

from synthgraph.agents.base import SynthAgent
from synthgraph.schemas.step_schema import normalize_steps

logger = logging.getLogger("SynthGraph.ExtracteurSingleShot")


# ==============================================================================
#  SCHÉMA PLAT (grammaire-friendly, détaillé)
# ==============================================================================

class FlatPrecursor(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    name: str = Field(default="", validation_alias=AliasChoices("name", "nom", "formula", "formule"),
                      description="Nom/formule du réactif, ex: SrCO3, IrO2, SrCl2·6H2O")
    role: str = Field(default="reactant", validation_alias=AliasChoices("role", "rôle", "type"),
                      description="reactant | flux | solvent | dopant | additive")
    amount: str = Field(default="", validation_alias=AliasChoices("amount", "quantite", "quantité", "ratio", "molar_ratio"),
                        description="Quantité ou ratio molaire, ex: '2.5 g' ou '1:2:7 molar ratio'")
    citation: str = Field(default="", validation_alias=AliasChoices("citation", "source_quote", "quote"),
                          description="Extrait exact du texte source")


class FlatStep(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    order: int = Field(default=0, validation_alias=AliasChoices("order", "ordre", "step_number", "num"),
                       description="Position chronologique (1-indexed)")
    variant_id: str = Field(default="v1", validation_alias=AliasChoices("variant_id", "variant", "sample_id", "sample"),
                            description="Variant identifier when multiple synthesis variants exist (v1, v2, ...)")
    operation: str = Field(default="generic", validation_alias=AliasChoices("operation", "opération", "type", "operation_type", "etape", "étape"), description=(
        "Type d'opération CANONIQUE. Traitements thermiques SÉPARÉS : "
        "'heating' (montée vers une consigne), 'soak' (palier/maintien isotherme), "
        "'cooling' (descente vers une consigne), 'quenching' (trempe rapide), "
        "'calcination', 'sintering', 'annealing'. Autres : 'mixing', 'grinding', "
        "'pressing', 'dissolution', 'flux_growth', 'crystal_growth', 'hydrothermal', "
        "'cvd', 'pvd', 'ald', 'washing', 'filtration', 'drying', 'separation'."))
    # Thermique
    temperature_c: Optional[float] = Field(default=None, description="Température de palier en °C (soak/calcination/sintering/annealing)")
    target_temperature_c: Optional[float] = Field(default=None, description="Température CIBLE d'une rampe (heating/cooling) en °C")
    from_temperature_c: Optional[float] = Field(default=None, description="Température de départ d'une trempe en °C")
    max_temperature_c: Optional[float] = Field(default=None, description="Température maximale (flux/crystal growth) OU borne MAX d'une plage de température en °C")
    ramp_rate_c_per_h: Optional[float] = Field(default=None, description="Vitesse de chauffe (heating) en °C/h")
    cooling_rate_c_per_h: Optional[float] = Field(default=None, description="Vitesse de refroidissement (cooling) en °C/h")
    duration_h: Optional[float] = Field(default=None, description="Durée/dwell en heures (null si absente)")
    atmosphere: Optional[str] = Field(default=None, description="Atmosphère, ex: air, Ar, O2, N2")
    equipment: Optional[str] = Field(default=None, description="Four/équipement, ex: box furnace, tube furnace")
    min_temperature_c: Optional[float] = Field(default=None, description="Température MIN d'une plage (quand le papier donne un intervalle)")
    min_duration_h: Optional[float] = Field(default=None, description="Durée MIN d'une plage en heures")
    max_duration_h: Optional[float] = Field(default=None, description="Durée MAX d'une plage en heures")
    # Matériaux / milieu
    solvent: Optional[str] = Field(default=None, description="Solvant (dissolution, washing)")
    medium: Optional[str] = Field(default=None, description="Milieu de broyage/mélange")
    quench_medium: Optional[str] = Field(default=None, description="Milieu de trempe, ex: water, air")
    flux_material: Optional[str] = Field(default=None, description="Flux fondant, ex: SrCl2, KCl, PbO")
    crucible_material: Optional[str] = Field(default=None, description="Creuset, ex: platinum, alumina")
    # Mécanique / physiques
    speed_rpm: Optional[float] = Field(default=None, description="Vitesse de rotation en rpm")
    pressure_mpa: Optional[float] = Field(default=None, description="Pression appliquée en MPa")
    concentration_mol_l: Optional[float] = Field(default=None, description="Concentration en mol/L")
    # Fourre-tout typé
    other_parameters: Dict[str, Any] = Field(default_factory=dict, description="Tout autre paramètre {nom: valeur} non couvert ci-dessus (avec son unité dans la valeur si connue)")
    details: str = Field(default="", description="Description libre de l'étape")
    citation: str = Field(default="", description="Extrait EXACT du texte justifiant l'étape et ses valeurs")


class FlatExtraction(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    reasoning: str = Field(default="", validation_alias=AliasChoices("reasoning", "raisonnement"))
    target: str = Field(default="", validation_alias=AliasChoices("target", "materiau_cible", "matériau_cible", "material", "cible", "target_material"),
                        description="Matériau final visé, ex: Sr2IrO4")
    method: str = Field(default="", validation_alias=AliasChoices("method", "methode", "méthode"),
                        description="Méthode de synthèse, ex: flux_growth")
    precursors: List[FlatPrecursor] = Field(default_factory=list,
                                            validation_alias=AliasChoices("precursors", "precurseurs", "précurseurs", "reactifs", "réactifs"))
    steps: List[FlatStep] = Field(default_factory=list,
                                  validation_alias=AliasChoices("steps", "etapes", "étapes", "operations", "opérations"))
    notes: str = Field(default="", validation_alias=AliasChoices("notes", "remarques", "notes_supplementaires"),
                       description="Remarques, paramètres absents, variantes")


SYSTEM_PROMPT = """Tu es l'Agent Extracteur de SynthGraph, expert en protocoles de synthèse inorganique.

MISSION : Extraire la recette de synthèse COMPLÈTE et DÉTAILLÉE du matériau cible.

RÈGLES ABSOLUES :
1. N'INVENTE JAMAIS de valeur. Une valeur numérique doit venir du texte ; sinon mets `null`
   (JAMAIS 0). N'utilise 0 que si le texte dit littéralement zéro.
2. Fournis `citation` (extrait EXACT du texte, copier-coller) pour chaque précurseur et chaque étape.
3. Liste TOUS les précurseurs/réactifs avec leur rôle et leur quantité/ratio molaire si donné
   (ex: '1:2:7 molar ratio'). RÔLES :
   - `flux` : sel inorganique fondu utilisé en excès comme solvant de croissance
     (ex: SrCl2, KCl, NaCl, PbO, KF, B2O3). C'est un FLUX, PAS un 'solvent'.
   - `solvent` : liquide moléculaire (eau, éthanol, acide). `reactant` : réactif stœchiométrique.
   - `dopant` : élément ajouté en faible quantité.
4. DÉCOMPOSE le programme thermique : CHAQUE rampe, CHAQUE palier, CHAQUE refroidissement
   est une ÉTAPE DISTINCTE avec un `operation` séparé. N'utilise PAS un seul 'thermal_treatment'.
   Types thermiques : 'heating' (montée), 'soak' (palier isotherme), 'cooling' (descente),
   'quenching' (trempe), 'calcination', 'sintering', 'annealing'.
   EXEMPLE — '1300°C →(8°C/h) 900°C →RT' se décompose en :
     • heating  : target_temperature_c=1300
     • cooling  : target_temperature_c=900, cooling_rate_c_per_h=8
     • cooling  : target_temperature_c=25 (RT)
   Et 'held at 1000°C for 24 h' → soak : temperature_c=1000, duration_h=24.
5. Utilise les BONS champs : montée→`target_temperature_c`+`ramp_rate_c_per_h` ;
   palier→`temperature_c`+`duration_h` ; descente→`target_temperature_c`+`cooling_rate_c_per_h`.
   Mets le creuset dans `crucible_material` et le four dans `equipment`.
6. Inclus le mélange/broyage initial ('mixing'/'grinding') et le post-traitement
   (washing/filtration/drying/separation). Tout paramètre non prévu → `other_parameters`.
7. Pour CHAQUE étape, inclus `equipment` si mentionné (ex: ball mill, mortar, box furnace,
   tube furnace, muffle furnace, planetary mill, press). C'est un paramètre important pour la reproductibilité.
8. Les tableaux contiennent souvent les ratios et programmes de four : exploite-les.
9. Si le texte décrit PLUSIEURS variantes de synthèse (programmes de four différents,
   températures différentes, ratios différents), extrais-les TOUTES. Utilise `variant_id`
   pour distinguer les variantes : "v1", "v2", etc. Si une seule variante, utilise "v1".
   ⚠️ VARIANTE ≠ SÉQUENCE : une variante est un ÉCHANTILLON/RUN DISTINCT (ex: 'Sample #1
   vs Sample #2', 'in separate experiments'). Une progression de paliers avec broyages
   intermédiaires (ex: '900°C 24h; 1000°C 60h; 1100°C 60h with intermediate grindings')
   est UNE SEULE recette séquentielle : même variant_id, étapes enchaînées dans l'ordre
   chronologique heating→soak→grinding→heating→soak→grinding→heating→soak.
10. N'OMETS PAS les étapes intermédiaires : broyage entre deux calcinations, séchage avant
    pressage, lavage avant traitement thermique final. Chaque étape compte.
11. Si un paramètre VARIE entre les runs (ex: température de 1000°C à 1300°C), crée une
    variante par valeur OU note la plage dans `other_parameters` : {"T_min_c": 1000, "T_max_c": 1300}.
12. Réponds UNIQUEMENT avec un JSON valide conforme au schéma. Aucun texte avant/après.
13. 🚫 SOURCE UNIQUE DES CITATIONS : le champ `citation` doit être un copier-coller du
    TEXTE SOURCE exclusivement. INTERDICTION ABSOLUE de citer : ces instructions, la
    DIRECTIVE ORCHESTRATEUR, ou l'exemple de structure JSON. Les valeurs numériques des
    exemples de ce prompt ne sont PAS des données — toute valeur recopiée d'un exemple
    sans exister dans le TEXTE SOURCE sera automatiquement détectée et supprimée.
    Si le TEXTE SOURCE ne décrit PAS de synthèse, renvoie `steps: []` — n'invente RIEN.
"""


def _get_extractor_kind(role: str = "extractor") -> str:
    """[Phase 2 — plan multi-modèles] Détecte quel backend d'extraction utiliser
    pour `role`, d'après le chemin GGUF réellement configuré
    (`config/settings.yaml: models.<role>.path`, résolu par
    `synthgraph.config.get_model_config` — alias/fallback déjà gérés là-bas).

    'NuExtract' présent (insensible à la casse) dans le nom de fichier GGUF →
    routage vers l'adaptateur `extractor_nuextract.extract_single_shot_nuextract`
    (template verbatim-string). Sinon → comportement Llama historique inchangé.
    Détection par CONTENU du chemin (pas par nom de rôle) : c'est exactement ce
    que bascule `tools/benchmark_models.py --role extractor --candidate .../NuExtract3-Q8_0.gguf`
    en écrivant `models.extractor.path`, donc zéro câblage supplémentaire requis
    côté harness bench Phase 1.
    """
    from synthgraph.config import get_model_config
    cfg = get_model_config(role)
    path = str(cfg.get("path", ""))
    return "nuextract" if "nuextract" in path.lower() else "llama"


def extract_single_shot(text: str, method_type: str, target: str,
                        model: str = "llama-3.1-8b", route_id: str = "route_1",
                        directive: dict | None = None, use_grammar: bool = False,
                        extra_hint: str = "", temperature: float | None = None,
                        role: str = "extractor") -> dict:
    """Extraction structurée — DISPATCHER (Phase 2 — plan multi-modèles).

    Signature et sortie inchangées (drop-in) pour les 4 sites d'appel de
    `runner.py`. Route en interne vers l'adaptateur du modèle réellement
    configuré pour `role` (cf `_get_extractor_kind`) :
    - GGUF NuExtract 3 configuré → `extractor_nuextract.extract_single_shot_nuextract`
      (template verbatim-string, cf ce module).
    - Sinon (Llama, défaut historique) → `_extract_single_shot_llama` ci-dessous,
      comportement STRICTEMENT inchangé par rapport à avant Phase 2.
    """
    if _get_extractor_kind(role) == "nuextract":
        from synthgraph.agents.extractor_nuextract import extract_single_shot_nuextract
        logger.info(f"[{route_id}] Routage extracteur → NuExtract (role={role})")
        return extract_single_shot_nuextract(
            text, method_type=method_type, target=target,
            model=model, route_id=route_id, directive=directive,
            use_grammar=use_grammar, extra_hint=extra_hint, temperature=temperature,
        )
    return _extract_single_shot_llama(
        text, method_type=method_type, target=target,
        model=model, route_id=route_id, directive=directive,
        use_grammar=use_grammar, extra_hint=extra_hint, temperature=temperature,
        role=role,
    )


# Alias explicite (Phase 2) — même fonction, nom alternatif pour les outils/tests
# qui veulent nommer le dispatch sans ambiguïté (cf mandat Phase 2, étape 2b).
extract_single_shot_dispatch = extract_single_shot


def _extract_single_shot_llama(text: str, method_type: str, target: str,
                        model: str = "llama-3.1-8b", route_id: str = "route_1",
                        directive: dict | None = None, use_grammar: bool = False,
                        extra_hint: str = "", temperature: float | None = None,
                        role: str = "extractor") -> dict:
    """Extraction structurée en un seul appel (mode json_object par défaut) — backend Llama.

    Renvoie un dict au format `pathways`, avec étapes NORMALISÉES par type
    (via `normalize_steps`) et `missing_parameters` renseigné.

    temperature : None = défaut agent (0.1). [V4.12] Les retries d'auto-consistance
    passent une valeur plus haute pour sortir des modes de fabrication systématiques ;
    le grounding déterministe en aval reste le filtre de vérité.
    role : [Phase 1 — plan multi-modèles] rôle de ROUTAGE MODÈLE transmis à
    `SynthAgent.role` → `LlamaEngineManager.get_llm(role)`. AVANT ce correctif,
    l'agent portait le libellé littéral "extraction single-shot" (jamais une clé
    de `config/settings.yaml: models` → repli silencieux sur `default`, comportement
    inchangé). Défaut "extractor" : c'est la seule fonction d'extraction du pipeline
    actif ; si `models.extractor` n'est pas configuré, `get_model_config` retombe
    sur `default` (fail-safe), donc aucune régression pour les installations qui
    n'ont pas encore de section `models:` par rôle.
    """
    import json as _json
    directive_block = ""
    if directive:
        directive_block = (
            f"DIRECTIVE ORCHESTRATEUR (objectif de mission — ce N'EST PAS le texte source, "
            f"n'en cite JAMAIS le contenu) : {_json.dumps(directive, ensure_ascii=False)}\n"
        )

    # [V4.6] Valeurs d'exemple volontairement IMPROBABLES (555/5/665/7) : si le modèle
    # les recopie au lieu de lire le texte, le grounding numérique les détecte à coup
    # sûr (1300°C/24h étaient des valeurs plausibles → fuites camouflées).
    skeleton = (
        '{"reasoning":"...","target":"' + target + '","method":"' + method_type + '",'
        '"precursors":[{"name":"IrO2","role":"reactant","amount":"1","citation":"..."}],'
        '"steps":['
        '{"order":1,"operation":"mixing","variant_id":"v1","citation":"..."},'
        '{"order":2,"operation":"heating","target_temperature_c":555,"atmosphere":"air","variant_id":"v1","citation":"..."},'
        '{"order":3,"operation":"soak","temperature_c":555,"duration_h":5,"atmosphere":"air","variant_id":"v1","citation":"..."},'
        '{"order":2,"operation":"heating","target_temperature_c":665,"atmosphere":"O2","variant_id":"v2","citation":"..."},'
        '{"order":3,"operation":"soak","temperature_c":665,"duration_h":7,"atmosphere":"O2","variant_id":"v2","citation":"..."}'
        '],"notes":""}'
    )
    user_prompt = (
        f"MATÉRIAU CIBLE : {target}\n"
        f"MÉTHODE : {method_type}\n"
        f"ROUTE : {route_id}\n"
        f"{directive_block}\n"
        f"TEXTE SOURCE :\n{text}\n\n"
        f"Extrais la recette complète. Utilise EXACTEMENT ces clés JSON anglaises "
        f"(exemple de STRUCTURE, pas de valeurs à copier) :\n{skeleton}\n\n"
        f"Décompose le programme thermique en étapes séparées (heating/soak/cooling/quenching). "
        f"Chaque valeur numérique DOIT avoir sa citation exacte du texte.\n"
        f"ATMOSPHÈRE : si le texte mentionne 'in air', 'flowing O2', 'under Ar', 'N2', 'vacuum', "
        f"remplis TOUJOURS le champ 'atmosphere' de chaque étape heating/soak avec la valeur normalisée "
        f"(air / O2 / Ar / N2 / vacuum). Le skeleton ci-dessus montre 'air' et 'O2' comme exemples.\n"
        f"Si PLUSIEURS variantes sont décrites (températures ou durées différentes, "
        f"ex: Table avec Sample #1/#2/#3, ou plusieurs programmes de four), "
        f"utilise variant_id='v1','v2',... pour les distinguer. "
        f"Le skeleton ci-dessus montre v1 ET v2 — reproduis ce pattern si le texte décrit "
        f"plusieurs conditions expérimentales pour la même recette."
    )
    if extra_hint:
        user_prompt += f"\n{extra_hint}"

    # [V4.9] Plafond 4096 : une recette réelle fait ~1500-2500 tokens JSON ; sans
    # plafond, des générations dégénérées à 8192 tokens (420-440 s × retries)
    # expliquaient les papiers à 27-30 min (constaté batch 1 : Hummers, CBD MnSe).
    agent_kwargs = dict(
        name=f"ExtracteurSS-{route_id}", role=role,
        model=model, system_prompt=SYSTEM_PROMPT, max_tokens=4096,
    )
    if temperature is not None:
        agent_kwargs["temperature"] = temperature
    agent = SynthAgent(**agent_kwargs)
    data = agent.generate_validated_json(
        user_prompt, schema_model=FlatExtraction, max_retries=2, use_grammar=use_grammar,
    )

    if not data or "error" in data:
        logger.warning(f"[SingleShot] Extraction échouée pour {route_id}: {str(data)[:200]}")
        return {"pathways": [], "confidence": 0.0, "extraction_notes": "single-shot failed",
                "route_id": route_id, "method_type": method_type}

    # Forcer method/target si le modèle les a omis (on les connaît via la directive)
    data.setdefault("method", method_type)
    data.setdefault("target", target)
    return _to_pathways_dict(data, method_type, route_id)


def _to_pathways_dict(data: dict, method_type: str, route_id: str) -> dict:
    """Convertit FlatExtraction → `pathways`, avec étapes normalisées par type.
    Regroupe les étapes par variant_id pour produire plusieurs pathways si nécessaire."""
    raw_steps = [s for s in (data.get("steps") or [])]

    # Group steps by variant_id
    from collections import defaultdict
    variants = defaultdict(list)
    for s in raw_steps:
        vid = s.get("variant_id", "v1") or "v1"
        variants[vid].append(s)

    precursors = []
    for p in data.get("precursors", []):
        precursors.append({
            "name": p.get("name", ""), "formula": p.get("name", ""),
            "role": p.get("role", "reactant"), "amount": p.get("amount", ""),
            "unit": "", "citation": p.get("citation", ""),
        })

    notes = [data.get("notes", "")] if data.get("notes") else []
    pathways = []
    total_steps = 0
    total_missing = 0

    for vid in sorted(variants.keys()):
        variant_steps = variants[vid]
        normalized_steps, missing_parameters = normalize_steps(variant_steps)
        for st in normalized_steps:
            st["step_name"] = f"{st.get('type', 'step')}_{st.get('order', '')}"

        variant_route_id = f"{route_id}_{vid}" if len(variants) > 1 else route_id
        pathway = {
            "target_material": {"name": data.get("target", ""), "formula": data.get("target", "")},
            "synthesis_route": method_type,
            "variant_id": vid,
            "precursors": precursors,
            "synthesis_steps": normalized_steps,
            "missing_parameters": missing_parameters,
            "missing_info": notes,
        }
        pathways.append(pathway)
        total_steps += len(normalized_steps)
        total_missing += len(missing_parameters)

    return {
        "pathways": pathways,
        "reasoning": data.get("reasoning", ""),
        "confidence": 0.8 if total_steps else 0.3,
        "route_id": route_id,
        "method_type": method_type,
        "extraction_notes": (f"single-shot ({total_steps} étapes normalisées, "
                             f"{len(precursors)} précurseurs, {total_missing} params requis manquants, "
                             f"{len(pathways)} variante(s))"),
    }
