@echo off
:: Check for Administrator privileges
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo Requesting administrative privileges...
    powershell -Command "Start-Process -FilePath '%0' -Verb RunAs"
    exit /b
)

echo =======================================================
echo Stopping PSA Telegram Notifier Local Deploy Completely
echo =======================================================

echo 1. Stopping and disabling Windows Scheduled Task...
schtasks /end /tn "PSATelegramNotifierWatchdog" >nul 2>&1
schtasks /change /tn "PSATelegramNotifierWatchdog" /disable >nul 2>&1

echo 2. Terminating python processes running notifier.py...
powershell -Command "Get-CimInstance Win32_Process -Filter \"Name like '%%python%%'\" | Where-Object { $_.CommandLine -like '*notifier.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"

echo 3. Terminating powershell watchdog processes running start_notifier.ps1...
powershell -Command "Get-CimInstance Win32_Process -Filter \"Name like '%%powershell%%'\" | Where-Object { $_.CommandLine -like '*start_notifier.ps1*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"

echo Done! The Local notifier and watchdog have been completely shut down.
pause
