# Tests für Argus RAG (Advanced RAG Features)

import unittest
from unittest.mock import Mock, patch
from pathlib import Path
import sys
import os

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.search.bm25 import BM25Index
from core.rag.reranker import LocalReranker
from core.rag.rag_pipeline import RAGPipeline


class TestAdvancedRAG(unittest.TestCase):
    """Tests für die Advanced RAG Features (BM25, RRF, Reranker, Metadata)."""

    def test_bm25_tokenization_and_search(self):
        """Testet den BM25 Tokenizer und die Suchfunktionalität."""
        index = BM25Index()
        
        # Test 1: Tokenizer splittet und verarbeitet Kleinschreibung
        tokens = index._tokenize("Das ist ein Test-Satz für Argus RAG.")
        self.assertIn("das", tokens)
        self.assertIn("ist", tokens)
        self.assertIn("test", tokens)
        self.assertIn("satz", tokens)
        self.assertIn("rag", tokens)

        # Test 2: Indexierung und Suche
        chunks = [
            {"text": "Python ist eine beliebte Programmiersprache", "quelle": "py.txt", "seite": 1},
            {"text": "ChromaDB ist eine schnelle Vektordatenbank", "quelle": "db.txt", "seite": 1},
            {"text": "Argus RAG kombiniert Vektorsuche mit BM25", "quelle": "argus.txt", "seite": 1}
        ]
        index.index_documents(chunks)
        
        # Suche nach "ChromaDB"
        results = index.search("ChromaDB", top_k=1)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["quelle"], "db.txt")
        self.assertIn("bm25_score", results[0])

    def test_reciprocal_rank_fusion(self):
        """Testet die Reciprocal Rank Fusion (RRF)."""
        pipeline = RAGPipeline(chroma_store=Mock(), model_router=Mock(), local_reranker=Mock())
        
        vector_results = [
            {"text": "A", "quelle": "1.txt", "seite": 1},
            {"text": "B", "quelle": "2.txt", "seite": 1},
            {"text": "C", "quelle": "3.txt", "seite": 1}
        ]
        
        bm25_results = [
            {"text": "C", "quelle": "3.txt", "seite": 1},
            {"text": "A", "quelle": "1.txt", "seite": 1},
            {"text": "D", "quelle": "4.txt", "seite": 1}
        ]
        
        # RRF ausführen (k=60)
        # Element C steht auf Rang 3 (Index 2) bei Vektor und Rang 1 (Index 0) bei BM25
        # Element A steht auf Rang 1 (Index 0) bei Vektor und Rang 2 (Index 1) bei BM25
        merged = pipeline._reciprocal_rank_fusion(vector_results, bm25_results, k=60)
        
        # Verifizieren, dass A und C oben stehen
        self.assertTrue(len(merged) >= 4)
        top_texts = [x["text"] for x in merged[:2]]
        self.assertIn("A", top_texts)
        self.assertIn("C", top_texts)

    def test_reranker_fallback_behavior(self):
        """Testet, dass der Reranker bei Inaktivität oder Fehlern die Chunks unverändert durchreicht."""
        # Reranker mit deaktivierter Option initialisieren
        with patch.dict(os.environ, {"RAG_RERANKING_ENABLED": "false"}):
            reranker = LocalReranker()
            chunks = [{"text": "A"}, {"text": "B"}]
            results = reranker.rerank("frage", chunks, top_n=1)
            
            # Sollte unverändert das erste Element zurückgeben
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0]["text"], "A")

    @patch("core.vectordb.chroma_store.ChromaStore")
    @patch("core.llm.model_router.ModelRouter")
    def test_rag_pipeline_query_with_filters(self, mock_router, mock_chroma):
        """Testet, dass RAGPipeline.query den where-Filter an ChromaDB weitergibt."""
        mock_chroma_inst = mock_chroma.return_value
        mock_chroma_inst.query_both.return_value = [
            {"text": "Inhalt", "quelle": "doc.pdf", "seite": 1, "typ": "tabelle"}
        ]
        mock_router_inst = mock_router.return_value
        mock_router_inst.generate.return_value = "Antwort"
        
        pipeline = RAGPipeline(chroma_store=mock_chroma_inst, model_router=mock_router_inst)
        
        # Query mit Filter abfeuern
        filter_dict = {"typ": "tabelle"}
        # Wir deaktiveren Hybrid-Search für diesen Test, um Vektorsuche-Parameter direkt zu prüfen
        with patch.dict(os.environ, {"RAG_HYBRID_SEARCH_ENABLED": "false"}):
            pipeline.query("Welche Daten stehen in der Tabelle?", filter_metadata=filter_dict)
            
            # Verifizieren, dass query_both mit where=filter_dict aufgerufen wurde
            mock_chroma_inst.query_both.assert_called_with(
                "Welche Daten stehen in der Tabelle?", 
                pipeline.MAX_CHUNKS * 3, 
                where=filter_dict
            )


if __name__ == "__main__":
    unittest.main()
