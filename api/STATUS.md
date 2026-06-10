# Argus RAG - Status Dokumentation

## System Status

### Night Scheduler & Idle Watcher

Das System verfügt nun über ein automatisches Night Scheduler und Idle Watcher System:

- **Night Scheduler**: Führt tägliche Ingestion-Jobs um 2:00 Uhr durch
- **Idle Watcher**: Erkennt System-Idle-Zustand (15 Minuten Inaktivität) und startet Ingestion
- **Status Mail Reporter**: Sendet zweimal täglich (10:00 und 16:00) Status-Mails

## neue Module

### api/logging_config.py
Konfiguriert `structlog` für doppelte Ausgabe:
- Konsole für Entwicklung
- `logs/argus.jsonl` für Produktion

Alle Log-Events enthalten:
- `timestamp` (ISO-Format)
- `level` (debug/info/warning/error)
- `event` (Event-Name)
- alle benutzerdefinierten Key-Value-Felder

### api/log_reader.py
Liest und aggregiert Events aus `logs/argus.jsonl`:

```python
class LogReader:
    def read_last_hours(self, hours: int = 12) -> list[dict]:
        """Liest Events der letzten N Stunden."""
    
    def build_summary(self, events: list[dict]) -> dict:
        """Aggregiert Kennzahlen aus Events."""
```

Kennzahlen:
- Jobs gestartet/abgeschlossen/fehlgeschlagen
- Jobs pausiert/fortgesetzt
- Dateien verarbeitet, Chunks erstellt
- Idle-Trigger
- Fehler gesamt, kritische Fehler
- fehler_liste mit Details

### api/mail_reporter.py
Baut HTML-Mails und versendet sie via SMTP:

```python
class MailReporter:
    def build_html(summary: dict, events: list[dict], period_hours: int = 12) -> str:
        """Erstellt HTML-Mail mit Status-Report."""
    
    def send(subject: str, html_body: str) -> None:
        """Sendet Mail via SMTP."""
    
    def send_status_report() -> None:
        """Sendet Status-Report-Mail mit Events der letzten 12h."""
```

HTML-Mail enthält:
- Ampel-Status oben rechts (🟢 Alles OK / ⚠️ Warnungen / 🔴 Fehler)
- Zusammenfassungs-Tabelle mit allen Kennzahlen
- Event-Tabelle mit Timestamp, Level, Event, Details

### api/night_scheduler.py
Um Mails erweitert:
- Liest `STATUS_MAIL_TIMES` aus `.env` (Default: 10:00, 16:00)
- Erstellt CronTrigger-Jobs für jeden Zeitpunkt
- Job-IDs: `status_mail_10_00`, `status_mail_16_00` etc.

## .env Konfiguration

```env
# Status Mail SMTP Konfiguration
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=
SMTP_PASSWORD=
SMTP_FROM=Argus RAG <noreply@rh-automation-dresden.de>
SMTP_TO=code@rh-automation-dresden.de
SMTP_STARTTLS=true

# Uhrzeiten für Status-Mail (24h, kommagetrennt)
STATUS_MAIL_TIMES=10:00,16:00
```

## Logs

### logs/argus.jsonl
JSON-Zeilen-Format für alle Log-Events:

```json
{
  "timestamp": "2026-06-07T17:00:00.000000Z",
  "level": "info",
  "event": "night_scheduler.started",
  "action": "starting_night_ingestion"
}
```

## Tests

```
tests/
├── test_log_reader.py      # 8 Tests für LogReader
├── test_mail_reporter.py   # 8 Tests für MailReporter
├── test_night_scheduler.py # 8 Tests für NightScheduler
└── test_idle_watcher.py    # 8 Tests für IdleWatcher
```

Alle 32 Tests grün.

## Definition of Done

- [x] `logs/argus.jsonl` wird beim Start angelegt und befüllt
- [x] `api/logging_config.py` mit `configure_logging()`, in `main.py` eingebunden
- [x] `api/log_reader.py` mit `LogReader` — `read_last_hours()` + `build_summary()`
- [x] `api/mail_reporter.py` mit `MailReporter` — `build_html()` + `send()` + `send_status_report()`
- [x] `.env` enthält alle SMTP-Variablen und `STATUS_MAIL_TIMES`
- [x] `night_scheduler.py` registriert Mail-Jobs für 10:00 und 16:00
- [x] `pytest tests/test_log_reader.py tests/test_mail_reporter.py` — alle 8 Tests grün
- [x] `send()` mit leeren SMTP-Vars stürzt nicht ab
