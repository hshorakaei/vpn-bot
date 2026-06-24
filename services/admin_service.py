"""
services/admin_service.py
مدیریت ادمین‌ها با سیستم نقش‌بندی سه‌سطحی.
نقش‌ها: super_admin > admin > support
"""

import database
import config

ROLES = ["support", "admin", "super_admin"]
ROLE_LABELS = {
    "super_admin": "👑 سوپر ادمین",
    "admin":       "🔧 ادمین",
    "support":     "🎧 پشتیبانی",
}

# دسترسی‌ها
PERMISSIONS = {
    "super_admin": {"all"},
    "admin":       {"manage_plans", "approve_orders", "view_users", "broadcast", "view_stats", "manage_configs"},
    "support":     {"approve_orders", "view_users"},
}


def get_admin(telegram_id: int) -> dict | None:
    with database.db_cursor() as cur:
        cur.execute("SELECT * FROM admins WHERE telegram_id = ?", (telegram_id,))
        row = cur.fetchone()
        return dict(row) if row else None


def is_admin(telegram_id: int) -> bool:
    # super_admin های config همیشه ادمین هستند
    if telegram_id in config.SUPER_ADMIN_IDS:
        return True
    return get_admin(telegram_id) is not None


def get_role(telegram_id: int) -> str | None:
    if telegram_id in config.SUPER_ADMIN_IDS:
        return "super_admin"
    admin = get_admin(telegram_id)
    return admin["role"] if admin else None


def has_permission(telegram_id: int, perm: str) -> bool:
    role = get_role(telegram_id)
    if not role:
        return False
    perms = PERMISSIONS.get(role, set())
    return "all" in perms or perm in perms


def add_admin(telegram_id: int, username: str, full_name: str, role: str, added_by: int) -> bool:
    """افزودن ادمین جدید. فقط super_admin می‌تواند super_admin اضافه کند."""
    adder_role = get_role(added_by)
    if adder_role == "admin" and role == "super_admin":
        return False
    with database.db_cursor() as cur:
        cur.execute(
            "INSERT OR REPLACE INTO admins (telegram_id, username, full_name, role, added_by) VALUES (?,?,?,?,?)",
            (telegram_id, username, full_name, role, added_by),
        )
    return True


def remove_admin(telegram_id: int, removed_by: int) -> bool:
    """حذف ادمین. super_admin های config قابل حذف نیستند."""
    if telegram_id in config.SUPER_ADMIN_IDS:
        return False
    target = get_admin(telegram_id)
    if not target:
        return False
    remover_role = get_role(removed_by)
    # ادمین معمولی نمی‌تواند super_admin حذف کند
    if target["role"] == "super_admin" and remover_role != "super_admin":
        return False
    with database.db_cursor() as cur:
        cur.execute("DELETE FROM admins WHERE telegram_id = ?", (telegram_id,))
    return True


def list_admins() -> list:
    with database.db_cursor() as cur:
        cur.execute("SELECT * FROM admins ORDER BY CASE role WHEN 'super_admin' THEN 0 WHEN 'admin' THEN 1 ELSE 2 END, added_at")
        return [dict(row) for row in cur.fetchall()]
