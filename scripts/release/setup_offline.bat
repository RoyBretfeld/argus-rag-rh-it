@echo off
setlocal enabledelayedexpansion
title Argus RAG - Offline-Setup
cd /d "%~dp0"

echo ==================================================
echo  Argus RAG - Offline-Setup (kein Internet noetig)
echo ==================================================
echo.

REM ---------- 1. Python 3.12 pruefen / aus Paket installieren ----------
py -3.12 -c "print('ok')" >nul 2>&1
if errorlevel 1 (
    echo [SETUP] Python 3.12 nicht gefunden - Installation aus Paket...
    installers\python-3.12.10-amd64.exe /quiet InstallAllUsers=0 PrependPath=1 Include_launcher=1 Include_test=0
    py -3.12 -c "print('ok')" >nul 2>&1
    if errorlevel 1 (
        echo.
        echo [HINWEIS] Python wurde installiert, aber der PATH ist in diesem
        echo           Fenster noch nicht aktiv. Bitte Fenster schliessen und
        echo           setup.bat ERNEUT ausfuehren.
        pause
        exit /b 1
    )
)
echo [OK] Python 3.12 vorhanden.

REM ---------- 2. Virtuelle Umgebung + Abhaengigkeiten (offline) ----------
if not exist .venv (
    echo [SETUP] Erstelle virtuelle Umgebung...
    py -3.12 -m venv .venv
    if errorlevel 1 ( echo [FEHLER] venv-Erstellung fehlgeschlagen. & pause & exit /b 1 )
)
echo [SETUP] Installiere Python-Abhaengigkeiten aus dem Paket (wheels\)...
.venv\Scripts\python -m pip install --no-index --find-links=wheels -r requirements.txt
if errorlevel 1 ( echo [FEHLER] Offline-Installation fehlgeschlagen. & pause & exit /b 1 )
echo [OK] Abhaengigkeiten installiert.

REM ---------- 3. Konfiguration ----------
if not exist .env (
    copy .env.example .env >nul
    echo [SETUP] .env aus Vorlage erstellt - bei Bedarf anpassen (SMTP, NAS-Pfade).
)

REM ---------- 4. Ollama aus Paket installieren ----------
set "OLLAMA_EXE=ollama"
where ollama >nul 2>&1
if errorlevel 1 (
    if exist "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" (
        set "OLLAMA_EXE=%LOCALAPPDATA%\Programs\Ollama\ollama.exe"
    ) else (
        echo [SETUP] Installiere Ollama aus Paket (dauert einige Minuten)...
        start /wait "" installers\OllamaSetup.exe /VERYSILENT /NORESTART
        if exist "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" (
            set "OLLAMA_EXE=%LOCALAPPDATA%\Programs\Ollama\ollama.exe"
        ) else (
            echo [WARNUNG] Ollama-Installation nicht verifizierbar.
            echo           Bitte installers\OllamaSetup.exe manuell ausfuehren,
            echo           danach setup.bat erneut starten.
            pause
            exit /b 1
        )
    )
)
echo [OK] Ollama vorhanden.

REM ---------- 5. Modelle aus Paket in den Ollama-Store kopieren ----------
set "STORE=%USERPROFILE%\.ollama\models"
if defined OLLAMA_MODELS set "STORE=%OLLAMA_MODELS%"
echo [SETUP] Kopiere KI-Modelle nach "%STORE%" (ca. 6 GB)...
robocopy ollama_models "%STORE%" /E /NFL /NDL /NJH /NJS
if %ERRORLEVEL% GEQ 8 ( echo [FEHLER] Modell-Kopie fehlgeschlagen. & pause & exit /b 1 )
echo [OK] Modelle installiert (mistral, moondream, nomic-embed-text).

echo.
echo ==================================================
echo  Offline-Setup abgeschlossen.
echo  Die Vektor-Datenbank startet leer (data/ wird beim
echo  ersten Start automatisch angelegt).
echo  Starten mit: start_argus.bat
echo ==================================================
pause
