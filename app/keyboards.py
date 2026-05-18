from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup


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


def name_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Взяти імʼя з Telegram", callback_data="register:use_tg_name")]
        ]
    )


def phone_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Поділитися номером", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
        input_field_placeholder="Або введіть номер вручну",
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
                InlineKeyboardButton(text="Користувачі", callback_data="admin:users:0"),
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
            [InlineKeyboardButton(text="Деактивувати", callback_data=f"admin:deactivate:{webinar_id}")]
        )
    else:
        status_rows.append([InlineKeyboardButton(text="Зробити активним", callback_data=f"admin:activate:{webinar_id}")])

    return InlineKeyboardMarkup(
        inline_keyboard=[
            *status_rows,
            [InlineKeyboardButton(text="Посилання", callback_data=f"admin:links:{webinar_id}")],
            [InlineKeyboardButton(text="Розсилки", callback_data=f"admin:messages:{webinar_id}")],
            [InlineKeyboardButton(text="Подивитись всі превʼю", callback_data=f"admin:preview_all:{webinar_id}")],
            [InlineKeyboardButton(text="Реєстрації", callback_data=f"admin:registrations:{webinar_id}")],
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
            [
                InlineKeyboardButton(text="Редагувати текст", callback_data=f"admin:edit_msg_text:{message_id}"),
                InlineKeyboardButton(text="Змінити час", callback_data=f"admin:edit_msg_time:{message_id}"),
            ],
            [
                InlineKeyboardButton(text="Додати медіа", callback_data=f"admin:edit_msg_media:{message_id}"),
                InlineKeyboardButton(text="Очистити медіа", callback_data=f"admin:clear_msg_media:{message_id}"),
            ],
            [InlineKeyboardButton(text="Кнопки", callback_data=f"admin:msg_buttons:{message_id}")],
            [InlineKeyboardButton(text="Превʼю для себе", callback_data=f"admin:preview_msg:{message_id}")],
            [InlineKeyboardButton(text="Відправити зараз", callback_data=f"admin:send_now:{message_id}")],
            [InlineKeyboardButton(text="Назад до розсилок", callback_data=f"admin:message_back:{message_id}")],
        ]
    )


def media_collect_keyboard(message_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Готово", callback_data=f"admin:finish_msg_media:{message_id}")],
            [InlineKeyboardButton(text="Скасувати", callback_data=f"admin:cancel_msg_media:{message_id}")],
        ]
    )


MESSAGE_BUTTON_URL_KEYS = {
    "zoom_url": "Zoom",
    "course_url": "Програма курсу",
    "instagram_ola_url": "Instagram Олі",
    "instagram_school_url": "Instagram школи",
    "instagram_studio_url": "Instagram студії",
    "curator_url": "Куратор Telegram",
}


def message_buttons_keyboard(message_id: str, buttons: list[dict]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for index, button in enumerate(buttons or []):
        label = button.get("text") or MESSAGE_BUTTON_URL_KEYS.get(button.get("url_key", ""), "Кнопка")
        rows.append([InlineKeyboardButton(text=f"Видалити: {label}", callback_data=f"admin:del_msg_button:{message_id}:{index}")])
    rows.extend(
        [
            [InlineKeyboardButton(text="Додати кнопку", callback_data=f"admin:add_msg_button:{message_id}")],
            [InlineKeyboardButton(text="Очистити кнопки", callback_data=f"admin:clear_msg_buttons:{message_id}")],
            [InlineKeyboardButton(text="Назад", callback_data=f"admin:message:{message_id}")],
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def message_button_url_key_keyboard(message_id: str) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=label, callback_data=f"admin:add_msg_button_key:{message_id}:{key}")]
        for key, label in MESSAGE_BUTTON_URL_KEYS.items()
    ]
    rows.append([InlineKeyboardButton(text="Скасувати", callback_data=f"admin:msg_buttons:{message_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def page_keyboard(
    *,
    prefix: str,
    page: int,
    total_pages: int,
    back_callback: str | None = None,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    nav: list[InlineKeyboardButton] = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="← Назад", callback_data=f"{prefix}:{page - 1}"))
    nav.append(InlineKeyboardButton(text=f"{page + 1}/{max(total_pages, 1)}", callback_data="admin:noop"))
    if page + 1 < total_pages:
        nav.append(InlineKeyboardButton(text="Далі →", callback_data=f"{prefix}:{page + 1}"))
    rows.append(nav)
    if back_callback:
        rows.append([InlineKeyboardButton(text="Назад", callback_data=back_callback)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def message_list_keyboard(webinar_id: str, messages: list[dict], page: int, total_pages: int) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=item.get("title", "Повідомлення"), callback_data=f"admin:message:{item['id']}")]
        for item in messages
    ]
    nav = page_keyboard(prefix=f"admin:messages:{webinar_id}", page=page, total_pages=total_pages).inline_keyboard
    rows.extend(nav)
    rows.append([InlineKeyboardButton(text="Назад до вебінарів", callback_data="admin:webinars")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def registration_list_keyboard(
    webinar_id: str,
    registrations: list[dict],
    page: int,
    total_pages: int,
) -> InlineKeyboardMarkup:
    rows = []
    for item in registrations:
        label = item.get("name") or item.get("phone") or item.get("id")
        rows.append([InlineKeyboardButton(text=label, callback_data=f"admin:registration:{item['id']}")])
    nav = page_keyboard(prefix=f"admin:registrations:{webinar_id}", page=page, total_pages=total_pages).inline_keyboard
    rows.extend(nav)
    rows.append([InlineKeyboardButton(text="Назад до вебінарів", callback_data="admin:webinars")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def user_list_keyboard(page: int, total_pages: int) -> InlineKeyboardMarkup:
    return page_keyboard(
        prefix="admin:users",
        page=page,
        total_pages=total_pages,
        back_callback="admin:panel",
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
