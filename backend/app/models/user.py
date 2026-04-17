"""User model — authentication root entity."""

import enum
import uuid

from sqlalchemy import Boolean, Enum, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class UserTier(str, enum.Enum):
    free = "free"
    standard = "standard"


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    tier: Mapped[UserTier] = mapped_column(
        Enum(UserTier, name="usertier"),
        default=UserTier.free,
        nullable=False,
    )

    # Relationships
    profile: Mapped["Profile"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "Profile", back_populates="user", uselist=False, lazy="select"
    )
    job_descriptions: Mapped[list["JobDescription"]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "JobDescription", back_populates="user", lazy="select"
    )
    resumes: Mapped[list["Resume"]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "Resume", back_populates="user", lazy="select"
    )
    ai_call_logs: Mapped[list["AICallLog"]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "AICallLog",
        back_populates="user",
        lazy="select",
        primaryjoin="User.id == foreign(AICallLog.user_id)",
        viewonly=True,
    )
    uploaded_files: Mapped[list["UploadedFile"]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "UploadedFile", back_populates="user", lazy="select"
    )
    refresh_tokens: Mapped[list["RefreshToken"]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "RefreshToken", back_populates="user", lazy="select"
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email!r} tier={self.tier}>"


# Imported here to avoid circular references at module level
from app.models.profile import Profile  # noqa: E402, F401
from app.models.job_description import JobDescription  # noqa: E402, F401
from app.models.resume import Resume  # noqa: E402, F401
from app.models.ai_call_log import AICallLog  # noqa: E402, F401
from app.models.refresh_token import RefreshToken  # noqa: E402, F401
from app.models.uploaded_file import UploadedFile  # noqa: E402, F401
