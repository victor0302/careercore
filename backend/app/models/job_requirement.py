"""Job requirement parsed from a job description."""

import enum
import uuid

from sqlalchemy import Boolean, Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UUIDPrimaryKeyMixin


class JobRequirementCategory(str, enum.Enum):
    skill = "skill"
    experience = "experience"
    education = "education"
    tool = "tool"
    domain = "domain"


class JobRequirement(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "job_requirements"

    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("job_descriptions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    requirement_text: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[JobRequirementCategory] = mapped_column(
        Enum(JobRequirementCategory, name="jobrequirementcategory"),
        nullable=False,
    )
    is_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    job: Mapped["JobDescription"] = relationship(
        "JobDescription",
        back_populates="requirements",
    )

    def __repr__(self) -> str:
        return (
            f"<JobRequirement id={self.id} category={self.category.value!r} "
            f"required={self.is_required}>"
        )


from app.models.job_description import JobDescription  # noqa: E402, F401
