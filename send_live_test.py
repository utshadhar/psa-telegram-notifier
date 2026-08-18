import sys, os, json, datetime, urllib.request, socket

script_dir = r"C:\Users\admin\.gemini\antigravity-ide\scratch\psa-telegram-notifier"
sys.path.insert(0, script_dir)

orig_bind = socket.socket.bind
def dummy_bind(self, addr):
    if len(addr) >= 2 and addr[1] == 8089:
        return
    return orig_bind(self, addr)
socket.socket.bind = dummy_bind

import notifier

out_lines = []

config = notifier.load_config()
local_now = notifier.get_local_time(config)
b_date, _ = notifier.get_business_date_and_active(local_now, 9, 1)

out_lines.append(f"Business Date: {b_date}")
stats = notifier.fetch_all_apis(b_date, config)

out_lines.append("Fetched Stats:")
for name, s in stats.items():
    if not name.startswith("_"):
        out_lines.append(f"  {name}: total_so={s.get('total_pending_so')}, total_co={s.get('total_pending_co')}")

msg = notifier.format_telegram_message(stats, b_date, config)

out_lines.append("\n--- FORMATTED TELEGRAM MESSAGE ---")
out_lines.append(msg)
out_lines.append("----------------------------------\n")

ok, err = notifier.send_telegram_notification(msg, config)
out_lines.append(f"Send result -> ok: {ok}, err: {err}")

with open(os.path.join(script_dir, "live_output_test.txt"), "w", encoding="utf-8") as f:
    f.write("\n".join(out_lines))

print("Saved output to live_output_test.txt")
