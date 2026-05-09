from __future__ import annotations

import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from app.config import Settings
from app.handlers_admin import build_admin_router
from app.handlers_user import build_user_router
from app.pocketbase import PocketBaseClient
from app.scheduler import build_scheduler


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    settings = Settings.from_env()
    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dispatcher = Dispatcher(storage=MemoryStorage())

    async with PocketBaseClient(settings) as pb:
        await pb.ensure_schema()
        await pb.ensure_default_webinar()
        dispatcher.include_router(build_admin_router(pb, settings.admin_ids, settings.timezone))
        dispatcher.include_router(build_user_router(pb, settings.admin_ids))
        scheduler = build_scheduler(bot, pb)
        scheduler.start()
        try:
            await dispatcher.start_polling(bot, allowed_updates=dispatcher.resolve_used_update_types())
        finally:
            scheduler.shutdown(wait=False)
            await bot.session.close()
