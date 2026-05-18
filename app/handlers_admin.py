from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from html import escape
from math import ceil
from zoneinfo import ZoneInfo

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BufferedInputFile, CallbackQuery, Message

from app.content import CONFIRMATION_TEXT, WELCOME_TEXT, default_scheduled_messages
from app.formatting import format_datetime_with_tz
from app.keyboards import (
    admin_keyboard,
    media_collect_keyboard,
    message_button_url_key_keyboard,
    message_buttons_keyboard,
    message_list_keyboard,
    registration_list_keyboard,
    scheduled_message_keyboard,
    user_list_keyboard,
    webinar_admin_keyboard,
    webinar_links_keyboard,
)
from app.pocketbase import USER_COLLECTION, PocketBaseClient
from app.scheduler import get_media_file_ids, send_message_preview, send_scheduled_message


DATE_INPUT_HINT = (
    "Введіть дату і час вебінару за Києвом.\n\n"
    "Наприклад:\n"
    "20.05.2026 18:00\n\n"
    "Також підійде формат: 2026-05-20 18:00"
)
PAGE_SIZE = 5


class WebinarCreateState(StatesGroup):
    title = State()
    scheduled_at = State()
    zoom_url = State()


class LinkEditState(StatesGroup):
    value = State()


class MessageEditState(StatesGroup):
    text = State()
    time = State()
    media = State()
    button_text = State()


LINK_FIELDS = {
    "zoom_url": "Zoom",
    "course_url": "Програма курсу",
    "instagram_ola_url": "Instagram Оли",
    "instagram_school_url": "Instagram школи",
    "instagram_studio_url": "Instagram студії",
    "curator_username": "Куратор Telegram",
}


STATUS_DESCRIPTIONS = {
    "draft": "неактивний, користувачі його не бачать",
    "published": "активний для /start і реєстрацій",
    "archived": "неактивний, користувачі його не бачать",
}


def build_admin_router(pb: PocketBaseClient, admin_ids: tuple[int, ...], timezone_name: str) -> Router:
    router = Router()

    def is_admin(user_id: int | None) -> bool:
        return bool(user_id and user_id in admin_ids)

    @router.message(F.text.in_({"/admin", "/panel"}))
    async def panel(message: Message, state: FSMContext) -> None:
        if not is_admin(message.from_user.id):
            return
        await state.clear()
        await message.answer("Адмін-панель Laranko", reply_markup=admin_keyboard())

    @router.callback_query(F.data == "admin:panel")
    async def panel_callback(callback: CallbackQuery, state: FSMContext) -> None:
        if not is_admin(callback.from_user.id):
            return
        await state.clear()
        await callback.message.answer("Адмін-панель Laranko", reply_markup=admin_keyboard())
        await callback.answer()

    @router.callback_query(F.data == "admin:noop")
    async def noop(callback: CallbackQuery) -> None:
        await callback.answer()

    @router.callback_query(F.data == "admin:stats")
    async def stats(callback: CallbackQuery) -> None:
        if not is_admin(callback.from_user.id):
            return
        users = await pb.list_all_records(USER_COLLECTION)
        webinars = await pb.list_all_records("webinars")
        registrations = await pb.list_all_records("registrations")
        pending = await pb.list_all_records("scheduled_messages", filter_='status="pending"')
        await callback.message.answer(
            "<b>Статистика</b>\n\n"
            f"Користувачів: <b>{len(users)}</b>\n"
            f"Вебінарів: <b>{len(webinars)}</b>\n"
            f"Реєстрацій: <b>{len(registrations)}</b>\n"
            f"Запланованих повідомлень: <b>{len(pending)}</b>"
        )
        await callback.answer()

    @router.callback_query(F.data.startswith("admin:users"))
    async def users(callback: CallbackQuery) -> None:
        if not is_admin(callback.from_user.id):
            return
        parts = callback.data.split(":")
        page = int(parts[2]) if len(parts) > 2 else 0
        records = await pb.list_all_records(USER_COLLECTION, sort="-last_seen_at")
        if not records:
            await callback.message.answer("Користувачів поки немає.", reply_markup=user_list_keyboard(0, 1))
            await callback.answer()
            return

        registrations = await pb.list_all_records("registrations", sort="-registered_at")
        registration_by_user = latest_registration_by_user(registrations)
        total_pages = max(ceil(len(records) / PAGE_SIZE), 1)
        page = min(max(page, 0), total_pages - 1)
        page_items = records[page * PAGE_SIZE : (page + 1) * PAGE_SIZE]
        lines = [
            "<b>Користувачі</b>",
            f"Всього: <b>{len(records)}</b> | Зареєстровані: <b>{len(registration_by_user)}</b>",
            f"Сторінка {page + 1}/{total_pages}",
            "",
        ]
        for index, item in enumerate(page_items, start=page * PAGE_SIZE + 1):
            lines.append(format_admin_user_row(index, item, registration_by_user.get(item.get("id")), timezone_name))

        await callback.message.answer(
            "\n\n".join(lines),
            reply_markup=user_list_keyboard(page, total_pages),
        )
        await callback.answer()

    @router.callback_query(F.data == "admin:webinars")
    async def webinars(callback: CallbackQuery) -> None:
        if not is_admin(callback.from_user.id):
            return
        records = await pb.list_records("webinars", sort="-scheduled_at", per_page=10)
        if not records:
            await callback.message.answer("Вебінарів поки немає.")
        for webinar in records:
            registrations = await pb.list_all_records("registrations", filter_=f'webinar="{webinar["id"]}"')
            status = webinar.get("status", "")
            visible_status = "active" if status == "published" else "inactive"
            status_description = STATUS_DESCRIPTIONS.get(status, STATUS_DESCRIPTIONS["draft"])
            await callback.message.answer(
                f"<b>{webinar.get('title')}</b>\n"
                f"ID: <code>{webinar.get('id')}</code>\n"
                f"Дата: {format_datetime_with_tz(webinar.get('scheduled_at'), timezone_name)}\n"
                f"Статус: <b>{visible_status}</b> — {status_description}\n"
                f"Реєстрацій: <b>{len(registrations)}</b>",
                reply_markup=webinar_admin_keyboard(webinar["id"], status),
            )
        await callback.answer()

    @router.callback_query(F.data.startswith("admin:deactivate:"))
    async def deactivate(callback: CallbackQuery) -> None:
        if not is_admin(callback.from_user.id):
            return
        webinar_id = callback.data.rsplit(":", 1)[1]
        await pb.update_record("webinars", webinar_id, {"status": "draft"})
        await callback.message.answer("Вебінар деактивовано. Користувачі не бачать його в /start.")
        await callback.answer()

    @router.callback_query(F.data.startswith("admin:activate:"))
    async def activate(callback: CallbackQuery) -> None:
        if not is_admin(callback.from_user.id):
            return
        webinar_id = callback.data.rsplit(":", 1)[1]
        await pb.update_record("webinars", webinar_id, {"status": "published"})
        await callback.message.answer("Вебінар активовано. Тепер він відкривається через /start і приймає реєстрації.")
        await callback.answer()

    @router.callback_query(F.data.startswith("admin:links:"))
    async def links(callback: CallbackQuery) -> None:
        if not is_admin(callback.from_user.id):
            return
        webinar_id = callback.data.rsplit(":", 1)[1]
        webinar = await pb.get_record("webinars", webinar_id)
        lines = [f"<b>Посилання для вебінару</b>\n{webinar.get('title', '')}\n"]
        for key, label in LINK_FIELDS.items():
            value = webinar.get(key) or "не задано"
            if key == "curator_username" and value != "не задано":
                value = "@" + str(value).lstrip("@")
            lines.append(f"<b>{label}:</b> {escape(str(value))}")
        await callback.message.answer(
            "\n".join(lines),
            reply_markup=webinar_links_keyboard(webinar_id),
        )
        await callback.answer()

    @router.callback_query(F.data.startswith("admin:edit_link:"))
    async def edit_link_start(callback: CallbackQuery, state: FSMContext) -> None:
        if not is_admin(callback.from_user.id):
            return
        _, _, webinar_id, field = callback.data.split(":", 3)
        if field not in LINK_FIELDS:
            await callback.answer("Поле не знайдено", show_alert=True)
            return
        webinar = await pb.get_record("webinars", webinar_id)
        current_value = webinar.get(field) or "не задано"
        await state.set_state(LinkEditState.value)
        await state.update_data(webinar_id=webinar_id, field=field)
        await callback.message.answer(
            f"Введіть нове значення для <b>{LINK_FIELDS[field]}</b>.\n\n"
            f"Поточне значення: <code>{escape(str(current_value))}</code>\n\n"
            "Щоб очистити поле, надішліть `-`."
        )
        await callback.answer()

    @router.message(LinkEditState.value)
    async def edit_link_finish(message: Message, state: FSMContext) -> None:
        if not is_admin(message.from_user.id):
            return
        data = await state.get_data()
        field = data["field"]
        webinar_id = data["webinar_id"]
        value = (message.text or "").strip()
        if value == "-":
            value = ""
        if field == "curator_username":
            value = value.lstrip("@")
        elif value and not value.startswith(("http://", "https://")):
            await message.answer("Посилання має починатися з http:// або https://. Спробуйте ще раз.")
            return
        webinar = await pb.update_record("webinars", webinar_id, {field: value})
        await state.clear()
        shown_value = ("@" + value) if field == "curator_username" and value else (value or "очищено")
        await message.answer(
            f"Готово. <b>{LINK_FIELDS[field]}</b>: {escape(shown_value)}",
            reply_markup=webinar_links_keyboard(webinar["id"]),
        )

    @router.callback_query(F.data.startswith("admin:messages:"))
    async def messages(callback: CallbackQuery) -> None:
        if not is_admin(callback.from_user.id):
            return
        parts = callback.data.split(":")
        webinar_id = parts[2]
        page = int(parts[3]) if len(parts) > 3 else 0
        records = await pb.list_all_records(
            "scheduled_messages",
            filter_=f'webinar="{webinar_id}"',
            sort="send_at",
        )
        if not records:
            await callback.message.answer("Для цього вебінару немає запланованих повідомлень.")
            await callback.answer()
            return
        total_pages = max(ceil(len(records) / PAGE_SIZE), 1)
        page = min(max(page, 0), total_pages - 1)
        page_items = records[page * PAGE_SIZE : (page + 1) * PAGE_SIZE]
        lines = [f"<b>Розсилки вебінару</b>\nСторінка {page + 1}/{total_pages}\n"]
        for index, item in enumerate(page_items, start=page * PAGE_SIZE + 1):
            lines.append(
                f"{index}. <b>{escape(item.get('title', 'Повідомлення'))}</b>\n"
                f"   Час: {format_datetime_with_tz(item.get('send_at'), timezone_name)}\n"
                f"   Статус: {escape(item.get('status') or '-')}, медіа: {escape(media_label(item))}"
            )
        await callback.message.answer(
            "\n".join(lines),
            reply_markup=message_list_keyboard(webinar_id, page_items, page, total_pages),
        )
        await callback.answer()

    @router.callback_query(F.data.startswith("admin:preview_all:"))
    async def preview_all_messages(callback: CallbackQuery) -> None:
        if not is_admin(callback.from_user.id):
            return
        webinar_id = callback.data.rsplit(":", 1)[1]
        now = datetime.now(timezone.utc).isoformat()
        records = await pb.list_all_records(
            "scheduled_messages",
            filter_=f'webinar="{webinar_id}" && status="pending" && send_at>="{now}"',
            sort="send_at",
        )
        if not records:
            await callback.message.answer("Для цього вебінару немає майбутніх запланованих повідомлень.")
            await callback.answer()
            return
        await callback.message.answer(f"Відправляю майбутні превʼю по черзі: <b>{len(records)}</b>.")
        for index, scheduled in enumerate(records, start=1):
            await callback.message.answer(
                f"<b>Превʼю {index}/{len(records)}</b>\n"
                f"{escape(scheduled.get('title', 'Повідомлення'))}\n"
                f"Час: {format_datetime_with_tz(scheduled.get('send_at'), timezone_name)}"
            )
            await send_message_preview(callback.bot, pb, scheduled, callback.from_user.id)
            await asyncio.sleep(0.3)
        await callback.message.answer("Готово, всі превʼю відправлено.")
        await callback.answer()

    @router.callback_query(F.data.startswith("admin:message:"))
    async def message_detail(callback: CallbackQuery) -> None:
        if not is_admin(callback.from_user.id):
            return
        message_id = callback.data.rsplit(":", 1)[1]
        item = await pb.get_record("scheduled_messages", message_id)
        preview = (item.get("text") or "").strip()
        if len(preview) > 900:
            preview = preview[:900] + "..."
        await callback.message.answer(
            f"<b>{escape(item.get('title', 'Повідомлення'))}</b>\n"
            f"ID: <code>{item['id']}</code>\n"
            f"Час: {format_datetime_with_tz(item.get('send_at'), timezone_name)}\n"
            f"Статус: <b>{escape(item.get('status') or '-')}</b>\n"
            f"Медіа: <b>{escape(media_label(item))}</b>\n\n"
            f"Кнопок: <b>{len(item.get('buttons') or [])}</b>\n\n"
            f"<b>Текст:</b>\n{escape(preview)}",
            reply_markup=scheduled_message_keyboard(item["id"]),
        )
        await callback.answer()

    @router.callback_query(F.data.startswith("admin:message_back:"))
    async def message_back(callback: CallbackQuery) -> None:
        if not is_admin(callback.from_user.id):
            return
        message_id = callback.data.rsplit(":", 1)[1]
        item = await pb.get_record("scheduled_messages", message_id)
        records = await pb.list_all_records(
            "scheduled_messages",
            filter_=f'webinar="{item["webinar"]}"',
            sort="send_at",
        )
        page_items = records[:PAGE_SIZE]
        total_pages = max(ceil(len(records) / PAGE_SIZE), 1)
        await callback.message.answer(
            "<b>Розсилки вебінару</b>\nСторінка 1/" + str(total_pages),
            reply_markup=message_list_keyboard(item["webinar"], page_items, 0, total_pages),
        )
        await callback.answer()

    @router.callback_query(F.data.startswith("admin:edit_msg_text:"))
    async def edit_message_text_start(callback: CallbackQuery, state: FSMContext) -> None:
        if not is_admin(callback.from_user.id):
            return
        await state.set_state(MessageEditState.text)
        await state.update_data(message_id=callback.data.rsplit(":", 1)[1])
        await callback.message.answer("Надішліть новий текст нагадування одним повідомленням.")
        await callback.answer()

    @router.message(MessageEditState.text)
    async def edit_message_text_finish(message: Message, state: FSMContext) -> None:
        if not is_admin(message.from_user.id):
            return
        text = (message.text or message.caption or "").strip()
        if len(text) < 3:
            await message.answer("Текст занадто короткий. Надішліть повний текст нагадування.")
            return
        data = await state.get_data()
        item = await pb.update_record("scheduled_messages", data["message_id"], {"text": text, "status": "pending"})
        await state.clear()
        await message.answer("Текст оновлено.", reply_markup=scheduled_message_keyboard(item["id"]))

    @router.callback_query(F.data.startswith("admin:edit_msg_time:"))
    async def edit_message_time_start(callback: CallbackQuery, state: FSMContext) -> None:
        if not is_admin(callback.from_user.id):
            return
        message_id = callback.data.rsplit(":", 1)[1]
        item = await pb.get_record("scheduled_messages", message_id)
        await state.set_state(MessageEditState.time)
        await state.update_data(message_id=message_id)
        await callback.message.answer(
            "Введіть нову дату і час відправки за Києвом.\n\n"
            f"Поточний час: <code>{format_datetime_with_tz(item.get('send_at'), timezone_name)}</code>\n\n"
            "Наприклад: 20.05.2026 17:00"
        )
        await callback.answer()

    @router.message(MessageEditState.time)
    async def edit_message_time_finish(message: Message, state: FSMContext) -> None:
        if not is_admin(message.from_user.id):
            return
        try:
            naive = parse_admin_datetime(message.text or "")
        except ValueError:
            await message.answer("Не вдалося прочитати дату. Приклад: 20.05.2026 17:00")
            return
        data = await state.get_data()
        send_at = naive.replace(tzinfo=ZoneInfo(timezone_name)).isoformat()
        item = await pb.update_record(
            "scheduled_messages",
            data["message_id"],
            {"send_at": send_at, "status": "pending", "sent_at": ""},
        )
        await state.clear()
        await message.answer(
            f"Час оновлено: <code>{format_datetime_with_tz(item['send_at'], timezone_name)}</code>",
            reply_markup=scheduled_message_keyboard(item["id"]),
        )

    @router.callback_query(F.data.startswith("admin:edit_msg_media:"))
    async def edit_message_media_start(callback: CallbackQuery, state: FSMContext) -> None:
        if not is_admin(callback.from_user.id):
            return
        await state.set_state(MessageEditState.media)
        message_id = callback.data.rsplit(":", 1)[1]
        await state.update_data(message_id=message_id, media_file_ids=[])
        await callback.message.answer(
            "Надішліть одне або кілька фото. Можна відправити альбомом або по одному, потім натисніть «Готово».\n\n"
            "Відео теж можна надіслати, але тільки одне.",
            reply_markup=media_collect_keyboard(message_id),
        )
        await callback.answer()

    @router.message(MessageEditState.media)
    async def edit_message_media_finish(message: Message, state: FSMContext) -> None:
        if not is_admin(message.from_user.id):
            return
        data = await state.get_data()
        message_id = data["message_id"]
        if message.photo:
            media_file_ids = list(data.get("media_file_ids") or [])
            media_file_ids.append(message.photo[-1].file_id)
            await state.update_data(media_file_ids=media_file_ids)
            await message.answer(
                f"Фото додано: <b>{len(media_file_ids)}</b>. Надішліть ще або натисніть «Готово».",
                reply_markup=media_collect_keyboard(message_id),
            )
            return
        elif message.video:
            item = await pb.update_record(
                "scheduled_messages",
                message_id,
                {
                    "media_type": "video",
                    "media_file_id": message.video.file_id,
                    "media_file_ids": [message.video.file_id],
                    "status": "pending",
                },
            )
            await state.clear()
            await message.answer("Відео додано.", reply_markup=scheduled_message_keyboard(item["id"]))
        else:
            await message.answer("Потрібно надіслати саме фото або відео.")
            return

    @router.callback_query(MessageEditState.media, F.data.startswith("admin:finish_msg_media:"))
    async def finish_message_media(callback: CallbackQuery, state: FSMContext) -> None:
        if not is_admin(callback.from_user.id):
            return
        data = await state.get_data()
        message_id = data.get("message_id") or callback.data.rsplit(":", 1)[1]
        media_file_ids = list(data.get("media_file_ids") or [])
        if not media_file_ids:
            await callback.answer("Спочатку надішліть хоча б одне фото", show_alert=True)
            return
        item = await pb.update_record(
            "scheduled_messages",
            message_id,
            {
                "media_type": "photo",
                "media_file_id": media_file_ids[0],
                "media_file_ids": media_file_ids,
                "status": "pending",
            },
        )
        await state.clear()
        await callback.message.answer(
            f"Фото додано: <b>{len(media_file_ids)}</b>.",
            reply_markup=scheduled_message_keyboard(item["id"]),
        )
        await callback.answer()

    @router.callback_query(MessageEditState.media, F.data.startswith("admin:cancel_msg_media:"))
    async def cancel_message_media(callback: CallbackQuery, state: FSMContext) -> None:
        if not is_admin(callback.from_user.id):
            return
        message_id = callback.data.rsplit(":", 1)[1]
        await state.clear()
        item = await pb.get_record("scheduled_messages", message_id)
        await callback.message.answer("Додавання медіа скасовано.", reply_markup=scheduled_message_keyboard(item["id"]))
        await callback.answer()

    @router.callback_query(F.data.startswith("admin:clear_msg_media:"))
    async def clear_message_media(callback: CallbackQuery) -> None:
        if not is_admin(callback.from_user.id):
            return
        message_id = callback.data.rsplit(":", 1)[1]
        item = await pb.update_record(
            "scheduled_messages",
            message_id,
            {"media_type": "none", "media_file_id": "", "media_file_ids": [], "status": "pending"},
        )
        await callback.message.answer("Медіа очищено.", reply_markup=scheduled_message_keyboard(item["id"]))
        await callback.answer()

    @router.callback_query(F.data.startswith("admin:msg_buttons:"))
    async def message_buttons(callback: CallbackQuery) -> None:
        if not is_admin(callback.from_user.id):
            return
        message_id = callback.data.rsplit(":", 1)[1]
        item = await pb.get_record("scheduled_messages", message_id)
        buttons = item.get("buttons") or []
        if buttons:
            lines = ["<b>Кнопки нагадування</b>"]
            for index, button in enumerate(buttons, start=1):
                lines.append(f"{index}. {escape(button.get('text', 'Кнопка'))} → <code>{escape(button.get('url_key', '-'))}</code>")
            text = "\n".join(lines)
        else:
            text = "<b>Кнопки нагадування</b>\nКнопок поки немає."
        await callback.message.answer(text, reply_markup=message_buttons_keyboard(message_id, buttons))
        await callback.answer()

    @router.callback_query(F.data.startswith("admin:add_msg_button:"))
    async def add_message_button_start(callback: CallbackQuery, state: FSMContext) -> None:
        if not is_admin(callback.from_user.id):
            return
        message_id = callback.data.rsplit(":", 1)[1]
        await state.set_state(MessageEditState.button_text)
        await state.update_data(message_id=message_id)
        await callback.message.answer("Надішліть текст нової кнопки.")
        await callback.answer()

    @router.message(MessageEditState.button_text)
    async def add_message_button_text(message: Message, state: FSMContext) -> None:
        if not is_admin(message.from_user.id):
            return
        text = (message.text or "").strip()
        if len(text) < 2:
            await message.answer("Текст кнопки занадто короткий. Надішліть текст ще раз.")
            return
        data = await state.get_data()
        await state.clear()
        await state.update_data(message_id=data["message_id"], button_text=text)
        await message.answer(
            "Оберіть, яке посилання відкриватиме кнопка.",
            reply_markup=message_button_url_key_keyboard(data["message_id"]),
        )

    @router.callback_query(F.data.startswith("admin:add_msg_button_key:"))
    async def add_message_button_finish(callback: CallbackQuery, state: FSMContext) -> None:
        if not is_admin(callback.from_user.id):
            return
        _, _, message_id, url_key = callback.data.split(":", 3)
        data = await state.get_data()
        button_text = (data.get("button_text") or "").strip()
        if not button_text:
            await callback.answer("Текст кнопки не знайдено, почніть додавання ще раз", show_alert=True)
            return
        item = await pb.get_record("scheduled_messages", message_id)
        buttons = list(item.get("buttons") or [])
        buttons.append({"text": button_text, "url_key": url_key})
        item = await pb.update_record("scheduled_messages", message_id, {"buttons": buttons, "status": "pending"})
        await state.clear()
        await callback.message.answer("Кнопку додано.", reply_markup=message_buttons_keyboard(message_id, item.get("buttons") or []))
        await callback.answer()

    @router.callback_query(F.data.startswith("admin:del_msg_button:"))
    async def delete_message_button(callback: CallbackQuery) -> None:
        if not is_admin(callback.from_user.id):
            return
        _, _, message_id, index_text = callback.data.split(":", 3)
        item = await pb.get_record("scheduled_messages", message_id)
        buttons = list(item.get("buttons") or [])
        try:
            index = int(index_text)
            buttons.pop(index)
        except (ValueError, IndexError):
            await callback.answer("Кнопку не знайдено", show_alert=True)
            return
        item = await pb.update_record("scheduled_messages", message_id, {"buttons": buttons, "status": "pending"})
        await callback.message.answer("Кнопку видалено.", reply_markup=message_buttons_keyboard(message_id, item.get("buttons") or []))
        await callback.answer()

    @router.callback_query(F.data.startswith("admin:clear_msg_buttons:"))
    async def clear_message_buttons(callback: CallbackQuery) -> None:
        if not is_admin(callback.from_user.id):
            return
        message_id = callback.data.rsplit(":", 1)[1]
        item = await pb.update_record("scheduled_messages", message_id, {"buttons": [], "status": "pending"})
        await callback.message.answer("Кнопки очищено.", reply_markup=message_buttons_keyboard(message_id, item.get("buttons") or []))
        await callback.answer()

    @router.callback_query(F.data.startswith("admin:preview_msg:"))
    async def preview_message(callback: CallbackQuery) -> None:
        if not is_admin(callback.from_user.id):
            return
        message_id = callback.data.rsplit(":", 1)[1]
        scheduled = await pb.get_record("scheduled_messages", message_id)
        await callback.message.answer("Превʼю нижче. Саме так повідомлення побачить користувач:")
        await send_message_preview(callback.bot, pb, scheduled, callback.from_user.id)
        await callback.answer()

    @router.callback_query(F.data.startswith("admin:registrations:"))
    async def registrations(callback: CallbackQuery) -> None:
        if not is_admin(callback.from_user.id):
            return
        parts = callback.data.split(":")
        webinar_id = parts[2]
        page = int(parts[3]) if len(parts) > 3 else 0
        webinar = await pb.get_record("webinars", webinar_id)
        records = await pb.list_all_records(
            "registrations",
            filter_=f'webinar="{webinar_id}"',
            sort="-registered_at",
        )
        if not records:
            await callback.message.answer("На цей вебінар ще немає реєстрацій.")
            await callback.answer()
            return
        total_pages = max(ceil(len(records) / PAGE_SIZE), 1)
        page = min(max(page, 0), total_pages - 1)
        page_items = records[page * PAGE_SIZE : (page + 1) * PAGE_SIZE]
        lines = [f"<b>Реєстрації</b>\n{escape(webinar.get('title', ''))}\nСторінка {page + 1}/{total_pages}\n"]
        for index, item in enumerate(page_items, start=page * PAGE_SIZE + 1):
            lines.append(
                f"{index}. <b>{escape(item.get('name') or '-')}</b>\n"
                f"   Телефон: {escape(item.get('phone') or '-')}\n"
                f"   Дата: {format_datetime_with_tz(item.get('registered_at'), timezone_name)}"
            )
        await callback.message.answer(
            "\n".join(lines),
            reply_markup=registration_list_keyboard(webinar_id, page_items, page, total_pages),
        )
        await callback.answer()

    @router.callback_query(F.data.startswith("admin:registration:"))
    async def registration_detail(callback: CallbackQuery) -> None:
        if not is_admin(callback.from_user.id):
            return
        registration_id = callback.data.rsplit(":", 1)[1]
        registration = await pb.get_record("registrations", registration_id)
        webinar = await pb.get_record("webinars", registration["webinar"])
        user = await pb.get_record(USER_COLLECTION, registration["user"])
        answers = registration.get("answers") or {}
        labels = {
            "name": "Імʼя",
            "phone": "Телефон",
            "design_stage": "Етап у дизайні",
            "realization_experience": "Досвід реалізації",
            "speaker_question": "Питання до Оли",
        }
        answer_lines = [
            f"<b>{label}:</b> {escape(str(answers.get(key) or registration.get(key) or '-'))}"
            for key, label in labels.items()
        ]
        await callback.message.answer(
            f"<b>Користувач</b>\n"
            f"Telegram ID: <code>{escape(str(user.get('telegram_id', '-')))}</code>\n"
            f"Username: @{escape(user.get('username') or '-')}\n"
            f"Telegram name: {escape(' '.join(filter(None, [user.get('first_name'), user.get('last_name')])) or '-')}\n\n"
            f"<b>Вебінар:</b> {escape(webinar.get('title', '-'))}\n"
            f"<b>Зареєстровано:</b> {format_datetime_with_tz(registration.get('registered_at'), timezone_name)}\n\n"
            + "\n".join(answer_lines)
        )
        await callback.answer()

    @router.callback_query(F.data.startswith("admin:send_now:"))
    async def send_now(callback: CallbackQuery) -> None:
        if not is_admin(callback.from_user.id):
            return
        message_id = callback.data.rsplit(":", 1)[1]
        scheduled = await pb.get_record("scheduled_messages", message_id)
        result = await send_scheduled_message(callback.bot, pb, scheduled)
        await callback.message.answer(
            f"Розсилку виконано.\nУспішно: {result['success_count']}\nПомилок: {result['failure_count']}"
        )
        await callback.answer()

    @router.callback_query(F.data == "admin:export")
    async def export(callback: CallbackQuery) -> None:
        if not is_admin(callback.from_user.id):
            return
        csv_bytes = await pb.registrations_csv()
        await callback.message.answer_document(
            BufferedInputFile(csv_bytes, filename="laranko_registrations.csv"),
            caption="Експорт реєстрацій",
        )
        await callback.answer()

    @router.callback_query(F.data == "admin:create_webinar")
    async def create_start(callback: CallbackQuery, state: FSMContext) -> None:
        if not is_admin(callback.from_user.id):
            return
        await state.set_state(WebinarCreateState.title)
        await callback.message.answer("Введіть назву нового вебінару.")
        await callback.answer()

    @router.message(WebinarCreateState.title)
    async def create_title(message: Message, state: FSMContext) -> None:
        if not is_admin(message.from_user.id):
            return
        await state.update_data(title=(message.text or "").strip())
        await state.set_state(WebinarCreateState.scheduled_at)
        await message.answer(DATE_INPUT_HINT)

    @router.message(WebinarCreateState.scheduled_at)
    async def create_date(message: Message, state: FSMContext) -> None:
        if not is_admin(message.from_user.id):
            return
        try:
            naive = parse_admin_datetime(message.text or "")
        except ValueError:
            await message.answer("Не вдалося прочитати дату.\n\n" + DATE_INPUT_HINT)
            return
        await state.update_data(scheduled_at=naive.replace(tzinfo=ZoneInfo(timezone_name)).isoformat())
        await state.set_state(WebinarCreateState.zoom_url)
        await message.answer("Вставте Zoom-посилання або напишіть `-`, якщо додасте пізніше.")

    @router.message(WebinarCreateState.zoom_url)
    async def create_finish(message: Message, state: FSMContext) -> None:
        if not is_admin(message.from_user.id):
            return
        data = await state.get_data()
        zoom_url = "" if (message.text or "").strip() == "-" else (message.text or "").strip()
        scheduled_at = datetime.fromisoformat(data["scheduled_at"])
        slug = f"webinar-{scheduled_at.strftime('%Y%m%d%H%M%S')}"
        webinar = await pb.create_record(
            "webinars",
            {
                "slug": slug,
                "title": data["title"],
                "description": WELCOME_TEXT.replace("20 травня о 18:00", scheduled_at.strftime("%d.%m.%Y о %H:%M")),
                "confirmation_text": CONFIRMATION_TEXT.replace("20 травня о 18:00", scheduled_at.strftime("%d.%m.%Y о %H:%M")),
                "scheduled_at": scheduled_at.isoformat(),
                "timezone": timezone_name,
                "status": "draft",
                "zoom_url": zoom_url,
                "course_url": "",
                "instagram_ola_url": "",
                "instagram_school_url": "",
                "instagram_studio_url": "",
                "curator_username": "Laranko_Academy",
            },
        )
        for template in default_scheduled_messages(scheduled_at):
            await pb.create_record(
                "scheduled_messages",
                {
                    "webinar": webinar["id"],
                    "title": template.title,
                    "text": template.text,
                    "send_at": template.send_at.isoformat(),
                    "buttons": [button.__dict__ for button in template.buttons],
                    "media_type": template.media_type,
                    "media_file_id": "",
                    "media_file_ids": [],
                    "status": "pending",
                    "sent_at": "",
                },
            )
        await state.clear()
        await message.answer("Вебінар створено як неактивний.", reply_markup=webinar_admin_keyboard(webinar["id"], "draft"))

    return router


def latest_registration_by_user(registrations: list[dict]) -> dict[str, dict]:
    result: dict[str, dict] = {}
    for registration in registrations:
        user_id = registration.get("user")
        if user_id and user_id not in result:
            result[user_id] = registration
    return result


def format_admin_user_row(index: int, user: dict, registration: dict | None, timezone_name: str) -> str:
    status_icon = "✅" if registration else "❌"
    full_name = " ".join(filter(None, [user.get("first_name"), user.get("last_name")])) or "-"
    username = f"@{user.get('username')}" if user.get("username") else "-"
    language = user.get("language_code") or "-"
    last_seen = format_datetime_with_tz(user.get("last_seen_at"), timezone_name)
    registered_at = format_datetime_with_tz(registration.get("registered_at"), timezone_name) if registration else "-"
    phone = registration.get("phone") if registration else ""
    name = registration.get("name") if registration else ""
    registration_line = (
        f"   ✅ Реєстрація: {escape(registered_at)}"
        + (f" | {escape(name)}" if name else "")
        + (f" | {escape(phone)}" if phone else "")
        if registration
        else "   ❌ Реєстрації ще немає"
    )
    return (
        f"{index}. {status_icon} <b>{escape(full_name)}</b>\n"
        f"   ID: <code>{escape(str(user.get('telegram_id') or '-'))}</code> | {escape(username)}\n"
        f"   Мова: {escape(language)} | Остання активність: {escape(last_seen)}\n"
        f"{registration_line}"
    )


def parse_admin_datetime(value: str) -> datetime:
    clean_value = " ".join(value.strip().split())
    formats = (
        "%d.%m.%Y %H:%M",
        "%d/%m/%Y %H:%M",
        "%Y-%m-%d %H:%M",
        "%d.%m.%y %H:%M",
    )
    for fmt in formats:
        try:
            return datetime.strptime(clean_value, fmt)
        except ValueError:
            pass
    raise ValueError("Unsupported datetime format")


def media_label(item: dict) -> str:
    media_type = item.get("media_type") or "none"
    media_file_ids = get_media_file_ids(item)
    if not media_file_ids or media_type == "none":
        return "не прикріплено"
    if media_type == "photo":
        if len(media_file_ids) == 1:
            return "1 фото прикріплено"
        return f"{len(media_file_ids)} фото прикріплено"
    if media_type == "video":
        return "відео прикріплено"
    return f"{media_type} прикріплено"
