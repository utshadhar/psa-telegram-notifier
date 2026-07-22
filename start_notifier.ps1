# Windows PowerShell Watchdog script for PSA Telegram Notifier
# Place this script in C:\psa-notifier\start_notifier.ps1

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$NotifierScript = Join-Path $ScriptDir "notifier.py"
$LogPath = Join-Path $ScriptDir "watchdog.log"

function Write-Log($Message) {
    $Timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $LogMessage = "[$Timestamp] $Message"
    Write-Output $LogMessage
    Add-Content -Path $LogPath -Value $LogMessage -ErrorAction SilentlyContinue
}

Write-Log "Watchdog script started."

# Loop indefinitely
while ($true) {
    # Check if network is available (Ping Google DNS)
    $NetworkAvailable = Test-Connection -ComputerName 8.8.8.8 -Count 1 -Quiet

    if (-not $NetworkAvailable) {
        Write-Log "Network is unavailable. Waiting for connection..."
        Start-Sleep -Seconds 10
        continue
    }

    # Check if notifier.py is running
    $Processes = Get-CimInstance Win32_Process -Filter "Name like '%python%'" -ErrorAction SilentlyContinue | Where-Object {
        $_.CommandLine -like "*notifier.py*"
    }
    if ($null -eq $Processes) {
        $Processes = Get-WmiObject Win32_Process -Filter "Name like '%python%'" -ErrorAction SilentlyContinue | Where-Object {
            $_.CommandLine -like "*notifier.py*"
        }
    }

    # Handle multiple processes to prevent duplicate notifications
    if ($Processes -and $Processes.Count -gt 1) {
        Write-Log "Multiple notifier processes detected ($($Processes.Count)). Killing all and restarting one clean instance..."
        foreach ($P in $Processes) {
            try {
                Stop-Process -Id $P.ProcessId -Force -ErrorAction SilentlyContinue
            }
            catch {}
        }
        $Processes = $null
    }

    if (-not $Processes) {
        Write-Log "Notifier process is NOT running. Starting notifier..."
        try {
            # Start process in background
            Start-Process -FilePath "python" -ArgumentList $NotifierScript -WindowStyle Hidden -WorkingDirectory $ScriptDir
            Write-Log "Notifier process started successfully."
        }
        catch {
            Write-Log "Failed to start notifier process: $_"
        }
    }

    # Check status every 15 seconds
    Start-Sleep -Seconds 15
}
