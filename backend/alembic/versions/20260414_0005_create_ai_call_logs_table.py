"""create ai_call_logs table

Revision ID: 20260414_0005
Revises: 20260414_0004
Create Date: 2026-04-14 10:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260414_0005"
down_revision: str | None = "20260414_0004"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

# user_id carries NO FK constraint — logs must survive user deletion for
# billing and audit purposes (see ADR-012 / AICallLog model comment).
aicalltype = postgresql.ENUM(
    "parse_job_description",
    "generate_bullets",
    "explain_score",
    "answer_followup",
    "generate_recommendations",
    "generate_learning_plan",
    name="aicalltype",
    create_type=False,
)


def upgrade() -> None:
    aicalltype.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "ai_call_logs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        # No ForeignKeyConstraint on user_id — intentional.
        # AI call logs are immutable audit/billing records.  Deleting a user
        # must not cascade-delete their cost history.
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("call_type", aicalltype, nullable=False),
        sa.Column("model", sa.String(length=100), nullable=False),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False),
        sa.Column("completion_tokens", sa.Integer(), nullable=False),
        sa.Column("total_tokens", sa.Integer(), nullable=False),
        sa.Column("cost_usd", sa.Numeric(10, 6), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ai_call_logs_user_created",
        "ai_call_logs",
        ["user_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_ai_call_logs_user_created", table_name="ai_call_logs")
    op.drop_table("ai_call_logs")
    aicalltype.drop(op.get_bind(), checkfirst=True)
