"""Job analysis, matched requirements, and missing requirements."""

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class MatchType(str, enum.Enum):
    full = "full"
    partial = "partial"
    missing = "missing"


class JobAnalysis(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "job_analyses"

    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("job_descriptions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    fit_score: Mapped[float] = mapped_column(Float, nullable=False)
    score_breakdown: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    analyzed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    # Relationships
    job: Mapped["JobDescription"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "JobDescription", back_populates="analyses"
    )
    matched_requirements: Mapped[list["MatchedRequirement"]] = relationship(
        "MatchedRequirement", back_populates="analysis", cascade="all, delete-orphan"
    )
    missing_requirements: Mapped[list["MissingRequirement"]] = relationship(
        "MissingRequirement", back_populates="analysis", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<JobAnalysis id={self.id} fit_score={self.fit_score:.2f}>"


class MatchedRequirement(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "matched_requirements"

    analysis_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("job_analyses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    requirement_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    match_type: Mapped[MatchType] = mapped_column(
        Enum(MatchType, name="matchtype"), nullable=False
    )
    source_entity_type: Mapped[str] = mapped_column(String(100), nullable=False)
    source_entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)

    # Relationships
    analysis: Mapped["JobAnalysis"] = relationship(
        "JobAnalysis", back_populates="matched_requirements"
    )


class MissingRequirement(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "missing_requirements"

    analysis_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("job_analyses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    requirement_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    suggested_action: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    analysis: Mapped["JobAnalysis"] = relationship(
        "JobAnalysis", back_populates="missing_requirements"
    )


from app.models.job_description import JobDescription  # noqa: E402, F401
