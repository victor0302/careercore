"""create audit_logs table

Revision ID: 20260414_0007
Revises: 20260414_0006
Create Date: 2026-04-14 12:00:00.000000

APPEND-ONLY TABLE — DO NOT UPDATE OR DELETE ROWS FROM APPLICATION CODE.
All writes must go through AuditService.log_event().  Direct INSERT, UPDATE,
or DELETE statements against audit_logs outside of the service are prohibited
and must be caught in code review.  A PostgreSQL INSERT-only role and row-level
security policy are Phase 2 hardening concerns (see ADR-012).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260414_0007"
down_revision: str | None = "20260414_0006"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "audit_logs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        # user_id is nullable — system-level events have no associated user.
        # No FK constraint — audit rows must survive user account deletion
        # (ADR-012: audit log is append-only, no FK to User).
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("action", sa.String(length=200), nullable=False),
        sa.Column("entity_type", sa.String(length=100), nullable=True),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=True),
        # ip_address is sized for IPv6 (max 45 chars: 8 groups × 4 hex + 7 colons)
        sa.Column("ip_address", sa.String(length=45), nullable=False),
        sa.Column("user_agent", sa.String(length=512), nullable=False),
        # No server_default — AuditService.log_event() sets created_at explicitly
        # so the recorded timestamp reflects application time, not DB receive time.
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_audit_logs_user_created",
        "audit_logs",
        ["user_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_audit_logs_user_created", table_name="audit_logs")
    op.drop_table("audit_logs")
