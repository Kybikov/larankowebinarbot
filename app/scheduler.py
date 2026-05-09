from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from aiogram import Bot
from aiogram.types import InputMediaPhoto
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.keyboards import url_buttons
from app.pocketbase import PocketBaseClient


def build_scheduler(bot: Bot, pb: PocketBaseClient) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=timezone.utc)
    scheduler.add_job(run_due_broadcasts, "interval", seconds=30, args=[bot, pb], max_instances=1)
    return scheduler


async def run_due_broadcasts(bot: Bot, pb: PocketBaseClient) -> None:
    for scheduled in await pb.pending_messages(datetime.now(timezone.utc)):
        await send_scheduled_message(bot, pb, scheduled)


async def send_message_preview(bot: Bot, pb: PocketBaseClient, scheduled: dict[str, Any], chat_id: int) -> None:
    webinar = await pb.get_record("webinars", scheduled["webinar"])
    await deliver_scheduled_message(bot, scheduled, webinar, chat_id)


async def send_scheduled_message(bot: Bot, pb: PocketBaseClient, scheduled: dict[str, Any]) -> dict[str, Any]:
    await pb.update_record("scheduled_messages", scheduled["id"], {"status": "sending"})
    webinar = await pb.get_record("webinars", scheduled["webinar"])
    registrations = await pb.registered_users_for_webinar(webinar["id"])
    errors: list[dict[str, str]] = []
    success_count = 0

    for registration in registrations:
        user = registration.get("user_record") or {}
        telegram_id = user.get("telegram_id")
        if not telegram_id:
            continue
        try:
            await deliver_scheduled_message(bot, scheduled, webinar, telegram_id)
            success_count += 1
        except Exception as exc:
            errors.append({"telegram_id": str(telegram_id), "error": str(exc)})

    now = datetime.now(timezone.utc).isoformat()
    failure_count = len(errors)
    status = "sent" if failure_count == 0 else "failed"
    await pb.update_record("scheduled_messages", scheduled["id"], {"status": status, "sent_at": now})
    await pb.log_broadcast(
        {
            "scheduled_message": scheduled["id"],
            "webinar": webinar["id"],
            "recipient_count": len(registrations),
            "success_count": success_count,
            "failure_count": failure_count,
            "errors": errors,
            "sent_at": now,
        }
    )
    return {
        "recipient_count": len(registrations),
        "success_count": success_count,
        "failure_count": failure_count,
        "errors": errors,
    }


async def deliver_scheduled_message(bot: Bot, scheduled: dict[str, Any], webinar: dict[str, Any], chat_id: int | str) -> None:
    keyboard = url_buttons(scheduled.get("buttons") or [], webinar)
    media_file_ids = get_media_file_ids(scheduled)
    if scheduled.get("media_type") == "photo" and len(media_file_ids) > 1:
        media = [
            InputMediaPhoto(media=file_id, caption=scheduled["text"] if index == 0 else None)
            for index, file_id in enumerate(media_file_ids)
        ]
        await bot.send_media_group(chat_id, media)
        if keyboard:
            await bot.send_message(chat_id, "Посилання:", reply_markup=keyboard)
    elif scheduled.get("media_type") == "photo" and media_file_ids:
        await bot.send_photo(chat_id, media_file_ids[0], caption=scheduled["text"], reply_markup=keyboard)
    elif scheduled.get("media_type") == "video" and media_file_ids:
        await bot.send_video(chat_id, media_file_ids[0], caption=scheduled["text"], reply_markup=keyboard)
    else:
        await bot.send_message(chat_id, scheduled["text"], reply_markup=keyboard)


def get_media_file_ids(scheduled: dict[str, Any]) -> list[str]:
    media_file_ids = scheduled.get("media_file_ids") or []
    if isinstance(media_file_ids, str):
        media_file_ids = [media_file_ids] if media_file_ids else []
    if media_file_ids:
        return [str(file_id) for file_id in media_file_ids if file_id]
    media_file_id = scheduled.get("media_file_id") or ""
    return [str(media_file_id)] if media_file_id else []
