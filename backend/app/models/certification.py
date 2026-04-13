"""Certification / credential entry linked to a user's master profile."""

import uuid
from datetime import date

from sqlalchemy import Date, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Certification(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "certifications"

    profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    issuer: Mapped[str | None] = mapped_column(String(255), nullable=True)
    issued_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    expiry_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    credential_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    credential_url: Mapped[str | None] = mapped_column(String(512), nullable=True)

    # Relationship
    profile: Mapped["Profile"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "Profile", back_populates="certifications"
    )

    def __repr__(self) -> str:
        return f"<Certification id={self.id} name={self.name!r} issuer={self.issuer!r}>"


from app.models.profile import Profile  # noqa: E402, F401
