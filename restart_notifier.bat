@echo off
:: PSA Telegram Notifier - Hard Restart Script
:: Pulls latest code from GitHub, kills python processes, and restarts notifier.py fresh.
:: Runs every day at 12:03 AM via Windows Task Scheduler.

cd /d "C:\Users\admin\.gemini\antigravity-ide\scratch\psa-telegram-notifier"

echo [%DATE% %TIME%] Pulling latest updates from GitHub...
git checkout conv_state.json >nul 2>&1
git pull origin main >nul 2>&1

echo [%DATE% %TIME%] Stopping ALL python processes (including zombies)...
taskkill /f /im python.exe >nul 2>&1
taskkill /f /im pythonw.exe >nul 2>&1

timeout /t 3 /nobreak >nul

echo [%DATE% %TIME%] Starting fresh notifier process...
start "" "C:\Program Files\Python311\pythonw.exe" "C:\Users\admin\.gemini\antigravity-ide\scratch\psa-telegram-notifier\notifier.py"

echo [%DATE% %TIME%] Notifier restarted successfully.
