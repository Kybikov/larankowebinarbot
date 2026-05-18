from __future__ import annotations

import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, BotCommandScopeChat, BotCommandScopeDefault

from app.attribution import start_attribution_server
from app.config import Settings
from app.handlers_admin import build_admin_router
from app.handlers_user import build_user_router
from app.meta_capi import MetaConversionsClient
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
    await setup_bot_commands(bot, settings.admin_ids)

    async with PocketBaseClient(settings) as pb:
        await pb.ensure_schema()
        await pb.ensure_default_webinar()
        meta = MetaConversionsClient(settings)
        attribution_runner = await start_attribution_server(settings, pb)
        dispatcher.include_router(build_admin_router(pb, settings.admin_ids, settings.timezone))
        dispatcher.include_router(build_user_router(pb, settings.admin_ids, meta))
        scheduler = build_scheduler(bot, pb)
        scheduler.start()
        try:
            await dispatcher.start_polling(bot, allowed_updates=dispatcher.resolve_used_update_types())
        finally:
            scheduler.shutdown(wait=False)
            await attribution_runner.cleanup()
            await bot.session.close()


async def setup_bot_commands(bot: Bot, admin_ids: tuple[int, ...]) -> None:
    default_commands = [
        BotCommand(command="start", description="Відкрити вебінар"),
    ]
    admin_commands = [
        *default_commands,
        BotCommand(command="admin", description="Адмін-панель"),
        BotCommand(command="panel", description="Адмін-панель"),
    ]
    await bot.set_my_commands(default_commands, scope=BotCommandScopeDefault())
    for admin_id in admin_ids:
        try:
            await bot.set_my_commands(admin_commands, scope=BotCommandScopeChat(chat_id=admin_id))
        except Exception:
            logging.exception("Failed to set admin bot commands for chat_id=%s", admin_id)
