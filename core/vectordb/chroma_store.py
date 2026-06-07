# NSI-RAGsystem Chroma Store
# ChromaDB Wrapper mit 2 Collections (lokal/cloud)

import structlog
from pathlib import Path
from typing import Optional
import hashlib
import os

import chromadb
from chromadb.config import Settings

logger = structlog.get_logger(__name__)

try:
    from core.llm.ollama_client import LocalLLMClient as OllamaClient
    OLLAMA_AVAILABLE = True
except ImportError:
    OLLAMA_AVAILABLE = False


class ChromaStore:
    """ChromaDB Wrapper mit 2 Collections (lokal f端r sensible, cloud f端r 鰂fentliche Dokumente)."""

    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(ChromaStore, cls).__new__(cls)
        return cls._instance

    def __init__(
        self,
        local_path: str = None,
        cloud_path: str = None,
    ):
        local_path = local_path or os.environ.get("CHROMA_LOCAL_PATH", "data/chroma_local")
        cloud_path = cloud_path or os.environ.get("CHROMA_CLOUD_PATH", "data/chroma_cloud")
        use_persistent = os.environ.get("CHROMA_PERSISTENT", "true").lower() == "true"
        config_key = (local_path, cloud_path, use_persistent)

        if (
            hasattr(self, "_initialized")
            and self._initialized
            and getattr(self, "_config_key", None) == config_key
        ):
            return
        self._initialized = True
        self._config_key = config_key

        self.local_path = local_path
        self.cloud_path = cloud_path
        self.use_persistent = use_persistent
        self.logger = logger.bind()
        self.client = None
        self.collection_local = None
        self.collection_cloud = None

        # ChromaDB initialisieren (embedded, persistent)
        self._init_chroma()

    def _init_chroma(self):
        """Initialisiert ChromaDB Client."""
        try:
            # In-Memory f端r Tests, Persistent f端r Produktiv
            if self.use_persistent:
                settings = Settings(
                    is_persistent=True,
                    persist_directory=self.local_path,
                )
                self.client = chromadb.Client(settings)
            else:
                self.client = chromadb.Client(Settings(allow_reset=True))

            # Collections erstellen/ laden
            self.collection_local = self.client.get_or_create_collection(
                name="nsi_local",
                metadata={"hnsw:space": "cosine", "dim": 768},
            )
            self.collection_cloud = self.client.get_or_create_collection(
                name="nsi_cloud",
                metadata={"hnsw:space": "cosine", "dim": 1536},
            )

            logger.info("chroma_store.initialized")

        except Exception as e:
            logger.error("chroma_store.init_error", fehler=str(e))
            raise

    def _get_embedding(self, text: str, collection_name: str) -> list[float]:
        """Generiert Embedding f端r Text."""
        if not OLLAMA_AVAILABLE:
            raise RuntimeError("Ollama nicht verf端gbar f端r Embeddings")

        client = OllamaClient()

        if collection_name == "nsi_local":
            model = "nomic-embed-text"  # lokal
        else:
            model = "mistral-embed"  # cloud (fallback auf lokal)

        try:
            embedding = client.embed(text, model=model)
            return embedding
        except Exception as e:
            logger.warning(
                "chroma_store.embedding_fallback",
                collection=collection_name,
                fehler=str(e),
            )
            # Fallback auf lokal
            return client.embed(text, model="nomic-embed-text")

    def _generate_chunk_id(self, chunk: dict) -> str:
        """Generiert SHA256-ID f端r Chunk (f端r Duplikaterkennung)."""
        source = chunk.get("quelle", "")
        page = chunk.get("seite", 0)
        typ = chunk.get("typ", "")
        text = chunk.get("text", "")[:50]

        data = f"{source}:{page}:{typ}:{text}"
        return hashlib.sha256(data.encode()).hexdigest()[:32]

    def add_chunks(self, chunks: list[dict], collection_name: str) -> int:
        """
        F端gt Chunks in die Collection ein.

        Args:
            chunks: List von Chunks mit text, typ, seite, quelle
            collection_name: "nsi_local" oder "nsi_cloud"

        Returns:
            Anzahl der eingef端gten Chunks
        """
        if collection_name == "nsi_local":
            collection = self.collection_local
        elif collection_name == "nsi_cloud":
            collection = self.collection_cloud
        else:
            raise ValueError(f"Unbekannte Collection: {collection_name}")

        if not chunks:
            return 0

        ids = []
        documents = []
        metadatas = []
        embeddings = []

        for chunk in chunks:
            chunk_id = self._generate_chunk_id(chunk)

            # Embedding generieren
            try:
                embedding = self._get_embedding(
                    chunk.get("embedding_text", chunk.get("text", "")),
                    collection_name,
                )
            except Exception as e:
                logger.warning(
                    "chroma_store.chunk_skipped",
                    seite=chunk.get("seite"),
                    fehler=str(e),
                )
                continue

            ids.append(chunk_id)
            documents.append(chunk.get("text", ""))
            
            meta = {
                "quelle": chunk.get("quelle", ""),
                "seite": chunk.get("seite", 0),
                "typ": chunk.get("typ", ""),
                "chunk_id": chunk_id,
            }
            if "kategorie" in chunk:
                meta["kategorie"] = chunk["kategorie"]
            if "dateityp" in chunk:
                meta["dateityp"] = chunk["dateityp"]
            for field in (
                "source_path",
                "ingest_order",
                "source_chunk_order",
                "total_files",
                "source_readonly",
                "source_sha256",
            ):
                if field in chunk:
                    meta[field] = chunk[field]
                
            metadatas.append(meta)
            embeddings.append(embedding)

        if ids:
            collection.add(
                ids=ids,
                documents=documents,
                metadatas=metadatas,
                embeddings=embeddings,
            )
            logger.info(
                "chroma_store.chunks_added",
                count=len(ids),
                collection=collection_name,
            )
            return len(ids)

        return 0

    def query(
        self, prompt: str, collection_name: str, top_k: int = 5, where: Optional[dict] = None
    ) -> list[dict]:
        """
        Fragt die Collection ab.

        Args:
            prompt: Nutzer-Frage
            collection_name: "nsi_local" oder "nsi_cloud"
            top_k: Anzahl der Ergebnisse
            where: Optionaler Metadaten-Filter

        Returns:
            List von Ergebnissen mit text, quelle, seite, typ, score
        """
        if collection_name == "nsi_local":
            collection = self.collection_local
        elif collection_name == "nsi_cloud":
            collection = self.collection_cloud
        else:
            raise ValueError(f"Unbekannte Collection: {collection_name}")

        try:
            # Embedding f端r Prompt
            query_embedding = self._get_embedding(prompt, collection_name)
        except Exception as e:
            logger.error(
                "chroma_store.query_embedding_error",
                fehler=str(e),
            )
            return []

        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where=where,
            include=["documents", "metadatas", "distances"],
        )

        chunks = []
        if results and results.get("documents"):
            docs = results["documents"][0]
            metas = results.get("metadatas", [])[0] if results.get("metadatas") else []
            dists = results.get("distances", [])[0] if results.get("distances") else []

            for i, doc in enumerate(docs):
                metadata = dict(metas[i]) if metas else {}
                chunks.append({
                    **metadata,
                    "text": doc,
                    "score": 1 - (dists[i] if dists else 0.5),  # Distanz -> Similarity
                })

        return chunks

    def query_both(self, prompt: str, top_k: int = 3, where: Optional[dict] = None) -> list[dict]:
        """
        Fragt beide Collections ab und fusioniert Ergebnisse.

        Args:
            prompt: Nutzer-Frage
            top_k: Anzahl pro Collection
            where: Optionaler Metadaten-Filter

        Returns:
            List von Ergebnissen sortiert nach Score
        """
        local_results = self.query(prompt, "nsi_local", top_k, where)
        cloud_results = self.query(prompt, "nsi_cloud", top_k, where)

        # zusammenf端hren
        all_results = local_results + cloud_results

        # nach Score sortieren
        all_results.sort(key=lambda x: x.get("score", 0), reverse=True)

        return all_results

    def collection_stats(self) -> dict:
        """Gibt Statistiken für beide Collections zurück."""
        return {
            "nsi_local": self.collection_local.count(),
            "nsi_cloud": self.collection_cloud.count(),
        }

    def get_all_chunks(self, collection_name: str, where: Optional[dict] = None) -> list[dict]:
        """Gibt alle Chunks einer Collection zurück."""
        if collection_name == "nsi_local":
            collection = self.collection_local
        elif collection_name == "nsi_cloud":
            collection = self.collection_cloud
        else:
            raise ValueError(f"Unbekannte Collection: {collection_name}")

        results = collection.get(where=where, include=["documents", "metadatas"])
        chunks = []
        if results and results.get("documents"):
            docs = results["documents"]
            metas = results.get("metadatas", [])
            ids = results.get("ids", [])
            for i, doc in enumerate(docs):
                metadata = dict(metas[i]) if metas else {}
                chunks.append({
                    **metadata,
                    "text": doc,
                    "chunk_id": ids[i] if ids else "",
                })
        return chunks

    def get_all_chunks_both(self, where: Optional[dict] = None) -> list[dict]:
        """Gibt alle Chunks aus beiden Collections zurück."""
        return self.get_all_chunks("nsi_local", where) + self.get_all_chunks("nsi_cloud", where)

    def reset(self):
        """Löscht beide Collections und erstellt sie neu."""
        try:
            self.client.delete_collection("nsi_local")
        except Exception as e:
            logger.warning("chroma_store.delete_local_failed", fehler=str(e))
        try:
            self.client.delete_collection("nsi_cloud")
        except Exception as e:
            logger.warning("chroma_store.delete_cloud_failed", fehler=str(e))
        self._init_chroma()
        logger.info("chroma_store.reset_complete")
