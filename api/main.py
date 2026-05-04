"""FastAPI app exposing /v1/activate for the Flow mobile/web app.

The bot writes activation_codes after a paid subscription; the app
posts the user-entered code here. We return validity, tariff, and
expiry so the app can flip the local subscription banner.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import AsyncIterator

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, text

from bot.config import get_settings
from bot.db import engine, session_scope
from bot.models import ActivationCode, Base, Subscription, User
from bot.services.catalog import seed_catalog
from bot.services.codes import redeem_code
from bot.services.users import is_valid_device_id

log = logging.getLogger("flowcare-api")
logging.basicConfig(level=logging.INFO)


async def _ensure_user_device_id_column(conn) -> None:
    """Pre-Alembic safety net: add the `users.device_id` column on existing
    dev DBs that were created by `Base.metadata.create_all` before the
    column landed. This is a no-op on fresh DBs (the column is part of the
    model) and on DBs that already have it. Once Alembic migrations land
    in production this can be removed.
    """
    dialect = conn.dialect.name
    try:
        if dialect == "sqlite":
            rows = await conn.execute(
                text("SELECT name FROM pragma_table_info('users')")
            )
            cols = {r[0] for r in rows}
            if "device_id" not in cols:
                await conn.execute(
                    text("ALTER TABLE users ADD COLUMN device_id VARCHAR(64)")
                )
                await conn.execute(
                    text(
                        "CREATE UNIQUE INDEX IF NOT EXISTS "
                        "ix_users_device_id ON users(device_id)"
                    )
                )
        else:  # postgres / others
            await conn.execute(
                text(
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS "
                    "device_id VARCHAR(64)"
                )
            )
            await conn.execute(
                text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS "
                    "ix_users_device_id ON users(device_id)"
                )
            )
    except Exception:  # noqa: BLE001
        log.exception("Failed to ensure users.device_id column")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await _ensure_user_device_id_column(conn)
    async with session_scope() as session:
        await seed_catalog(session)
    yield


app = FastAPI(
    title="FlowCare Activation API",
    version="1.0.0",
    description="Validates activation codes issued by the FlowCare Telegram bot.",
    lifespan=lifespan,
)


class ActivateIn(BaseModel):
    code: str = Field(..., min_length=4, max_length=16)
    device_id: str | None = Field(default=None, max_length=64)


class ActivateOut(BaseModel):
    valid: bool
    tariff: str | None = None
    expires: str | None = None
    redeemed_at: str | None = None


class SubscriptionOut(BaseModel):
    tier: str
    expires: str
    started_at: str
    activation_code: str | None = None
    redeemed_at: str | None = None


@app.post("/v1/activate", response_model=ActivateOut)
async def activate(body: ActivateIn) -> ActivateOut:
    async with session_scope() as session:
        result = await redeem_code(session, body.code, device_id=body.device_id)
    if result is None:
        return ActivateOut(valid=False)
    code, sub = result
    return ActivateOut(
        valid=True,
        tariff=sub.tariff.value,
        expires=sub.expires_at.date().isoformat(),
        redeemed_at=(code.redeemed_at.isoformat() if code.redeemed_at else None),
    )


def _is_active(sub: Subscription, now: datetime) -> bool:
    expires = sub.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    return expires >= now and sub.status == "active"


@app.get("/v1/subscription/by-device/{device_id}", response_model=SubscriptionOut)
async def subscription_by_device(device_id: str) -> SubscriptionOut:
    """Auto-sync entry point.

    Returns the latest active subscription for the user that has bound
    this device id via `/start link_<id>` or `/start premium_<id>`.

    Side-effect: when the matching subscription has an activation code
    that nobody has redeemed yet, we redeem it on this device's behalf
    so the bot's `/mybox` reflects the linkage and we don't leave a
    floating one-shot code lying around.
    """
    if not is_valid_device_id(device_id):
        raise HTTPException(status_code=400, detail="invalid_device_id")
    now = datetime.now(timezone.utc)
    async with session_scope() as session:
        user = (
            await session.execute(
                select(User).where(User.device_id == device_id)
            )
        ).scalar_one_or_none()
        if user is None:
            raise HTTPException(status_code=404, detail="device_not_bound")
        subs = (
            await session.execute(
                select(Subscription)
                .where(Subscription.user_id == user.id)
                .order_by(Subscription.expires_at.desc())
            )
        ).scalars().all()
        active = next((s for s in subs if _is_active(s, now)), None)
        if active is None:
            raise HTTPException(status_code=404, detail="no_active_subscription")
        code = (
            await session.execute(
                select(ActivationCode).where(
                    ActivationCode.subscription_id == active.id
                )
            )
        ).scalar_one_or_none()
        # Auto-redeem so the bot's /mybox reflects the device linkage.
        if code is not None and code.redeemed_at is None:
            code.redeemed_at = now
            code.redeemed_by_device = device_id
        expires_iso = active.expires_at.date().isoformat()
        started_iso = active.started_at.date().isoformat()
        return SubscriptionOut(
            tier=active.tariff.value,
            expires=expires_iso,
            started_at=started_iso,
            activation_code=(code.code if code is not None else None),
            redeemed_at=(code.redeemed_at.isoformat() if code and code.redeemed_at else None),
        )


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


def run() -> None:  # pragma: no cover
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "api.main:app", host=settings.api_host, port=settings.api_port, reload=False
    )
