# Projekt-Notizen (Night-Job-Feature, 2026-06)

> Konsolidiert 2026-06-10: Die früheren Verweise auf `memory/*.md` zeigten auf ein
> nie eingechecktes Verzeichnis — Inhalte sind hier direkt zusammengefasst.

## Night Scheduler (`api/night_scheduler.py`)
- APScheduler `BackgroundScheduler` mit `CronTrigger`, Startzeit über
  `NIGHT_SCHEDULER_HOUR` / `NIGHT_SCHEDULER_MINUTE` (Default 02:00).
- SHA-256-Duplikatprüfung vor Ingestion; fehlgeschlagene Dateien erzeugen
  Failed-Job-Einträge statt den Lauf abzubrechen.
- In FastAPI-Lifespan integriert (Start/Stop mit der App).

## Idle Watcher (`api/idle_watcher.py`)
- Idle-Erkennung über Windows-API (`GetLastInputInfo` via ctypes).
- `IDLE_THRESHOLD_MINUTES` (Default 15) bis Ingestion anläuft,
  `IDLE_CHECK_INTERVAL_SECONDS` (Default 60) Prüfintervall.
- Endpoint: `GET /api/system/idle`; Frontend zeigt Idle-Badge im `NightQueuePanel.tsx`.

## Status-Mail (`api/mail_reporter.py`)
- HTML-Mails via SMTP; Konfiguration ausschließlich über `.env`
  (`SMTP_HOST/PORT/USER/PASSWORD/FROM/TO/STARTTLS`, `STATUS_MAIL_TIMES`).
- Ohne `SMTP_USER`/`SMTP_PASSWORD` wird der Versand sauber übersprungen (Log-Eintrag).

## Tests
- Je 8 Unit-Tests für `night_scheduler` und `idle_watcher`, dazu
  `test_mail_reporter.py` und `test_log_reader.py`.
- Windows-Import-Crash-Fix: Tests sind von der `unstructured`/`magic`-Importkette
  isoliert (deshalb einzelne Skips in der Suite).
- Suite-Stand 2026-06-10: 90 passed, 5 skipped (`py -3.12 -m pytest tests/ -q`).

## Umgebung (Windows-Hinweis)
- Abhängigkeiten liegen im globalen Python 3.12 — immer `py -3.12` verwenden;
  `python` im PATH kann auf ein fremdes venv zeigen.
