"""Unit tests for migration 20260414_0007: audit_logs table."""

import importlib.util
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

_MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "20260414_0007_create_audit_logs_table.py"
)
_SPEC = importlib.util.spec_from_file_location("audit_log_migration_0007", _MIGRATION_PATH)
assert _SPEC is not None
assert _SPEC.loader is not None
_MIGRATION = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MIGRATION)


def test_migration_revision_id() -> None:
    assert _MIGRATION.revision == "20260414_0007"


def test_migration_down_revision_links_to_0006() -> None:
    assert _MIGRATION.down_revision == "20260414_0006"


def test_migration_has_upgrade_and_downgrade() -> None:
    assert callable(_MIGRATION.upgrade)
    assert callable(_MIGRATION.downgrade)


class _FakeOp:
    def __init__(self) -> None:
        self.bind = object()
        self.tables: dict[str, tuple[object, ...]] = {}
        self.indexes: list[tuple[str, str, list[str], bool]] = []
        self.dropped_indexes: list[tuple[str, str]] = []
        self.dropped_tables: list[str] = []

    def get_bind(self) -> object:
        return self.bind

    def create_table(self, name: str, *elements: object) -> None:
        self.tables[name] = elements

    def create_index(
        self, name: str, table_name: str, columns: list[str], unique: bool = False
    ) -> None:
        self.indexes.append((name, table_name, columns, unique))

    def drop_index(self, name: str, table_name: str) -> None:
        self.dropped_indexes.append((name, table_name))

    def drop_table(self, name: str) -> None:
        self.dropped_tables.append(name)

    def f(self, name: str) -> str:
        return name


def _columns(elements: tuple[object, ...]) -> dict[str, sa.Column[object]]:
    return {
        element.name: element
        for element in elements
        if isinstance(element, sa.Column)
    }


def test_upgrade_creates_audit_logs_table(monkeypatch) -> None:
    fake_op = _FakeOp()
    monkeypatch.setattr(_MIGRATION, "op", fake_op)

    _MIGRATION.upgrade()

    assert "audit_logs" in fake_op.tables


def test_upgrade_creates_composite_index(monkeypatch) -> None:
    fake_op = _FakeOp()
    monkeypatch.setattr(_MIGRATION, "op", fake_op)

    _MIGRATION.upgrade()

    assert fake_op.indexes == [
        ("ix_audit_logs_user_created", "audit_logs", ["user_id", "created_at"], False),
    ]


def test_user_id_column_is_nullable(monkeypatch) -> None:
    fake_op = _FakeOp()
    monkeypatch.setattr(_MIGRATION, "op", fake_op)

    _MIGRATION.upgrade()

    cols = _columns(fake_op.tables["audit_logs"])
    assert cols["user_id"].nullable is True


def test_user_id_has_no_foreign_key(monkeypatch) -> None:
    fake_op = _FakeOp()
    monkeypatch.setattr(_MIGRATION, "op", fake_op)

    _MIGRATION.upgrade()

    fks = [
        element
        for element in fake_op.tables["audit_logs"]
        if isinstance(element, sa.ForeignKeyConstraint)
    ]
    fk_columns = {col for fk in fks for col in fk.column_keys}
    assert "user_id" not in fk_columns


def test_action_column_is_varchar_200_not_null(monkeypatch) -> None:
    fake_op = _FakeOp()
    monkeypatch.setattr(_MIGRATION, "op", fake_op)

    _MIGRATION.upgrade()

    cols = _columns(fake_op.tables["audit_logs"])
    assert isinstance(cols["action"].type, sa.String)
    assert cols["action"].type.length == 200
    assert cols["action"].nullable is False


def test_created_at_has_no_server_default(monkeypatch) -> None:
    """created_at must not have a server_default — app sets it explicitly."""
    fake_op = _FakeOp()
    monkeypatch.setattr(_MIGRATION, "op", fake_op)

    _MIGRATION.upgrade()

    cols = _columns(fake_op.tables["audit_logs"])
    assert cols["created_at"].server_default is None


def test_downgrade_drops_index_then_table(monkeypatch) -> None:
    fake_op = _FakeOp()
    monkeypatch.setattr(_MIGRATION, "op", fake_op)

    _MIGRATION.downgrade()

    assert fake_op.dropped_indexes == [("ix_audit_logs_user_created", "audit_logs")]
    assert fake_op.dropped_tables == ["audit_logs"]
