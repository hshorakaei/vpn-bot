"""
services/xui_api.py
لایه ارتباط با API پنل 3X-UI (نسخه جدید React/Vite).
این نسخه از پنل قبل از لاگین نیاز به CSRF token دارد که از صفحه اصلی استخراج می‌شود.
"""

import re
import requests
import urllib3

import config

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

CSRF_PATTERN = re.compile(r'name="csrf-token"\s+content="([^"]+)"')


class XUIClient:
    def __init__(self):
        self.base_url = config.XUI_PANEL_URL
        self.session = requests.Session()
        self.session.verify = False
        self.session.headers.update({"User-Agent": "Mozilla/5.0 (vpn-bot)"})
        self._logged_in = False
        self._csrf_token = None

    def _fetch_csrf_token(self) -> str:
        resp = self.session.get(f"{self.base_url}/", timeout=10)
        resp.raise_for_status()
        match = CSRF_PATTERN.search(resp.text)
        if not match:
            raise RuntimeError("توکن CSRF در صفحه پنل پیدا نشد. ساختار پنل ممکن است تغییر کرده باشد.")
        return match.group(1)

    def login(self) -> bool:
        csrf_token = self._fetch_csrf_token()
        self._csrf_token = csrf_token
        resp = self.session.post(
            f"{self.base_url}/login",
            json={"username": config.XUI_USERNAME, "password": config.XUI_PASSWORD},
            headers={"X-CSRF-Token": csrf_token},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        self._logged_in = bool(data.get("success"))
        if self._logged_in:
            self.session.headers.update({"X-CSRF-Token": csrf_token})
        return self._logged_in

    def _ensure_login(self):
        if not self._logged_in:
            if not self.login():
                raise RuntimeError("ورود به پنل 3X-UI ناموفق بود. یوزرنیم/پسورد را بررسی کنید.")

    def list_inbounds(self) -> list:
        self._ensure_login()
        resp = self.session.get(f"{self.base_url}/panel/api/inbounds/list", timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if not data.get("success"):
            raise RuntimeError(f"خطا در دریافت اینباندها: {data.get('msg')}")
        return data.get("obj", [])

    def add_client(self, inbound_id: int, email: str,
                    total_gb: float, expire_timestamp_ms: int) -> dict:
        """
        افزودن کلاینت جدید به یک یا چند اینباند (endpoint جدید /panel/api/clients/add).
        UUID به‌صورت خودکار توسط پنل ساخته می‌شود و در پاسخ برگردانده می‌شود.
        خروجی: دیکشنری اطلاعات کلاینت ساخته‌شده (شامل uuid).
        """
        self._ensure_login()

        payload = {
            "client": {
                "email": email,
                "totalGB": int(total_gb * 1024 * 1024 * 1024),
                "expiryTime": expire_timestamp_ms,
                "tgId": 0,
                "limitIp": 0,
                "enable": True,
            },
            "inboundIds": [inbound_id],
        }

        resp = self.session.post(
            f"{self.base_url}/panel/api/clients/add",
            json=payload,
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        if not data.get("success"):
            raise RuntimeError(f"خطا در افزودن کلاینت: {data.get('msg')}")
        return data.get("obj", {})


    def get_inbound(self, inbound_id: int) -> dict:
        """دریافت اطلاعات کامل یک اینباند مشخص."""
        inbounds = self.list_inbounds()
        for ib in inbounds:
            if ib.get("id") == inbound_id:
                return ib
        raise RuntimeError(f"اینباند با id={inbound_id} پیدا نشد.")

    def get_client_by_email(self, inbound_id: int, email: str) -> dict:
        """
        پیدا کردن کلاینت با ایمیل از داخل یک اینباند.
        چون add_client اطلاعات کلاینت ساخته‌شده را برنمی‌گرداند،
        بعد از ساخت از این متد برای گرفتن UUID استفاده می‌کنیم.
        """
        inbound = self.get_inbound(inbound_id)
        settings = inbound.get("settings", {})
        if isinstance(settings, str):
            import json as _j
            settings = _j.loads(settings)
        for client in settings.get("clients", []):
            if client.get("email") == email:
                return client
        raise RuntimeError(f"کلاینت با ایمیل '{email}' در اینباند {inbound_id} پیدا نشد.")

if __name__ == "__main__":
    client = XUIClient()
    print("در حال تلاش برای ورود به پنل...")
    if client.login():
        print("✅ ورود موفق بود.")
        inbounds = client.list_inbounds()
        print(f"✅ تعداد اینباندهای یافت‌شده: {len(inbounds)}")
        for ib in inbounds:
            print(f"  - id={ib.get('id')} | remark={ib.get('remark')} | protocol={ib.get('protocol')} | port={ib.get('port')}")
    else:
        print("❌ ورود ناموفق بود.")
