"""Tests für log_reader.py."""
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch

import pytest


class TestLogReaderReadLastHours:
    """Testet read_last_hours Methode."""

    def test_read_last_hours_empty_file(self, tmp_path):
        """Liest leere Log-Datei - leere Liste zurück."""
        log_file = tmp_path / "empty.jsonl"
        log_file.write_text("")

        from api.log_reader import LogReader
        reader = LogReader(log_file)
        events = reader.read_last_hours(12)
        assert events == []

    def test_read_last_hours_filters_by_time(self, tmp_path):
        """Filtert Events außerhalb des Zeitfensters."""
        log_file = tmp_path / "test.jsonl"

        # Event innerhalb des Zeitfensters (heute)
        recent = datetime.now(timezone.utc).replace(hour=10, minute=0, second=0, microsecond=0)

        # Event außerhalb des Zeitfensters (mehr als 12 Stunden alt)
        # Wir nutzen einen timestamp aus dem vergangenen Jahr
        old = datetime.now(timezone.utc).replace(
            year=2025, month=12, day=1, hour=10, minute=0, second=0, microsecond=0
        )

        events = [
            {"timestamp": old.isoformat(), "event": "old_event"},
            {"timestamp": recent.isoformat(), "event": "recent_event"},
        ]

        log_file.write_text("\n".join(json.dumps(e) for e in events) + "\n")

        from api.log_reader import LogReader
        reader = LogReader(log_file)
        result = reader.read_last_hours(12)
        # Nur recent Event sollte zurückkommen
        assert len(result) == 1
        assert result[0]["event"] == "recent_event"

    def test_read_last_hours_handles_invalid_timestamp(self, tmp_path):
        """Behandelt ungültige Timestamps ohne Crash."""
        log_file = tmp_path / "invalid.jsonl"
        # Event ohne Timestamp
        log_file.write_text('{"event": "no_timestamp"}\n')

        from api.log_reader import LogReader
        reader = LogReader(log_file)
        result = reader.read_last_hours(12)
        assert len(result) == 1

    def test_read_last_hours_empty_file_path(self, tmp_path):
        """Liest nicht existierende Datei - leere Liste."""
        log_file = tmp_path / "nonexistent.jsonl"

        from api.log_reader import LogReader
        reader = LogReader(log_file)
        result = reader.read_last_hours(12)
        assert result == []


class TestLogReaderBuildSummary:
    """Testet build_summary Methode."""

    def test_build_summary_counts_events(self):
        """Zählt Events korrekt."""
        from api.log_reader import LogReader

        events = [
            {"event": "night_scheduler.job_created", "level": "info"},
            {"event": "idle_watcher.ingest_triggered", "level": "info"},
            {"event": "ingestion_job.completed", "status": "completed", "level": "info"},
            {"event": "ingestion_job.failed", "status": "failed", "level": "error", "fehler": "Error msg"},
            {"event": "idle_watcher.jobs_paused", "level": "info"},
            {"event": "idle_watcher.jobs_resumed", "level": "info"},
            {"event": "night_scheduler.job_created", "level": "info"},
        ]

        reader = LogReader()
        summary = reader.build_summary(events)

        assert summary["jobs_gestartet"] == 3
        assert summary["jobs_abgeschlossen"] == 1
        assert summary["jobs_fehlgeschlagen"] == 1
        assert summary["jobs_pausiert"] == 1
        assert summary["jobs_fortgesetzt"] == 1

    def test_build_summary_fehler_liste(self):
        """Gibt fehler_liste mit korrekten Feldern zurück."""
        from api.log_reader import LogReader

        events = [
            {"event": "ingestion_job.failed", "level": "error", "fehler": "Datei nicht gefunden", "timestamp": "2026-06-07T10:00:00Z"},
            {"event": "night_scheduler.root_skipped_unavailable", "level": "error", "fehler": "Root nicht erreichbar", "timestamp": "2026-06-07T11:00:00Z"},
        ]

        reader = LogReader()
        summary = reader.build_summary(events)

        assert len(summary["fehler_liste"]) == 2
        assert summary["fehler_liste"][0]["event"] == "ingestion_job.failed"
        assert summary["fehler_liste"][0]["detail"] == "Datei nicht gefunden"
        assert summary["fehler_liste"][0]["timestamp"] == "2026-06-07T10:00:00Z"

    def test_build_summary_counts_idle_trigger(self):
        """Zählt idle_trigger korrekt."""
        from api.log_reader import LogReader

        events = [
            {"event": "idle_watcher.ingest_triggered", "level": "info"},
            {"event": "idle_watcher.ingest_triggered", "level": "info"},
            {"event": "night_scheduler.job_created", "level": "info"},
        ]

        reader = LogReader()
        summary = reader.build_summary(events)

        assert summary["idle_trigger"] == 2
        assert summary["jobs_gestartet"] == 3  # 2 idle + 1 job_created

    def test_build_summary_fehler_liste_only_errors(self):
        """Gibt fehler_liste nur für errors (nicht warnings)."""
        from api.log_reader import LogReader

        events = [
            {"event": "error_event", "level": "error", "fehler": "Error 1"},
            {"event": "warning_event", "level": "warning", "fehler": "Warning 1"},
        ]

        reader = LogReader()
        summary = reader.build_summary(events)

        assert len(summary["fehler_liste"]) == 1
        assert summary["fehler_liste"][0]["event"] == "error_event"
