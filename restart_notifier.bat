@echo off
:: PSA Telegram Notifier - Hard Restart Script
:: Kills ALL pythonw.exe instances running notifier.py, then starts fresh.
:: Runs every day at 00:03 via Windows Task Scheduler.

echo [%DATE% %TIME%] Stopping all notifier processes...

:: Kill any pythonw.exe running notifier.py (force kill)
taskkill /f /im pythonw.exe >nul 2>&1

:: Wait 3 seconds for processes to fully terminate
timeout /t 3 /nobreak >nul

echo [%DATE% %TIME%] Starting fresh notifier process...

:: Start notifier as windowless background process
start "" "C:\Program Files\Python311\pythonw.exe" "C:\Users\admin\.gemini\antigravity-ide\scratch\psa-telegram-notifier\notifier.py"

echo [%DATE% %TIME%] Notifier restarted successfully.
