"""
handlers/start.py
هندلر دستور /start و نمایش منوی اصلی کاربر.
"""

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

import database


def main_menu_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton("🛒 خرید سرویس", callback_data="buy")],
        [InlineKeyboardButton("📦 سرویس‌های من", callback_data="my_services")],
        [InlineKeyboardButton("📋 مشاهده پلن‌ها", callback_data="plans")],
        [InlineKeyboardButton("ℹ️ راهنمای اتصال", callback_data="guide")],
    ]
    return InlineKeyboardMarkup(buttons)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    with database.db_cursor() as cur:
        cur.execute(
            """
            INSERT INTO users (telegram_id, username, full_name)
            VALUES (?, ?, ?)
            ON CONFLICT(telegram_id) DO UPDATE SET
                username = excluded.username,
                full_name = excluded.full_name
            """,
            (user.id, user.username, user.full_name),
        )

    text = (
        f"سلام {user.first_name} 👋\n\n"
        "به ربات فروش VPN خوش آمدید.\n"
        "از منوی زیر یکی از گزینه‌ها را انتخاب کنید:"
    )
    await update.message.reply_text(text, reply_markup=main_menu_keyboard())
