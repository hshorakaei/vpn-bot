"""
bot.py
نقطه ورود اصلی ربات تلگرام فروش VPN.
"""

import logging

from telegram import Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

import config
import database
from handlers.start import start_command, main_menu_keyboard
from handlers.admin import get_admin_handlers
from handlers.buy import get_buy_handlers

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    placeholder_texts = {
        "my_services": "📦 بخش سرویس‌های من به‌زودی فعال می‌شود.",
        "plans": "📋 بخش مشاهده پلن‌ها به‌زودی فعال می‌شود.",
        "guide": "ℹ️ راهنمای اتصال به‌زودی اضافه می‌شود.",
    }
    text = placeholder_texts.get(query.data, "این گزینه هنوز پیاده‌سازی نشده است.")
    await query.edit_message_text(text)


async def back_main_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """بازگشت به منوی اصلی."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "از منوی زیر یکی از گزینه‌ها را انتخاب کنید:",
        reply_markup=main_menu_keyboard(),
    )


async def post_init(app: Application):
    from telegram import BotCommand
    await app.bot.set_my_commands([
        BotCommand("start", "شروع و نمایش منوی اصلی"),
        BotCommand("admin", "پنل مدیریت (مخصوص ادمین)"),
        BotCommand("cancel", "لغو عملیات جاری"),
    ])


def main():
    database.init_db()
    logger.info("دیتابیس آماده است.")

    app = Application.builder().token(config.BOT_TOKEN).post_init(post_init).build()

    app.add_handler(CommandHandler("start", start_command))

    # هندلرهای ادمین (باید قبل از عمومی باشند)
    for handler in get_admin_handlers():
        app.add_handler(handler)

    # هندلرهای خرید
    for handler in get_buy_handlers():
        app.add_handler(handler)

    # بازگشت به منو
    app.add_handler(CallbackQueryHandler(back_main_callback, pattern="^back_main$"))

    # هندلر عمومی منوی کاربر
    app.add_handler(CallbackQueryHandler(
        menu_callback,
        pattern="^(my_services|plans|guide)$",
    ))

    logger.info("ربات در حال اجراست...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
