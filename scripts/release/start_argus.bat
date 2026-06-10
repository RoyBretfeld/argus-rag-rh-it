@echo off
title Argus RAG
cd /d "%~dp0"

if not exist .venv\Scripts\python.exe (
    echo [FEHLER] Keine Installation gefunden - bitte zuerst setup.bat ausfuehren.
    pause
    exit /b 1
)

REM Ollama-Dienst sicherstellen (startet ihn bei Bedarf im Hintergrund)
set "OLLAMA_EXE=ollama"
where ollama >nul 2>&1
if errorlevel 1 if exist "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" set "OLLAMA_EXE=%LOCALAPPDATA%\Programs\Ollama\ollama.exe"
"%OLLAMA_EXE%" list >nul 2>&1
if errorlevel 1 (
    echo [START] Starte Ollama-Dienst...
    start "Ollama" /min "%OLLAMA_EXE%" serve
    timeout /t 3 /nobreak >nul
)

echo ==================================================
echo  Argus RAG startet auf http://localhost:8000
echo ==================================================
start "Argus RAG Backend" cmd /k ".venv\Scripts\python -m uvicorn api.main:app --host 0.0.0.0 --port 8000"
timeout /t 4 /nobreak >nul
start http://localhost:8000
