import unittest
from pathlib import Path
from tempfile import NamedTemporaryFile
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

from api.main import app
from api.routes.upload import normalize_source_path
from api.upload_handler import UploadHandler


class TestUploadOrdering(unittest.TestCase):
    def test_normalize_source_path_preserves_hierarchy(self):
        result = normalize_source_path(
            r"NAS\01_Kunden\002_Projekt\Dokument.pdf",
            "Dokument.pdf",
        )
        self.assertEqual(result, "NAS/01_Kunden/002_Projekt/Dokument.pdf")

    def test_normalize_source_path_removes_traversal(self):
        result = normalize_source_path(
            "../../NAS/../Vertraulich/Plan.pdf",
            "Plan.pdf",
        )
        self.assertEqual(result, "NAS/Vertraulich/Plan.pdf")

    @patch("api.upload_handler.CHROMA_STORE")
    @patch("api.upload_handler.route")
    def test_handler_persists_path_and_sequence_metadata(self, mock_route, mock_store):
        mock_route.return_value = Mock(
            chunks=[{
                "text": "Inhalt",
                "quelle": "temp.txt",
                "seite": 1,
                "typ": "text",
            }],
            collection="nsi_local",
        )
        mock_store.add_chunks.return_value = 1

        with NamedTemporaryFile(suffix=".txt", delete=False) as temp:
            temp.write(b"Inhalt")
            temp_path = Path(temp.name)

        try:
            result = UploadHandler().process_upload(
                temp_path,
                "dokumente",
                True,
                source_path="01_Kunden/002_Projekt/Plan.txt",
                ingest_order=17,
                total_files=8000,
            )
        finally:
            temp_path.unlink(missing_ok=True)

        self.assertIsNone(result.fehler)
        chunks = mock_store.add_chunks.call_args.args[0]
        self.assertEqual(chunks[0]["quelle"], "01_Kunden/002_Projekt/Plan.txt")
        self.assertEqual(chunks[0]["source_path"], "01_Kunden/002_Projekt/Plan.txt")
        self.assertEqual(chunks[0]["ingest_order"], 17)
        self.assertEqual(chunks[0]["source_chunk_order"], 1)
        self.assertEqual(chunks[0]["total_files"], 8000)

    @patch("api.routes.upload.UploadHandler")
    def test_upload_endpoint_forwards_nas_order(self, mock_handler_class):
        mock_handler = mock_handler_class.return_value
        mock_handler.process_upload.return_value = Mock(
            fehler=None,
            chunks_erstellt=3,
        )

        response = TestClient(app).post(
            "/api/upload",
            files={"files": ("Plan.txt", b"Inhalt", "text/plain")},
            data={
                "kategorie": "dokumente",
                "vertraulich": "true",
                "source_path": r"NAS\01_Kunden\002_Projekt\Plan.txt",
                "ingest_order": "17",
                "total_files": "8000",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["processed_files"],
            ["NAS/01_Kunden/002_Projekt/Plan.txt"],
        )
        call = mock_handler.process_upload.call_args
        self.assertEqual(call.kwargs["source_path"], "NAS/01_Kunden/002_Projekt/Plan.txt")
        self.assertEqual(call.kwargs["ingest_order"], 17)
        self.assertEqual(call.kwargs["total_files"], 8000)


if __name__ == "__main__":
    unittest.main()
