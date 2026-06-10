"""LogReader-Modul für Argus RAG.

Liest und aggregiert Events aus logs/argus.jsonl.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class LogReader:
    """Liest und aggregiert Events aus dem JSON-Log-File."""

    def __init__(self, log_file: str | Path = "logs/argus.jsonl"):
        self.log_file = Path(log_file)

    def read_last_hours(self, hours: int = 12) -> list[dict]:
        """Liest Events der letzten N Stunden.

        Args:
            hours: Anzahl der Stunden rückwirkend zu lesen.

        Returns:
            List von Event-Dicts, chronologisch sortiert.
        """
        if not self.log_file.exists():
            return []

        events = []
        cutoff = datetime.now(timezone.utc).replace(
            hour=datetime.now(timezone.utc).hour,
            minute=0,
            second=0,
            microsecond=0,
        )

        cutoff_time = cutoff.timestamp() - (hours * 3600)

        try:
            with self.log_file.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        event = json.loads(line)
                        # Prüfe Timestamp
                        timestamp_str = event.get("timestamp", "")
                        if timestamp_str:
                            try:
                                ts = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
                                if ts.timestamp() >= cutoff_time:
                                    events.append(event)
                            except (ValueError, TypeError):
                                # Fallback: wenn Timestamp nicht parsbar ist, trotzdem aufnehmen
                                events.append(event)
                        else:
                            # Fallback: wenn kein Timestamp, aufnehmen
                            events.append(event)
                    except json.JSONDecodeError:
                        continue
        except Exception:
            pass

        # Chronologisch sortieren
        events.sort(key=lambda e: e.get("timestamp", ""))
        return events

    def build_summary(self, events: list[dict]) -> dict[str, Any]:
        """Aggregiert Kennzahlen aus den Events.

        Args:
            events: Liste von Events aus read_last_hours().

        Returns:
            Dict mit aggregierten Kennzahlen und fehler_liste.
        """
        summary = {
            "jobs_gestartet": 0,
            "jobs_abgeschlossen": 0,
            "jobs_fehlgeschlagen": 0,
            "jobs_pausiert": 0,
            "jobs_fortgesetzt": 0,
            "dateien_verarbeitet": 0,
            "chunks_erstellt": 0,
            "idle_trigger": 0,
            "fehler_gesamt": 0,
            "kritische_fehler": 0,
            "fehler_liste": [],
        }

        for event in events:
            level = event.get("level", "info").lower()
            event_name = event.get("event", "")

            # Jobs gestartet
            if event_name in ("night_scheduler.job_created", "idle_watcher.ingest_triggered"):
                summary["jobs_gestartet"] += 1

            # Jobs abgeschlossen
            if event.get("status") == "completed" or event_name == "ingestion_job.completed":
                summary["jobs_abgeschlossen"] += 1

            # Jobs fehlgeschlagen
            if event.get("status") == "failed" or event_name == "ingestion_job.failed":
                summary["jobs_fehlgeschlagen"] += 1
            if event_name == "night_scheduler.root_skipped_unavailable":
                summary["jobs_fehlgeschlagen"] += 1

            # Jobs pausiert/fortgesetzt
            if event_name == "idle_watcher.jobs_paused":
                summary["jobs_pausiert"] += 1
            if event_name == "idle_watcher.jobs_resumed":
                summary["jobs_fortgesetzt"] += 1

            # Dateien verarbeitet
            if "processed_files" in event:
                try:
                    summary["dateien_verarbeitet"] += int(event["processed_files"])
                except (ValueError, TypeError):
                    pass

            # Chunks erstellt
            if "chunks_erstellt" in event:
                try:
                    summary["chunks_erstellt"] += int(event["chunks_erstellt"])
                except (ValueError, TypeError):
                    pass

            # Idle-Trigger
            if event_name == "idle_watcher.ingest_triggered":
                summary["idle_trigger"] += 1

            # Fehler gesamt
            if level in ("error", "warning"):
                summary["fehler_gesamt"] += 1
                if level == "error":
                    summary["kritische_fehler"] += 1

            # Fehlerliste aufbauen
            if level == "error":
                summary["fehler_liste"].append({
                    "timestamp": event.get("timestamp", ""),
                    "event": event.get("event", ""),
                    "detail": event.get("fehler", str(event)),
                })

        return summary
