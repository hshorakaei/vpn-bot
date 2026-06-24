"""
services/xui_api.py
لایه ارتباط با API پنل 3X-UI.
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
            # برخی نسخه‌های جدیدتر 3X-UI نیاز به CSRF ندارند
            return ""
        return match.group(1)

    def login(self) -> bool:
        csrf_token = self._fetch_csrf_token()
        self._csrf_token = csrf_token
        headers = {}
        if csrf_token:
            headers["X-CSRF-Token"] = csrf_token
        resp = self.session.post(
            f"{self.base_url}/login",
            json={"username": config.XUI_USERNAME, "password": config.XUI_PASSWORD},
            headers=headers,
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        self._logged_in = bool(data.get("success"))
        if self._logged_in and csrf_token:
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
               total_gb: float, expire_timestamp_ms: int, limit_ip: int = 0) -> dict:
    self._ensure_login()
    payload = {
        "client": {
            "email": email,
            "totalGB": int(total_gb * 1024 * 1024 * 1024),
            "expiryTime": expire_timestamp_ms,
            "tgId": 0,
            "limitIp": limit_ip,
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
        inbounds = self.list_inbounds()
        for ib in inbounds:
            if ib.get("id") == inbound_id:
                return ib
        raise RuntimeError(f"اینباند با id={inbound_id} پیدا نشد.")

    def get_client_by_email(self, inbound_id: int, email: str) -> dict:
        inbound = self.get_inbound(inbound_id)
        settings = inbound.get("settings", {})
        if isinstance(settings, str):
            import json as _j
            settings = _j.loads(settings)
        for client in settings.get("clients", []):
            if client.get("email") == email:
                return client
        raise RuntimeError(f"کلاینت با ایمیل '{email}' در اینباند {inbound_id} پیدا نشد.")
