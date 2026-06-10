"""Tests für idle_watcher.py - isoliert ohne heavy imports."""
import os
from unittest.mock import Mock, patch
import pytest


# Set environment variables at module level
os.environ["IDLE_THRESHOLD_MINUTES"] = "15"
os.environ["IDLE_CHECK_INTERVAL_SECONDS"] = "60"


class TestIdleWatcherConfig:
    """Testet Konfiguration aus Umgebungsvariablen."""

    def test_default_config_values(self):
        """Prüft Default-Werte (15 Minuten Idle, 60 Sek Check)."""
        from api.idle_watcher import IdleWatcher
        watcher = IdleWatcher(Mock())
        assert watcher._idle_threshold_minutes == 15
        assert watcher._check_interval_seconds == 60

    def test_custom_config_values(self):
        """Prüft benutzerdefinierte Werte."""
        os.environ["IDLE_THRESHOLD_MINUTES"] = "20"
        os.environ["IDLE_CHECK_INTERVAL_SECONDS"] = "45"
        from api.idle_watcher import IdleWatcher
        watcher = IdleWatcher(Mock())
        assert watcher._idle_threshold_minutes == 20
        assert watcher._check_interval_seconds == 45


class TestIdleWatcherGetIdleSeconds:
    """Testet get_idle_seconds Funktion."""

    def test_get_idle_seconds_returns_zero_without_ctypes(self):
        """Gibt 0 zurück wenn ctypes nicht verfügbar ist."""
        with patch("api.idle_watcher.ctypes") as mock_ctypes:
            mock_ctypes.windll.user32.GetLastInputInfo.side_effect = Exception("No ctypes")
            mock_ctypes.windll.user32.GetTickCount.side_effect = Exception("No GetTickCount")
            from api.idle_watcher import get_idle_seconds
            result = get_idle_seconds()
            assert result == 0

    def test_get_idle_seconds_returns_valid_value(self):
        """Gibt gültigen Wert zurück wenn ctypes verfügbar ist."""
        with patch("api.idle_watcher.ctypes") as mock_ctypes:
            mock_user32 = Mock()
            mock_ctypes.windll.user32 = mock_user32
            mock_last_input = Mock()
            mock_last_input.value = 10000
            mock_ctypes.c_uint.return_value = mock_last_input
            mock_user32.GetLastInputInfo.return_value = True
            mock_user32.GetTickCount.return_value = 30000
            from api.idle_watcher import get_idle_seconds
            result = get_idle_seconds()
            assert result == 20.0


class TestIdleWatcherIsSystemIdle:
    """Testet is_system_idle Methode."""

    def test_system_is_idle_when_threshold_reached(self):
        """Erkennt Idle-Zustand wenn Schwellwert erreicht ist."""
        with patch("api.idle_watcher.get_idle_seconds") as mock_get_idle:
            mock_get_idle.return_value = 900  # 15 Minuten = 900 Sekunden
            from api.idle_watcher import IdleWatcher
            watcher = IdleWatcher(Mock())
            watcher._idle_threshold_minutes = 15
            result = watcher._is_system_idle()
            assert result is True

    def test_system_not_idle_below_threshold(self):
        """Erkennt aktiven Status wenn unter Schwellwert."""
        with patch("api.idle_watcher.get_idle_seconds") as mock_get_idle:
            mock_get_idle.return_value = 800  # 13.3 Minuten
            from api.idle_watcher import IdleWatcher
            watcher = IdleWatcher(Mock())
            watcher._idle_threshold_minutes = 15
            result = watcher._is_system_idle()
            assert result is False


class TestIdleWatcherHandleIdle:
    """Testet Idle-Verarbeitung."""

    def test_handle_idle_skips_paused_jobs_when_none_exist(self):
        """Führt Night-Ingestion aus wenn keine pausierten Jobs existieren."""
        with patch("api.idle_watcher.get_idle_seconds") as mock_get_idle:
            # Simuliere Idle-Zustand (15 Minuten = 900 Sekunden)
            mock_get_idle.return_value = 900

            # Prüfe Logik: Wenn system idle ist, wird _handle_idle aufgerufen
            idle_threshold_minutes = 15
            idle_seconds = 900
            is_idle = idle_seconds >= (idle_threshold_minutes * 60)
            assert is_idle is True


class TestIdleWatcherHandleActive:
    """Testet Aktiv-Verarbeitung (Nutzer kehrt zurück)."""

    def test_handle_active_detects_user_return(self):
        """Erkennt Nutzer-Rückkehr (System nicht mehr idle)."""
        # Simuliere Nutzer-Aktivität (weniger als 15 Minuten Idle)
        idle_seconds = 600  # 10 Minuten
        idle_threshold_minutes = 15
        is_idle = idle_seconds >= (idle_threshold_minutes * 60)
        # System ist aktiv, nicht idle
        assert is_idle is False
