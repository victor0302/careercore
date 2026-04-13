"""Master profile — the career data graph for a user."""

import uuid

from sqlalchemy import Float, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Profile(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    current_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    target_domain: Mapped[str | None] = mapped_column(String(255), nullable=True)
    summary_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    completeness_pct: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    # Relationships
    user: Mapped["User"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "User", back_populates="profile"
    )
    work_experiences: Mapped[list["WorkExperience"]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "WorkExperience", back_populates="profile", cascade="all, delete-orphan"
    )
    projects: Mapped[list["Project"]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "Project", back_populates="profile", cascade="all, delete-orphan"
    )
    skills: Mapped[list["Skill"]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "Skill", back_populates="profile", cascade="all, delete-orphan"
    )
    certifications: Mapped[list["Certification"]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "Certification", back_populates="profile", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Profile id={self.id} user_id={self.user_id} completeness={self.completeness_pct:.0%}>"


from app.models.user import User  # noqa: E402, F401
from app.models.work_experience import WorkExperience  # noqa: E402, F401
from app.models.project import Project  # noqa: E402, F401
from app.models.skill import Skill  # noqa: E402, F401
from app.models.certification import Certification  # noqa: E402, F401
