import logging
import os
import re
import tempfile
import time
from typing import Any

from telethon import TelegramClient, events
from telethon.tl.custom import Button

from bot.config import settings
from bot.db import get_categories, get_companies_for_export, get_company_details
from bot.handlers.start import back_to_menu_keyboard
from bot.states import get_session

logger = logging.getLogger(__name__)

EXPORT_MENU_MESSAGE = (
    "📇 <b>ייצוא אנשי קשר (VCF)</b>\n\n"
    "בחרו מה לייצא — הקובץ יישלח כאן ומתאים לייבוא ישיר לאנשי הקשר בטלפון."
)
EXPORT_QUERY_PROMPT = "🔍 כתבו את מילת החיפוש שלפיה לייצא אנשי קשר (לדוגמה: <i>ביטוח</i>)."
EXPORT_EMPTY_MESSAGE = "😕 לא נמצאו חברות תואמות לייצוא."
ERROR_GENERIC = "❌ אירעה שגיאה. כדאי לנסות שוב בעוד מספר רגעים."


def export_menu_keyboard() -> list:
    return [
        [Button.inline("📦 כל המאגר", data=b"exp:all")],
        [Button.inline("📂 לפי קטגוריה", data=b"exp:catlist")],
        [Button.inline("🔍 לפי חיפוש", data=b"exp:querymode")],
        [Button.inline("↩️ תפריט ראשי", data=b"menu:main")],
    ]


def _category_list_keyboard(categories: list[tuple[str, int]]) -> list:
    rows = [
        [Button.inline(f"{cat} ({count})", data=f"exp:cat:{cat}".encode("utf-8"))]
        for cat, count in categories
    ]
    rows.append([Button.inline("↩️ חזרה", data=b"menu:export")])
    return rows


def escape_vcard_text(text: Any) -> str:
    if not text:
        return ""
    text = str(text).replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")
    return text.replace("\r\n", "\\n").replace("\n", "\\n")


def company_to_vcard(company: dict) -> str:
    name = (company.get("name") or company.get("legal_name") or company.get("slug") or "ללא שם").strip()
    escaped_name = escape_vcard_text(name)
    lines = [
        "BEGIN:VCARD",
        "VERSION:3.0",
        f"FN;CHARSET=UTF-8:{escaped_name}",
        f"ORG;CHARSET=UTF-8:{escaped_name}",
    ]

    if company.get("category"):
        lines.append(f"CATEGORIES;CHARSET=UTF-8:{escape_vcard_text(company['category'].strip())}")

    for p in company.get("phones", []):
        num = (p.get("clean_number") or p.get("number") or "").strip()
        if not num:
            continue
        type_parts = ["WORK", "FAX" if p.get("kind") == "fax" else "VOICE"]
        if p.get("is_primary"):
            type_parts.append("PREF")
        label = p.get("label") or ""
        if label:
            lines.append(f"X-ABLabel;CHARSET=UTF-8:{escape_vcard_text(label)}")
        lines.append(f"TEL;TYPE={','.join(type_parts)}:{num}")

    for e in company.get("emails", []):
        email = (e.get("email") or "").strip()
        if email:
            lines.append(f"EMAIL;TYPE=INTERNET,WORK:{email}")

    if company.get("website_url"):
        lines.append(f"URL:{company['website_url']}")

    for b in company.get("branches", [])[:3]:
        street = escape_vcard_text(b.get("address") or "")
        city = escape_vcard_text(b.get("city") or "")
        lines.append(f"ADR;TYPE=WORK;CHARSET=UTF-8:;;{street};{city};;IL;")

    notes = []
    if company.get("description"):
        notes.append(company["description"])
    if company.get("ai_summary"):
        notes.append(f"סיכום שירות: {company['ai_summary']}")
    wa_contacts = [w.get("phone") or w.get("url") for w in company.get("whatsapp", []) if w.get("phone") or w.get("url")]
    if wa_contacts:
        notes.append(f"WhatsApp: {', '.join(wa_contacts)}")
    if notes:
        lines.append(f"NOTE;CHARSET=UTF-8:{escape_vcard_text(chr(10).join(notes))}")

    lines.append("END:VCARD")
    return "\r\n".join(lines) + "\r\n"


def build_vcf(companies: list[dict]) -> str:
    return "".join(company_to_vcard(c) for c in companies)


async def send_vcf_file(event, companies: list[dict], filename_base: str) -> None:
    if not companies:
        await event.respond(EXPORT_EMPTY_MESSAGE, buttons=back_to_menu_keyboard())
        return

    safe_name = re.sub(r"[^a-zA-Z0-9_\u0590-\u05FF]", "_", filename_base) or "contacts"
    tmp_path = os.path.join(tempfile.gettempdir(), f"{safe_name}_{int(time.time())}.vcf")

    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(build_vcf(companies))

        await event.respond(
            f"✅ יוצאו {len(companies)} אנשי קשר.",
            file=tmp_path,
            buttons=back_to_menu_keyboard(),
        )
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            logger.warning("failed to remove temp vcf file %s", tmp_path)


async def handle_export_query(event, chat_id: int, query: str) -> None:
    try:
        companies = await get_companies_for_export(settings.db_path, query=query)
        await send_vcf_file(event, companies, f"search_{query}")
    except Exception:
        logger.exception("error exporting query for chat_id=%s query=%r", chat_id, query)
        await event.respond(ERROR_GENERIC)


def register_handlers(client: TelegramClient) -> None:
    @client.on(events.CallbackQuery(pattern=rb"^exp:"))
    async def handle_export_callback(event: events.CallbackQuery.Event) -> None:
        chat_id = event.chat_id
        data = event.data.decode("utf-8")
        action = data.split(":", 1)[1]

        try:
            if action == "all":
                await event.answer("מייצא את כל המאגר, רגע...")
                companies = await get_companies_for_export(settings.db_path, all_companies=True)
                await send_vcf_file(event, companies, "support_contacts_il_all")

            elif action == "catlist":
                categories = await get_categories(settings.db_path)
                await event.edit(
                    "📂 בחרו קטגוריה לייצוא:",
                    buttons=_category_list_keyboard(categories),
                )

            elif action.startswith("cat:"):
                category = action.split(":", 1)[1]
                await event.answer(f"מייצא את קטגוריית {category}, רגע...")
                companies = await get_companies_for_export(settings.db_path, category=category)
                await send_vcf_file(event, companies, f"category_{category}")

            elif action == "querymode":
                session = get_session(chat_id)
                session.awaiting_export_query = True
                await event.edit(EXPORT_QUERY_PROMPT, buttons=back_to_menu_keyboard(), parse_mode="html")

            elif action.startswith("one:"):
                slug = action.split(":", 1)[1]
                await event.answer("מייצא, רגע...")
                company = await get_company_details(settings.db_path, slug)
                await send_vcf_file(event, [company] if company else [], f"company_{slug}")

        except Exception:
            logger.exception("error handling export callback for chat_id=%s data=%r", chat_id, data)
            await event.answer(ERROR_GENERIC, alert=True)
