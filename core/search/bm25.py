# Argus RAG BM25 Keyword Search
# Native leichtgewichtige Python-Implementierung für BM25

import math
import re
from typing import List, Dict, Any, Optional

class BM25Index:
    """In-Memory BM25 Indexer für Dokument-Chunks aus ChromaDB."""

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.documents: List[Dict[str, Any]] = []
        self.corpus_size = 0
        self.avg_doc_len = 0.0
        self.doc_lengths: List[int] = []
        self.doc_term_freqs: List[Dict[str, int]] = []
        self.term_doc_freqs: Dict[str, int] = {}  # In wie vielen Dokumenten kommt der Term vor (n_q)

    def _tokenize(self, text: str) -> List[str]:
        """Einfacher deutscher Tokenizer (Kleinschreibung, nur alphanumerische Zeichen)."""
        if not text:
            return []
        # In Kleinschreibung konvertieren und nach Wortzeichen splitten
        tokens = re.findall(r'\w+', text.lower())
        return tokens

    def index_documents(self, chunks: List[Dict[str, Any]]):
        """Indiziert die übergebenen Chunks für die BM25-Suche."""
        self.documents = chunks
        self.corpus_size = len(chunks)
        
        if self.corpus_size == 0:
            self.avg_doc_len = 0.0
            self.doc_lengths = []
            self.doc_term_freqs = []
            self.term_doc_freqs = {}
            return

        self.doc_lengths = []
        self.doc_term_freqs = []
        self.term_doc_freqs = {}

        total_len = 0
        for chunk in chunks:
            text = chunk.get("text", "")
            tokens = self._tokenize(text)
            doc_len = len(tokens)
            self.doc_lengths.append(doc_len)
            total_len += doc_len

            # Frequenzen für dieses Dokument berechnen
            tf: Dict[str, int] = {}
            for token in tokens:
                tf[token] = tf.get(token, 0) + 1
            self.doc_term_freqs.append(tf)

            # Dokumentfrequenzen (DF) aktualisieren
            for token in tf.keys():
                self.term_doc_freqs[token] = self.term_doc_freqs.get(token, 0) + 1

        self.avg_doc_len = total_len / self.corpus_size

    def _idf(self, term: str) -> float:
        """Berechnet das Inverse Document Frequency (IDF) für einen Term."""
        n_q = self.term_doc_freqs.get(term, 0)
        # Standard-BM25-IDF mit Glättung
        return math.log((self.corpus_size - n_q + 0.5) / (n_q + 0.5) + 1.0)

    def search(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """Sucht im Index nach der Query und gibt die Top-K Chunks mit Scores zurück."""
        if self.corpus_size == 0:
            return []

        query_tokens = self._tokenize(query)
        if not query_tokens:
            return []

        scores: List[float] = [0.0] * self.corpus_size

        for token in query_tokens:
            if token not in self.term_doc_freqs:
                continue
            
            idf_val = self._idf(token)
            
            for doc_idx in range(self.corpus_size):
                tf = self.doc_term_freqs[doc_idx].get(token, 0)
                if tf == 0:
                    continue
                
                doc_len = self.doc_lengths[doc_idx]
                
                # BM25 Formel-Komponenten
                numerator = tf * (self.k1 + 1)
                denominator = tf + self.k1 * (1 - self.b + self.b * (doc_len / self.avg_doc_len))
                
                scores[doc_idx] += idf_val * (numerator / denominator)

        # Chunks mit Scores paaren und sortieren
        scored_chunks = []
        for doc_idx, score in enumerate(scores):
            if score > 0.0:
                chunk = dict(self.documents[doc_idx])
                # Füge BM25-Score hinzu (normalisiert für Vergleichbarkeit)
                chunk["bm25_score"] = score
                # Setze Standard-Score als BM25-Score
                chunk["score"] = score
                scored_chunks.append(chunk)

        # Nach Score absteigend sortieren
        scored_chunks.sort(key=lambda x: x.get("bm25_score", 0.0), reverse=True)
        return scored_chunks[:top_k]
