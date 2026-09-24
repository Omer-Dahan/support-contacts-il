import asyncio
import logging

from telethon import TelegramClient, events

from bot.config import settings
from bot.handlers import admin, callbacks, export, search, start
from bot.users_db import ensure_user, init_users_db


async def main() -> None:
    logging.basicConfig(level=logging.INFO)

    await init_users_db(settings.users_db_path)

    client = TelegramClient("bot_session", settings.api_id, settings.api_hash)

    @client.on(events.NewMessage)
    async def track_incoming_message(event: events.NewMessage.Event) -> None:
        try:
            sender = await event.get_sender()
            chat_id = event.chat_id
            first_name = getattr(sender, "first_name", "") or ""
            username = getattr(sender, "username", "") or ""
            asyncio.create_task(
                ensure_user(chat_id, first_name, username, settings.users_db_path)
            )
        except Exception:
            pass

    start.register_handlers(client)
    search.register_handlers(client)
    export.register_handlers(client)
    callbacks.register_handlers(client)
    admin.register_handlers(client)

    await client.start(bot_token=settings.bot_token)
    logging.info("Support Contacts IL bot started (Telethon MTProto)")
    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
