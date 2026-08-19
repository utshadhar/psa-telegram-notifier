@echo off
:: PSA Telegram Notifier - Smart Watchdog (with logging and auto-pull)
set LOG=C:\Users\admin\.gemini\antigravity-ide\scratch\psa-telegram-notifier\logs\watchdog.log
cd /d "C:\Users\admin\.gemini\antigravity-ide\scratch\psa-telegram-notifier"

set PS_SCRIPT=%TEMP%\psa_health_check.ps1
echo try { > "%PS_SCRIPT%"
echo   $r = Invoke-WebRequest -Uri "http://localhost:8085/" -TimeoutSec 10 -UseBasicParsing -ErrorAction Stop >> "%PS_SCRIPT%"
echo   $j = $r.Content ^| ConvertFrom-Json >> "%PS_SCRIPT%"
echo   if ($j.status -eq "online") { exit 0 } else { exit 1 } >> "%PS_SCRIPT%"
echo } catch { exit 2 } >> "%PS_SCRIPT%"

powershell -NoProfile -ExecutionPolicy Bypass -File "%PS_SCRIPT%"
set HEALTH=%ERRORLEVEL%
del "%PS_SCRIPT%" >nul 2>&1

if %HEALTH%==0 (
    exit /b 0
)

echo [%DATE% %TIME%] WATCHDOG: Bot health FAILED (code=%HEALTH%). Pulling latest code & force restarting... >> "%LOG%"
git checkout conv_state.json >nul 2>&1
git pull origin main >> "%LOG%" 2>&1

powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort 8085,8089 -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }" >nul 2>&1
taskkill /f /im python.exe >nul 2>&1
taskkill /f /im pythonw.exe >nul 2>&1
timeout /t 2 /nobreak >nul
start "" "C:\Program Files\Python311\pythonw.exe" "C:\Users\admin\.gemini\antigravity-ide\scratch\psa-telegram-notifier\notifier.py"
echo [%DATE% %TIME%] WATCHDOG: Notifier restarted successfully. >> "%LOG%"
