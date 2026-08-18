import urllib.request, json, sys, socket

_orig_bind = socket.socket.bind
_orig_listen = socket.socket.listen

def _fake_bind(self, addr):
    if len(addr) >= 2 and addr[1] == 8089: return
    return _orig_bind(self, addr)

def _fake_listen(self, backlog=1):
    try: return _orig_listen(self, backlog)
    except OSError: pass

socket.socket.bind = _fake_bind
socket.socket.listen = _fake_listen

sys.path.insert(0, r"C:\Users\admin\.gemini\antigravity-ide\scratch\psa-telegram-notifier")
import notifier

url = "https://psa.mgi.org/api/getALLData/2026-08-17/2026-08-18/0?server=0"
headers = {"Accept": "application/json", "User-Agent": "Mozilla/5.0"}
req = urllib.request.Request(url, headers=headers)
with urllib.request.urlopen(req, timeout=12) as resp:
    raw = resp.read().decode("utf-8")
    data = json.loads(raw)

if isinstance(data, dict) and "data" in data and isinstance(data["data"], (dict, list)):
    data = data["data"]

so_list = data.get("SO", []) if isinstance(data, dict) else []
co_list = data.get("CO", []) if isinstance(data, dict) else []

print(f"Raw SO count: {len(so_list)}, Raw CO count: {len(co_list)}")

config = notifier.load_config()

# Step through first 10 SO items
for idx, item in enumerate(so_list[:10]):
    process = str(item.get("process") or "").strip().upper()
    is_so = (process == "SO")
    server = notifier.get_server_allocation(item) if hasattr(notifier, "get_server_allocation") else "Unknown"
    tx_id = notifier.get_unique_id(item, ["TransactionId", "transactionid", "Transaction_ID", "transaction_id"])
    is_pending = notifier.is_so_pending(item, "PSA")
    print(f"SO item #{idx}: process='{process}', is_so={is_so}, server='{server}', tx_id='{tx_id}', is_pending={is_pending}")

# Step through first 10 CO items
for idx, item in enumerate(co_list[:10]):
    process = str(item.get("process") or "").strip().upper()
    is_co = (process in ("CO", "CONTRACT", "COLLECTION"))
    co_id = notifier.get_unique_id(item, ["pay_id", "payid", "PayId", "Transaction_ID", "TransactionId"])
    is_pending = notifier.is_co_pending(item, "PSA")
    print(f"CO item #{idx}: process='{process}', is_co={is_co}, co_id='{co_id}', is_pending={is_pending}")
