"""Unit tests for migration 20260414_0006: uploaded_files table."""

import importlib.util
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

_MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "20260414_0006_create_uploaded_files_table.py"
)
_SPEC = importlib.util.spec_from_file_location("uploaded_file_migration_0006", _MIGRATION_PATH)
assert _SPEC is not None
assert _SPEC.loader is not None
_MIGRATION = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MIGRATION)


def test_migration_revision_id() -> None:
    assert _MIGRATION.revision == "20260414_0006"


def test_migration_down_revision_links_to_0005() -> None:
    assert _MIGRATION.down_revision == "20260414_0005"


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


def _foreign_keys(elements: tuple[object, ...]) -> list[sa.ForeignKeyConstraint]:
    return [
        element
        for element in elements
        if isinstance(element, sa.ForeignKeyConstraint)
    ]


def test_upgrade_creates_uploaded_files_table_enum_and_index(monkeypatch) -> None:
    fake_op = _FakeOp()
    created: list[tuple[object, bool]] = []

    monkeypatch.setattr(_MIGRATION, "op", fake_op)
    monkeypatch.setattr(
        _MIGRATION.filestatus,
        "create",
        lambda bind, checkfirst=False: created.append((bind, checkfirst)),
    )

    _MIGRATION.upgrade()

    assert created == [(fake_op.bind, True)]
    assert "uploaded_files" in fake_op.tables

    cols = _columns(fake_op.tables["uploaded_files"])
    assert cols["status"].type is _MIGRATION.filestatus
    assert cols["status"].server_default.arg.text == "'pending'"
    assert isinstance(cols["id"].type, postgresql.UUID)
    assert isinstance(cols["created_at"].type, sa.DateTime)
    assert cols["created_at"].type.timezone is True
    assert isinstance(cols["updated_at"].type, sa.DateTime)
    assert cols["updated_at"].type.timezone is True

    fks = _foreign_keys(fake_op.tables["uploaded_files"])
    assert len(fks) == 1
    assert fks[0].column_keys == ["user_id"]
    assert fks[0].elements[0].target_fullname == "users.id"
    assert fks[0].ondelete == "CASCADE"

    assert cols["storage_key"].unique is True

    assert fake_op.indexes == [
        ("ix_uploaded_files_user_id", "uploaded_files", ["user_id"], False),
    ]


def test_upgrade_filestatus_enum_values_are_complete() -> None:
    assert set(_MIGRATION.filestatus.enums) == {
        "pending",
        "processing",
        "ready",
        "error",
    }


def test_downgrade_drops_index_table_and_enum(monkeypatch) -> None:
    fake_op = _FakeOp()
    dropped: list[tuple[object, bool]] = []

    monkeypatch.setattr(_MIGRATION, "op", fake_op)
    monkeypatch.setattr(
        _MIGRATION.filestatus,
        "drop",
        lambda bind, checkfirst=False: dropped.append((bind, checkfirst)),
    )

    _MIGRATION.downgrade()

    assert fake_op.dropped_indexes == [
        ("ix_uploaded_files_user_id", "uploaded_files"),
    ]
    assert fake_op.dropped_tables == ["uploaded_files"]
    assert dropped == [(fake_op.bind, True)]
