# Tests für SourceVerifier

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.reasoning.source_verifier import SourceVerifier


class TestSourceVerifier(unittest.TestCase):
    """Tests für Quellenbewertung und Konflikterkennung."""

    def setUp(self):
        self.verifier = SourceVerifier()

    def test_high_confidence_with_consistent_internal_and_web_sources(self):
        result = self.verifier.verify(
            frage="Wann ist der Termin?",
            antwort="Der Termin ist am 12.06.2026.",
            rag_quellen=[
                {
                    "text": "Der Termin findet am 12.06.2026 statt.",
                    "quelle": "vertrag.pdf",
                    "seite": 1,
                    "score": 0.91,
                }
            ],
            web_quellen=[
                {
                    "titel": "Projektseite",
                    "url": "https://example.com",
                    "inhalt": "Aktueller Termin: 12.06.2026.",
                }
            ],
        )

        self.assertEqual(result["verdict"], "sicher")
        self.assertFalse(result["needs_human_review"])
        self.assertEqual(result["source_counts"]["internal"], 1)
        self.assertEqual(result["source_counts"]["web"], 1)

    def test_detects_date_conflict_between_sources(self):
        result = self.verifier.verify(
            frage="Wann ist der Termin?",
            antwort="Der Termin ist unklar.",
            rag_quellen=[
                {"text": "Der Termin ist am 12.06.2026.", "quelle": "vertrag.pdf", "seite": 1}
            ],
            web_quellen=[
                {"titel": "Webseite", "inhalt": "Der Termin wurde auf 18.06.2026 verschoben."}
            ],
        )

        self.assertEqual(result["verdict"], "widerspruch_gefunden")
        self.assertTrue(result["needs_human_review"])
        self.assertGreaterEqual(len(result["conflicts"]), 1)

    def test_no_sources_has_low_confidence(self):
        result = self.verifier.verify(
            frage="Was steht im Dokument?",
            antwort="Keine relevanten Dokumente gefunden.",
            rag_quellen=[],
            web_quellen=[],
        )

        self.assertEqual(result["confidence_label"], "niedrig")
        self.assertTrue(result["needs_human_review"])

    def test_system_profile_answer_is_high_confidence(self):
        result = self.verifier.verify(
            frage="Wer bist du?",
            antwort="Ich bin Argus RAG.",
            rag_quellen=[
                {
                    "text": "Du bist Argus RAG.",
                    "quelle": "argus_profile",
                    "seite": 0,
                    "typ": "system_identity",
                    "score": 1.0,
                }
            ],
            web_quellen=[],
        )

        self.assertEqual(result["verdict"], "sicher")
        self.assertEqual(result["confidence"], 0.95)
        self.assertFalse(result["needs_human_review"])


if __name__ == "__main__":
    unittest.main()
