@echo off
:: PSA Telegram Notifier - Auto-Pull Script
:: Runs every 15 minutes to pull latest commits from GitHub
set LOG=C:\Users\admin\.gemini\antigravity-ide\scratch\psa-telegram-notifier\logs\watchdog.log
cd /d "C:\Users\admin\.gemini\antigravity-ide\scratch\psa-telegram-notifier"

git checkout conv_state.json >nul 2>&1
git fetch origin main >nul 2>&1

for /f "tokens=*" %%i in ('git rev-parse HEAD') do set LOCAL_REV=%%i
for /f "tokens=*" %%j in ('git rev-parse origin/main') do set REMOTE_REV=%%j

if "%LOCAL_REV%"=="%REMOTE_REV%" (
    exit /b 0
)

echo [%DATE% %TIME%] AUTOPULL: New commits detected on GitHub (%REMOTE_REV%). Pulling and restarting... >> "%LOG%"
git pull origin main >> "%LOG%" 2>&1

taskkill /f /im python.exe >nul 2>&1
taskkill /f /im pythonw.exe >nul 2>&1
timeout /t 2 /nobreak >nul
start "" "C:\Program Files\Python311\pythonw.exe" "C:\Users\admin\.gemini\antigravity-ide\scratch\psa-telegram-notifier\notifier.py"
echo [%DATE% %TIME%] AUTOPULL: Notifier updated and restarted successfully. >> "%LOG%"
