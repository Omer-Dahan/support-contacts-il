import logging
import os
from datetime import datetime
from typing import Any, Optional

import aiosqlite

logger = logging.getLogger(__name__)


async def init_users_db(db_path: str) -> None:
    """אתחול מסד נתוני המשתמשים והאירועים (users.db)."""
    if not db_path:
        return

    dir_name = os.path.dirname(db_path)
    if dir_name:
        os.makedirs(dir_name, exist_ok=True)

    async with aiosqlite.connect(db_path) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                chat_id INTEGER PRIMARY KEY,
                first_name TEXT,
                username TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                last_seen TEXT DEFAULT (datetime('now'))
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER,
                event_type TEXT NOT NULL,
                query TEXT,
                detail TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type)"
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_events_created ON events(created_at)"
        )
        await db.commit()


async def ensure_user(
    chat_id: int,
    first_name: str = "",
    username: str = "",
    db_path: str = "",
) -> None:
    """מוודא רישום משתמש ומעדכן את שדה last_seen ושמות המשתמש."""
    if not db_path:
        return
    try:
        async with aiosqlite.connect(db_path) as db:
            await db.execute("""
                INSERT INTO users (chat_id, first_name, username, created_at, last_seen)
                VALUES (?, ?, ?, datetime('now'), datetime('now'))
                ON CONFLICT(chat_id) DO UPDATE SET
                    last_seen = datetime('now'),
                    first_name = CASE WHEN excluded.first_name != '' THEN excluded.first_name ELSE users.first_name END,
                    username = CASE WHEN excluded.username != '' THEN excluded.username ELSE users.username END
            """, (chat_id, first_name, username))
            await db.commit()
    except Exception:
        logger.exception("Failed to ensure user in db for chat_id=%s", chat_id)


async def update_last_seen(chat_id: int, db_path: str = "") -> None:
    """עדכון מועד פעילות אחרון (last_seen) של משתמש קיים."""
    if not db_path:
        return
    try:
        async with aiosqlite.connect(db_path) as db:
            await db.execute(
                "UPDATE users SET last_seen = datetime('now') WHERE chat_id = ?",
                (chat_id,),
            )
            await db.commit()
    except Exception:
        logger.exception("Failed to update last_seen for chat_id=%s", chat_id)


async def record_event(
    chat_id: int,
    event_type: str,
    query: Optional[str] = None,
    detail: Optional[str] = None,
    db_path: str = "",
) -> None:
    """רישום אירוע פעילות בטבלת events."""
    if not db_path:
        return
    try:
        async with aiosqlite.connect(db_path) as db:
            await db.execute("""
                INSERT INTO events (chat_id, event_type, query, detail, created_at)
                VALUES (?, ?, ?, ?, datetime('now'))
            """, (chat_id, event_type, query, detail))
            await db.commit()
    except Exception:
        logger.exception("Failed to record event %s for chat_id=%s", event_type, chat_id)


async def get_admin_stats(db_path: str) -> dict[str, Any]:
    """שליפת נתוני סטטיסטיקה מקיפים עבור לוח הניהול."""
    stats: dict[str, Any] = {
        "total_users": 0,
        "active_users_7d": 0,
        "new_users_today": 0,
        "new_users_week": 0,
        "total_searches": 0,
        "today_searches": 0,
        "week_searches": 0,
        "top_companies": [],
        "top_queries": [],
        "total_exports": 0,
        "exports_by_type": {},
        "updated_at": datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
    }
    if not db_path or not os.path.exists(db_path):
        return stats

    try:
        async with aiosqlite.connect(db_path) as db:
            # Users
            async with db.execute("SELECT COUNT(*) FROM users") as cur:
                row = await cur.fetchone()
                stats["total_users"] = row[0] if row else 0

            async with db.execute(
                "SELECT COUNT(*) FROM users WHERE last_seen >= datetime('now', '-7 days')"
            ) as cur:
                row = await cur.fetchone()
                stats["active_users_7d"] = row[0] if row else 0

            async with db.execute(
                "SELECT COUNT(*) FROM users WHERE date(created_at, 'localtime') = date('now', 'localtime')"
            ) as cur:
                row = await cur.fetchone()
                stats["new_users_today"] = row[0] if row else 0

            async with db.execute(
                "SELECT COUNT(*) FROM users WHERE created_at >= datetime('now', '-7 days')"
            ) as cur:
                row = await cur.fetchone()
                stats["new_users_week"] = row[0] if row else 0

            # Searches
            async with db.execute(
                "SELECT COUNT(*) FROM events WHERE event_type = 'search'"
            ) as cur:
                row = await cur.fetchone()
                stats["total_searches"] = row[0] if row else 0

            async with db.execute(
                "SELECT COUNT(*) FROM events WHERE event_type = 'search' AND date(created_at, 'localtime') = date('now', 'localtime')"
            ) as cur:
                row = await cur.fetchone()
                stats["today_searches"] = row[0] if row else 0

            async with db.execute(
                "SELECT COUNT(*) FROM events WHERE event_type = 'search' AND created_at >= datetime('now', '-7 days')"
            ) as cur:
                row = await cur.fetchone()
                stats["week_searches"] = row[0] if row else 0

            # Top 10 viewed companies
            async with db.execute("""
                SELECT detail, COUNT(*) AS cnt
                FROM events
                WHERE event_type = 'company_view' AND detail IS NOT NULL AND detail != ''
                GROUP BY detail
                ORDER BY cnt DESC
                LIMIT 10
            """) as cur:
                stats["top_companies"] = await cur.fetchall()

            # Top 10 searches
            async with db.execute("""
                SELECT query, COUNT(*) AS cnt
                FROM events
                WHERE event_type = 'search' AND query IS NOT NULL AND query != ''
                GROUP BY query
                ORDER BY cnt DESC
                LIMIT 10
            """) as cur:
                stats["top_queries"] = await cur.fetchall()

            # Exports
            async with db.execute(
                "SELECT COUNT(*) FROM events WHERE event_type = 'export'"
            ) as cur:
                row = await cur.fetchone()
                stats["total_exports"] = row[0] if row else 0

            async with db.execute("""
                SELECT detail, COUNT(*) AS cnt
                FROM events
                WHERE event_type = 'export'
                GROUP BY detail
                ORDER BY cnt DESC
            """) as cur:
                rows = await cur.fetchall()
                stats["exports_by_type"] = {r[0] or "unknown": r[1] for r in rows}

    except Exception:
        logger.exception("Failed to get admin stats from users db: %s", db_path)

    return stats
