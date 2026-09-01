import asyncio
import logging

from telethon import TelegramClient

from bot.config import settings
from bot.handlers import callbacks, export, search, start


async def main() -> None:
    logging.basicConfig(level=logging.INFO)

    client = TelegramClient("bot_session", settings.api_id, settings.api_hash)

    start.register_handlers(client)
    search.register_handlers(client)
    export.register_handlers(client)
    callbacks.register_handlers(client)

    await client.start(bot_token=settings.bot_token)
    logging.info("Support Contacts IL bot started (Telethon MTProto)")
    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
