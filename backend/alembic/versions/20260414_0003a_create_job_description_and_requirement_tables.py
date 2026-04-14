"""create job description and job requirement tables

Revision ID: 20260414_0003a
Revises: 20260413_0003
Create Date: 2026-04-14 13:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260414_0003a"
down_revision: str | None = "20260413_0003"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

jobrequirementcategory = postgresql.ENUM(
    "skill",
    "experience",
    "education",
    "tool",
    "domain",
    name="jobrequirementcategory",
    create_type=False,
)


def upgrade() -> None:
    jobrequirementcategory.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "job_descriptions",
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("company", sa.String(length=255), nullable=True),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("parsed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_job_descriptions_user_id"),
        "job_descriptions",
        ["user_id"],
        unique=False,
    )

    op.create_table(
        "job_requirements",
        sa.Column(
            "job_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("requirement_text", sa.Text(), nullable=False),
        sa.Column("category", jobrequirementcategory, nullable=False),
        sa.Column(
            "is_required",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.ForeignKeyConstraint(["job_id"], ["job_descriptions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_job_requirements_job_id"),
        "job_requirements",
        ["job_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_job_requirements_job_id"), table_name="job_requirements")
    op.drop_table("job_requirements")

    op.drop_index(op.f("ix_job_descriptions_user_id"), table_name="job_descriptions")
    op.drop_table("job_descriptions")

    jobrequirementcategory.drop(op.get_bind(), checkfirst=True)
