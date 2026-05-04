"""Admin notifications for Lira BOX onboarding & sales flow."""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from html import escape
from typing import TYPE_CHECKING, Mapping, Sequence

from bot.config import get_settings

if TYPE_CHECKING:
    from aiogram import Bot
    from aiogram.types import User as TGUser

    from bot.models import Profile

log = logging.getLogger(__name__)


# Russian month names in genitive case (for "5 марта" style dates).
_RU_MONTHS_GEN = (
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
)


def _ru_date(d: date) -> str:
    """Format a date as `5 марта 2026` (genitive month, RU)."""
    return f"{d.day} {_RU_MONTHS_GEN[d.month - 1]} {d.year}"


def _format_cycle_window(
    last_period_start: date | None,
    cycle_length_days: int | None,
    period_length_days: int | None,
) -> tuple[str | None, str | None]:
    """Return (period_window, cycle_window) — Russian date-range strings.

    `period_window`: dates the user is bleeding (e.g. "5 марта — 9 марта 2026").
    `cycle_window`: full cycle from last period start to the day before the
    next expected period (e.g. "5 марта — 1 апреля 2026").
    Either entry is None when the underlying field is missing — admin
    string falls back to the legacy `28 дн., месячные 5 дн.` line.
    """
    period: str | None = None
    cycle: str | None = None
    if last_period_start and period_length_days:
        end = last_period_start + timedelta(days=max(period_length_days - 1, 0))
        period = f"{_ru_date(last_period_start)} — {_ru_date(end)}"
    if last_period_start and cycle_length_days:
        end = last_period_start + timedelta(days=max(cycle_length_days - 1, 0))
        cycle = f"{_ru_date(last_period_start)} — {_ru_date(end)}"
    return period, cycle


# Human labels for option ids stored on Profile.
PADS_LABELS: Mapping[str, str] = {
    "pads-always-ultra-normal": "Always Ultra Normal",
    "pads-kotex-young-normal": "Kotex Young Normal",
    "pads-naturella-camomile": "Naturella Camomile",
    "pads-libresse-invisible": "Libresse Invisible",
    "pads-natracare-organic": "Natracare Organic",
}
TAMPONS_LABELS: Mapping[str, str] = {
    "tampons-tampax-compak-normal": "Tampax Compak Normal",
    "tampons-ob-procomfort-mini": "o.b. ProComfort Mini",
    "tampons-kotex-click-super": "Kotex Click Super",
}
OTHER_HYGIENE_LABELS: Mapping[str, str] = {
    "cup": "Менструальные чаши",
    "panties": "Менструальные трусы",
}
FLOW_HEAVINESS_LABELS: Mapping[str, str] = {
    "light": "Скудные",
    "normal": "Средние",
    "heavy": "Обильные",
    "very_heavy": "Очень обильные",
    "variable": "По-разному",
}
ALLERGIES_LABELS: Mapping[str, str] = {
    "chocolate": "Шоколад",
    "nuts": "Орехи",
    "gluten": "Глютен",
    "lactose": "Лактоза",
    "essential_oils": "Эфирные масла",
    "fragrance": "Ароматизаторы",
    "latex": "Латекс",
}
DIETS_LABELS: Mapping[str, str] = {
    "normal": "Обычное",
    "healthy": "ПП",
    "vegetarian": "Вегетарианство",
    "vegan": "Веганство",
    "no_sugar": "Без сахара",
}
GOALS_LABELS: Mapping[str, str] = {
    "lose": "Худею",
    "maintain": "Поддерживаю",
    "gain": "Набираю",
    "just_care": "Просто забочусь о себе",
}
JOYS_LABELS: Mapping[str, str] = {
    "sweets": "Сладкое",
    "tea": "Чай",
    "face_care": "Уход за лицом",
    "body_care": "Уход за телом",
    "small_things": "Мелочи (свечи, носки)",
    "books": "Книги",
}
SEASONS_LABELS: Mapping[str, str] = {
    "winter": "Зима",
    "spring": "Весна",
    "summer": "Лето",
    "autumn": "Осень",
}
CALMING_LABELS: Mapping[str, str] = {
    "bath": "Ванна",
    "tea": "Чай",
    "silence": "Тишина",
    "hugs": "Объятия",
    "food": "Еда",
    "sport": "Спорт",
}
OCCUPATIONS_LABELS: Mapping[str, str] = {
    "office": "Офис / удалёнка",
    "active": "Активная работа",
    "home": "Дома / декрет",
    "studying": "Учусь",
}


def _h(value: str | None) -> str:
    return escape(value) if value else "—"


def _list(values: Sequence[str] | None, labels: Mapping[str, str]) -> str:
    if not values:
        return "—"
    return ", ".join(escape(labels.get(v, v)) for v in values)


def _label(value: str | None, labels: Mapping[str, str]) -> str:
    if not value:
        return "—"
    return escape(labels.get(value, value))


def _user_link(user_tg: "TGUser") -> str:
    name = user_tg.first_name or user_tg.username or str(user_tg.id)
    handle = f"@{user_tg.username}" if user_tg.username else ""
    return (
        f"<a href='tg://user?id={user_tg.id}'>{escape(name)}</a>"
        + (f" {escape(handle)}" if handle else "")
        + f" • <code>{user_tg.id}</code>"
    )


def format_full_profile(user_tg: "TGUser", profile: "Profile") -> str:
    """HTML digest of every answer the client gave during the questionnaire."""
    lines: list[str] = []
    lines.append("📋 <b>Новая анкета Lira BOX</b>")
    lines.append(_user_link(user_tg))
    lines.append("")
    lines.append("<b>Шаг 1. Профиль</b>")
    lines.append(f"• Имя: {_h(profile.name)}")
    lines.append(
        "• Год рождения: "
        + (str(profile.birth_year) if profile.birth_year else "—")
    )
    lines.append(f"• Город: {_h(profile.city)}")
    if profile.cycle_sync_code:
        lines.append(
            f"• Код синхронизации: <code>{escape(profile.cycle_sync_code)}</code> "
            "(расшифрован)"
        )
    elif profile.flow_app_code:
        lines.append(f"• Код Lira: <code>{escape(profile.flow_app_code)}</code>")
    period_window, cycle_window = _format_cycle_window(
        profile.last_period_start,
        profile.cycle_length_days,
        profile.period_length_days,
    )
    if period_window:
        lines.append(f"• Месячные: <b>{escape(period_window)}</b>")
    elif profile.last_period_start:
        # Fall back to a single-day line if we don't know the period
        # length — better than dropping the date entirely.
        lines.append(
            f"• Последние месячные: <b>{escape(_ru_date(profile.last_period_start))}</b>"
        )
    if cycle_window:
        lines.append(
            f"• Цикл: <b>{escape(cycle_window)}</b> "
            f"({profile.cycle_length_days} дн.)"
        )
    else:
        lines.append(
            f"• Цикл: {profile.cycle_length_days or '—'} дн., "
            f"месячные {profile.period_length_days or '—'} дн."
        )
    lines.append("")
    lines.append("<b>Шаг 2. Гигиена</b>")
    lines.append(f"• Прокладки: {_list(profile.hygiene_pads, PADS_LABELS)}")
    lines.append(f"• Тампоны: {_list(profile.hygiene_tampons, TAMPONS_LABELS)}")
    lines.append(
        f"• Чаши/трусы: {_list(profile.hygiene_other, OTHER_HYGIENE_LABELS)}"
    )
    lines.append(
        f"• Обильность: {_label(profile.flow_heaviness, FLOW_HEAVINESS_LABELS)}"
    )
    lines.append("")
    lines.append("<b>Шаг 3. Аллергии и кожа</b>")
    lines.append(f"• Аллергии: {_list(profile.allergies, ALLERGIES_LABELS)}")
    sensitive = (
        "да" if profile.sensitive_skin is True else "нет"
        if profile.sensitive_skin is False else "—"
    )
    lines.append(f"• Чувствительная кожа: {sensitive}")
    if profile.allergy_notes:
        lines.append(f"• Заметки: {escape(profile.allergy_notes)}")
    lines.append("")
    lines.append("<b>Шаг 4. Образ жизни</b>")
    lines.append(f"• Питание: {_label(profile.diet, DIETS_LABELS)}")
    lines.append(f"• Цель: {_label(profile.goal, GOALS_LABELS)}")
    lines.append(f"• Радует: {_list(profile.joys, JOYS_LABELS)}")
    lines.append(
        "• Любовь к новинкам: "
        + (f"{profile.novelty_score}/5" if profile.novelty_score else "—")
    )
    if profile.dislikes:
        lines.append(f"• Не любит: {escape(profile.dislikes)}")
    lines.append("")
    lines.append("<b>Шаг 5. Глубинные предпочтения</b>")
    lines.append(
        f"• Любимый сезон: {_label(profile.favorite_season, SEASONS_LABELS)}"
    )
    lines.append(f"• Успокаивает: {_list(profile.calming, CALMING_LABELS)}")
    lines.append(
        f"• Род деятельности: {_label(profile.occupation, OCCUPATIONS_LABELS)}"
    )
    if profile.hobbies:
        lines.append(f"• Хобби: {escape(profile.hobbies)}")
    lines.append("")
    lines.append("<b>Шаг 6. Адрес доставки</b>")
    lines.append(f"• Страна: {_h(profile.address_country)}")
    lines.append(f"• Город: {_h(profile.address_city)}")
    lines.append(f"• Улица: {_h(profile.address_street)}")
    lines.append(
        f"• Дом / кв.: {_h(profile.address_building)} / {_h(profile.address_apartment)}"
    )
    lines.append(f"• Индекс: {_h(profile.address_postal)}")
    lines.append(f"• Телефон: {_h(profile.address_phone)}")
    lines.append("")
    lines.append(
        "<i>"
        + escape(datetime.now().strftime("%d.%m.%Y %H:%M"))
        + " • анкета завершена, ждём оплату</i>"
    )
    return "\n".join(lines)


async def notify_admin_full_profile(
    bot: "Bot", user_tg: "TGUser", profile: "Profile"
) -> None:
    settings = get_settings()
    if not settings.admin_chat_id:
        log.info("ADMIN_CHAT_ID not set — skipping full-profile notification")
        return
    text = format_full_profile(user_tg, profile)
    try:
        await bot.send_message(
            settings.admin_chat_id,
            text,
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
    except Exception:  # noqa: BLE001
        log.exception("Failed to send full-profile admin notification")


async def notify_admin_step(
    bot: "Bot", user_tg: "TGUser", *, step_index: int, step_title: str
) -> None:
    settings = get_settings()
    if not settings.admin_chat_id:
        return
    text = (
        f"➡️ {_user_link(user_tg)} закончила <b>шаг {step_index}/7</b> — "
        f"{escape(step_title)}"
    )
    try:
        await bot.send_message(
            settings.admin_chat_id,
            text,
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
    except Exception:  # noqa: BLE001
        log.exception("Failed to send step-progress admin notification")
