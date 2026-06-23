"""
handlers/admin.py
پنل مدیریت کامل با سیستم نقش‌بندی سه‌سطحی.
"""

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes, ConversationHandler, CommandHandler,
    CallbackQueryHandler, MessageHandler, filters,
)

from services import plans as plans_service
from services import admin_service
from services.xui_api import XUIClient

# ─── states ──────────────────────────────────────────────
# افزودن پلن xui
TITLE, INBOUND, VOLUME, DURATION, PRICE, CONFIRM = range(6)
# تنظیمات پرداخت
SET_CARD, SET_PAYMENT_DESC = range(10, 12)
# ویرایش پلن
EDIT_FIELD, EDIT_VALUE = range(20, 22)
# افزودن ادمین
ADD_ADMIN_ID, ADD_ADMIN_ROLE = range(30, 32)
# پیام همگانی
BROADCAST_MSG = 40
# تنظیمات دیگر
SET_SUPPORT_ID, SET_WELCOME = range(50, 52)
# افزودن پلن دستی
MANUAL_TITLE, MANUAL_DURATION, MANUAL_PRICE, MANUAL_CONFIG_TEXT = range(60, 64)
# افزودن کانفیگ به پلن موجود
ADD_CONFIG_TO_PLAN = 70


# ─── helpers ─────────────────────────────────────────────

def _perm(perm: str):
    """دکوراتور ساده برای چک دسترسی."""
    def decorator(func):
        async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
            uid = update.effective_user.id
            if not admin_service.has_permission(uid, perm) and not admin_service.has_permission(uid, "all"):
                if update.callback_query:
                    await update.callback_query.answer("⛔ دسترسی ندارید.", show_alert=True)
                else:
                    await update.message.reply_text("⛔ دسترسی ندارید.")
                return
            return await func(update, context)
        return wrapper
    return decorator


def _admin_main_keyboard(user_id: int) -> InlineKeyboardMarkup:
    role = admin_service.get_role(user_id)
    is_super = role == "super_admin"
    is_admin_plus = role in ("super_admin", "admin")

    rows = []
    if is_admin_plus:
        rows += [
            [InlineKeyboardButton("➕ افزودن پلن XUI", callback_data="admin_add_plan"),
             InlineKeyboardButton("➕ افزودن پلن دستی", callback_data="admin_add_manual_plan")],
            [InlineKeyboardButton("📋 مدیریت پلن‌ها", callback_data="admin_list_plans")],
            [InlineKeyboardButton("💳 تنظیمات پرداخت", callback_data="admin_payment_settings")],
            [InlineKeyboardButton("📢 پیام همگانی", callback_data="admin_broadcast")],
            [InlineKeyboardButton("📊 آمار", callback_data="admin_stats")],
        ]
    rows += [
        [InlineKeyboardButton("👥 مشاهده کاربران", callback_data="admin_users")],
        [InlineKeyboardButton("📦 سفارش‌های در انتظار", callback_data="admin_pending_orders")],
    ]
    if is_super:
        rows += [
            [InlineKeyboardButton("🔑 مدیریت ادمین‌ها", callback_data="admin_manage_admins")],
            [InlineKeyboardButton("⚙️ تنظیمات عمومی", callback_data="admin_general_settings")],
        ]
    return InlineKeyboardMarkup(rows)


async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not admin_service.is_admin(uid):
        return
    role_label = admin_service.ROLE_LABELS.get(admin_service.get_role(uid), "")
    await update.message.reply_text(
        f"🛠 پنل مدیریت\nنقش شما: {role_label}",
        reply_markup=_admin_main_keyboard(uid),
    )


async def admin_back(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = update.effective_user.id
    if not admin_service.is_admin(uid):
        return
    role_label = admin_service.ROLE_LABELS.get(admin_service.get_role(uid), "")
    await query.edit_message_text(
        f"🛠 پنل مدیریت\nنقش شما: {role_label}",
        reply_markup=_admin_main_keyboard(uid),
    )


# ─── آمار ────────────────────────────────────────────────

async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not admin_service.has_permission(update.effective_user.id, "view_stats"):
        await query.answer("⛔ دسترسی ندارید.", show_alert=True)
        return
    s = plans_service.get_stats()
    text = (
        "📊 آمار کلی:\n\n"
        f"👥 کل کاربران: {s['total_users']:,}\n"
        f"🆕 کاربران هفت روز اخیر: {s['new_users_week']:,}\n"
        f"✅ سفارش‌های تایید شده: {s['total_orders']:,}\n"
        f"⏳ سفارش‌های در انتظار: {s['pending_orders']:,}\n"
        f"💰 درآمد کل: {s['total_revenue']:,} تومان"
    )
    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back")]]),
    )


# ─── مدیریت پلن‌ها ──────────────────────────────────────

async def admin_list_plans(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not admin_service.has_permission(update.effective_user.id, "manage_plans"):
        await query.answer("⛔ دسترسی ندارید.", show_alert=True)
        return

    all_plans = plans_service.list_all_plans()
    if not all_plans:
        await query.edit_message_text(
            "هیچ پلنی ثبت نشده است.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back")]]),
        )
        return

    buttons = []
    for p in all_plans:
        status = "✅" if p["is_active"] else "❌"
        ptype = "🔧" if p["plan_type"] == "xui" else "📝"
        vol = f"{int(p['volume_gb'])}GB | " if p.get("volume_gb") else ""
        label = f"{status}{ptype} #{p['id']} {p['title']} | {vol}{p['duration_days']}روز | {p['price']:,}ت"
        buttons.append([InlineKeyboardButton(label, callback_data=f"admin_plan_{p['id']}")])
    buttons.append([InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back")])

    await query.edit_message_text(
        "📋 روی هر پلن بزنید برای مدیریت:",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def admin_plan_detail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    plan_id = int(query.data.split("_")[2])
    await _show_plan_detail(query, plan_id, update.effective_user.id)


async def _show_plan_detail(query, plan_id, user_id):
    plan = plans_service.get_plan(plan_id)
    if not plan:
        await query.edit_message_text("❌ این پلن پیدا نشد.")
        return

    ptype = plan.get("plan_type", "xui")
    status = "✅ فعال" if plan["is_active"] else "❌ غیرفعال"
    toggle_label = "❌ غیرفعال کردن" if plan["is_active"] else "✅ فعال کردن"

    if ptype == "xui":
        detail = (
            f"اینباند ID: {plan['inbound_id']}\n"
            f"حجم: {plan['volume_gb']} GB\n"
        )
    else:
        avail = plans_service.get_available_config_count(plan_id)
        detail = f"نوع: کانفیگ دستی\nموجودی: {avail} کانفیگ آزاد\n"

    text = (
        f"📦 پلن #{plan['id']}: {plan['title']}\n\n"
        + detail
        + f"مدت: {plan['duration_days']} روز\n"
        f"قیمت: {plan['price']:,} تومان\n"
        f"وضعیت: {status}"
    )

    buttons = [
        [InlineKeyboardButton(toggle_label, callback_data=f"admin_toggle_{plan_id}")],
        [InlineKeyboardButton("✏️ ویرایش پلن", callback_data=f"admin_edit_{plan_id}")],
    ]
    if ptype == "manual":
        buttons.append([InlineKeyboardButton("➕ افزودن کانفیگ", callback_data=f"admin_addconfig_{plan_id}")])
        buttons.append([InlineKeyboardButton("📋 مشاهده کانفیگ‌ها", callback_data=f"admin_listconfigs_{plan_id}")])
    buttons.append([InlineKeyboardButton("🗑 حذف پلن", callback_data=f"admin_delete_{plan_id}")])
    buttons.append([InlineKeyboardButton("🔙 بازگشت به لیست", callback_data="admin_list_plans")])

    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons))


async def admin_toggle_plan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    plan_id = int(query.data.split("_")[2])
    plan = plans_service.get_plan(plan_id)
    if not plan:
        await query.edit_message_text("❌ پلن پیدا نشد.")
        return
    plans_service.toggle_plan(plan_id, not bool(plan["is_active"]))
    await _show_plan_detail(query, plan_id, update.effective_user.id)


async def admin_delete_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    plan_id = int(query.data.split("_")[2])
    plan = plans_service.get_plan(plan_id)
    if not plan:
        await query.edit_message_text("❌ پلن پیدا نشد.")
        return
    has_p = plans_service.has_purchases(plan_id)
    warning = "\n⚠️ این پلن خریدار دارد. تاریخچه خریدها حفظ می‌شود." if has_p else ""
    await query.edit_message_text(
        f"⚠️ آیا از حذف پلن #{plan_id} «{plan['title']}» مطمئنی؟{warning}",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🗑 بله، حذف شود", callback_data=f"admin_confirmdelete_{plan_id}")],
            [InlineKeyboardButton("🔙 انصراف", callback_data=f"admin_plan_{plan_id}")],
        ]),
    )


async def admin_delete_execute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    plan_id = int(query.data.split("_")[2])
    try:
        plans_service.delete_plan(plan_id)
        await query.edit_message_text(
            f"✅ پلن #{plan_id} حذف شد.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت به لیست", callback_data="admin_list_plans")]]),
        )
    except Exception as e:
        await query.edit_message_text(f"❌ خطا در حذف: {e}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data=f"admin_plan_{plan_id}")]]))


# ─── ویرایش پلن ──────────────────────────────────────────

async def admin_edit_plan_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    plan_id = int(query.data.split("_")[2])
    plan = plans_service.get_plan(plan_id)
    if not plan:
        await query.edit_message_text("❌ پلن پیدا نشد.")
        return ConversationHandler.END
    context.user_data["editing_plan_id"] = plan_id

    buttons = [
        [InlineKeyboardButton("📝 عنوان", callback_data="editfield_title")],
        [InlineKeyboardButton("⏱ مدت (روز)", callback_data="editfield_duration_days"),
         InlineKeyboardButton("💰 قیمت", callback_data="editfield_price")],
    ]
    if plan.get("plan_type") == "xui":
        buttons.append([InlineKeyboardButton("💾 حجم (GB)", callback_data="editfield_volume_gb"),
                        InlineKeyboardButton("🔌 اینباند ID", callback_data="editfield_inbound_id")])
    buttons.append([InlineKeyboardButton("🔙 انصراف", callback_data=f"admin_plan_{plan_id}")])

    await query.edit_message_text(
        f"✏️ ویرایش پلن #{plan_id}\nکدام فیلد را تغییر می‌دهید؟",
        reply_markup=InlineKeyboardMarkup(buttons),
    )
    return EDIT_FIELD


async def admin_edit_field_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    field = query.data.split("_", 1)[1]
    context.user_data["editing_field"] = field
    labels = {
        "title": "عنوان جدید",
        "duration_days": "مدت جدید (به روز)",
        "price": "قیمت جدید (به تومان)",
        "volume_gb": "حجم جدید (به گیگابایت)",
        "inbound_id": "شماره اینباند جدید",
    }
    await query.edit_message_text(f"مقدار جدید برای «{labels.get(field, field)}» را وارد کنید:")
    return EDIT_VALUE


async def admin_edit_value_save(update: Update, context: ContextTypes.DEFAULT_TYPE):
    plan_id = context.user_data.get("editing_plan_id")
    field = context.user_data.get("editing_field")
    raw = update.message.text.strip()
    try:
        if field in ("duration_days", "price", "inbound_id"):
            value = int(raw)
        elif field == "volume_gb":
            value = float(raw)
        else:
            value = raw
        assert value
    except Exception:
        await update.message.reply_text("❌ مقدار نامعتبر است. دوباره وارد کنید:")
        return EDIT_VALUE

    plans_service.update_plan(plan_id, **{field: value})
    await update.message.reply_text(
        f"✅ فیلد «{field}» با موفقیت ذخیره شد.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت به پلن", callback_data=f"admin_plan_{plan_id}")]]),
    )
    context.user_data.clear()
    return ConversationHandler.END


async def admin_edit_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("لغو شد.")
    return ConversationHandler.END


# ─── افزودن پلن XUI ──────────────────────────────────────

async def add_plan_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("عنوان پلن را وارد کنید:")
    return TITLE


async def add_plan_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["new_plan"] = {"title": update.message.text.strip(), "plan_type": "xui"}
    try:
        client = XUIClient()
        inbounds = client.list_inbounds()
    except Exception as e:
        await update.message.reply_text(f"❌ خطا در دریافت اینباندها: {e}")
        return ConversationHandler.END
    context.user_data["inbounds_cache"] = {str(ib["id"]): ib for ib in inbounds}
    lines = ["اینباند مورد نظر را با ارسال ID انتخاب کنید:\n"]
    for ib in inbounds:
        lines.append(f"🔹 ID={ib['id']} | {ib.get('remark')} | {ib.get('protocol')} | پورت {ib.get('port')}")
    await update.message.reply_text("\n".join(lines))
    return INBOUND


async def add_plan_inbound(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text not in context.user_data.get("inbounds_cache", {}):
        await update.message.reply_text("❌ ID معتبر نیست:")
        return INBOUND
    context.user_data["new_plan"]["inbound_id"] = int(text)
    await update.message.reply_text("حجم پلن را به گیگابایت وارد کنید:")
    return VOLUME


async def add_plan_volume(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        volume = float(update.message.text.strip())
        assert volume > 0
    except Exception:
        await update.message.reply_text("❌ عدد معتبر وارد کنید:")
        return VOLUME
    context.user_data["new_plan"]["volume_gb"] = volume
    await update.message.reply_text("مدت زمان پلن را به روز وارد کنید:")
    return DURATION


async def add_plan_duration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        duration = int(update.message.text.strip())
        assert duration > 0
    except Exception:
        await update.message.reply_text("❌ عدد صحیح وارد کنید:")
        return DURATION
    context.user_data["new_plan"]["duration_days"] = duration
    await update.message.reply_text("قیمت پلن را به تومان وارد کنید:")
    return PRICE


async def add_plan_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        price = int(update.message.text.strip())
        assert price > 0
    except Exception:
        await update.message.reply_text("❌ عدد صحیح وارد کنید:")
        return PRICE
    context.user_data["new_plan"]["price"] = price
    d = context.user_data["new_plan"]
    await update.message.reply_text(
        f"تایید اطلاعات پلن:\n\n"
        f"عنوان: {d['title']}\n"
        f"اینباند ID: {d['inbound_id']}\n"
        f"حجم: {d['volume_gb']} GB\n"
        f"مدت: {d['duration_days']} روز\n"
        f"قیمت: {price:,} تومان\n\n"
        "برای تایید عدد 1 و برای لغو عدد 0 بفرستید."
    )
    return CONFIRM


async def add_plan_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    d = context.user_data.get("new_plan", {})
    if update.message.text.strip() == "1":
        plan_id = plans_service.create_plan(
            title=d["title"],
            inbound_id=d.get("inbound_id"),
            volume_gb=d.get("volume_gb"),
            duration_days=d["duration_days"],
            price=d["price"],
            plan_type="xui",
        )
        await update.message.reply_text(f"✅ پلن XUI #{plan_id} ساخته شد.")
    else:
        await update.message.reply_text("❌ لغو شد.")
    context.user_data.clear()
    return ConversationHandler.END


async def add_plan_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("لغو شد.")
    return ConversationHandler.END


# ─── افزودن پلن دستی ─────────────────────────────────────

async def add_manual_plan_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("عنوان پلن دستی را وارد کنید (مثلاً: تونل Cloudflare Edge 30 روزه):")
    return MANUAL_TITLE


async def add_manual_plan_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["new_manual_plan"] = {"title": update.message.text.strip()}
    await update.message.reply_text("مدت زمان پلن را به روز وارد کنید:")
    return MANUAL_DURATION


async def add_manual_plan_duration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        duration = int(update.message.text.strip())
        assert duration > 0
    except Exception:
        await update.message.reply_text("❌ عدد صحیح وارد کنید:")
        return MANUAL_DURATION
    context.user_data["new_manual_plan"]["duration_days"] = duration
    await update.message.reply_text("قیمت پلن را به تومان وارد کنید:")
    return MANUAL_PRICE


async def add_manual_plan_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        price = int(update.message.text.strip())
        assert price > 0
    except Exception:
        await update.message.reply_text("❌ عدد صحیح وارد کنید:")
        return MANUAL_PRICE
    context.user_data["new_manual_plan"]["price"] = price
    await update.message.reply_text(
        "اکنون اولین کانفیگ را وارد کنید (لینک یا متن).\n"
        "بعد از ثبت، می‌توانید بیشتر اضافه کنید.\n"
        "برای لغو /cancel بزنید."
    )
    return MANUAL_CONFIG_TEXT


async def add_manual_plan_config(update: Update, context: ContextTypes.DEFAULT_TYPE):
    d = context.user_data["new_manual_plan"]
    plan_id = plans_service.create_plan(
        title=d["title"],
        duration_days=d["duration_days"],
        price=d["price"],
        plan_type="manual",
    )
    config_text = update.message.text.strip()
    plans_service.add_manual_config(plan_id, config_text)
    context.user_data.clear()
    await update.message.reply_text(
        f"✅ پلن دستی #{plan_id} با یک کانفیگ ساخته شد.\n"
        "برای افزودن کانفیگ بیشتر به مدیریت پلن برو.",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("📋 مدیریت پلن‌ها", callback_data="admin_list_plans")
        ]]),
    )
    return ConversationHandler.END


# ─── مدیریت کانفیگ‌های دستی ──────────────────────────────

async def admin_add_config_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    plan_id = int(query.data.split("_")[2])
    context.user_data["adding_config_plan_id"] = plan_id
    await query.edit_message_text(
        "کانفیگ جدید را وارد کنید (لینک یا متن):\n\n"
        "هر پیام = یک کانفیگ. بعد از ارسال هر کانفیگ می‌توانید ادامه دهید.\n"
        "برای پایان /cancel بزنید."
    )
    return ADD_CONFIG_TO_PLAN


async def admin_add_config_save(update: Update, context: ContextTypes.DEFAULT_TYPE):
    plan_id = context.user_data.get("adding_config_plan_id")
    if not plan_id:
        return ConversationHandler.END
    plans_service.add_manual_config(plan_id, update.message.text.strip())
    count = plans_service.get_available_config_count(plan_id)
    await update.message.reply_text(
        f"✅ کانفیگ اضافه شد. موجودی فعلی: {count} عدد\n\n"
        "کانفیگ بعدی را بفرستید یا /cancel بزنید."
    )
    return ADD_CONFIG_TO_PLAN


async def admin_list_configs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    plan_id = int(query.data.split("_")[2])
    configs = plans_service.list_manual_configs(plan_id)
    if not configs:
        await query.edit_message_text(
            "هیچ کانفیگی ثبت نشده.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data=f"admin_plan_{plan_id}")]]),
        )
        return
    buttons = []
    for c in configs[:15]:
        status = "✅ آزاد" if not c["is_used"] else f"✔ استفاده شده"
        preview = c["config_text"][:30] + "..." if len(c["config_text"]) > 30 else c["config_text"]
        label = f"#{c['id']} {status} | {preview}"
        buttons.append([InlineKeyboardButton(label, callback_data=f"admin_delconfig_{c['id']}_{plan_id}")])
    buttons.append([InlineKeyboardButton("🔙 بازگشت", callback_data=f"admin_plan_{plan_id}")])
    await query.edit_message_text(
        f"📋 کانفیگ‌های پلن #{plan_id}:\n(روی کانفیگ آزاد بزنید برای حذف)",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def admin_delete_config(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    parts = query.data.split("_")
    config_id = int(parts[2])
    plan_id = int(parts[3])
    plans_service.delete_manual_config(config_id)
    await query.answer("✅ کانفیگ حذف شد.", show_alert=True)
    # بازنمایی لیست
    configs = plans_service.list_manual_configs(plan_id)
    buttons = []
    for c in configs[:15]:
        status = "✅ آزاد" if not c["is_used"] else "✔ استفاده شده"
        preview = c["config_text"][:30] + "..."
        buttons.append([InlineKeyboardButton(f"#{c['id']} {status} | {preview}", callback_data=f"admin_delconfig_{c['id']}_{plan_id}")])
    buttons.append([InlineKeyboardButton("🔙 بازگشت", callback_data=f"admin_plan_{plan_id}")])
    await query.edit_message_text(
        f"📋 کانفیگ‌های پلن #{plan_id}:",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


# ─── تنظیمات پرداخت ──────────────────────────────────────

async def admin_payment_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    card = plans_service.get_setting("payment_card", "تنظیم نشده")
    desc = plans_service.get_setting("payment_desc", "تنظیم نشده")
    await query.edit_message_text(
        f"💳 تنظیمات پرداخت:\n\nشماره کارت: {card}\nتوضیحات: {desc}",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✏️ تغییر شماره کارت", callback_data="admin_set_card")],
            [InlineKeyboardButton("✏️ تغییر توضیحات پرداخت", callback_data="admin_set_paymentdesc")],
            [InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back")],
        ]),
    )


async def admin_set_card_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("شماره کارت جدید را وارد کنید:")
    return SET_CARD


async def admin_set_card_save(update: Update, context: ContextTypes.DEFAULT_TYPE):
    plans_service.set_setting("payment_card", update.message.text.strip())
    await update.message.reply_text("✅ شماره کارت ذخیره شد.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت به تنظیمات", callback_data="admin_payment_settings")]]))
    return ConversationHandler.END


async def admin_set_paymentdesc_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("توضیحات پرداخت را وارد کنید:")
    return SET_PAYMENT_DESC


async def admin_set_paymentdesc_save(update: Update, context: ContextTypes.DEFAULT_TYPE):
    plans_service.set_setting("payment_desc", update.message.text.strip())
    await update.message.reply_text("✅ توضیحات ذخیره شد.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت به تنظیمات", callback_data="admin_payment_settings")]]))
    return ConversationHandler.END


async def settings_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("لغو شد.")
    return ConversationHandler.END


# ─── تنظیمات عمومی ───────────────────────────────────────

async def admin_general_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    support = plans_service.get_setting("support_id", "تنظیم نشده")
    await query.edit_message_text(
        f"⚙️ تنظیمات عمومی:\n\nپشتیبانی: {support}",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✏️ تنظیم پشتیبانی", callback_data="admin_set_support")],
            [InlineKeyboardButton("✏️ پیام خوش‌آمدگویی", callback_data="admin_set_welcome")],
            [InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back")],
        ]),
    )


async def admin_set_support_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("یوزرنیم یا لینک پشتیبانی را وارد کنید (مثلاً @support_user):")
    return SET_SUPPORT_ID


async def admin_set_support_save(update: Update, context: ContextTypes.DEFAULT_TYPE):
    plans_service.set_setting("support_id", update.message.text.strip())
    await update.message.reply_text("✅ پشتیبانی ذخیره شد.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="admin_general_settings")]]))
    return ConversationHandler.END


async def admin_set_welcome_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "پیام خوش‌آمدگویی را وارد کنید.\n{name} جای نام کاربر را می‌گیرد:"
    )
    return SET_WELCOME


async def admin_set_welcome_save(update: Update, context: ContextTypes.DEFAULT_TYPE):
    plans_service.set_setting("welcome_message", update.message.text.strip())
    await update.message.reply_text("✅ پیام خوش‌آمدگویی ذخیره شد.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="admin_general_settings")]]))
    return ConversationHandler.END


# ─── مدیریت ادمین‌ها ──────────────────────────────────────

async def admin_manage_admins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not admin_service.has_permission(update.effective_user.id, "all"):
        await query.answer("⛔ فقط super_admin.", show_alert=True)
        return

    admins = admin_service.list_admins()
    lines = ["🔑 لیست ادمین‌ها:\n"]
    for a in admins:
        role_label = admin_service.ROLE_LABELS.get(a["role"], a["role"])
        uname = f"@{a['username']}" if a.get("username") else f"#{a['telegram_id']}"
        lines.append(f"{role_label} — {uname} (ID: {a['telegram_id']})")

    await query.edit_message_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ افزودن ادمین", callback_data="admin_add_admin")],
            [InlineKeyboardButton("➖ حذف ادمین", callback_data="admin_remove_admin")],
            [InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back")],
        ]),
    )


async def admin_add_admin_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "آیدی عددی تلگرام ادمین جدید را وارد کنید:\n"
        "(کاربر باید یک‌بار /start زده باشد)"
    )
    return ADD_ADMIN_ID


async def admin_add_admin_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        uid = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("❌ آیدی عددی وارد کنید:")
        return ADD_ADMIN_ID

    context.user_data["new_admin_id"] = uid
    await update.message.reply_text(
        "نقش را انتخاب کنید:",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🎧 پشتیبانی", callback_data="newrole_support")],
            [InlineKeyboardButton("🔧 ادمین", callback_data="newrole_admin")],
            [InlineKeyboardButton("👑 سوپر ادمین", callback_data="newrole_super_admin")],
        ]),
    )
    return ADD_ADMIN_ROLE


async def admin_add_admin_role(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    role = query.data.split("_", 1)[1]
    new_id = context.user_data.get("new_admin_id")
    adder = update.effective_user

    import database as db
    with db.db_cursor() as cur:
        cur.execute("SELECT username, full_name FROM users WHERE telegram_id=?", (new_id,))
        row = cur.fetchone()
    uname = row["username"] if row else ""
    fname = row["full_name"] if row else ""

    success = admin_service.add_admin(new_id, uname, fname, role, adder.id)
    if success:
        await query.edit_message_text(
            f"✅ ادمین جدید با نقش {admin_service.ROLE_LABELS[role]} اضافه شد.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="admin_manage_admins")]]),
        )
    else:
        await query.edit_message_text(
            "❌ خطا: شما اجازه اضافه کردن این نقش را ندارید.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="admin_manage_admins")]]),
        )
    context.user_data.clear()
    return ConversationHandler.END


async def admin_remove_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    admins = admin_service.list_admins()
    buttons = []
    for a in admins:
        if a["telegram_id"] in __import__("config").SUPER_ADMIN_IDS:
            continue  # config super_adminها قابل حذف نیستند
        role_label = admin_service.ROLE_LABELS.get(a["role"], a["role"])
        uname = f"@{a['username']}" if a.get("username") else str(a["telegram_id"])
        buttons.append([InlineKeyboardButton(f"🗑 {role_label} — {uname}", callback_data=f"admin_doremove_{a['telegram_id']}")])
    buttons.append([InlineKeyboardButton("🔙 بازگشت", callback_data="admin_manage_admins")])
    await query.edit_message_text("کدام ادمین را حذف کنم?", reply_markup=InlineKeyboardMarkup(buttons))


async def admin_do_remove_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    target_id = int(query.data.split("_")[2])
    success = admin_service.remove_admin(target_id, update.effective_user.id)
    msg = "✅ ادمین حذف شد." if success else "❌ امکان حذف وجود ندارد."
    await query.edit_message_text(msg,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="admin_manage_admins")]]))


# ─── پیام همگانی ──────────────────────────────────────────

async def admin_broadcast_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not admin_service.has_permission(update.effective_user.id, "broadcast"):
        await query.answer("⛔ دسترسی ندارید.", show_alert=True)
        return
    await query.edit_message_text(
        "📢 پیام همگانی:\n\nمتن پیامی که می‌خواهید برای همه کاربران ارسال شود را بنویسید:\n"
        "(برای لغو /cancel بزنید)"
    )
    return BROADCAST_MSG


async def admin_broadcast_send(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg_text = update.message.text.strip()
    if not msg_text:
        await update.message.reply_text("❌ متن پیام خالی است:")
        return BROADCAST_MSG

    await update.message.reply_text("⏳ در حال ارسال پیام همگانی...")

    import database as db
    with db.db_cursor() as cur:
        cur.execute("SELECT telegram_id FROM users WHERE is_banned=0")
        users = [row["telegram_id"] for row in cur.fetchall()]

    sent, failed = 0, 0
    for uid in users:
        try:
            await update.get_bot().send_message(chat_id=uid, text=msg_text)
            sent += 1
        except Exception:
            failed += 1

    with db.db_cursor() as cur:
        cur.execute(
            "INSERT INTO broadcast_log (admin_id, message, sent_count, failed_count) VALUES (?,?,?,?)",
            (update.effective_user.id, msg_text, sent, failed),
        )

    await update.message.reply_text(
        f"✅ ارسال پایان یافت.\n\nموفق: {sent}\nناموفق: {failed}",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back")]]),
    )
    return ConversationHandler.END


async def broadcast_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("لغو شد.")
    return ConversationHandler.END


# ─── مشاهده کاربران ──────────────────────────────────────

async def admin_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not admin_service.has_permission(update.effective_user.id, "view_users"):
        await query.answer("⛔ دسترسی ندارید.", show_alert=True)
        return

    import database as db
    with db.db_cursor() as cur:
        cur.execute("SELECT * FROM users ORDER BY joined_at DESC LIMIT 20")
        users = [dict(row) for row in cur.fetchall()]

    if not users:
        await query.edit_message_text("هیچ کاربری ثبت نشده.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back")]]))
        return

    lines = ["👥 ۲۰ کاربر اخیر:\n"]
    for u in users:
        banned = " ⛔" if u["is_banned"] else ""
        uname = f"@{u['username']}" if u.get("username") else "-"
        lines.append(f"• {u['full_name']} ({uname}) — {u['telegram_id']}{banned}")

    buttons = [[InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back")]]
    await query.edit_message_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(buttons))


# ─── سفارش‌های در انتظار ──────────────────────────────────

async def admin_pending_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not admin_service.has_permission(update.effective_user.id, "approve_orders"):
        await query.answer("⛔ دسترسی ندارید.", show_alert=True)
        return

    import database as db
    with db.db_cursor() as cur:
        cur.execute("""
            SELECT o.id, o.telegram_id, o.created_at, p.title, p.price
            FROM orders o JOIN plans p ON o.plan_id=p.id
            WHERE o.status='pending'
            ORDER BY o.created_at ASC
        """)
        orders = [dict(row) for row in cur.fetchall()]

    if not orders:
        await query.edit_message_text("هیچ سفارش در انتظاری وجود ندارد.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back")]]))
        return

    lines = [f"📦 {len(orders)} سفارش در انتظار:\n"]
    for o in orders:
        lines.append(f"#{o['id']} — {o['title']} — {o['price']:,}ت — کاربر {o['telegram_id']}")

    await query.edit_message_text("\n".join(lines),
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back")]]))


# ─── register handlers ────────────────────────────────────

def get_admin_handlers():
    add_plan_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(add_plan_start, pattern="^admin_add_plan$")],
        states={
            TITLE:    [MessageHandler(filters.TEXT & ~filters.COMMAND, add_plan_title)],
            INBOUND:  [MessageHandler(filters.TEXT & ~filters.COMMAND, add_plan_inbound)],
            VOLUME:   [MessageHandler(filters.TEXT & ~filters.COMMAND, add_plan_volume)],
            DURATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_plan_duration)],
            PRICE:    [MessageHandler(filters.TEXT & ~filters.COMMAND, add_plan_price)],
            CONFIRM:  [MessageHandler(filters.TEXT & ~filters.COMMAND, add_plan_confirm)],
        },
        fallbacks=[CommandHandler("cancel", add_plan_cancel)],
    )

    add_manual_plan_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(add_manual_plan_start, pattern="^admin_add_manual_plan$")],
        states={
            MANUAL_TITLE:       [MessageHandler(filters.TEXT & ~filters.COMMAND, add_manual_plan_title)],
            MANUAL_DURATION:    [MessageHandler(filters.TEXT & ~filters.COMMAND, add_manual_plan_duration)],
            MANUAL_PRICE:       [MessageHandler(filters.TEXT & ~filters.COMMAND, add_manual_plan_price)],
            MANUAL_CONFIG_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_manual_plan_config)],
        },
        fallbacks=[CommandHandler("cancel", add_plan_cancel)],
    )

    edit_plan_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_edit_plan_start, pattern="^admin_edit_\\d+$")],
        states={
            EDIT_FIELD: [CallbackQueryHandler(admin_edit_field_select, pattern="^editfield_")],
            EDIT_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_edit_value_save)],
        },
        fallbacks=[CommandHandler("cancel", admin_edit_cancel)],
    )

    payment_settings_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(admin_set_card_start, pattern="^admin_set_card$"),
            CallbackQueryHandler(admin_set_paymentdesc_start, pattern="^admin_set_paymentdesc$"),
        ],
        states={
            SET_CARD:         [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_set_card_save)],
            SET_PAYMENT_DESC: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_set_paymentdesc_save)],
        },
        fallbacks=[CommandHandler("cancel", settings_cancel)],
    )

    general_settings_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(admin_set_support_start, pattern="^admin_set_support$"),
            CallbackQueryHandler(admin_set_welcome_start, pattern="^admin_set_welcome$"),
        ],
        states={
            SET_SUPPORT_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_set_support_save)],
            SET_WELCOME:    [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_set_welcome_save)],
        },
        fallbacks=[CommandHandler("cancel", settings_cancel)],
    )

    add_admin_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_add_admin_start, pattern="^admin_add_admin$")],
        states={
            ADD_ADMIN_ID:   [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_add_admin_id)],
            ADD_ADMIN_ROLE: [CallbackQueryHandler(admin_add_admin_role, pattern="^newrole_")],
        },
        fallbacks=[CommandHandler("cancel", settings_cancel)],
    )

    broadcast_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_broadcast_start, pattern="^admin_broadcast$")],
        states={
            BROADCAST_MSG: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_broadcast_send)],
        },
        fallbacks=[CommandHandler("cancel", broadcast_cancel)],
    )

    add_config_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_add_config_start, pattern="^admin_addconfig_\\d+$")],
        states={
            ADD_CONFIG_TO_PLAN: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_add_config_save)],
        },
        fallbacks=[CommandHandler("cancel", settings_cancel)],
    )

    return [
        CommandHandler("admin", admin_command),
        add_plan_conv,
        add_manual_plan_conv,
        edit_plan_conv,
        payment_settings_conv,
        general_settings_conv,
        add_admin_conv,
        broadcast_conv,
        add_config_conv,
        CallbackQueryHandler(admin_list_plans,        pattern="^admin_list_plans$"),
        CallbackQueryHandler(admin_plan_detail,       pattern="^admin_plan_\\d+$"),
        CallbackQueryHandler(admin_toggle_plan,       pattern="^admin_toggle_\\d+$"),
        CallbackQueryHandler(admin_delete_confirm,    pattern="^admin_delete_\\d+$"),
        CallbackQueryHandler(admin_delete_execute,    pattern="^admin_confirmdelete_\\d+$"),
        CallbackQueryHandler(admin_payment_settings,  pattern="^admin_payment_settings$"),
        CallbackQueryHandler(admin_general_settings,  pattern="^admin_general_settings$"),
        CallbackQueryHandler(admin_stats,             pattern="^admin_stats$"),
        CallbackQueryHandler(admin_users,             pattern="^admin_users$"),
        CallbackQueryHandler(admin_pending_orders,    pattern="^admin_pending_orders$"),
        CallbackQueryHandler(admin_manage_admins,     pattern="^admin_manage_admins$"),
        CallbackQueryHandler(admin_remove_admin,      pattern="^admin_remove_admin$"),
        CallbackQueryHandler(admin_do_remove_admin,   pattern="^admin_doremove_\\d+$"),
        CallbackQueryHandler(admin_list_configs,      pattern="^admin_listconfigs_\\d+$"),
        CallbackQueryHandler(admin_delete_config,     pattern="^admin_delconfig_\\d+_\\d+$"),
        CallbackQueryHandler(admin_back,              pattern="^admin_back$"),
    ]
