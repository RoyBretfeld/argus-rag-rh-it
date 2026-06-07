from __future__ import annotations

import hashlib
import os
import re
import shutil
import sqlite3
import tempfile
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import structlog

from api.upload_handler import UploadHandler
from core.ingestor.document_type_router import FILE_TYPE_MAP

logger = structlog.get_logger(__name__)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _natural_key(value: str) -> list[object]:
    return [
        int(part) if part.isdigit() else part.casefold()
        for part in re.split(r"(\d+)", value.replace("\\", "/"))
    ]


def parse_allowed_roots(raw_value: str | None = None) -> dict[str, Path]:
    """Parst `name=pfad;name2=pfad2` aus der Umgebung."""
    raw = raw_value if raw_value is not None else os.environ.get("ARGUS_NAS_ROOTS", "")
    roots: dict[str, Path] = {}
    for entry in raw.split(";"):
        entry = entry.strip()
        if not entry or "=" not in entry:
            continue
        name, path_value = entry.split("=", 1)
        safe_name = re.sub(r"[^a-zA-Z0-9_-]", "-", name.strip()).strip("-")
        if safe_name and path_value.strip():
            roots[safe_name] = Path(path_value.strip()).expanduser().resolve()
    return roots


class IngestionJobManager:
    """Persistente, sequenzielle Read-only-Ingestion für freigegebene Ordner."""

    def __init__(
        self,
        db_path: str | Path = "data/ingestion_jobs.sqlite3",
        allowed_roots: dict[str, Path] | None = None,
        poll_interval: float = 0.5,
    ):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.allowed_roots = allowed_roots if allowed_roots is not None else parse_allowed_roots()
        self.poll_interval = poll_interval
        self._stop_event = threading.Event()
        self._wake_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._init_db()

    @contextmanager
    def _connect(self):
        connection = sqlite3.connect(self.db_path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _init_db(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS ingestion_jobs (
                    id TEXT PRIMARY KEY,
                    root_id TEXT NOT NULL,
                    relative_path TEXT NOT NULL,
                    category TEXT NOT NULL,
                    confidential INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    total_files INTEGER NOT NULL DEFAULT 0,
                    processed_files INTEGER NOT NULL DEFAULT 0,
                    failed_files INTEGER NOT NULL DEFAULT 0,
                    total_chunks INTEGER NOT NULL DEFAULT 0,
                    current_file TEXT,
                    last_error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    completed_at TEXT
                );
                CREATE TABLE IF NOT EXISTS ingestion_job_files (
                    job_id TEXT NOT NULL,
                    position INTEGER NOT NULL,
                    relative_path TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    chunks INTEGER NOT NULL DEFAULT 0,
                    source_sha256 TEXT,
                    error TEXT,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (job_id, position),
                    FOREIGN KEY (job_id) REFERENCES ingestion_jobs(id) ON DELETE CASCADE
                );
                """
            )
            connection.execute(
                "UPDATE ingestion_jobs SET status='queued', updated_at=? WHERE status='running'",
                (_utc_now(),),
            )
            connection.execute(
                "UPDATE ingestion_job_files SET status='pending', updated_at=? WHERE status='running'",
                (_utc_now(),),
            )

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._worker_loop,
            name="argus-ingestion-worker",
            daemon=True,
        )
        self._thread.start()
        self._wake_event.set()

    def stop(self, timeout: float = 10.0) -> None:
        self._stop_event.set()
        self._wake_event.set()
        if self._thread:
            self._thread.join(timeout=timeout)

    def list_roots(self) -> list[dict]:
        return [
            {
                "id": root_id,
                "path": str(root),
                "available": root.exists() and root.is_dir(),
                "read_only": True,
            }
            for root_id, root in sorted(self.allowed_roots.items())
        ]

    def create_job(
        self,
        root_id: str,
        relative_path: str = "",
        category: str = "dokumente",
        confidential: bool = True,
    ) -> dict:
        source_dir = self._resolve_source_dir(root_id, relative_path)
        files = self._scan_files(source_dir)
        if not files:
            raise ValueError("Im freigegebenen Ordner wurden keine unterstützten Dateien gefunden.")

        job_id = uuid.uuid4().hex
        now = _utc_now()
        normalized_relative = source_dir.relative_to(self.allowed_roots[root_id]).as_posix()
        if normalized_relative == ".":
            normalized_relative = ""

        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO ingestion_jobs (
                    id, root_id, relative_path, category, confidential, status,
                    total_files, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, 'queued', ?, ?, ?)
                """,
                (
                    job_id,
                    root_id,
                    normalized_relative,
                    category,
                    int(confidential),
                    len(files),
                    now,
                    now,
                ),
            )
            connection.executemany(
                """
                INSERT INTO ingestion_job_files (
                    job_id, position, relative_path, status, updated_at
                ) VALUES (?, ?, ?, 'pending', ?)
                """,
                [
                    (
                        job_id,
                        position,
                        file_path.relative_to(self.allowed_roots[root_id]).as_posix(),
                        now,
                    )
                    for position, file_path in enumerate(files, start=1)
                ],
            )
        self._wake_event.set()
        return self.get_job(job_id)

    def list_jobs(self, limit: int = 20) -> list[dict]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM ingestion_jobs ORDER BY created_at DESC LIMIT ?",
                (max(1, min(limit, 100)),),
            ).fetchall()
        return [self._serialize_job(row) for row in rows]

    def get_job(self, job_id: str) -> dict:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM ingestion_jobs WHERE id=?",
                (job_id,),
            ).fetchone()
        if not row:
            raise KeyError(job_id)
        return self._serialize_job(row)

    def pause_job(self, job_id: str) -> dict:
        self._set_status(job_id, {"queued", "running"}, "paused")
        return self.get_job(job_id)

    def resume_job(self, job_id: str) -> dict:
        self._set_status(job_id, {"paused", "failed"}, "queued")
        self._wake_event.set()
        return self.get_job(job_id)

    def cancel_job(self, job_id: str) -> dict:
        self._set_status(job_id, {"queued", "running", "paused", "failed"}, "cancelled")
        return self.get_job(job_id)

    def _set_status(self, job_id: str, allowed: set[str], target: str) -> None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT status FROM ingestion_jobs WHERE id=?",
                (job_id,),
            ).fetchone()
            if not row:
                raise KeyError(job_id)
            if row["status"] not in allowed:
                raise ValueError(f"Statuswechsel von {row['status']} nach {target} nicht erlaubt.")
            connection.execute(
                "UPDATE ingestion_jobs SET status=?, updated_at=? WHERE id=?",
                (target, _utc_now(), job_id),
            )

    def _resolve_source_dir(self, root_id: str, relative_path: str) -> Path:
        if root_id not in self.allowed_roots:
            raise ValueError("NAS-Wurzel ist nicht freigegeben.")
        root = self.allowed_roots[root_id]
        if not root.exists() or not root.is_dir():
            raise ValueError("NAS-Wurzel ist nicht erreichbar.")
        candidate = (root / relative_path.replace("\\", "/").strip("/")).resolve()
        if candidate != root and root not in candidate.parents:
            raise ValueError("Der angeforderte Ordner liegt außerhalb der Freigabe.")
        if not candidate.exists() or not candidate.is_dir():
            raise ValueError("Der angeforderte Ordner existiert nicht.")
        return candidate

    def _scan_files(self, source_dir: Path) -> list[Path]:
        allowed_extensions = set(FILE_TYPE_MAP)
        files = [
            path
            for path in source_dir.rglob("*")
            if path.is_file() and path.suffix.lower() in allowed_extensions
        ]
        files.sort(key=lambda path: _natural_key(path.relative_to(source_dir).as_posix()))
        return files

    def _worker_loop(self) -> None:
        while not self._stop_event.is_set():
            job = self._claim_next_job()
            if not job:
                self._wake_event.wait(self.poll_interval)
                self._wake_event.clear()
                continue
            self._process_job(job)

    def _claim_next_job(self) -> sqlite3.Row | None:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT * FROM ingestion_jobs
                WHERE status='queued'
                ORDER BY created_at ASC
                LIMIT 1
                """
            ).fetchone()
            if row:
                connection.execute(
                    "UPDATE ingestion_jobs SET status='running', updated_at=? WHERE id=?",
                    (_utc_now(), row["id"]),
                )
            return row

    def _process_job(self, job: sqlite3.Row) -> None:
        job_id = job["id"]
        try:
            root = self.allowed_roots.get(job["root_id"])
            if not root or not root.exists():
                raise RuntimeError("NAS-Wurzel ist während des Jobs nicht erreichbar.")

            while not self._stop_event.is_set():
                status = self.get_job(job_id)["status"]
                if status != "running":
                    return
                file_row = self._claim_next_file(job_id)
                if not file_row:
                    self._complete_job(job_id)
                    return
                self._process_file(job, file_row, root)
        except Exception as exc:
            logger.error("ingestion_job.failed", job_id=job_id, fehler=str(exc))
            with self._connect() as connection:
                connection.execute(
                    """
                    UPDATE ingestion_jobs
                    SET status='failed', last_error=?, updated_at=?
                    WHERE id=?
                    """,
                    (str(exc), _utc_now(), job_id),
                )

    def _claim_next_file(self, job_id: str) -> sqlite3.Row | None:
        now = _utc_now()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT * FROM ingestion_job_files
                WHERE job_id=? AND status='pending'
                ORDER BY position ASC
                LIMIT 1
                """,
                (job_id,),
            ).fetchone()
            if row:
                connection.execute(
                    """
                    UPDATE ingestion_job_files
                    SET status='running', updated_at=?
                    WHERE job_id=? AND position=?
                    """,
                    (now, job_id, row["position"]),
                )
                connection.execute(
                    """
                    UPDATE ingestion_jobs
                    SET current_file=?, updated_at=?
                    WHERE id=?
                    """,
                    (row["relative_path"], now, job_id),
                )
            return row

    def _process_file(self, job: sqlite3.Row, file_row: sqlite3.Row, root: Path) -> None:
        source_path = (root / file_row["relative_path"]).resolve()
        if source_path != root and root not in source_path.parents:
            self._record_file_error(job["id"], file_row, "Quelldatei liegt außerhalb der Freigabe.")
            return

        before_hash = self._sha256(source_path)
        temp_path: Path | None = None
        try:
            with source_path.open("rb") as source, tempfile.NamedTemporaryFile(
                mode="wb",
                suffix=source_path.suffix.lower(),
                prefix="argus_nas_",
                delete=False,
            ) as target:
                shutil.copyfileobj(source, target, length=1024 * 1024)
                temp_path = Path(target.name)

            result = UploadHandler().process_upload(
                temp_path,
                job["category"],
                bool(job["confidential"]),
                source_path=file_row["relative_path"],
                ingest_order=file_row["position"],
                total_files=job["total_files"],
            )
            after_hash = self._sha256(source_path)
            if before_hash != after_hash:
                raise RuntimeError("NAS-Original wurde während der Ingestion verändert.")
            if result.fehler:
                raise RuntimeError(result.fehler)
            self._record_file_success(job["id"], file_row, result.chunks_erstellt, before_hash)
        except Exception as exc:
            self._record_file_error(job["id"], file_row, str(exc))
        finally:
            if temp_path:
                temp_path.unlink(missing_ok=True)

    def _record_file_success(
        self,
        job_id: str,
        file_row: sqlite3.Row,
        chunks: int,
        source_hash: str,
    ) -> None:
        now = _utc_now()
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE ingestion_job_files
                SET status='completed', chunks=?, source_sha256=?, error=NULL, updated_at=?
                WHERE job_id=? AND position=?
                """,
                (chunks, source_hash, now, job_id, file_row["position"]),
            )
            connection.execute(
                """
                UPDATE ingestion_jobs
                SET processed_files=processed_files+1, total_chunks=total_chunks+?,
                    current_file=NULL, last_error=NULL, updated_at=?
                WHERE id=?
                """,
                (chunks, now, job_id),
            )

    def _record_file_error(
        self,
        job_id: str,
        file_row: sqlite3.Row,
        error: str,
    ) -> None:
        now = _utc_now()
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE ingestion_job_files
                SET status='failed', error=?, updated_at=?
                WHERE job_id=? AND position=?
                """,
                (error, now, job_id, file_row["position"]),
            )
            connection.execute(
                """
                UPDATE ingestion_jobs
                SET processed_files=processed_files+1, failed_files=failed_files+1,
                    current_file=NULL, last_error=?, updated_at=?
                WHERE id=?
                """,
                (error, now, job_id),
            )

    def _complete_job(self, job_id: str) -> None:
        now = _utc_now()
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE ingestion_jobs
                SET status='completed', current_file=NULL, updated_at=?, completed_at=?
                WHERE id=?
                """,
                (now, now, job_id),
            )

    @staticmethod
    def _sha256(file_path: Path) -> str:
        digest = hashlib.sha256()
        with file_path.open("rb") as source:
            for block in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()

    @staticmethod
    def _serialize_job(row: sqlite3.Row) -> dict:
        total = row["total_files"]
        processed = row["processed_files"]
        return {
            **dict(row),
            "confidential": bool(row["confidential"]),
            "progress_percent": round((processed / total) * 100, 1) if total else 0.0,
        }


job_manager = IngestionJobManager()
