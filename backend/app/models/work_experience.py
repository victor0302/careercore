"""Work experience entry linked to a user's master profile."""

import uuid
from datetime import date

from sqlalchemy import Boolean, Date, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class WorkExperience(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "work_experiences"

    profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_file_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("uploaded_files.id", ondelete="SET NULL"),
        nullable=True,
    )

    employer: Mapped[str] = mapped_column(String(255), nullable=False)
    role_title: Mapped[str] = mapped_column(String(255), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_current: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    description_raw: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Structured AI-extracted data
    bullets: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    skill_tags: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)
    tool_tags: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)
    domain_tags: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)

    # Relationships
    profile: Mapped["Profile"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "Profile", back_populates="work_experiences"
    )
    source_file: Mapped["UploadedFile | None"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "UploadedFile", foreign_keys=[source_file_id]
    )

    def __repr__(self) -> str:
        return f"<WorkExperience id={self.id} role={self.role_title!r} employer={self.employer!r}>"


from app.models.profile import Profile  # noqa: E402, F401
from app.models.uploaded_file import UploadedFile  # noqa: E402, F401
