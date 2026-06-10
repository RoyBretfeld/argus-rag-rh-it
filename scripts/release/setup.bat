@echo off
setlocal enabledelayedexpansion
title Argus RAG - Setup
cd /d "%~dp0"

echo ==================================================
echo  Argus RAG - Setup (portables Release)
echo ==================================================
echo.

REM ---------- 1. Python 3.12 pruefen / installieren ----------
py -3.12 -c "print('ok')" >nul 2>&1
if errorlevel 1 (
    echo [SETUP] Python 3.12 nicht gefunden - Installation via winget...
    winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
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

REM ---------- 2. Virtuelle Umgebung + Abhaengigkeiten ----------
if not exist .venv (
    echo [SETUP] Erstelle virtuelle Umgebung...
    py -3.12 -m venv .venv
    if errorlevel 1 ( echo [FEHLER] venv-Erstellung fehlgeschlagen. & pause & exit /b 1 )
)
echo [SETUP] Installiere Python-Abhaengigkeiten (mehrere GB, kann 10-30 min dauern)...
.venv\Scripts\python -m pip install --upgrade pip
.venv\Scripts\python -m pip install -r requirements.txt
if errorlevel 1 ( echo [FEHLER] pip install fehlgeschlagen - Internetverbindung pruefen. & pause & exit /b 1 )
echo [OK] Abhaengigkeiten installiert.

REM ---------- 3. Konfiguration ----------
if not exist .env (
    copy .env.example .env >nul
    echo [SETUP] .env aus Vorlage erstellt - bei Bedarf anpassen (SMTP, NAS-Pfade).
)

REM ---------- 4. Ollama pruefen / installieren ----------
set "OLLAMA_EXE=ollama"
where ollama >nul 2>&1
if errorlevel 1 (
    if exist "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" (
        set "OLLAMA_EXE=%LOCALAPPDATA%\Programs\Ollama\ollama.exe"
    ) else (
        echo [SETUP] Ollama nicht gefunden - Installation via winget...
        winget install -e --id Ollama.Ollama --accept-package-agreements --accept-source-agreements
        if exist "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" (
            set "OLLAMA_EXE=%LOCALAPPDATA%\Programs\Ollama\ollama.exe"
        ) else (
            echo [WARNUNG] Ollama-Installation nicht verifizierbar. Modelle bitte
            echo           spaeter manuell laden: ollama pull mistral / moondream / nomic-embed-text
            goto :fertig
        )
    )
)
echo [OK] Ollama vorhanden.

REM ---------- 5. Modelle laden (ca. 6 GB Download) ----------
echo [SETUP] Lade Ollama-Modelle (mistral, moondream, nomic-embed-text)...
"%OLLAMA_EXE%" pull mistral
if errorlevel 1 echo [WARNUNG] mistral konnte nicht geladen werden.
"%OLLAMA_EXE%" pull moondream
if errorlevel 1 echo [WARNUNG] moondream konnte nicht geladen werden.
"%OLLAMA_EXE%" pull nomic-embed-text
if errorlevel 1 echo [WARNUNG] nomic-embed-text konnte nicht geladen werden.

:fertig
echo.
echo ==================================================
echo  Setup abgeschlossen.
echo  Die Vektor-Datenbank startet leer (data/ wird beim
echo  ersten Start automatisch angelegt).
echo  Starten mit: start_argus.bat
echo ==================================================
pause
