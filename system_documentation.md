# PSA Telegram Notifier: Comprehensive A to Z System Documentation

This document explains the complete architecture, background workflows, commands, and local control endpoints of the **PSA Telegram Notifier**.

---

## 1. System Architecture

```mermaid
flowchart TD
    subgraph Telegram Servers
        TC[User Client] <--> TB[Telegram Bot API]
    end

    subgraph Local PC (Offline Mode)
        subgraph Watchdog Service
            WD[start_notifier.ps1]
        end
        
        subgraph Notifier App (python.exe)
            LP[Long Polling Thread]
            MS[Monitoring Scheduler Thread]
            AS[Aging Alert Scheduler Thread]
            FL[Takeover / Failover Thread]
            HS[Local HTTP Server :8080]
        end
        
        WD -- Restarts if dead --> Notifier App
        LP -- Query updates --> TB
        LP -- Commands / Buttons --> HS
        MS -- Periodic checks --> API_Sources
        AS -- Tracks aging transactions --> API_Sources
        HS -- GET /trigger --> MS
        HS -- GET /stop_render --> Render_API
        HS -- GET /resume_render --> Render_API
    end

    subgraph Render.com (Online Mode)
        RS[Render Web Service]
    end

    subgraph Render_API [Render.com API]
        R_API[suspend / resume endpoints]
    end

    subgraph Data Sources
        API_Sources[(1. PSA API<br/>2. SmartSales SO/CO<br/>3. SmartSales OBD<br/>4. SAP Contract<br/>5. FreshLPG)]
    end

    RS -- Webhook Requests --> TB
    MS -- Outbound HTTPS --> TB
    AS -- Outbound HTTPS --> TB
    FL -- Swaps Webhook / Standby --> TB
```

---

## 2. A to Z Background Workflows

### A. Bot Setup & Environment Modes
* **Watchdog Background Loop**: The Windows Task Scheduler runs [start_notifier.ps1](file:///C:/Users/admin/.gemini/antigravity-ide/scratch/psa-telegram-notifier/start_notifier.ps1) as `SYSTEM` in the background. Every 15 seconds, it queries for any active `python.exe` process running `notifier.py`. If it crashes or terminates, the watchdog restarts it automatically.
* **Environment Identification**: When `notifier.py` boots, it checks the environment variables:
  - If the `RENDER` environment variable is defined, it runs in **Render (Webhook) Mode**.
  - Otherwise, it runs in **Local (Long Polling) Mode**.
* **Local Webhook Cleansing**: To ensure the bot doesn't send messages to Render's dormant endpoint, the Local boot script automatically calls `deleteWebhook` on Telegram. This switches the Telegram Bot's delivery method to long-polling immediately.

### B. Background Schedulers (Behind-the-Scenes Calculations)
1. **Periodic Check Scheduler (`scheduler_loop`)**: Runs every `poll_interval_minutes` (default 30 mins) aligned to clock boundary times (e.g. xx:00 and xx:30). It triggers a parallel check of all active APIs via a `ThreadPoolExecutor` and dispatches the summary report.
2. **Takeover and Failover Loop (`takeover_failover_loop`)**: Runs every 15 seconds. If running on Local, it queries the Render server health endpoint. If Render fails, Local takes over active monitoring. If Render recovers, Local yields control and registers Render's webhook back.
3. **Heartbeat Loop (`local_heartbeat_ping_loop`)**: Runs on Local every 30 seconds. It pings the Render server `/heartbeat` endpoint to let Render know the Local machine is alive and active.
4. **Log Rotation**: In Local mode, the application auto-deletes log files older than 3 days inside the `logs/` directory to prevent disk bloating.

---

## 3. Interactive Bot Commands & Configuration (A to Z Guide)

When you send a message to the bot, it is processed as follows:
* **The Polling/Webhook Flow**: The text message is received by the script. If the message sender is your authorized `telegram_chat_id`, the command is parsed and handled.
* **Configuration States**: When you trigger a command to change a threshold, the bot enters a **Conversational State** (e.g. `AWAITING_VAL_F1`) and prompts you for input. Once you send the value, it immediately updates **both** the temporary threshold and the permanent default threshold, saving it to [config.json](file:///C:/Users/admin/.gemini/antigravity-ide/scratch/psa-telegram-notifier/config.json).

### Detailed Command Directory:

| Command | Action / Behind the Scenes | User Interaction | Bot Response |
| :--- | :--- | :--- | :--- |
| `/feature` | Reads the current memory state of all variables and formats a summary. | User types `/feature` or clicks button. | Returns a list of all features, their status (`on`/`off`), current values, and default values. |
| `/status` / `/report` | Instantly runs the parallel fetching executor across all 5 API endpoints. | User types command or clicks button. | Sends the full Markdown summary report (totals and server breakdowns) to the chat. |
| `/f1` | Triggers threshold adjustment for **PSA Sales Orders (SO)**. Turns checker **ON**. | User types `/f1`. | Prompts: `"Please enter the value for psa_so_pending_threshold_minutes:"`. User sends a number, and both default & session variables are updated. |
| `/o1` | Sets the PSA SO threshold and its default to `0`. Turns checker **OFF**. | User types `/o1`. | `"psa_so_pending_threshold_minutes checker is off."` |
| `/f2` | Triggers threshold adjustment for **PSA Collection Orders (CO)**. Turns checker **ON**. | User types `/f2`. | Prompts for threshold value. User sends a number, and both default & session variables are updated. |
| `/o2` | Sets the PSA CO threshold and its default to `0`. Turns checker **OFF**. | User types `/o2`. | `"psa_co_pending_threshold_minutes checker is off."` |
| `/f3` | Triggers threshold adjustment for **SmartSales OBD Pending**. Turns checker **ON**. | User types `/f3`. | Prompts for threshold value. User sends a number, and both default & session variables are updated. |
| `/o3` | Sets the OBD threshold and its default to `0`. Turns checker **OFF**. | User types `/o3`. | `"Smartsales_obd_pending_threshold_minutes checker is off."` |
| `/f4` | Triggers threshold adjustment for **Cement SO Checker**. Turns checker **ON**. | User types `/f4`. | Prompts for threshold value. User sends a number, and both default & session variables are updated. |
| `/o4` | Sets the Cement SO threshold and its default to `0`. Turns checker **OFF**. | User types `/o4`. | `"Smartsales_so_pending_threshold_minutes checker is off."` |
| `/f5` | Triggers threshold adjustment for **Cement CO Checker**. Turns checker **ON**. | User types `/f5`. | Prompts for threshold value. User sends a number, and both default & session variables are updated. |
| `/o5` | Sets the Cement CO threshold and its default to `0`. Turns checker **OFF**. | User types `/o5`. | `"Smartsales_co_pending_threshold_minutes checker is off."` |
| `/f6` | Triggers threshold adjustment for **SAP Contract Checker**. Turns checker **ON**. | User types `/f6`. | Prompts for threshold value. User sends a number, and both default & session variables are updated. |
| `/o6` | Sets the SAP Contract threshold and its default to `0`. Turns checker **OFF**. | User types `/o6`. | `"SAP_Contract_pending_threshold_minutes checker is off."` |
| `/f7` | Triggers threshold adjustment for **Off-Hours SmartSales OBD Checker**. Turns checker **ON**. | User types `/f7`. | Prompts for threshold value. User sends a number, and both default & session variables are updated. |
| `/o7` | Turns Off-Hours OBD checker and voice calls **OFF** (sets both to `0` / `none`). | User types `/o7`. | `"SMARTSALES_OBD_OFFHOURS_THRESHOLD_MINUTES checker is off."` |
| `/f7_start` | Configures the starting hour for the off-hours check (midnight boundary). | User types `/f7_start`. | Prompts: `"Please enter the value for in which hour I want to start f7:"`. User replies with hour (0-24). |
| `/f7_end` | Configures the ending hour for the off-hours check. | User types `/f7_end`. | Prompts: `"Please enter the value for in which hour I want to end f7:"`. User replies with hour (0-24). |
| `/f7_user` | Configures target telegram usernames, IDs, or CallMeBot phone numbers for voice calls. | User types `/f7_user`. | Prompts: `"Please enter the value for CallMeBot target users/numbers:"`. User replies with target config. |
| `/f7_test` | Instantly triggers a test CallMeBot voice alert to the configured targets. | User types `/f7_test`. | Sends TTS text payload to CallMeBot API, returning the call outcome (e.g. `call queued` or `line busy`). |
| `/f8` | Triggers threshold adjustment for **FreshLPG Sales Orders (SO)**. Turns checker **ON**. | User types `/f8`. | Prompts for threshold value. User sends a number, and both default & session variables are updated. |
| `/o8` | Sets the FreshLPG SO threshold and its default to `0`. Turns checker **OFF**. | User types `/o8`. | `"freshlpg_so_pending_threshold_minutes checker is off."` |
| `/f9` | Triggers threshold adjustment for **FreshLPG Collection Orders (CO)**. Turns checker **ON**. | User types `/f9`. | Prompts for threshold value. User sends a number, and both default & session variables are updated. |
| `/o9` | Sets the FreshLPG CO threshold and its default to `0`. Turns checker **OFF**. | User types `/o9`. | `"freshlpg_co_pending_threshold_minutes checker is off."` |

---

## 4. HTTP Management & Control Endpoints

You can interact with the local HTTP server from any browser or HTTP client. By default, the server listens on **all interfaces (`0.0.0.0`) on port `8080`**, allowing other computers on the same network to access it.

### A. Accessing from Other PCs on the Same Network
To access these endpoints from another PC on the same network:
1. Find your host machine's private local IP address (e.g., `192.168.1.100`).
2. Run this PowerShell command on the host PC as **Administrator** to open port `8080` in Windows Firewall:
   ```powershell
   New-NetFirewallRule -DisplayName "PSA Notifier Local Port" -Direction Inbound -LocalPort 8080 -Protocol TCP -Action Allow
   ```
3. Open a browser on the other PC and visit: `http://<host-ip-address>:8080/trigger?force=true`.

### B. Endpoint Directory

* **Health Check**: `GET http://localhost:8080/`
  * Returns the server status, active hour validation, and configuration check.
* **Force Check Trigger (Foreground Run)**: `GET http://localhost:8080/trigger?force=true`
  * Runs a real-time check across all 5 APIs (including FreshLPG) immediately and sends the summary report to Telegram.
* **Suspend Render Web Service**: `GET http://localhost:8080/stop_render`
  * Uses your RENDER API Key and Service ID to send a suspension request to Render, immediately **pausing the Render web service**.
* **Resume Render Web Service**: `GET http://localhost:8080/resume_render`
  * Sends a resume request to Render, **waking up the Render service**.

---

## 5. Local Scripts Directory

* **[register_task.bat](file:///C:/Users/admin/.gemini/antigravity-ide/scratch/psa-telegram-notifier/register_task.bat)**: Registers the powershell watchdog script as a Windows Scheduled Task under the `SYSTEM` account to run automatically at startup.
* **[stop_local_notifier.bat](file:///C:/Users/admin/.gemini/antigravity-ide/scratch/psa-telegram-notifier/stop_local_notifier.bat)**: Disables the watchdog task and terminates all local `python` and `powershell` processes running the notifier.
* **[stop_render.ps1](file:///C:/Users/admin/.gemini/antigravity-ide/scratch/psa-telegram-notifier/stop_render.ps1)**: A standalone powershell command script to suspend the Render service using the Render API.
* **[resume_render.ps1](file:///C:/Users/admin/.gemini/antigravity-ide/scratch/psa-telegram-notifier/resume_render.ps1)**: A standalone powershell command script to resume/unsuspend the Render service.
* **[push_to_github.ps1](file:///C:/Users/admin/.gemini/antigravity-ide/scratch/psa-telegram-notifier/push_to_github.ps1)**: Interactive git helper script to add all changes, commit, and force-push them using your local Git credentials/environment.
