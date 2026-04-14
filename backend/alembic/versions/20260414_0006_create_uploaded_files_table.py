"""create uploaded_files table

Revision ID: 20260414_0006
Revises: 20260414_0005
Create Date: 2026-04-14 11:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260414_0006"
down_revision: str | None = "20260414_0005"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

filestatus = postgresql.ENUM(
    "pending",
    "processing",
    "ready",
    "error",
    name="filestatus",
    create_type=False,
)


def upgrade() -> None:
    filestatus.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "uploaded_files",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("original_filename", sa.String(length=512), nullable=False),
        sa.Column("content_type", sa.String(length=128), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("storage_key", sa.String(length=1024), nullable=False, unique=True),
        sa.Column(
            "status",
            filestatus,
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column("extracted_text", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
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
        op.f("ix_uploaded_files_user_id"),
        "uploaded_files",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_uploaded_files_user_id"), table_name="uploaded_files")
    op.drop_table("uploaded_files")
    filestatus.drop(op.get_bind(), checkfirst=True)
