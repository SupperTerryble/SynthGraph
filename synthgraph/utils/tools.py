"""
src/tools.py — SynthGraph
Outils partagés par les agents : lecture PDF et connexion Neo4j.

Toutes les constantes sont définies en haut du fichier.
"""

# ==============================================================================
#  CONSTANTES
# ==============================================================================
PDF_MAX_PAGES        = 50       # Limite de pages traitées
CHUNK_MAX_CHARS      = 3000     # Taille max d'un chunk de texte
CHUNK_OVERLAP_CHARS  = 200      # Chevauchement entre chunks
NEO4J_TIMEOUT        = 30       # secondes

SECTION_MARKERS = [
    "experimental", "synthesis", "preparation", "materials and methods",
    "méthode", "expérimental", "synthèse", "sol-gel", "hydrothermal",
    "characterization", "results and discussion"
]

# ==============================================================================
#  IMPORTS
# ==============================================================================
import os
import re
import json
import logging
import base64
from pathlib import Path
from typing import Optional

logger = logging.getLogger("SynthGraph.Tools")

# ==============================================================================
#  OUTIL 1 : LECTURE PDF
# ==============================================================================

class PDFReaderTool:
    """Extrait le texte d'un PDF scientifique (opendataloader-pdf → fallback PyMuPDF)."""

    def __init__(self, max_pages: int = PDF_MAX_PAGES,
                 chunk_size: int = CHUNK_MAX_CHARS,
                 overlap: int = CHUNK_OVERLAP_CHARS):
        self.max_pages = max_pages
        self.chunk_size = chunk_size
        self.overlap = overlap

    def extract_text(self, pdf_path: str, use_marker: bool = False) -> str:
        """Extrait le texte structuré du PDF (opendataloader-pdf si dispo, sinon PyMuPDF)."""
        from synthgraph.rag.pdf_parser import parse_pdf_for_vision

        try:
            full_text = parse_pdf_for_vision(pdf_path)
            return full_text
        except Exception as e:
            logger.error(f"Erreur extraction PDF : {e}")
            return self._read_as_text(pdf_path)

    def _read_as_text(self, path: str) -> str:
        """Fallback : lit le fichier comme texte brut (pour .txt)."""
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                return f.read()
        except Exception as e:
            logger.error(f"Erreur lecture fichier texte : {e}")
            return ""

    def extract_images(self, pdf_path: str, out_dir: str = "logs/extracted_images",
                       min_pixels: int = 160, min_bytes: int = 8_000) -> list[str]:
        """[V4.8] Extrait les images du PDF en FICHIERS et retourne leurs chemins.

        (Avant : liste de base64 en mémoire, jamais consommée par le chemin actif —
        et le legacy supposait déjà des chemins.) Filtre les vignettes/logos
        (< min_pixels de côté ou < min_bytes) inutiles à l'Agent Vision.
        Nommage : <stem>/p{page}_i{idx}.{ext} → 'p3_i1' aide à relier 'Fig. 3'.
        """
        paths: list[str] = []
        try:
            import fitz
            stem = Path(pdf_path).stem[:60].replace(" ", "_")
            dest = Path(out_dir) / stem
            dest.mkdir(parents=True, exist_ok=True)
            doc = fitz.open(pdf_path)
            pages = min(len(doc), self.max_pages)
            skipped = 0
            for i in range(pages):
                page = doc[i]
                for idx, img_info in enumerate(page.get_images(full=True), 1):
                    xref = img_info[0]
                    base_image = doc.extract_image(xref)
                    w, h = base_image.get("width", 0), base_image.get("height", 0)
                    data = base_image["image"]
                    if (w and w < min_pixels) or (h and h < min_pixels) or len(data) < min_bytes:
                        skipped += 1
                        continue
                    ext = base_image.get("ext", "png")
                    # [V4.11] Audit, problème 2 : les PDF encodent parfois en JPEG2000
                    # (.jpx) ou autres formats que la chaîne vision ne décode pas —
                    # échec silencieux constaté (0 réponse sur 8, papier MnSe).
                    # Conversion en PNG via Pixmap pour tout format non standard.
                    if ext not in ("png", "jpeg", "jpg"):
                        try:
                            pix = fitz.Pixmap(doc, xref)
                            if pix.colorspace and pix.colorspace.n > 3:
                                pix = fitz.Pixmap(fitz.csRGB, pix)
                            data = pix.tobytes("png")
                            logger.info(f"  [img] p{i + 1}_i{idx}.{ext} converti en PNG "
                                        f"(format non supporté par la chaîne vision)")
                            ext = "png"
                            pix = None
                        except Exception as ce:
                            logger.warning(f"  [img] conversion {ext}→png impossible ({ce}) "
                                           f"— image ignorée pour la vision")
                            skipped += 1
                            continue
                    p = dest / f"p{i + 1}_i{idx}.{ext}"
                    if not p.exists():
                        p.write_bytes(data)
                    paths.append(str(p))
            doc.close()
            logger.info(f"Extraites {len(paths)} images exploitables du PDF "
                        f"({skipped} vignettes ignorées) → {dest}")
        except Exception as e:
            logger.error(f"Erreur extraction d'images : {e}")
        return paths

    def extract_sections(self, text: str) -> dict[str, str]:
        """Identifie et sépare les sections du document."""
        sections = {"full": text, "experimental": "", "introduction": "",
                    "results": "", "conclusion": ""}
        normalized = text.lower()
        for marker in SECTION_MARKERS:
            idx = normalized.find(marker)
            if idx != -1:
                section_text = text[idx:idx + 5000]
                if "experimental" in marker or "synthesis" in marker or "preparation" in marker:
                    sections["experimental"] += "\n" + section_text
        return sections

    def chunk_text(self, text: str) -> list[str]:
        """Découpe le texte en chunks avec chevauchement."""
        chunks = []
        start = 0
        while start < len(text):
            end = min(start + self.chunk_size, len(text))
            chunk = text[start:end]
            # Couper au dernier saut de ligne pour éviter de couper une phrase
            if end < len(text):
                last_nl = chunk.rfind("\n")
                if last_nl > self.chunk_size // 2:
                    end = start + last_nl
                    chunk = text[start:end]
            chunks.append(chunk.strip())
            if end >= len(text):
                break
            start = max(start + 1, end - self.overlap)
        return [c for c in chunks if len(c) > 50]

    def process(self, file_path: str, use_marker: bool = False) -> dict:
        """Pipeline complet : extraction → sections → chunks."""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Fichier introuvable : {file_path}")

        if path.suffix.lower() == ".pdf":
            text = self.extract_text(str(path), use_marker=use_marker)
        else:
            text = self._read_as_text(str(path))

        sections = self.extract_sections(text)
        # Utiliser la section expérimentale si trouvée, sinon tout le texte
        target_text = sections["experimental"] if len(sections["experimental"]) > 200 else text
        chunks = self.chunk_text(target_text)

        return {
            "full_text":    text,
            "sections":     sections,
            "chunks":       chunks,
            "total_chars":  len(text),
            "total_chunks": len(chunks),
            "file_path":    str(path),
            "file_name":    path.name,
        }

# ==============================================================================
#  OUTIL 2 : CONNEXION NEO4J
# ==============================================================================

class Neo4jTool:
    """Exécute des requêtes Cypher sur Neo4j, avec fallback fichier .cypher."""

    def __init__(self, uri: str = "bolt://localhost:7687",
                 user: str = "neo4j",
                 password: str = "synthgraph2026",
                 database: str = "neo4j",
                 cypher_output_path: str = "logs/cypher_output.cypher",
                 timeout: int = NEO4J_TIMEOUT):
        self.uri = uri
        self.user = user
        self.password = password
        self.database = database
        self.cypher_output_path = cypher_output_path
        self.timeout = timeout
        self._driver = None
        self._pending_queries: list[str] = []

    def connect(self) -> bool:
        """Tente la connexion à Neo4j."""
        try:
            from neo4j import GraphDatabase
            self._driver = GraphDatabase.driver(self.uri, auth=(self.user, self.password))
            self._driver.verify_connectivity()
            logger.info(f"Connexion Neo4j établie : {self.uri}")
            return True
        except ImportError:
            logger.warning("Driver neo4j non installé. Requêtes sauvegardées en .cypher uniquement.")
            return False
        except Exception as e:
            logger.warning(f"Neo4j inaccessible ({e}). Mode fichier .cypher activé.")
            return False

    def run_query(self, query: str, params: dict = None) -> Optional[list]:
        """Exécute une query Cypher. Fallback fichier si pas de connexion."""
        self._pending_queries.append(query)
        if self._driver:
            try:
                with self._driver.session(database=self.database) as session:
                    result = session.run(query, params or {})
                    return [dict(record) for record in result]
            except Exception as e:
                logger.error(f"Erreur Neo4j : {e} | query: {query[:150]!r} | params: {str(params)[:150]}")
                return None
        return None

    def flush_to_file(self) -> str:
        """Sauvegarde toutes les requêtes en attente dans le fichier .cypher."""
        Path(self.cypher_output_path).parent.mkdir(exist_ok=True)
        with open(self.cypher_output_path, "w", encoding="utf-8") as f:
            f.write("// ============================================================\n")
            f.write("// SynthGraph — Requêtes Cypher générées\n")
            f.write(f"// Date : {__import__('datetime').datetime.now().isoformat()}\n")
            f.write("// ============================================================\n\n")
            for i, q in enumerate(self._pending_queries, 1):
                f.write(f"// Query {i}\n{q}\n\n")
        logger.info(f"{len(self._pending_queries)} requêtes Cypher sauvegardées → {self.cypher_output_path}")
        return self.cypher_output_path

    def close(self):
        if self._driver:
            self._driver.close()

# ==============================================================================
#  OUTIL 3 : UTILITAIRE JSON
# ==============================================================================

def safe_json_parse(text: str) -> Optional[dict]:
    """Extrait et parse le premier bloc JSON trouvé dans un texte."""
    if not text:
        return None

    # Étape 0: Suppression du bloc de réflexion DeepSeek R1 (Chain of Thought)
    cleaned = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL).strip()

    # Étape A: Nettoyage des balises markdown éventuelles
    cleaned = re.sub(r'```(?:json)?', '', cleaned)
    cleaned = re.sub(r'```', '', cleaned)
    
    # Étape B: Trouver le début et la fin de l'objet ou tableau JSON
    start_idx_dict = cleaned.find('{')
    start_idx_list = cleaned.find('[')
    
    end_idx_dict = cleaned.rfind('}')
    end_idx_list = cleaned.rfind(']')
    
    start_idx = -1
    end_idx = -1
    
    # Déterminer si on a un objet ou un tableau en premier
    if start_idx_dict != -1 and (start_idx_list == -1 or start_idx_dict < start_idx_list):
        start_idx = start_idx_dict
        end_idx = end_idx_dict
    elif start_idx_list != -1:
        start_idx = start_idx_list
        end_idx = end_idx_list
        
    if start_idx == -1 or end_idx == -1 or end_idx < start_idx:
        return None
        
    # Étape C: Extraire la sous-chaîne
    json_str = cleaned[start_idx:end_idx+1]
    
    # Étape D: Parsing
    try:
        import json_repair
        parsed = json_repair.repair_json(json_str, return_objects=True)
        if isinstance(parsed, list):
            return {"data": parsed}
        if isinstance(parsed, dict):
            return parsed
        return None
    except Exception as e:
        logger.error(f"Erreur de parsing JSON LLM avec json_repair : {e}")
        return {"error": "Invalid JSON format generated by LLM.", "raw_text": text}


# ==============================================================================
#  OUTIL 4 : RÉCUPÉRATION DYNAMIQUE DE SCHÉMA DE SYNTHÈSE
# ==============================================================================

class GetSynthesisSchemaTool:
    """
    Outil permettant aux agents de récupérer dynamiquement la structure JSON attendue
    pour une méthode de dépôt spécifique ou une étape intermédiaire (lavage, broyage...).
    """
    
    @staticmethod
    def get_synthesis_schema(method_or_step_name: str) -> str:
        """
        Retourne la structure JSON formattée pour la méthode ou l'étape spécifiée.
        """
        import sys
        from pathlib import Path
        
        # Ajouter les répertoires nécessaires au PATH
        core_dir = Path(__file__).parent.parent.parent / "SynthMapper_V3"
        if str(core_dir) not in sys.path:
            sys.path.insert(0, str(core_dir))
            
        try:
            from core.synthesis_schemas import get_schema_for_method, get_schema_for_step, list_available_methods
            
            clean_name = method_or_step_name.strip().upper()
            available_methods = list_available_methods()
            
            # 1. Vérifier si c'est une méthode de dépôt principale
            if clean_name in available_methods:
                schema = get_schema_for_method(clean_name)
                return json.dumps(schema, indent=2, ensure_ascii=False)
                
            # 2. Sinon, essayer de récupérer une étape intermédiaire (lavage, broyage...)
            schema_step = get_schema_for_step(method_or_step_name)
            if "error" not in schema_step:
                return json.dumps(schema_step, indent=2, ensure_ascii=False)
                
            # 3. Fallback en cas d'erreur
            return json.dumps({
                "error": f"Schéma pour '{method_or_step_name}' introuvable.",
                "available_methods": available_methods,
                "available_steps": ["washing", "milling", "pelletizing"]
            }, indent=2)
            
        except Exception as e:
            return json.dumps({"error": f"Erreur d'importation des schémas : {str(e)}"}, indent=2)

class OntologyTool:
    """Outil d'ontologie des méthodes de synthèse."""
    @staticmethod
    def get_route_definition(route_name: str) -> str:
        """Retourne la définition standard et les étapes pour une méthode donnée."""
        route = route_name.lower()
        import json
        from synthgraph.config import MACRO_METHODS_PATH

        json_path = MACRO_METHODS_PATH
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                definitions = json.load(f)
        except Exception as e:
            return json.dumps({"error": f"Impossible de charger l'ontologie: {e}"}, indent=2)
            
        # Fuzzy matching basique
        for key, value in definitions.items():
            if key in route or route in key:
                return json.dumps({"route": key, **value}, indent=2, ensure_ascii=False)
                
        return json.dumps({
            "error": f"Méthode '{route_name}' inconnue dans l'ontologie.",
            "available_methods": list(definitions.keys())
        }, indent=2)
