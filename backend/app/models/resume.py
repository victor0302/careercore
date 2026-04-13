"""Resume, resume versions, bullets, and evidence links."""

import uuid

from sqlalchemy import Boolean, Float, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Resume(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "resumes"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("job_descriptions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Relationships
    user: Mapped["User"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "User", back_populates="resumes"
    )
    job: Mapped["JobDescription | None"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "JobDescription", back_populates="resumes"
    )
    versions: Mapped[list["ResumeVersion"]] = relationship(
        "ResumeVersion", back_populates="resume", cascade="all, delete-orphan"
    )
    bullets: Mapped[list["ResumeBullet"]] = relationship(
        "ResumeBullet", back_populates="resume", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Resume id={self.id} user_id={self.user_id}>"


class ResumeVersion(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "resume_versions"

    resume_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("resumes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    fit_score_at_gen: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Relationship
    resume: Mapped["Resume"] = relationship("Resume", back_populates="versions")

    def __repr__(self) -> str:
        return f"<ResumeVersion id={self.id} resume_id={self.resume_id}>"


class ResumeBullet(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "resume_bullets"

    resume_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("resumes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    is_ai_generated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_approved: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Relationships
    resume: Mapped["Resume"] = relationship("Resume", back_populates="bullets")
    evidence_links: Mapped[list["EvidenceLink"]] = relationship(
        "EvidenceLink", back_populates="bullet", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<ResumeBullet id={self.id} approved={self.is_approved}>"


class EvidenceLink(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "evidence_links"

    bullet_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("resume_bullets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_entity_type: Mapped[str] = mapped_column(String(100), nullable=False)
    source_entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    # Relationship
    bullet: Mapped["ResumeBullet"] = relationship("ResumeBullet", back_populates="evidence_links")

    def __repr__(self) -> str:
        return (
            f"<EvidenceLink bullet_id={self.bullet_id} "
            f"source={self.source_entity_type}:{self.source_entity_id}>"
        )


from app.models.user import User  # noqa: E402, F401
from app.models.job_description import JobDescription  # noqa: E402, F401
