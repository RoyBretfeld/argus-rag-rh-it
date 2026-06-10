"""Tests für mail_reporter.py."""
import os
from unittest.mock import Mock, patch, MagicMock

import pytest


class TestMailReporterBuildHtml:
    """Testet build_html Methode."""

    def test_build_html_returns_valid_html(self):
        """Gibt validen HTML-String zurück."""
        from api.log_reader import LogReader
        from api.mail_reporter import MailReporter

        reader = LogReader()
        summary = reader.build_summary([])
        reporter = MailReporter()
        html = reporter.build_html(summary, [], 12)

        assert "<html>" in html
        assert "<head>" in html
        assert "<body" in html  # body tag mit attributes
        assert "Argus RAG" in html
        assert "Status-Report" in html

    def test_build_html_includes_summary_data(self):
        """Enthält Summary-Daten in HTML-Tabelle."""
        from api.log_reader import LogReader
        from api.mail_reporter import MailReporter

        reader = LogReader()
        events = [
            {"event": "night_scheduler.job_created", "level": "info"},
        ]
        summary = reader.build_summary(events)

        reporter = MailReporter()
        html = reporter.build_html(summary, events, 12)

        assert "Jobs gestartet" in html
        assert "abgeschlossen" in html
        assert "fehlgeschlagen" in html

    def test_build_html_includes_event_table(self):
        """Enthält Event-Tabelle in HTML."""
        from api.log_reader import LogReader
        from api.mail_reporter import MailReporter

        reader = LogReader()
        summary = reader.build_summary([])
        reporter = MailReporter()

        events = [
            {"event": "test_event", "level": "info", "timestamp": "2026-06-07T10:00:00Z"},
        ]
        html = reporter.build_html(summary, events, 12)

        assert "<table" in html  # table tag mit attributes
        assert "test_event" in html

    def test_build_html_status_colors(self):
        """Enthält korrekte Farben für Status (ampel)."""
        from api.log_reader import LogReader
        from api.mail_reporter import MailReporter

        reader = LogReader()
        events = [
            {"event": "error_event", "level": "error", "fehler": "Error"},
        ]
        summary = reader.build_summary(events)

        reporter = MailReporter()
        html = reporter.build_html(summary, events, 12)

        assert "Fehler" in html  # Red status for errors


class TestMailReporterSend:
    """Testet send Methode."""

    def test_send_without_smtp_vars_logs_warning(self):
        """Ohne SMTP-Vars wird nur gewarnt."""
        from api.mail_reporter import MailReporter

        # Leere SMTP-Vars
        with patch.dict(os.environ, {"SMTP_USER": "", "SMTP_PASSWORD": ""}):
            reporter = MailReporter()

            with patch("api.mail_reporter.logger") as mock_logger:
                reporter.send("Test Subject", "<html>Test</html>")
                mock_logger.warning.assert_called_once()

    def test_send_with_mock_smtp(self):
        """Sendet mit mocktem SMTP-Server."""
        from api.mail_reporter import MailReporter

        with patch.dict(
            os.environ,
            {
                "SMTP_HOST": "smtp.gmail.com",
                "SMTP_PORT": "587",
                "SMTP_USER": "test@example.com",
                "SMTP_PASSWORD": "password",
                "SMTP_FROM": "sender@example.com",
                "SMTP_TO": "recipient@example.com",
            },
        ):
            reporter = MailReporter()

            with patch("api.mail_reporter.smtplib.SMTP") as mock_smtp:
                mock_server = MagicMock()
                mock_smtp.return_value = mock_server

                reporter.send("Test Subject", "<html>Test</html>")

                mock_smtp.assert_called_once_with("smtp.gmail.com", 587)
                mock_server.starttls.assert_called_once()
                mock_server.login.assert_called_once_with("test@example.com", "password")
                mock_server.send_message.assert_called_once()
                mock_server.quit.assert_called_once()

    def test_send_handles_smtp_error(self):
        """Behandelt SMTP-Fehler ohne Absturz."""
        from api.mail_reporter import MailReporter

        with patch.dict(
            os.environ,
            {
                "SMTP_HOST": "smtp.gmail.com",
                "SMTP_PORT": "587",
                "SMTP_USER": "test@example.com",
                "SMTP_PASSWORD": "password",
            },
        ):
            reporter = MailReporter()

            with patch("api.mail_reporter.smtplib.SMTP") as mock_smtp:
                mock_smtp.side_effect = Exception("Connection failed")

                with patch("api.mail_reporter.logger") as mock_logger:
                    reporter.send("Test Subject", "<html>Test</html>")
                    mock_logger.error.assert_called_once()


class TestMailReporterSendStatusReport:
    """Testet send_status_report Methode."""

    def test_send_status_report_flow(self):
        """Vollständiger Ablauf: read -> summary -> build -> send."""
        from api.log_reader import LogReader
        from api.mail_reporter import MailReporter

        # Mock LogReader
        mock_reader = Mock(spec=LogReader)
        mock_reader.read_last_hours.return_value = []
        mock_reader.build_summary.return_value = {
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

        # SMTP-Vars setzen BEFORE Reporter creation
        with patch.dict(
            os.environ,
            {
                "SMTP_HOST": "smtp.gmail.com",
                "SMTP_PORT": "587",
                "SMTP_USER": "test@example.com",
                "SMTP_PASSWORD": "password",
            },
        ):
            reporter = MailReporter(log_reader=mock_reader)

            with patch("api.mail_reporter.smtplib.SMTP") as mock_smtp:
                mock_server = MagicMock()
                mock_smtp.return_value = mock_server
                mock_server.send_message.return_value = None

                reporter.send_status_report()

                # Prüfe dass read_last_hours aufgerufen wurde
                mock_reader.read_last_hours.assert_called_once_with(12)
                # Prüfe dass build_summary aufgerufen wurde
                mock_reader.build_summary.assert_called_once()
                # Prüfe dass send aufgerufen wurde
                mock_server.send_message.assert_called_once()


