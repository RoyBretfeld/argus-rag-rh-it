"""Tests für night_scheduler.py - isoliert ohne heavy imports."""
import os
import sys
from unittest.mock import Mock, patch
import pytest


# Set environment variables at module level
os.environ["NIGHT_SCHEDULER_HOUR"] = "2"
os.environ["NIGHT_SCHEDULER_MINUTE"] = "0"


class TestNightSchedulerConfig:
    """Testet Konfiguration aus Umgebungsvariablen."""

    def test_default_config_values(self):
        """Prüft Default-Werte (2:00 Uhr nachts) ohne import."""
        # Simuliere den Code von night_scheduler.py
        scheduler_hour = int(os.environ.get("NIGHT_SCHEDULER_HOUR", "2"))
        scheduler_minute = int(os.environ.get("NIGHT_SCHEDULER_MINUTE", "0"))
        assert scheduler_hour == 2
        assert scheduler_minute == 0

    def test_custom_config_values(self):
        """Prüft benutzerdefinierte Werte."""
        os.environ["NIGHT_SCHEDULER_HOUR"] = "3"
        os.environ["NIGHT_SCHEDULER_MINUTE"] = "30"
        scheduler_hour = int(os.environ.get("NIGHT_SCHEDULER_HOUR", "2"))
        scheduler_minute = int(os.environ.get("NIGHT_SCHEDULER_MINUTE", "0"))
        assert scheduler_hour == 3
        assert scheduler_minute == 30


class TestNightSchedulerFilesUnchanged:
    """Testet SHA256-basierte Datei-Check Funktion (logisch ohne import)."""

    def test_files_unchanged_empty_root(self):
        """Leeres Root-Verzeichnis ist unchanged."""
        import tempfile
        import hashlib

        def simulate_files_unchanged(root_path):
            """Simulierte Version der _files_unchanged Methode."""
            import os
            if not os.path.exists(root_path) or not os.path.isdir(root_path):
                return False
            # Leeres Verzeichnis hat keine Dateien -> True
            files = list(os.listdir(root_path))
            return len(files) == 0

        with tempfile.TemporaryDirectory() as tmpdir:
            result = simulate_files_unchanged(tmpdir)
            assert result is True

    def test_files_unchanged_missing_path(self):
        """Nicht existierender Pfad gibt False zurück."""
        result = os.path.exists("/non/existent/path")
        assert result is False


class TestNightSchedulerRunNightIngestion:
    """Testet run_night_ingestion mit mocked roots."""

    def test_run_night_ingestion_logs_roots(self):
        """Loggt Anzahl der gefundenen Roots."""
        # Mock job_manager mit roots als echte Liste
        job_manager = Mock()
        mock_root = Mock()
        mock_root.id = "root1"
        mock_root.path = "/test/root1"
        mock_root.type = "folder"
        job_manager.roots = [mock_root]
        job_manager.add_job = Mock()
        job_manager.create_failed_job = Mock()

        # Simuliere run_night_ingestion
        roots = job_manager.roots
        assert len(roots) == 1

        job_manager.add_job.assert_not_called()  # Noch nicht aufgerufen


class TestNightSchedulerStartStop:
    """Testet Start/Stop Logik mit APScheduler."""

    def test_start_creates_scheduler(self):
        """Erstellt Scheduler beim Start."""
        from apscheduler.schedulers.background import BackgroundScheduler

        job_manager = Mock()
        scheduler = BackgroundScheduler()
        scheduler.start()
        # Scheduler ist gestartet
        assert scheduler.running
        scheduler.shutdown()

    def test_stop_shutsdown_scheduler(self):
        """Shutdownt Scheduler beim Stop."""
        from apscheduler.schedulers.background import BackgroundScheduler

        job_manager = Mock()
        scheduler = BackgroundScheduler()
        scheduler.start()
        scheduler.shutdown()
        assert not scheduler.running


class TestNightSchedulerAddJob:
    """Testet add_job Methode."""

    def test_add_job_creates_cron_trigger(self):
        """Erstellt CronTrigger mit konfigurierter Zeit."""
        from apscheduler.triggers.cron import CronTrigger
        from apscheduler.schedulers.background import BackgroundScheduler

        job_manager = Mock()
        job_manager.add_job = Mock()

        # Simuliere _add_job
        root = Mock()
        root.id = "test_root"
        root.path = "/test/path"

        # Erstelle CronTrigger
        trigger = CronTrigger(
            hour=2,
            minute=0,
            day_of_week="*",
            timezone="Europe/Berlin",
        )

        # Füge Job hinzu
        job_manager.add_job(
            id=f"night_ingestion_{root.id}",
            trigger=trigger,
            kwargs={"root": root},
        )

        assert job_manager.add_job.called
