# Render Environment Variables Documentation

If your environment variables on Render are deleted or reset, you can restore them using the following list.

## Core Bot Configurations

| Variable Name | Description | Example / Recommended Value |
| :--- | :--- | :--- |
| `TELEGRAM_BOT_TOKEN` | API Token of your Telegram bot (from @BotFather). | `8994618380:AAFxJSC5KNBfs6iLX12VWvB3uSTheOvJ-CA` |
| `TELEGRAM_CHAT_ID` | Your Telegram user/chat ID (from @userinfobot). | `1262260329` |
| `PORT` | Render's HTTP service port (bound automatically by Render). | `10000` |
| `RENDER` | Triggers the Render execution (webhook) mode. | `true` |

## API URL Configurations

| Variable Name | Description | Default Blueprint Value |
| :--- | :--- | :--- |
| `PSA_API_URL_TEMPLATE` | URL Template for PSA Sales/Collection Orders (API 1). | `https://psa.mgi.org/api/getALLData/{business_date}/{business_date}/0?server=0` |
| `API_2_URL_TEMPLATE` | URL Template for Cement/SmartSales SO/CO (API 2). | `https://smartsales.mgi.org/api/get-so-payment-collection?start_date={date}&end_date={date}&server_allocation=0&so=1&co=1&so_zone=0&co_zone=0&so_product_line=0&co_product_line=0` |
| `API_2_HEADERS` | JSON Authorization headers for API 2. | `{"Accept": "application/json", "Authorization": "Bearer 2170..."}` |
| `API_3_URL_TEMPLATE` | URL Template for SmartSales OBD (API 3). | `https://smartsales.mgi.org/api/delivery-program-to-all-incoterm?product_line=0&env=1&plan_id=-&order_no=-&delivery_plan_no=-&plant_code=0&inco_term=0&server_allocation=0&start_date={date}&end_date={date}` |
| `API_3_HEADERS` | JSON headers for API 3. | `{"app-key": "AnF3XAy..."}` |
| `API_4_URL_TEMPLATE` | URL Template for SAP Contract Pending (API 4). | `https://psa.mgi.org/api/getCorpAllData/{business_date}/{business_date}/8?server=0` |
| `API_5_URL_TEMPLATE` | URL Template for FreshLPG SO/CO (API 5). | `https://freshlpg.mgi.org/api/get-so-payment-collection?start_date={date}&end_date={date}&server_allocation=0&so=1&co=1&so_zone=0&co_zone=0&so_product_line=0&co_product_line=0` |
| `API_5_HEADERS` | JSON headers for API 5. | `{"Accept": "application/json", "Authorization": "Bearer 2170..."}` |

## Threshold Defaults & Call Targets

> [!NOTE]
> Automatic environment variable updates via Render API have been **disabled** to protect your Telegram bot secrets from being overwritten or deleted.
> To permanently change a threshold default, modify it directly in the Render dashboard's **Environment** tab.

| Variable Name | Description | Default Value |
| :--- | :--- | :--- |
| `PSA_SO_PENDING_THRESHOLD_MINUTES_DEFAULT` | Default threshold minutes for PSA SO (f1) | `15` |
| `PSA_CO_PENDING_THRESHOLD_MINUTES_DEFAULT` | Default threshold minutes for PSA CO (f2) | `10` |
| `OBD_PENDING_THRESHOLD_MINUTES_DEFAULT` | Default threshold minutes for SmartSales OBD (f3) | `20` |
| `CEMENTAPI_SO_PENDING_THRESHOLD_MINUTES_DEFAULT` | Default threshold minutes for Cement SO (f4) | `15` |
| `CEMENTAPI_CO_PENDING_THRESHOLD_MINUTES_DEFAULT` | Default threshold minutes for Cement CO (f5) | `10` |
| `CONTRACTAPI_CO_PENDING_THRESHOLD_MINUTES_DEFAULT` | Default threshold for SAP Contract (f6) | `10` |
| `SMARTSALES_OBD_OFFHOURS_THRESHOLD_MINUTES_DEFAULT` | Default threshold for Off-Hours OBD (f7) | `30` |
| `FRESHLPG_SO_PENDING_THRESHOLD_MINUTES_DEFAULT` | Default threshold for FreshLPG SO (f8) | `15` |
| `FRESHLPG_CO_PENDING_THRESHOLD_MINUTES_DEFAULT` | Default threshold for FreshLPG CO (f9) | `10` |
| `OBD_OFFHOURS_START_HOUR_DEFAULT` | Default start hour for f7 off-hours | `1` |
| `OBD_OFFHOURS_END_HOUR_DEFAULT` | Default end hour for f7 off-hours | `8` |
| `CALLMEBOT_USER_DEFAULT` | Default CallMeBot targets (comma-separated list of usernames/phone numbers. Validated for username format or starting with `+`. Invalid list inputs will fall back to `+8801838262248` default) | `@UshDhar, +8801838262248` |
| `PREFERRED_ENV` | Startup preferred state setting. | `Local` |
