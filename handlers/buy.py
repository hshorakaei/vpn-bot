"""
handlers/buy.py
هندلر خرید سرویس: نمایش پلن‌ها، ثبت خرید، ارسال لینک و QR Code.
"""

import time
import qrcode
import io

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler, CallbackQueryHandler

import database
from services import plans as plans_service
from services.xui_api import XUIClient
from services.link_builder import get_connection_link

CONFIRM_BUY = 10


async def show_plans(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """نمایش لیست پلن‌های فعال به کاربر."""
    query = update.callback_query
    await query.answer()

    active_plans = plans_service.list_active_plans()
    if not active_plans:
        await query.edit_message_text("در حال حاضر هیچ پلن فعالی موجود نیست.")
        return

    buttons = []
    for p in active_plans:
        label = f"{p['title']} | {int(p['volume_gb'])}GB | {p['duration_days']} روز | {p['price']:,} تومان"
        buttons.append([InlineKeyboardButton(label, callback_data=f"buyplan_{p['id']}")])
    buttons.append([InlineKeyboardButton("🔙 بازگشت", callback_data="back_main")])

    await query.edit_message_text(
        "📋 پلن‌های موجود:\nیکی را انتخاب کنید:",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def confirm_plan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """نمایش جزئیات پلن انتخابی و درخواست تایید خرید."""
    query = update.callback_query
    await query.answer()

    plan_id = int(query.data.split("_")[1])
    plan = plans_service.get_plan(plan_id)
    if not plan:
        await query.edit_message_text("❌ این پلن دیگر موجود نیست.")
        return

    context.user_data["selected_plan_id"] = plan_id

    text = (
        f"🛒 جزئیات سرویس انتخابی:\n\n"
        f"📦 پلن: {plan['title']}\n"
        f"💾 حجم: {int(plan['volume_gb'])} گیگابایت\n"
        f"📅 مدت: {plan['duration_days']} روز\n"
        f"💰 قیمت: {plan['price']:,} تومان\n\n"
        "آیا خرید را تایید می‌کنید؟"
    )
    buttons = [
        [InlineKeyboardButton("✅ تایید و خرید", callback_data="confirm_buy")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="buy")],
    ]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons))


async def process_purchase(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """انجام خرید واقعی: ساخت کلاینت در پنل، ذخیره در دیتابیس، ارسال لینک."""
    query = update.callback_query
    await query.answer()

    plan_id = context.user_data.get("selected_plan_id")
    if not plan_id:
        await query.edit_message_text("❌ خطا: پلنی انتخاب نشده است. دوباره /start بزنید.")
        return

    plan = plans_service.get_plan(plan_id)
    if not plan:
        await query.edit_message_text("❌ این پلن دیگر موجود نیست.")
        return

    await query.edit_message_text("⏳ در حال ساخت سرویس شما، لطفاً چند ثانیه صبر کنید...")

    user = update.effective_user
    timestamp = int(time.time())
    email = f"tg{user.id}_{plan_id}_{timestamp}"
    expire_ms = int((timestamp + plan["duration_days"] * 86400) * 1000)

    try:
        xui = XUIClient()
        xui.add_client(
            inbound_id=plan["inbound_id"],
            email=email,
            total_gb=plan["volume_gb"],
            expire_timestamp_ms=expire_ms,
        )
        client_info = xui.get_client_by_email(plan["inbound_id"], email)
        uuid = client_info.get("id", "")

        link = get_connection_link(
            inbound_id=plan["inbound_id"],
            uuid=uuid,
            remark=f"VPN-{plan['title']}",
        )

        # ذخیره خرید در دیتابیس
        from datetime import datetime, timezone
        expire_dt = datetime.fromtimestamp(expire_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

        with database.db_cursor() as cur:
            cur.execute(
                """
                INSERT INTO purchases
                    (telegram_id, plan_id, inbound_id, client_email, client_uuid, expire_at, volume_gb)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (user.id, plan_id, plan["inbound_id"], email, uuid, expire_dt, plan["volume_gb"]),
            )

        # ساخت QR Code
        qr_img = qrcode.make(link)
        buf = io.BytesIO()
        qr_img.save(buf, format="PNG")
        buf.seek(0)

        caption = (
            f"✅ سرویس شما با موفقیت فعال شد!\n\n"
            f"📦 پلن: {plan['title']}\n"
            f"💾 حجم: {int(plan['volume_gb'])} گیگابایت\n"
            f"📅 انقضا: {expire_dt[:10]}\n\n"
            f"🔗 لینک اتصال:\n<code>{link}</code>\n\n"
            "برای اتصال، لینک بالا را کپی کنید یا QR Code را اسکن کنید."
        )

        await context.bot.send_photo(
            chat_id=user.id,
            photo=buf,
            caption=caption,
            parse_mode="HTML",
        )

    except Exception as e:
        await context.bot.send_message(
            chat_id=user.id,
            text=f"❌ خطا در ساخت سرویس: {e}\nلطفاً با پشتیبانی تماس بگیرید.",
        )
        return

    context.user_data.clear()


def get_buy_handlers():
    return [
        CallbackQueryHandler(show_plans, pattern="^buy$"),
        CallbackQueryHandler(confirm_plan, pattern="^buyplan_"),
        CallbackQueryHandler(process_purchase, pattern="^confirm_buy$"),
    ]
