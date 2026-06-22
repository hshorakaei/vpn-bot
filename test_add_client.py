import time
import json

from services.xui_api import XUIClient

client = XUIClient()

test_email = f"test_{int(time.time())}"
expire_ms = int((time.time() + 86400) * 1000)

print(f"در حال ساخت کلاینت آزمایشی با ایمیل: {test_email}")
client.add_client(
    inbound_id=1,
    email=test_email,
    total_gb=1,
    expire_timestamp_ms=expire_ms,
)
print("✅ کلاینت ساخته شد. در حال جستجوی آن در لیست اینباندها...")

inbounds = client.list_inbounds()
for ib in inbounds:
    if ib.get("id") == 1:
        settings = ib.get("settings", {})
        if isinstance(settings, str):
            settings = json.loads(settings)
        for c in settings.get("clients", []):
            if c.get("email") == test_email:
                print("✅ کلاینت پیدا شد:")
                print(json.dumps(c, indent=2, ensure_ascii=False))
