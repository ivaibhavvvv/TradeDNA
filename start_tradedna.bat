@echo off
setlocal enabledelayedexpansion
title TradeDNA Intelligence Platform Launcher
cls
echo ======================================================================
echo           Starting TradeDNA Exness MT5 Intelligence Platform
echo ======================================================================
echo.

cd /d "%~dp0"

echo [1/4] Cleaning up any previous hanging processes on ports 8000 & 3000...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8000" ^| findstr "LISTENING"') do taskkill /f /pid %%a >nul 2>&1
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":3000" ^| findstr "LISTENING"') do taskkill /f /pid %%a >nul 2>&1

echo [2/4] Starting FastAPI Backend Engine (Port 8000)...
start "TradeDNA Backend API" /min cmd /c "cd /d "%~dp0apps\api" && .venv\Scripts\python.exe -m uvicorn src.main:app --host 127.0.0.1 --port 8000"

echo [3/4] Starting Next.js Web Dashboard (Port 3000)...
start "TradeDNA Frontend Web" /min cmd /c "cd /d "%~dp0apps\web" && npm.cmd run dev"

echo [4/4] Waiting for backend and frontend services to be 100%% ready...
powershell -NoProfile -Command ^
  "$backendOk = $false; $frontendOk = $false; $attempts = 0;" ^
  "while ((-not $backendOk -or -not $frontendOk) -and $attempts -lt 40) {" ^
  "  Start-Sleep -Milliseconds 800; $attempts++;" ^
  "  if (-not $backendOk) {" ^
  "    try { $res = Invoke-WebRequest -Uri 'http://127.0.0.1:8000/health' -UseBasicParsing -TimeoutSec 2; if ($res.StatusCode -eq 200) { $backendOk = $true; Write-Host '  [OK] Backend API is Healthy (Port 8000)' -ForegroundColor Green } } catch {}" ^
  "  }" ^
  "  if (-not $frontendOk) {" ^
  "    try { $res = Invoke-WebRequest -Uri 'http://localhost:3000/health' -UseBasicParsing -TimeoutSec 2; if ($res.StatusCode -eq 200) { $frontendOk = $true; Write-Host '  [OK] Frontend Dashboard is Healthy (Port 3000)' -ForegroundColor Green } } catch {}" ^
  "  }" ^
  "}"

echo.
echo ======================================================================
echo TradeDNA is LIVE and RUNNING!
echo Dashboard: http://localhost:3000
echo ======================================================================
echo.
echo Opening TradeDNA in your default browser...
start http://localhost:3000/dashboard/overview

echo.
echo NOTE: Keep this window or the minimized services running while using TradeDNA.
echo To cleanly stop all services, run stop_tradedna.bat.
pause
