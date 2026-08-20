@echo off
title Stopping TradeDNA
echo ======================================================================
echo           Stopping TradeDNA Services
echo ======================================================================
echo.

echo Freeing Port 8000 (Backend API)...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8000" ^| findstr "LISTENING"') do (
    taskkill /f /pid %%a >nul 2>&1
)

echo Freeing Port 3000 (Frontend Web App)...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":3000" ^| findstr "LISTENING"') do (
    taskkill /f /pid %%a >nul 2>&1
)

echo.
echo All TradeDNA services have been stopped cleanly.
timeout /t 2 /nobreak >nul
