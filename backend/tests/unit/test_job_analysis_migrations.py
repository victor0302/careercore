"""Unit tests for migration 20260414_0004: job analysis tables."""

import importlib.util
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

_MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "20260414_0004_create_job_analysis_tables.py"
)
_SPEC = importlib.util.spec_from_file_location("job_analysis_migration_0004", _MIGRATION_PATH)
assert _SPEC is not None
assert _SPEC.loader is not None
_MIGRATION = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MIGRATION)


def test_migration_revision_id() -> None:
    assert _MIGRATION.revision == "20260414_0004"


def test_migration_down_revision_links_to_0003() -> None:
    assert _MIGRATION.down_revision == "20260413_0003"


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


def test_upgrade_creates_expected_tables_indexes_and_types(monkeypatch) -> None:
    fake_op = _FakeOp()
    created: list[tuple[object, bool]] = []

    monkeypatch.setattr(_MIGRATION, "op", fake_op)
    monkeypatch.setattr(
        _MIGRATION.matchtype,
        "create",
        lambda bind, checkfirst=False: created.append((bind, checkfirst)),
    )

    _MIGRATION.upgrade()

    assert created == [(fake_op.bind, True)]
    assert set(fake_op.tables) == {
        "job_analyses",
        "matched_requirements",
        "missing_requirements",
    }

    job_analysis_columns = _columns(fake_op.tables["job_analyses"])
    assert isinstance(job_analysis_columns["score_breakdown"].type, postgresql.JSONB)
    assert isinstance(job_analysis_columns["analyzed_at"].type, sa.DateTime)
    assert job_analysis_columns["analyzed_at"].type.timezone is True

    job_analysis_fks = _foreign_keys(fake_op.tables["job_analyses"])
    assert {tuple(fk.column_keys) for fk in job_analysis_fks} == {("job_id",), ("user_id",)}
    assert {tuple(fk.elements[0].target_fullname.split(".")) for fk in job_analysis_fks} == {
        ("job_descriptions", "id"),
        ("users", "id"),
    }
    assert {fk.ondelete for fk in job_analysis_fks} == {"CASCADE"}

    matched_columns = _columns(fake_op.tables["matched_requirements"])
    assert matched_columns["match_type"].type is _MIGRATION.matchtype

    matched_fks = _foreign_keys(fake_op.tables["matched_requirements"])
    assert len(matched_fks) == 1
    assert matched_fks[0].column_keys == ["analysis_id"]
    assert matched_fks[0].elements[0].target_fullname == "job_analyses.id"
    assert matched_fks[0].ondelete == "CASCADE"

    missing_fks = _foreign_keys(fake_op.tables["missing_requirements"])
    assert len(missing_fks) == 1
    assert missing_fks[0].column_keys == ["analysis_id"]
    assert missing_fks[0].elements[0].target_fullname == "job_analyses.id"
    assert missing_fks[0].ondelete == "CASCADE"

    assert fake_op.indexes == [
        ("ix_job_analyses_job_id", "job_analyses", ["job_id"], False),
        ("ix_job_analyses_user_id", "job_analyses", ["user_id"], False),
        ("ix_matched_requirements_analysis_id", "matched_requirements", ["analysis_id"], False),
        ("ix_missing_requirements_analysis_id", "missing_requirements", ["analysis_id"], False),
    ]


def test_downgrade_drops_tables_indexes_and_enum(monkeypatch) -> None:
    fake_op = _FakeOp()
    dropped: list[tuple[object, bool]] = []

    monkeypatch.setattr(_MIGRATION, "op", fake_op)
    monkeypatch.setattr(
        _MIGRATION.matchtype,
        "drop",
        lambda bind, checkfirst=False: dropped.append((bind, checkfirst)),
    )

    _MIGRATION.downgrade()

    assert fake_op.dropped_indexes == [
        ("ix_missing_requirements_analysis_id", "missing_requirements"),
        ("ix_matched_requirements_analysis_id", "matched_requirements"),
        ("ix_job_analyses_user_id", "job_analyses"),
        ("ix_job_analyses_job_id", "job_analyses"),
    ]
    assert fake_op.dropped_tables == [
        "missing_requirements",
        "matched_requirements",
        "job_analyses",
    ]
    assert dropped == [(fake_op.bind, True)]
