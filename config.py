"""
config.py
بارگذاری تمام تنظیمات حساس پروژه از فایل .env
"""

import os
from dotenv import load_dotenv

load_dotenv()


def _require(key: str) -> str:
    value = os.getenv(key)
    if not value:
        raise RuntimeError(
            f"متغیر '{key}' در فایل .env تنظیم نشده است. "
            f"لطفاً فایل .env را بررسی و مقداردهی کنید."
        )
    return value


# --- تلگرام ---
BOT_TOKEN = _require("BOT_TOKEN")
ADMIN_IDS = [
    int(x.strip()) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()
]

# --- پنل 3X-UI ---
# توجه: شناسه اینباند (inbound_id) ثابت نیست؛ هر پلن فروش، اینباند
# مخصوص خودش را در دیتابیس (جدول plans) دارد و توسط ادمین تنظیم می‌شود.
XUI_PANEL_URL = _require("XUI_PANEL_URL").rstrip("/")
XUI_USERNAME = _require("XUI_USERNAME")
XUI_PASSWORD = _require("XUI_PASSWORD")

# --- دیتابیس ---
DATABASE_PATH = os.getenv("DATABASE_PATH", "data/vpn_bot.db")
