"""
services/plans.py
عملیات دیتابیسی مربوط به پلن‌های فروش.
دو نوع پلن پشتیبانی می‌شود:
  - xui: اتصال خودکار به پنل 3X-UI
  - manual: کانفیگ متنی که ادمین وارد می‌کند
"""

import database


# ─── پلن‌ها ────────────────────────────────────────────────

def create_plan(title, duration_days, price,
                plan_type="xui", inbound_id=None, volume_gb=None, limit_ip=0):
    with database.db_cursor() as cur:
        cur.execute(
            """INSERT INTO plans
               (title, plan_type, inbound_id, volume_gb, duration_days, price, limit_ip)
               VALUES (?,?,?,?,?,?,?)""",
            (title, plan_type, inbound_id, volume_gb, duration_days, price, limit_ip),
        )
        return cur.lastrowid


def update_plan(plan_id, **fields):
    allowed = {"title", "inbound_id", "volume_gb", "duration_days", "price", "is_active", "plan_type"}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return
    set_clause = ", ".join(f"{k}=?" for k in updates)
    values = list(updates.values()) + [plan_id]
    with database.db_cursor() as cur:
        cur.execute(f"UPDATE plans SET {set_clause} WHERE id=?", values)


def list_active_plans():
    with database.db_cursor() as cur:
        cur.execute("SELECT * FROM plans WHERE is_active=1 ORDER BY price ASC")
        return [dict(row) for row in cur.fetchall()]


def list_all_plans():
    with database.db_cursor() as cur:
        cur.execute("SELECT * FROM plans ORDER BY id DESC")
        return [dict(row) for row in cur.fetchall()]


def get_plan(plan_id):
    with database.db_cursor() as cur:
        cur.execute("SELECT * FROM plans WHERE id=?", (plan_id,))
        row = cur.fetchone()
        return dict(row) if row else None


def has_purchases(plan_id):
    with database.db_cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM purchases WHERE plan_id=?", (plan_id,))
        return cur.fetchone()[0] > 0


def delete_plan(plan_id):
    """
    حذف پلن حتی در صورت وجود خریداران.
    سفارش‌های pending و کانفیگ‌های استفاده‌نشده حذف می‌شوند.
    خریدهای قبلی حفظ می‌شوند (plan_id به NULL تبدیل می‌شود).
    """
    with database.db_cursor() as cur:
        cur.execute("DELETE FROM orders WHERE plan_id=? AND status='pending'", (plan_id,))
        cur.execute("DELETE FROM manual_configs WHERE plan_id=? AND is_used=0", (plan_id,))
        # حفظ تاریخچه خریدها با NULL کردن plan_id
        cur.execute("UPDATE purchases SET plan_id=NULL WHERE plan_id=?", (plan_id,))
        cur.execute("DELETE FROM plans WHERE id=?", (plan_id,))


def toggle_plan(plan_id, is_active):
    with database.db_cursor() as cur:
        cur.execute("UPDATE plans SET is_active=? WHERE id=?", (1 if is_active else 0, plan_id))


# ─── کانفیگ‌های دستی ─────────────────────────────────────

def add_manual_config(plan_id, config_text, label=None):
    with database.db_cursor() as cur:
        cur.execute(
            "INSERT INTO manual_configs (plan_id, config_text, label) VALUES (?,?,?)",
            (plan_id, config_text.strip(), label),
        )
        return cur.lastrowid


def get_available_config_count(plan_id):
    with database.db_cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM manual_configs WHERE plan_id=? AND is_used=0",
            (plan_id,),
        )
        return cur.fetchone()[0]


def pop_manual_config(plan_id, telegram_id):
    """گرفتن یک کانفیگ آزاد و اختصاص به کاربر."""
    with database.db_cursor() as cur:
        cur.execute(
            "SELECT id, config_text, label FROM manual_configs WHERE plan_id=? AND is_used=0 LIMIT 1",
            (plan_id,),
        )
        row = cur.fetchone()
        if not row:
            return None
        cur.execute(
            "UPDATE manual_configs SET is_used=1, assigned_to=?, used_at=CURRENT_TIMESTAMP WHERE id=?",
            (telegram_id, row["id"]),
        )
        return dict(row)


def list_manual_configs(plan_id):
    with database.db_cursor() as cur:
        cur.execute("SELECT * FROM manual_configs WHERE plan_id=? ORDER BY id DESC", (plan_id,))
        return [dict(row) for row in cur.fetchall()]


def delete_manual_config(config_id):
    with database.db_cursor() as cur:
        cur.execute("DELETE FROM manual_configs WHERE id=? AND is_used=0", (config_id,))


# ─── تنظیمات ─────────────────────────────────────────────

def get_setting(key, default=""):
    with database.db_cursor() as cur:
        cur.execute("SELECT value FROM settings WHERE key=?", (key,))
        row = cur.fetchone()
        return row[0] if row else default


def set_setting(key, value):
    with database.db_cursor() as cur:
        cur.execute(
            "INSERT INTO settings (key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )


# ─── آمار ────────────────────────────────────────────────

def get_stats():
    with database.db_cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM users")
        total_users = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM orders WHERE status='approved'")
        total_orders = cur.fetchone()[0]

        cur.execute("""
            SELECT COALESCE(SUM(p.price), 0)
            FROM orders o JOIN plans p ON o.plan_id=p.id
            WHERE o.status='approved'
        """)
        total_revenue = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM orders WHERE status='pending'")
        pending_orders = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM users WHERE joined_at >= date('now', '-7 days')")
        new_users_week = cur.fetchone()[0]

        return {
            "total_users": total_users,
            "total_orders": total_orders,
            "total_revenue": total_revenue,
            "pending_orders": pending_orders,
            "new_users_week": new_users_week,
        }
