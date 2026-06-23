"""
handlers/start.py
هندلر /start و منوی اصلی کاربر.
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
        [InlineKeyboardButton("🎧 پشتیبانی", callback_data="support")],
    ]
    return InlineKeyboardMarkup(buttons)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    with database.db_cursor() as cur:
        cur.execute(
            """INSERT INTO users (telegram_id, username, full_name)
               VALUES (?,?,?)
               ON CONFLICT(telegram_id) DO UPDATE SET
                   username=excluded.username,
                   full_name=excluded.full_name""",
            (user.id, user.username, user.full_name),
        )
        cur.execute("SELECT is_banned FROM users WHERE telegram_id=?", (user.id,))
        row = cur.fetchone()

    if row and row["is_banned"]:
        await update.message.reply_text("⛔ دسترسی شما به ربات محدود شده است.")
        return

    from services.plans import get_setting
    welcome = get_setting("welcome_message", f"سلام {user.first_name} 👋\n\nبه ربات فروش VPN خوش آمدید.")
    await update.message.reply_text(
        welcome.replace("{name}", user.first_name),
        reply_markup=main_menu_keyboard(),
    )
