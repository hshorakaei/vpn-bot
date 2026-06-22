"""
services/link_builder.py
ساخت لینک اتصال vless:// برای هر اینباند بر اساس تنظیمات آن.
"""

from urllib.parse import urlencode, quote
from services.xui_api import XUIClient


def build_vless_reality_link(uuid: str, inbound: dict, remark: str) -> str:
    """ساخت لینک vless برای اینباند از نوع Reality."""
    stream = inbound.get("streamSettings", {})
    reality = stream.get("realitySettings", {})
    reality_inner = reality.get("settings", {})
    tcp_settings = stream.get("tcpSettings", {})

    server = inbound.get("shareAddr") or "216.9.226.249"
    port = inbound.get("port", 443)
    public_key = reality_inner.get("publicKey", "")
    fingerprint = reality_inner.get("fingerprint", "chrome")
    server_names = reality.get("serverNames", [])
    sni = server_names[0] if server_names else ""
    short_ids = reality.get("shortIds", [""])
    sid = short_ids[0] if short_ids else ""
    spider_x = reality_inner.get("spiderX", "/")

    params = {
        "type": stream.get("network", "tcp"),
        "security": "reality",
        "pbk": public_key,
        "fp": fingerprint,
        "sni": sni,
        "sid": sid,
        "spx": spider_x,
        "flow": "xtls-rprx-vision",
    }

    query = "&".join(f"{k}={quote(str(v), safe='')}" for k, v in params.items())
    link = f"vless://{uuid}@{server}:{port}?{query}#{quote(remark, safe='')}"
    return link


def get_connection_link(inbound_id: int, uuid: str, remark: str) -> str:
    """دریافت تنظیمات اینباند از پنل و ساخت لینک اتصال."""
    client = XUIClient()
    inbound = client.get_inbound(inbound_id)
    protocol = inbound.get("protocol", "vless")
    stream = inbound.get("streamSettings", {})
    security = stream.get("security", "")

    if protocol == "vless" and security == "reality":
        return build_vless_reality_link(uuid, inbound, remark)

    raise NotImplementedError(
        f"ساخت لینک برای پروتکل {protocol}/{security} هنوز پیاده‌سازی نشده است."
    )
