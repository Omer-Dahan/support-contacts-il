import html
import logging

from telethon import TelegramClient, events
from telethon.tl.custom import Button

from bot.config import is_admin, settings
from bot.users_db import get_admin_stats

logger = logging.getLogger(__name__)


def admin_keyboard() -> list[list[Button]]:
    """כפתורי לוח הבקרה למנהל."""
    return [
        [
            Button.inline("🔄 רענן", data=b"adm:refresh"),
            Button.url("📢 ערוץ הבוטים שלנו", "https://t.me/YD_IL_BOTS"),
        ]
    ]


async def build_admin_report() -> str:
    """בניית דו\"ח סטטיסטיקות שימוש עבור המנהל."""
    stats = await get_admin_stats(settings.users_db_path)

    total_users = stats.get("total_users", 0)
    active_7d = stats.get("active_users_7d", 0)
    new_today = stats.get("new_users_today", 0)
    new_week = stats.get("new_users_week", 0)

    total_searches = stats.get("total_searches", 0)
    today_searches = stats.get("today_searches", 0)
    week_searches = stats.get("week_searches", 0)

    top_comp = stats.get("top_companies", [])
    if top_comp:
        comp_lines = [
            f"  {i}. <b>{html.escape(str(name))}</b> ({cnt:,})"
            for i, (name, cnt) in enumerate(top_comp, 1)
        ]
        comp_text = "\n".join(comp_lines)
    else:
        comp_text = "  <i>אין נתונים עדיין</i>"

    top_queries = stats.get("top_queries", [])
    if top_queries:
        query_lines = [
            f"  {i}. <i>{html.escape(str(q))}</i> ({cnt:,})"
            for i, (q, cnt) in enumerate(top_queries, 1)
        ]
        queries_text = "\n".join(query_lines)
    else:
        queries_text = "  <i>אין נתונים עדיין</i>"

    total_exports = stats.get("total_exports", 0)
    exp_by_type = stats.get("exports_by_type", {})
    if exp_by_type:
        exp_labels = {
            "all": "📦 כל המאגר",
            "category": "📂 לפי קטגוריה",
            "one": "🏢 חברה בודדת",
            "query": "🔍 לפי חיפוש",
        }
        exp_lines = [
            f"  • {exp_labels.get(k, html.escape(str(k)))}: <b>{v:,}</b>"
            for k, v in exp_by_type.items()
        ]
        exp_text = "\n".join(exp_lines)
    else:
        exp_text = "  <i>אין נתונים עדיין</i>"

    updated_at = stats.get("updated_at", "")

    return (
        "📊 <b>לוח בקרה וניהול - Support Contacts IL</b>\n"
        "──────────────────\n\n"
        "👥 <b>משתמשים:</b>\n"
        f"• סה\"כ משתמשים: <b>{total_users:,}</b>\n"
        f"• פעילים ב-7 ימים: <b>{active_7d:,}</b>\n"
        f"• חדשים היום: <b>{new_today:,}</b>\n"
        f"• חדשים השבוע: <b>{new_week:,}</b>\n\n"
        "🔍 <b>חיפושים:</b>\n"
        f"• סה\"כ חיפושים: <b>{total_searches:,}</b>\n"
        f"• חיפושים היום: <b>{today_searches:,}</b>\n"
        f"• חיפושים ב-7 ימים: <b>{week_searches:,}</b>\n\n"
        "🏢 <b>10 החברות הנצפות ביותר:</b>\n"
        f"{comp_text}\n\n"
        "🔎 <b>10 החיפושים הנפוצים ביותר:</b>\n"
        f"{queries_text}\n\n"
        "📇 <b>ייצויי VCF:</b>\n"
        f"• סה\"כ ייצואים: <b>{total_exports:,}</b>\n"
        f"{exp_text}\n"
        "──────────────────\n"
        f"🕒 <i>עודכן לאחרונה: {updated_at}</i>"
    )


def register_handlers(client: TelegramClient) -> None:
    """רישום ה-handlers של פאנל הניהול."""

    @client.on(events.NewMessage(pattern=r"^/(admin|stats)(\s|$)"))
    async def handle_admin_command(event: events.NewMessage.Event) -> None:
        sender_id = event.sender_id or event.chat_id
        if not is_admin(sender_id):
            logger.warning(
                "Unauthorized access attempt to admin command from sender_id=%s",
                sender_id,
            )
            return

        try:
            report_text = await build_admin_report()
            await event.respond(
                report_text,
                buttons=admin_keyboard(),
                parse_mode="html",
            )
        except Exception:
            logger.exception("Error generating admin report for sender_id=%s", sender_id)
            await event.respond("❌ אירעה שגיאה בעת יצירת דו\"ח הניהול.")

    @client.on(events.CallbackQuery(pattern=rb"^adm:"))
    async def handle_admin_callback(event: events.CallbackQuery.Event) -> None:
        sender_id = event.sender_id or event.chat_id
        if not is_admin(sender_id):
            logger.warning(
                "Unauthorized callback attempt to admin from sender_id=%s",
                sender_id,
            )
            return

        data = event.data

        if data == b"adm:refresh":
            try:
                await event.answer("מרענן נתונים... ⏳")
                report_text = await build_admin_report()
                await event.edit(
                    report_text,
                    buttons=admin_keyboard(),
                    parse_mode="html",
                )
            except Exception:
                logger.exception("Error refreshing admin report for sender_id=%s", sender_id)
                await event.answer("❌ אירעה שגיאה בעת רענון הנתונים.", alert=True)
