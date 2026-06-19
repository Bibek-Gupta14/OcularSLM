import os
import re
import logging
from typing import List, Dict, Any

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("WorkspaceVectorStore")

class FallbackVectorStore:
    """
    A pure-Python/numpy fallback vector database in case ChromaDB 
    fails to install or load on the host Windows system.
    """
    def __init__(self):
        self.documents = []
        self.embeddings = []
        self.metadatas = []
        self.ids = []
        self.model = None
        self._init_embedding_model()

    def _init_embedding_model(self):
        try:
            from sentence_transformers import SentenceTransformer
            logger.info("Initializing fallback sentence-transformers model (all-MiniLM-L6-v2)...")
            self.model = SentenceTransformer("all-MiniLM-L6-v2")
        except Exception as e:
            logger.warning(f"Failed to load sentence-transformers: {e}. Falling back to simple TF-IDF representation.")
            self.model = None

    def add(self, ids: List[str], documents: List[str], metadatas: List[Dict[str, Any]]):
        if not documents:
            return
        
        self.ids.extend(ids)
        self.documents.extend(documents)
        self.metadatas.extend(metadatas)
        
        if self.model:
            try:
                embeddings = self.model.encode(documents, convert_to_numpy=True)
                for emb in embeddings:
                    self.embeddings.append(emb)
            except Exception as e:
                logger.error(f"Failed to compute embeddings: {e}")
        else:
            # Create a simple bag-of-words / TF-IDF style placeholder vector for simple cosine search
            # if sentence-transformers is missing.
            for doc in documents:
                self.embeddings.append(self._simple_vectorize(doc))

    def _simple_vectorize(self, text: str) -> Dict[str, float]:
        # Extract alphanumeric words and build frequency map
        words = re.findall(r'\w+', text.lower())
        freq = {}
        for w in words:
            freq[w] = freq.get(w, 0.0) + 1.0
        return freq

    def _simple_cosine_similarity(self, vec1: Dict[str, float], vec2: Dict[str, float]) -> float:
        intersection = set(vec1.keys()) & set(vec2.keys())
        numerator = sum([vec1[x] * vec2[x] for x in intersection])
        sum1 = sum([vec1[x]**2 for x in vec1.keys()])
        sum2 = sum([vec2[x]**2 for x in vec2.keys()])
        denominator = (sum1 ** 0.5) * (sum2 ** 0.5)
        if not denominator:
            return 0.0
        return float(numerator) / denominator

    def query(self, query_texts: List[str], n_results: int = 5) -> Dict[str, Any]:
        if not query_texts:
            return {"documents": [[]], "metadatas": [[]], "distances": [[]]}
        
        query_text = query_texts[0]
        results = []

        if self.model:
            try:
                import numpy as np
                query_emb = self.model.encode([query_text], convert_to_numpy=True)[0]
                for idx, emb in enumerate(self.embeddings):
                    # Compute cosine similarity
                    dot_prod = np.dot(query_emb, emb)
                    norm_q = np.linalg.norm(query_emb)
                    norm_e = np.linalg.norm(emb)
                    sim = dot_prod / (norm_q * norm_e) if (norm_q * norm_e) > 0 else 0.0
                    results.append((sim, idx))
            except Exception as e:
                logger.error(f"Fallback embedding query failed: {e}")
                # Fallback to simple TF-IDF cosine if numpy search errors out
                query_vec = self._simple_vectorize(query_text)
                for idx, doc in enumerate(self.documents):
                    doc_vec = self._simple_vectorize(doc)
                    sim = self._simple_cosine_similarity(query_vec, doc_vec)
                    results.append((sim, idx))
        else:
            query_vec = self._simple_vectorize(query_text)
            for idx, doc in enumerate(self.documents):
                doc_vec = self._simple_vectorize(doc)
                sim = self._simple_cosine_similarity(query_vec, doc_vec)
                results.append((sim, idx))

        # Sort by similarity descending (highest first)
        results.sort(key=lambda x: x[0], reverse=True)
        top_results = results[:n_results]

        res_docs = []
        res_meta = []
        res_dist = []
        
        for sim, idx in top_results:
            res_docs.append(self.documents[idx])
            res_meta.append(self.metadatas[idx])
            # distance = 1 - similarity for matching chromadb format
            res_dist.append(1.0 - sim)

        return {
            "documents": [res_docs],
            "metadatas": [res_meta],
            "distances": [res_dist]
        }


class WorkspaceVectorStore:
    def __init__(self, persist_directory: str = "./.vector_store"):
        self.persist_directory = persist_directory
        self.use_fallback = False
        self.chroma_client = None
        self.collection = None
        self.fallback_db = None
        self._init_db()

    def _init_db(self):
        try:
            import chromadb
            from chromadb.config import Settings
            logger.info("Initializing ChromaDB client...")
            self.chroma_client = chromadb.PersistentClient(
                path=self.persist_directory,
                settings=Settings(anonymized_telemetry=False)
            )
            # Create or get collection
            self.collection = self.chroma_client.get_or_create_collection(
                name="workspace_files",
                metadata={"hnsw:space": "cosine"}
            )
            logger.info("ChromaDB initialized successfully.")
        except Exception as e:
            logger.warning(f"ChromaDB not available or failed to load: {e}. Switching to memory-efficient FallbackVectorStore.")
            self.use_fallback = True
            self.fallback_db = FallbackVectorStore()

    def index_workspace(self, root_dir: str = ".") -> int:
        """
        Scans the workspace directory, chunks files, and indexes them.
        Returns the number of chunks indexed.
        """
        # Clear existing entries in DB
        if not self.use_fallback:
            try:
                # Re-create collection to clear
                self.chroma_client.delete_collection("workspace_files")
                self.collection = self.chroma_client.create_collection(
                    name="workspace_files",
                    metadata={"hnsw:space": "cosine"}
                )
            except Exception as e:
                logger.warning(f"Failed to reset ChromaDB collection: {e}")
        else:
            self.fallback_db = FallbackVectorStore()

        ignore_dirs = {".git", ".vector_store", "__pycache__", "assets", "static", "node_modules", ".vscode"}
        ignore_extensions = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".pdf", ".pyc", ".db", ".zip", ".tar", ".gz"}

        ids = []
        documents = []
        metadatas = []
        chunk_count = 0

        for root, dirs, files in os.walk(root_dir):
            # Prune directory search path
            dirs[:] = [d for d in dirs if d not in ignore_dirs]
            
            for file in files:
                ext = os.path.splitext(file)[1].lower()
                if ext in ignore_extensions:
                    continue
                
                file_path = os.path.join(root, file)
                rel_path = os.path.relpath(file_path, root_dir)
                
                try:
                    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read()
                    
                    if not content.strip():
                        continue
                    
                    # Split content into overlapping chunks (e.g. 800 chars chunk, 200 overlap)
                    chunk_size = 800
                    overlap = 200
                    
                    for idx, start in enumerate(range(0, len(content), chunk_size - overlap)):
                        chunk = content[start:start + chunk_size]
                        chunk_id = f"{rel_path}_chunk_{idx}"
                        
                        ids.append(chunk_id)
                        documents.append(chunk)
                        metadatas.append({
                            "path": rel_path,
                            "filename": file,
                            "chunk_index": idx
                        })
                        chunk_count += 1
                        
                except Exception as e:
                    logger.warning(f"Error reading file {file_path} for vector index: {e}")

        # Add to vector store in batches to avoid size limits
        batch_size = 100
        for i in range(0, len(documents), batch_size):
            b_ids = ids[i:i+batch_size]
            b_docs = documents[i:i+batch_size]
            b_metas = metadatas[i:i+batch_size]
            
            if self.use_fallback:
                self.fallback_db.add(ids=b_ids, documents=b_docs, metadatas=b_metas)
            else:
                try:
                    # ChromaDB embeds using its default embedding model (sentence-transformers under the hood)
                    self.collection.add(ids=b_ids, documents=b_docs, metadatas=b_metas)
                except Exception as e:
                    logger.error(f"ChromaDB batch insertion failed: {e}. Falling back immediately.")
                    self.use_fallback = True
                    self.fallback_db = FallbackVectorStore()
                    self.fallback_db.add(ids=b_ids, documents=b_docs, metadatas=b_metas)

        logger.info(f"Indexed {chunk_count} code chunks across workspace.")
        return chunk_count

    def search(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Performs semantic search on workspace files.
        """
        if self.use_fallback:
            results = self.fallback_db.query(query_texts=[query], n_results=limit)
        else:
            try:
                results = self.collection.query(query_texts=[query], n_results=limit)
            except Exception as e:
                logger.error(f"ChromaDB query failed: {e}. Retrying via fallback.")
                if not self.fallback_db:
                    self.fallback_db = FallbackVectorStore()
                results = self.fallback_db.query(query_texts=[query], n_results=limit)

        formatted_results = []
        if results and "documents" in results and results["documents"]:
            docs = results["documents"][0]
            metas = results["metadatas"][0]
            dists = results["distances"][0] if "distances" in results else [0.0] * len(docs)
            
            for i in range(len(docs)):
                formatted_results.append({
                    "content": docs[i],
                    "metadata": metas[i],
                    "score": 1.0 - dists[i]  # Convert distance to similarity score
                })
        
        return formatted_results
