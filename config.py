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


def _int_list(key: str) -> list:
    return [int(x.strip()) for x in os.getenv(key, "").split(",") if x.strip()]


# --- تلگرام ---
BOT_TOKEN = _require("BOT_TOKEN")

# super_admin ها از .env هستند و قابل حذف توسط ادمین‌های دیگر نیستند
SUPER_ADMIN_IDS = _int_list("SUPER_ADMIN_IDS")

# برای سازگاری با کدهای قدیمی — از دیتابیس بخوان در صورت نیاز
ADMIN_IDS = SUPER_ADMIN_IDS

# --- پنل 3X-UI ---
XUI_PANEL_URL = _require("XUI_PANEL_URL").rstrip("/")
XUI_USERNAME = _require("XUI_USERNAME")
XUI_PASSWORD = _require("XUI_PASSWORD")

# آدرس سرور برای لینک‌سازی — هرگز مستقیم در کد ننویس
SERVER_HOST = _require("SERVER_HOST")

# --- دیتابیس ---
DATABASE_PATH = os.getenv("DATABASE_PATH", "data/vpn_bot.db")
