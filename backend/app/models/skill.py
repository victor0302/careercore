"""Skill entry linked to a user's master profile."""

import uuid

from sqlalchemy import Float, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Skill(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "skills"

    profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    proficiency_level: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )  # e.g. beginner/intermediate/expert
    years_of_experience: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Relationship
    profile: Mapped["Profile"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "Profile", back_populates="skills"
    )

    def __repr__(self) -> str:
        return f"<Skill id={self.id} name={self.name!r}>"


from app.models.profile import Profile  # noqa: E402, F401
