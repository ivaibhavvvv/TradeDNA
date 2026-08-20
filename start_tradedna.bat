@echo off
title TradeDNA Intelligence Platform
echo ======================================================================
echo           Starting TradeDNA Exness MT5 Intelligence Platform
echo ======================================================================
echo.

cd /d "%~dp0"

echo [1/3] Starting Backend API (FastAPI on Port 8000)...
start "TradeDNA Backend API" /min cmd /c "cd /d apps\api && .venv\Scripts\python.exe -m uvicorn src.main:app --host 127.0.0.1 --port 8000"

echo [2/3] Starting Frontend Web App (Next.js on Port 3000)...
start "TradeDNA Frontend Web" /min cmd /c "cd /d apps\web && npm.cmd run dev"

echo [3/3] Waiting for services to initialize...
timeout /t 5 /nobreak >nul

echo Opening TradeDNA at: http://localhost:3000
start http://localhost:3000

echo.
echo ======================================================================
echo TradeDNA is LIVE and RUNNING!
echo - Web Dashboard:  http://localhost:3000
echo - API Docs:       http://127.0.0.1:8000/docs
echo.
echo (To stop TradeDNA, run stop_tradedna.bat or close the minimized windows)
echo ======================================================================
pause
