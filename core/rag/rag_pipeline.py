# NSI-RAGsystem RAG Pipeline
# LlamaIndex Query-Pipeline

import structlog
import os
from typing import Optional

logger = structlog.get_logger(__name__)

try:
    from core.vectordb.chroma_store import ChromaStore
    from core.llm.model_router import ModelRouter
    from core.search.bm25 import BM25Index
    from core.rag.reranker import LocalReranker

    CHROMA_STORE = ChromaStore()
    MODEL_ROUTER = ModelRouter()
    LOCAL_RERANKER = LocalReranker()
except ImportError as e:
    logger.warning("core_imports_failed", fehler=str(e))


class RAGPipeline:
    """LlamaIndex-basierte Query-Pipeline f端r RAG-Abfragen."""

    # System-Prompt (deutsch)
    SYSTEM_PROMPT = (
        "Du bist Argus, ein präziser und allessehender Assistent. "
        "Beantworte Fragen ausschließlich auf Basis der bereitgestellten Dokumente. "
        "Antworte immer auf Deutsch. Wenn die Antwort nicht in den Dokumenten steht, "
        "sage das klar. Erfinde keine Informationen."
    )

    # Max Kontext-Chunks
    MAX_CHUNKS = 5

    def __init__(
        self,
        chroma_store: ChromaStore = None,
        model_router: ModelRouter = None,
        local_reranker: LocalReranker = None,
    ):
        self.chroma_store = chroma_store or CHROMA_STORE
        self.model_router = model_router or MODEL_ROUTER
        self.local_reranker = local_reranker or LOCAL_RERANKER

    def query(self, user_prompt: str, filter_metadata: Optional[dict] = None) -> dict:
        """
        Führt eine RAG-Abfrage durch.

        Args:
            user_prompt: Nutzer-Frage
            filter_metadata: Optionaler Metadaten-Filter

        Returns:
            {
                "antwort": str,
                "quellen": list[dict],
                "modell": str,
                "vertraulich": bool,
            }
        """
        logger.info(
            "rag_pipeline.query_start",
            prompt_length=len(user_prompt),
            filter_metadata=filter_metadata,
        )

        try:
            # 1. PromptInjectionBlocker prüfen (hier vereinfacht)
            if self._is_prompt_injection(user_prompt):
                return {
                    "antwort": "Ihre Anfrage wurde nicht verarbeitet. Verdacht auf Prompt-Injection erkannt.",
                    "quellen": [],
                    "modell": "",
                    "vertraulich": False,
                }

            # 3. Retrieval (Hybrid Search & Fallbacks)
            hybrid_enabled = os.environ.get("RAG_HYBRID_SEARCH_ENABLED", "true").lower() == "true"
            candidate_k = self.MAX_CHUNKS * 3

            if hybrid_enabled:
                # A. Vektorsuche
                vector_chunks = self.chroma_store.query_both(user_prompt, candidate_k, where=filter_metadata)
                
                # B. BM25 Suche
                all_chunks = self.chroma_store.get_all_chunks_both(where=filter_metadata)
                if all_chunks and isinstance(all_chunks, list):
                    bm25_index = BM25Index()
                    bm25_index.index_documents(all_chunks)
                    bm25_chunks = bm25_index.search(user_prompt, top_k=candidate_k)
                else:
                    bm25_chunks = []
                
                # C. RRF Fusion
                candidates = self._reciprocal_rank_fusion(vector_chunks, bm25_chunks)
            else:
                # Nur Vektorsuche
                candidates = self.chroma_store.query_both(user_prompt, candidate_k, where=filter_metadata)

            # 4. Re-Ranking (Cross-Encoder)
            chunks = self.local_reranker.rerank(user_prompt, candidates, top_n=self.MAX_CHUNKS)

            if not chunks:
                return {
                    "antwort": "Es konnten keine relevanten Dokumente gefunden werden.",
                    "quellen": [],
                    "modell": "",
                    "vertraulich": False,
                }

            # 5. Kontext aufbauen
            context = self._build_context(chunks)

            # 5. Modell-Entscheidung basierend auf Collection
            vertraulich = any(
                c.get("quelle", "").endswith("_local")
                or c.get("typ") == "vertraulich"
                for c in chunks
            )

            # 6. Antwort generieren
            prompt = f"{self.SYSTEM_PROMPT}\n\nRelevante Dokumente:\n{context}\n\nFrage: {user_prompt}"

            antwort = self.model_router.generate(
                prompt=prompt,
                vertraulich=vertraulich,
            )

            # 7. Ergebnis zurückgeben
            result = {
                "antwort": antwort,
                "quellen": chunks,
                "modell": self.model_router.model_cloud if not vertraulich else self.model_router.model_local,
                "vertraulich": vertraulich,
            }

            logger.info(
                "rag_pipeline.query_complete",
                antwort_length=len(antwort),
                quellen_anzahl=len(chunks),
            )

            return result

        except Exception as e:
            logger.error(
                "rag_pipeline.error",
                fehler=str(e),
            )
            raise

    def _is_prompt_injection(self, prompt: str) -> bool:
        """
        Einfacher PromptInjectionBlocker.
        Prüft auf typische Injection-Muster.
        """
        injection_patterns = [
            "ignoriere deine anweisungen",
            "du bist jetzt",
            "system override",
            "ignore previous instructions",
            "give me the password",
        ]
        prompt_lower = prompt.lower()
        return any(pattern in prompt_lower for pattern in injection_patterns)

    def _get_embedding(self, text: str) -> list[float]:
        """Generiert Embedding f端r Text (gleiche Logik wie ChromaStore)."""
        return self.chroma_store._get_embedding(text, "nsi_local")

    def _build_context(self, chunks: list[dict]) -> str:
        """Baut den Kontext-String f端r den LLM."""
        context_parts = []
        for chunk in chunks:
            source = chunk.get("quelle", "unbekannt")
            page = chunk.get("seite", "?")
            chunk_text = chunk.get("text", "")  # Gesamter Chunk-Inhalt
            context_parts.append(f"[{source} S.{page}]\n{chunk_text}\n---")

        return "\n\n".join(context_parts)

    def _reciprocal_rank_fusion(self, vector_results: list[dict], bm25_results: list[dict], k: int = 60) -> list[dict]:
        """Fusioniert Ergebnisse aus Vektorsuche und BM25 mittels Reciprocal Rank Fusion (RRF)."""
        rrf_scores = {}

        def get_key(chunk):
            return chunk.get("text", "")

        for rank, chunk in enumerate(vector_results):
            key = get_key(chunk)
            rrf_scores[key] = rrf_scores.get(key, 0.0) + (1.0 / (k + rank + 1))

        for rank, chunk in enumerate(bm25_results):
            key = get_key(chunk)
            rrf_scores[key] = rrf_scores.get(key, 0.0) + (1.0 / (k + rank + 1))

        merged_chunks = {}
        for chunk in vector_results + bm25_results:
            key = get_key(chunk)
            if key not in merged_chunks:
                merged_chunks[key] = dict(chunk)
            merged_chunks[key]["score"] = rrf_scores[key]

        sorted_chunks = list(merged_chunks.values())
        sorted_chunks.sort(key=lambda x: x.get("score", 0.0), reverse=True)
        return sorted_chunks
