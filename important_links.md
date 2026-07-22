# Important Links

Below are the key links for monitoring and triggering the PSA Telegram Notifier:

### 1. Manual Alert Trigger Link (Render.com)
Use this URL to manually trigger a data check and Telegram notification dispatch immediately (bypassing the business-hours check):
- **URL**: [https://psa-telegram-notifier.onrender.com/trigger?force=true](https://psa-telegram-notifier.onrender.com/trigger?force=true)

### 2. Service Keep-Awake Dashboard (cron-job.org)
This service pings your application every 5 minutes with a custom User-Agent to keep the Render free tier awake 24/7:
- **URL**: [console.cron-job.org](https://console.cron-job.org/)

### 3. Notifier Main Status Page (Render.com)
Use this URL to check the health status, server time, business date, and configuration correctness:
- **URL**: [https://psa-telegram-notifier.onrender.com/](https://psa-telegram-notifier.onrender.com/)

### 4. Notifier Debug & Webhook Diagnostics Page (Render.com)
Use this URL to inspect live Telegram webhook configurations, raw message payloads, and error logs:
- **URL**: [https://psa-telegram-notifier.onrender.com/debug](https://psa-telegram-notifier.onrender.com/debug)

### 5. Old Monitor Dashboard (UptimeRobot)
Use this link to access your UptimeRobot dashboard to delete the old monitor:
- **URL**: [uptimerobot.com/dashboard](https://uptimerobot.com/dashboard)
