"""End-to-end test of the auto-sync API endpoint.

Spins up a fresh in-memory SQLite, monkey-patches the bot.db engine to
point at it, then drives the FastAPI app via httpx.AsyncClient. We
test the happy path (active subscription is returned + activation code
auto-redeemed) and the failure paths the app's UI branches on.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import api.main as api_main
import bot.db as bot_db
from bot.models import ActivationCode, Base, Subscription, Tariff, User


@pytest_asyncio.fixture
async def app_client(monkeypatch):
    """Replace the global engine + sessionmaker with an isolated SQLite
    instance and yield (client, Session) that talk to the FastAPI app
    against that DB. We intentionally bypass the FastAPI lifespan event
    so the engine binding stays under test control.
    """
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)

    monkeypatch.setattr(bot_db, "engine", engine, raising=True)
    monkeypatch.setattr(bot_db, "SessionLocal", Session, raising=True)
    monkeypatch.setattr(api_main, "engine", engine, raising=False)

    transport = ASGITransport(app=api_main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, Session

    await engine.dispose()


@pytest.mark.asyncio
async def test_returns_404_when_device_unknown(app_client) -> None:
    client, _ = app_client
    res = await client.get("/v1/subscription/by-device/abcd1234efgh5678")
    assert res.status_code == 404
    assert res.json()["detail"] == "device_not_bound"


@pytest.mark.asyncio
async def test_returns_400_for_malformed_device_id(app_client) -> None:
    client, _ = app_client
    res = await client.get("/v1/subscription/by-device/bad")
    assert res.status_code == 400
    assert res.json()["detail"] == "invalid_device_id"


@pytest.mark.asyncio
async def test_returns_404_when_user_has_no_active_subscription(app_client) -> None:
    client, Session = app_client
    async with Session() as s:
        s.add(User(telegram_id=1, device_id="abcd1234efgh5678"))
        await s.commit()
    res = await client.get("/v1/subscription/by-device/abcd1234efgh5678")
    assert res.status_code == 404
    assert res.json()["detail"] == "no_active_subscription"


@pytest.mark.asyncio
async def test_returns_active_subscription_and_redeems_code(app_client) -> None:
    client, Session = app_client
    expires = datetime.now(timezone.utc) + timedelta(days=20)
    async with Session() as s:
        user = User(telegram_id=1, device_id="abcd1234efgh5678")
        s.add(user)
        await s.flush()
        sub = Subscription(
            user_id=user.id,
            tariff=Tariff.PREMIUM,
            status="active",
            started_at=datetime.now(timezone.utc) - timedelta(days=10),
            expires_at=expires,
        )
        s.add(sub)
        await s.flush()
        code = ActivationCode(
            code="A7K9TXM2",
            user_id=user.id,
            subscription_id=sub.id,
        )
        s.add(code)
        await s.commit()

    res = await client.get("/v1/subscription/by-device/abcd1234efgh5678")
    assert res.status_code == 200
    body = res.json()
    assert body["tier"] == "premium"
    assert body["expires"] == expires.date().isoformat()
    assert body["activation_code"] == "A7K9TXM2"
    assert body["redeemed_at"] is not None

    # Confirm the side-effect: the activation code was auto-redeemed.
    async with Session() as s:
        stored = (
            await s.execute(select(ActivationCode).where(ActivationCode.code == "A7K9TXM2"))
        ).scalar_one()
        assert stored.redeemed_at is not None
        assert stored.redeemed_by_device == "abcd1234efgh5678"


@pytest.mark.asyncio
async def test_picks_latest_subscription_when_multiple_exist(app_client) -> None:
    client, Session = app_client
    now = datetime.now(timezone.utc)
    async with Session() as s:
        user = User(telegram_id=1, device_id="abcd1234efgh5678")
        s.add(user)
        await s.flush()
        # Older expired sub
        s.add(
            Subscription(
                user_id=user.id,
                tariff=Tariff.BASIC,
                status="expired",
                started_at=now - timedelta(days=120),
                expires_at=now - timedelta(days=10),
            )
        )
        # Newer active sub
        s.add(
            Subscription(
                user_id=user.id,
                tariff=Tariff.VIP,
                status="active",
                started_at=now - timedelta(days=5),
                expires_at=now + timedelta(days=25),
            )
        )
        await s.commit()

    res = await client.get("/v1/subscription/by-device/abcd1234efgh5678")
    assert res.status_code == 200
    assert res.json()["tier"] == "vip"
