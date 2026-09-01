import html
import logging

from telethon import TelegramClient, events
from telethon.tl.custom import Button

from bot.config import settings
from bot.db import PAGE_SIZE, search_companies
from bot.handlers.export import handle_export_query
from bot.handlers.start import back_to_menu_keyboard
from bot.states import get_session

logger = logging.getLogger(__name__)

SEARCH_PROMPT_MESSAGE = (
    "🔍 <b>חיפוש חופשי</b>\n\n"
    "כתבו שם חברה, קטגוריה, עיר או כל מילה רלוונטית — לדוגמה: "
    "<i>חשמל</i>, <i>בנק מזרחי</i>, <i>תל אביב</i>."
)
NO_RESULTS_MESSAGE = '😕 לא נמצאו תוצאות עבור "{query}".\n\nנסו מילה אחרת או פחות ספציפית.'
ERROR_GENERIC = "❌ אירעה שגיאה. כדאי לנסות שוב בעוד מספר רגעים."


def render_results_page(session) -> tuple[str, list]:
    """מרנדר עמוד תוצאות נוכחי (חיפוש או קטגוריה) לפי session.results ו-session.page."""
    total = len(session.results)
    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    page = max(0, min(session.page, total_pages - 1))
    session.page = page

    start = page * PAGE_SIZE
    page_items = session.results[start : start + PAGE_SIZE]

    lines = [f"{session.origin_label} (נמצאו {total} תוצאות, עמוד {page + 1}/{total_pages})", ""]
    for i, item in enumerate(page_items, start=1):
        name = html.escape(item.get("name") or "ללא שם")
        category = html.escape(item.get("category") or "כללי")
        phone = item.get("primary_phone") or "אין מספר ראשי"
        lines.append(f"{start + i}. <b>{name}</b> — {category}\n   📞 {phone}")

    buttons = []
    for item in page_items:
        name = item.get("name") or "ללא שם"
        label = name if len(name) <= 40 else name[:37] + "..."
        buttons.append([Button.inline(f"🏢 {label}", data=f"co:{item['slug']}".encode("utf-8"))])

    buttons.append(
        [
            Button.inline("◀ הקודם" if page > 0 else "·", data=b"nav:prev" if page > 0 else b"nav:noop"),
            Button.inline(f"{page + 1}/{total_pages}", data=b"nav:noop"),
            Button.inline("הבא ▶" if page < total_pages - 1 else "·", data=b"nav:next" if page < total_pages - 1 else b"nav:noop"),
        ]
    )
    buttons.append([Button.inline("↩️ תפריט ראשי", data=b"menu:main")])

    return "\n".join(lines), buttons


def _is_search_text(event: events.NewMessage.Event) -> bool:
    text = (event.raw_text or "").strip()
    return bool(text) and not text.startswith("/")


def register_handlers(client: TelegramClient) -> None:
    @client.on(events.NewMessage(func=_is_search_text))
    async def handle_text_query(event: events.NewMessage.Event) -> None:
        chat_id = event.chat_id
        query = event.raw_text.strip()
        session = get_session(chat_id)

        if session.awaiting_export_query:
            session.awaiting_export_query = False
            await handle_export_query(event, chat_id, query)
            return

        try:
            results = await search_companies(settings.db_path, query)
            session.results = results
            session.page = 0
            session.category = None
            session.last_query = query
            session.origin_label = f'🔍 תוצאות עבור "{html.escape(query)}"'

            if not results:
                await event.respond(
                    NO_RESULTS_MESSAGE.format(query=html.escape(query)),
                    buttons=back_to_menu_keyboard(),
                    parse_mode="html",
                )
                return

            text, buttons = render_results_page(session)
            await event.respond(text, buttons=buttons, parse_mode="html")
        except Exception:
            logger.exception("error handling search query for chat_id=%s query=%r", chat_id, query)
            await event.respond(ERROR_GENERIC)
