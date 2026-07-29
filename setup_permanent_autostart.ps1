# Permanent 24/7 Autostart Installer for PSA Telegram Notifier
# Ensures start_notifier.ps1 runs automatically on Windows boot & user login, completely silent in background.

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$WatchdogScript = Join-Path $ScriptDir "start_notifier.ps1"

# 1. Create Silent VBScript Launcher in Windows Startup Folder
$StartupFolder = [Environment]::GetFolderPath("Startup")
$VbsPath = Join-Path $StartupFolder "StartNotifierWatchdog.vbs"

$VbsContent = "Set WshShell = CreateObject(`"WScript.Shell`")`nWshShell.Run `"powershell.exe -ExecutionPolicy Bypass -WindowStyle Hidden -File `"`"$WatchdogScript`"`"`", 0, False"

$VbsContent | Set-Content -Path $VbsPath -Encoding ASCII
Write-Host "Created Windows Startup Launcher: $VbsPath"

# 2. Also register User Scheduled Task (without requiring Admin elevation)
$TaskName = "PSATelegramNotifierWatchdog"
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

try {
    $Action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-ExecutionPolicy Bypass -WindowStyle Hidden -File `"$WatchdogScript`""
    $Trigger = New-ScheduledTaskTrigger -AtLogOn
    $Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable
    
    Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -ErrorAction Stop | Out-Null
    Write-Host "Created User Scheduled Task: $TaskName"
} catch {
    Write-Host "Windows Startup folder VBScript will handle autostart."
}

# 3. Launch watchdog detached via WMI so it is immune to parent process job cleanup
Write-Host "Launching detached watchdog process right now..."
$Cmd = "powershell.exe -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$WatchdogScript`""
wmic process call create "$Cmd" | Out-Null
Start-Sleep -Seconds 3
Write-Host "Permanent Autostart Setup Complete!"
