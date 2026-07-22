@echo off
:: Check for Administrator privileges
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo Requesting administrative privileges...
    powershell -Command "Start-Process -FilePath '%0' -Verb RunAs"
    exit /b
)

set SCRIPT_DIR=%~dp0
set PS_SCRIPT=%SCRIPT_DIR%start_notifier.ps1

echo Creating Windows Scheduled Task for PSA Telegram Notifier...
schtasks /create /tn "PSATelegramNotifierWatchdog" /tr "powershell.exe -ExecutionPolicy Bypass -WindowStyle Hidden -File \"%PS_SCRIPT%\"" /sc onstart /ru "SYSTEM" /f

if %errorLevel% equ 0 (
    echo Task created successfully! The notifier watchdog will run automatically at startup.
) else (
    echo Failed to create the scheduled task.
)
pause
