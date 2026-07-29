# PowerShell script to register PSA Telegram Notifier Watchdog as a permanent Windows Scheduled Task
# Task runs at Windows startup and checks every 5 minutes to ensure Watchdog is ALWAYS running.

$TaskName = "PSATelegramNotifierWatchdog"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$WatchdogScript = Join-Path $ScriptDir "start_notifier.ps1"

Write-Host "Registering permanent Windows Scheduled Task: $TaskName..."

# Unregister existing task if it exists
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

$Action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-ExecutionPolicy Bypass -WindowStyle Hidden -File `"$WatchdogScript`""

# Trigger 1: At system startup
$TriggerStartup = New-ScheduledTaskTrigger -AtStartup

# Trigger 2: Repeat every 5 minutes indefinitely
$TriggerRepeat = New-ScheduledTaskTrigger -At (Get-Date) -Once -RepetitionInterval (New-TimeSpan -Minutes 5)

$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit (New-TimeSpan -Hours 0)  # Infinite execution limit

$Principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest

try {
    Register-ScheduledTask `
        -TaskName $TaskName `
        -Action $Action `
        -Trigger @($TriggerStartup, $TriggerRepeat) `
        -Settings $Settings `
        -Principal $Principal `
        -ErrorAction Stop | Out-Null
    Write-Host "✅ Scheduled Task '$TaskName' successfully registered with SYSTEM privileges (runs 24/7 on boot)."
} catch {
    # Fallback to current user if SYSTEM privileges require elevation
    try {
        $CurrentUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
        $UserPrincipal = New-ScheduledTaskPrincipal -UserId $CurrentUser -RunLevel Highest
        Register-ScheduledTask `
            -TaskName $TaskName `
            -Action $Action `
            -Trigger @($TriggerStartup, $TriggerRepeat) `
            -Settings $Settings `
            -Principal $UserPrincipal `
            -ErrorAction Stop | Out-Null
        Write-Host "✅ Scheduled Task '$TaskName' successfully registered under current user ($CurrentUser)."
    } catch {
        Write-Host "❌ Failed to register scheduled task: $_"
    }
}
