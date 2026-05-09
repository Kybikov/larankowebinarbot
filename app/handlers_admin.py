from __future__ import annotations

from datetime import datetime
from html import escape
from zoneinfo import ZoneInfo

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BufferedInputFile, CallbackQuery, Message

from app.content import CONFIRMATION_TEXT, WELCOME_TEXT, default_scheduled_messages
from app.keyboards import admin_keyboard, scheduled_message_keyboard, webinar_admin_keyboard, webinar_links_keyboard
from app.pocketbase import PocketBaseClient
from app.scheduler import send_scheduled_message


DATE_INPUT_HINT = (
    "Введіть дату і час вебінару за Києвом.\n\n"
    "Наприклад:\n"
    "20.05.2026 18:00\n\n"
    "Також підійде формат: 2026-05-20 18:00"
)


class WebinarCreateState(StatesGroup):
    title = State()
    scheduled_at = State()
    zoom_url = State()


class LinkEditState(StatesGroup):
    value = State()


LINK_FIELDS = {
    "zoom_url": "Zoom",
    "course_url": "Програма курсу",
    "instagram_ola_url": "Instagram Оли",
    "instagram_school_url": "Instagram школи",
    "instagram_studio_url": "Instagram студії",
    "curator_username": "Куратор Telegram",
}


STATUS_DESCRIPTIONS = {
    "draft": "чернетка, користувачі її не бачать",
    "published": "активний вебінар для /start і реєстрацій",
    "archived": "архів, користувачі її не бачать",
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

    @router.callback_query(F.data == "admin:stats")
    async def stats(callback: CallbackQuery) -> None:
        if not is_admin(callback.from_user.id):
            return
        users = await pb.list_all_records("users")
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

    @router.callback_query(F.data == "admin:users")
    async def users(callback: CallbackQuery) -> None:
        if not is_admin(callback.from_user.id):
            return
        records = await pb.list_records("users", sort="-last_seen_at", per_page=20)
        if not records:
            text = "Користувачів поки немає."
        else:
            lines = [
                f"• <code>{item.get('telegram_id')}</code> @{item.get('username') or '-'} "
                f"{item.get('first_name') or ''} {item.get('last_name') or ''}".strip()
                for item in records
            ]
            text = "<b>Останні користувачі</b>\n\n" + "\n".join(lines)
        await callback.message.answer(text)
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
            status_description = STATUS_DESCRIPTIONS.get(status, "")
            await callback.message.answer(
                f"<b>{webinar.get('title')}</b>\n"
                f"ID: <code>{webinar.get('id')}</code>\n"
                f"Дата: {webinar.get('scheduled_at')}\n"
                f"Статус: <b>{status}</b>"
                f"{f' — {status_description}' if status_description else ''}\n"
                f"Реєстрацій: <b>{len(registrations)}</b>",
                reply_markup=webinar_admin_keyboard(webinar["id"], status),
            )
        await callback.answer()

    @router.callback_query(F.data.startswith("admin:archive:"))
    async def archive(callback: CallbackQuery) -> None:
        if not is_admin(callback.from_user.id):
            return
        webinar_id = callback.data.rsplit(":", 1)[1]
        await pb.update_record("webinars", webinar_id, {"status": "archived"})
        await callback.message.answer("Вебінар архівовано.")
        await callback.answer()

    @router.callback_query(F.data.startswith("admin:draft:"))
    async def draft(callback: CallbackQuery) -> None:
        if not is_admin(callback.from_user.id):
            return
        webinar_id = callback.data.rsplit(":", 1)[1]
        await pb.update_record("webinars", webinar_id, {"status": "draft"})
        await callback.message.answer("Вебінар знято з публікації. Тепер користувачі не бачать його в /start.")
        await callback.answer()

    @router.callback_query(F.data.startswith("admin:publish:"))
    async def publish(callback: CallbackQuery) -> None:
        if not is_admin(callback.from_user.id):
            return
        webinar_id = callback.data.rsplit(":", 1)[1]
        await pb.update_record("webinars", webinar_id, {"status": "published"})
        await callback.message.answer("Вебінар опубліковано. Тепер він активний для /start і реєстрацій.")
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
        webinar_id = callback.data.rsplit(":", 1)[1]
        records = await pb.list_records(
            "scheduled_messages",
            filter_=f'webinar="{webinar_id}"',
            sort="send_at",
            per_page=30,
        )
        if not records:
            await callback.message.answer("Для цього вебінару немає запланованих повідомлень.")
        for item in records:
            await callback.message.answer(
                f"<b>{item.get('title')}</b>\n"
                f"Статус: <b>{item.get('status')}</b>\n"
                f"Час: {item.get('send_at')}",
                reply_markup=scheduled_message_keyboard(item["id"]),
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
                    "status": "pending",
                    "sent_at": "",
                },
            )
        await state.clear()
        await message.answer("Вебінар створено як чернетку.", reply_markup=webinar_admin_keyboard(webinar["id"], "draft"))

    return router


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
