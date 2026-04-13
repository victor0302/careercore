"""Job description — raw text pasted or uploaded by the user."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class JobDescription(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "job_descriptions"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    company: Mapped[str | None] = mapped_column(String(255), nullable=True)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    parsed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    user: Mapped["User"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "User", back_populates="job_descriptions"
    )
    analyses: Mapped[list["JobAnalysis"]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "JobAnalysis", back_populates="job", cascade="all, delete-orphan"
    )
    resumes: Mapped[list["Resume"]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "Resume", back_populates="job"
    )

    def __repr__(self) -> str:
        return f"<JobDescription id={self.id} title={self.title!r} company={self.company!r}>"


from app.models.user import User  # noqa: E402, F401
from app.models.job_analysis import JobAnalysis  # noqa: E402, F401
from app.models.resume import Resume  # noqa: E402, F401
