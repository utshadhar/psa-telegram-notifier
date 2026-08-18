import sys, os, json, datetime, urllib.parse, urllib.request

script_dir = r"C:\Users\admin\.gemini\antigravity-ide\scratch\psa-telegram-notifier"
sys.path.insert(0, script_dir)
import notifier

config = notifier.load_config()
local_now = notifier.get_local_time(config)
b_date, active = notifier.get_business_date_and_active(local_now, 9, 1)

out = []
out.append(f"Business Date: {b_date}, Local Time: {local_now}")

apis = config.get('apis', [])
for api in apis:
    name = api.get('name')
    url_template = api.get('url_template')
    headers = dict(api.get('headers', {}))
    headers['User-Agent'] = 'Mozilla/5.0'

    date_str = b_date.strftime('%Y-%m-%d')
    start_date_str = (b_date - datetime.timedelta(days=1)).strftime('%Y-%m-%d')
    
    url = url_template.replace('{business_date}', date_str).replace('{date}', date_str).replace('{start_date}', start_date_str).replace('{end_date}', date_str)
    
    out.append(f"\n=========================================")
    out.append(f"API: {name}")
    out.append(f"URL: {url}")
    out.append(f"Filter Pending: {api.get('filter_pending')}, Default Process: {api.get('default_process')}")
    
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            raw_text = resp.read().decode('utf-8')
            data = json.loads(raw_text)
            
            if isinstance(data, dict):
                out.append(f"Response Type: dict, Keys: {list(data.keys())}")
                for k, v in data.items():
                    if isinstance(v, list):
                        out.append(f"  Key '{k}': list of {len(v)} items")
                        if v and isinstance(v[0], dict):
                            out.append(f"    Sample Item Keys: {list(v[0].keys())}")
                            out.append(f"    Sample Item: {json.dumps(v[0])[:200]}")
            elif isinstance(data, list):
                out.append(f"Response Type: list, Count: {len(data)}")
                if data and isinstance(data[0], dict):
                    out.append(f"  Sample Item Keys: {list(data[0].keys())}")
                    out.append(f"  Sample Item: {json.dumps(data[0])[:200]}")
            else:
                out.append(f"Response Type: {type(data)}")
                
            parsed = notifier.parse_psa_data(data, filter_pending=api.get('filter_pending', False), default_process=api.get('default_process'), api_name=name, config=config)
            out.append(f"--> PARSED RESULT: {parsed}")
            
    except Exception as e:
        out.append(f"ERROR fetching {name}: {e}")

out_path = os.path.join(script_dir, "scratch_api_report.txt")
with open(out_path, "w", encoding="utf-8") as f:
    f.write("\n".join(out))
print("Wrote diagnostic report to:", out_path)
