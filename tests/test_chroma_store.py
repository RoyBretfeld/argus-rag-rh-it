# Tests für ChromaStore

import unittest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.vectordb.chroma_store import ChromaStore


class TestChromaStore(unittest.TestCase):
    """Tests für ChromaStore."""

    def setUp(self):
        """Vorbereitung für Tests."""
        # In-Memory für Tests
        with patch.dict("os.environ", {"CHROMA_PERSISTENT": "false"}):
            self.store = ChromaStore()

    def tearDown(self):
        """Aufräumen nach Tests."""
        try:
            self.store.client.reset()
        except Exception:
            pass

    @patch("core.vectordb.chroma_store.OLLAMA_AVAILABLE", True)
    @patch("core.vectordb.chroma_store.OllamaClient")
    def test_add_chunks_local(self, mock_client):
        """Test 1: add_chunks nsi_local → count erhöht sich."""
        mock_client.return_value.embed.return_value = [0.1] * 768

        chunks = [
            {"text": "Test Chunk 1", "typ": "text", "quelle": "test.pdf", "seite": 1},
            {"text": "Test Chunk 2", "typ": "text", "quelle": "test.pdf", "seite": 2},
        ]

        count = self.store.add_chunks(chunks, "nsi_local")
        self.assertEqual(count, 2)
        self.assertEqual(self.store.collection_local.count(), 2)

    @patch("core.vectordb.chroma_store.OLLAMA_AVAILABLE", True)
    @patch("core.vectordb.chroma_store.OllamaClient")
    def test_query_top_k(self, mock_client):
        """Test 2: query gibt top_k Ergebnisse zurück."""
        mock_client.return_value.embed.return_value = [0.1] * 768

        # Chunks hinzufügen
        chunks = [
            {"text": "Python ist eine Programmiersprache", "typ": "text", "quelle": "doc.pdf", "seite": 1},
            {"text": "Java ist eine Programmiersprache", "typ": "text", "quelle": "doc2.pdf", "seite": 1},
            {"text": "C++ ist eine Programmiersprache", "typ": "text", "quelle": "doc3.pdf", "seite": 1},
        ]
        self.store.add_chunks(chunks, "nsi_local")

        # Query durchführen
        results = self.store.query("Welche Programmiersprachen?", "nsi_local", top_k=2)
        self.assertEqual(len(results), 2)

    @patch("core.vectordb.chroma_store.OLLAMA_AVAILABLE", True)
    @patch("core.vectordb.chroma_store.OllamaClient")
    def test_duplicate_chunk(self, mock_client):
        """Test 3: Duplikat-Chunk → überschrieben, nicht doppelt gespeichert."""
        mock_client.return_value.embed.return_value = [0.1] * 768

        chunks = [
            {"text": "Doppelter Text", "typ": "text", "quelle": "test.pdf", "seite": 1},
        ]

        # Erstes Mal hinzufügen
        self.store.add_chunks(chunks, "nsi_local")
        count1 = self.store.collection_local.count()

        # Selber Chunk nochmal hinzufügen
        self.store.add_chunks(chunks, "nsi_local")
        count2 = self.store.collection_local.count()

        # Sollte überschrieben sein, nicht doppelt
        self.assertEqual(count1, count2)

    @patch("core.vectordb.chroma_store.OLLAMA_AVAILABLE", True)
    @patch("core.vectordb.chroma_store.OllamaClient")
    def test_query_both(self, mock_client):
        """Test 4: query_both → Ergebnisse aus beiden Collections."""
        mock_client.return_value.embed.return_value = [0.1] * 768

        # In beide Collections was hinzufügen
        self.store.add_chunks(
            [{"text": "Lokaler Chunk", "typ": "text", "quelle": "local.pdf", "seite": 1}],
            "nsi_local"
        )
        self.store.add_chunks(
            [{"text": "Cloud Chunk", "typ": "text", "quelle": "cloud.pdf", "seite": 1}],
            "nsi_cloud"
        )

        # query_both aufrufen
        results = self.store.query_both("Irgendeine Frage", top_k=3)
        self.assertGreater(len(results), 0)


if __name__ == "__main__":
    unittest.main()
