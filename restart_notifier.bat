@echo off
:: PSA Telegram Notifier - Hard Restart Script
:: Kills ALL python/pythonw processes and restarts notifier.py fresh.
:: Runs every day at 00:15 via Windows Task Scheduler.

echo [%DATE% %TIME%] Stopping ALL python processes (including zombies)...

:: Kill all python/pythonw processes including SYSTEM-owned zombies
taskkill /f /im python.exe >nul 2>&1
taskkill /f /im pythonw.exe >nul 2>&1

:: Wait 3 seconds for all sockets to release (TIME_WAIT, CLOSE_WAIT)
timeout /t 3 /nobreak >nul

echo [%DATE% %TIME%] Starting fresh notifier process...

:: Start notifier as windowless background process
start "" "C:\Program Files\Python311\pythonw.exe" "C:\Users\admin\.gemini\antigravity-ide\scratch\psa-telegram-notifier\notifier.py"

echo [%DATE% %TIME%] Notifier restarted successfully.
