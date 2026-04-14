"""Unit tests for migration 20260414_0005: ai_call_logs table."""

import importlib.util
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

_MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "20260414_0005_create_ai_call_logs_table.py"
)
_SPEC = importlib.util.spec_from_file_location("ai_call_log_migration_0005", _MIGRATION_PATH)
assert _SPEC is not None
assert _SPEC.loader is not None
_MIGRATION = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MIGRATION)


def test_migration_revision_id() -> None:
    assert _MIGRATION.revision == "20260414_0005"


def test_migration_down_revision_links_to_0004() -> None:
    assert _MIGRATION.down_revision == "20260414_0004"


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


def _foreign_keys(elements: tuple[object, ...]) -> list[sa.ForeignKeyConstraint]:
    return [
        element
        for element in elements
        if isinstance(element, sa.ForeignKeyConstraint)
    ]


def test_upgrade_creates_table_and_index(monkeypatch) -> None:
    fake_op = _FakeOp()
    created: list[tuple[object, bool]] = []

    monkeypatch.setattr(_MIGRATION, "op", fake_op)
    monkeypatch.setattr(
        _MIGRATION.aicalltype,
        "create",
        lambda bind, checkfirst=False: created.append((bind, checkfirst)),
    )

    _MIGRATION.upgrade()

    # Enum was created before the table
    assert created == [(fake_op.bind, True)]

    # Table was registered
    assert "ai_call_logs" in fake_op.tables

    cols = _columns(fake_op.tables["ai_call_logs"])

    # call_type uses the aicalltype enum object
    assert cols["call_type"].type is _MIGRATION.aicalltype

    # cost_usd is Numeric(10, 6)
    assert isinstance(cols["cost_usd"].type, sa.Numeric)
    assert cols["cost_usd"].type.precision == 10
    assert cols["cost_usd"].type.scale == 6

    # created_at is a timezone-aware DateTime
    assert isinstance(cols["created_at"].type, sa.DateTime)
    assert cols["created_at"].type.timezone is True

    # user_id has NO foreign key constraint (intentional — see migration comment)
    fks = _foreign_keys(fake_op.tables["ai_call_logs"])
    fk_columns = {col for fk in fks for col in fk.column_keys}
    assert "user_id" not in fk_columns

    # Composite index on (user_id, created_at)
    assert fake_op.indexes == [
        ("ix_ai_call_logs_user_created", "ai_call_logs", ["user_id", "created_at"], False),
    ]


def test_upgrade_enum_values_are_complete(monkeypatch) -> None:
    """The aicalltype enum must contain all six AICallType values."""
    expected = {
        "parse_job_description",
        "generate_bullets",
        "explain_score",
        "answer_followup",
        "generate_recommendations",
        "generate_learning_plan",
    }
    assert set(_MIGRATION.aicalltype.enums) == expected


def test_downgrade_drops_index_table_and_enum(monkeypatch) -> None:
    fake_op = _FakeOp()
    dropped: list[tuple[object, bool]] = []

    monkeypatch.setattr(_MIGRATION, "op", fake_op)
    monkeypatch.setattr(
        _MIGRATION.aicalltype,
        "drop",
        lambda bind, checkfirst=False: dropped.append((bind, checkfirst)),
    )

    _MIGRATION.downgrade()

    assert fake_op.dropped_indexes == [
        ("ix_ai_call_logs_user_created", "ai_call_logs"),
    ]
    assert fake_op.dropped_tables == ["ai_call_logs"]
    assert dropped == [(fake_op.bind, True)]
