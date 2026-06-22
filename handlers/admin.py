"""
handlers/admin.py
پنل مدیریت ادمین: افزودن/حذف/مشاهده پلن‌ها.
دسترسی این بخش فقط برای کاربرانی است که آیدی‌شان در config.ADMIN_IDS باشد.
"""

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes, ConversationHandler, CommandHandler,
    CallbackQueryHandler, MessageHandler, filters,
)

import config
from services import plans as plans_service
from services.xui_api import XUIClient

TITLE, INBOUND, VOLUME, DURATION, PRICE, CONFIRM = range(6)


def is_admin(user_id: int) -> bool:
    return user_id in config.ADMIN_IDS


async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    buttons = [
        [InlineKeyboardButton("➕ افزودن پلن جدید", callback_data="admin_add_plan")],
        [InlineKeyboardButton("📋 لیست پلن‌ها", callback_data="admin_list_plans")],
    ]
    await update.message.reply_text(
        "🛠 پنل مدیریت\nیکی از گزینه‌ها را انتخاب کنید:",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def admin_list_plans(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(update.effective_user.id):
        return

    all_plans = plans_service.list_all_plans()
    if not all_plans:
        await query.edit_message_text("هیچ پلنی هنوز ثبت نشده است.")
        return

    lines = ["📋 لیست پلن‌ها:\n"]
    for p in all_plans:
        status = "✅ فعال" if p["is_active"] else "❌ غیرفعال"
        lines.append(
            f"#{p['id']} | {p['title']} | {p['volume_gb']}GB | "
            f"{p['duration_days']} روز | {p['price']:,} تومان | {status}"
        )
    await query.edit_message_text("\n".join(lines))


async def add_plan_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END

    await query.edit_message_text("عنوان پلن را وارد کنید (مثلاً «۱ ماهه ۵۰ گیگ»):")
    return TITLE


async def add_plan_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["new_plan_title"] = update.message.text.strip()

    try:
        client = XUIClient()
        inbounds = client.list_inbounds()
    except Exception as e:
        await update.message.reply_text(f"❌ خطا در دریافت اینباندها از پنل: {e}")
        return ConversationHandler.END

    context.user_data["inbounds_cache"] = {
        str(ib["id"]): ib for ib in inbounds
    }

    lines = ["یکی از اینباندهای زیر را با ارسال شماره ID آن انتخاب کنید:\n"]
    for ib in inbounds:
        lines.append(f"🔹 ID: {ib['id']} | {ib.get('remark')} | {ib.get('protocol')} | پورت {ib.get('port')}")
    await update.message.reply_text("\n".join(lines))
    return INBOUND


async def add_plan_inbound(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    valid_ids = context.user_data.get("inbounds_cache", {})

    if text not in valid_ids:
        await update.message.reply_text("❌ این ID معتبر نیست. دوباره شماره صحیح را وارد کنید:")
        return INBOUND

    context.user_data["new_plan_inbound_id"] = int(text)
    await update.message.reply_text("حجم پلن را به گیگابایت وارد کنید (مثلاً 50):")
    return VOLUME


async def add_plan_volume(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    try:
        volume = float(text)
        if volume <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ عدد معتبر وارد کنید (مثلاً 50):")
        return VOLUME

    context.user_data["new_plan_volume"] = volume
    await update.message.reply_text("مدت زمان پلن را به روز وارد کنید (مثلاً 30):")
    return DURATION


async def add_plan_duration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    try:
        duration = int(text)
        if duration <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ عدد صحیح وارد کنید (مثلاً 30):")
        return DURATION

    context.user_data["new_plan_duration"] = duration
    await update.message.reply_text("قیمت پلن را به تومان وارد کنید (مثلاً 150000):")
    return PRICE


async def add_plan_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    try:
        price = int(text)
        if price <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ عدد صحیح وارد کنید (مثلاً 150000):")
        return PRICE

    context.user_data["new_plan_price"] = price

    d = context.user_data
    summary = (
        "لطفاً اطلاعات پلن را تایید کنید:\n\n"
        f"عنوان: {d['new_plan_title']}\n"
        f"اینباند ID: {d['new_plan_inbound_id']}\n"
        f"حجم: {d['new_plan_volume']} GB\n"
        f"مدت: {d['new_plan_duration']} روز\n"
        f"قیمت: {price:,} تومان\n\n"
        "برای تایید عدد 1 و برای لغو عدد 0 را ارسال کنید."
    )
    await update.message.reply_text(summary)
    return CONFIRM


async def add_plan_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    d = context.user_data

    if text == "1":
        plan_id = plans_service.create_plan(
            title=d["new_plan_title"],
            inbound_id=d["new_plan_inbound_id"],
            volume_gb=d["new_plan_volume"],
            duration_days=d["new_plan_duration"],
            price=d["new_plan_price"],
        )
        await update.message.reply_text(f"✅ پلن با شماره #{plan_id} با موفقیت ساخته شد.")
    else:
        await update.message.reply_text("❌ ساخت پلن لغو شد.")

    context.user_data.clear()
    return ConversationHandler.END


async def add_plan_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("عملیات لغو شد.")
    return ConversationHandler.END


def get_admin_handlers():
    add_plan_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(add_plan_start, pattern="^admin_add_plan$")],
        states={
            TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_plan_title)],
            INBOUND: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_plan_inbound)],
            VOLUME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_plan_volume)],
            DURATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_plan_duration)],
            PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_plan_price)],
            CONFIRM: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_plan_confirm)],
        },
        fallbacks=[CommandHandler("cancel", add_plan_cancel)],
    )

    return [
        CommandHandler("admin", admin_command),
        add_plan_conv,
        CallbackQueryHandler(admin_list_plans, pattern="^admin_list_plans$"),
    ]
