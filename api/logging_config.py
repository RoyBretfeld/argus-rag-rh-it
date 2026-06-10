"""Logging-Konfiguration für Argus RAG.

Konfiguriert structlog mit zwei Output-destinationen:
- Konsole (für Entwicklung)
- logs/argus.jsonl (für Produktion/Auswertung)
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import structlog
from structlog.stdlib import add_log_level


def _add_event_name(logger, method_name, event_dict):
    """Fügt 'event' zum Dict hinzu wenn nicht vorhanden."""
    if "event" not in event_dict:
        event_dict["event"] = method_name
    return event_dict


def configure_logging() -> None:
    """Konfiguriert structlog für doppelte Ausgabe (Konsole + JSON-File).

    Alle Log-Events werden nach logs/argus.jsonl im JSON-Format geschrieben.
    Konsole bleibt für visuelles Feedback bei Development aktiv.

    Dieser Ansatz nutzt den nativen structlog mit eigener Processorkette die
    auf beiden Outputs schreibt.
    """
    # Verzeichnis für Log-Dateien sicherstellen
    log_dir = Path("logs")
    log_dir.mkdir(parents=True, exist_ok=True)

    log_file = log_dir / "argus.jsonl"

    # Console-Renderer (für Entwicklung)
    console_renderer = structlog.dev.ConsoleRenderer(
        colors=True,
    )

    # Eigenes Renderer-Objekt für doppelte Ausgabe
    class DualOutput:
        def __init__(self, console_renderer, log_file):
            self._console_renderer = console_renderer
            self._log_file = log_file

        def __call__(self, logger, method_name, event_dict):
            # Zuerst in Datei schreiben
            try:
                file_output = json.dumps(event_dict, sort_keys=True) + "\n"
                with self._log_file.open("a", encoding="utf-8") as f:
                    f.write(file_output)
            except Exception:
                pass

            # Dann Console-Ausgabe (als String zurückgeben)
            return self._console_renderer(logger, method_name, event_dict)

    # Konfiguration: eigener Renderer in der Processorkette
    structlog.configure(
        processors=[
            _add_event_name,
            add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            DualOutput(console_renderer, log_file),
        ],
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        wrapper_class=structlog.make_filtering_bound_logger(min_level="debug"),
        cache_logger_on_first_use=True,
    )


# Helper-Funktion für den Export
def get_structlog_config() -> dict:
    """Gibt die aktuelle structlog-Konfiguration als Dictionary zurück."""
    return {
        "log_file": "logs/argus.jsonl",
        "format": "jsonl",
        "timestamp_format": "iso",
    }
