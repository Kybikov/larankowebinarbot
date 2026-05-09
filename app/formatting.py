from __future__ import annotations

from html import escape

from app.content import REGISTRATION_QUESTIONS


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
        f"Дата: {escape(webinar.get('scheduled_at', '-'))}\n"
        f"Реєстрацій: <b>{registrations_count}</b>"
    )
