"""Night Scheduler - Automatische Nacht-Ingestion für NSI RAG-System.

Nutzt APScheduler BackgroundScheduler mit CronTrigger für tägliche Jobs
und implementiert SHA256-Duplikat-Check zur Überspringung unveränderter Roots.

Enthält auch Status-Mail-Jobs um 10:00 und 16:00 Uhr.
"""

from __future__ import annotations

import hashlib
import os
from datetime import datetime
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

import structlog

from api.ingestion_jobs import IngestionJobManager
from api.mail_reporter import MailReporter

logger = structlog.get_logger(__name__)


def _get_sha256(filepath: Path) -> str:
    """Berechnet SHA256 einer Datei."""
    sha256 = hashlib.sha256()
    try:
        with filepath.open("rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        return sha256.hexdigest()
    except Exception:
        return ""


class NightScheduler:
    """Scheduler für automatische Nacht-Ingestion."""

    def __init__(self, job_manager: IngestionJobManager):
        self.job_manager = job_manager
        self.scheduler: BackgroundScheduler | None = None

    def _get_config(self) -> tuple[int, int]:
        """Liest Konfiguration aus Umgebungsvariablen mit Defaults."""
        hour = int(os.environ.get("NIGHT_SCHEDULER_HOUR", "2"))
        minute = int(os.environ.get("NIGHT_SCHEDULER_MINUTE", "0"))
        return hour, minute

    def _get_status_mail_times(self) -> list[tuple[int, int]]:
        """Liest Status-Mail-Zeiten aus Umgebung (Default: 10:00, 16:00)."""
        times_str = os.environ.get("STATUS_MAIL_TIMES", "10:00,16:00")
        times = []
        for time_str in times_str.split(","):
            time_str = time_str.strip()
            if not time_str:
                continue
            try:
                hour, minute = map(int, time_str.split(":"))
                times.append((hour, minute))
            except ValueError:
                logger.warning(
                    "night_scheduler.invalid_mail_time",
                    time=time_str,
                    reason="Format error, should be HH:MM",
                )
        return times

    def _files_unchanged(self, root_id: str, root_path: str) -> bool:
        """Prüft ob alle Dateien im Root denselben SHA256 haben wie beim letzten Job."""
        try:
            path = Path(root_path)
            if not path.exists() or not path.is_dir():
                return False

            # Hole den letzten erfolgreichen Job für diesen Root
            with self.job_manager._connect() as conn:
                row = conn.execute(
                    """
                    SELECT id FROM ingestion_jobs
                    WHERE root_id=? AND status='completed'
                    ORDER BY completed_at DESC LIMIT 1
                    """,
                    (root_id,),
                ).fetchone()
                if not row:
                    return False
                last_job_id = row["id"]

                # Hole alle Dateien und deren SHA256 aus dem letzten Job
                files_in_job = conn.execute(
                    "SELECT relative_path, source_sha256 FROM ingestion_job_files WHERE job_id=?",
                    (last_job_id,),
                ).fetchall()

                if not files_in_job:
                    return False

                # Prüfe jede Datei
                for rel_path, expected_sha in files_in_job:
                    current_path = path / rel_path.replace("/", "\\")
                    if not current_path.exists():
                        return False
                    current_sha = _get_sha256(current_path)
                    if current_sha != expected_sha:
                        return False
                return True
        except Exception:
            return False

    def run_night_ingestion(self) -> None:
        """Haupt-Logik: Liest Roots, prüft auf Änderungen, legt Jobs an."""
        logger.info("night_scheduler.started", action="starting_night_ingestion")
        hour, minute = self._get_config()

        roots = self.job_manager.list_roots()
        logger.info("night_scheduler.found_roots", count=len(roots))

        for root in roots:
            root_id = root["id"]
            root_path = root["path"]
            available = root.get("available", True)

            if not available:
                # Root nicht erreichbar → failed Job anlegen
                logger.info("night_scheduler.root_skipped_unavailable", root_id=root_id)
                self._create_failed_job(root_id, "NAS-Root nicht erreichbar beim Nachtjob")
                continue

            # Prüfe ob Dateien unverändert sind (SHA256-Duplikat-Check)
            if self._files_unchanged(root_id, root_path):
                logger.info("night_scheduler.skipped_unchanged", root_id=root_id)
                continue

            # Neuen Job erstellen
            try:
                self.job_manager.create_job(root_id=root_id)
                logger.info("night_scheduler.job_created", root_id=root_id)
            except Exception as exc:
                logger.error("night_scheduler.job_failed", root_id=root_id, fehler=str(exc))

        logger.info("night_scheduler.completed", hour=hour, minute=minute)

    def _create_failed_job(self, root_id: str, error_message: str) -> None:
        """Erstellt einen direkt failed Job in der DB."""
        job_id = datetime.now().strftime("night_%Y%m%d_%H%M%S") + "_" + root_id
        now = datetime.now().isoformat()
        with self.job_manager._connect() as conn:
            conn.execute(
                """
                INSERT INTO ingestion_jobs (
                    id, root_id, relative_path, category, confidential, status,
                    total_files, created_at, updated_at, last_error
                ) VALUES (?, ?, ?, ?, ?, 'failed', ?, ?, ?, ?)
                """,
                (job_id, root_id, "", "dokumente", 1, 0, now, now, error_message),
            )

    def start(self) -> None:
        """Startet den Scheduler."""
        hour, minute = self._get_config()
        mail_times = self._get_status_mail_times()

        if self.scheduler:
            return

        self.scheduler = BackgroundScheduler()

        # Night-Ingestion Job
        trigger = CronTrigger(hour=hour, minute=minute)
        self.scheduler.add_job(
            self.run_night_ingestion,
            trigger=trigger,
            id="night_ingestion",
            replace_existing=True,
        )
        logger.info(
            "night_scheduler.job_added",
            job_id="night_ingestion",
            trigger=f"cron {hour}:{minute}",
        )

        # Status-Mail Jobs
        for mail_hour, mail_minute in mail_times:
            job_id = f"status_mail_{mail_hour}_{mail_minute}"
            mail_trigger = CronTrigger(hour=mail_hour, minute=mail_minute)
            self.scheduler.add_job(
                self._send_status_mail,
                trigger=mail_trigger,
                id=job_id,
                replace_existing=True,
            )
            logger.info(
                "night_scheduler.job_added",
                job_id=job_id,
                trigger=f"cron {mail_hour}:{mail_minute}",
            )

        self.scheduler.start()
        logger.info("night_scheduler.started", hour=hour, minute=minute)

    def _send_status_mail(self) -> None:
        """Sendet Status-Mail - wrapper für MailReporter."""
        try:
            reporter = MailReporter()
            reporter.send_status_report()
            logger.info("night_scheduler.mail_sent")
        except Exception as exc:
            logger.error("night_scheduler.mail_error", fehler=str(exc))

    def stop(self) -> None:
        """Stoppt den Scheduler."""
        if self.scheduler:
            self.scheduler.shutdown(wait=False)
            self.scheduler = None
        logger.info("night_scheduler.stopped")


# Singleton-Instanz
_scheduler: NightScheduler | None = None


def get_scheduler(job_manager: IngestionJobManager | None = None) -> NightScheduler:
    """Holt oder initialisiert die Singleton-Instanz."""
    global _scheduler
    if _scheduler is None:
        if job_manager is None:
            raise ValueError("job_manager ist required für Initialisierung")
        _scheduler = NightScheduler(job_manager)
    elif job_manager is not None and _scheduler.job_manager != job_manager:
        _scheduler = NightScheduler(job_manager)
    return _scheduler


def start_scheduler(job_manager: IngestionJobManager | None = None) -> NightScheduler:
    """Startet den Scheduler."""
    scheduler = get_scheduler(job_manager)
    scheduler.start()
    return scheduler


def stop_scheduler() -> None:
    """Stoppt den Scheduler."""
    global _scheduler
    if _scheduler:
        _scheduler.stop()
        _scheduler = None
