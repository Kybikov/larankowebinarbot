from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def start_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Зареєструватися на вебінар", callback_data="register:start")]
        ]
    )


def choice_keyboard(prefix: str, choices: list[str]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=choice, callback_data=f"{prefix}:{index}")]
            for index, choice in enumerate(choices)
        ]
    )


def links_keyboard(webinar: dict) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Instagram академії",
                    url=webinar.get("instagram_school_url") or "https://www.instagram.com/laranko_study",
                )
            ],
            [
                InlineKeyboardButton(
                    text="Instagram спікерки Оли Франко",
                    url=webinar.get("instagram_ola_url") or "https://www.instagram.com/oolachka",
                )
            ],
        ]
    )


def admin_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Вебінари", callback_data="admin:webinars"),
                InlineKeyboardButton(text="Статистика", callback_data="admin:stats"),
            ],
            [
                InlineKeyboardButton(text="Користувачі", callback_data="admin:users"),
                InlineKeyboardButton(text="Експорт CSV", callback_data="admin:export"),
            ],
            [InlineKeyboardButton(text="Створити вебінар", callback_data="admin:create_webinar")],
        ]
    )


def webinar_admin_keyboard(webinar_id: str, status: str = "") -> InlineKeyboardMarkup:
    status = (status or "").lower()
    status_rows: list[list[InlineKeyboardButton]] = []
    if status == "published":
        status_rows.append(
            [InlineKeyboardButton(text="Зняти з публікації", callback_data=f"admin:draft:{webinar_id}")]
        )
        status_rows.append([InlineKeyboardButton(text="Архівувати", callback_data=f"admin:archive:{webinar_id}")])
    elif status == "archived":
        status_rows.append([InlineKeyboardButton(text="Опублікувати знову", callback_data=f"admin:publish:{webinar_id}")])
    else:
        status_rows.append([InlineKeyboardButton(text="Опублікувати", callback_data=f"admin:publish:{webinar_id}")])
        status_rows.append([InlineKeyboardButton(text="Архівувати", callback_data=f"admin:archive:{webinar_id}")])

    return InlineKeyboardMarkup(
        inline_keyboard=[
            *status_rows,
            [InlineKeyboardButton(text="Посилання", callback_data=f"admin:links:{webinar_id}")],
            [InlineKeyboardButton(text="Розсилки", callback_data=f"admin:messages:{webinar_id}")],
            [InlineKeyboardButton(text="Назад", callback_data="admin:panel")],
        ]
    )


def webinar_links_keyboard(webinar_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Zoom", callback_data=f"admin:edit_link:{webinar_id}:zoom_url")],
            [InlineKeyboardButton(text="Програма курсу", callback_data=f"admin:edit_link:{webinar_id}:course_url")],
            [InlineKeyboardButton(text="Instagram Оли", callback_data=f"admin:edit_link:{webinar_id}:instagram_ola_url")],
            [InlineKeyboardButton(text="Instagram школи", callback_data=f"admin:edit_link:{webinar_id}:instagram_school_url")],
            [InlineKeyboardButton(text="Instagram студії", callback_data=f"admin:edit_link:{webinar_id}:instagram_studio_url")],
            [InlineKeyboardButton(text="Куратор Telegram", callback_data=f"admin:edit_link:{webinar_id}:curator_username")],
            [InlineKeyboardButton(text="Назад", callback_data="admin:webinars")],
        ]
    )


def scheduled_message_keyboard(message_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Відправити зараз", callback_data=f"admin:send_now:{message_id}")],
            [InlineKeyboardButton(text="Назад", callback_data="admin:webinars")],
        ]
    )


def url_buttons(buttons: list[dict], webinar: dict) -> InlineKeyboardMarkup | None:
    rows: list[list[InlineKeyboardButton]] = []
    url_map = {
        "zoom_url": webinar.get("zoom_url"),
        "course_url": webinar.get("course_url"),
        "instagram_ola_url": webinar.get("instagram_ola_url"),
        "instagram_school_url": webinar.get("instagram_school_url"),
        "instagram_studio_url": webinar.get("instagram_studio_url"),
        "curator_url": f"https://t.me/{webinar.get('curator_username', 'Laranko_Academy').lstrip('@')}",
    }
    for button in buttons or []:
        url = url_map.get(button.get("url_key", ""))
        if url:
            rows.append([InlineKeyboardButton(text=button.get("text", "Відкрити"), url=url)])
    return InlineKeyboardMarkup(inline_keyboard=rows) if rows else None
