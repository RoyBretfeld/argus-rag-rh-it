"""IdleWatcher - Erkennung von System-Idle-Zustand für Ingestion-Steuerung.

Nutzt Windows ctypes-API GetLastInputInfo um die letzte Eingabe-Zeit zu ermitteln.
Beendet Ingestion-Jobs bei Nutzeraktivität und startet nach Idle-Zeit neu.
"""

from __future__ import annotations

import os
import threading
import time
from typing import Any

import ctypes
import structlog

logger = structlog.get_logger(__name__)


def get_idle_seconds() -> float:
    """Ermittelt die aktuelle Idle-Zeit in Sekunden (nur Windows)."""
    try:
        user32 = ctypes.windll.user32
        last_input_info = ctypes.c_uint()
        struct_size = ctypes.sizeof(ctypes.c_uint)

        if user32.GetLastInputInfo(ctypes.byref(last_input_info), struct_size):
            tick_count = user32.GetTickCount()
            # GetTickCount gibt ms zurück, GetLastInputInfo auch ms
            # Differenz ist die Idle-Zeit in ms
            idle_ms = tick_count - last_input_info.value
            return idle_ms / 1000.0
    except Exception:
        pass
    return 0


# Importiere IngestionJobManager erst bei Bedarf (nach dem Import)
_job_manager: Any = None


def _get_job_manager() -> Any:
    """Lazy Import von IngestionJobManager."""
    global _job_manager
    if _job_manager is None:
        from api.ingestion_jobs import IngestionJobManager
        _job_manager = IngestionJobManager()
    return _job_manager


class IdleWatcher:
    """Watcher für System-Idle-Zustand."""

    def __init__(self, job_manager: Any | None = None):
        self.job_manager = job_manager or _get_job_manager()
        self._thread: threading.Thread | None = None
        self._running = False
        self._idle_threshold_minutes = self._get_idle_threshold_minutes()
        self._check_interval_seconds = self._get_check_interval_seconds()
        self._last_state: str | None = None  # "idle" oder "active"

    def _get_idle_threshold_minutes(self) -> int:
        """Liest Idle-Schwellwert aus Umgebung (Default: 15 Minuten)."""
        return int(os.environ.get("IDLE_THRESHOLD_MINUTES", "15"))

    def _get_check_interval_seconds(self) -> int:
        """Liest Prüfintervall aus Umgebung (Default: 60 Sekunden)."""
        return int(os.environ.get("IDLE_CHECK_INTERVAL_SECONDS", "60"))

    def _is_system_idle(self) -> bool:
        """Prüft ob das System im Idle-Zustand ist."""
        idle_seconds = get_idle_seconds()
        idle_threshold_seconds = self._idle_threshold_minutes * 60
        return idle_seconds >= idle_threshold_seconds

    def _get_paused_jobs_by_idle(self) -> list[dict[str, Any]]:
        """Holt alle Jobs die vom IdleWatcher pausiert wurden."""
        with self.job_manager._connect() as conn:
            rows = conn.execute(
                "SELECT id FROM ingestion_jobs WHERE last_error LIKE ?",
                ("%IdleWatcher: Nutzer aktiv%",),
            ).fetchall()
        return [dict(row) for row in rows]

    def _get_running_jobs(self) -> list[dict[str, Any]]:
        """Holt alle laufenden Jobs."""
        with self.job_manager._connect() as conn:
            rows = conn.execute(
                "SELECT id FROM ingestion_jobs WHERE status='running'",
            ).fetchall()
        return [dict(row) for row in rows]

    def _handle_idle(self) -> None:
        """Wird aufgerufen wenn System idle wird."""
        paused_jobs = self._get_paused_jobs_by_idle()
        if paused_jobs:
            # Pausierte Jobs von IdleWatcher fortsetzen
            for job in paused_jobs:
                try:
                    self.job_manager.resume_job(job["id"])
                    logger.info(
                        "idle_watcher.jobs_resumed",
                        job_id=job["id"],
                        reason="IdleWatcher: Nutzer aktiv",
                    )
                except Exception as exc:
                    logger.error(
                        "idle_watcher.resume_failed",
                        job_id=job["id"],
                        fehler=str(exc),
                    )
        else:
            # Keine pausierten Jobs -> Night-Ingestion direkt starten
            logger.info("idle_watcher.ingest_triggered", reason="idle_threshold_reached")
            from api.night_scheduler import _scheduler
            if _scheduler and hasattr(_scheduler, 'run_night_ingestion'):
                _scheduler.run_night_ingestion()

    def _handle_active(self) -> None:
        """Wird aufgerufen wenn Nutzer zurückkehrt (System aktiv)."""
        running_jobs = self._get_running_jobs()
        if running_jobs:
            for job in running_jobs:
                try:
                    self.job_manager.pause_job(job["id"])
                    logger.info(
                        "idle_watcher.jobs_paused",
                        job_id=job["id"],
                        reason="IdleWatcher: Nutzer aktiv",
                    )
                except Exception as exc:
                    logger.error(
                        "idle_watcher.pause_failed",
                        job_id=job["id"],
                        fehler=str(exc),
                    )

    def _worker(self) -> None:
        """Worker-Thread für den Idle-Checker."""
        logger.info("idle_watcher.started", interval_seconds=self._check_interval_seconds)
        while self._running:
            try:
                is_idle = self._is_system_idle()
                current_state = "idle" if is_idle else "active"

                if current_state != self._last_state:
                    if is_idle:
                        self._handle_idle()
                    else:
                        self._handle_active()
                    self._last_state = current_state

                if is_idle:
                    logger.info("idle_watcher.system_idle", idle_seconds=round(get_idle_seconds(), 2))
                else:
                    logger.info("idle_watcher.user_returned", idle_seconds=round(get_idle_seconds(), 2))

            except Exception as exc:
                logger.error("idle_watcher.worker_error", fehler=str(exc))

            time.sleep(self._check_interval_seconds)

    def start(self) -> None:
        """Startet den Idle-Watcher."""
        if self._thread and self._thread.is_alive():
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._worker,
            name="argus-idle-watcher",
            daemon=True,
        )
        self._thread.start()
        logger.info("idle_watcher.started", interval_seconds=self._check_interval_seconds)

    def stop(self) -> None:
        """Stoppt den Idle-Watcher."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None
        logger.info("idle_watcher.stopped")


# Singleton-Instanz
_idle_watcher: IdleWatcher | None = None


def get_idle_watcher(job_manager: Any | None = None) -> IdleWatcher:
    """Holt oder initialisiert die Singleton-Instanz."""
    global _idle_watcher
    if _idle_watcher is None:
        _idle_watcher = IdleWatcher(job_manager)
    elif job_manager is not None:
        _idle_watcher.job_manager = job_manager
    return _idle_watcher


def start_idle_watcher(job_manager: Any | None = None) -> IdleWatcher:
    """Startet den Idle-Watcher."""
    watcher = get_idle_watcher(job_manager)
    watcher.start()
    return watcher


def stop_idle_watcher() -> None:
    """Stoppt den Idle-Watcher."""
    global _idle_watcher
    if _idle_watcher:
        _idle_watcher.stop()
        _idle_watcher = None
