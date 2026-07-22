import os
import sys
import json
import datetime
import time
import urllib.request
import urllib.parse
from urllib.parse import urlparse, parse_qs
import threading
import http.server
import socketserver
import concurrent.futures

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(SCRIPT_DIR, "config.json")
LOG_LOCK = threading.Lock()
_builtin_print = print

def log_message(msg):
    """
    Logs a message to console. 
    If running offline (no RENDER environment variable), also saves it to logs/{YYYY-MM-DD}.log.
    """
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    formatted_msg = f"[{timestamp}] {msg}"
    _builtin_print(formatted_msg, flush=True)
    
    # Check if running offline
    is_online = os.environ.get("RENDER") == "true"
    if not is_online:
        logs_dir = os.path.join(SCRIPT_DIR, "logs")
        try:
            with LOG_LOCK:
                if not os.path.exists(logs_dir):
                    os.makedirs(logs_dir)
                today_str = datetime.datetime.now().strftime("%Y-%m-%d")
                log_file = os.path.join(logs_dir, f"{today_str}.log")
                with open(log_file, "a", encoding="utf-8") as f:
                    f.write(formatted_msg + "\n")
        except Exception as e:
            _builtin_print(f"[{timestamp}] Failed to write log to file: {e}")

def print(*args, **kwargs):
    """Overrides default print to redirect output to log_message, cleaning redundant timestamps."""
    msg = " ".join(str(arg) for arg in args)
    # Strip any leading [YYYY-MM-DD HH:MM:SS] timestamp pattern if already present
    import re
    cleaned_msg = re.sub(r'^\[\d{4}-\d{2}-\d{2}\s\d{2}:\d{2}:\d{2}(?:\.\d+)?\]\s*', '', msg)
    log_message(cleaned_msg)

def rotate_local_logs():
    """Deletes local log files older than 3 days."""
    is_online = os.environ.get("RENDER") == "true"
    if is_online:
        return
        
    logs_dir = os.path.join(SCRIPT_DIR, "logs")
    if not os.path.exists(logs_dir):
        return
        
    now = datetime.datetime.now()
    cutoff_date = now - datetime.timedelta(days=3)
    
    try:
        with LOG_LOCK:
            for filename in os.listdir(logs_dir):
                if filename.endswith(".log"):
                    date_part = filename[:-4]
                    try:
                        file_date = datetime.datetime.strptime(date_part, "%Y-%m-%d")
                        if file_date.date() < cutoff_date.date():
                            file_path = os.path.join(logs_dir, filename)
                            os.remove(file_path)
                            print(f"[{now.strftime('%Y-%m-%d %H:%M:%S')}] Auto-deleted old log file: {filename}")
                    except ValueError:
                        pass
    except Exception as e:
        print(f"[{now.strftime('%Y-%m-%d %H:%M:%S')}] Failed during log rotation: {e}")

# Global variables for webhook diagnostics
LAST_WEBHOOK_PAYLOAD = None
LAST_WEBHOOK_ERROR = None

# Conversational / interactive variables for aging alert checks
USER_CONVERSATION_STATE = None
PENDING_CONFIG_UPDATE = None
IS_STANDBY = False
LAST_LOCAL_HEARTBEAT = 0.0
LOCAL_ONLINE_STATE = True
LONG_POLLING_ACTIVE = False

# State switching and failover variables
PREFERRED_ENV = "Local"
ACTIVE_ENV = "Local"
BOTH_DEAD_ALERT_SENT = False
LAST_API_POLL_SUCCESS = True
CONFIG_ERROR = False

# Flapping/consecutive success and failure counters
LOCAL_CONSECUTIVE_SUCCESS = 0
LOCAL_CONSECUTIVE_FAILURE = 0
RENDER_CONSECUTIVE_SUCCESS = 0
RENDER_CONSECUTIVE_FAILURE = 0

# Configuration variables (Current vs Default)
PSA_SO_PENDING_THRESHOLD_MINUTES = 15
PSA_SO_PENDING_THRESHOLD_MINUTES_DEFAULT = 15

PSA_CO_PENDING_THRESHOLD_MINUTES = 10
PSA_CO_PENDING_THRESHOLD_MINUTES_DEFAULT = 10

OBD_PENDING_THRESHOLD_MINUTES = 20
OBD_PENDING_THRESHOLD_MINUTES_DEFAULT = 20

CEMENTAPI_SO_PENDING_THRESHOLD_MINUTES = 15
CEMENTAPI_SO_PENDING_THRESHOLD_MINUTES_DEFAULT = 15

CEMENTAPI_CO_PENDING_THRESHOLD_MINUTES = 10
CEMENTAPI_CO_PENDING_THRESHOLD_MINUTES_DEFAULT = 10

CONTRACTAPI_CO_PENDING_THRESHOLD_MINUTES = 10
CONTRACTAPI_CO_PENDING_THRESHOLD_MINUTES_DEFAULT = 10

SMARTSALES_OBD_OFFHOURS_THRESHOLD_MINUTES = 30
SMARTSALES_OBD_OFFHOURS_THRESHOLD_MINUTES_DEFAULT = 30

FRESHLPG_SO_PENDING_THRESHOLD_MINUTES = 15
FRESHLPG_SO_PENDING_THRESHOLD_MINUTES_DEFAULT = 15

FRESHLPG_CO_PENDING_THRESHOLD_MINUTES = 10
FRESHLPG_CO_PENDING_THRESHOLD_MINUTES_DEFAULT = 10

OBD_OFFHOURS_START_HOUR = 0
OBD_OFFHOURS_START_HOUR_DEFAULT = 0

OBD_OFFHOURS_END_HOUR = 0
OBD_OFFHOURS_END_HOUR_DEFAULT = 0

CALLMEBOT_USER = "@UshDhar"
CALLMEBOT_USER_DEFAULT = "+8801838262248"

def is_hour_in_range(hour, start, end):
    """Checks if an hour is within a start/end window, supporting midnight wrap-around and 24h mode."""
    if (start == 0 and end == 24) or (start == 0 and end == 0) or (start == end and start != 0):
        return True
    if start < end:
        return start <= hour < end
    else:
        return hour >= start or hour < end

def is_in_10min_psa_window(dt):
    """Checks if local time is within the 11:01 PM to 12:59 AM window (23:01 to 00:59)."""
    hour = dt.hour
    minute = dt.minute
    if hour == 23 and minute >= 1:
        return True
    if hour == 0 and minute <= 59:
        return True
    return False

def load_thresholds():
    global PSA_SO_PENDING_THRESHOLD_MINUTES, PSA_CO_PENDING_THRESHOLD_MINUTES, OBD_PENDING_THRESHOLD_MINUTES
    global CEMENTAPI_SO_PENDING_THRESHOLD_MINUTES, CEMENTAPI_CO_PENDING_THRESHOLD_MINUTES
    global CONTRACTAPI_CO_PENDING_THRESHOLD_MINUTES
    global SMARTSALES_OBD_OFFHOURS_THRESHOLD_MINUTES, OBD_OFFHOURS_START_HOUR, OBD_OFFHOURS_END_HOUR
    global FRESHLPG_SO_PENDING_THRESHOLD_MINUTES, FRESHLPG_CO_PENDING_THRESHOLD_MINUTES
    global CALLMEBOT_USER
    
    global PSA_SO_PENDING_THRESHOLD_MINUTES_DEFAULT, PSA_CO_PENDING_THRESHOLD_MINUTES_DEFAULT, OBD_PENDING_THRESHOLD_MINUTES_DEFAULT
    global CEMENTAPI_SO_PENDING_THRESHOLD_MINUTES_DEFAULT, CEMENTAPI_CO_PENDING_THRESHOLD_MINUTES_DEFAULT
    global CONTRACTAPI_CO_PENDING_THRESHOLD_MINUTES_DEFAULT
    global SMARTSALES_OBD_OFFHOURS_THRESHOLD_MINUTES_DEFAULT, OBD_OFFHOURS_START_HOUR_DEFAULT, OBD_OFFHOURS_END_HOUR_DEFAULT
    global FRESHLPG_SO_PENDING_THRESHOLD_MINUTES_DEFAULT, FRESHLPG_CO_PENDING_THRESHOLD_MINUTES_DEFAULT
    global CALLMEBOT_USER_DEFAULT
    
    global PREFERRED_ENV, ACTIVE_ENV, CONFIG_ERROR

    defaults = {
        "PSA_SO_PENDING_THRESHOLD_MINUTES_DEFAULT": 26,
        "PSA_CO_PENDING_THRESHOLD_MINUTES_DEFAULT": 10,
        "OBD_PENDING_THRESHOLD_MINUTES_DEFAULT": 20,
        "CEMENTAPI_SO_PENDING_THRESHOLD_MINUTES_DEFAULT": 15,
        "CEMENTAPI_CO_PENDING_THRESHOLD_MINUTES_DEFAULT": 10,
        "CONTRACTAPI_CO_PENDING_THRESHOLD_MINUTES_DEFAULT": 10,
        "SMARTSALES_OBD_OFFHOURS_THRESHOLD_MINUTES_DEFAULT": 30,
        "FRESHLPG_SO_PENDING_THRESHOLD_MINUTES_DEFAULT": 15,
        "FRESHLPG_CO_PENDING_THRESHOLD_MINUTES_DEFAULT": 10,
        "OBD_OFFHOURS_START_HOUR_DEFAULT": 0,
        "OBD_OFFHOURS_END_HOUR_DEFAULT": 0,
        "CALLMEBOT_USER_DEFAULT": "@UshDhar, +8801838262248",
        
        "PSA_SO_PENDING_THRESHOLD_MINUTES": None,
        "PSA_CO_PENDING_THRESHOLD_MINUTES": None,
        "OBD_PENDING_THRESHOLD_MINUTES": None,
        "CEMENTAPI_SO_PENDING_THRESHOLD_MINUTES": None,
        "CEMENTAPI_CO_PENDING_THRESHOLD_MINUTES": None,
        "CONTRACTAPI_CO_PENDING_THRESHOLD_MINUTES": None,
        "SMARTSALES_OBD_OFFHOURS_THRESHOLD_MINUTES": None,
        "FRESHLPG_SO_PENDING_THRESHOLD_MINUTES": None,
        "FRESHLPG_CO_PENDING_THRESHOLD_MINUTES": None,
        "OBD_OFFHOURS_START_HOUR": None,
        "OBD_OFFHOURS_END_HOUR": None,
        "CALLMEBOT_USER": None,
        
        "PREFERRED_ENV": "Local"
    }

    # Backward compatibility: try loading legacy keys from config.json first
    legacy_mappings = {
        "PSA_SO_PENDING_THRESHOLD_MINUTES": "PSA_SO_PENDING_THRESHOLD_MINUTES_DEFAULT",
        "PSA_CO_PENDING_THRESHOLD_MINUTES": "PSA_CO_PENDING_THRESHOLD_MINUTES_DEFAULT",
        "OBD_PENDING_THRESHOLD_MINUTES": "OBD_PENDING_THRESHOLD_MINUTES_DEFAULT",
        "CEMENTAPI_SO_PENDING_THRESHOLD_MINUTES": "CEMENTAPI_SO_PENDING_THRESHOLD_MINUTES_DEFAULT",
        "CEMENTAPI_CO_PENDING_THRESHOLD_MINUTES": "CEMENTAPI_CO_PENDING_THRESHOLD_MINUTES_DEFAULT",
        "CONTRACTAPI_CO_PENDING_THRESHOLD_MINUTES": "CONTRACTAPI_CO_PENDING_THRESHOLD_MINUTES_DEFAULT",
        "SMARTSALES_OBD_OFFHOURS_THRESHOLD_MINUTES": "SMARTSALES_OBD_OFFHOURS_THRESHOLD_MINUTES_DEFAULT",
        "FRESHLPG_SO_PENDING_THRESHOLD_MINUTES": "FRESHLPG_SO_PENDING_THRESHOLD_MINUTES_DEFAULT",
        "FRESHLPG_CO_PENDING_THRESHOLD_MINUTES": "FRESHLPG_CO_PENDING_THRESHOLD_MINUTES_DEFAULT",
        "OBD_OFFHOURS_START_HOUR": "OBD_OFFHOURS_START_HOUR_DEFAULT",
        "OBD_OFFHOURS_END_HOUR": "OBD_OFFHOURS_END_HOUR_DEFAULT",
        "CALLMEBOT_USER": "CALLMEBOT_USER_DEFAULT"
    }

    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, 'r') as f:
                saved = json.load(f)
                # First load default keys if they exist
                for k, v in saved.items():
                    if k in defaults:
                        defaults[k] = v
                # Fallback to legacy keys if default keys don't exist in config.json yet
                for legacy_k, default_k in legacy_mappings.items():
                    if default_k not in saved and legacy_k in saved:
                        defaults[default_k] = saved[legacy_k]
        except Exception as e:
            print(f"Error loading thresholds from config.json: {e}")

    for key in defaults:
        env_val = os.environ.get(key)
        # Fallback to check legacy env var if default env var is not present
        if env_val is None:
            legacy_key = next((lk for lk, dk in legacy_mappings.items() if dk == key), None)
            if legacy_key:
                env_val = os.environ.get(legacy_key)

        if env_val is not None:
            if isinstance(defaults[key], bool):
                defaults[key] = (str(env_val).strip().lower() in ("true", "1", "yes"))
            elif isinstance(defaults[key], int):
                try:
                    defaults[key] = int(env_val)
                except ValueError:
                    pass
            elif defaults[key] is None:
                # Determine type from default counterpart or handle as string
                try:
                    defaults[key] = int(env_val)
                except ValueError:
                    defaults[key] = str(env_val)
            else:
                defaults[key] = str(env_val)

    # Assign default globals
    PSA_SO_PENDING_THRESHOLD_MINUTES_DEFAULT = defaults["PSA_SO_PENDING_THRESHOLD_MINUTES_DEFAULT"]
    PSA_CO_PENDING_THRESHOLD_MINUTES_DEFAULT = defaults["PSA_CO_PENDING_THRESHOLD_MINUTES_DEFAULT"]
    OBD_PENDING_THRESHOLD_MINUTES_DEFAULT = defaults["OBD_PENDING_THRESHOLD_MINUTES_DEFAULT"]
    CEMENTAPI_SO_PENDING_THRESHOLD_MINUTES_DEFAULT = defaults["CEMENTAPI_SO_PENDING_THRESHOLD_MINUTES_DEFAULT"]
    CEMENTAPI_CO_PENDING_THRESHOLD_MINUTES_DEFAULT = defaults["CEMENTAPI_CO_PENDING_THRESHOLD_MINUTES_DEFAULT"]
    CONTRACTAPI_CO_PENDING_THRESHOLD_MINUTES_DEFAULT = defaults["CONTRACTAPI_CO_PENDING_THRESHOLD_MINUTES_DEFAULT"]
    SMARTSALES_OBD_OFFHOURS_THRESHOLD_MINUTES_DEFAULT = defaults["SMARTSALES_OBD_OFFHOURS_THRESHOLD_MINUTES_DEFAULT"]
    FRESHLPG_SO_PENDING_THRESHOLD_MINUTES_DEFAULT = defaults["FRESHLPG_SO_PENDING_THRESHOLD_MINUTES_DEFAULT"]
    FRESHLPG_CO_PENDING_THRESHOLD_MINUTES_DEFAULT = defaults["FRESHLPG_CO_PENDING_THRESHOLD_MINUTES_DEFAULT"]
    OBD_OFFHOURS_START_HOUR_DEFAULT = defaults["OBD_OFFHOURS_START_HOUR_DEFAULT"]
    OBD_OFFHOURS_END_HOUR_DEFAULT = defaults["OBD_OFFHOURS_END_HOUR_DEFAULT"]
    CALLMEBOT_USER_DEFAULT = defaults["CALLMEBOT_USER_DEFAULT"]
    PREFERRED_ENV = defaults["PREFERRED_ENV"]

    if not CALLMEBOT_USER_DEFAULT or CALLMEBOT_USER_DEFAULT.strip().lower() in ["none", "off", ""]:
        CALLMEBOT_USER_DEFAULT = "1262260329"

    # Initialize current/runtime variables (fallback to defaults if None)
    PSA_SO_PENDING_THRESHOLD_MINUTES = defaults["PSA_SO_PENDING_THRESHOLD_MINUTES"] if defaults["PSA_SO_PENDING_THRESHOLD_MINUTES"] is not None else PSA_SO_PENDING_THRESHOLD_MINUTES_DEFAULT
    PSA_CO_PENDING_THRESHOLD_MINUTES = defaults["PSA_CO_PENDING_THRESHOLD_MINUTES"] if defaults["PSA_CO_PENDING_THRESHOLD_MINUTES"] is not None else PSA_CO_PENDING_THRESHOLD_MINUTES_DEFAULT
    OBD_PENDING_THRESHOLD_MINUTES = defaults["OBD_PENDING_THRESHOLD_MINUTES"] if defaults["OBD_PENDING_THRESHOLD_MINUTES"] is not None else OBD_PENDING_THRESHOLD_MINUTES_DEFAULT
    CEMENTAPI_SO_PENDING_THRESHOLD_MINUTES = defaults["CEMENTAPI_SO_PENDING_THRESHOLD_MINUTES"] if defaults["CEMENTAPI_SO_PENDING_THRESHOLD_MINUTES"] is not None else CEMENTAPI_SO_PENDING_THRESHOLD_MINUTES_DEFAULT
    CEMENTAPI_CO_PENDING_THRESHOLD_MINUTES = defaults["CEMENTAPI_CO_PENDING_THRESHOLD_MINUTES"] if defaults["CEMENTAPI_CO_PENDING_THRESHOLD_MINUTES"] is not None else CEMENTAPI_CO_PENDING_THRESHOLD_MINUTES_DEFAULT
    CONTRACTAPI_CO_PENDING_THRESHOLD_MINUTES = defaults["CONTRACTAPI_CO_PENDING_THRESHOLD_MINUTES"] if defaults["CONTRACTAPI_CO_PENDING_THRESHOLD_MINUTES"] is not None else CONTRACTAPI_CO_PENDING_THRESHOLD_MINUTES_DEFAULT
    SMARTSALES_OBD_OFFHOURS_THRESHOLD_MINUTES = defaults["SMARTSALES_OBD_OFFHOURS_THRESHOLD_MINUTES"] if defaults["SMARTSALES_OBD_OFFHOURS_THRESHOLD_MINUTES"] is not None else SMARTSALES_OBD_OFFHOURS_THRESHOLD_MINUTES_DEFAULT
    FRESHLPG_SO_PENDING_THRESHOLD_MINUTES = defaults["FRESHLPG_SO_PENDING_THRESHOLD_MINUTES"] if defaults["FRESHLPG_SO_PENDING_THRESHOLD_MINUTES"] is not None else FRESHLPG_SO_PENDING_THRESHOLD_MINUTES_DEFAULT
    FRESHLPG_CO_PENDING_THRESHOLD_MINUTES = defaults["FRESHLPG_CO_PENDING_THRESHOLD_MINUTES"] if defaults["FRESHLPG_CO_PENDING_THRESHOLD_MINUTES"] is not None else FRESHLPG_CO_PENDING_THRESHOLD_MINUTES_DEFAULT
    OBD_OFFHOURS_START_HOUR = defaults["OBD_OFFHOURS_START_HOUR"] if defaults["OBD_OFFHOURS_START_HOUR"] is not None else OBD_OFFHOURS_START_HOUR_DEFAULT
    OBD_OFFHOURS_END_HOUR = defaults["OBD_OFFHOURS_END_HOUR"] if defaults["OBD_OFFHOURS_END_HOUR"] is not None else OBD_OFFHOURS_END_HOUR_DEFAULT
    CALLMEBOT_USER = defaults["CALLMEBOT_USER"] if defaults["CALLMEBOT_USER"] is not None else CALLMEBOT_USER_DEFAULT

    # Determine ACTIVE_ENV at startup
    is_render = (os.environ.get("RENDER") is not None or os.environ.get("RENDER_SERVICE_ID") is not None)
    
    # Core configuration variable validation
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    
    token_ok = bool(token and "YOUR_TELEGRAM" not in token and token.strip() != "")
    chat_ok = bool(chat_id and "YOUR_TELEGRAM" not in chat_id and chat_id.strip() != "")

    if is_render:
        ACTIVE_ENV = "Render"
        if not token_ok or not chat_ok:
            CONFIG_ERROR = True
            print(f"[{datetime.datetime.now()}] CRITICAL CONFIGURATION ALERT: TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID is missing or not configured on Render!")
    else:
        ACTIVE_ENV = "Local"

def save_thresholds():
    global PSA_SO_PENDING_THRESHOLD_MINUTES_DEFAULT, PSA_CO_PENDING_THRESHOLD_MINUTES_DEFAULT, OBD_PENDING_THRESHOLD_MINUTES_DEFAULT
    global CEMENTAPI_SO_PENDING_THRESHOLD_MINUTES_DEFAULT, CEMENTAPI_CO_PENDING_THRESHOLD_MINUTES_DEFAULT
    global CONTRACTAPI_CO_PENDING_THRESHOLD_MINUTES_DEFAULT
    global SMARTSALES_OBD_OFFHOURS_THRESHOLD_MINUTES_DEFAULT, OBD_OFFHOURS_START_HOUR_DEFAULT, OBD_OFFHOURS_END_HOUR_DEFAULT
    global FRESHLPG_SO_PENDING_THRESHOLD_MINUTES_DEFAULT, FRESHLPG_CO_PENDING_THRESHOLD_MINUTES_DEFAULT
    global CALLMEBOT_USER_DEFAULT
    global PREFERRED_ENV

    global PSA_SO_PENDING_THRESHOLD_MINUTES, PSA_CO_PENDING_THRESHOLD_MINUTES, OBD_PENDING_THRESHOLD_MINUTES
    global CEMENTAPI_SO_PENDING_THRESHOLD_MINUTES, CEMENTAPI_CO_PENDING_THRESHOLD_MINUTES
    global CONTRACTAPI_CO_PENDING_THRESHOLD_MINUTES
    global SMARTSALES_OBD_OFFHOURS_THRESHOLD_MINUTES, OBD_OFFHOURS_START_HOUR, OBD_OFFHOURS_END_HOUR
    global FRESHLPG_SO_PENDING_THRESHOLD_MINUTES, FRESHLPG_CO_PENDING_THRESHOLD_MINUTES
    global CALLMEBOT_USER

    thresholds = {
        "PSA_SO_PENDING_THRESHOLD_MINUTES": PSA_SO_PENDING_THRESHOLD_MINUTES,
        "PSA_CO_PENDING_THRESHOLD_MINUTES": PSA_CO_PENDING_THRESHOLD_MINUTES,
        "OBD_PENDING_THRESHOLD_MINUTES": OBD_PENDING_THRESHOLD_MINUTES,
        "CEMENTAPI_SO_PENDING_THRESHOLD_MINUTES": CEMENTAPI_SO_PENDING_THRESHOLD_MINUTES,
        "CEMENTAPI_CO_PENDING_THRESHOLD_MINUTES": CEMENTAPI_CO_PENDING_THRESHOLD_MINUTES,
        "CONTRACTAPI_CO_PENDING_THRESHOLD_MINUTES": CONTRACTAPI_CO_PENDING_THRESHOLD_MINUTES,
        "SMARTSALES_OBD_OFFHOURS_THRESHOLD_MINUTES": SMARTSALES_OBD_OFFHOURS_THRESHOLD_MINUTES,
        "FRESHLPG_SO_PENDING_THRESHOLD_MINUTES": FRESHLPG_SO_PENDING_THRESHOLD_MINUTES,
        "FRESHLPG_CO_PENDING_THRESHOLD_MINUTES": FRESHLPG_CO_PENDING_THRESHOLD_MINUTES,
        "OBD_OFFHOURS_START_HOUR": OBD_OFFHOURS_START_HOUR,
        "OBD_OFFHOURS_END_HOUR": OBD_OFFHOURS_END_HOUR,
        "CALLMEBOT_USER": CALLMEBOT_USER,

        "PSA_SO_PENDING_THRESHOLD_MINUTES_DEFAULT": PSA_SO_PENDING_THRESHOLD_MINUTES_DEFAULT,
        "PSA_CO_PENDING_THRESHOLD_MINUTES_DEFAULT": PSA_CO_PENDING_THRESHOLD_MINUTES_DEFAULT,
        "OBD_PENDING_THRESHOLD_MINUTES_DEFAULT": OBD_PENDING_THRESHOLD_MINUTES_DEFAULT,
        "CEMENTAPI_SO_PENDING_THRESHOLD_MINUTES_DEFAULT": CEMENTAPI_SO_PENDING_THRESHOLD_MINUTES_DEFAULT,
        "CEMENTAPI_CO_PENDING_THRESHOLD_MINUTES_DEFAULT": CEMENTAPI_CO_PENDING_THRESHOLD_MINUTES_DEFAULT,
        "CONTRACTAPI_CO_PENDING_THRESHOLD_MINUTES_DEFAULT": CONTRACTAPI_CO_PENDING_THRESHOLD_MINUTES_DEFAULT,
        "SMARTSALES_OBD_OFFHOURS_THRESHOLD_MINUTES_DEFAULT": SMARTSALES_OBD_OFFHOURS_THRESHOLD_MINUTES_DEFAULT,
        "FRESHLPG_SO_PENDING_THRESHOLD_MINUTES_DEFAULT": FRESHLPG_SO_PENDING_THRESHOLD_MINUTES_DEFAULT,
        "FRESHLPG_CO_PENDING_THRESHOLD_MINUTES_DEFAULT": FRESHLPG_CO_PENDING_THRESHOLD_MINUTES_DEFAULT,
        "OBD_OFFHOURS_START_HOUR_DEFAULT": OBD_OFFHOURS_START_HOUR_DEFAULT,
        "OBD_OFFHOURS_END_HOUR_DEFAULT": OBD_OFFHOURS_END_HOUR_DEFAULT,
        "CALLMEBOT_USER_DEFAULT": CALLMEBOT_USER_DEFAULT,
        "PREFERRED_ENV": PREFERRED_ENV
    }
    try:
        config_data = {}
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, 'r') as f:
                config_data = json.load(f)
        for k, v in thresholds.items():
            config_data[k] = v
        with open(CONFIG_PATH, 'w') as f:
            json.dump(config_data, f, indent=4)
    except Exception as e:
        print(f"Error saving to config.json: {e}")

def update_render_env_vars_async():
    """
    Spawns a background thread to update all default environment variable thresholds via Render API,
    and triggers a redeployment to apply the change.
    """
    return
        
    def run_update():
        global PSA_SO_PENDING_THRESHOLD_MINUTES_DEFAULT, PSA_CO_PENDING_THRESHOLD_MINUTES_DEFAULT, OBD_PENDING_THRESHOLD_MINUTES_DEFAULT
        global CEMENTAPI_SO_PENDING_THRESHOLD_MINUTES_DEFAULT, CEMENTAPI_CO_PENDING_THRESHOLD_MINUTES_DEFAULT
        global CONTRACTAPI_CO_PENDING_THRESHOLD_MINUTES_DEFAULT
        global SMARTSALES_OBD_OFFHOURS_THRESHOLD_MINUTES_DEFAULT, OBD_OFFHOURS_START_HOUR_DEFAULT, OBD_OFFHOURS_END_HOUR_DEFAULT
        global FRESHLPG_SO_PENDING_THRESHOLD_MINUTES_DEFAULT, FRESHLPG_CO_PENDING_THRESHOLD_MINUTES_DEFAULT
        global CALLMEBOT_USER_DEFAULT
        global PREFERRED_ENV
        
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
        
        active_states = {
            "PSA_SO_PENDING_THRESHOLD_MINUTES_DEFAULT": PSA_SO_PENDING_THRESHOLD_MINUTES_DEFAULT,
            "PSA_CO_PENDING_THRESHOLD_MINUTES_DEFAULT": PSA_CO_PENDING_THRESHOLD_MINUTES_DEFAULT,
            "OBD_PENDING_THRESHOLD_MINUTES_DEFAULT": OBD_PENDING_THRESHOLD_MINUTES_DEFAULT,
            "CEMENTAPI_SO_PENDING_THRESHOLD_MINUTES_DEFAULT": CEMENTAPI_SO_PENDING_THRESHOLD_MINUTES_DEFAULT,
            "CEMENTAPI_CO_PENDING_THRESHOLD_MINUTES_DEFAULT": CEMENTAPI_CO_PENDING_THRESHOLD_MINUTES_DEFAULT,
            "CONTRACTAPI_CO_PENDING_THRESHOLD_MINUTES_DEFAULT": CONTRACTAPI_CO_PENDING_THRESHOLD_MINUTES_DEFAULT,
            "SMARTSALES_OBD_OFFHOURS_THRESHOLD_MINUTES_DEFAULT": SMARTSALES_OBD_OFFHOURS_THRESHOLD_MINUTES_DEFAULT,
            "FRESHLPG_SO_PENDING_THRESHOLD_MINUTES_DEFAULT": FRESHLPG_SO_PENDING_THRESHOLD_MINUTES_DEFAULT,
            "FRESHLPG_CO_PENDING_THRESHOLD_MINUTES_DEFAULT": FRESHLPG_CO_PENDING_THRESHOLD_MINUTES_DEFAULT,
            "OBD_OFFHOURS_START_HOUR_DEFAULT": OBD_OFFHOURS_START_HOUR_DEFAULT,
            "OBD_OFFHOURS_END_HOUR_DEFAULT": OBD_OFFHOURS_END_HOUR_DEFAULT,
            "CALLMEBOT_USER_DEFAULT": CALLMEBOT_USER_DEFAULT,
            "PREFERRED_ENV": PREFERRED_ENV
        }
        
        # 1. GET all current environment variables
        get_url = f"https://api.render.com/v1/services/{service_id}/env-vars"
        get_req = urllib.request.Request(get_url, headers=headers, method="GET")
        
        try:
            with urllib.request.urlopen(get_req, timeout=15) as resp:
                if resp.status == 200:
                    raw_data = json.loads(resp.read().decode('utf-8'))
                    new_env_vars = []
                    existing_keys = set()
                    
                    if isinstance(raw_data, list):
                        for item in raw_data:
                            if "envVar" in item:
                                k = item["envVar"]["key"]
                                v = item["envVar"]["value"]
                            else:
                                k = item.get("key")
                                v = item.get("value")
                            
                            if k:
                                existing_keys.add(k)
                                if k in active_states:
                                    new_env_vars.append({"key": k, "value": str(active_states[k])})
                                else:
                                    new_env_vars.append({"key": k, "value": str(v)})
                                    
                        # Add any variables not yet existing on Render
                        for k, val in active_states.items():
                            if k not in existing_keys:
                                new_env_vars.append({"key": k, "value": str(val)})
                                
                        # 2. PUT the updated list of variables
                        put_url = f"https://api.render.com/v1/services/{service_id}/env-vars"
                        put_data = json.dumps(new_env_vars).encode('utf-8')
                        put_req = urllib.request.Request(put_url, data=put_data, headers=headers, method="PUT")
                        
                        with urllib.request.urlopen(put_req, timeout=15) as put_resp:
                            if put_resp.status in (200, 201, 204):
                                log_message(f"Render API: Successfully synchronized default thresholds to Render env vars.")
                            else:
                                log_message(f"Render API: Received status {put_resp.status} when PUTting env vars.")
                                return
                    else:
                        log_message(f"Render API: Unexpected format for GET env-vars response: {type(raw_data)}")
                        return
                else:
                    log_message(f"Render API: Received status {resp.status} when GETting env vars.")
                    return
        except Exception as e:
            log_message(f"Render API: Failed to GET/PUT environment variables: {e}")
            return
            
        # 3. Trigger a deploy to apply the updated environment variables
        deploy_url = f"https://api.render.com/v1/services/{service_id}/deploys"
        deploy_data = json.dumps({}).encode('utf-8')
        deploy_req = urllib.request.Request(deploy_url, data=deploy_data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(deploy_req, timeout=15) as resp:
                if resp.status in (200, 201, 202):
                    log_message(f"Render API: Successfully triggered redeployment of service {service_id}.")
                else:
                    log_message(f"Render API: Received status {resp.status} when triggering deploy.")
        except Exception as e:
            log_message(f"Render API: Failed to trigger redeployment: {e}")

    threading.Thread(target=run_update, daemon=True).start()

def is_valid_callmebot_target(target):
    t = target.strip()
    if not t:
        return False
    if t.startswith("+"):
        return t[1:].isdigit() and len(t) >= 10
    if t.isdigit():
        return False
    t_clean = t.lstrip("@")
    has_letter = any(c.isalpha() for c in t_clean)
    is_alnum = all(c.isalnum() or c == "_" for c in t_clean)
    return has_letter and is_alnum and len(t_clean) >= 3

def validate_callmebot_user_list(user_list_str):
    parts = [p.strip() for p in user_list_str.split(",") if p.strip()]
    if not parts:
        return False
    for p in parts:
        if not is_valid_callmebot_target(p):
            return False
    return True

LAST_CALL_TIME = 0.0
LAST_VOICE_ALERT_TIME = 0.0
CALL_LOCK = threading.Lock()

def trigger_callmebot_call_async(text, config):
    """
    Spawns background threads to trigger CallMeBot Telegram voice calls
    for all configured users in CALLMEBOT_USER (comma-separated),
    ensuring a minimum 70-second interval between consecutive calls.
    """
    global CALLMEBOT_USER
    if not CALLMEBOT_USER or CALLMEBOT_USER.lower() in ["none", "off", ""]:
        return
        
    targets = []
    for t in CALLMEBOT_USER.split(","):
        t_clean = t.strip()
        if not t_clean:
            continue
        if not t_clean.startswith("@") and not t_clean.startswith("+") and not t_clean.isdigit():
            t_clean = "@" + t_clean
        targets.append(t_clean)
    if not targets:
        return
        
    # URL encode text
    encoded_text = urllib.parse.quote(text)
    
    def run_calls():
        global LAST_CALL_TIME
        with CALL_LOCK:
            for target in targets:
                now = time.time()
                elapsed = now - LAST_CALL_TIME
                if elapsed < 70.0:
                    sleep_needed = 70.0 - elapsed
                    log_message(f"CallMeBot Rate Limiter: sleeping {sleep_needed:.1f} seconds to ensure 70s spacing.")
                    time.sleep(sleep_needed)
                
                LAST_CALL_TIME = time.time()
                url = f"http://api.callmebot.com/start.php?user={target}&text={encoded_text}&lang=en-US-Standard-B"
                try:
                    log_message(f"Initiating CallMeBot voice call alert to {target}...")
                    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                    with urllib.request.urlopen(req, timeout=10) as response:
                        res_content = response.read().decode('utf-8')
                        log_message(f"CallMeBot response for {target}: {res_content}")
                except Exception as e:
                    log_message(f"CallMeBot call failed for {target}: {e}")

    threading.Thread(target=run_calls, daemon=True).start()



load_thresholds()

PENDING_FIRST_SEEN = {}
PENDING_ALERTS_SENT = {}
PENDING_LOCK = threading.Lock()

def load_config():
    """Loads configuration from config.json and overrides with environment variables if present."""
    defaults = {
        "telegram_bot_token": "",
        "telegram_chat_id": "",
        "monitoring_start_hour": 9,
        "monitoring_end_hour": 1,
        "poll_interval_minutes": 30,
        "server_port": 8080,
        "timezone_offset_hours": 6,
        "apis": [],
        "cv_sorting_api_url": "",
        "cv_sorting_api_cookie": "",
        "rpa_config_api_url": "",
        "rpa_config_api_cookie": "",
        "psa_pending_check_url_template": ""
    }
    
    config = defaults.copy()
    file_config = {}
    try:
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, 'r') as f:
                file_config = json.load(f)
                for key in config:
                    if key in file_config:
                        config[key] = file_config[key]
    except Exception as e:
        print(f"Error loading config.json: {e}.")

    # Override Port if set dynamically by environment (like Render)
    env_port = os.environ.get("PORT")
    if env_port:
        try:
            config["server_port"] = int(env_port)
        except ValueError:
            pass

    # Override bot token / chat id from env vars
    for key in ["telegram_bot_token", "telegram_chat_id", "cv_sorting_api_url", "cv_sorting_api_cookie", "rpa_config_api_url", "rpa_config_api_cookie", "psa_pending_check_url_template"]:
        env_val = os.environ.get(key.upper()) or os.environ.get(key.lower())
        if env_val:
            config[key] = env_val

    for key in ["monitoring_start_hour", "monitoring_end_hour", "poll_interval_minutes", "timezone_offset_hours"]:
        env_val = os.environ.get(key.upper()) or os.environ.get(key.lower())
        if env_val:
            try:
                config[key] = int(env_val)
            except ValueError:
                pass

    # Initialize with hardcoded production APIs blueprint
    apis = [
        {
            "name": "PSA",
            "url_template": "https://psa.mgi.org/api/getALLData/{business_date}/{business_date}/0?server=0",
            "filter_pending": True
        },
        {
            "name": "API_2",
            "url_template": "https://smartsales.mgi.org/api/get-so-payment-collection?start_date={date}&end_date={date}&server_allocation=0&so=1&co=1&so_zone=0&co_zone=0&so_product_line=0&co_product_line=0",
            "headers": {"Accept": "application/json", "Authorization": "Bearer 2170|6KxNVYnJD5RoVJTac3CsXmoqjNPCB5Y4g2w8HtNzbc8a3149"},
            "filter_pending": False
        },
        {
            "name": "API_3",
            "url_template": "https://smartsales.mgi.org/api/delivery-program-to-all-incoterm?product_line=0&env=1&plan_id=-&order_no=-&delivery_plan_no=-&plant_code=0&inco_term=0&server_allocation=0&start_date={date}&end_date={date}",
            "headers": {"app-key": "AnF3XAy79fvJvgksKzE0waBh8otfNlXE6htzYxuk"},
            "filter_pending": False
        },
        {
            "name": "API_4",
            "url_template": "https://psa.mgi.org/api/getCorpAllData/{business_date}/{business_date}/8?server=0",
            "filter_pending": False
        },
        {
            "name": "API_5",
            "url_template": "https://freshlpg.mgi.org/api/get-so-payment-collection?start_date={date}&end_date={date}&server_allocation=0&so=1&co=1&so_zone=0&co_zone=0&so_product_line=0&co_product_line=0",
            "headers": {"Accept": "application/json", "Authorization": "Bearer 2170|6KxNVYnJD5RoVJTac3CsXmoqjNPCB5Y4g2w8HtNzbc8a3149"},
            "filter_pending": False
        }
    ]

    # Read environments override for PSA_API_URL_TEMPLATE
    env_psa = (os.environ.get("PSA_API_URL_TEMPLATE") or 
               os.environ.get("psa_api_url_template") or 
               os.environ.get("PSA_PENDING_CHECK_URL_TEMPLATE") or 
               os.environ.get("psa_pending_check_url_template"))
    env_psa_headers = os.environ.get("PSA_API_HEADERS") or os.environ.get("psa_api_headers")
    
    psa_api = next((a for a in apis if a.get("name") == "PSA"), None)
    if psa_api:
        if env_psa:
            psa_api["url_template"] = env_psa
        if env_psa_headers:
            try:
                psa_api["headers"] = json.loads(env_psa_headers)
            except Exception:
                pass

    # Read environments override for API_2_URL_TEMPLATE, API_3_URL_TEMPLATE, API_4_URL_TEMPLATE, API_5_URL_TEMPLATE
    for i in range(2, 6):
        env_key = f"API_{i}_URL_TEMPLATE"
        env_val = os.environ.get(env_key.upper()) or os.environ.get(env_key.lower())
        env_headers_key = f"API_{i}_HEADERS"
        env_headers = os.environ.get(env_headers_key.upper()) or os.environ.get(env_headers_key.lower())
        
        api_name = f"API_{i}"
        existing = next((a for a in apis if a.get("name") == api_name), None)
        if existing:
            if env_val:
                existing["url_template"] = env_val
            if env_headers:
                try:
                    existing["headers"] = json.loads(env_headers)
                except Exception:
                    pass

    # Post-process apis to apply default parameters for known names/patterns if not already set
    for api in apis:
        name_lower = api.get("name", "").lower()
        if "obd" in name_lower or name_lower == "api_3":
            if "default_process" not in api:
                api["default_process"] = "SO"
            if "label_so" not in api:
                api["label_so"] = "OBD"
        elif "contract" in name_lower or name_lower == "api_4":
            if "default_process" not in api:
                api["default_process"] = "CO"
            if "label_co" not in api:
                api["label_co"] = "CON"

    config["apis"] = apis
    return config

def get_local_time(config):
    """Returns the current datetime offset to local timezone (default UTC+6)."""
    offset = config.get("timezone_offset_hours", 6)
    utc_now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
    return utc_now + datetime.timedelta(hours=offset)

def get_business_date_and_active(dt, start_hour, end_hour):
    """
    Calculates the business date and checks if the service should be active.
    - If end_hour < start_hour, the monitoring window spans overnight (e.g. 9 AM to 1 AM next day).
      - From midnight (00:00) to 1:05 AM (with grace period), the business date is yesterday and active is True.
      - From 9:00 AM to midnight, the business date is today and active is True.
      - Between 1:05 AM and 9:00 AM, active is False.
    - If end_hour >= start_hour, the window is same-day (e.g., 9 AM to 5 PM).
      - Active if time is between start_hour and end_hour + 5 min grace.
      - Business date is always today.
    """
    start_time = datetime.time(start_hour, 0, 0)
    # Include 5-minute grace period to ensure the aligned scheduler check running at end_hour:00 executes
    end_time = datetime.time(end_hour, 5, 0)
    current_time = dt.time()

    if end_hour < start_hour:
        if current_time <= end_time:
            # Past midnight, before the end window: business date is yesterday, active
            return (dt - datetime.timedelta(days=1)).date(), True
        elif current_time >= start_time:
            # Today, after start window: business date is today, active
            return dt.date(), True
        else:
            # During inactive morning gap (e.g. 1:05 AM to 9:00 AM)
            return dt.date(), False
    else:
        if start_time <= current_time <= end_time:
            return dt.date(), True
        else:
            return dt.date(), False

def is_empty_value(val):
    """Checks if a value is empty, null, whitespace, or a placeholder like '-'."""
    if val is None:
        return True
    s = str(val).strip()
    return s == "" or s.lower() in ("null", "none", "-")

def is_so_pending(item, api_name=None):
    """Checks if a Sales Order is pending (has no sales order number)."""
    if api_name in ["API_5", "FreshLPG_Pending_Orders", "freshlpg"]:
        return True
            
    for key in ["soNumber", "so_number"]:
        if key in item:
            return is_empty_value(item.get(key))
    return True

def is_co_pending(item, api_name=None):
    """Checks if a Collection Order is pending (has no collection/contract number)."""
    if api_name in ["API_5", "FreshLPG_Pending_Orders", "freshlpg"]:
        return True
        
    for key in ["contractNumber", "coNumber", "co_number"]:
        if key in item:
            return is_empty_value(item.get(key))

    # If coNumber/contractNumber key is not present, but soNumber is present and non-empty, it's a completed SO
    for key in ["soNumber", "so_number"]:
        if key in item and not is_empty_value(item.get(key)):
            return False

    return True

def clear_aging_memory(proc_type, api_name=None):
    """Clears all first-seen and alert-sent memory for a specific process type and optionally API name."""
    global PENDING_FIRST_SEEN, PENDING_ALERTS_SENT
    with PENDING_LOCK:
        seen_keys = [
            k for k in PENDING_FIRST_SEEN.keys() 
            if k[0] == proc_type and (api_name is None or k[1] == api_name)
        ]
        for k in seen_keys:
            del PENDING_FIRST_SEEN[k]
        alert_keys = [
            k for k in PENDING_ALERTS_SENT.keys() 
            if k[0] == proc_type and (api_name is None or k[1] == api_name)
        ]
        for k in alert_keys:
            del PENDING_ALERTS_SENT[k]
    log_message(f"Cleared aging memory for: {proc_type} (API: {api_name})")

def track_and_alert_aging(tx_id, server, process_type, api_name, config):
    """
    Tracks the first seen time of a pending transaction, calculates its age,
    and dispatches a Telegram notification if it crosses the configured threshold.
    """
    if not api_name or not config:
        return
        
    global PENDING_FIRST_SEEN, PENDING_ALERTS_SENT
    global PSA_SO_PENDING_THRESHOLD_MINUTES, PSA_CO_PENDING_THRESHOLD_MINUTES, OBD_PENDING_THRESHOLD_MINUTES
    global CEMENTAPI_SO_PENDING_THRESHOLD_MINUTES, CEMENTAPI_CO_PENDING_THRESHOLD_MINUTES
    global CONTRACTAPI_CO_PENDING_THRESHOLD_MINUTES
    global SMARTSALES_OBD_OFFHOURS_THRESHOLD_MINUTES, OBD_OFFHOURS_START_HOUR, OBD_OFFHOURS_END_HOUR
    
    current_time = get_local_time(config)
    
    # Check if active monitoring hour
    _, active = get_business_date_and_active(
        current_time,
        config.get("monitoring_start_hour", 9),
        config.get("monitoring_end_hour", 1)
    )
    
    # Determine process type (SO, CO, or OBD)
    is_obd = "obd" in api_name.lower() or api_name.lower() == "api_3"
    proc_key = "OBD" if is_obd else process_type
    
    is_f7_window = is_obd and is_hour_in_range(current_time.hour, OBD_OFFHOURS_START_HOUR, OBD_OFFHOURS_END_HOUR)
    
    if not active:
        # If outside active hours, only allow f7 window check
        if not is_f7_window:
            return
            
    key = (proc_key, api_name, tx_id)
    
    with PENDING_LOCK:
        if key not in PENDING_FIRST_SEEN:
            PENDING_FIRST_SEEN[key] = current_time
            
        first_seen = PENDING_FIRST_SEEN[key]
        age_seconds = (current_time - first_seen).total_seconds()
        age_minutes = age_seconds / 60.0
        
    # Threshold mapping
    if is_obd:
        if is_f7_window:
            threshold = SMARTSALES_OBD_OFFHOURS_THRESHOLD_MINUTES
        else:
            threshold = OBD_PENDING_THRESHOLD_MINUTES
    elif api_name == "PSA":
        if process_type == "SO":
            threshold = PSA_SO_PENDING_THRESHOLD_MINUTES
        elif process_type == "CO":
            threshold = PSA_CO_PENDING_THRESHOLD_MINUTES
        else:
            return
    elif api_name in ["API_2", "SmartSales_Pending_Orders"]:
        if process_type == "SO":
            threshold = CEMENTAPI_SO_PENDING_THRESHOLD_MINUTES
        elif process_type == "CO":
            threshold = CEMENTAPI_CO_PENDING_THRESHOLD_MINUTES
        else:
            return
    elif api_name in ["API_5", "FreshLPG_Pending_Orders", "freshlpg"]:
        if process_type == "SO":
            threshold = FRESHLPG_SO_PENDING_THRESHOLD_MINUTES
        elif process_type == "CO":
            threshold = FRESHLPG_CO_PENDING_THRESHOLD_MINUTES
        else:
            return
    elif api_name in ["API_4", "SAP_Contract_Pending"]:
        if process_type == "CO":
            threshold = CONTRACTAPI_CO_PENDING_THRESHOLD_MINUTES
        else:
            return
    else:
        # Fallback: disable alerts for completely unknown APIs
        return
        
    if threshold <= 0:
        return  # Checker is disabled/off
        
    if age_minutes >= threshold:
        alert_key = (proc_key, api_name, tx_id, threshold)
        with PENDING_LOCK:
            already_sent = alert_key in PENDING_ALERTS_SENT
            if already_sent:
                sent_time = PENDING_ALERTS_SENT[alert_key]
                elapsed = (current_time - sent_time).total_seconds() / 60.0
                if elapsed >= 10.0:
                    del PENDING_ALERTS_SENT[alert_key]
                    PENDING_FIRST_SEEN[key] = current_time
                    return
            
        if not already_sent:
            total_sec = int(age_seconds)
            mins = total_sec // 60
            secs = total_sec % 60
            
            # Determine API Name and Unique ID Name for standard template
            name_lower = (api_name or "").lower()
            if is_obd:
                api_label = "SmartSales OBD"
                id_label = "Plan_Id"
            elif api_name in ["API_4", "SAP_Contract_Pending"] or "contract" in name_lower:
                api_label = "SAP Contract"
                id_label = "Transaction_ID"
            elif api_name == "PSA":
                api_label = f"PSA {process_type}"
                id_label = "TransactionId" if process_type == "SO" else "pay_id"
            elif api_name in ["API_2", "SmartSales_Pending_Orders"]:
                api_label = f"SmartSales {process_type}"
                id_label = "TransactionId" if process_type == "SO" else "pay_id"
            elif api_name in ["API_5", "FreshLPG_Pending_Orders", "freshlpg"]:
                api_label = f"FreshLPG {process_type}"
                id_label = "TransactionId" if process_type == "SO" else "pay_id"
            else:
                api_label = (api_name or "API").replace("_", " ")
                id_label = "TransactionId" if process_type == "SO" else "pay_id"
                
            msg = f"{api_label} {id_label} is {tx_id} in server {server} for {mins} min {secs} sec"
                
            log_message(f"Aging Alert triggered: {msg}")
            send_telegram_notification(msg, config)
            if is_obd and is_f7_window:
                global LAST_VOICE_ALERT_TIME
                now_ts = time.time()
                if now_ts - LAST_VOICE_ALERT_TIME >= 600.0:
                    LAST_VOICE_ALERT_TIME = now_ts
                    trigger_callmebot_call_async(msg, config)
                else:
                    log_message("CallMeBot voice call global spacing: alert skipped (already called in the last 10 minutes).")
            
            with PENDING_LOCK:
                PENDING_ALERTS_SENT[alert_key] = current_time

def parse_psa_data(data, filter_pending=True, default_process=None, api_name=None, config=None):
    """
    Parses and counts pending SO and CO from PSA API response.
    Deduplicates based on TransactionId/Transaction_ID/pay_id per serverAllocation.
    Filters out non-pending records if filter_pending is True.
    Handles standard getALLData (SO/CO grouped lists), getCorpAllData, and single lists.
    Also tracks and alerts on transaction aging in memory if api_name/config is provided.
    """
    raw_so_list = []
    raw_co_list = []

    if isinstance(data, dict):
        if "SO" in data or "CO" in data:
            raw_so_list = data.get("SO", [])
            raw_co_list = data.get("CO", [])
        else:
            all_lists = []
            for key, val in data.items():
                if isinstance(val, list):
                    all_lists.extend(val)
            
            if default_process is None:
                raw_so_list = all_lists
                raw_co_list = all_lists
            elif default_process.upper() == "SO":
                raw_so_list = all_lists
            elif default_process.upper() == "CO":
                raw_co_list = all_lists
                
            if not raw_so_list and not raw_co_list:
                return {"server_stats": {}, "total_pending_so": 0, "total_pending_co": 0}
    elif isinstance(data, list):
        if default_process is None:
            raw_so_list = data
            raw_co_list = data
        elif default_process.upper() == "SO":
            raw_so_list = data
        elif default_process.upper() == "CO":
            raw_co_list = data
    else:
        return {"server_stats": {}, "total_pending_so": 0, "total_pending_co": 0}

    print(f"[{datetime.datetime.now()}] Parsing {len(raw_so_list)} SO and {len(raw_co_list)} CO raw records...")

    server_so_ids = {}
    server_co_ids = {}
    active_pending_ids = set()

    name_lower = (api_name or "").lower()
    proc_upper = (default_process or "").upper()
    is_obd_api = "obd" in name_lower or name_lower == "api_3" or proc_upper == "OBD"
    is_contract_api = "contract" in name_lower or name_lower == "api_4" or proc_upper in ("CON", "CONTRACT")

    # Define keys based on API specification
    if is_obd_api:
        so_keys = ["Plan_Id", "plan_id", "planid"]
        co_keys = []
    elif is_contract_api:
        so_keys = []
        co_keys = ["Transaction_ID", "TransactionId", "transaction_id", "transactionid"]
    elif proc_upper == "SO":
        so_keys = ["TransactionId", "transactionid", "Transaction_ID", "transaction_id", "Plan_Id", "plan_id", "planid"]
        co_keys = ["pay_id", "payid", "PayId"]
    elif proc_upper == "CO":
        so_keys = ["TransactionId", "transactionid", "Transaction_ID", "transaction_id"]
        co_keys = ["pay_id", "payid", "PayId", "Transaction_ID", "TransactionId", "transaction_id", "transactionid"]
    else:
        so_keys = ["TransactionId", "transactionid", "Transaction_ID", "transaction_id", "Plan_Id", "plan_id", "planid", "pay_id", "payid"]
        co_keys = ["pay_id", "payid", "PayId", "Transaction_ID", "TransactionId", "transaction_id", "transactionid"]

    def has_non_null_key(item, keys):
        for key in keys:
            if key in item and item[key] is not None:
                return True
            k_lower = key.lower()
            for k, val in item.items():
                if k.lower() == k_lower and val is not None:
                    return True
        return False

    def has_key_case_insensitive(item, keys):
        for key in keys:
            if key in item:
                return True
            k_lower = key.lower()
            for k in item.keys():
                if k.lower() == k_lower:
                    return True
        return False

    def get_unique_id(item, keys):
        for key in keys:
            if key in item:
                val = item[key]
                if val is not None and str(val).strip() != "":
                    return str(val).strip()
            k_lower = key.lower()
            for k, val in item.items():
                if k.lower() == k_lower:
                    if val is not None and str(val).strip() != "":
                        return str(val).strip()
        return None

    def get_server_allocation(item):
        for key in ["serverAllocation", "Server_Allocation", "server_allocation", "ServerAllocation"]:
            if key in item:
                val = item[key]
                if val is not None:
                    return str(val).strip()
            k_lower = key.lower()
            for k, val in item.items():
                if k.lower() == k_lower:
                    if val is not None:
                        return str(val).strip()
        return "Unknown"

    so_indicators = ["soNumber", "so_number", "doNumber", "do_number"]
    co_indicators = ["coNumber", "co_number", "contractNumber", "contract_number", "pay_id", "payid", "PayId"]

    # 1. Process Sales Orders (SO) / OBD
    if default_process is None or default_process.upper() == "SO":
        for item in raw_so_list:
            if not isinstance(item, dict):
                continue
                
            process = str(item.get("process") or "").strip().upper()
            if default_process is not None:
                is_so = (default_process.upper() == "SO")
            else:
                if process in ("SO", "CO", "CONTRACT", "COLLECTION"):
                    is_so = (process == "SO")
                else:
                    is_so = (has_key_case_insensitive(item, so_indicators) or ("do_number" in item and not has_non_null_key(item, co_indicators)))
            if not is_so:
                continue

            server = get_server_allocation(item)
            tx_id = get_unique_id(item, so_keys)
            if tx_id is None:
                continue

            if is_so_pending(item, api_name):
                active_pending_ids.add(tx_id)
                track_and_alert_aging(tx_id, server, "SO", api_name, config)

            if not filter_pending or is_so_pending(item, api_name):
                if server not in server_so_ids:
                    server_so_ids[server] = set()
                server_so_ids[server].add(tx_id)

    # 2. Process Collection Orders (CO) / Contract
    if default_process is None or default_process.upper() == "CO":
        for item in raw_co_list:
            if not isinstance(item, dict):
                continue

            process = str(item.get("process") or "").strip().upper()
            if default_process is not None:
                is_co = (default_process.upper() == "CO")
            else:
                if process in ("SO", "CO", "CONTRACT", "COLLECTION"):
                    is_co = (process in ("CO", "CONTRACT", "COLLECTION"))
                else:
                    is_co = has_non_null_key(item, co_indicators)
            if not is_co:
                continue

            server = get_server_allocation(item)
            
            # Get the unique ID for CO, fallback to TransactionId if pay_id is missing
            co_id = get_unique_id(item, ["pay_id", "payid", "PayId"])
            if co_id is None:
                co_id = get_unique_id(item, ["Transaction_ID", "TransactionId", "transaction_id", "transactionid"])
                    
            if co_id is None:
                continue

            if is_co_pending(item, api_name):
                active_pending_ids.add(co_id)
                track_and_alert_aging(co_id, server, "CO", api_name, config)

            if not filter_pending or is_co_pending(item, api_name):
                if server not in server_co_ids:
                    server_co_ids[server] = set()
                server_co_ids[server].add(co_id)

    # Compile server statistics
    all_servers = set(server_so_ids.keys()) | set(server_co_ids.keys())
    server_stats = {}
    for server in all_servers:
        server_stats[server] = {
            "pending_so": len(server_so_ids.get(server, set())),
            "pending_co": len(server_co_ids.get(server, set())),
            "so_ids": list(server_so_ids.get(server, set())),
            "co_ids": list(server_co_ids.get(server, set()))
        }

    total_so = sum(len(ids) for ids in server_so_ids.values())
    total_co = sum(len(ids) for ids in server_co_ids.values())

    # Memory cleanup for completed/disappeared items
    if api_name:
        with PENDING_LOCK:
            seen_keys_to_remove = [k for k in PENDING_FIRST_SEEN.keys() if k[1] == api_name and k[2] not in active_pending_ids]
            for k in seen_keys_to_remove:
                del PENDING_FIRST_SEEN[k]
            alert_keys_to_remove = [k for k in PENDING_ALERTS_SENT.keys() if k[1] == api_name and k[2] not in active_pending_ids]
            for k in alert_keys_to_remove:
                del PENDING_ALERTS_SENT[k]

    print(f"[{datetime.datetime.now()}] Parsing complete. Total pending SO: {total_so}, Total pending CO: {total_co}.")

    return {
        "server_stats": server_stats,
        "total_pending_so": total_so,
        "total_pending_co": total_co
    }

def fetch_and_parse(business_date, api_config, config=None):
    """Fetches raw data from a specific API template and parses pending stats."""
    template = api_config.get("url_template", "")
    if not template or "YOUR_" in template:
        raise ValueError(f"API template is not configured: {api_config.get('name')}")
        
    start_date = business_date - datetime.timedelta(days=1)
    end_date = business_date
    start_date_str = start_date.strftime("%Y-%m-%d")
    end_date_str = end_date.strftime("%Y-%m-%d")

    url = template
    business_date_str = business_date.strftime("%Y-%m-%d")
    if "{business_date}" in url:
        url = url.replace("{business_date}", business_date_str)
    if "{start_date}" in url or "{end_date}" in url:
        url = url.replace("{start_date}", start_date_str).replace("{end_date}", end_date_str)
    elif "{date}" in url:
        if url.count("{date}") == 2:
            url = url.replace("{date}", start_date_str, 1).replace("{date}", end_date_str, 1)
        else:
            url = url.replace("{date}", end_date_str)
            
    print(f"[{datetime.datetime.now()}] Fetching data from: {url}")
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    custom_headers = api_config.get("headers")
    if custom_headers and isinstance(custom_headers, dict):
        for h_key, h_val in custom_headers.items():
            headers[h_key] = h_val

    req = urllib.request.Request(
        url,
        headers=headers
    )
    
    with urllib.request.urlopen(req, timeout=15) as response:
        raw_data = response.read().decode('utf-8')
        data = json.loads(raw_data)
        return parse_psa_data(
            data,
            filter_pending=api_config.get("filter_pending", True),
            default_process=api_config.get("default_process"),
            api_name=api_config.get("name"),
            config=config
        )

def fetch_cv_sorting_data(config):
    """Fetches CV Sorting task statistics from private development API and groups by status."""
    url = config.get("cv_sorting_api_url", "")
    if not url or "YOUR_" in url:
        return None
        
    print(f"[{datetime.datetime.now()}] Fetching CV sorting data from: {url}")
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    cookie = config.get("cv_sorting_api_cookie", "")
    if cookie:
        headers["Cookie"] = cookie

    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=15) as response:
        raw_data = response.read().decode('utf-8')
        res_json = json.loads(raw_data)
        
    data = res_json.get("data", [])
    
    # We want task_no values grouped by status
    # Focused statuses: pending, downloading, downloaded, notfound, screening
    stats = {
        "pending": [],
        "downloading": [],
        "downloaded": [],
        "notfound": [],
        "screening": []
    }
    
    for item in data:
        if not isinstance(item, dict):
            continue
        status = str(item.get("status") or "").strip().lower()
        task_no = str(item.get("task_no") or "").strip()
        if task_no and status in stats:
            # Capitalize task number as requested by user (e.g. TASK3 -> Task3)
            stats[status].append(task_no.capitalize())
            
    # Sort task lists for clean presentation
    for status in stats:
        stats[status].sort()
        
    return stats

def fetch_rpa_config_data(config):
    """Fetches RPA configuration and extracts PROFILECOUNT."""
    url = config.get("rpa_config_api_url", "")
    if not url or "YOUR_" in url:
        return None
        
    print(f"[{datetime.datetime.now()}] Fetching RPA config from: {url}")
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    cookie = config.get("rpa_config_api_cookie", "")
    if cookie:
        headers["Cookie"] = cookie

    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=15) as response:
        raw_data = response.read().decode('utf-8')
        res_json = json.loads(raw_data)
        
    profile_count = str(res_json.get("PROFILECOUNT") or "0").strip()
    return {"profile_count": profile_count}

def fetch_all_apis(business_date, config):
    """Fetches and aggregates pending stats from all configured API templates in parallel."""
    apis = config.get("apis", [])
    results = {}
    
    # Filter out active configurations
    active_apis = []
    for api_config in apis:
        url_template = api_config.get("url_template", "")
        if url_template and "YOUR_" not in url_template:
            active_apis.append(api_config)
            
    cv_url = config.get("cv_sorting_api_url", "")
    rpa_url = config.get("rpa_config_api_url", "")
    
    if not active_apis and not cv_url and not rpa_url:
        raise ValueError("No API templates are configured. Please set the API_URL_TEMPLATE variables.")

    # Determine thread pool size
    num_tasks = len(active_apis)
    if cv_url:
        num_tasks += 1
    if rpa_url:
        num_tasks += 1

    def task_wrapper(func, name):
        try:
            res = func()
            return name, res, None
        except Exception as e:
            return name, None, e

    # Fetch all active APIs in parallel using ThreadPoolExecutor
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, num_tasks)) as executor:
        futures = []
        for api_config in active_apis:
            api_name = api_config.get("name", "Unknown API")
            futures.append(executor.submit(
                task_wrapper,
                lambda api_cfg=api_config: fetch_and_parse(business_date, api_cfg, config),
                api_name
            ))
            
        if cv_url:
            futures.append(executor.submit(
                task_wrapper,
                lambda: fetch_cv_sorting_data(config),
                "_cv_sorting"
            ))
            
        if rpa_url:
            futures.append(executor.submit(
                task_wrapper,
                lambda: fetch_rpa_config_data(config),
                "_rpa_config"
            ))
            
        for future in concurrent.futures.as_completed(futures):
            name, stats, err = future.result()
            if err:
                print(f"[{datetime.datetime.now()}] Error fetching from {name}: {err}")
            else:
                results[name] = stats
                
    return results

def send_telegram_notification(message, config, reply_markup=None):
    """Sends a formatted message to Telegram. Returns (success, error_message)."""
    token = config.get("telegram_bot_token")
    chat_id = config.get("telegram_chat_id")
    if not token or not chat_id or "YOUR_TELEGRAM" in token or "YOUR_TELEGRAM" in chat_id:
        err_msg = "Telegram credentials not configured. Skipping message dispatch."
        print(f"[{datetime.datetime.now()}] {err_msg}")
        return False, err_msg

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message
    }
    if reply_markup is not None:
        payload["reply_markup"] = reply_markup
    else:
        payload["reply_markup"] = {
            "keyboard": [
                [{"text": "/feature"}, {"text": "/status"}, {"text": "/report"}],
                [{"text": "/f1"}, {"text": "/f2"}, {"text": "/f3"}, {"text": "/f4"}, {"text": "/f5"}, {"text": "/f6"}, {"text": "/f7"}, {"text": "/f8"}, {"text": "/f9"}],
                [{"text": "/o1"}, {"text": "/o2"}, {"text": "/o3"}, {"text": "/o4"}, {"text": "/o5"}, {"text": "/o6"}, {"text": "/o7"}, {"text": "/o8"}, {"text": "/o9"}]
            ],
            "resize_keyboard": True,
            "is_persistent": True
        }
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0"
        },
        method="POST"
    )
    try:
        print(f"[{datetime.datetime.now()}] Sending notification to Telegram...")
        with urllib.request.urlopen(req, timeout=10) as response:
            res = json.loads(response.read().decode('utf-8'))
            success = res.get("ok", False)
            if success:
                print(f"[{datetime.datetime.now()}] Telegram notification sent successfully.")
                return True, None
            else:
                err_msg = f"Telegram API error: {res}"
                print(f"[{datetime.datetime.now()}] {err_msg}")
                return False, err_msg
    except Exception as e:
        err_msg = f"Exception sending Telegram notification: {e}"
        return False, err_msg

def answer_callback_query(callback_query_id, config):
    token = config.get("telegram_bot_token")
    if not token:
        return
    url = f"https://api.telegram.org/bot{token}/answerCallbackQuery"
    payload = {"callback_query_id": callback_query_id}
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            response.read()
    except Exception:
        pass

def is_time_for_pending_alert(dt, end_hour):
    """
    Checks if local time is between 11:01 PM (23:01) and 12:59 AM next day (00:59).
    """
    current_time = dt.time()
    start_time = datetime.time(23, 1, 0)
    end_time = datetime.time(0, 59, 0)
    
    if current_time >= start_time or current_time <= end_time:
        return True
    return False

def check_and_send_pending_alert(business_date, config, force=False):
    """Checks if there is any pending data on the special check URL, and if so sends a Telegram alert."""
    template = config.get("psa_pending_check_url_template", "")
    if not template or "YOUR_" in template:
        apis = config.get("apis", [])
        psa_api = next((a for a in apis if "psa" in a.get("name", "").lower()), None)
        if psa_api:
            template = psa_api.get("url_template", "")
            
    if not template or "YOUR_" in template:
        return
        
    local_now = get_local_time(config)
    if not force:
        # Check if active monitoring hours
        _, active = get_business_date_and_active(
            local_now,
            config.get("monitoring_start_hour", 9),
            config.get("monitoring_end_hour", 1)
        )
        if not active:
            print(f"[{datetime.datetime.now()}] Extra pending check skipped: Outside active monitoring hours.")
            return

    # Replace date placeholder
    date_str = business_date.strftime("%Y-%m-%d")
    url = template.replace("{business_date}", date_str).replace("{date}", date_str)
    
    print(f"[{datetime.datetime.now()}] Running extra pending check from: {url}")
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            raw_data = response.read().decode('utf-8')
            data = json.loads(raw_data)
            stats = parse_psa_data(data, filter_pending=True, api_name="PSA_PENDING_CHECK", config=config)
            total_so = stats.get("total_pending_so", 0)
            total_co = stats.get("total_pending_co", 0)
            if total_so > 0 or total_co > 0:
                print(f"[{datetime.datetime.now()}] Extra pending check detected pending data (SO: {total_so}, CO: {total_co}). Sending alert...")
                alert_msg = f"PSA Data still pending\n(Pending SO: {total_so}, Pending CO: {total_co})"
                send_telegram_notification(alert_msg, config)
            else:
                print(f"[{datetime.datetime.now()}] Extra pending check complete: No pending data.")
    except Exception as e:
        print(f"[{datetime.datetime.now()}] Error during extra pending check: {e}")

def pending_alert_scheduler_loop(stop_event):
    """Background thread that runs the extra pending alert check every 10 minutes aligned."""
    print(f"[{datetime.datetime.now()}] Background pending alert scheduler thread started.")
    while not stop_event.is_set():
        config = load_config()
        # Only check if configured or fallback PSA API is available
        template = config.get("psa_pending_check_url_template", "")
        if not template or "YOUR_" in template:
            apis = config.get("apis", [])
            psa_api = next((a for a in apis if "psa" in a.get("name", "").lower()), None)
            if psa_api:
                template = psa_api.get("url_template", "")
                
        if not template or "YOUR_" in template:
            if stop_event.wait(60):
                break
            continue
            
        interval = 10
        local_now = get_local_time(config)
        minutes_to_next = interval - (local_now.minute % interval)
        seconds_to_next = minutes_to_next * 60 - local_now.second - (local_now.microsecond / 1_000_000.0)
        if seconds_to_next <= 0:
            seconds_to_next = interval * 60
            
        if stop_event.wait(seconds_to_next):
            break
            
        local_check = get_local_time(config)
        end_hour = config.get("monitoring_end_hour", 1)
        poll_interval = config.get("poll_interval_minutes", 30)
        
        # Only run if we are inside the late-night window and current instance is active
        if is_time_for_pending_alert(local_check, end_hour) and is_current_instance_active():
            # Skip checking if it aligns with the main poll interval to avoid duplicates
            if local_check.minute % poll_interval != 0:
                business_date, _ = get_business_date_and_active(
                    local_check,
                    config.get("monitoring_start_hour", 9),
                    end_hour
                )
                check_and_send_pending_alert(business_date, config, force=True)

def format_telegram_message(stats, business_date, config):
    """Formats the parsed counts, server breakdown, and local report times into a Markdown message."""
    date_str = business_date.strftime("%Y-%m-%d")
    yesterday = business_date - datetime.timedelta(days=1)
    yesterday_str = yesterday.strftime("%Y-%m-%d")

    # Calculate local report and next scheduled time
    local_now = get_local_time(config)
    report_time_str = local_now.strftime("%Y-%m-%d %H:%M:%S")
    
    std_interval = config.get("poll_interval_minutes", 30)
    std_minutes_to_next = std_interval - (local_now.minute % std_interval)
    std_next = local_now + datetime.timedelta(minutes=std_minutes_to_next)
    std_next = std_next.replace(second=0, microsecond=0)
    
    candidates = [std_next]
    w_start = local_now.replace(hour=11, minute=1, second=0, microsecond=0)
    if w_start > local_now:
        candidates.append(w_start)
    for m in [10, 20, 30, 40, 50]:
        t = local_now.replace(hour=11, minute=m, second=0, microsecond=0)
        if t > local_now:
            candidates.append(t)
    t_12_00 = local_now.replace(hour=12, minute=0, second=0, microsecond=0)
    if t_12_00 > local_now:
        candidates.append(t_12_00)
    for m in [10, 20, 30, 40, 50]:
        t = local_now.replace(hour=12, minute=m, second=0, microsecond=0)
        if t > local_now:
            candidates.append(t)
    w_end = local_now.replace(hour=12, minute=59, second=0, microsecond=0)
    if w_end > local_now:
        candidates.append(w_end)
        
    future_candidates = [c for c in candidates if c > local_now]
    next_report = min(future_candidates)
    next_report_str = next_report.strftime("%Y-%m-%d %H:%M:%S")

    # Header
    lines = [
        f"📅 Business Date: {date_str}",
        f"📅 API Date Range: {yesterday_str} to {date_str}",
        f"🕒 Report Time: {report_time_str} (Local)",
        f"⏰ Next Report: {next_report_str} (Local)"
    ]

    # Retrieve all configured APIs to maintain their config order
    apis = config.get("apis", [])
    
    # Determine the set of APIs to format. Include any additional ones from stats.
    apis_to_process = []
    processed_names = set()
    
    for api_config in apis:
        name = api_config.get("name")
        if name and name in stats:
            apis_to_process.append((name, api_config))
            processed_names.add(name)
            
    for name in stats:
        if name not in processed_names:
            # Fallback for APIs not explicitly in config list but present in stats
            apis_to_process.append((name, {}))

    for name, api_config in apis_to_process:
        if name.startswith("_"):
            continue
        api_stats = stats[name]
        
        # Determine display_name based on name (case-insensitive checks)
        name_lower = name.lower()
        if name_lower in ("psa", "api_1", "psa_pending_orders", "psa pending orders"):
            display_name = "PSA Pending Orders"
        elif name_lower in ("api_2", "cement_so_collection", "smartsales_pending_orders", "smartsales pending orders"):
            display_name = "SmartSales Pending Orders"
        elif name_lower in ("api_5", "freshlpg_pending_orders", "freshlpg pending orders", "freshlpg"):
            display_name = "FreshLPG Pending Orders"
        elif name_lower in ("api_3", "cement_obd_program", "smartsales_obd_pending", "smartsales obd pending", "smartsales_obd"):
            display_name = "SmartSales OBD Pending"
        elif name_lower in ("api_4", "sap_contract_create", "sap_contract_pending", "sap contract pending", "sap_contract"):
            display_name = "SAP Contract Pending"
        else:
            display_name = name.replace("_", " ")
        
        # Determine labels and default processes robustly
        default_process = api_config.get("default_process")
        if default_process is None:
            if "obd" in name_lower or name_lower == "api_3":
                default_process = "SO"
            elif "contract" in name_lower or name_lower == "api_4":
                default_process = "CO"
                
        label_so = api_config.get("label_so")
        if label_so is None:
            if "obd" in name_lower or name_lower == "api_3":
                label_so = "OBD"
            else:
                label_so = "Sales Orders (SO)"
                
        label_co = api_config.get("label_co")
        if label_co is None:
            if "contract" in name_lower or name_lower == "api_4":
                label_co = "CON"
            else:
                label_co = "Collection Orders (CO)"
        
        # Server allocation short labels
        short_so = "SO" if label_so == "Sales Orders (SO)" else label_so
        short_co = "CO" if label_co == "Collection Orders (CO)" else label_co
        
        # Append empty line and section title
        lines.append("")
        lines.append(f"📢 {display_name} Summary")
        lines.append("📊 Total Pending:")
        
        total_so = api_stats.get("total_pending_so", 0)
        total_co = api_stats.get("total_pending_co", 0)
        
        if default_process is None:
            lines.append(f"• {label_so}: {total_so}")
            lines.append(f"• {label_co}: {total_co}")
        elif default_process.upper() == "SO":
            lines.append(f"• {label_so}: {total_so}")
        elif default_process.upper() == "CO":
            lines.append(f"• {label_co}: {total_co}")
            
        skip_server = ("contract" in name_lower or name_lower == "api_4")
        if not skip_server:
            server_stats = api_stats.get("server_stats", {})
            if server_stats:
                lines.append("")
                lines.append("🖥️ By Server Allocation:")
                for server in sorted(server_stats.keys()):
                    s_stats = server_stats[server]
                    server_so = s_stats.get("pending_so", 0)
                    server_co = s_stats.get("pending_co", 0)
                    
                    if default_process is None:
                        lines.append(f"• {server}: {short_so}: {server_so} | {short_co}: {server_co}")
                    elif default_process.upper() == "SO":
                        if "obd" in name_lower or name_lower == "api_3":
                            so_ids = s_stats.get("so_ids", [])
                            unique_ids_str = ", ".join(sorted(str(x) for x in set(so_ids)))
                            plan_str = f" (Plan_Id - {unique_ids_str})" if unique_ids_str else ""
                            lines.append(f"• {server}: {short_so}: {server_so}{plan_str}")
                        else:
                            lines.append(f"• {server}: {short_so}: {server_so}")
                    elif default_process.upper() == "CO":
                        lines.append(f"• {server}: {short_co}: {server_co}")
            else:
                lines.append("")
                lines.append("ℹ️ No active server allocations detected.")

    # Format CV Sorting Section if present in stats
    if "_cv_sorting" in stats or "_rpa_config" in stats:
        lines.append("")
        lines.append("CV Sorting -")
        
        cv_stats = stats.get("_cv_sorting")
        if cv_stats:
            # We want specific statuses in a specific order:
            # Pending, Downloading, Downloaded, Not Found, Screening
            status_mappings = [
                ("pending", "Pending"),
                ("downloading", "Downloading"),
                ("downloaded", "Downloaded"),
                ("notfound", "Not Found"),
                ("screening", "Screening")
            ]
            for status_key, status_label in status_mappings:
                task_list = cv_stats.get(status_key, [])
                count = len(task_list)
                if count > 0:
                    tasks_str = ", ".join(task_list)
                    lines.append(f"{status_label} - {count} ({tasks_str})")
                else:
                    lines.append(f"{status_label} - {count}")
        else:
            lines.append("Pending - 0")
            lines.append("Downloading - 0")
            lines.append("Downloaded - 0")
            lines.append("Not Found - 0")
            lines.append("Screening - 0")
            
        rpa_stats = stats.get("_rpa_config")
        profile_count = rpa_stats.get("profile_count", "0") if rpa_stats else "0"
        lines.append(f"Profile Count - {profile_count}")

    return "\n".join(lines)

def register_bot_commands(config):
    """Registers the bot command menu dynamically on Telegram."""
    token = config.get("telegram_bot_token")
    if not token or "YOUR_TELEGRAM" in token:
        return
        
    url = f"https://api.telegram.org/bot{token}/setMyCommands"
    commands_list = [
        {"command": "feature", "description": "List all features & current threshold status"},
        {"command": "status", "description": "Get immediate report of all active APIs"},
        {"command": "report", "description": "Get immediate report of all active APIs"},
        {"command": "f1", "description": "PSA SO checker threshold"},
        {"command": "o1", "description": "Turn off PSA SO checker"},
        {"command": "f2", "description": "PSA CO checker threshold"},
        {"command": "o2", "description": "Turn off PSA CO checker"},
        {"command": "f3", "description": "SmartSales OBD checker threshold"},
        {"command": "o3", "description": "Turn off SmartSales OBD checker"},
        {"command": "f4", "description": "Cement SO checker threshold"},
        {"command": "o4", "description": "Turn off Cement SO checker"},
        {"command": "f5", "description": "Cement CO checker threshold"},
        {"command": "o5", "description": "Turn off Cement CO checker"},
        {"command": "f6", "description": "SAP Contract checker threshold"},
        {"command": "o6", "description": "Turn off SAP Contract checker"},
        {"command": "f7", "description": "Off-Hours SmartSales OBD checker threshold"},
        {"command": "f7_start", "description": "Set start hour for f7 off-hours window"},
        {"command": "f7_end", "description": "Set end hour for f7 off-hours window"},
        {"command": "f7_user", "description": "Set CallMeBot target users/numbers"},
        {"command": "o7", "description": "Turn off f7 off-hours OBD checker and voice calls"},
        {"command": "f7_test", "description": "Initiate a test CallMeBot voice call instantly"},
        {"command": "f8", "description": "FreshLPG SO checker threshold"},
        {"command": "o8", "description": "Turn off FreshLPG SO checker"},
        {"command": "f9", "description": "FreshLPG CO checker threshold"},
        {"command": "o9", "description": "Turn off FreshLPG CO checker"}
    ]
    
    try:
        data = json.dumps({"commands": commands_list}).encode('utf-8')
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "Mozilla/5.0"
            },
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=5) as response:
            res = json.loads(response.read().decode('utf-8'))
            print(f"[{datetime.datetime.now()}] Bot commands registration response: {res}")
    except Exception as e:
        print(f"[{datetime.datetime.now()}] Failed to register bot commands: {e}")

def register_webhook(public_url, config):
    """Registers the Telegram Webhook dynamically."""
    token = config.get("telegram_bot_token")
    if not token or "YOUR_TELEGRAM" in token:
        return
        
    webhook_url = f"{public_url.rstrip('/')}/webhook"
    url = f"https://api.telegram.org/bot{token}/setWebhook?url={webhook_url}"
    try:
        print(f"[{datetime.datetime.now()}] Registering Telegram Webhook: {webhook_url}")
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0"}
        )
        with urllib.request.urlopen(req, timeout=5) as response:
            res = json.loads(response.read().decode('utf-8'))
            print(f"[{datetime.datetime.now()}] Webhook registration response: {res}")
        register_bot_commands(config)
    except Exception as e:
        print(f"[{datetime.datetime.now()}] Failed to register webhook: {e}")

def run_scheduled_check(business_date=None, force=False):
    """Retrieves config, fetches pending data, and dispatches to Telegram if active or forced."""
    global LAST_API_POLL_SUCCESS
    config = load_config()
    if business_date is None:
        local_now = get_local_time(config)
        business_date, active = get_business_date_and_active(
            local_now,
            config.get("monitoring_start_hour", 9),
            config.get("monitoring_end_hour", 1)
        )
        if not active and not force:
            print(f"[{datetime.datetime.now()}] Outside monitoring hours and force=False. Check skipped.")
            return False

    local_now = get_local_time(config)
    # 11:01 PM to 12:59 AM check: only run check_and_send_pending_alert
    if is_in_10min_psa_window(local_now) and not force:
        print(f"[{datetime.datetime.now()}] Inside 11:01 PM-12:59 AM window. Running ONLY PSA pending filter check.")
        try:
            check_and_send_pending_alert(business_date, config, force=True)
            return True
        except Exception as e:
            print(f"[{datetime.datetime.now()}] Error during PSA pending filter check: {e}")
            return False

    try:
        stats = fetch_all_apis(business_date, config)
        msg = format_telegram_message(stats, business_date, config)
        ok, err = send_telegram_notification(msg, config)
        if ok:
            check_and_send_pending_alert(business_date, config)
        return ok
    except Exception as e:
        LAST_API_POLL_SUCCESS = False
        print(f"[{datetime.datetime.now()}] Error during scheduled monitoring check: {e}")
        return False

def aging_alerts_scheduler_loop(stop_event):
    """Background thread that runs the aging alert check every 1 minute to detect threshold crossings."""
    log_message("Background aging alert checker thread started.")
    while not stop_event.is_set():
        if stop_event.wait(60):
            break
            
        # Embedded 3-day log rotation
        rotate_local_logs()
            
        global PSA_SO_PENDING_THRESHOLD_MINUTES, PSA_CO_PENDING_THRESHOLD_MINUTES, OBD_PENDING_THRESHOLD_MINUTES
        global CEMENTAPI_SO_PENDING_THRESHOLD_MINUTES, CEMENTAPI_CO_PENDING_THRESHOLD_MINUTES
        global CONTRACTAPI_CO_PENDING_THRESHOLD_MINUTES
        global SMARTSALES_OBD_OFFHOURS_THRESHOLD_MINUTES, OBD_OFFHOURS_START_HOUR, OBD_OFFHOURS_END_HOUR
        global FRESHLPG_SO_PENDING_THRESHOLD_MINUTES, FRESHLPG_CO_PENDING_THRESHOLD_MINUTES
        global LAST_API_POLL_SUCCESS
        
        if (PSA_SO_PENDING_THRESHOLD_MINUTES <= 0 and 
            PSA_CO_PENDING_THRESHOLD_MINUTES <= 0 and 
            OBD_PENDING_THRESHOLD_MINUTES <= 0 and 
            CEMENTAPI_SO_PENDING_THRESHOLD_MINUTES <= 0 and 
            CEMENTAPI_CO_PENDING_THRESHOLD_MINUTES <= 0 and
            CONTRACTAPI_CO_PENDING_THRESHOLD_MINUTES <= 0 and
            SMARTSALES_OBD_OFFHOURS_THRESHOLD_MINUTES <= 0 and
            FRESHLPG_SO_PENDING_THRESHOLD_MINUTES <= 0 and
            FRESHLPG_CO_PENDING_THRESHOLD_MINUTES <= 0):
            continue
            
        config = load_config()
        local_now = get_local_time(config)
        business_date, active = get_business_date_and_active(
            local_now,
            config.get("monitoring_start_hour", 9),
            config.get("monitoring_end_hour", 1)
        )
        
        is_f7_active = is_hour_in_range(local_now.hour, OBD_OFFHOURS_START_HOUR, OBD_OFFHOURS_END_HOUR) and (SMARTSALES_OBD_OFFHOURS_THRESHOLD_MINUTES > 0)
        
        # Skip if outside active hours and off-hours OBD is inactive, or if current instance is standby
        if (not active and not is_f7_active) or not is_current_instance_active():
            continue
            
        try:
            fetch_all_apis(business_date, config)
            LAST_API_POLL_SUCCESS = True
        except Exception as e:
            LAST_API_POLL_SUCCESS = False
            log_message(f"Error in background aging alert check loop: {e}")

def scheduler_loop(stop_event):
    """Periodic scheduler running on a background thread aligned to block boundaries."""
    print(f"[{datetime.datetime.now()}] Background monitoring thread started.")
    
    # We removed the immediate startup check to prevent spamming notifications 
    # when cloud hosting instances (like Render) restart or wake up from sleep.

    while not stop_event.is_set():
        config = load_config()
        local_now = get_local_time(config)

        # Standard interval
        std_interval = config.get("poll_interval_minutes", 30)
        
        # Calculate standard next report time
        std_minutes_to_next = std_interval - (local_now.minute % std_interval)
        std_next = local_now + datetime.timedelta(minutes=std_minutes_to_next)
        std_next = std_next.replace(second=0, microsecond=0)
        
        candidates = [std_next]
        
        # Add 10-min alignment candidates for 11:01 PM to 12:59 AM window (23:01 to 00:59)
        w_start = local_now.replace(hour=23, minute=1, second=0, microsecond=0)
        if w_start > local_now:
            candidates.append(w_start)
            
        for m in [10, 20, 30, 40, 50]:
            t = local_now.replace(hour=23, minute=m, second=0, microsecond=0)
            if t > local_now:
                candidates.append(t)
                
        base_day = local_now if local_now.hour == 0 else (local_now + datetime.timedelta(days=1))
        t_00_00 = base_day.replace(hour=0, minute=0, second=0, microsecond=0)
        if t_00_00 > local_now:
            candidates.append(t_00_00)
            
        for m in [10, 20, 30, 40, 50]:
            t = base_day.replace(hour=0, minute=m, second=0, microsecond=0)
            if t > local_now:
                candidates.append(t)
                
        w_end = base_day.replace(hour=0, minute=59, second=0, microsecond=0)
        if w_end > local_now:
            candidates.append(w_end)
            
        # Find earliest candidate strictly in the future
        future_candidates = [c for c in candidates if c > local_now]
        next_report = min(future_candidates)
        
        seconds_to_next = (next_report - local_now).total_seconds()
        if seconds_to_next <= 0:
            seconds_to_next = 60.0

        print(f"[{datetime.datetime.now()}] Next poll aligned check in {seconds_to_next:.1f} seconds (at {next_report.strftime('%Y-%m-%d %H:%M:%S')}).")
        if stop_event.wait(seconds_to_next):
            break

        local_check = get_local_time(config)
        business_date, active = get_business_date_and_active(
            local_check,
            config.get("monitoring_start_hour", 9),
            config.get("monitoring_end_hour", 1)
        )
        if active:
            if is_current_instance_active():
                print(f"[{datetime.datetime.now()}] Aligned time reached. Running monitoring check...")
                run_scheduled_check(business_date)
            else:
                print(f"[{datetime.datetime.now()}] Aligned time reached. Instance is standby. Skipping check.")
        else:
            print(f"[{datetime.datetime.now()}] Aligned time reached. Outside active monitoring hours. Skipping check.")

class MockHandler:
    def __init__(self, update_dict):
        import io
        body = json.dumps(update_dict).encode('utf-8')
        self.rfile = io.BytesIO(body)
        self.headers = {"Content-Length": str(len(body))}
        self.path = "/webhook"
    def send_json_response(self, status_code, body):
        pass
    def send_response(self, *args, **kwargs):
        pass
    def send_header(self, *args, **kwargs):
        pass
    def end_headers(self, *args, **kwargs):
        pass

def process_long_poll_update(update, config):
    try:
        mock_handler = MockHandler(update)
        RequestHandler.do_POST(mock_handler)
    except Exception as e:
        log_message(f"Error processing long polling update: {e}")

def check_render_health(config):
    render_url = os.environ.get("RENDER_EXTERNAL_URL") or config.get("render_external_url")
    if not render_url:
        return False, "Render URL not configured"
    url = render_url.rstrip('/') + "/"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=3) as resp:
            status = resp.status
            if status == 200:
                print(f"[{datetime.datetime.now()}] Render health check: SUCCEEDED ({url}) - HTTP 200 OK")
                return True, "HTTP 200 OK"
            else:
                print(f"[{datetime.datetime.now()}] Render health check: FAILED ({url}) - HTTP Status {status}")
                return False, f"HTTP Status {status}"
    except Exception as e:
        print(f"[{datetime.datetime.now()}] Render health check: FAILED ({url}) - {e}")
        return False, str(e)

def check_local_health(config):
    global LAST_LOCAL_HEARTBEAT
    if LAST_LOCAL_HEARTBEAT == 0.0:
        print(f"[{datetime.datetime.now()}] Local health check: FAILED - No heartbeat received yet")
        return False, "No heartbeat received yet"
    elapsed = time.time() - LAST_LOCAL_HEARTBEAT
    if elapsed <= 45.0:
        print(f"[{datetime.datetime.now()}] Local health check: SUCCEEDED - Heartbeat received {elapsed:.1f}s ago")
        return True, f"Heartbeat received {elapsed:.1f}s ago"
    else:
        print(f"[{datetime.datetime.now()}] Local health check: FAILED - Heartbeat timeout (last seen {elapsed:.1f}s ago)")
        return False, f"Heartbeat timeout (last seen {elapsed:.1f}s ago)"

def is_current_instance_active():
    global ACTIVE_ENV
    is_render = (os.environ.get("RENDER") is not None)
    if is_render:
        return ACTIVE_ENV == "Render"
    else:
        return ACTIVE_ENV == "Local"

def handle_pending_threshold_update(handler, var_name, val, clear_args, config):
    global USER_CONVERSATION_STATE, PENDING_CONFIG_UPDATE
    PENDING_CONFIG_UPDATE = {
        "var_name": var_name,
        "val": val,
        "clear_args": clear_args
    }
    USER_CONVERSATION_STATE = "AWAITING_APPLY_MODE"
    msg = (
        f"Threshold value '{val}' received for {var_name}.\n\n"
        "Apply to:\n"
        "1. Active Only (temporary)\n"
        "2. Persistent (save to defaults)\n\n"
        "Please reply with 1 or 2 (or type 'cancel' to abort)."
    )
    send_telegram_notification(msg, config)
    handler.send_json_response(200, {"status": "ok", "message": msg})

# Mapping from feature keys to variable names and metadata
CONV_FEATURE_MAP = {
    "f1": {
        "var": "PSA_SO_PENDING_THRESHOLD_MINUTES",
        "default_var": "PSA_SO_PENDING_THRESHOLD_MINUTES_DEFAULT",
        "label": "psa_so_pending_threshold_minutes",
        "default_prompt": "psa_default_so_pending_threshold_minutes",
        "current_prompt": "psa_so_pending_threshold_minutes",
        "fallback_default": 20,
        "clear_args": [["SO", "PSA"]]
    },
    "f2": {
        "var": "PSA_CO_PENDING_THRESHOLD_MINUTES",
        "default_var": "PSA_CO_PENDING_THRESHOLD_MINUTES_DEFAULT",
        "label": "psa_co_pending_threshold_minutes",
        "default_prompt": "psa_default_co_pending_threshold_minutes",
        "current_prompt": "psa_co_pending_threshold_minutes",
        "fallback_default": 20,
        "clear_args": [["CO", "PSA"]]
    },
    "f3": {
        "var": "OBD_PENDING_THRESHOLD_MINUTES",
        "default_var": "OBD_PENDING_THRESHOLD_MINUTES_DEFAULT",
        "label": "Smartsales_obd_pending_threshold_minutes",
        "default_prompt": "smartsales_default_obd_pending_threshold_minutes",
        "current_prompt": "Smartsales_obd_pending_threshold_minutes",
        "fallback_default": 20,
        "clear_args": [["OBD"]]
    },
    "f4": {
        "var": "CEMENTAPI_SO_PENDING_THRESHOLD_MINUTES",
        "default_var": "CEMENTAPI_SO_PENDING_THRESHOLD_MINUTES_DEFAULT",
        "label": "Smartsales_so_pending_threshold_minutes",
        "default_prompt": "smartsales_default_so_pending_threshold_minutes",
        "current_prompt": "Smartsales_so_pending_threshold_minutes",
        "fallback_default": 20,
        "clear_args": [["SO", "API_2"], ["SO", "SmartSales_Pending_Orders"]]
    },
    "f5": {
        "var": "CEMENTAPI_CO_PENDING_THRESHOLD_MINUTES",
        "default_var": "CEMENTAPI_CO_PENDING_THRESHOLD_MINUTES_DEFAULT",
        "label": "Smartsales_co_pending_threshold_minutes",
        "default_prompt": "smartsales_default_co_pending_threshold_minutes",
        "current_prompt": "Smartsales_co_pending_threshold_minutes",
        "fallback_default": 20,
        "clear_args": [["CO", "API_2"], ["CO", "SmartSales_Pending_Orders"]]
    },
    "f6": {
        "var": "CONTRACTAPI_CO_PENDING_THRESHOLD_MINUTES",
        "default_var": "CONTRACTAPI_CO_PENDING_THRESHOLD_MINUTES_DEFAULT",
        "label": "SAP_Contract_pending_threshold_minutes",
        "default_prompt": "sap_contract_default_pending_threshold_minutes",
        "current_prompt": "SAP_Contract_pending_threshold_minutes",
        "fallback_default": 20,
        "clear_args": [["CO", "API_4"], ["CO", "SAP_Contract_Pending"]]
    },
    "f7": {
        "var": "SMARTSALES_OBD_OFFHOURS_THRESHOLD_MINUTES",
        "default_var": "SMARTSALES_OBD_OFFHOURS_THRESHOLD_MINUTES_DEFAULT",
        "label": "SMARTSALES_OBD_OFFHOURS_THRESHOLD_MINUTES",
        "default_prompt": "SMARTSALES_Default_OBD_OFFHOURS_THRESHOLD_MINUTES",
        "current_prompt": "SMARTSALES_OBD_OFFHOURS_THRESHOLD_MINUTES",
        "fallback_default": 10,
        "clear_args": [["OBD"]]
    },
    "f8": {
        "var": "FRESHLPG_SO_PENDING_THRESHOLD_MINUTES",
        "default_var": "FRESHLPG_SO_PENDING_THRESHOLD_MINUTES_DEFAULT",
        "label": "freshlpg_so_pending_threshold_minutes",
        "default_prompt": "freshlpg_default_so_pending_threshold_minutes",
        "current_prompt": "freshlpg_so_pending_threshold_minutes",
        "fallback_default": 20,
        "clear_args": [["SO", "API_5"], ["SO", "FreshLPG_Pending_Orders"]]
    },
    "f9": {
        "var": "FRESHLPG_CO_PENDING_THRESHOLD_MINUTES",
        "default_var": "FRESHLPG_CO_PENDING_THRESHOLD_MINUTES_DEFAULT",
        "label": "freshlpg_co_pending_threshold_minutes",
        "default_prompt": "freshlpg_default_co_pending_threshold_minutes",
        "current_prompt": "freshlpg_co_pending_threshold_minutes",
        "fallback_default": 20,
        "clear_args": [["CO", "API_5"], ["CO", "FreshLPG_Pending_Orders"]]
    },
    "f7_start": {
        "var": "OBD_OFFHOURS_START_HOUR",
        "default_var": "OBD_OFFHOURS_START_HOUR_DEFAULT",
        "label": "in which hour I want to start f7",
        "default_prompt": "default hour I want to start f7",
        "current_prompt": "in which hour I want to start f7.",
        "fallback_default": 0,
        "clear_args": [],
        "is_hour": True
    },
    "f7_end": {
        "var": "OBD_OFFHOURS_END_HOUR",
        "default_var": "OBD_OFFHOURS_END_HOUR_DEFAULT",
        "label": "in which hour I want to end f7",
        "default_prompt": "default hour I want to end f7",
        "current_prompt": "in which hour I want to end f7.",
        "fallback_default": 0,
        "clear_args": [],
        "is_hour": True
    },
    "f7_user": {
        "var": "CALLMEBOT_USER",
        "default_var": "CALLMEBOT_USER_DEFAULT",
        "label": "CallMeBot target users/numbers",
        "default_prompt": "default CallMeBot target users/numbers",
        "current_prompt": "call me target users/numbers.(default +8801838262248)",
        "fallback_default": "@UshDhar, +8801838262248",
        "clear_args": [],
        "is_user": True
    }
}

FEATURE_VARS = CONV_FEATURE_MAP

def telegram_api_call(method, payload, config):
    token = config.get("telegram_bot_token")
    if not token:
        return None
    url = f"https://api.telegram.org/bot{token}/{method}"
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0"
        },
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            return json.loads(response.read().decode('utf-8'))
    except Exception as e:
        print(f"[{datetime.datetime.now()}] Telegram API call {method} failed: {e}")
        return None

def start_feature_conversation(handler, feat_key, config):
    global USER_CONVERSATION_STATE
    USER_CONVERSATION_STATE = f"SELECT_MODE_{feat_key.upper()}"
    meta = CONV_FEATURE_MAP[feat_key]
    msg = f"Update options for {meta['label']}:"
    reply_markup = {
        "inline_keyboard": [
            [
                {"text": "Default", "callback_data": "default"},
                {"text": "Current", "callback_data": "current"},
                {"text": "None", "callback_data": "none"}
            ]
        ]
    }
    send_telegram_notification(msg, config, reply_markup=reply_markup)
    handler.send_json_response(200, {"status": "ok", "message": msg})

def handle_feature_trigger(handler, feat_key, config):
    start_feature_conversation(handler, feat_key, config)

def run_long_polling_loop(stop_event):
    global LONG_POLLING_ACTIVE, IS_STANDBY, ACTIVE_ENV
    if LONG_POLLING_ACTIVE:
        return
    LONG_POLLING_ACTIVE = True
    log_message("Telegram Long Polling thread started.")
    
    offset = 0
    while not stop_event.is_set():
        is_render = (os.environ.get("RENDER") is not None)
        if is_render or ACTIVE_ENV == "Render":
            time.sleep(2)
            continue
            
        config = load_config()
        token = config.get("telegram_bot_token")
        if not token:
            time.sleep(5)
            continue
            
        url = f"https://api.telegram.org/bot{token}/getUpdates?offset={offset}&timeout=20"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=25) as resp:
                res = json.loads(resp.read().decode('utf-8'))
                if res.get("ok"):
                    for update in res.get("result", []):
                        offset = update.get("update_id", 0) + 1
                        message = update.get("message") or update.get("edited_message")
                        if message:
                            process_long_poll_update(update, config)
        except Exception as e:
            time.sleep(2)

def takeover_failover_loop(stop_event):
    global PREFERRED_ENV, ACTIVE_ENV, IS_STANDBY, BOTH_DEAD_ALERT_SENT, LAST_API_POLL_SUCCESS, CONFIG_ERROR
    global LOCAL_CONSECUTIVE_SUCCESS, LOCAL_CONSECUTIVE_FAILURE
    global RENDER_CONSECUTIVE_SUCCESS, RENDER_CONSECUTIVE_FAILURE
    
    log_message("Background takeover/failover loop started.")
    while not stop_event.is_set():
        if stop_event.wait(15):
            break
            
        if CONFIG_ERROR:
            continue
            
        config = load_config()
        is_render = (os.environ.get("RENDER") is not None or os.environ.get("RENDER_SERVICE_ID") is not None)
        
        if is_render:
            # We are Render, target is Local
            alive, reason = check_local_health(config)
            if alive:
                LOCAL_CONSECUTIVE_SUCCESS += 1
                LOCAL_CONSECUTIVE_FAILURE = 0
            else:
                LOCAL_CONSECUTIVE_FAILURE += 1
                LOCAL_CONSECUTIVE_SUCCESS = 0
                
            if PREFERRED_ENV == "Local":
                if LOCAL_CONSECUTIVE_FAILURE >= 3 and ACTIVE_ENV == "Local":
                    ACTIVE_ENV = "Render"
                    IS_STANDBY = False
                    render_url = os.environ.get("RENDER_EXTERNAL_URL") or config.get("render_external_url")
                    if render_url:
                        threading.Thread(target=register_webhook, args=(render_url, config), daemon=True).start()
                    msg = "⚠️ Local Notifier is offline (3 consecutive timeout checks). Render has automatically taken over monitoring."
                    log_message(msg)
                    send_telegram_notification(msg, config)
                elif LOCAL_CONSECUTIVE_SUCCESS >= 3 and ACTIVE_ENV == "Render":
                    ACTIVE_ENV = "Local"
                    IS_STANDBY = True
                    token = config.get("telegram_bot_token")
                    if token:
                        delete_url = f"https://api.telegram.org/bot{token}/deleteWebhook"
                        try:
                            req = urllib.request.Request(delete_url, headers={"User-Agent": "Mozilla/5.0"})
                            with urllib.request.urlopen(req, timeout=3) as resp:
                                pass
                        except Exception as e:
                            log_message(f"Failed to delete webhook: {e}")
                    msg = "✅ Local Notifier has recovered (3 consecutive successful checks). Render has automatically yielded monitoring back to Local."
                    log_message(msg)
                    send_telegram_notification(msg, config)
            elif PREFERRED_ENV == "Render":
                if ACTIVE_ENV == "Local":
                    ACTIVE_ENV = "Render"
                    IS_STANDBY = False
                    render_url = os.environ.get("RENDER_EXTERNAL_URL") or config.get("render_external_url")
                    if render_url:
                        threading.Thread(target=register_webhook, args=(render_url, config), daemon=True).start()
                    msg = "🔄 Render is now the active monitoring environment."
                    log_message(msg)
                    send_telegram_notification(msg, config)
        else:
            # We are Local, target is Render
            alive, reason = check_render_health(config)
            if alive:
                RENDER_CONSECUTIVE_SUCCESS += 1
                RENDER_CONSECUTIVE_FAILURE = 0
            else:
                RENDER_CONSECUTIVE_FAILURE += 1
                RENDER_CONSECUTIVE_SUCCESS = 0
                
            if PREFERRED_ENV == "Render":
                if RENDER_CONSECUTIVE_FAILURE >= 3 and ACTIVE_ENV == "Render":
                    ACTIVE_ENV = "Local"
                    IS_STANDBY = False
                    token = config.get("telegram_bot_token")
                    if token:
                        delete_url = f"https://api.telegram.org/bot{token}/deleteWebhook"
                        try:
                            req = urllib.request.Request(delete_url, headers={"User-Agent": "Mozilla/5.0"})
                            with urllib.request.urlopen(req, timeout=3) as resp:
                                pass
                        except Exception as e:
                            log_message(f"Failed to delete webhook: {e}")
                    msg = "⚠️ Render Notifier is offline (3 consecutive timeout checks). Local has automatically taken over monitoring."
                    log_message(msg)
                    send_telegram_notification(msg, config)
                elif RENDER_CONSECUTIVE_SUCCESS >= 3 and ACTIVE_ENV == "Local":
                    ACTIVE_ENV = "Render"
                    IS_STANDBY = True
                    render_url = os.environ.get("RENDER_EXTERNAL_URL") or config.get("render_external_url")
                    if render_url:
                        threading.Thread(target=register_webhook, args=(render_url, config), daemon=True).start()
                    msg = "✅ Render Notifier has recovered (3 consecutive successful checks). Local has automatically yielded monitoring back to Render."
                    log_message(msg)
                    send_telegram_notification(msg, config)
            elif PREFERRED_ENV == "Local":
                if ACTIVE_ENV == "Render":
                    ACTIVE_ENV = "Local"
                    IS_STANDBY = False
                    token = config.get("telegram_bot_token")
                    if token:
                        delete_url = f"https://api.telegram.org/bot{token}/deleteWebhook"
                        try:
                            req = urllib.request.Request(delete_url, headers={"User-Agent": "Mozilla/5.0"})
                            with urllib.request.urlopen(req, timeout=3) as resp:
                                pass
                        except Exception as e:
                            log_message(f"Failed to delete webhook: {e}")
                    msg = "🔄 Local is now the active monitoring environment."
                    log_message(msg)
                    send_telegram_notification(msg, config)

        # Silence Rule: check if both environments are dead
        if not alive and not LAST_API_POLL_SUCCESS:
            if not BOTH_DEAD_ALERT_SENT:
                BOTH_DEAD_ALERT_SENT = True
                msg = "🚨 CRITICAL: Both Render and Local environments are currently unavailable/failing!"
                log_message(msg)
                send_telegram_notification(msg, config)
        else:
            BOTH_DEAD_ALERT_SENT = False

def local_heartbeat_ping_loop(stop_event):
    log_message("Local heartbeat ping loop started.")
    while not stop_event.is_set():
        is_render = (os.environ.get("RENDER") is not None)
        if not is_render:
            config = load_config()
            render_url = os.environ.get("RENDER_EXTERNAL_URL") or config.get("render_external_url")
            if render_url and PREFERRED_ENV == "Local":
                url = f"{render_url.rstrip('/')}/heartbeat"
                try:
                    req = urllib.request.Request(url, data=json.dumps({}).encode('utf-8'), method="POST", headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"})
                    with urllib.request.urlopen(req, timeout=5) as resp:
                        resp.read()
                except Exception as e:
                    pass
        if stop_event.wait(15):
            break

class RequestHandler(http.server.BaseHTTPRequestHandler):
    """HTTP Request Handler exposing REST endpoints."""
    
    def log_message(self, format, *args):
        # Override log message to print clearly to terminal
        sys.stdout.write(f"[{datetime.datetime.now()}] {self.address_string()} - {format%args}\n")

    def send_json_response(self, status_code, data):
        try:
            content = json.dumps(data).encode('utf-8')
            self.send_response(status_code)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
            self.send_header('Access-Control-Allow-Headers', 'Content-Type')
            self.end_headers()
            self.wfile.write(content)
        except Exception as e:
            print(f"[{datetime.datetime.now()}] Error writing response: {e}")

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_GET(self):
        config = load_config()
        parsed_url = urlparse(self.path)
        path = parsed_url.path
        query_params = parse_qs(parsed_url.query)

        # Automatically register webhook if running on a public hostname (like Render)
        proto = self.headers.get('X-Forwarded-Proto', 'http')
        host = self.headers.get('Host')
        if host and "localhost" not in host and "127.0.0.1" not in host:
            public_url = f"{proto}://{host}"
            threading.Thread(target=register_webhook, args=(public_url, config), daemon=True).start()

        if path == '/':
            local_now = get_local_time(config)
            business_date, active = get_business_date_and_active(
                local_now,
                config.get("monitoring_start_hour", 9),
                config.get("monitoring_end_hour", 1)
            )
            # Mask credentials
            token = config.get("telegram_bot_token", "")
            chat_id = config.get("telegram_chat_id", "")
            
            token_ok = bool(token and "YOUR_TELEGRAM" not in token)
            chat_ok = bool(chat_id and "YOUR_TELEGRAM" not in chat_id)
            
            masked_token = (token[:6] + "..." + token[-4:]) if token_ok and len(token) > 10 else "not_configured"
            masked_chat = (chat_id[:3] + "..." + chat_id[-3:]) if chat_ok and len(chat_id) > 6 else "not_configured"

            apis_status = []
            for api in config.get("apis", []):
                apis_status.append({
                    "name": api.get("name"),
                    "url_configured": bool(api.get("url_template") and "YOUR_" not in api.get("url_template")),
                    "filter_pending": api.get("filter_pending", True),
                    "default_process": api.get("default_process"),
                    "headers_configured": bool(api.get("headers"))
                })

            response = {
                "status": "online",
                "server_time": local_now.strftime("%Y-%m-%d %H:%M:%S"),
                "business_date": business_date.strftime("%Y-%m-%d"),
                "is_active_monitoring_hour": active,
                "thresholds": {
                    "PSA_SO_PENDING_THRESHOLD_MINUTES": PSA_SO_PENDING_THRESHOLD_MINUTES,
                    "PSA_CO_PENDING_THRESHOLD_MINUTES": PSA_CO_PENDING_THRESHOLD_MINUTES,
                    "OBD_PENDING_THRESHOLD_MINUTES": OBD_PENDING_THRESHOLD_MINUTES,
                    "CEMENTAPI_SO_PENDING_THRESHOLD_MINUTES": CEMENTAPI_SO_PENDING_THRESHOLD_MINUTES,
                    "CEMENTAPI_CO_PENDING_THRESHOLD_MINUTES": CEMENTAPI_CO_PENDING_THRESHOLD_MINUTES,
                    "CONTRACTAPI_CO_PENDING_THRESHOLD_MINUTES": CONTRACTAPI_CO_PENDING_THRESHOLD_MINUTES,
                    "SMARTSALES_OBD_OFFHOURS_THRESHOLD_MINUTES": SMARTSALES_OBD_OFFHOURS_THRESHOLD_MINUTES,
                    "FRESHLPG_SO_PENDING_THRESHOLD_MINUTES": FRESHLPG_SO_PENDING_THRESHOLD_MINUTES,
                    "FRESHLPG_CO_PENDING_THRESHOLD_MINUTES": FRESHLPG_CO_PENDING_THRESHOLD_MINUTES,
                    "OBD_OFFHOURS_START_HOUR": OBD_OFFHOURS_START_HOUR,
                    "OBD_OFFHOURS_END_HOUR": OBD_OFFHOURS_END_HOUR
                },
                "config": {
                    "telegram_bot_token_configured": token_ok,
                    "telegram_chat_id_configured": chat_ok,
                    "telegram_bot_token_masked": masked_token,
                    "telegram_chat_id_masked": masked_chat,
                    "monitoring_start_hour": config.get("monitoring_start_hour", 9),
                    "monitoring_end_hour": config.get("monitoring_end_hour", 1),
                    "poll_interval_minutes": config.get("poll_interval_minutes", 30),
                    "server_port": config.get("server_port", 8080),
                    "timezone_offset_hours": config.get("timezone_offset_hours", 6),
                    "apis": apis_status
                }
            }
            self.send_json_response(200, response)
            
        elif path == '/debug':
            token = config.get("telegram_bot_token", "")
            chat_id = config.get("telegram_chat_id", "")
            
            token_ok = bool(token and "YOUR_TELEGRAM" not in token)
            masked_token = (token[:6] + "..." + token[-4:]) if token_ok and len(token) > 10 else "not_configured"
            
            webhook_info = {}
            if token_ok:
                try:
                    url = f"https://api.telegram.org/bot{token}/getWebhookInfo"
                    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                    with urllib.request.urlopen(req, timeout=5) as response_webhook:
                        webhook_info = json.loads(response_webhook.read().decode('utf-8'))
                except Exception as e:
                    webhook_info = {"error": str(e)}

            response = {
                "status": "online",
                "telegram_bot_token_configured": token_ok,
                "telegram_bot_token_masked": masked_token,
                "expected_chat_id": chat_id,
                "telegram_webhook_info": webhook_info
            }
            self.send_json_response(200, response)

        elif path == '/debug_files':
            import glob
            files = glob.glob("*") + glob.glob(".*")
            file_details = {}
            for f in files:
                if os.path.isfile(f):
                    try:
                        sz = os.path.getsize(f)
                        content_sample = ""
                        if f in ["config.json", ".env"]:
                            with open(f, "r", encoding="utf-8") as file_obj:
                                content_sample = file_obj.read()
                        file_details[f] = {"size": sz, "content": content_sample}
                    except Exception as e:
                        file_details[f] = {"error": str(e)}
            self.send_json_response(200, {
                "files": file_details,
                "cwd": os.getcwd()
            })
            
        elif path == '/debug_memory':
            with PENDING_LOCK:
                first_seen_serializable = {str(k): v.strftime("%Y-%m-%d %H:%M:%S") for k, v in PENDING_FIRST_SEEN.items()}
                alerts_sent_serializable = {str(k): v.strftime("%Y-%m-%d %H:%M:%S") for k, v in PENDING_ALERTS_SENT.items()}
            self.send_json_response(200, {
                "first_seen_count": len(PENDING_FIRST_SEEN),
                "alerts_sent_count": len(PENDING_ALERTS_SENT),
                "first_seen": first_seen_serializable,
                "alerts_sent": alerts_sent_serializable
            })
            
        elif path == '/pending':
            local_now = get_local_time(config)
            business_date, _ = get_business_date_and_active(
                local_now,
                config.get("monitoring_start_hour", 9),
                config.get("monitoring_end_hour", 1)
            )
            try:
                stats = fetch_all_apis(business_date, config)
                self.send_json_response(200, {
                    "status": "success",
                    "business_date": business_date.strftime("%Y-%m-%d"),
                    "stats": stats
                })
            except Exception as e:
                self.send_json_response(500, {
                    "status": "error",
                    "message": f"Failed to fetch or parse data: {e}"
                })
                
        elif path == '/trigger':
            force = query_params.get("force", ["false"])[0].lower() == "true"
            local_now = get_local_time(config)
            business_date, active = get_business_date_and_active(
                local_now,
                config.get("monitoring_start_hour", 9),
                config.get("monitoring_end_hour", 1)
            )
            
            if not active and not force:
                self.send_json_response(200, {
                    "status": "skipped",
                    "message": "Outside active monitoring hours. Notification skipped. Use ?force=true to override.",
                    "business_date": business_date.strftime("%Y-%m-%d")
                })
                return

            try:
                stats = fetch_all_apis(business_date, config)
                msg = format_telegram_message(stats, business_date, config)
                ok, err = send_telegram_notification(msg, config)
                if ok:
                    check_and_send_pending_alert(business_date, config)
                    self.send_json_response(200, {
                        "status": "success",
                        "message": "Notification triggered and sent successfully.",
                        "business_date": business_date.strftime("%Y-%m-%d"),
                        "stats": stats
                    })
                else:
                    self.send_json_response(502, {
                        "status": "error",
                        "message": f"Failed to send Telegram notification: {err}",
                        "business_date": business_date.strftime("%Y-%m-%d"),
                        "stats": stats
                    })
            except Exception as e:
                self.send_json_response(500, {
                    "status": "error",
                    "message": f"Trigger operation failed: {e}"
                })
        elif path == '/stop_render':
            api_key = config.get("RENDER_API_KEY") or os.environ.get("RENDER_API_KEY")
            service_id = config.get("RENDER_SERVICE_ID") or os.environ.get("RENDER_SERVICE_ID")
            if not api_key or not service_id:
                self.send_json_response(400, {"error": "RENDER_API_KEY or RENDER_SERVICE_ID not configured"})
                return
            url = f"https://api.render.com/v1/services/{service_id}/suspend"
            req = urllib.request.Request(url, headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"}, method="POST")
            try:
                with urllib.request.urlopen(req, timeout=10) as resp:
                    self.send_json_response(200, {"status": "success", "message": "Render service suspended successfully"})
            except Exception as e:
                self.send_json_response(500, {"error": f"Failed to suspend Render service: {e}"})
        elif path == '/resume_render':
            api_key = config.get("RENDER_API_KEY") or os.environ.get("RENDER_API_KEY")
            service_id = config.get("RENDER_SERVICE_ID") or os.environ.get("RENDER_SERVICE_ID")
            if not api_key or not service_id:
                self.send_json_response(400, {"error": "RENDER_API_KEY or RENDER_SERVICE_ID not configured"})
                return
            url = f"https://api.render.com/v1/services/{service_id}/resume"
            req = urllib.request.Request(url, headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"}, method="POST")
            try:
                with urllib.request.urlopen(req, timeout=10) as resp:
                    self.send_json_response(200, {"status": "success", "message": "Render service resumed successfully"})
            except Exception as e:
                self.send_json_response(500, {"error": f"Failed to resume Render service: {e}"})
        else:
            self.send_json_response(404, {"error": "Not Found"})

    def do_POST(self):
        global IS_STANDBY, LAST_LOCAL_HEARTBEAT, LOCAL_ONLINE_STATE, ACTIVE_ENV, PREFERRED_ENV
        config = load_config()
        parsed_url = urlparse(self.path)
        path = parsed_url.path
        query_params = parse_qs(parsed_url.query)

        if path == '/heartbeat':
            LAST_LOCAL_HEARTBEAT = time.time()
            if not LOCAL_ONLINE_STATE:
                log_message("Heartbeat received. Local was offline and is now back online!")
                LOCAL_ONLINE_STATE = True
                IS_STANDBY = True
                
                # Automatically delete Render webhook so Local long polling wakes up
                token = config.get("telegram_bot_token")
                if token:
                    delete_url = f"https://api.telegram.org/bot{token}/deleteWebhook"
                    try:
                        req = urllib.request.Request(delete_url, headers={"User-Agent": "Mozilla/5.0"})
                        with urllib.request.urlopen(req, timeout=10) as resp:
                            res = json.loads(resp.read().decode('utf-8'))
                            if res.get("ok"):
                                log_message("Webhook successfully deleted to yield back to Local.")
                    except Exception as e:
                        log_message(f"Failed to delete webhook on recovery: {e}")
                
                send_telegram_notification("✅ Local Notifier has recovered and is online. Render has automatically yielded monitoring back to Local.", config)
            elif not IS_STANDBY:
                log_message("Heartbeat received from Local. Render is going to Standby.")
                IS_STANDBY = True
                
            self.send_json_response(200, {"status": "ok", "message": "heartbeat received"})
            return

        if path == '/webhook':
            try:
                content_length = int(self.headers.get('Content-Length', 0))
                body = self.rfile.read(content_length)
                update = json.loads(body.decode('utf-8'))
                
                global LAST_WEBHOOK_PAYLOAD, LAST_WEBHOOK_ERROR
                global USER_CONVERSATION_STATE, PSA_SO_PENDING_THRESHOLD_MINUTES, PSA_CO_PENDING_THRESHOLD_MINUTES, OBD_PENDING_THRESHOLD_MINUTES
                global CEMENTAPI_SO_PENDING_THRESHOLD_MINUTES, CEMENTAPI_CO_PENDING_THRESHOLD_MINUTES
                global CONTRACTAPI_CO_PENDING_THRESHOLD_MINUTES
                global SMARTSALES_OBD_OFFHOURS_THRESHOLD_MINUTES, OBD_OFFHOURS_START_HOUR, OBD_OFFHOURS_END_HOUR
                global FRESHLPG_SO_PENDING_THRESHOLD_MINUTES, FRESHLPG_CO_PENDING_THRESHOLD_MINUTES
                global CALLMEBOT_USER
                global PSA_SO_PENDING_THRESHOLD_MINUTES_DEFAULT, PSA_CO_PENDING_THRESHOLD_MINUTES_DEFAULT
                global OBD_PENDING_THRESHOLD_MINUTES_DEFAULT, CEMENTAPI_SO_PENDING_THRESHOLD_MINUTES_DEFAULT
                global CEMENTAPI_CO_PENDING_THRESHOLD_MINUTES_DEFAULT, CONTRACTAPI_CO_PENDING_THRESHOLD_MINUTES_DEFAULT
                global SMARTSALES_OBD_OFFHOURS_THRESHOLD_MINUTES_DEFAULT, FRESHLPG_SO_PENDING_THRESHOLD_MINUTES_DEFAULT
                global FRESHLPG_CO_PENDING_THRESHOLD_MINUTES_DEFAULT, CALLMEBOT_USER_DEFAULT
                
                LAST_WEBHOOK_PAYLOAD = update
                LAST_WEBHOOK_ERROR = None
                
                callback_query = update.get("callback_query")
                message = update.get("message") or update.get("edited_message")
                
                is_callback = False
                if callback_query:
                    is_callback = True
                    message = callback_query.get("message")
                    chat = message.get("chat") if message else None
                    chat_id = str(chat.get("id")) if chat else ""
                    text = str(callback_query.get("data") or "").strip().lower()
                    
                    callback_id = callback_query.get("id")
                    if callback_id:
                        threading.Thread(target=answer_callback_query, args=(callback_id, config), daemon=True).start()
                
                if message or is_callback:
                    if not is_callback:
                        chat = message.get("chat")
                        chat_id = str(chat.get("id")) if chat else ""
                        text = str(message.get("text") or "").strip().lower()
                    
                    expected_chat_id = str(config.get("telegram_chat_id", "")).strip()
                    
                    if chat_id == expected_chat_id:
                        import re
                        
                        # Conversational state handling
                        if USER_CONVERSATION_STATE and text.startswith("/"):
                            log_message(f"User sent command '{text}' while in state '{USER_CONVERSATION_STATE}'. Cancelling previous state.")
                            USER_CONVERSATION_STATE = None

                        if USER_CONVERSATION_STATE:
                            # 1. SELECT_MODE_FEAT
                            if USER_CONVERSATION_STATE.startswith("SELECT_MODE_"):
                                feat_key = USER_CONVERSATION_STATE[len("SELECT_MODE_"):].lower()
                                meta = CONV_FEATURE_MAP.get(feat_key)
                                if meta:
                                    if text in ["default", "1"]:
                                        USER_CONVERSATION_STATE = f"AWAITING_DEFAULT_VAL_{feat_key.upper()}"
                                        prompt = meta["default_prompt"]
                                        send_telegram_notification(prompt, config)
                                        self.send_json_response(200, {"status": "ok", "message": prompt})
                                        return
                                    elif text in ["current", "2"]:
                                        USER_CONVERSATION_STATE = f"AWAITING_CURRENT_VAL_{feat_key.upper()}"
                                        prompt = meta["current_prompt"]
                                        send_telegram_notification(prompt, config)
                                        self.send_json_response(200, {"status": "ok", "message": prompt})
                                        return
                                    elif text in ["none", "3"]:
                                        var_name = meta["var"]
                                        if meta.get("is_hour"):
                                            cur_val = globals()[var_name]
                                            msg = f"{var_name} = {cur_val}h"
                                        elif meta.get("is_user"):
                                            cur_val = globals()[var_name]
                                            msg = f"CALLMEBOT_USER = {cur_val}"
                                        else:
                                            globals()[var_name] = 0
                                            if meta["clear_args"]:
                                                for args in meta["clear_args"]:
                                                    clear_aging_memory(*args)
                                            msg = f"{meta['label']} checker is off."
                                        save_thresholds()
                                        update_render_env_vars_async()
                                        send_telegram_notification(msg, config)
                                        USER_CONVERSATION_STATE = None
                                        self.send_json_response(200, {"status": "ok", "message": msg})
                                        return
                                    else:
                                        msg = "Please select Default, Current, or None."
                                        send_telegram_notification(msg, config)
                                        self.send_json_response(200, {"status": "ok", "message": msg})
                                        return

                            # 2. AWAITING_DEFAULT_VAL_FEAT
                            elif USER_CONVERSATION_STATE.startswith("AWAITING_DEFAULT_VAL_"):
                                feat_key = USER_CONVERSATION_STATE[len("AWAITING_DEFAULT_VAL_"):].lower()
                                meta = CONV_FEATURE_MAP.get(feat_key)
                                if meta:
                                    default_var = meta["default_var"]
                                    if meta.get("is_hour"):
                                        try:
                                            match = re.search(r'\d+', text)
                                            if not match:
                                                raise ValueError()
                                            val = int(match.group())
                                            if not (0 <= val <= 24):
                                                raise ValueError()
                                        except (ValueError, TypeError):
                                            val = meta["fallback_default"]
                                        globals()[default_var] = val
                                        save_thresholds()
                                        update_render_env_vars_async()
                                        msg = f"{default_var} = {val}h"
                                        send_telegram_notification(msg, config)
                                        USER_CONVERSATION_STATE = None
                                        self.send_json_response(200, {"status": "ok", "message": msg})
                                        return
                                    elif meta.get("is_user"):
                                        val = str(text).strip()
                                        is_off = val.lower() in ["none", "off", "0", ""]
                                        if is_off or not validate_callmebot_user_list(val):
                                            val = meta["fallback_default"]
                                        globals()[default_var] = val
                                        save_thresholds()
                                        update_render_env_vars_async()
                                        msg = f"{default_var} = {val}"
                                        send_telegram_notification(msg, config)
                                        USER_CONVERSATION_STATE = None
                                        self.send_json_response(200, {"status": "ok", "message": msg})
                                        return
                                    else:
                                        try:
                                            match = re.search(r'-?\d+', text)
                                            if not match:
                                                raise ValueError()
                                            val = int(match.group())
                                            if val <= 0:
                                                raise ValueError()
                                        except (ValueError, TypeError):
                                            val = meta["fallback_default"]
                                        globals()[default_var] = val
                                        save_thresholds()
                                        update_render_env_vars_async()
                                        msg = f"{meta['default_prompt']} = {val} min"
                                        send_telegram_notification(msg, config)
                                        ask_msg = f"want to on {meta['label']}?"
                                        reply_markup = {
                                            "inline_keyboard": [
                                                [
                                                    {"text": "Yes", "callback_data": "yes"},
                                                    {"text": "No", "callback_data": "no"}
                                                ]
                                            ]
                                        }
                                        send_telegram_notification(ask_msg, config, reply_markup=reply_markup)
                                        USER_CONVERSATION_STATE = f"AWAITING_ON_CONFIRM_{feat_key.upper()}"
                                        self.send_json_response(200, {"status": "ok", "message": ask_msg})
                                        return

                            # 3. AWAITING_CURRENT_VAL_FEAT
                            elif USER_CONVERSATION_STATE.startswith("AWAITING_CURRENT_VAL_"):
                                feat_key = USER_CONVERSATION_STATE[len("AWAITING_CURRENT_VAL_"):].lower()
                                meta = CONV_FEATURE_MAP.get(feat_key)
                                if meta:
                                    var_name = meta["var"]
                                    default_var = meta["default_var"]
                                    if meta.get("is_hour"):
                                        try:
                                            match = re.search(r'\d+', text)
                                            if not match:
                                                raise ValueError()
                                            val = int(match.group())
                                            if not (0 <= val <= 24):
                                                raise ValueError()
                                        except (ValueError, TypeError):
                                            val = globals()[default_var]
                                        globals()[var_name] = val
                                        save_thresholds()
                                        update_render_env_vars_async()
                                        msg = f"{var_name} = {val}h"
                                        send_telegram_notification(msg, config)
                                        USER_CONVERSATION_STATE = None
                                        self.send_json_response(200, {"status": "ok", "message": msg})
                                        return
                                    elif meta.get("is_user"):
                                        val = str(text).strip()
                                        is_off = val.lower() in ["none", "off", "0", ""]
                                        if is_off or not validate_callmebot_user_list(val):
                                            val = globals()[default_var]
                                        globals()[var_name] = val
                                        save_thresholds()
                                        update_render_env_vars_async()
                                        msg = f"CALLMEBOT_USER = {val}"
                                        send_telegram_notification(msg, config)
                                        USER_CONVERSATION_STATE = None
                                        self.send_json_response(200, {"status": "ok", "message": msg})
                                        return
                                    else:
                                        try:
                                            match = re.search(r'-?\d+', text)
                                            if not match:
                                                raise ValueError()
                                            val = int(match.group())
                                            if val <= 0:
                                                raise ValueError()
                                        except (ValueError, TypeError):
                                            val = globals()[default_var]
                                        globals()[var_name] = val
                                        save_thresholds()
                                        update_render_env_vars_async()
                                        msg = f"{meta['current_prompt']} = {val} min"
                                        send_telegram_notification(msg, config)
                                        ask_msg = f"want to on {meta['label']}?"
                                        reply_markup = {
                                            "inline_keyboard": [
                                                [
                                                    {"text": "Yes", "callback_data": "yes"},
                                                    {"text": "No", "callback_data": "no"}
                                                ]
                                             ]
                                         }
                                        send_telegram_notification(ask_msg, config, reply_markup=reply_markup)
                                        USER_CONVERSATION_STATE = f"AWAITING_ON_CONFIRM_{feat_key.upper()}"
                                        self.send_json_response(200, {"status": "ok", "message": ask_msg})
                                        return

                            # 4. AWAITING_ON_CONFIRM_FEAT
                            elif USER_CONVERSATION_STATE.startswith("AWAITING_ON_CONFIRM_"):
                                feat_key = USER_CONVERSATION_STATE[len("AWAITING_ON_CONFIRM_"):].lower()
                                meta = CONV_FEATURE_MAP.get(feat_key)
                                if meta:
                                    if text in ["yes", "y"]:
                                        # Ask Default or Current
                                        USER_CONVERSATION_STATE = f"AWAITING_ON_CHOICE_{feat_key.upper()}"
                                        msg = "Select Default or Current:"
                                        reply_markup = {
                                            "inline_keyboard": [
                                                [
                                                    {"text": "Default", "callback_data": "default"},
                                                    {"text": "Current", "callback_data": "current"},
                                                    {"text": "None", "callback_data": "none"}
                                                ]
                                            ]
                                        }
                                        send_telegram_notification(msg, config, reply_markup=reply_markup)
                                        self.send_json_response(200, {"status": "ok", "message": msg})
                                        return
                                    elif text in ["no", "n"]:
                                        # Turn checker off
                                        var_name = meta["var"]
                                        globals()[var_name] = 0
                                        if meta["clear_args"]:
                                            for args in meta["clear_args"]:
                                                clear_aging_memory(*args)
                                        save_thresholds()
                                        update_render_env_vars_async()
                                        msg = f"{meta['label']} checker is off."
                                        send_telegram_notification(msg, config)
                                        USER_CONVERSATION_STATE = None
                                        self.send_json_response(200, {"status": "ok", "message": msg})
                                        return
                                    else:
                                        msg = "Please select Yes or No."
                                        send_telegram_notification(msg, config)
                                        self.send_json_response(200, {"status": "ok", "message": msg})
                                        return

                            # 5. AWAITING_ON_CHOICE_FEAT
                            elif USER_CONVERSATION_STATE.startswith("AWAITING_ON_CHOICE_"):
                                feat_key = USER_CONVERSATION_STATE[len("AWAITING_ON_CHOICE_"):].lower()
                                meta = CONV_FEATURE_MAP.get(feat_key)
                                if meta:
                                    if text in ["default", "1"]:
                                        # Set current = default
                                        default_var = meta["default_var"]
                                        default_val = globals()[default_var]
                                        var_name = meta["var"]
                                        globals()[var_name] = default_val
                                        save_thresholds()
                                        update_render_env_vars_async()
                                        msg = f"{meta['label']} checker is on. {meta['label']} = {default_val} min."
                                        send_telegram_notification(msg, config)
                                        USER_CONVERSATION_STATE = None
                                        self.send_json_response(200, {"status": "ok", "message": msg})
                                        return
                                    elif text in ["current", "2"]:
                                        # If current not set, current = default. Else current is used.
                                        var_name = meta["var"]
                                        current_val = globals()[var_name]
                                        default_var = meta["default_var"]
                                        default_val = globals()[default_var]
                                        if current_val <= 0:
                                            current_val = default_val
                                            globals()[var_name] = current_val
                                        save_thresholds()
                                        update_render_env_vars_async()
                                        msg = f"{meta['label']} checker is on. {meta['label']} = {current_val} min."
                                        send_telegram_notification(msg, config)
                                        USER_CONVERSATION_STATE = None
                                        self.send_json_response(200, {"status": "ok", "message": msg})
                                        return
                                    elif text in ["none", "3"]:
                                        # Turn checker off
                                        var_name = meta["var"]
                                        globals()[var_name] = 0
                                        if meta["clear_args"]:
                                            for args in meta["clear_args"]:
                                                clear_aging_memory(*args)
                                        save_thresholds()
                                        update_render_env_vars_async()
                                        msg = f"{meta['label']} checker is off."
                                        send_telegram_notification(msg, config)
                                        USER_CONVERSATION_STATE = None
                                        self.send_json_response(200, {"status": "ok", "message": msg})
                                        return
                                    else:
                                        msg = "Please select Default, Current, or None."
                                        send_telegram_notification(msg, config)
                                        self.send_json_response(200, {"status": "ok", "message": msg})
                                        return

                        # Check if user sent off shortcuts: o1-o9, f1_off-f9_off, f1 off-f9 off
                        off_match = re.match(r'^(?:/)?(?:o([1-9])|f([1-9])_off|f([1-9])\s+off)$', text)
                        if off_match:
                            num = int(next(g for g in off_match.groups() if g is not None))
                            feat_key = f"f{num}"
                            meta = CONV_FEATURE_MAP.get(feat_key)
                            if meta:
                                var_name = meta["var"]
                                globals()[var_name] = 0
                                if num == 7:
                                    globals()["CALLMEBOT_USER"] = "none"
                                if meta["clear_args"]:
                                    for args in meta["clear_args"]:
                                        clear_aging_memory(*args)
                                save_thresholds()
                                update_render_env_vars_async()
                                msg = f"{meta['label']} checker is off."
                                send_telegram_notification(msg, config)
                                USER_CONVERSATION_STATE = None
                                self.send_json_response(200, {"status": "ok", "message": msg})
                                return

                        # Direct command triggers
                        if text in ["f1", "f1 on", "/f1", "/f1_on"]:
                            start_feature_conversation(self, "f1", config)
                            return
                        elif text in ["f2", "f2 on", "/f2", "/f2_on"]:
                            start_feature_conversation(self, "f2", config)
                            return
                        elif text in ["f3", "f3 on", "/f3", "/f3_on"]:
                            start_feature_conversation(self, "f3", config)
                            return
                        elif text in ["f4", "f4 on", "/f4", "/f4_on"]:
                            start_feature_conversation(self, "f4", config)
                            return
                        elif text in ["f5", "f5 on", "/f5", "/f5_on"]:
                            start_feature_conversation(self, "f5", config)
                            return
                        elif text in ["f6", "f6 on", "/f6", "/f6_on"]:
                            start_feature_conversation(self, "f6", config)
                            return
                        elif text in ["f7", "f7 on", "/f7", "/f7_on"]:
                            start_feature_conversation(self, "f7", config)
                            return
                        elif text in ["f8", "f8 on", "/f8", "/f8_on"]:
                            start_feature_conversation(self, "f8", config)
                            return
                        elif text in ["f9", "f9 on", "/f9", "/f9_on"]:
                            start_feature_conversation(self, "f9", config)
                            return
                        elif text in ["f7_start", "/f7_start"]:
                            start_feature_conversation(self, "f7_start", config)
                            return
                        elif text in ["f7_end", "/f7_end"]:
                            start_feature_conversation(self, "f7_end", config)
                            return
                        elif text in ["f7_user", "/f7_user"]:
                            start_feature_conversation(self, "f7_user", config)
                            return
                        elif text in ["f7_test", "/f7_test"]:
                            msg = f"Initiating a test voice call via CallMeBot to: {CALLMEBOT_USER}"
                            send_telegram_notification(msg, config)
                            trigger_callmebot_call_async("This is a test call from your PSA Telegram Notifier bot. Everything is working correctly.", config)
                            self.send_json_response(200, {"status": "ok", "message": msg})
                            return

                        elif text in ["feature", "/feature"]:
                            f1_status = "on" if PSA_SO_PENDING_THRESHOLD_MINUTES > 0 else "off"
                            f2_status = "on" if PSA_CO_PENDING_THRESHOLD_MINUTES > 0 else "off"
                            f3_status = "on" if OBD_PENDING_THRESHOLD_MINUTES > 0 else "off"
                            f4_status = "on" if CEMENTAPI_SO_PENDING_THRESHOLD_MINUTES > 0 else "off"
                            f5_status = "on" if CEMENTAPI_CO_PENDING_THRESHOLD_MINUTES > 0 else "off"
                            f6_status = "on" if CONTRACTAPI_CO_PENDING_THRESHOLD_MINUTES > 0 else "off"
                            f7_status = "on" if SMARTSALES_OBD_OFFHOURS_THRESHOLD_MINUTES > 0 else "off"
                            f8_status = "on" if FRESHLPG_SO_PENDING_THRESHOLD_MINUTES > 0 else "off"
                            f9_status = "on" if FRESHLPG_CO_PENDING_THRESHOLD_MINUTES > 0 else "off"
                            
                            f1_def_status = "on" if PSA_SO_PENDING_THRESHOLD_MINUTES_DEFAULT > 0 else "off"
                            f2_def_status = "on" if PSA_CO_PENDING_THRESHOLD_MINUTES_DEFAULT > 0 else "off"
                            f3_def_status = "on" if OBD_PENDING_THRESHOLD_MINUTES_DEFAULT > 0 else "off"
                            f4_def_status = "on" if CEMENTAPI_SO_PENDING_THRESHOLD_MINUTES_DEFAULT > 0 else "off"
                            f5_def_status = "on" if CEMENTAPI_CO_PENDING_THRESHOLD_MINUTES_DEFAULT > 0 else "off"
                            f6_def_status = "on" if CONTRACTAPI_CO_PENDING_THRESHOLD_MINUTES_DEFAULT > 0 else "off"
                            f7_def_status = "on" if SMARTSALES_OBD_OFFHOURS_THRESHOLD_MINUTES_DEFAULT > 0 else "off"
                            f8_def_status = "on" if FRESHLPG_SO_PENDING_THRESHOLD_MINUTES_DEFAULT > 0 else "off"
                            f9_def_status = "on" if FRESHLPG_CO_PENDING_THRESHOLD_MINUTES_DEFAULT > 0 else "off"
                            
                            psa_so_val = f"{PSA_SO_PENDING_THRESHOLD_MINUTES} min" if PSA_SO_PENDING_THRESHOLD_MINUTES > 0 else "off"
                            psa_co_val = f"{PSA_CO_PENDING_THRESHOLD_MINUTES} min" if PSA_CO_PENDING_THRESHOLD_MINUTES > 0 else "off"
                            obd_val = f"{OBD_PENDING_THRESHOLD_MINUTES} min" if OBD_PENDING_THRESHOLD_MINUTES > 0 else "off"
                            cementapi_so_val = f"{CEMENTAPI_SO_PENDING_THRESHOLD_MINUTES} min" if CEMENTAPI_SO_PENDING_THRESHOLD_MINUTES > 0 else "off"
                            cementapi_co_val = f"{CEMENTAPI_CO_PENDING_THRESHOLD_MINUTES} min" if CEMENTAPI_CO_PENDING_THRESHOLD_MINUTES > 0 else "off"
                            contractapi_co_val = f"{CONTRACTAPI_CO_PENDING_THRESHOLD_MINUTES} min" if CONTRACTAPI_CO_PENDING_THRESHOLD_MINUTES > 0 else "off"
                            smartsales_obd_offhours_val = f"{SMARTSALES_OBD_OFFHOURS_THRESHOLD_MINUTES} min" if SMARTSALES_OBD_OFFHOURS_THRESHOLD_MINUTES > 0 else "off"
                            freshlpg_so_val = f"{FRESHLPG_SO_PENDING_THRESHOLD_MINUTES} min" if FRESHLPG_SO_PENDING_THRESHOLD_MINUTES > 0 else "off"
                            freshlpg_co_val = f"{FRESHLPG_CO_PENDING_THRESHOLD_MINUTES} min" if FRESHLPG_CO_PENDING_THRESHOLD_MINUTES > 0 else "off"
                            
                            psa_so_def = f"{PSA_SO_PENDING_THRESHOLD_MINUTES_DEFAULT} min" if PSA_SO_PENDING_THRESHOLD_MINUTES_DEFAULT > 0 else "off"
                            psa_co_def = f"{PSA_CO_PENDING_THRESHOLD_MINUTES_DEFAULT} min" if PSA_CO_PENDING_THRESHOLD_MINUTES_DEFAULT > 0 else "off"
                            obd_def = f"{OBD_PENDING_THRESHOLD_MINUTES_DEFAULT} min" if OBD_PENDING_THRESHOLD_MINUTES_DEFAULT > 0 else "off"
                            cementapi_so_def = f"{CEMENTAPI_SO_PENDING_THRESHOLD_MINUTES_DEFAULT} min" if CEMENTAPI_SO_PENDING_THRESHOLD_MINUTES_DEFAULT > 0 else "off"
                            cementapi_co_def = f"{CEMENTAPI_CO_PENDING_THRESHOLD_MINUTES_DEFAULT} min" if CEMENTAPI_CO_PENDING_THRESHOLD_MINUTES_DEFAULT > 0 else "off"
                            contractapi_co_def = f"{CONTRACTAPI_CO_PENDING_THRESHOLD_MINUTES_DEFAULT} min" if CONTRACTAPI_CO_PENDING_THRESHOLD_MINUTES_DEFAULT > 0 else "off"
                            smartsales_obd_offhours_def = f"{SMARTSALES_OBD_OFFHOURS_THRESHOLD_MINUTES_DEFAULT} min" if SMARTSALES_OBD_OFFHOURS_THRESHOLD_MINUTES_DEFAULT > 0 else "off"
                            freshlpg_so_def = f"{FRESHLPG_SO_PENDING_THRESHOLD_MINUTES_DEFAULT} min" if FRESHLPG_SO_PENDING_THRESHOLD_MINUTES_DEFAULT > 0 else "off"
                            freshlpg_co_def = f"{FRESHLPG_CO_PENDING_THRESHOLD_MINUTES_DEFAULT} min" if FRESHLPG_CO_PENDING_THRESHOLD_MINUTES_DEFAULT > 0 else "off"
                            
                            configs_metadata = [
                                {
                                    "key": "status / report",
                                    "default": "na",
                                    "val": "na",
                                    "desc": "use for report view"
                                },
                                {
                                    "key": "f1",
                                    "default": f1_def_status,
                                    "val": f1_status,
                                    "desc": "psa so pending checker status"
                                },
                                {
                                    "key": "psa_so_pending_threshold_minutes",
                                    "default": psa_so_def,
                                    "val": psa_so_val,
                                    "desc": "psa so pending threshold variable"
                                },
                                {
                                    "key": "f2",
                                    "default": f2_def_status,
                                    "val": f2_status,
                                    "desc": "psa co checker status"
                                },
                                {
                                    "key": "psa_co_pending_threshold_minutes",
                                    "default": psa_co_def,
                                    "val": psa_co_val,
                                    "desc": "psa co pending threshold variable"
                                },
                                {
                                    "key": "f3",
                                    "default": f3_def_status,
                                    "val": f3_status,
                                    "desc": "obd checker status"
                                },
                                {
                                    "key": "obd_pending_threshold_minutes",
                                    "default": obd_def,
                                    "val": obd_val,
                                    "desc": "obd pending threshold variable"
                                },
                                {
                                    "key": "f4",
                                    "default": f4_def_status,
                                    "val": f4_status,
                                    "desc": "cementapi so checker status"
                                },
                                {
                                    "key": "cementapi_so_pending_threshold_minutes",
                                    "default": cementapi_so_def,
                                    "val": cementapi_so_val,
                                    "desc": "cementapi so pending threshold variable"
                                },
                                {
                                    "key": "f5",
                                    "default": f5_def_status,
                                    "val": f5_status,
                                    "desc": "cementapi co checker status"
                                },
                                {
                                    "key": "cementapi_co_pending_threshold_minutes",
                                    "default": cementapi_co_def,
                                    "val": cementapi_co_val,
                                    "desc": "cementapi co pending threshold variable"
                                },
                                {
                                    "key": "f6",
                                    "default": f6_def_status,
                                    "val": f6_status,
                                    "desc": "contractapi co checker status"
                                },
                                {
                                    "key": "contractapi_co_pending_threshold_minutes",
                                    "default": contractapi_co_def,
                                    "val": contractapi_co_val,
                                    "desc": "contractapi co pending threshold variable"
                                },
                                {
                                    "key": "f7",
                                    "default": f7_def_status,
                                    "val": f7_status,
                                    "desc": "smart sales obd off-hours checker status"
                                },
                                {
                                    "key": "smartsales_obd_offhours_threshold_minutes",
                                    "default": smartsales_obd_offhours_def,
                                    "val": smartsales_obd_offhours_val,
                                    "desc": "smart sales obd off-hours threshold variable"
                                },
                                {
                                    "key": "obd_offhours_start_hour",
                                    "default": str(OBD_OFFHOURS_START_HOUR_DEFAULT),
                                    "val": str(OBD_OFFHOURS_START_HOUR),
                                    "desc": "start hour for off-hours obd checker"
                                },
                                {
                                    "key": "obd_offhours_end_hour",
                                    "default": str(OBD_OFFHOURS_END_HOUR_DEFAULT),
                                    "val": str(OBD_OFFHOURS_END_HOUR),
                                    "desc": "end hour for off-hours obd checker"
                                },
                                {
                                    "key": "f7_user",
                                    "default": CALLMEBOT_USER_DEFAULT,
                                    "val": CALLMEBOT_USER,
                                    "desc": "CallMeBot targets for off-hours OBD voice call"
                                },
                                {
                                    "key": "f8",
                                    "default": f8_def_status,
                                    "val": f8_status,
                                    "desc": "freshlpg so checker status"
                                },
                                {
                                    "key": "freshlpg_so_pending_threshold_minutes",
                                    "default": freshlpg_so_def,
                                    "val": freshlpg_so_val,
                                    "desc": "freshlpg so pending threshold variable"
                                },
                                {
                                    "key": "f9",
                                    "default": f9_def_status,
                                    "val": f9_status,
                                    "desc": "freshlpg co checker status"
                                },
                                {
                                    "key": "freshlpg_co_pending_threshold_minutes",
                                    "default": freshlpg_co_def,
                                    "val": freshlpg_co_val,
                                    "desc": "freshlpg co pending threshold variable"
                                }
                            ]
                            
                            output_blocks = []
                            for c in configs_metadata:
                                block = (
                                    f"variable name - {c['key']}\n"
                                    f"default value - {c['default']}\n"
                                    f"current value - {c['val']}\n"
                                    f"description - {c['desc']}"
                                )
                                output_blocks.append(block)
                            
                            feature_msg = "\n\n".join(output_blocks)
                            send_telegram_notification(feature_msg, config)
                            self.send_json_response(200, {"status": "ok", "message": feature_msg})
                            return

                        elif text in ["switch_to_local", "/switch_to_local", "switch_to_render", "/switch_to_render"]:
                            msg = "State switching is disabled. Render runs webhook only and Local runs long polling only."
                            send_telegram_notification(msg, config)
                            self.send_json_response(200, {"status": "ok", "message": msg})
                            return
                        if text in ["status", "/status", "report", "/report"]:
                            print(f"[{datetime.datetime.now()}] Webhook received 'status' command from chat {chat_id}. Processing in background...")
                            local_now = get_local_time(config)
                            business_date, _ = get_business_date_and_active(
                                local_now,
                                config.get("monitoring_start_hour", 9),
                                config.get("monitoring_end_hour", 1)
                            )
                            
                            def async_webhook_handler(b_date, cfg):
                                global LAST_WEBHOOK_ERROR
                                try:
                                    stats = fetch_all_apis(b_date, cfg)
                                    msg = format_telegram_message(stats, b_date, cfg)
                                    ok, err = send_telegram_notification(msg, cfg)
                                    if not ok:
                                        LAST_WEBHOOK_ERROR = f"Failed to send Telegram notification: {err}"
                                    else:
                                        check_and_send_pending_alert(b_date, cfg)
                                except Exception as thread_err:
                                    LAST_WEBHOOK_ERROR = f"Thread Exception: {str(thread_err)}"
                                    print(f"[{datetime.datetime.now()}] Error handling webhook request in background: {thread_err}")
                            
                            threading.Thread(
                                target=async_webhook_handler,
                                args=(business_date, config),
                                daemon=True
                            ).start()
                            
                            self.send_json_response(200, {"status": "ok", "message": "Report request received. Sending summary shortly..."})
                            return
                        else:
                            LAST_WEBHOOK_ERROR = f"Command not recognized: {text}"
                            self.send_json_response(200, {"status": "ignored", "message": "Command not recognized. Try 'status'."})
                            return
                    else:
                        LAST_WEBHOOK_ERROR = f"Unauthorized chat_id: {chat_id} (expected: {expected_chat_id})"
                        print(f"[{datetime.datetime.now()}] Webhook received message from unauthorized chat: {chat_id}")
                        self.send_json_response(403, {"error": "Unauthorized chat_id"})
                        return
                else:
                    LAST_WEBHOOK_ERROR = "No message object found in update"
                self.send_json_response(200, {"status": "ok"})
            except Exception as e:
                LAST_WEBHOOK_ERROR = f"Exception: {str(e)}"
                print(f"[{datetime.datetime.now()}] Webhook error: {e}")
                self.send_json_response(500, {"error": str(e)})

        elif path == '/trigger':
            force = query_params.get("force", ["false"])[0].lower() == "true"
            local_now = get_local_time(config)
            business_date, active = get_business_date_and_active(
                local_now,
                config.get("monitoring_start_hour", 9),
                config.get("monitoring_end_hour", 1)
            )
            
            if not active and not force:
                self.send_json_response(200, {
                    "status": "skipped",
                    "message": "Outside active monitoring hours. Notification skipped. Use ?force=true to override.",
                    "business_date": business_date.strftime("%Y-%m-%d")
                })
                return

            try:
                stats = fetch_all_apis(business_date, config)
                msg = format_telegram_message(stats, business_date, config)
                ok, err = send_telegram_notification(msg, config)
                if ok:
                    check_and_send_pending_alert(business_date, config)
                    self.send_json_response(200, {
                        "status": "success",
                        "message": "Notification triggered and sent successfully.",
                        "business_date": business_date.strftime("%Y-%m-%d"),
                        "stats": stats
                    })
                else:
                    self.send_json_response(502, {
                        "status": "error",
                        "message": f"Failed to send Telegram notification: {err}",
                        "business_date": business_date.strftime("%Y-%m-%d"),
                        "stats": stats
                    })
            except Exception as e:
                self.send_json_response(500, {
                    "status": "error",
                    "message": f"Trigger operation failed: {e}"
                })
        else:
            self.send_json_response(404, {"error": "Not Found"})

class ThreadingHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    """Multi-threaded HTTP Server using socketserver.ThreadingMixIn."""
    daemon_threads = True

def main():
    """Entry point — boots Render (webhook) or Local (long polling) mode automatically."""
    config = load_config()
    port = config.get("server_port", 8080)
    stop_event = threading.Event()

    is_render = (os.environ.get("RENDER") == "true" or os.environ.get("RENDER_SERVICE_ID") is not None)

    # Start background scheduler (interval reports)
    sched_thread = threading.Thread(target=scheduler_loop, args=(stop_event,), daemon=True)
    sched_thread.start()

    # Start pending alert background scheduler
    sched_thread_2 = threading.Thread(target=pending_alert_scheduler_loop, args=(stop_event,), daemon=True)
    sched_thread_2.start()

    # Start aging alerts background scheduler
    sched_thread_3 = threading.Thread(target=aging_alerts_scheduler_loop, args=(stop_event,), daemon=True)
    sched_thread_3.start()

    if is_render:
        print(f"[{datetime.datetime.now()}] Booting in RENDER (webhook) mode.")
        register_bot_commands(config)
        
        # Register Render Webhook on startup
        render_url = os.environ.get("RENDER_EXTERNAL_URL") or config.get("render_external_url")
        if render_url:
            threading.Thread(target=register_webhook, args=(render_url, config), daemon=True).start()
        
        server = ThreadingHTTPServer(('', port), RequestHandler)
        print(f"[{datetime.datetime.now()}] API server starting on port {port}...")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print(f"\n[{datetime.datetime.now()}] KeyboardInterrupt received. Cleaning up...")
        finally:
            stop_event.set()
            server.server_close()
            print(f"[{datetime.datetime.now()}] Server shut down. Goodbye!")
    else:
        print(f"[{datetime.datetime.now()}] Booting in LOCAL (long polling) mode.")
        
        # Release Telegram Webhook lock by deleting webhook on start
        token = config.get("telegram_bot_token")
        if token and "YOUR_TELEGRAM" not in token:
            delete_url = f"https://api.telegram.org/bot{token}/deleteWebhook"
            try:
                req = urllib.request.Request(delete_url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=5) as resp:
                    print(f"[{datetime.datetime.now()}] Deleted Telegram webhook to enable local long polling.")
            except Exception as e:
                print(f"[{datetime.datetime.now()}] Failed to delete webhook: {e}")
                
        register_bot_commands(config)

        # Start long polling thread
        lp_thread = threading.Thread(target=run_long_polling_loop, args=(stop_event,), daemon=True)
        lp_thread.start()

        server = ThreadingHTTPServer(('', port), RequestHandler)
        print(f"[{datetime.datetime.now()}] Local API server starting on port {port}...")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print(f"\n[{datetime.datetime.now()}] KeyboardInterrupt received. Cleaning up...")
        finally:
            stop_event.set()
            server.server_close()
            print(f"[{datetime.datetime.now()}] Server shut down. Goodbye!")


if __name__ == '__main__':
    main()
