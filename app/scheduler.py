from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from aiogram import Bot
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


async def send_scheduled_message(bot: Bot, pb: PocketBaseClient, scheduled: dict[str, Any]) -> dict[str, Any]:
    await pb.update_record("scheduled_messages", scheduled["id"], {"status": "sending"})
    webinar = await pb.get_record("webinars", scheduled["webinar"])
    registrations = await pb.registered_users_for_webinar(webinar["id"])
    buttons = scheduled.get("buttons") or []
    keyboard = url_buttons(buttons, webinar)
    errors: list[dict[str, str]] = []
    success_count = 0

    for registration in registrations:
        user = registration.get("user_record") or {}
        telegram_id = user.get("telegram_id")
        if not telegram_id:
            continue
        try:
            media_file_id = scheduled.get("media_file_id") or ""
            if scheduled.get("media_type") == "photo" and media_file_id:
                await bot.send_photo(telegram_id, media_file_id, caption=scheduled["text"], reply_markup=keyboard)
            elif scheduled.get("media_type") == "video" and media_file_id:
                await bot.send_video(telegram_id, media_file_id, caption=scheduled["text"], reply_markup=keyboard)
            else:
                await bot.send_message(telegram_id, scheduled["text"], reply_markup=keyboard)
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
