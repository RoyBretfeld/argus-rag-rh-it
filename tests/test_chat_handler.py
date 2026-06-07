# Tests für ChatHandler mit Modus-Router

import unittest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from api.chat_handler import ChatHandler, Modus, ChatResult


class TestChatHandler(unittest.TestCase):
    """Tests für ChatHandler mit Modus-Router."""

    def setUp(self):
        """Vorbereitung für Tests."""
        self.mock_rag_pipeline = Mock()
        self.mock_web_search = Mock()
        self.mock_model_router = Mock()
        self.handler = ChatHandler(
            rag_pipeline=self.mock_rag_pipeline,
            web_search_pipeline=self.mock_web_search,
            model_router=self.mock_model_router,
        )

    def test_wissensbasis_modus(self):
        """Test 1: Modus WISSENSBASIS → RAGPipeline aufgerufen, WebSearch nicht."""
        self.mock_rag_pipeline.query.return_value = {
            "antwort": "Antwort aus Wissensbasis",
            "quellen": [{"text": "Chunk 1", "quelle": "doc.pdf", "seite": 1}],
            "modell": "mistral-7b-lokal",
            "vertraulich": True,
        }

        result = self.handler.answer("Frage?", Modus.WISSENSBASIS, vertraulich=True)

        self.mock_rag_pipeline.query.assert_called_once()
        self.mock_web_search.search_and_answer.assert_not_called()
        self.assertEqual(result.modus, Modus.WISSENSBASIS)
        self.assertIn("Wissensbasis", result.antwort)

    def test_internet_modus(self):
        """Test 2: Modus INTERNET → WebSearchPipeline aufgerufen, RAG nicht."""
        self.mock_web_search.search_and_answer.return_value = Mock(
            antwort="Antwort aus Internet",
            quellen=[{"titel": "Webseite", "url": "https://example.com"}],
            modell="mistral-large-2512",
            treffer=5,
        )
        self.mock_model_router.model_cloud = "mistral-large-2512"

        result = self.handler.answer("Frage?", Modus.INTERNET, vertraulich=False)

        self.mock_web_search.search_and_answer.assert_called_once()
        self.mock_rag_pipeline.query.assert_not_called()
        self.assertEqual(result.modus, Modus.INTERNET)

    def test_beides_modus(self):
        """Test 3: Modus BEIDES → beide aufgerufen, Synthese-Prompt übergeben."""
        self.mock_rag_pipeline.query.return_value = {
            "antwort": "RAG-Antwort",
            "quellen": [],
            "modell": "mistral-7b-lokal",
            "vertraulich": True,
        }
        self.mock_web_search.search_and_answer.return_value = Mock(
            antwort="Web-Antwort",
            quellen=[],
            modell="mistral-large-2512",
            treffer=5,
        )
        self.mock_model_router.generate.return_value = "Synthese-Antwort"

        result = self.handler.answer("Frage?", Modus.BEIDES, vertraulich=True)

        self.mock_rag_pipeline.query.assert_called_once()
        self.mock_web_search.search_and_answer.assert_called_once()
        self.mock_model_router.generate.assert_called_once()

    def test_chat_result_all_fields(self):
        """Test 4: ChatResult hat alle Pflichtfelder."""
        self.mock_rag_pipeline.query.return_value = {
            "antwort": "Antwort",
            "quellen": [],
            "modell": "mistral-7b-lokal",
            "vertraulich": True,
        }

        result = self.handler.answer("Frage?", Modus.WISSENSBASIS, vertraulich=True)

        self.assertIsInstance(result, ChatResult)
        self.assertIn("antwort", result.__dict__)
        self.assertIn("rag_quellen", result.__dict__)
        self.assertIn("web_quellen", result.__dict__)
        self.assertIn("modell", result.__dict__)
        self.assertIn("modus", result.__dict__)
        self.assertIn("vertraulich", result.__dict__)
        self.assertIn("dauer_sekunden", result.__dict__)
        self.assertIn("verification", result.__dict__)
        self.assertIn("confidence", result.verification)

    def test_dauer_sekunden(self):
        """Test 5: dauer_sekunden > 0."""
        self.mock_rag_pipeline.query.return_value = {
            "antwort": "Antwort",
            "quellen": [],
            "modell": "mistral-7b-lokal",
            "vertraulich": True,
        }

        result = self.handler.answer("Frage?", Modus.WISSENSBASIS, vertraulich=True)

        self.assertGreater(result.dauer_sekunden, 0)

    def test_verification_detects_conflict_in_beides_modus(self):
        """Test 6: SourceVerifier erkennt Widersprüche zwischen internen und Web-Quellen."""
        self.mock_rag_pipeline.query.return_value = {
            "antwort": "Interner Termin: 12.06.2026",
            "quellen": [{"text": "Der Termin ist am 12.06.2026.", "quelle": "vertrag.pdf", "seite": 1}],
            "modell": "mistral-7b-lokal",
            "vertraulich": True,
        }
        self.mock_web_search.search_and_answer.return_value = Mock(
            antwort="Web-Termin: 18.06.2026",
            quellen=[{"titel": "Webseite", "inhalt": "Der Termin wurde auf 18.06.2026 verschoben."}],
            modell="mistral-large-2512",
            treffer=1,
        )
        self.mock_model_router.generate.return_value = "Die Quellen nennen unterschiedliche Termine."

        result = self.handler.answer("Wann ist der Termin?", Modus.BEIDES, vertraulich=True)

        self.assertEqual(result.verification["verdict"], "widerspruch_gefunden")
        self.assertTrue(result.verification["needs_human_review"])

    def test_identity_question_uses_argus_profile(self):
        """Test 7: Identitätsfragen werden aus dem Systemprofil beantwortet."""
        result = self.handler.answer("Wer bist du?", Modus.WISSENSBASIS, vertraulich=False)

        self.mock_rag_pipeline.query.assert_not_called()
        self.mock_web_search.search_and_answer.assert_not_called()
        self.assertEqual(result.modus, "systemprofil")
        self.assertEqual(result.modell, "argus-profile")
        self.assertIn("Argus RAG", result.antwort)
        self.assertIn("Recherche-, Dokumenten- und Prüfagent", result.antwort)


if __name__ == "__main__":
    unittest.main()
