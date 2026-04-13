"""Audit service — append-only event log.

Every state-changing operation (create, update, delete, login, logout)
must call AuditService.log_event() AFTER the operation succeeds.
This log is never deleted or modified.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog


class AuditService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def log_event(
        self,
        action: str,
        ip_address: str,
        user_agent: str,
        user_id: uuid.UUID | None = None,
        entity_type: str | None = None,
        entity_id: uuid.UUID | None = None,
    ) -> None:
        """Append an immutable audit entry to the audit_logs table.

        Args:
            action:      Verb describing the event, e.g. "user.login", "resume.create".
            ip_address:  Source IP from the request (X-Forwarded-For in prod).
            user_agent:  User-Agent header value.
            user_id:     UUID of the acting user, or None for system events.
            entity_type: Model class name of the affected entity, e.g. "Resume".
            entity_id:   PK of the affected entity.
        """
        entry = AuditLog(
            user_id=user_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            ip_address=ip_address,
            user_agent=user_agent,
            created_at=datetime.now(tz=timezone.utc),
        )
        self._db.add(entry)
        await self._db.flush()  # write without committing — caller owns the transaction
