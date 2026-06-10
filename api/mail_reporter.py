"""MailReporter-Modul für Argus RAG.

Baut HTML-Mails und versendet sie via SMTP.
"""

from __future__ import annotations

import os
import smtplib
import structlog
from email.mime.text import MIMEText
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from api.log_reader import LogReader

logger = structlog.get_logger(__name__)


class MailReporter:
    """Reporter der Status-Mails generiert und versendet."""

    def __init__(
        self,
        log_reader: LogReader | None = None,
        log_file: str | Path = "logs/argus.jsonl",
    ):
        self.log_reader = log_reader or LogReader(log_file)
        self.smtp_host = os.environ.get("SMTP_HOST", "")
        self.smtp_port = int(os.environ.get("SMTP_PORT", "587"))
        self.smtp_user = os.environ.get("SMTP_USER", "")
        self.smtp_password = os.environ.get("SMTP_PASSWORD", "")
        self.smtp_from = os.environ.get("SMTP_FROM", "Argus RAG <noreply@rh-automation-dresden.de>")
        self.smtp_to = os.environ.get("SMTP_TO", "code@rh-automation-dresden.de")
        self.smtp_starttls = os.environ.get("SMTP_STARTTLS", "true").lower() == "true"

    def build_html(
        self,
        summary: dict[str, Any],
        events: list[dict],
        period_hours: int = 12,
    ) -> str:
        """Erstellt HTML-Mail mit Status-Report.

        Args:
            summary: Aggregierte Kennzahlen von LogReader.build_summary().
            events: Liste aller Events.
            period_hours: Zeitspanne in Stunden.

        Returns:
            HTML-Mail-String mit Inline-Styles.
        """
        # Zeitspanne ermitteln
        end_time = datetime.now(timezone.utc)
        start_time = datetime.fromtimestamp(
            end_time.timestamp() - (period_hours * 3600),
            tz=timezone.utc,
        )

        # Ampel-Status ermitteln
        if summary["kritische_fehler"] > 0:
            status_emoji = "🔴"
            status_text = "Fehler"
            status_color = "#dc3545"
        elif summary["fehler_gesamt"] > 0:
            status_emoji = "🟡"
            status_text = "Warnungen"
            status_color = "#ffc107"
        else:
            status_emoji = "🟢"
            status_text = "Alles OK"
            status_color = "#28a745"

        # HTML generieren
        html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Argus RAG Status-Report</title>
</head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 0; padding: 20px; background-color: #f5f5f5;">
    <div style="max-width: 800px; margin: 0 auto; background: white; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
        <!-- Header mit Ampel-Status -->
        <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 30px; border-radius: 8px 8px 0 0; color: white;">
            <h1 style="margin: 0; font-size: 24px;">Argus RAG — Status-Report</h1>
            <div style="display: flex; align-items: center; gap: 15px; margin-top: 15px; font-size: 18px; font-weight: bold;">
                <span style="font-size: 28px;">{status_emoji}</span>
                <span>{status_text}</span>
            </div>
        </div>

        <!-- Zeitraum und Zusammenfassung -->
        <div style="padding: 30px;">
            <p style="margin: 0 0 20px 0; color: #666;">
                Zeitraum: {start_time.strftime('%d.%m.%Y %H:%M')} – {end_time.strftime('%d.%m.%Y %H:%M')} ({period_hours}h)
            </p>

            <!-- Zusammenfassungs-Tabelle -->
            <table style="width: 100%; border-collapse: collapse; margin-bottom: 30px; background: #f8f9fa; border-radius: 8px; overflow: hidden;">
                <tr>
                    <td style="padding: 15px; border-bottom: 1px solid #e9ecef; text-align: center; font-size: 14px;">
                        <div style="font-size: 24px; font-weight: bold; color: #333;">{summary['jobs_gestartet']}</div>
                        <div style="color: #666;">Jobs gestartet</div>
                    </td>
                    <td style="padding: 15px; border-bottom: 1px solid #e9ecef; text-align: center; font-size: 14px;">
                        <div style="font-size: 24px; font-weight: bold; color: #333;">{summary['jobs_abgeschlossen']}</div>
                        <div style="color: #666;">abgeschlossen</div>
                    </td>
                    <td style="padding: 15px; border-bottom: 1px solid #e9ecef; text-align: center; font-size: 14px;">
                        <div style="font-size: 24px; font-weight: bold; color: #dc3545;">{summary['jobs_fehlgeschlagen']}</div>
                        <div style="color: #666;">fehlgeschlagen</div>
                    </td>
                </tr>
                <tr>
                    <td style="padding: 15px; border-bottom: 1px solid #e9ecef; text-align: center; font-size: 14px;">
                        <div style="font-size: 24px; font-weight: bold; color: #333;">{summary['dateien_verarbeitet']}</div>
                        <div style="color: #666;">Dateien verarbeitet</div>
                    </td>
                    <td style="padding: 15px; border-bottom: 1px solid #e9ecef; text-align: center; font-size: 14px;">
                        <div style="font-size: 24px; font-weight: bold; color: #333;">{summary['chunks_erstellt']}</div>
                        <div style="color: #666;">Chunks erstellt</div>
                    </td>
                    <td style="padding: 15px; text-align: center; font-size: 14px;">
                        <div style="font-size: 24px; font-weight: bold; color: #333;">{summary['idle_trigger']}</div>
                        <div style="color: #666;">Idle-Trigger</div>
                    </td>
                </tr>
                <tr>
                    <td style="padding: 15px; border-top: 1px solid #e9ecef; text-align: center; font-size: 14px;">
                        <div style="font-size: 24px; font-weight: bold; color: #ffc107;">{summary['jobs_pausiert']}</div>
                        <div style="color: #666;">pausiert</div>
                    </td>
                    <td style="padding: 15px; border-top: 1px solid #e9ecef; text-align: center; font-size: 14px;">
                        <div style="font-size: 24px; font-weight: bold; color: #28a745;">{summary['jobs_fortgesetzt']}</div>
                        <div style="color: #666;">fortgesetzt</div>
                    </td>
                    <td style="padding: 15px; border-top: 1px solid #e9ecef; text-align: center; font-size: 14px;">
                        <div style="font-size: 24px; font-weight: bold; color: #dc3545;">{summary['kritische_fehler']}</div>
                        <div style="color: #666;">kritische Fehler</div>
                    </td>
                </tr>
            </table>

            <!-- Events-Tabelle -->
            <h2 style="margin: 0 0 15px 0; color: #333; font-size: 18px;">Event-Übersicht</h2>
            <div style="max-height: 400px; overflow-y: auto; border: 1px solid #dee2e6; border-radius: 4px;">
                <table style="width: 100%; border-collapse: collapse; font-size: 13px;">
                    <thead style="background: #f8f9fa; position: sticky; top: 0;">
                        <tr>
                            <th style="padding: 10px; text-align: left; border-bottom: 2px solid #dee2e6;">Zeit</th>
                            <th style="padding: 10px; text-align: left; border-bottom: 2px solid #dee2e6;">Level</th>
                            <th style="padding: 10px; text-align: left; border-bottom: 2px solid #dee2e6;">Event</th>
                            <th style="padding: 10px; text-align: left; border-bottom: 2px solid #dee2e6;">Details</th>
                        </tr>
                    </thead>
                    <tbody>
                        {self._render_events(events)}
                    </tbody>
                </table>
            </div>
        </div>

        <!-- Footer -->
        <div style="background: #f8f9fa; padding: 20px 30px; border-radius: 0 0 8px 8px; text-align: center; font-size: 12px; color: #666;">
            <p style="margin: 0;">Diese Mail wurde automatisch generiert vom Argus RAG System.</p>
            <p style="margin: 5px 0 0 0;">&copy; {end_time.year} RH Automation Dresden</p>
        </div>
    </div>
</body>
</html>
"""
        return html

    def _render_events(self, events: list[dict]) -> str:
        """RenderEvents als HTML-Table Rows.

        Args:
            events: Liste von Events.

        Returns:
            HTML-String mit table rows.
        """
        rows = []
        for event in events[-50:]:  # Nur letzte 50 Events
            timestamp = event.get("timestamp", "")
            level = event.get("level", "info").lower()
            event_name = event.get("event", "")
            detail = event.get("fehler", str(event))

            # Level-Farbe
            if level == "error":
                level_color = "#dc3545"
            elif level == "warning":
                level_color = "#ffc107"
            else:
                level_color = "#28a745"

            # Kürze Detail-Text
            if len(detail) > 100:
                detail = detail[:97] + "..."

            row = f"""<tr style="border-bottom: 1px solid #e9ecef;">
    <td style="padding: 8px 10px; font-size: 12px; color: #666;">{timestamp}</td>
    <td style="padding: 8px 10px; font-size: 12px; color: {level_color}; font-weight: bold;">{level.upper()}</td>
    <td style="padding: 8px 10px; font-size: 12px; font-family: monospace;">{event_name}</td>
    <td style="padding: 8px 10px; font-size: 12px; color: #495057;">{detail}</td>
</tr>"""
            rows.append(row)

        return "\n".join(rows)

    def send(self, subject: str, html_body: str) -> None:
        """Sendet die Mail via SMTP.

        Args:
            subject: Mail-Betreff.
            html_body: HTML-Mail-Body.
        """
        # Prüfe SMTP-Vars
        if not self.smtp_user or not self.smtp_password:
            logger.warning(
                "mail_reporter.smtp_not_configured",
                message="SMTP-User oder SMTP-Password nicht gesetzt. Mail nicht versendet.",
            )
            return

        msg = MIMEText(html_body, "html", "utf-8")
        msg["Subject"] = subject
        msg["From"] = self.smtp_from
        msg["To"] = self.smtp_to

        try:
            # SMTP-Verbindung aufbauen
            if self.smtp_starttls:
                server = smtplib.SMTP(self.smtp_host, self.smtp_port)
                server.starttls()
            else:
                server = smtplib.SMTP_SSL(self.smtp_host, self.smtp_port)

            server.login(self.smtp_user, self.smtp_password)
            server.send_message(msg)
            server.quit()

            logger.info(
                "mail_reporter.sent",
                subject=subject,
                to=self.smtp_to,
            )
        except smtplib.SMTPException as e:
            logger.error(
                "mail_reporter.send_error",
                fehler=str(e),
                subject=subject,
                to=self.smtp_to,
            )
        except Exception as e:
            logger.error(
                "mail_reporter.send_error",
                fehler=str(e),
                subject=subject,
                to=self.smtp_to,
            )

    def send_status_report(self) -> None:
        """Sendet Status-Report-Mail mit Events der letzten 12h."""
        # Events lesen
        events = self.log_reader.read_last_hours(12)
        summary = self.log_reader.build_summary(events)

        # Timestamp für Subject
        end_time = datetime.now(timezone.utc)

        # Status für Subject ermitteln
        if summary["kritische_fehler"] > 0:
            status_text = "🚨 Fehler"
        elif summary["fehler_gesamt"] > 0:
            status_text = "⚠️ Warnungen"
        else:
            status_text = "✅ OK"

        subject = f"[Argus RAG] Status-Report {end_time.strftime('%d.%m.%Y %H:%M')} — {status_text}"

        # HTML generieren
        html = self.build_html(summary, events, 12)

        # Senden
        self.send(subject, html)
