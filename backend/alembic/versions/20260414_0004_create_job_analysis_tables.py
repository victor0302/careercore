"""create job analysis and requirement match tables

Revision ID: 20260414_0004
Revises: 20260413_0003
Create Date: 2026-04-14 09:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260414_0004"
down_revision: str | None = "20260413_0003"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

matchtype = postgresql.ENUM(
    "full",
    "partial",
    "missing",
    name="matchtype",
    create_type=False,
)


def upgrade() -> None:
    matchtype.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "job_analyses",
        sa.Column(
            "job_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("fit_score", sa.Float(), nullable=False),
        sa.Column("score_breakdown", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "analyzed_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.ForeignKeyConstraint(["job_id"], ["job_descriptions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_job_analyses_job_id"),
        "job_analyses",
        ["job_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_job_analyses_user_id"),
        "job_analyses",
        ["user_id"],
        unique=False,
    )

    op.create_table(
        "matched_requirements",
        sa.Column(
            "analysis_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("requirement_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("match_type", matchtype, nullable=False),
        sa.Column("source_entity_type", sa.String(length=100), nullable=False),
        sa.Column("source_entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.ForeignKeyConstraint(["analysis_id"], ["job_analyses.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_matched_requirements_analysis_id"),
        "matched_requirements",
        ["analysis_id"],
        unique=False,
    )

    op.create_table(
        "missing_requirements",
        sa.Column(
            "analysis_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("requirement_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("suggested_action", sa.Text(), nullable=True),
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.ForeignKeyConstraint(["analysis_id"], ["job_analyses.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_missing_requirements_analysis_id"),
        "missing_requirements",
        ["analysis_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_missing_requirements_analysis_id"),
        table_name="missing_requirements",
    )
    op.drop_table("missing_requirements")

    op.drop_index(
        op.f("ix_matched_requirements_analysis_id"),
        table_name="matched_requirements",
    )
    op.drop_table("matched_requirements")

    op.drop_index(op.f("ix_job_analyses_user_id"), table_name="job_analyses")
    op.drop_index(op.f("ix_job_analyses_job_id"), table_name="job_analyses")
    op.drop_table("job_analyses")

    matchtype.drop(op.get_bind(), checkfirst=True)
