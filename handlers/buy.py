"""
handlers/buy.py
هندلر خرید سرویس — پشتیبانی از پلن XUI و پلن دستی.
"""

import time
import qrcode
import io
from datetime import datetime, timezone

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes, CallbackQueryHandler,
    MessageHandler, ConversationHandler, filters,
)

import config
import database
from services import plans as plans_service
from services.xui_api import XUIClient
from services.link_builder import get_connection_link

WAITING_RECEIPT = 20


def _plan_label(p: dict) -> str:
    """برچسب نمایش پلن — سازگار با هر دو نوع xui و manual."""
    vol = f"{int(p['volume_gb'])}GB | " if p.get("volume_gb") else ""
    return f"{p['title']} | {vol}{p['duration_days']} روز | {p['price']:,} تومان"


async def show_plans(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    active_plans = plans_service.list_active_plans()
    if not active_plans:
        await query.edit_message_text(
            "در حال حاضر هیچ پلن فعالی موجود نیست.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="back_main")]]),
        )
        return

    buttons = []
    for p in active_plans:
        # پلن دستی: اگه موجودی نداشت نشون نده
        if p.get("plan_type") == "manual":
            if plans_service.get_available_config_count(p["id"]) == 0:
                continue

        buttons.append([InlineKeyboardButton(_plan_label(p), callback_data=f"buyplan_{p['id']}")])

    if not buttons:
        await query.edit_message_text(
            "در حال حاضر هیچ پلن فعالی موجود نیست.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="back_main")]]),
        )
        return

    buttons.append([InlineKeyboardButton("🔙 بازگشت", callback_data="back_main")])
    await query.edit_message_text(
        "📋 پلن‌های موجود:",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def confirm_plan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    plan_id = int(query.data.split("_")[1])
    plan = plans_service.get_plan(plan_id)
    if not plan:
        await query.edit_message_text("❌ این پلن دیگر موجود نیست.")
        return

    context.user_data["selected_plan_id"] = plan_id

    vol_line = f"💾 {int(plan['volume_gb'])} گیگابایت\n" if plan.get("volume_gb") else ""
    ptype_label = "🔧 XUI" if plan.get("plan_type") == "xui" else "📝 کانفیگ دستی"

    await query.edit_message_text(
        f"🛒 سرویس انتخابی:\n\n"
        f"📦 {plan['title']} ({ptype_label})\n"
        f"{vol_line}"
        f"📅 {plan['duration_days']} روز\n"
        f"💰 {plan['price']:,} تومان\n\n"
        "آیا ثبت سفارش کنم؟",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ ثبت سفارش", callback_data="submit_order")],
            [InlineKeyboardButton("🔙 بازگشت", callback_data="buy")],
        ]),
    )


async def submit_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    plan_id = context.user_data.get("selected_plan_id")
    if not plan_id:
        await query.edit_message_text("❌ خطا: دوباره /start بزنید.")
        return

    plan = plans_service.get_plan(plan_id)
    if not plan:
        await query.edit_message_text("❌ این پلن دیگر موجود نیست.")
        return

    user = update.effective_user
    with database.db_cursor() as cur:
        cur.execute(
            "INSERT INTO orders (telegram_id, plan_id, status) VALUES (?,?,'pending')",
            (user.id, plan_id),
        )
        order_id = cur.lastrowid

    context.user_data["pending_order_id"] = order_id

    card = plans_service.get_setting("payment_card", "تنظیم نشده - با ادمین تماس بگیرید")
    desc = plans_service.get_setting("payment_desc", "بعد از واریز، رسید را ارسال کنید.")

    vol_line = f"💾 {int(plan['volume_gb'])} گیگابایت\n" if plan.get("volume_gb") else ""

    await query.edit_message_text(
        f"✅ سفارش #{order_id} ثبت شد.\n\n"
        f"📦 پلن: {plan['title']}\n"
        f"{vol_line}"
        f"💰 مبلغ: {plan['price']:,} تومان\n\n"
        f"💳 شماره کارت:\n<code>{card}</code>\n\n"
        f"📝 {desc}\n\n"
        "⬇️ بعد از واریز، عکس رسید را همین‌جا ارسال کنید:",
        parse_mode="HTML",
    )


async def receive_receipt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    order_id = context.user_data.get("pending_order_id")
    if not order_id:
        return

    user = update.effective_user

    with database.db_cursor() as cur:
        cur.execute(
            "SELECT o.*, p.title, p.volume_gb, p.duration_days, p.price, p.plan_type "
            "FROM orders o JOIN plans p ON o.plan_id=p.id WHERE o.id=?",
            (order_id,),
        )
        order = cur.fetchone()

    if not order:
        return

    order = dict(order)
    if order["status"] != "pending":
        await update.message.reply_text("⚠️ این سفارش قبلاً پردازش شده است.")
        context.user_data.pop("pending_order_id", None)
        return

    vol_line = f"💾 {int(order['volume_gb'])} GB | " if order.get("volume_gb") else ""
    caption = (
        f"🧾 رسید پرداخت - سفارش #{order_id}\n\n"
        f"👤 {user.full_name}" + (f" (@{user.username})" if user.username else "") +
        f"\n🆔 <code>{user.id}</code>\n"
        f"📦 {order['title']}\n"
        f"{vol_line}{order['duration_days']} روز\n"
        f"💰 {order['price']:,} تومان"
    )
    buttons = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ تایید و فعال‌سازی", callback_data=f"approve_order_{order_id}"),
            InlineKeyboardButton("❌ رد سفارش", callback_data=f"reject_order_{order_id}"),
        ]
    ])

    sent_to_admin = False
    for admin_id in config.SUPER_ADMIN_IDS:
        try:
            if update.message.photo:
                await context.bot.send_photo(
                    chat_id=admin_id,
                    photo=update.message.photo[-1].file_id,
                    caption=caption,
                    parse_mode="HTML",
                    reply_markup=buttons,
                )
            elif update.message.document:
                await context.bot.send_document(
                    chat_id=admin_id,
                    document=update.message.document.file_id,
                    caption=caption,
                    parse_mode="HTML",
                    reply_markup=buttons,
                )
            sent_to_admin = True
        except Exception:
            pass

    # ارسال به ادمین‌های دیتابیس هم
    from services.admin_service import list_admins
    for admin in list_admins():
        if admin["telegram_id"] in config.SUPER_ADMIN_IDS:
            continue
        try:
            if update.message.photo:
                await context.bot.send_photo(
                    chat_id=admin["telegram_id"],
                    photo=update.message.photo[-1].file_id,
                    caption=caption,
                    parse_mode="HTML",
                    reply_markup=buttons,
                )
            elif update.message.document:
                await context.bot.send_document(
                    chat_id=admin["telegram_id"],
                    document=update.message.document.file_id,
                    caption=caption,
                    parse_mode="HTML",
                    reply_markup=buttons,
                )
            sent_to_admin = True
        except Exception:
            pass

    if sent_to_admin:
        await update.message.reply_text(
            "✅ رسید شما دریافت شد و برای بررسی ارسال گردید.\n"
            "بعد از تایید، سرویس شما فعال خواهد شد."
        )
        context.user_data.pop("pending_order_id", None)
    else:
        await update.message.reply_text("❌ خطا در ارسال رسید. لطفاً مجدداً تلاش کنید.")


async def _edit_admin_message(query, text: str, reply_markup=None):
    try:
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode="HTML")
    except Exception:
        try:
            await query.edit_message_caption(caption=text, reply_markup=reply_markup, parse_mode="HTML")
        except Exception:
            await query.message.reply_text(text, reply_markup=reply_markup, parse_mode="HTML")


async def approve_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    from services.admin_service import has_permission
    if not has_permission(update.effective_user.id, "approve_orders"):
        await query.answer("⛔ دسترسی ندارید.", show_alert=True)
        return

    order_id = int(query.data.split("_")[2])

    with database.db_cursor() as cur:
        cur.execute(
            "SELECT o.*, p.title, p.inbound_id, p.volume_gb, p.duration_days, p.plan_type "
            "FROM orders o JOIN plans p ON o.plan_id=p.id WHERE o.id=?",
            (order_id,),
        )
        order = cur.fetchone()

    if not order:
        await _edit_admin_message(query, "❌ سفارش پیدا نشد.")
        return

    order = dict(order)
    if order["status"] != "pending":
        await _edit_admin_message(query, f"⚠️ این سفارش قبلاً پردازش شده ({order['status']}).")
        return

    await _edit_admin_message(query, "⏳ در حال ساخت سرویس...")

    plan_type = order.get("plan_type", "xui")

    try:
        if plan_type == "manual":
            await _approve_manual_order(context, order, order_id)
        else:
            await _approve_xui_order(context, query, order, order_id)

        await query.edit_message_text(f"✅ سفارش #{order_id} تایید شد و سرویس برای کاربر ارسال گردید.")

    except Exception as e:
        with database.db_cursor() as cur:
            cur.execute("UPDATE orders SET status='failed' WHERE id=?", (order_id,))
        await query.edit_message_text(f"❌ خطا در ساخت سرویس: {e}")


async def _approve_xui_order(context, query, order, order_id):
    """تایید سفارش XUI — ساخت کلاینت در پنل."""
    timestamp = int(time.time())
    email = f"tg{order['telegram_id']}_{order['plan_id']}_{timestamp}"
    expire_ms = int((timestamp + order["duration_days"] * 86400) * 1000)

    xui = XUIClient()
    plan = plans_service.get_plan(order["plan_id"])
    limit_ip = plan.get("limit_ip", 0) if plan else 0
    xui.add_client(
        inbound_id=order["inbound_id"],
        email=email,
        total_gb=order["volume_gb"],
        expire_timestamp_ms=expire_ms,
        limit_ip=limit_ip,
    )
    client_info = xui.get_client_by_email(order["inbound_id"], email)
    uuid = client_info.get("id", "")

    link = get_connection_link(
        inbound_id=order["inbound_id"],
        uuid=uuid,
        remark=f"VPN-{order['title']}",
    )

    expire_dt = datetime.fromtimestamp(expire_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")

    with database.db_cursor() as cur:
        cur.execute(
            "INSERT INTO purchases (telegram_id, plan_id, inbound_id, client_email, client_uuid, expire_at, volume_gb) "
            "VALUES (?,?,?,?,?,?,?)",
            (order["telegram_id"], order["plan_id"], order["inbound_id"], email, uuid, expire_dt, order["volume_gb"]),
        )
        cur.execute("UPDATE orders SET status='approved' WHERE id=?", (order_id,))

    qr_img = qrcode.make(link)
    buf = io.BytesIO()
    qr_img.save(buf, format="PNG")
    buf.seek(0)

    await context.bot.send_photo(
        chat_id=order["telegram_id"],
        photo=buf,
        caption=(
            f"✅ سرویس شما فعال شد!\n\n"
            f"📦 {order['title']}\n"
            f"💾 {int(order['volume_gb'])} گیگابایت\n"
            f"📅 انقضا: {expire_dt}\n\n"
            f"🔗 لینک اتصال:\n<code>{link}</code>\n\n"
            "لینک را کپی یا QR Code را اسکن کنید."
        ),
        parse_mode="HTML",
    )


async def _approve_manual_order(context, order, order_id):
    """تایید سفارش دستی — ارسال کانفیگ از موجودی."""
    config_row = plans_service.pop_manual_config(order["plan_id"], order["telegram_id"])
    if not config_row:
        raise RuntimeError("موجودی کانفیگ تمام شده است. لطفاً کانفیگ جدید اضافه کنید.")

    timestamp = int(time.time())
    expire_dt = datetime.fromtimestamp(
        timestamp + order["duration_days"] * 86400
    ).strftime("%Y-%m-%d")

    with database.db_cursor() as cur:
        cur.execute(
            "INSERT INTO purchases (telegram_id, plan_id, config_text, expire_at) VALUES (?,?,?,?)",
            (order["telegram_id"], order["plan_id"], config_row["config_text"], expire_dt),
        )
        cur.execute("UPDATE orders SET status='approved' WHERE id=?", (order_id,))

    await context.bot.send_message(
        chat_id=order["telegram_id"],
        text=(
            f"✅ سرویس شما فعال شد!\n\n"
            f"📦 {order['title']}\n"
            f"📅 انقضا: {expire_dt}\n\n"
            f"🔗 کانفیگ اتصال:\n<code>{config_row['config_text']}</code>\n\n"
            "کانفیگ را کپی کنید و در نرم‌افزار وارد کنید."
        ),
        parse_mode="HTML",
    )


async def reject_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    from services.admin_service import has_permission
    if not has_permission(update.effective_user.id, "approve_orders"):
        await query.answer("⛔ دسترسی ندارید.", show_alert=True)
        return

    order_id = int(query.data.split("_")[2])

    with database.db_cursor() as cur:
        cur.execute("SELECT telegram_id FROM orders WHERE id=? AND status='pending'", (order_id,))
        order = cur.fetchone()

    if not order:
        await _edit_admin_message(query, "❌ سفارش پیدا نشد یا قبلاً پردازش شده.")
        return

    with database.db_cursor() as cur:
        cur.execute("UPDATE orders SET status='rejected' WHERE id=?", (order_id,))

    await context.bot.send_message(
        chat_id=order["telegram_id"],
        text=f"❌ سفارش #{order_id} تایید نشد.\nدر صورت سوال با پشتیبانی تماس بگیرید.",
    )
    await _edit_admin_message(query, f"❌ سفارش #{order_id} رد شد.")


def get_buy_handlers():
    return [
        CallbackQueryHandler(show_plans,    pattern="^buy$"),
        CallbackQueryHandler(confirm_plan,  pattern="^buyplan_\\d+$"),
        CallbackQueryHandler(submit_order,  pattern="^submit_order$"),
        CallbackQueryHandler(approve_order, pattern="^approve_order_\\d+$"),
        CallbackQueryHandler(reject_order,  pattern="^reject_order_\\d+$"),
        MessageHandler(
            filters.PHOTO | filters.Document.ALL,
            receive_receipt,
        ),
    ]
