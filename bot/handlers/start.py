from telethon import TelegramClient, events
from telethon.tl.custom import Button

WELCOME_MESSAGE = (
    "📇 <b>Support Contacts IL</b>\n\n"
    "מאגר פרטי שירות לקוחות של 645 חברות ישראליות — טלפונים, מיילים, "
    "וואטסאפ, סניפים ושעות פעילות, במקום אחד.\n\n"
    "איך אפשר לעזור?"
)

ABOUT_MESSAGE = (
    "ℹ️ <b>על המאגר</b>\n\n"
    "📊 645 חברות · 2,118 מספרי טלפון · 2,379 מיילים · 5,556 סניפים\n\n"
    "🔎 החיפוש מבוסס על מנוע FTS5 עם תמיכה בעברית (ה' הידיעה, ריבוי והטיות) "
    "ומדורג לפי רלוונטיות.\n\n"
    "📇 אפשר לייצא כל חברה, קטגוריה שלמה או תוצאות חיפוש כקובץ אנשי קשר (VCF) "
    "שמתאים לייבוא ישיר לטלפון."
)


def main_menu_keyboard() -> list:
    return [
        [Button.inline("🔍 חיפוש חופשי", data=b"menu:search")],
        [Button.inline("📂 לפי קטגוריה", data=b"menu:categories")],
        [Button.inline("📇 ייצוא VCF", data=b"menu:export")],
        [Button.inline("ℹ️ על המאגר", data=b"menu:about")],
    ]


def back_to_menu_keyboard() -> list:
    return [[Button.inline("↩️ תפריט ראשי", data=b"menu:main")]]


def register_handlers(client: TelegramClient) -> None:
    @client.on(events.NewMessage(pattern=r"^/start"))
    async def handle_start(event: events.NewMessage.Event) -> None:
        await event.respond(WELCOME_MESSAGE, buttons=main_menu_keyboard(), parse_mode="html")
