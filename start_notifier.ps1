# Windows PowerShell Watchdog script for PSA Telegram Notifier
# Auto-pulls latest code from GitHub and restarts notifier on new commits
# Sends Telegram notification on successful auto-update

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$NotifierScript = Join-Path $ScriptDir "notifier.py"
$LogPath = Join-Path $ScriptDir "watchdog.log"

# Find git executable dynamically
$GitExe = "C:\Program Files\Git\cmd\git.exe"
if (-not (Test-Path $GitExe)) {
    $GitCommand = Get-Command git -ErrorAction SilentlyContinue
    if ($GitCommand) {
        $GitExe = $GitCommand.Source
    }
}

function Write-Log($Message) {
    $Timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $LogMessage = "[$Timestamp] $Message"
    Write-Output $LogMessage
    Add-Content -Path $LogPath -Value $LogMessage -ErrorAction SilentlyContinue
}

function Send-TelegramMessage($Text) {
    # Dynamically read token and chat ID from config.json
    $ConfigPath = Join-Path $ScriptDir "config.json"
    if (Test-Path $ConfigPath) {
        try {
            $Config = Get-Content -Raw -Path $ConfigPath | ConvertFrom-Json
            $TelegramToken = $Config.telegram_bot_token
            $TelegramChatId = $Config.telegram_chat_id
            
            if ($TelegramToken -and $TelegramChatId -and -not ($TelegramToken -like "*YOUR_*") -and -not ($TelegramChatId -like "*YOUR_*")) {
                $Url = "https://api.telegram.org/bot$TelegramToken/sendMessage"
                $Body = @{ chat_id = $TelegramChatId; text = $Text }
                Invoke-RestMethod -Uri $Url -Method Post -Body $Body -ErrorAction SilentlyContinue | Out-Null
            }
        }
        catch { <# Silently ignore #> }
    }
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
        $PythonExe = "C:\Program Files\Python311\python.exe"
        if (-not (Test-Path $PythonExe)) {
            $PythonExe = (Get-Command python -ErrorAction SilentlyContinue).Source
        }
        if (-not $PythonExe) {
            $PythonExe = "python"
        }
        Start-Process -FilePath $PythonExe -ArgumentList $NotifierScript -WindowStyle Hidden -WorkingDirectory $ScriptDir
        Write-Log "Notifier process started successfully."
    }
    catch {
        Write-Log "Failed to start notifier process: $_"
    }
}


# ---- Single-instance lock (prevents duplicate watchdogs) ----
$MutexName = "Global\PSATelegramNotifierWatchdog_V2"
$Mutex = New-Object System.Threading.Mutex($false, $MutexName)
$GotLock = $Mutex.WaitOne(0, $false)
if (-not $GotLock) {
    Write-Output "Another watchdog instance is already running. Exiting."
    exit 0
}

Write-Log "Watchdog script started."


# Counter to track when to do a git check (every 1 minute = 4 cycles of 15s)
$GitCheckCounter = 0
$GitCheckInterval = 4  # 4 x 15s = 1 minute

# Loop indefinitely
while ($true) {
    # ---- Notifier Process & HTTP Health Check ----
    $IsHealthy = $false
    foreach ($P in @(8085, 8080, 8086, 8087, 8088)) {
        try {
            $HealthReq = (Invoke-WebRequest -Uri "http://localhost:$P/" -TimeoutSec 5 -UseBasicParsing -ErrorAction Stop).Content | ConvertFrom-Json
            if ($HealthReq.status -eq "online") {
                $IsHealthy = $true
                break
            }
        } catch {}
    }

    if (-not $IsHealthy) {
        $Processes = Get-CimInstance Win32_Process -Filter "Name like '%python%'" -ErrorAction SilentlyContinue | Where-Object {
            $_.CommandLine -like "*notifier.py*"
        }
        if ($Processes -and @($Processes).Count -gt 1) {
            Write-Log "Multiple notifier processes detected ($(@($Processes).Count)). Killing all and restarting one clean instance..."
            Stop-Notifier
            $Processes = $null
        }

        if (-not $Processes -or @($Processes).Count -eq 0) {
            Write-Log "Notifier process is NOT running or unresponsive. Starting notifier..."
            Stop-Notifier
            Start-Notifier
            Start-Sleep -Seconds 8  # Give notifier time to bind port before next loop
        }
    }

    # ---- Network Check (only for git pull) ----
    $NetworkAvailable = $false
    try {
        $ConfigPath = Join-Path $ScriptDir "config.json"
        if (Test-Path $ConfigPath) {
            $Config = Get-Content -Raw -Path $ConfigPath | ConvertFrom-Json
            $TelegramToken = $Config.telegram_bot_token
            if ($TelegramToken -and -not ($TelegramToken -like "*YOUR_*")) {
                $Url = "https://api.telegram.org/bot$TelegramToken/getMe"
                $Res = Invoke-RestMethod -Uri $Url -TimeoutSec 5 -ErrorAction Stop
                if ($Res.ok) {
                    $NetworkAvailable = $true
                }

                # Check if there are pending Telegram updates waiting on server (stalled long polling detector)
                $WebhookInfoUrl = "https://api.telegram.org/bot$TelegramToken/getWebhookInfo"
                $WebhookRes = Invoke-RestMethod -Uri $WebhookInfoUrl -TimeoutSec 5 -ErrorAction SilentlyContinue
                if ($WebhookRes -and $WebhookRes.ok -and $WebhookRes.result.pending_update_count -gt 0) {
                    $PendingCount = $WebhookRes.result.pending_update_count
                    Write-Log "Pending Telegram updates detected on server ($PendingCount). Restarting notifier process to process queue..."
                    Stop-Notifier
                    Start-Notifier
                    Start-Sleep -Seconds 8
                }
            }
        }
    } catch {}

    if (-not $NetworkAvailable) {
        $NetworkAvailable = Test-Connection -ComputerName github.com -Count 1 -Quiet
        if (-not $NetworkAvailable) {
            $NetworkAvailable = Test-Connection -ComputerName 8.8.8.8 -Count 1 -Quiet
        }
    }

    if (-not $NetworkAvailable) {
        Write-Log "Network is unavailable. Git check skipped."
        Start-Sleep -Seconds 15
        continue
    }

    # ---- Git Auto-Pull Check (every 1 minute) ----
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
                    # Get commit details for notification
                    $CommitMsg    = & $GitExe -C $ScriptDir log origin/main -1 --pretty=format:"%s" 2>$null
                    $CommitAuthor = & $GitExe -C $ScriptDir log origin/main -1 --pretty=format:"%an" 2>$null
                    $CommitTime   = & $GitExe -C $ScriptDir log origin/main -1 --pretty=format:"%cr" 2>$null
                    $ShortHash    = $RemoteHead.Substring(0,7)

                    Write-Log "New version detected on GitHub! Commit: $ShortHash - $CommitMsg"

                    # Stop running notifier
                    Stop-Notifier

                    # Pull latest changes (force overwrite local)
                    & $GitExe -C $ScriptDir reset --hard origin/main 2>$null
                    & $GitExe -C $ScriptDir pull origin main --ff-only 2>$null

                    Write-Log "Git pull complete (local: $ShortHash). Restarting notifier..."
                    Start-Sleep -Seconds 2
                    Start-Notifier

                    # Send Telegram confirmation
                    $CommitLine = "Commit: $ShortHash"
                    $Msg = "Update: Local Notifier Auto-Updated!" + "`n`n" +
                           "New version pulled from GitHub" + "`n" +
                           $CommitLine + "`n" +
                           "Message: " + $CommitMsg + "`n" +
                           "Author: " + $CommitAuthor + "`n" +
                           "Pushed: " + $CommitTime + "`n`n" +
                           "Notifier restarted with new code."
                    Send-TelegramMessage $Msg
                    Write-Log "Telegram update notification sent."

                    Start-Sleep -Seconds 13  # Skip rest of sleep cycle
                    continue
                }
            }
            catch {
                Write-Log "Git check failed: $_"
            }
        }
    }

    # Check status every 15 seconds
    Start-Sleep -Seconds 15
}
