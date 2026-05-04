from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    CallbackQuery,
)

from bot.db import session_scope
from bot.services.users import bind_device_id, get_or_create_user, is_valid_device_id
from bot.states import Onboarding

log = logging.getLogger(__name__)
router = Router(name="start")


WELCOME = (
    "Привет, я <b>Flow</b> 🌸\n\n"
    "Я помогу собрать персональный <b>бокс заботы</b> — каждый месяц "
    "к датам М тебе будет приезжать коробка со средствами гигиены, "
    "уходом и приятностями. Подобрано лично под тебя: твои "
    "предпочтения, аллергии, образ жизни и фаза цикла.\n\n"
    "Также есть <b>Lira Premium</b> — цифровой тариф 199 ₽/мес: "
    "расширенная аналитика, прогноз овуляции, экспорт PDF/CSV, гайды. "
    "Без бокса и без опросника — оплатил, получил код активации, "
    "ввёл в приложении.\n\n"
    "Для бокса сначала зададу несколько вопросов (можно прерваться и "
    "вернуться позже — твои ответы сохраняются), потом покажу тарифы и "
    "оформим подписку через Telegram-оплату. После оплаты дам код для "
    "приложения."
)


def _welcome_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✨ Lira Premium — 199₽/мес",
                    callback_data="premium:buy",
                )
            ],
            [
                InlineKeyboardButton(
                    text="📦 Бокс заботы (опросник)",
                    callback_data="onboarding:start",
                )
            ],
            [
                InlineKeyboardButton(
                    text="📦 Мой бокс", callback_data="cabinet:status"
                )
            ],
        ]
    )


def _parse_device_suffix(args: str | None, prefix: str) -> str | None:
    """Pull the device id out of a `<prefix>_<device_id>` start argument.

    Returns None if the argument is missing, doesn't start with the prefix,
    or carries an unparseable / oversized device id.
    """
    if not args:
        return None
    raw = args.strip()
    if not raw.startswith(f"{prefix}_"):
        return None
    candidate = raw[len(prefix) + 1 :]
    if not is_valid_device_id(candidate):
        return None
    return candidate


@router.message(CommandStart(deep_link=True), F.text.regexp(r"^/start\s+premium(_[A-Za-z0-9._-]{8,64})?\b"))
async def on_start_premium(
    message: Message, state: FSMContext, command: CommandObject
) -> None:
    """Deep link from the app: tariff is preselected as Premium → straight to invoice.

    Supports `/start premium` (legacy, no device binding) and
    `/start premium_<device_id>` which binds the device before invoicing,
    so polling /v1/subscription/by-device picks up the activation
    automatically once payment is finalised.
    """
    await state.clear()
    if message.from_user is not None:
        async with session_scope() as session:
            user = await get_or_create_user(session, message.from_user)
            device_id = _parse_device_suffix(command.args, "premium")
            if device_id is not None:
                await bind_device_id(session, user, device_id)
    await _send_premium_invoice(message, state)


@router.message(CommandStart(deep_link=True), F.text.regexp(r"^/start\s+link_[A-Za-z0-9._-]{8,64}\b"))
async def on_start_link(
    message: Message, state: FSMContext, command: CommandObject
) -> None:
    """Bind a Lira install to this Telegram user without going to checkout.

    Used when the user wants to pre-authorise the device so that any
    *existing* paid subscription on this Telegram account starts pushing
    state to the app immediately.
    """
    await state.clear()
    if message.from_user is None:
        return
    device_id = _parse_device_suffix(command.args, "link")
    if device_id is None:
        await message.answer(
            "Не получилось распознать код устройства. Открой приложение "
            "Lira → «Подписка» → «Привязать через Telegram» ещё раз."
        )
        return
    async with session_scope() as session:
        user = await get_or_create_user(session, message.from_user)
        await bind_device_id(session, user, device_id)
    await message.answer(
        "Готово! Устройство привязано к этому Telegram-аккаунту 🌸\n\n"
        "Если у тебя уже есть активная подписка — приложение подхватит её "
        "в течение пары минут. После следующей оплаты подписка тоже "
        "включится автоматически — без ввода кода."
    )


@router.callback_query(F.data == "premium:buy")
async def on_premium_buy(cb: CallbackQuery, state: FSMContext) -> None:
    if cb.message is None:
        await cb.answer()
        return
    await state.clear()
    if cb.from_user is not None:
        async with session_scope() as session:
            await get_or_create_user(session, cb.from_user)
    try:
        await cb.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await _send_premium_invoice(cb.message, state)
    await cb.answer()


async def _send_premium_invoice(message: Message, state: FSMContext) -> None:
    """Push the user straight into invoicing for the Premium tariff."""
    from bot.models import Tariff
    from bot.services.payments import TARIFF_META, send_invoice

    tariff = Tariff.PREMIUM
    await state.set_state(Onboarding.waiting_payment)
    await state.update_data(_tariff=tariff.value)
    await message.answer(
        "<b>Lira Premium</b>\n"
        "Цифровой тариф — 199 ₽/мес. Без бокса и без опросника.\n\n"
        "После оплаты пришлю код активации — введи его в приложении "
        "Lira на экране «Подписка».",
        parse_mode="HTML",
    )
    sent = await send_invoice(message.bot, message.chat.id, tariff)
    if not sent:
        await message.answer(
            "Платёжный провайдер пока не настроен. Можешь оформить "
            "Premium в тестовом режиме — нажми кнопку ниже, и я пришлю "
            "код активации.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text=f"✅ Оформить за {TARIFF_META[tariff]['price']} ₽ (тест)",
                            callback_data=f"manualpay:{tariff.value}",
                        )
                    ]
                ]
            ),
        )


@router.message(CommandStart())
async def on_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    if message.from_user is not None:
        async with session_scope() as session:
            await get_or_create_user(session, message.from_user)

    await message.answer(
        WELCOME,
        parse_mode="HTML",
        reply_markup=_welcome_keyboard(),
    )


@router.message(Command("help"))
async def on_help(message: Message) -> None:
    await message.answer(
        "Команды:\n"
        "/start — приветствие\n"
        "/setup — пройти / продолжить настройку бокса\n"
        "/mybox — личный кабинет (статус подписки, дата ближайшего бокса)\n"
        "/cancel — отменить текущий ввод"
    )


@router.message(Command("cancel"))
async def on_cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Окей, отменила. Чтобы начать заново — /start.")
