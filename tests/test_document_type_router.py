# Tests für DocumentTypeRouter

import unittest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.ingestor.document_type_router import route, IngestResult


class TestDocumentTypeRouter(unittest.TestCase):
    """Tests für DocumentTypeRouter."""

    def setUp(self):
        """Vorbereitung für Tests."""
        self.test_file_pdf = Path("/tmp/test.pdf")
        self.test_file_docx = Path("/tmp/test.docx")
        self.test_file_jpg = Path("/tmp/test.jpg")
        self.test_file_csv = Path("/tmp/test.csv")
        self.test_file_exe = Path("/tmp/test.exe")

    @patch("core.ingestor.document_type_router.PDFMultimodalIngestor")
    def test_pdf_routing(self, mock_ingestor):
        """Test 1: PDF → PDFMultimodalIngestor aufgerufen."""
        mock_ingestor.return_value.ingest.return_value = [
            {"text": "Test", "typ": "pdf_seite", "seite": 1}
        ]
        result = route(self.test_file_pdf, vertraulich=True)
        self.assertIsInstance(result, IngestResult)
        self.assertEqual(result.kategorie, "dokumente")

    @patch("core.ingestor.document_type_router.OfficeIngestor")
    def test_docx_routing(self, mock_ingestor):
        """Test 2: DOCX → OfficeIngestor aufgerufen."""
        mock_ingestor.return_value.ingest.return_value = [
            {"text": "Test", "typ": "dokument"}
        ]
        result = route(self.test_file_docx, vertraulich=False)
        self.assertIsInstance(result, IngestResult)

    @patch("core.ingestor.document_type_router.ImageIngestor")
    def test_jpg_routing(self, mock_ingestor):
        """Test 3: JPG → ImageIngestor aufgerufen."""
        mock_ingestor.return_value.ingest.return_value = [
            {"text": "Bild", "typ": "bild"}
        ]
        result = route(self.test_file_jpg, vertraulich=True)
        self.assertEqual(result.kategorie, "bilder")

    @patch("core.ingestor.document_type_router.DataIngestor")
    def test_csv_routing(self, mock_ingestor):
        """Test 4: CSV → DataIngestor aufgerufen."""
        mock_ingestor.return_value.ingest.return_value = [
            {"text": "CSV", "typ": "dokument"}
        ]
        result = route(self.test_file_csv, vertraulich=False)
        self.assertEqual(result.kategorie, "technische_daten")

    def test_unsupported_extension(self):
        """Test 5: .exe → ValueError."""
        with self.assertRaises(ValueError) as context:
            route(self.test_file_exe, vertraulich=True)
        self.assertIn("Nicht unterstützter Dateityp", str(context.exception))

    @patch("core.ingestor.document_type_router.PDFMultimodalIngestor")
    def test_vertraulich_local_collection(self, mock_ingestor):
        """Test 6: vertraulich=True → collection="nsi_local"."""
        mock_ingestor.return_value.ingest.return_value = []
        result = route(self.test_file_pdf, vertraulich=True)
        self.assertEqual(result.collection, "nsi_local")

    @patch("core.ingestor.document_type_router.OfficeIngestor")
    def test_public_cloud_collection(self, mock_ingestor):
        """Test 7: vertraulich=False → collection="nsi_cloud"."""
        mock_ingestor.return_value.ingest.return_value = []
        result = route(self.test_file_docx, vertraulich=False)
        self.assertEqual(result.collection, "nsi_cloud")


if __name__ == "__main__":
    unittest.main()
