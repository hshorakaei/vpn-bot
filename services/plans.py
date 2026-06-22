"""
services/plans.py
عملیات دیتابیسی مربوط به پلن‌های فروش.
"""

import database


def create_plan(title: str, inbound_id: int, volume_gb: float,
                 duration_days: int, price: int) -> int:
    """ساخت یک پلن جدید و برگرداندن id آن."""
    with database.db_cursor() as cur:
        cur.execute(
            """
            INSERT INTO plans (title, inbound_id, volume_gb, duration_days, price)
            VALUES (?, ?, ?, ?, ?)
            """,
            (title, inbound_id, volume_gb, duration_days, price),
        )
        return cur.lastrowid


def list_active_plans() -> list:
    """لیست پلن‌های فعال، برای نمایش به کاربر در بخش خرید."""
    with database.db_cursor() as cur:
        cur.execute("SELECT * FROM plans WHERE is_active = 1 ORDER BY price ASC")
        return [dict(row) for row in cur.fetchall()]


def list_all_plans() -> list:
    """لیست همه پلن‌ها (فعال و غیرفعال)، برای پنل مدیریت."""
    with database.db_cursor() as cur:
        cur.execute("SELECT * FROM plans ORDER BY id DESC")
        return [dict(row) for row in cur.fetchall()]


def get_plan(plan_id: int) -> dict | None:
    with database.db_cursor() as cur:
        cur.execute("SELECT * FROM plans WHERE id = ?", (plan_id,))
        row = cur.fetchone()
        return dict(row) if row else None


def delete_plan(plan_id: int) -> None:
    with database.db_cursor() as cur:
        cur.execute("DELETE FROM plans WHERE id = ?", (plan_id,))


def toggle_plan(plan_id: int, is_active: bool) -> None:
    with database.db_cursor() as cur:
        cur.execute(
            "UPDATE plans SET is_active = ? WHERE id = ?",
            (1 if is_active else 0, plan_id),
        )
