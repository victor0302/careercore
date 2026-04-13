"""Project entry linked to a user's master profile."""

import uuid

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Project(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "projects"

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

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description_raw: Mapped[str | None] = mapped_column(Text, nullable=True)
    url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    bullets: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    skill_tags: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)
    tool_tags: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)
    domain_tags: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)

    # Relationships
    profile: Mapped["Profile"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "Profile", back_populates="projects"
    )
    source_file: Mapped["UploadedFile | None"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "UploadedFile", foreign_keys=[source_file_id]
    )

    def __repr__(self) -> str:
        return f"<Project id={self.id} name={self.name!r}>"


from app.models.profile import Profile  # noqa: E402, F401
from app.models.uploaded_file import UploadedFile  # noqa: E402, F401
