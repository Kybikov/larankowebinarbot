from __future__ import annotations

from datetime import datetime, timezone
from html import escape
from zoneinfo import ZoneInfo

from app.content import REGISTRATION_QUESTIONS


DEFAULT_DISPLAY_TZ = "Europe/Kyiv"


def format_datetime(value: str | datetime | None, timezone_name: str = DEFAULT_DISPLAY_TZ) -> str:
    if not value:
        return "-"
    if isinstance(value, datetime):
        parsed = value
    else:
        raw = str(value).strip()
        if not raw:
            return "-"
        normalized = raw.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            return raw
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    local = parsed.astimezone(ZoneInfo(timezone_name))
    return local.strftime("%d.%m.%Y о %H:%M")


def format_datetime_with_tz(value: str | datetime | None, timezone_name: str = DEFAULT_DISPLAY_TZ) -> str:
    formatted = format_datetime(value, timezone_name)
    return "-" if formatted == "-" else f"{formatted} за Києвом"


def admin_registration_text(user: dict, webinar: dict, answers: dict) -> str:
    tg = [
        f"ID: <code>{user.get('telegram_id', '')}</code>",
        f"Username: @{escape(user.get('username') or '-')}",
        f"Імʼя Telegram: {escape(' '.join(filter(None, [user.get('first_name'), user.get('last_name')])) or '-')}",
        f"Мова: {escape(user.get('language_code') or '-')}",
    ]
    answer_lines = []
    for question in REGISTRATION_QUESTIONS:
        answer_lines.append(f"<b>{escape(question['key'])}</b>: {escape(str(answers.get(question['key'], '-')))}")
    return (
        "🆕 <b>Нова реєстрація на вебінар</b>\n\n"
        f"<b>Вебінар:</b> {escape(webinar.get('title', '-'))}\n\n"
        "<b>Telegram:</b>\n"
        + "\n".join(tg)
        + "\n\n<b>Анкета:</b>\n"
        + "\n".join(answer_lines)
    )


def webinar_summary(webinar: dict, registrations_count: int = 0) -> str:
    return (
        f"<b>{escape(webinar.get('title', '-'))}</b>\n"
        f"ID: <code>{webinar.get('id', '')}</code>\n"
        f"Статус: <b>{escape(webinar.get('status', '-'))}</b>\n"
        f"Дата: {escape(format_datetime_with_tz(webinar.get('scheduled_at')))}\n"
        f"Реєстрацій: <b>{registrations_count}</b>"
    )
