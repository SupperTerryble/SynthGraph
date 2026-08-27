import os
import gc
import logging
from pathlib import Path
from langchain_text_splitters import RecursiveCharacterTextSplitter, MarkdownTextSplitter
from synthgraph.rag.pdf_parser import parse_pdf_for_vision

# Logging local
logger = logging.getLogger("SynthGraph.RAG")


class DocumentRAG:
    """
    Gestionnaire RAG local utilisant ChromaDB (ou pure Python offline fallback).
    Découpe le document PDF scientifique en chunks pour n'alimenter les LLMs
    qu'avec des morceaux de textes sémantiquement pertinents, évitant la surcharge contextuelle.
    """
    
    def __init__(self, persist_directory: str = "logs/chroma_db"):
        self.persist_directory = persist_directory
        self.documents = []
        self.indexed = False
        
        if os.environ.get("SYNTHGRAPH_OFFLINE") == "1":
            raise RuntimeError("Le mode SYNTHGRAPH_OFFLINE est désactivé. ChromaDB est obligatoire pour éviter les hallucinations.")
            
        try:
            import chromadb
            from chromadb.utils import embedding_functions
            logger.info("Initialisation de ChromaDB (RAG)...")
            self.emb_fn = embedding_functions.DefaultEmbeddingFunction()
            self.client = chromadb.PersistentClient(path=self.persist_directory)
            try:
                self.client.delete_collection(name="pdf_chunks")
            except Exception: pass
            self.collection = self.client.create_collection(
                name="pdf_chunks", 
                embedding_function=self.emb_fn
            )
        except Exception as e:
            logger.error(f"Erreur fatale ChromaDB : {e}")
            raise RuntimeError(f"Impossible de charger ChromaDB ou le modèle d'embedding : {e}")

    def index_pdf(self, pdf_path: str, use_vision_parser: bool = True) -> int:
        """
        Ingère un PDF. Utilise le parseur multimodal PyMuPDF pour générer des images et balises.
        """
        text = ""
        
        if use_vision_parser:
            try:
                logger.info(f"Extraction multimodale (Texte + Vision) pour {pdf_path}")
                text = parse_pdf_for_vision(pdf_path)
            except Exception as e:
                logger.warning(f"Le parseur Vision a échoué ({e}). Fallback sur PyMuPDF basique.")
                
        if not text:
            # Fallback PyMuPDF (fitz) basique
            try:
                import fitz
                doc = fitz.open(pdf_path)
                text = chr(12).join([page.get_text() for page in doc])
            except Exception as e:
                logger.error(f"PyMuPDF basique a échoué: {e}")
                return 0
                
        return self.index_text(text)

    def index_text(self, text: str) -> int:
        """
        Découpe un texte (idéalement Markdown) en chunks via Langchain.
        """
        if not text.strip():
            logger.warning("Texte vide fourni pour la vectorisation.")
            return 0
            
        logger.info("Découpage du document avec MarkdownTextSplitter...")
        splitter = MarkdownTextSplitter(
            chunk_size=800,
            chunk_overlap=150
        )
        
        chunks = splitter.create_documents([text])
        self.documents = [c.page_content for c in chunks]
        
        try:
            logger.info(f"Vectorisation ChromaDB de {len(self.documents)} chunks en cours...")
            ids = [f"chunk_{i}" for i in range(len(self.documents))]
            metadatas = [{"chunk_id": i} for i in range(len(self.documents))]
            self.collection.add(documents=self.documents, metadatas=metadatas, ids=ids)
            logger.info(f"  DocumentRAG : {len(self.documents)} chunks indexés, {sum(len(d) for d in self.documents)} chars")
        except Exception as e:
            logger.error(f"Erreur fatale lors de la vectorisation ChromaDB : {e}")
            raise RuntimeError(f"Vectorisation ChromaDB échouée (DocumentRAG) : {e}")
                
        self.indexed = True
        gc.collect()
        return len(self.documents)

    def query(self, query_texts: str, n_results: int = 3) -> str:
        """
        Cherche les chunks les plus pertinents et les concatène.
        """
        if not self.indexed:
            logger.warning("Aucun document indexé pour la requête RAG.")
            return ""
            
        logger.info(f"Recherche contexte RAG : '{query_texts}' (top {n_results})")
        
        try:
            results = self.collection.query(
                query_texts=[query_texts],
                n_results=n_results
            )
            documents = results.get('documents', [[]])[0]
            return "\n...\n".join(documents)
        except Exception as e:
            logger.error(f"Erreur fatale lors de la requête ChromaDB : {e}")
            raise RuntimeError(f"Requête ChromaDB échouée (DocumentRAG) : {e}")

    def get_orchestrator_context(self) -> str:
        """Récupère intro, abstrait et vue globale pour l'Orchestrateur."""
        return self.query("Abstract Introduction Synthesis Method Overview strategy", n_results=4)

    def get_extraction_context(self) -> str:
        """Récupère les détails expérimentaux pour l'Extracteur."""
        return self.query("Synthesis procedure experimental setup chemicals precursors temperature duration time atmosphere stirring", n_results=5)

    def get_contextual_context(self, route_id: str = "", method_type: str = "") -> str:
        """Récupère les discussions, échecs et optimisations pour l'Agent Contextuel."""
        query = "Optimization failure attempts previous unsuccessful trial and error extensive screening conditions amorphous parameters effect"
        if method_type:
            query = f"{method_type} {query}"
        return self.query(query, n_results=4)


class MarkdownRAG:
    """
    Gestionnaire RAG local pour documents Markdown (.mmd ou .md).
    Découpe le document par sections basées sur les headers (ex. #, ##, ###)
    instanciation).
    """

    def __init__(self, persist_directory: str = "logs/chroma_db_markdown"):
        self.persist_directory = persist_directory
        self.documents = []
        self.indexed = False
        
        if os.environ.get("SYNTHGRAPH_OFFLINE") == "1":
            raise RuntimeError("Le mode SYNTHGRAPH_OFFLINE est désactivé. ChromaDB est obligatoire pour éviter les hallucinations.")
            
        try:
            import chromadb
            from chromadb.utils import embedding_functions
            logger.info("Initialisation de ChromaDB (Markdown RAG)...")
            self.emb_fn = embedding_functions.DefaultEmbeddingFunction()
            self.client = chromadb.PersistentClient(path=self.persist_directory)
            try:
                self.client.delete_collection(name="markdown_chunks")
            except Exception: pass
            self.collection = self.client.create_collection(
                name="markdown_chunks", 
                embedding_function=self.emb_fn
            )
        except Exception as e:
            logger.error(f"Erreur fatale ChromaDB : {e}")
            raise RuntimeError(f"Impossible de charger ChromaDB ou le modèle d'embedding (MarkdownRAG) : {e}")

    def index_markdown(self, markdown_text: str) -> int:
        """
        Découpe un texte markdown en sections basées sur les headers (#, ##, ###).
        """
        import re
        import gc
        if not markdown_text.strip():
            logger.warning("Texte vide fourni pour la vectorisation.")
            return 0
            
        logger.info("Découpage du document Markdown par sections...")
        
        sections = []
        lines = markdown_text.split("\n")
        current_header = "Introduction / Title"
        current_content = []
        header_pattern = re.compile(r"^(#{1,6})\s+(.*)$")
        
        for line in lines:
            match = header_pattern.match(line)
            if match:
                if current_content:
                    sections.append({
                        "header": current_header,
                        "content": "\n".join(current_content).strip()
                    })
                    current_content = []
                current_header = line.strip()
            else:
                current_content.append(line)
                
        if current_content:
            sections.append({
                "header": current_header,
                "content": "\n".join(current_content).strip()
            })
            
        self.documents = []
        idx = 0
        for section in sections:
            header = section["header"]
            content = section["content"]
            if not content:
                continue
                
            if len(content) > 1500:
                from langchain_text_splitters import RecursiveCharacterTextSplitter
                splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=150)
                sub_chunks = splitter.split_text(content)
                for sub_idx, chunk in enumerate(sub_chunks):
                    full_text = f"Section: {header}\n\nContent (Part {sub_idx+1}):\n{chunk}"
                    self.documents.append(full_text)
            else:
                full_text = f"Section: {header}\n\nContent:\n{content}"
                self.documents.append(full_text)
            idx += 1
            
        if not self.documents:
            logger.warning("Aucune section markdown trouvée à indexer.")
            return 0
            
        try:
            logger.info(f"Vectorisation ChromaDB de {len(self.documents)} chunks markdown...")
            ids = [f"sec_{i}" for i in range(len(self.documents))]
            metadatas = [{"header": "header", "sub_chunk": 0} for i in range(len(self.documents))]
            self.collection.add(documents=self.documents, metadatas=metadatas, ids=ids)
        except Exception as e:
            logger.error(f"Erreur fatale lors de la vectorisation ChromaDB : {e}")
            raise RuntimeError(f"Vectorisation ChromaDB échouée (MarkdownRAG) : {e}")
                
        self.indexed = True
        gc.collect()
        return len(self.documents)

    def query(self, query_texts: str, n_results: int = 3) -> str:
        """
        Cherche les sections les plus pertinentes et les concatène.
        """
        if not self.indexed:
            logger.warning("Aucun document indexé pour la requête RAG.")
            return ""
            
        logger.info(f"Recherche contexte RAG : '{query_texts}' (top {n_results})")
        
        try:
            results = self.collection.query(
                query_texts=[query_texts],
                n_results=n_results
            )
            documents = results.get('documents', [[]])[0]
            return "\n\n---\n\n".join(documents)
        except Exception as e:
            logger.error(f"Erreur fatale lors de la requête ChromaDB : {e}")
            raise RuntimeError(f"Requête ChromaDB échouée (MarkdownRAG) : {e}")


class BibleRAG:
    """
    Base de connaissances persistante pour l'Agent Thermodynamicien (Dual-RAG).
    Conserve les ouvrages de référence (textbooks, reviews) sans jamais les effacer.
    """
    
    def __init__(self, persist_directory: str = "logs/chroma_db_bible"):
        self.persist_directory = persist_directory
        self.collection = None
        
        if os.environ.get("SYNTHGRAPH_OFFLINE") == "1":
            raise RuntimeError("Le mode SYNTHGRAPH_OFFLINE est désactivé. ChromaDB est obligatoire pour éviter les hallucinations.")
            
        try:
            import chromadb
            from chromadb.utils import embedding_functions
            
            os.makedirs(self.persist_directory, exist_ok=True)
            client = chromadb.PersistentClient(path=self.persist_directory)
            
            emb_fn = embedding_functions.DefaultEmbeddingFunction()
            
            self.collection = client.get_or_create_collection(
                name="synthgraph_bible",
                embedding_function=emb_fn
            )
            logger.info(f"BibleRAG initialisée avec succès dans {self.persist_directory}")
        except Exception as e:
            logger.error(f"Erreur fatale ChromaDB Bible : {e}")
            raise RuntimeError(f"Impossible de charger ChromaDB ou le modèle d'embedding (BibleRAG) : {e}")

    def ingest_bible(self, folder_path: str = "data/bible_documents/"):
        """
        Ingère les documents PDF de référence dans la base persistante.
        N'efface pas les documents existants.
        """
        import fitz  # PyMuPDF
        folder = Path(folder_path)
        if not folder.exists():
            folder.mkdir(parents=True, exist_ok=True)
            logger.warning(f"Le dossier Bible {folder_path} n'existait pas et a été créé. Placez-y vos PDF.")
            return 0
            
        pdf_files = list(folder.glob("*.pdf"))
        if not pdf_files:
            logger.info(f"Aucun PDF trouvé dans {folder_path} pour la Bible.")
            return 0
            
        splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
        total_chunks = 0
        
        existing_sources = set()
        if self.collection is not None:
            try:
                result = self.collection.get(include=["metadatas"])
                if result and "metadatas" in result and result["metadatas"]:
                    for meta in result["metadatas"]:
                        if meta and "source" in meta:
                            existing_sources.add(meta["source"])
            except Exception as e:
                logger.warning(f"Impossible de vérifier les sources existantes : {e}")
        
        for pdf_path in pdf_files:
            if pdf_path.name in existing_sources:
                logger.info(f"Ouvrage déjà indexé (ignoré) : {pdf_path.name}")
                continue
                
            logger.info(f"Lecture du textbook : {pdf_path.name}")
            try:
                doc = fitz.open(str(pdf_path))
                full_text = ""
                for page in doc:
                    full_text += page.get_text("text") + "\n"
                    
                chunks = splitter.split_text(full_text)
                
                if self.collection is not None and chunks:
                    # Utiliser le hash du nom du fichier et l'index pour des IDs uniques
                    ids = [f"{pdf_path.stem}_{i}" for i in range(len(chunks))]
                    metadatas = [{"source": pdf_path.name} for _ in chunks]
                    
                    # ChromaDB a une limite de lot (max batch size = 5461)
                    # On découpe donc l'ajout en sous-lots de 5000
                    batch_size = 5000
                    for i in range(0, len(chunks), batch_size):
                        self.collection.add(
                            documents=chunks[i:i+batch_size], 
                            metadatas=metadatas[i:i+batch_size], 
                            ids=ids[i:i+batch_size]
                        )
                        
                    total_chunks += len(chunks)
                    logger.info(f"Ajouté {len(chunks)} chunks depuis {pdf_path.name} à la Bible.")
            except Exception as e:
                logger.error(f"Erreur d'ingestion de {pdf_path.name} : {e}")
                
        # Construction de l'index BM25 à la fin de l'ingestion
        self.build_bm25_index()
        return total_chunks

    def build_bm25_index(self):
        """Construit l'index BM25 en mémoire à partir de la base ChromaDB."""
        try:
            from rank_bm25 import BM25Okapi
            self.bm25_corpus = []
            self.bm25_metadatas = []
            if self.collection is not None:
                logger.info("Construction de l'index BM25 en mémoire...")
                result = self.collection.get(include=["documents", "metadatas"])
                if result and "documents" in result:
                    self.bm25_corpus = result["documents"]
                    self.bm25_metadatas = result["metadatas"]
                    
                tokenized_corpus = [doc.lower().split() for doc in self.bm25_corpus]
                if tokenized_corpus:
                    self.bm25 = BM25Okapi(tokenized_corpus)
                    logger.info(f"Index BM25 construit avec {len(tokenized_corpus)} chunks.")
                else:
                    self.bm25 = None
            else:
                self.bm25 = None
        except Exception as e:
            logger.error(f"Erreur lors de la construction BM25 : {e}")
            self.bm25 = None

    def query_bible_hybrid(self, query: str, n_results: int = 10, synthesis_routes: list[str] = None) -> list[dict]:
        """
        Recherche hybride: ChromaDB (sémantique) + BM25 (mots-clés).
        Retourne une liste de chunks dédupliqués.
        Si synthesis_routes est fourni, filtre ou favorise les documents dont la source correspond aux méthodes.
        """
        results_list = []
        seen_docs = set()
        
        # Enrichir la requête pour ChromaDB
        chroma_query = query
        valid_routes = [r for r in (synthesis_routes or []) if r and r.lower() not in ["unknown", "autre"]]
        if valid_routes:
            routes_str = " or ".join(valid_routes)
            chroma_query = f"{query} (synthesis method: {routes_str})"
            logger.info(f"Filtre de méthode activé : {routes_str}")
            
        # 1. Recherche ChromaDB
        try:
            chroma_res = self.collection.query(query_texts=[chroma_query], n_results=n_results)
            docs = chroma_res.get('documents', [[]])[0]
            metas = chroma_res.get('metadatas', [[{}]])[0]
            for d, m in zip(docs, metas):
                if d not in seen_docs:
                    seen_docs.add(d)
                    results_list.append({"content": d, "source": m.get('source', 'Unknown')})
        except Exception as e:
            logger.error(f"Erreur ChromaDB query: {e}")
            raise RuntimeError(f"Requête ChromaDB échouée (BibleRAG) : {e}")
                
        # 2. Recherche BM25
        if getattr(self, 'bm25', None) is not None:
            try:
                # Ajouter la route à la requête tokenisée pour booster son score
                bm25_query = query
                if valid_routes:
                    for route in valid_routes:
                        bm25_query += f" {route} {route}" # Double poids pour chaque route
                    
                tokenized_query = bm25_query.lower().split()
                bm25_scores = self.bm25.get_scores(tokenized_query)
                # Obtenir les indices des top_n scores
                import numpy as np
                top_indices = np.argsort(bm25_scores)[::-1][:n_results]
                
                for idx in top_indices:
                    if bm25_scores[idx] > 0:
                        d = self.bm25_corpus[idx]
                        m = self.bm25_metadatas[idx]
                        if d not in seen_docs:
                            seen_docs.add(d)
                            results_list.append({"content": d, "source": m.get('source', 'Unknown')})
            except Exception as e:
                logger.error(f"Erreur BM25 query: {e}")
                
        # 3. Filtrage / Boost basé sur la méthode
        if valid_routes:
            filtered_results = []
            lower_routes = [r.lower() for r in valid_routes]
            
            # Séparer ceux qui matchent de ceux qui ne matchent pas
            for r in results_list:
                src = r["source"].lower()
                # Ex: "sol-gel" dans "D1Sol-GelScience" ou "hydrothermal" dans "Handbook_of_hydrothermal..."
                matched = any((route in src or route.replace("-", "") in src) for route in lower_routes)
                if matched:
                    filtered_results.insert(0, r) # Boost (mettre au début)
                else:
                    filtered_results.append(r)
            results_list = filtered_results
            
        return results_list[:n_results*2] # Retourner au max 20 résultats (10 chroma + 10 BM25) pour le Reranker

    def query_bible(self, query: str, n_results: int = 3) -> str:
        """Méthode fallback classique. Renvoie MAX 3 chunks ultra-pertinents."""
        chunks = self.query_bible_hybrid(query, n_results)
        if not chunks:
            return "Avertissement: Aucun résultat trouvé."
            
        output = []
        # STRICT LIMIT to 3 chunks to prevent context dilution (sycophancy)
        for c in chunks[:3]:
            output.append(f"[Source: {c['source']}]\n{c['content']}")
            
        return "\n\n---\n\n".join(output)
