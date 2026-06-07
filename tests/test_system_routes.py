# Tests für System- & Hardware-API-Routen

import unittest
from unittest.mock import Mock, patch
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi.testclient import TestClient
from api.main import app

class TestSystemRoutes(unittest.TestCase):
    """Tests für die System- & Hardware-API-Routen."""

    def setUp(self):
        self.client = TestClient(app)

    @patch("api.routes.system.chroma_store")
    @patch("api.routes.system.get_gpu_info")
    @patch("api.routes.system.get_system_ram")
    def test_get_stats(self, mock_ram, mock_gpu, mock_chroma):
        """Testet den GET /api/system/stats Endpunkt."""
        # Da chroma_store im Route-Modul eventuell None ist (wenn ChromaDB-Init fehlschlägt),
        # mocken wir das gesamte chroma_store Objekt in system.py.
        # Aber da mock_chroma bereits ein Mock ist, simulieren wir die stats Rückgabe:
        if mock_chroma:
            mock_chroma.collection_stats.return_value = {"nsi_local": 10, "nsi_cloud": 5}
            
        mock_gpu.return_value = {
            "available": True,
            "name": "NVIDIA GeForce RTX 4080",
            "total_vram_mb": 16384.0,
            "used_vram_mb": 4096.0,
            "free_vram_mb": 12288.0,
            "method": "pytorch"
        }
        mock_ram.return_value = {
            "total_gb": 32.0,
            "used_gb": 12.0,
            "available_gb": 20.0,
            "percent": 37.5
        }

        response = self.client.get("/api/system/stats")
        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertIn("database", data)
        if mock_chroma:
            self.assertEqual(data["database"]["nsi_local"], 10)
            self.assertEqual(data["database"]["nsi_cloud"], 5)
        self.assertEqual(data["gpu"]["name"], "NVIDIA GeForce RTX 4080")
        self.assertEqual(data["ram"]["percent"], 37.5)

    @patch("api.routes.system.chroma_store")
    def test_reset_database(self, mock_chroma):
        """Testet den POST /api/system/reset Endpunkt."""
        response = self.client.post("/api/system/reset")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")
        if mock_chroma:
            mock_chroma.reset.assert_called_once()

if __name__ == "__main__":
    unittest.main()
