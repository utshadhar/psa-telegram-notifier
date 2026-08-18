import urllib.request, json, datetime, sys

script_dir = r"C:\Users\admin\.gemini\antigravity-ide\scratch\psa-telegram-notifier"

# Fetch PSA data directly
url = "https://psa.mgi.org/api/getALLData/2026-08-17/2026-08-18/0?server=0"
headers = {"Accept": "application/json", "User-Agent": "Mozilla/5.0"}
req = urllib.request.Request(url, headers=headers)
with urllib.request.urlopen(req, timeout=12) as resp:
    data = json.loads(resp.read().decode("utf-8"))

# Parse using notifier functions (by copying parse logic or running directly)
raw_so_list = data.get("SO", [])
raw_co_list = data.get("CO", [])

print(f"Direct PSA URL: {url}")
print(f"Raw SO List Count: {len(raw_so_list)}")
print(f"Raw CO List Count: {len(raw_co_list)}")

# Test parse_psa_data
so_ids = set()
co_ids = set()

for item in raw_so_list:
    if isinstance(item, dict):
        tx_id = item.get("TransactionId") or item.get("Transaction_ID")
        if tx_id:
            so_ids.add(str(tx_id))

for item in raw_co_list:
    if isinstance(item, dict):
        pay_id = item.get("pay_id") or item.get("TransactionId")
        if pay_id:
            co_ids.add(str(pay_id))

print(f"Unique SO IDs: {len(so_ids)}")
print(f"Unique CO IDs: {len(co_ids)}")
