import sys, os, json, datetime, urllib.request

script_dir = r"C:\Users\admin\.gemini\antigravity-ide\scratch\psa-telegram-notifier"
sys.path.insert(0, script_dir)
import notifier

config = notifier.load_config()
local_now = notifier.get_local_time(config)
b_date, active = notifier.get_business_date_and_active(local_now, 9, 1)

out_lines = []
out_lines.append(f"Business Date: {b_date}")

apis = config.get("apis", [])
for api in apis:
    name = api.get("name")
    url_template = api.get("url_template")
    headers = dict(api.get("headers", {}))
    headers["User-Agent"] = "Mozilla/5.0"

    date_str = b_date.strftime("%Y-%m-%d")
    start_date_str = (b_date - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    
    url = url_template.replace("{business_date}", date_str).replace("{date}", date_str).replace("{start_date}", start_date_str).replace("{end_date}", date_str)
    
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            raw = resp.read().decode("utf-8")
            data = json.loads(raw)
            
            # Check unwrap
            if isinstance(data, dict) and "data" in data and isinstance(data["data"], (dict, list)):
                unwrapped_data = data["data"]
            else:
                unwrapped_data = data

            parsed = notifier.parse_psa_data(unwrapped_data, filter_pending=api.get("filter_pending", False), default_process=api.get("default_process"), api_name=name, config=config)
            so = parsed.get("total_pending_so", 0)
            co = parsed.get("total_pending_co", 0)
            out_lines.append(f"{name} -> SO: {so} | CO: {co}")
    except Exception as e:
        out_lines.append(f"{name} -> ERROR: {e}")

out_path = r"C:\Users\admin\.gemini\antigravity-ide\scratch\psa-telegram-notifier\counts.txt"
with open(out_path, "w", encoding="utf-8") as f:
    f.write("\n".join(out_lines))

print("SUCCESS: Saved counts to:", out_path)
