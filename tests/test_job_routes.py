import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from api.main import app


class TestJobRoutes(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    @patch("api.routes.jobs.job_manager")
    def test_list_roots(self, mock_manager):
        mock_manager.list_roots.return_value = [{
            "id": "wissen",
            "path": r"Z:\Wissen",
            "available": True,
            "read_only": True,
        }]
        response = self.client.get("/api/jobs/roots")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["roots"][0]["read_only"])

    @patch("api.routes.jobs.job_manager")
    def test_create_job(self, mock_manager):
        mock_manager.create_job.return_value = {
            "id": "job-1",
            "status": "queued",
            "total_files": 8000,
        }
        response = self.client.post(
            "/api/jobs",
            json={
                "root_id": "wissen",
                "relative_path": "01_Kunden",
                "category": "dokumente",
                "confidential": True,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["total_files"], 8000)
        mock_manager.create_job.assert_called_once_with(
            root_id="wissen",
            relative_path="01_Kunden",
            category="dokumente",
            confidential=True,
        )

    @patch("api.routes.jobs.job_manager")
    def test_create_job_rejects_unsafe_path(self, mock_manager):
        mock_manager.create_job.side_effect = ValueError(
            "Der angeforderte Ordner liegt außerhalb der Freigabe."
        )
        response = self.client.post(
            "/api/jobs",
            json={"root_id": "wissen", "relative_path": "../privat"},
        )
        self.assertEqual(response.status_code, 400)

    @patch("api.routes.jobs.job_manager")
    def test_pause_resume_and_cancel(self, mock_manager):
        mock_manager.pause_job.return_value = {"id": "job-1", "status": "paused"}
        mock_manager.resume_job.return_value = {"id": "job-1", "status": "queued"}
        mock_manager.cancel_job.return_value = {"id": "job-1", "status": "cancelled"}

        self.assertEqual(
            self.client.post("/api/jobs/job-1/pause").json()["status"],
            "paused",
        )
        self.assertEqual(
            self.client.post("/api/jobs/job-1/resume").json()["status"],
            "queued",
        )
        self.assertEqual(
            self.client.post("/api/jobs/job-1/cancel").json()["status"],
            "cancelled",
        )


if __name__ == "__main__":
    unittest.main()
