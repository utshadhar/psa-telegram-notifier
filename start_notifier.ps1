# Windows PowerShell Watchdog script for PSA Telegram Notifier
# Auto-pulls latest code from GitHub and restarts notifier on new commits

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$NotifierScript = Join-Path $ScriptDir "notifier.py"
$LogPath = Join-Path $ScriptDir "watchdog.log"
$GitExe = "C:\Program Files\Git\cmd\git.exe"

function Write-Log($Message) {
    $Timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $LogMessage = "[$Timestamp] $Message"
    Write-Output $LogMessage
    Add-Content -Path $LogPath -Value $LogMessage -ErrorAction SilentlyContinue
}

function Stop-Notifier {
    $Processes = Get-CimInstance Win32_Process -Filter "Name like '%python%'" -ErrorAction SilentlyContinue | Where-Object {
        $_.CommandLine -like "*notifier.py*"
    }
    foreach ($P in $Processes) {
        try { Stop-Process -Id $P.ProcessId -Force -ErrorAction SilentlyContinue } catch {}
    }
}

function Start-Notifier {
    try {
        Start-Process -FilePath "python" -ArgumentList $NotifierScript -WindowStyle Hidden -WorkingDirectory $ScriptDir
        Write-Log "Notifier process started successfully."
    }
    catch {
        Write-Log "Failed to start notifier process: $_"
    }
}

Write-Log "Watchdog script started."

# Counter to track when to do a git check (every 5 minutes = 20 cycles of 15s)
$GitCheckCounter = 0
$GitCheckInterval = 20  # 20 x 15s = 5 minutes

# Loop indefinitely
while ($true) {
    # Check if network is available (Ping Google DNS)
    $NetworkAvailable = Test-Connection -ComputerName 8.8.8.8 -Count 1 -Quiet

    if (-not $NetworkAvailable) {
        Write-Log "Network is unavailable. Waiting for connection..."
        Start-Sleep -Seconds 10
        continue
    }

    # ---- Git Auto-Pull Check (every 5 minutes) ----
    $GitCheckCounter++
    if ($GitCheckCounter -ge $GitCheckInterval) {
        $GitCheckCounter = 0

        if (Test-Path (Join-Path $ScriptDir ".git")) {
            try {
                # Fetch latest from origin silently
                & $GitExe -C $ScriptDir fetch origin --quiet 2>$null

                # Compare local HEAD vs remote main
                $LocalHead  = & $GitExe -C $ScriptDir rev-parse HEAD 2>$null
                $RemoteHead = & $GitExe -C $ScriptDir rev-parse origin/main 2>$null

                if ($LocalHead -and $RemoteHead -and ($LocalHead -ne $RemoteHead)) {
                    Write-Log "New version detected on GitHub (remote: $($RemoteHead.Substring(0,7))). Pulling and restarting..."

                    # Stop running notifier
                    Stop-Notifier

                    # Pull latest changes (force overwrite local)
                    & $GitExe -C $ScriptDir reset --hard origin/main 2>$null
                    & $GitExe -C $ScriptDir pull origin main --ff-only 2>$null

                    Write-Log "Git pull complete. Restarting notifier with new code..."
                    Start-Sleep -Seconds 2
                    Start-Notifier
                    Start-Sleep -Seconds 13  # Skip the rest of the sleep cycle
                    continue
                }
            }
            catch {
                Write-Log "Git check failed: $_"
            }
        }
    }

    # ---- Notifier Process Check ----
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
            try { Stop-Process -Id $P.ProcessId -Force -ErrorAction SilentlyContinue } catch {}
        }
        $Processes = $null
    }

    if (-not $Processes) {
        Write-Log "Notifier process is NOT running. Starting notifier..."
        Start-Notifier
    }

    # Check status every 15 seconds
    Start-Sleep -Seconds 15
}
