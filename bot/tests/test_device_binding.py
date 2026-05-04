"""Tests for the auto-sync device-id flow on the bot side."""
from __future__ import annotations

import pytest

from bot.models import User
from bot.services.users import bind_device_id, is_valid_device_id


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("a" * 32, True),
        ("0123456789abcdef0123456789abcdef", True),
        ("abcd1234", True),  # exactly 8 chars (lower bound)
        ("Aa0._-Zz", True),  # mixed case + allowed punctuation
        ("a" * 64, True),  # upper bound
        ("a" * 65, False),  # too long
        ("abc", False),  # too short
        ("", False),
        ("with space", False),
        ("emoji🌸here", False),
        ("semi;colon", False),
    ],
)
def test_is_valid_device_id(raw: str, expected: bool) -> None:
    assert is_valid_device_id(raw) is expected


@pytest.mark.asyncio
async def test_bind_device_id_sets_column_on_first_call(session) -> None:
    user = User(telegram_id=1)
    session.add(user)
    await session.flush()

    changed = await bind_device_id(session, user, "abcd1234efgh5678")
    assert changed is True
    assert user.device_id == "abcd1234efgh5678"


@pytest.mark.asyncio
async def test_bind_device_id_is_idempotent(session) -> None:
    user = User(telegram_id=1, device_id="abcd1234efgh5678")
    session.add(user)
    await session.flush()

    changed = await bind_device_id(session, user, "abcd1234efgh5678")
    assert changed is False


@pytest.mark.asyncio
async def test_bind_device_id_rejects_invalid_input(session) -> None:
    user = User(telegram_id=1)
    session.add(user)
    await session.flush()

    changed = await bind_device_id(session, user, "bad")
    assert changed is False
    assert user.device_id is None


@pytest.mark.asyncio
async def test_bind_device_id_steals_from_previous_owner(session) -> None:
    """When the same Lira install re-links to a different Telegram
    account, the device id has to move — the unique index would
    otherwise reject the second insert."""
    a = User(telegram_id=1, device_id="abcd1234efgh5678")
    b = User(telegram_id=2)
    session.add_all([a, b])
    await session.flush()

    changed = await bind_device_id(session, b, "abcd1234efgh5678")
    assert changed is True
    assert b.device_id == "abcd1234efgh5678"
    await session.refresh(a)
    assert a.device_id is None
