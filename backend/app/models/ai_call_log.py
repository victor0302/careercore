"""AI call log — immutable record of every LLM invocation."""

import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, Enum, Float, Index, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class AICallType(str, enum.Enum):
    parse_job_description = "parse_job_description"
    generate_bullets = "generate_bullets"
    explain_score = "explain_score"
    answer_followup = "answer_followup"
    generate_recommendations = "generate_recommendations"
    generate_learning_plan = "generate_learning_plan"


class AICallLog(Base):
    __tablename__ = "ai_call_logs"
    __table_args__ = (Index("ix_ai_call_logs_user_created", "user_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        # Not a FK so logs survive user deletion — important for billing/audit
        nullable=False,
    )
    call_type: Mapped[AICallType] = mapped_column(
        Enum(AICallType, name="aicalltype"), nullable=False
    )
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost_usd: Mapped[float] = mapped_column(Numeric(10, 6), nullable=False, default=0.0)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False)

    # Soft relationship — not enforced at DB level so deleting a user keeps logs
    user: Mapped["User"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "User",
        back_populates="ai_call_logs",
        foreign_keys=[user_id],
        primaryjoin="AICallLog.user_id == User.id",
    )

    def __repr__(self) -> str:
        return (
            f"<AICallLog id={self.id} type={self.call_type} "
            f"tokens={self.total_tokens} success={self.success}>"
        )


from app.models.user import User  # noqa: E402, F401
