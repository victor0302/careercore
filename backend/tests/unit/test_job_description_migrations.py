"""Unit tests for migration 20260414_0003a: job description and requirement tables."""

import importlib.util
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

_MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "20260414_0003a_create_job_description_and_requirement_tables.py"
)
_SPEC = importlib.util.spec_from_file_location(
    "job_description_requirement_migration_0003a",
    _MIGRATION_PATH,
)
assert _SPEC is not None
assert _SPEC.loader is not None
_MIGRATION = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MIGRATION)


def test_migration_revision_id() -> None:
    assert _MIGRATION.revision == "20260414_0003a"


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


def test_upgrade_creates_expected_tables_indexes_and_enum(monkeypatch) -> None:
    fake_op = _FakeOp()
    created: list[tuple[object, bool]] = []

    monkeypatch.setattr(_MIGRATION, "op", fake_op)
    monkeypatch.setattr(
        _MIGRATION.jobrequirementcategory,
        "create",
        lambda bind, checkfirst=False: created.append((bind, checkfirst)),
    )

    _MIGRATION.upgrade()

    assert created == [(fake_op.bind, True)]
    assert set(fake_op.tables) == {"job_descriptions", "job_requirements"}

    job_description_columns = _columns(fake_op.tables["job_descriptions"])
    assert isinstance(job_description_columns["parsed_at"].type, sa.DateTime)
    assert job_description_columns["parsed_at"].type.timezone is True

    job_description_fks = _foreign_keys(fake_op.tables["job_descriptions"])
    assert len(job_description_fks) == 1
    assert job_description_fks[0].column_keys == ["user_id"]
    assert job_description_fks[0].elements[0].target_fullname == "users.id"
    assert job_description_fks[0].ondelete == "CASCADE"

    job_requirement_columns = _columns(fake_op.tables["job_requirements"])
    assert isinstance(job_requirement_columns["requirement_text"].type, sa.Text)
    assert job_requirement_columns["category"].type is _MIGRATION.jobrequirementcategory

    job_requirement_fks = _foreign_keys(fake_op.tables["job_requirements"])
    assert len(job_requirement_fks) == 1
    assert job_requirement_fks[0].column_keys == ["job_id"]
    assert job_requirement_fks[0].elements[0].target_fullname == "job_descriptions.id"
    assert job_requirement_fks[0].ondelete == "CASCADE"

    assert fake_op.indexes == [
        ("ix_job_descriptions_user_id", "job_descriptions", ["user_id"], False),
        ("ix_job_requirements_job_id", "job_requirements", ["job_id"], False),
    ]


def test_downgrade_drops_tables_indexes_and_enum(monkeypatch) -> None:
    fake_op = _FakeOp()
    dropped: list[tuple[object, bool]] = []

    monkeypatch.setattr(_MIGRATION, "op", fake_op)
    monkeypatch.setattr(
        _MIGRATION.jobrequirementcategory,
        "drop",
        lambda bind, checkfirst=False: dropped.append((bind, checkfirst)),
    )

    _MIGRATION.downgrade()

    assert fake_op.dropped_indexes == [
        ("ix_job_requirements_job_id", "job_requirements"),
        ("ix_job_descriptions_user_id", "job_descriptions"),
    ]
    assert fake_op.dropped_tables == [
        "job_requirements",
        "job_descriptions",
    ]
    assert dropped == [(fake_op.bind, True)]
