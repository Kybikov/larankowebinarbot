from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BufferedInputFile, CallbackQuery, Message

from app.content import CONFIRMATION_TEXT, WELCOME_TEXT, default_scheduled_messages
from app.keyboards import admin_keyboard, scheduled_message_keyboard, webinar_admin_keyboard
from app.pocketbase import PocketBaseClient
from app.scheduler import send_scheduled_message


class WebinarCreateState(StatesGroup):
    title = State()
    scheduled_at = State()
    zoom_url = State()


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
            await callback.message.answer(
                f"<b>{webinar.get('title')}</b>\n"
                f"ID: <code>{webinar.get('id')}</code>\n"
                f"Дата: {webinar.get('scheduled_at')}\n"
                f"Статус: <b>{webinar.get('status')}</b>\n"
                f"Реєстрацій: <b>{len(registrations)}</b>",
                reply_markup=webinar_admin_keyboard(webinar["id"]),
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

    @router.callback_query(F.data.startswith("admin:publish:"))
    async def publish(callback: CallbackQuery) -> None:
        if not is_admin(callback.from_user.id):
            return
        webinar_id = callback.data.rsplit(":", 1)[1]
        await pb.update_record("webinars", webinar_id, {"status": "published"})
        await callback.message.answer("Вебінар опубліковано.")
        await callback.answer()

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
        await message.answer("Введіть дату і час у форматі YYYY-MM-DD HH:MM за Києвом.")

    @router.message(WebinarCreateState.scheduled_at)
    async def create_date(message: Message, state: FSMContext) -> None:
        if not is_admin(message.from_user.id):
            return
        try:
            naive = datetime.strptime((message.text or "").strip(), "%Y-%m-%d %H:%M")
        except ValueError:
            await message.answer("Не вдалося прочитати дату. Приклад: 2026-05-20 18:00")
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
        await message.answer("Вебінар створено як чернетку.", reply_markup=webinar_admin_keyboard(webinar["id"]))

    return router
