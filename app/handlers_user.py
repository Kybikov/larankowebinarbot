from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove

from app.content import REGISTRATION_QUESTIONS
from app.formatting import admin_registration_text
from app.keyboards import choice_keyboard, links_keyboard, name_keyboard, phone_keyboard, start_keyboard
from app.pocketbase import USER_COLLECTION, PocketBaseClient


logger = logging.getLogger(__name__)


class RegistrationState(StatesGroup):
    answering = State()


def build_user_router(pb: PocketBaseClient, admin_ids: tuple[int, ...]) -> Router:
    router = Router()

    @router.message(CommandStart())
    async def start(message: Message, state: FSMContext) -> None:
        logger.info("Handling /start for user_id=%s username=%s", message.from_user.id, message.from_user.username)
        await state.clear()
        await pb.upsert_user(message.from_user)
        webinar = await pb.active_webinar()
        await message.answer(webinar.get("description") or "", reply_markup=start_keyboard())

    @router.callback_query(F.data == "register:start")
    async def start_registration(callback: CallbackQuery, state: FSMContext) -> None:
        user = await pb.upsert_user(callback.from_user)
        webinar = await pb.active_webinar()
        existing = await pb.registration_for(user["id"], webinar["id"])
        if existing:
            await callback.message.answer(
                "Ви вже зареєстровані на цей вебінар 🤍",
                reply_markup=links_keyboard(webinar),
            )
            await callback.answer()
            return
        await state.set_state(RegistrationState.answering)
        await state.update_data(step=0, answers={}, user_id=user["id"], webinar_id=webinar["id"])
        await ask_question(callback.message, 0)
        await callback.answer()

    @router.callback_query(RegistrationState.answering, F.data.startswith("answer:"))
    async def choice_answer(callback: CallbackQuery, state: FSMContext) -> None:
        data = await state.get_data()
        step = int(data["step"])
        question = REGISTRATION_QUESTIONS[step]
        if question["kind"] != "choice":
            await callback.answer("Напишіть відповідь текстом", show_alert=True)
            return
        index = int(callback.data.split(":", 1)[1])
        choices = question["choices"]
        if index >= len(choices):
            await callback.answer("Варіант не знайдено", show_alert=True)
            return
        await save_answer_and_continue(callback.message, state, choices[index])
        await callback.answer()

    @router.callback_query(RegistrationState.answering, F.data == "register:use_tg_name")
    async def use_tg_name(callback: CallbackQuery, state: FSMContext) -> None:
        data = await state.get_data()
        step = int(data["step"])
        question = REGISTRATION_QUESTIONS[step]
        if question["key"] != "name":
            await callback.answer("Ця кнопка зараз недоступна", show_alert=True)
            return
        profile_name = " ".join(
            part for part in [callback.from_user.first_name, callback.from_user.last_name] if part
        ).strip()
        if not profile_name:
            await callback.answer("У Telegram не вказано імʼя. Напишіть його вручну.", show_alert=True)
            return
        await save_answer_and_continue(callback.message, state, profile_name)
        await callback.answer()

    @router.message(RegistrationState.answering, F.contact)
    async def contact_answer(message: Message, state: FSMContext) -> None:
        data = await state.get_data()
        step = int(data["step"])
        question = REGISTRATION_QUESTIONS[step]
        if question["key"] != "phone":
            await message.answer("Дякую, але зараз потрібно відповісти на інше питання.")
            return
        if message.contact.user_id and message.contact.user_id != message.from_user.id:
            await message.answer("Будь ласка, поділіться саме своїм номером або введіть його вручну.")
            return
        await save_answer_and_continue(message, state, message.contact.phone_number)

    @router.message(RegistrationState.answering)
    async def text_answer(message: Message, state: FSMContext) -> None:
        data = await state.get_data()
        step = int(data["step"])
        question = REGISTRATION_QUESTIONS[step]
        if question["kind"] == "choice":
            await message.answer("Будь ласка, оберіть один із варіантів кнопкою.")
            return
        text = (message.text or "").strip()
        if len(text) < 2:
            await message.answer("Напишіть, будь ласка, трохи детальніше.")
            return
        await save_answer_and_continue(message, state, text)

    @router.message()
    async def fallback_start(message: Message, state: FSMContext) -> None:
        current_state = await state.get_state()
        if current_state:
            logger.info("Ignoring fallback while state=%s for user_id=%s", current_state, message.from_user.id)
            return
        logger.info(
            "Handling fallback start for user_id=%s username=%s text=%r",
            message.from_user.id,
            message.from_user.username,
            message.text,
        )
        await start(message, state)

    async def ask_question(message: Message, step: int) -> None:
        question = REGISTRATION_QUESTIONS[step]
        keyboard = None
        if question["kind"] == "choice":
            keyboard = choice_keyboard("answer", question["choices"])
        elif question["key"] == "name":
            keyboard = name_keyboard()
        elif question["key"] == "phone":
            keyboard = phone_keyboard()
        await message.answer(question["text"], reply_markup=keyboard)

    async def save_answer_and_continue(message: Message, state: FSMContext, answer: str) -> None:
        data = await state.get_data()
        step = int(data["step"])
        answers = dict(data.get("answers", {}))
        answers[REGISTRATION_QUESTIONS[step]["key"]] = answer
        step += 1
        if step < len(REGISTRATION_QUESTIONS):
            await state.update_data(step=step, answers=answers)
            if REGISTRATION_QUESTIONS[step - 1]["key"] == "phone":
                await message.answer("Дякую, номер збережено.", reply_markup=ReplyKeyboardRemove())
            await ask_question(message, step)
            return

        webinar = await pb.get_record("webinars", data["webinar_id"])
        user = await pb.get_record(USER_COLLECTION, data["user_id"])
        await pb.save_registration(user_id=user["id"], webinar_id=webinar["id"], answers=answers)
        await state.clear()
        await message.answer(
            webinar.get("confirmation_text") or "Готово, ви успішно зареєстровані 🤍",
            reply_markup=links_keyboard(webinar),
        )
        notification = admin_registration_text(user, webinar, answers)
        for admin_id in admin_ids:
            try:
                await message.bot.send_message(admin_id, notification)
            except Exception:
                pass

    return router
