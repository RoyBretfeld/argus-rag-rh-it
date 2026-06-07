# Argus RAG Local Reranker
# Lokales Re-Ranking mit Cross-Encoder-Modellen (sentence-transformers)

import os
import structlog
from typing import List, Dict, Any

logger = structlog.get_logger(__name__)

# Versuche sentence-transformers zu importieren, ansonsten Fallback aktivieren
try:
    from sentence_transformers import CrossEncoder
    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SENTENCE_TRANSFORMERS_AVAILABLE = False
    logger.warning("reranker.sentence_transformers_missing", message="sentence-transformers nicht installiert. Re-Ranking wird übersprungen.")


class LocalReranker:
    """Lokaler Re-Ranker zur präzisen Neusortierung von RAG-Chunks via Cross-Encoder."""

    def __init__(self):
        self.enabled = os.environ.get("RAG_RERANKING_ENABLED", "true").lower() == "true"
        self.model_name = os.environ.get("RAG_RERANKER_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2")
        self.model = None

        if self.enabled and SENTENCE_TRANSFORMERS_AVAILABLE:
            try:
                logger.info("reranker.loading_model", model_name=self.model_name)
                # Lädt den Cross-Encoder (automatische GPU/CPU Zuweisung durch sentence-transformers)
                self.model = CrossEncoder(self.model_name)
                logger.info("reranker.model_loaded_successfully", model_name=self.model_name)
            except Exception as e:
                logger.error("reranker.model_loading_failed", fehler=str(e))
                self.model = None

    def rerank(self, query: str, chunks: List[Dict[str, Any]], top_n: int = 5) -> List[Dict[str, Any]]:
        """
        Sortiert die Chunks basierend auf der Relevanz zum Query neu.

        Args:
            query: Die Suchanfrage des Users
            chunks: Liste von Chunks aus der Hybrid-Suche
            top_n: Anzahl der zurückzugebenden Chunks

        Returns:
            Die top_n am besten bewerteten Chunks
        """
        if not chunks:
            return []

        # Fallback: Falls nicht aktiviert, Ladefehler vorliegen oder Bib fehlt
        if not self.enabled or self.model is None:
            logger.debug("reranker.disabled_or_unavailable_fallback", count=len(chunks))
            return chunks[:top_n]

        try:
            logger.info("reranker.start_reranking", chunk_count=len(chunks), query=query[:30])
            
            # Paare für Cross-Encoder bauen: [Query, Dokumenten-Text]
            pairs = [[query, chunk.get("text", "")] for chunk in chunks]
            
            # Scores berechnen
            scores = self.model.predict(pairs)
            
            # Scores in Chunks eintragen und indexieren
            for idx, score in enumerate(scores):
                chunks[idx]["rerank_score"] = float(score)
                # Wir aktualisieren den Haupt-Score für Konsistenz in der Anzeige
                chunks[idx]["score"] = float(score)

            # Nach Rerank-Score absteigend sortieren
            reranked_chunks = sorted(chunks, key=lambda x: x.get("rerank_score", -999.0), reverse=True)
            
            logger.info("reranker.complete", top_score=reranked_chunks[0].get("rerank_score") if reranked_chunks else None)
            return reranked_chunks[:top_n]

        except Exception as e:
            logger.warning("reranker.execution_failed_fallback", fehler=str(e))
            # Lautloser Fallback bei Fehlern während der Vorhersage
            return chunks[:top_n]
