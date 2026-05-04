from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bot.models.base import Base

if TYPE_CHECKING:
    from bot.models.profile import Profile
    from bot.models.subscription import Subscription
    from bot.models.activation_code import ActivationCode


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    username: Mapped[str | None] = mapped_column(String(64))
    first_name: Mapped[str | None] = mapped_column(String(128))
    language_code: Mapped[str | None] = mapped_column(String(8))
    # Auto-sync: device_id stamped by the Lira app via /start link_<id> or
    # /start premium_<id>. Lets the API resolve the user (and its latest
    # subscription) without the manual 8-char activation code.
    device_id: Mapped[str | None] = mapped_column(
        String(64), unique=True, index=True
    )

    profile: Mapped["Profile | None"] = relationship(
        "Profile", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    subscriptions: Mapped[list["Subscription"]] = relationship(
        "Subscription", back_populates="user", cascade="all, delete-orphan"
    )
    activation_codes: Mapped[list["ActivationCode"]] = relationship(
        "ActivationCode", back_populates="user", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<User id={self.id} tg={self.telegram_id} @{self.username}>"
