"""Shared fixtures for the bot test suite.

Forces the SQLAlchemy engine onto a fresh in-memory aiosqlite DB and
stubs out env-vars that bot.config requires, so test runs are
hermetic and don't need a real BOT_TOKEN.
"""
from __future__ import annotations

import os

# Must be set before bot.config / bot.db are imported anywhere.
os.environ.setdefault("BOT_TOKEN", "test-token")
os.environ.setdefault("ADMIN_CHAT_ID", "0")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

import pytest_asyncio  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402

from bot.models import Base  # noqa: E402


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as s:
        yield s
    await engine.dispose()
