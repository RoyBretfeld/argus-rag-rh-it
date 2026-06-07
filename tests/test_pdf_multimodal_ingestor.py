# Tests für PDFMultimodalIngestor

import unittest
from unittest.mock import Mock, patch, MagicMock
from io import BytesIO
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.ingestor.pdf_multimodal_ingestor import PDFMultimodalIngestor


class MockPixmap:
    """Mock für ein fitz Pixmap-Objekt."""
    def __init__(self):
        self.width = 100
        self.height = 100
        self.samples = b"\x00" * 30000  # 100 * 100 * 3 Bytes RGB


class MockPDFPage:
    """Mock für eine PDF-Seite."""
    def __init__(self, number: int):
        self.number = number
        self.text_content = f"Text auf Seite {number + 1}"

    def get_text(self, fmt: str):
        return self.text_content

    def get_pixmap(self, matrix=None, alpha=False):
        return MockPixmap()

    def get_images(self, full: bool = False):
        return []


class MockPDFDoc:
    """Mock für ein PDF-Dokument."""
    def __init__(self):
        self.pages = [MockPDFPage(0), MockPDFPage(1)]

    def __len__(self):
        return len(self.pages)

    def __getitem__(self, index):
        return self.pages[index]

    def close(self):
        pass


class TestPDFMultimodalIngestor(unittest.TestCase):
    """Tests für PDFMultimodalIngestor."""

    def setUp(self):
        """Vorbereitung für Tests."""
        self.ingestor = PDFMultimodalIngestor(vertraulich=True)
        self.test_pdf = Path("/tmp/test.pdf")

    @patch("core.llm.model_router.ModelRouter.generate_vision")
    @patch("fitz.open")
    def test_vision_extraction(self, mock_open, mock_generate_vision):
        """Test 1: PDF mit erfolgreicher Vision-Analyse → Chunks vom Typ 'pdf_seite'."""
        mock_open.return_value = MockPDFDoc()
        mock_generate_vision.return_value = "Strukturierte Vision Beschreibung"

        result = self.ingestor.ingest(self.test_pdf)
        self.assertGreater(len(result), 0)
        self.assertTrue(all(c["typ"] == "pdf_seite" for c in result))
        self.assertTrue(all("Strukturierte Vision Beschreibung" in c["text"] for c in result))

    @patch("fitz.open")
    def test_fallback_on_vision_error(self, mock_open):
        """Test 2: Vision-LLM schlägt fehl → Fallback auf Plain-Text-Extraktion."""
        mock_open.return_value = MockPDFDoc()
        
        # Wir provozieren eine Exception beim Rendern, um den globalen Fallback-Pfad der Seite zu triggern
        with patch.object(self.ingestor, "_render_page_as_image", side_effect=Exception("Render error")):
            result = self.ingestor.ingest(self.test_pdf)
            self.assertGreater(len(result), 0)
            self.assertTrue(any("Text auf Seite 1" in c["text"] for c in result))
            self.assertTrue(any("[Fallback-Text-Extraktion]" in c["text"] for c in result))

    @patch("core.llm.model_router.ModelRouter.generate_vision")
    @patch("fitz.open")
    def test_metadata_present(self, mock_open, mock_generate_vision):
        """Test 3: Metadaten vorhanden (seite, quelle, typ)."""
        mock_open.return_value = MockPDFDoc()
        mock_generate_vision.return_value = "Testbeschreibung"

        result = self.ingestor.ingest(self.test_pdf)
        for chunk in result:
            self.assertIn("seite", chunk)
            self.assertIn("quelle", chunk)
            self.assertIn("typ", chunk)

    @patch("core.llm.model_router.ModelRouter.generate_vision")
    @patch("fitz.open")
    def test_multiple_pages(self, mock_open, mock_generate_vision):
        """Test 4: Mehrere Seiten werden verarbeitet."""
        mock_open.return_value = MockPDFDoc()
        mock_generate_vision.return_value = "Testbeschreibung"

        result = self.ingestor.ingest(self.test_pdf)
        # 2 Chunks (einer pro Seite)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["seite"], 1)
        self.assertEqual(result[1]["seite"], 2)


if __name__ == "__main__":
    unittest.main()
