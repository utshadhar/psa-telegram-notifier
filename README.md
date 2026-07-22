# PSA Telegram Notifier (Zero-Dependency)

A lightweight background monitoring service and REST API built using only Python's standard library. It polls the PSA API for pending Sales Orders (SO) and Collection Orders (CO) and sends periodic summary notifications to Telegram.

## Features
- **Zero Package Installation**: No `pip install` required. Uses only built-in Python modules.
- **Extremely Low Footprint**: Consumes less than 15MB of RAM and under 20KB of disk space.
- **Overnight Active Hours**: Supports running across midnight (e.g., 9:00 AM to 1:00 AM the next day). Automatically queries yesterday's data when checking after midnight.
- **Standard HTTP API**: Web API endpoints for checking health, querying stats, and manually triggering alerts.

---

## Step-by-Step Setup Guide

### Step 1: Install Python
Ensure Python (version 3.6 or higher) is installed on your server.
- **Windows**: Download and install from [python.org](https://www.python.org/downloads/). Ensure you check **"Add Python to PATH"** during installation.
- **Linux (Ubuntu/Debian)**: Usually pre-installed. Otherwise, run:
  ```bash
  sudo apt update && sudo apt install python3 -y
  ```

### Step 2: Set Up Telegram Bot and Chat ID

To send notifications, you need a Telegram Bot and your personal Chat ID:

1. **Create a Telegram Bot**:
   - Open Telegram and search for `@BotFather`.
   - Send the message `/newbot` and follow the prompts to name your bot.
   - `@BotFather` will give you a **Bot Token** (e.g., `123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ`). Copy this.

2. **Get Your Telegram Chat ID**:
   - Search for `@userinfobot` in Telegram and start a chat.
   - It will reply with your **Id** (a number like `987654321`). Copy this.
   - **Crucial**: You must message your new bot (`/start`) before it can send you notifications.

---

### Step 3: Configure the Application

Create a file named `config.json` in the same directory (you can copy the structure from `config.json.example`) and fill in your details:

```json
{
  "telegram_bot_token": "YOUR_TELEGRAM_BOT_TOKEN",
  "telegram_chat_id": "YOUR_TELEGRAM_CHAT_ID",
  "apis": [
    {
      "name": "PSA_Pending_Orders",
      "url_template": "YOUR_PSA_API_URL_TEMPLATE",
      "filter_pending": true
    },
    {
      "name": "SmartSales_Pending_Orders",
      "url_template": "YOUR_SMARTSALES_PENDING_ORDERS_URL_TEMPLATE",
      "filter_pending": false,
      "headers": {
        "Accept": "application/json",
        "Authorization": "Bearer YOUR_BEARER_TOKEN"
      }
    },
    {
      "name": "SmartSales_OBD_Pending",
      "url_template": "YOUR_CEMENT_OBD_PROGRAM_URL_TEMPLATE",
      "filter_pending": false,
      "default_process": "SO",
      "label_so": "OBD",
      "headers": {
        "app-key": "YOUR_APP_KEY"
      }
    },
    {
      "name": "SAP_Contract_Pending",
      "url_template": "YOUR_SAP_CONTRACT_CREATE_URL_TEMPLATE",
      "filter_pending": false,
      "default_process": "CO",
      "label_co": "CON"
    }
  ],
  "monitoring_start_hour": 9,
  "monitoring_end_hour": 1,
  "poll_interval_minutes": 30,
  "server_port": 8080,
  "timezone_offset_hours": 6
}
```

#### Settings Details:
- `telegram_bot_token`: Paste your bot token here.
- `telegram_chat_id`: Paste your Telegram chat ID number here.
- `apis`: A list of API configurations to monitor:
  - `name`: Friendly display name for the API source (e.g. `PSA_Pending_Orders` maps to `PSA Pending Orders Summary` on the Telegram report).
  - `url_template`: The API request URL template (use `{start_date}` and `{end_date}` or `{date}`).
  - `filter_pending`: If `true`, filters items to count only pending records. If `false`, counts all returned items as pending.
  - `headers`: Optional JSON dictionary of custom HTTP request headers (such as `Authorization` or `app-key`).
  - `default_process`: Optional classification override (`"SO"` or `"CO"`). Bypasses standard process checks and forces all records to be handled as the specified type.
  - `label_so` / `label_co`: Optional custom label overrides (e.g. `"OBD"`, `"CON"`) displayed on the totals and server breakdowns instead of the default "Sales Orders (SO)" / "Collection Orders (CO)".
- `monitoring_start_hour`: The hour when monitoring begins (e.g., `9` is 9:00 AM).
- `monitoring_end_hour`: The hour when monitoring ends (e.g., `1` is 1:00 AM next day).
- `poll_interval_minutes`: Time between checks in minutes. It aligns checks to boundary times (e.g. at 30 minutes, checks run exactly at xx:00 and xx:30).
- `server_port`: Port the REST API will run on.
- `timezone_offset_hours`: Timezone offset in hours (default `6` for UTC+6).

---

### Step 4: Run the Application

#### 1. Running in the Foreground (for testing)
Open your terminal (PowerShell/Command Prompt on Windows, Bash on Linux), navigate to the folder, and run:
```bash
python notifier.py
```
You will see output indicating the API server has started and the background monitoring thread is running.

#### 2. Running as a Background Service
To keep the script running when you close your terminal:

- **On Windows (Simple Way)**:
  Create a script named `run_notifier.bat` in the same directory with the following content:
  ```bat
  @echo off
  python "%~dp0notifier.py"
  ```
  You can run this using **Windows Task Scheduler** to trigger "At startup" or "At user log on".

- **On Linux (Using systemd)**:
  Create a service file at `/etc/systemd/system/psa-notifier.service`:
  ```ini
  [Unit]
  Description=PSA Telegram Notifier Service
  After=network.target

  [Service]
  Type=simple
  User=root
  WorkingDirectory=/path/to/psa-telegram-notifier
  ExecStart=/usr/bin/python3 notifier.py
  Restart=always

  [Install]
  WantedBy=multi-user.target
  ```
  Enable and start the service:
  ```bash
  sudo systemctl daemon-reload
  sudo systemctl enable psa-notifier.service
  sudo systemctl start psa-notifier.service
  ```

---

### Deploying to Render.com
Render is a cloud application hosting platform. You can deploy this service to Render's free tier:

1. **Create a GitHub Repository**: Push this code to a public or private GitHub repository.
2. **Create a Render Web Service**:
   - Log into [Render.com](https://render.com) and create a new **Web Service**.
   - Connect your GitHub repository.
   - Choose the **Python** environment.
   - Set the Start Command to: `python notifier.py`
   - Select the **Free** instance type.
3. **Configure Environment Variables**:
   Since `config.json` is not committed to Git, configure settings under the **Environment** tab in Render:
   - `PORT`: `10000` (Render's default port, which the app automatically detects and binds to).
   - `TELEGRAM_BOT_TOKEN`: *Your Telegram Bot Token*
   - `TELEGRAM_CHAT_ID`: *Your Telegram Chat ID*
   - `PSA_API_URL_TEMPLATE`: *Your PSA API template URL*
   - `API_2_URL_TEMPLATE`: *Optional additional monitored API*
   - `API_3_URL_TEMPLATE` / `API_4_URL_TEMPLATE`: *Optional additional monitored APIs*
   - `TIMEZONE_OFFSET_HOURS`: `6` (or your timezone offset)
   
   **Note on Configuration Persistence**:
   Automatic synchronization via the Render API has been disabled to protect your Telegram bot secrets from being overwritten. To permanently change a threshold default, modify it directly in your Render dashboard's **Environment** tab.

### Keeping the Free Service Awake (cron-job.org)
Render's free tier web services spin down (go to sleep) after 15 minutes of inactivity (no incoming HTTP requests). When spun down, the background scheduler thread stops running and scheduled reports will be missed. 

Standard uptime monitors like UptimeRobot are often blocked by Render's edge firewall (returning `403 Forbidden` errors), so the best free alternative is **cron-job.org**, which allows sending a custom User-Agent header.

To keep the service awake 24/7 reliably:
1. Log into [cron-job.org](https://cron-job.org/) and create a free account.
2. Click **Create Cronjob**:
   - **Title**: `PSA Notifier Keep-Awake`
   - **Address**: `https://your-render-subdomain.onrender.com/` (use the **root** URL of your Render service, **NOT** `/trigger`).
   - **Schedule**: Every 5 minutes (to trigger before the 15-minute idle timeout).
3. Scroll down to **Advanced Settings** > **HTTP Headers**:
   - Add a custom header:
     - **Key**: `User-Agent`
     - **Value**: `Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36`
4. Click **Create**. This pings the server disguised as a desktop browser, bypassing edge blocks and keeping the service awake 24/7.

### Clean Up Old UptimeRobot Monitors (Recommended)
Since Render blocks UptimeRobot's standard user-agents (resulting in `403 Forbidden` errors), UptimeRobot will not keep the service awake and will spam your logs with failed request errors. You should delete the old monitor:
1. Log into your [UptimeRobot Dashboard](https://uptimerobot.com/dashboard).
2. Locate the monitor you created for your Render app (e.g. `PSA Notifier Keep-Awake`).
3. Click the **cog/gear icon** (options) or **three dots** next to the monitor.
4. Select **Delete** (or click the trash can icon).
5. Confirm the deletion in the popup.

---

## HTTP REST API Endpoints

Once running, you can interact with the notifier via HTTP (e.g. from a web browser or tools like Postman):

### 1. Health & Config Status
- **URL**: `GET http://localhost:8080/`
- **Description**: Returns the server status, current server time, business date, active hour validation, and configuration check (sensitive credentials are masked).
- **Response Example**:
  ```json
  {
    "status": "online",
    "server_time": "2026-06-21 15:30:00",
    "business_date": "2026-06-21",
    "is_active_monitoring_hour": true,
    "config": {
      "telegram_bot_token_configured": true,
      "telegram_chat_id_configured": true,
      "telegram_bot_token_masked": "123456...",
      "telegram_chat_id_masked": "987...",
      "monitoring_start_hour": 9,
      "monitoring_end_hour": 1,
      "poll_interval_minutes": 30,
      "server_port": 8080,
      "timezone_offset_hours": 6,
      "apis": [
        {
          "name": "PSA_Pending_Orders",
          "url_configured": true,
          "filter_pending": true,
          "default_process": null,
          "headers_configured": false
        },
        {
          "name": "SmartSales_OBD_Pending",
          "url_configured": true,
          "filter_pending": false,
          "default_process": "SO",
          "headers_configured": true
        }
      ]
    }
  }
  ```

### 2. Fetch Live Stats
- **URL**: `GET http://localhost:8080/pending`
- **Description**: Connects to all configured APIs, processes and counts pending transactions, and returns the stats grouped by API in JSON format.
- **Response Example**:
  ```json
  {
    "status": "success",
    "business_date": "2026-06-21",
    "stats": {
      "PSA_Pending_Orders": {
        "server_stats": {
          "1": { "pending_so": 5, "pending_co": 3, "so_ids": ["TX100"], "co_ids": ["PAY200"] }
        },
        "total_pending_so": 5,
        "total_pending_co": 3
      },
      "SmartSales_OBD_Pending": {
        "server_stats": {
          "1": { "pending_so": 2, "pending_co": 0, "so_ids": ["123", "456"], "co_ids": [] }
        },
        "total_pending_so": 2,
        "total_pending_co": 0
      }
    }
  }
  ```

### 3. Manual Notification Trigger
- **URL**: `POST http://localhost:8080/trigger`
- **Description**: Manually triggers a real-time check across all APIs and immediately sends the formatted Telegram notification report.
- **Response Example**:
  ```json
  {
    "status": "success",
    "message": "Notification triggered and sent successfully.",
    "business_date": "2026-06-21",
    "stats": { ... }
  }
  ```

### 4. Webhook Diagnostics & Debugging
- **URL**: `GET http://localhost:8080/debug`
- **Description**: Returns live diagnostics including the Telegram Bot webhook settings on Telegram servers, the raw JSON payload of the last received webhook update, and any authorization or validation errors.
- **Response Example**:
  ```json
  {
    "status": "online",
    "telegram_bot_token_configured": true,
    "telegram_bot_token_masked": "123456...aBcD",
    "expected_chat_id": "987654321",
    "telegram_webhook_info": {
      "ok": true,
      "result": {
        "url": "https://your-domain.com/webhook",
        "pending_update_count": 0,
        "max_connections": 40
      }
    },
    "last_webhook_payload": { ... },
    "last_webhook_error": null
  }
  ```

---

### Interactive Webhook & Long Polling Commands

You can send commands directly to the Telegram bot to toggle checkers, adjust threshold parameters, switch active servers, or inspect features:

### 1. Active Server Switcher
* **`/switch_to_local`**: Sets the active listener to the local server (deletes Render webhook, enabling Local Long Polling).
* **`/switch_to_render`**: Sets the active listener back to Render (registers Render webhook URL and puts Local in Standby).

### 2. Checker Controls (Thresholds & Off Shortcuts)
* **`f1` / `/f1`**: Turn on/configure **PSA Sales Orders (SO)** checker.
  * **`/o1`**: Turn off the PSA SO checker completely.
* **`f2` / `/f2`**: Turn on/configure **PSA Collection Orders (CO)** checker.
  * **`/o2`**: Turn off the PSA CO checker completely.
* **`f3` / `/f3`**: Turn on/configure **SmartSales OBD (API_3)** checker.
  * **`/o3`**: Turn off the SmartSales OBD checker completely.
* **`f4` / `/f4`**: Turn on/configure **Cement Sales Orders (cementapi SO)** checker.
  * **`/o4`**: Turn off the Cement SO checker completely.
* **`f5` / `/f5`**: Turn on/configure **Cement Collection Orders (cementapi CO)** checker.
  * **`/o5`**: Turn off the Cement CO checker completely.
* **`f6` / `/f6`**: Turn on/configure **SAP Contract Pending (contractapi CO)** checker.
  * **`/o6`**: Turn off the SAP Contract checker completely.
* **`f7` / `/f7`**: Turn on/configure **Off-Hours SmartSales OBD Checker** (default 30 min).
  * **`/f7_start`**: Set the start hour for the off-hours window (e.g. `1` for 1 AM).
  * **`/f7_end`**: Set the end hour for the off-hours window (e.g. `8` for 8 AM).
  * **`/f7_user`**: Configure target Usernames/IDs/Phone Numbers for CallMeBot voice alerts.
  * **`/o7`**: Turn off the Off-Hours OBD checker and voice calls completely.
  * **`/f7_test`**: Instantly trigger a test CallMeBot voice alert to targets.
* **`f8` / `/f8`**: Turn on/configure **FreshLPG Sales Orders (freshlpg SO)** checker.
  * **`/o8`**: Turn off the FreshLPG SO checker completely.
* **`f9` / `/f9`**: Turn on/configure **FreshLPG Collection Orders (freshlpg CO)** checker.
  * **`/o9`**: Turn off the FreshLPG CO checker completely.

### 3. Status & Configurations Command
* **`feature` / `/feature`**: The bot replies with a formatted overview listing all commands/functions, their short descriptions, and their current in-memory configurations (e.g., threshold values in minutes, or if they are turned `off`).

### 4. Immediate Summary Reports
* **`status` / `/status` / `report` / `/report`**: Immediately queries all configured APIs and posts the formatted summary report directly to Telegram.

---

## Embedded Logging & Log Rotation (Offline Mode)

- **Online Mode (Render)**: All output is printed to stdout/stderr and collected by the Render console log viewer.
- **Offline Mode (Local)**: The application automatically creates a `logs/` directory in the project root.
  - All operations are logged to daily log reports named `logs/YYYY-MM-DD.log`.
  - **3-Day Auto-Rotation**: To prevent the disk from filling up, the bot automatically checks the `logs/` directory every minute and deletes any log files older than 3 days.

---

## Verifying Code Correctness (Unit Tests)

You can run automated offline unit tests to confirm the date and parser math:
```bash
python -m unittest test_notifier.py
```
This tests date calculation across midnight, duplicate order parsing, server grouping, and Telegram text formatting without hitting the real APIs.
