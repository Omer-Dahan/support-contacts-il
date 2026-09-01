import html
import logging

from telethon import TelegramClient, events
from telethon.tl.custom import Button

from bot.config import settings
from bot.db import get_categories, get_companies_by_category, get_company_details
from bot.handlers.details import render_company_details
from bot.handlers.export import EXPORT_MENU_MESSAGE, export_menu_keyboard
from bot.handlers.search import ERROR_GENERIC, SEARCH_PROMPT_MESSAGE, render_results_page
from bot.handlers.start import ABOUT_MESSAGE, WELCOME_MESSAGE, back_to_menu_keyboard, main_menu_keyboard
from bot.states import get_session

logger = logging.getLogger(__name__)


def _categories_keyboard(categories: list[tuple[str, int]]) -> list:
    rows = [
        [Button.inline(f"{cat} ({count})", data=f"cat:{cat}".encode("utf-8"))]
        for cat, count in categories
    ]
    rows.append([Button.inline("↩️ תפריט ראשי", data=b"menu:main")])
    return rows


def register_handlers(client: TelegramClient) -> None:
    @client.on(events.CallbackQuery(pattern=rb"^menu:"))
    async def handle_menu(event: events.CallbackQuery.Event) -> None:
        chat_id = event.chat_id
        action = event.data.decode("utf-8").split(":", 1)[1]

        try:
            get_session(chat_id).awaiting_export_query = False

            if action == "main":
                await event.edit(WELCOME_MESSAGE, buttons=main_menu_keyboard(), parse_mode="html")

            elif action == "search":
                await event.edit(SEARCH_PROMPT_MESSAGE, buttons=back_to_menu_keyboard(), parse_mode="html")

            elif action == "categories":
                categories = await get_categories(settings.db_path)
                await event.edit(
                    "📂 <b>בחרו קטגוריה:</b>",
                    buttons=_categories_keyboard(categories),
                    parse_mode="html",
                )

            elif action == "export":
                await event.edit(EXPORT_MENU_MESSAGE, buttons=export_menu_keyboard(), parse_mode="html")

            elif action == "about":
                await event.edit(ABOUT_MESSAGE, buttons=back_to_menu_keyboard(), parse_mode="html")
        except Exception:
            logger.exception("error handling menu callback for chat_id=%s", chat_id)
            await event.answer(ERROR_GENERIC, alert=True)

    @client.on(events.CallbackQuery(pattern=rb"^cat:"))
    async def handle_category_select(event: events.CallbackQuery.Event) -> None:
        chat_id = event.chat_id
        category = event.data.decode("utf-8").split(":", 1)[1]

        try:
            session = get_session(chat_id)
            companies = await get_companies_by_category(settings.db_path, category)
            session.results = companies
            session.page = 0
            session.category = category
            session.origin_label = f"📂 קטגוריה: {html.escape(category)}"

            if not companies:
                await event.edit(
                    f"😕 לא נמצאו חברות בקטגוריית {html.escape(category)}.",
                    buttons=back_to_menu_keyboard(),
                    parse_mode="html",
                )
                return

            text, buttons = render_results_page(session)
            await event.edit(text, buttons=buttons, parse_mode="html")
        except Exception:
            logger.exception("error handling category select for chat_id=%s category=%r", chat_id, category)
            await event.answer(ERROR_GENERIC, alert=True)

    @client.on(events.CallbackQuery(pattern=rb"^co:"))
    async def handle_company_select(event: events.CallbackQuery.Event) -> None:
        chat_id = event.chat_id
        slug = event.data.decode("utf-8").split(":", 1)[1]

        try:
            company = await get_company_details(settings.db_path, slug)
            if not company:
                await event.answer("החברה לא נמצאה.", alert=True)
                return

            text, buttons = render_company_details(company)
            await event.edit(text, buttons=buttons, parse_mode="html")
        except Exception:
            logger.exception("error handling company select for chat_id=%s slug=%r", chat_id, slug)
            await event.answer(ERROR_GENERIC, alert=True)

    @client.on(events.CallbackQuery(pattern=rb"^nav:"))
    async def handle_nav(event: events.CallbackQuery.Event) -> None:
        chat_id = event.chat_id
        action = event.data.decode("utf-8").split(":", 1)[1]

        try:
            if action == "noop":
                await event.answer()
                return

            session = get_session(chat_id)
            if not session.results:
                await event.edit(WELCOME_MESSAGE, buttons=main_menu_keyboard(), parse_mode="html")
                return

            if action == "next":
                session.page += 1
            elif action == "prev":
                session.page -= 1
            # "back_to_list" - re-render current page as-is

            text, buttons = render_results_page(session)
            await event.edit(text, buttons=buttons, parse_mode="html")
        except Exception:
            logger.exception("error handling nav callback for chat_id=%s", chat_id)
            await event.answer(ERROR_GENERIC, alert=True)
