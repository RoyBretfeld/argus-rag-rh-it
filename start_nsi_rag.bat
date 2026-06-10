@echo off
title NSI-RAGsystem Launcher
cd /d "%~dp0"

echo ==================================================
echo [WATCHDOG] Starte NSI-RAGsystem Backend...
echo ==================================================
start "NSI-RAG API Backend" cmd /k "py -3.12 -m uvicorn api.main:app --host 0.0.0.0 --port 8000"

echo ==================================================
echo [WATCHDOG] Starte NSI-RAGsystem React Frontend...
echo ==================================================
cd frontend
start "NSI-RAG React Frontend" cmd /k "npm run dev -- --host 0.0.0.0 --port 5173"

echo ==================================================
echo NSI-RAGsystem erfolgreich gestartet!
echo API: http://localhost:8000
echo Frontend: http://localhost:5173
echo ==================================================
pause
