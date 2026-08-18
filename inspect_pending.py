import urllib.request, json, datetime

date_str = "2026-08-18"
start_date_str = "2026-08-17"

apis = [
    ("PSA", "https://psa.mgi.org/api/getALLData/2026-08-17/2026-08-18/0?server=0", {}, True, None),
    ("API_3 (OBD)", "https://smartsales.mgi.org/api/delivery-program-to-all-incoterm?product_line=0&env=1&plan_id=-&order_no=-&delivery_plan_no=-&plant_code=1201%2C%201222%2C%201223%2C%201224%2C%201225%2C%201226%2C%201227%2C%201228%2C%201229%2C%201230%2C%201231%2C%201233%2C%201234%2C%201235%2C%201236%2C%201237%2C%201238%2C%201239%2C%201241%2C%201243%2C%201244%2C%201245%2C%201246%2C%201247%2C%201248%2C%201249%2C%201250%2C%201251%2C1253%2C1255%2C1256&inco_term=0&server_allocation=0&start_date=2026-08-17&end_date=2026-08-18", {"app-key": "AnF3XAy79fvJvgksKzE0waBh8otfNlXE6htzYxuk"}, True, "SO"),
    ("API_4 (Contract)", "https://psa.mgi.org/api/getCorpAllData/2026-08-17/2026-08-18/8?server=0", {}, True, "CO")
]

out = []
for name, url, headers, fp, dp in apis:
    headers["User-Agent"] = "Mozilla/5.0"
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if isinstance(data, dict) and "data" in data and isinstance(data["data"], (dict, list)):
                data = data["data"]
            
            out.append(f"\n=========================================")
            out.append(f"API: {name}")
            if isinstance(data, dict):
                so = data.get("SO", [])
                co = data.get("CO", [])
                out.append(f"Raw dict SO count: {len(so)}, CO count: {len(co)}")
                if so: out.append(f"Sample SO item: {json.dumps(so[0])[:300]}")
                if co: out.append(f"Sample CO item: {json.dumps(co[0])[:300]}")
            elif isinstance(data, list):
                out.append(f"Raw list count: {len(data)}")
                if data: out.append(f"Sample list item: {json.dumps(data[0])[:300]}")
    except Exception as e:
        out.append(f"ERROR: {e}")

out_path = r"C:\Users\admin\.gemini\antigravity-ide\scratch\psa-telegram-notifier\inspect_pending.txt"
with open(out_path, "w", encoding="utf-8") as f:
    f.write("\n".join(out))

print("Saved inspection output to:", out_path)
