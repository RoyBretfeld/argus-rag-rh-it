import sqlite3
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from api.ingestion_jobs import IngestionJobManager, parse_allowed_roots


class TestIngestionJobs(unittest.TestCase):
    def setUp(self):
        self.temp_dir = TemporaryDirectory()
        self.root = Path(self.temp_dir.name) / "wissen"
        self.root.mkdir()
        self.db_path = Path(self.temp_dir.name) / "jobs.sqlite3"

    def tearDown(self):
        self.temp_dir.cleanup()

    def create_manager(self):
        return IngestionJobManager(
            db_path=self.db_path,
            allowed_roots={"wissen": self.root},
            poll_interval=0.02,
        )

    def test_parse_allowed_roots(self):
        roots = parse_allowed_roots(f"wissen={self.root};projekte={self.root}")
        self.assertEqual(roots["wissen"], self.root.resolve())
        self.assertEqual(roots["projekte"], self.root.resolve())

    def test_job_inventory_uses_natural_path_order(self):
        for relative_path in ("10_Ende.txt", "2_Mitte.txt", "01_Start.txt"):
            (self.root / relative_path).write_text(relative_path, encoding="utf-8")

        manager = self.create_manager()
        job = manager.create_job("wissen")

        with manager._connect() as connection:
            paths = [
                row["relative_path"]
                for row in connection.execute(
                    "SELECT relative_path FROM ingestion_job_files WHERE job_id=? ORDER BY position",
                    (job["id"],),
                )
            ]
        self.assertEqual(paths, ["01_Start.txt", "2_Mitte.txt", "10_Ende.txt"])

    def test_path_traversal_is_rejected(self):
        manager = self.create_manager()
        with self.assertRaisesRegex(ValueError, "außerhalb"):
            manager.create_job("wissen", "../")

    def test_running_job_is_requeued_after_restart(self):
        manager = self.create_manager()
        (self.root / "Dokument.txt").write_text("Inhalt", encoding="utf-8")
        job = manager.create_job("wissen")
        with manager._connect() as connection:
            connection.execute(
                "UPDATE ingestion_jobs SET status='running' WHERE id=?",
                (job["id"],),
            )
            connection.execute(
                "UPDATE ingestion_job_files SET status='running' WHERE job_id=?",
                (job["id"],),
            )

        restarted_manager = self.create_manager()
        self.assertEqual(restarted_manager.get_job(job["id"])["status"], "queued")
        with restarted_manager._connect() as connection:
            file_status = connection.execute(
                "SELECT status FROM ingestion_job_files WHERE job_id=?",
                (job["id"],),
            ).fetchone()["status"]
        self.assertEqual(file_status, "pending")

    @patch("api.ingestion_jobs.UploadHandler")
    def test_worker_processes_files_sequentially_from_temp_copies(self, mock_handler_class):
        (self.root / "01.txt").write_text("eins", encoding="utf-8")
        (self.root / "02.txt").write_text("zwei", encoding="utf-8")
        calls = []

        def process(temp_path, _category, _confidential, **kwargs):
            calls.append((Path(temp_path), kwargs["source_path"], Path(temp_path).read_text()))
            return Mock(fehler=None, chunks_erstellt=2)

        mock_handler_class.return_value.process_upload.side_effect = process
        manager = self.create_manager()
        job = manager.create_job("wissen")
        manager.start()
        try:
            deadline = time.time() + 5
            while time.time() < deadline:
                current = manager.get_job(job["id"])
                if current["status"] == "completed":
                    break
                time.sleep(0.03)
        finally:
            manager.stop()

        current = manager.get_job(job["id"])
        self.assertEqual(current["status"], "completed")
        self.assertEqual(current["processed_files"], 2)
        self.assertEqual(current["total_chunks"], 4)
        self.assertEqual([call[1] for call in calls], ["01.txt", "02.txt"])
        self.assertEqual([call[2] for call in calls], ["eins", "zwei"])
        self.assertTrue(all(call[0] != self.root / call[1] for call in calls))
        self.assertEqual((self.root / "01.txt").read_text(), "eins")
        self.assertEqual((self.root / "02.txt").read_text(), "zwei")

    def test_pause_and_resume_are_persistent(self):
        (self.root / "Dokument.txt").write_text("Inhalt", encoding="utf-8")
        manager = self.create_manager()
        job = manager.create_job("wissen")
        paused = manager.pause_job(job["id"])
        self.assertEqual(paused["status"], "paused")
        resumed = manager.resume_job(job["id"])
        self.assertEqual(resumed["status"], "queued")


if __name__ == "__main__":
    unittest.main()
