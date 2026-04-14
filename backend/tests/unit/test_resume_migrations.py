"""Unit tests for migration 20260414_0008: resume tables."""

import importlib.util
from pathlib import Path

import sqlalchemy as sa

_MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "20260414_0008_create_resume_tables.py"
)
_SPEC = importlib.util.spec_from_file_location("resume_migration_0008", _MIGRATION_PATH)
assert _SPEC is not None
assert _SPEC.loader is not None
_MIGRATION = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MIGRATION)


def test_migration_revision_id() -> None:
    assert _MIGRATION.revision == "20260414_0008"


def test_migration_down_revision_links_to_0007() -> None:
    assert _MIGRATION.down_revision == "20260414_0007"


class _FakeOp:
    def __init__(self) -> None:
        self.tables: dict[str, tuple[object, ...]] = {}
        self.indexes: list[tuple[str, str, list[str], bool]] = []
        self.dropped_indexes: list[tuple[str, str]] = []
        self.dropped_tables: list[str] = []

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


def test_upgrade_creates_all_resume_tables(monkeypatch) -> None:
    fake_op = _FakeOp()
    monkeypatch.setattr(_MIGRATION, "op", fake_op)

    _MIGRATION.upgrade()

    assert set(fake_op.tables) == {
        "resumes",
        "resume_versions",
        "resume_bullets",
        "evidence_links",
    }


def test_is_approved_has_server_default_false(monkeypatch) -> None:
    fake_op = _FakeOp()
    monkeypatch.setattr(_MIGRATION, "op", fake_op)

    _MIGRATION.upgrade()

    cols = _columns(fake_op.tables["resume_bullets"])
    assert cols["is_approved"].nullable is False
    assert cols["is_approved"].server_default is not None
    assert cols["is_approved"].server_default.arg.text == "false"


def test_evidence_links_has_no_created_at_column(monkeypatch) -> None:
    fake_op = _FakeOp()
    monkeypatch.setattr(_MIGRATION, "op", fake_op)

    _MIGRATION.upgrade()

    cols = _columns(fake_op.tables["evidence_links"])
    assert "created_at" not in cols


def test_evidence_links_bullet_fk_uses_on_delete_cascade(monkeypatch) -> None:
    fake_op = _FakeOp()
    monkeypatch.setattr(_MIGRATION, "op", fake_op)

    _MIGRATION.upgrade()

    fks = _foreign_keys(fake_op.tables["evidence_links"])
    assert len(fks) == 1
    assert fks[0].column_keys == ["bullet_id"]
    assert fks[0].elements[0].target_fullname == "resume_bullets.id"
    assert fks[0].ondelete == "CASCADE"


def test_resumes_job_fk_uses_on_delete_set_null(monkeypatch) -> None:
    fake_op = _FakeOp()
    monkeypatch.setattr(_MIGRATION, "op", fake_op)

    _MIGRATION.upgrade()

    fks = {
        tuple(fk.column_keys): fk
        for fk in _foreign_keys(fake_op.tables["resumes"])
    }
    job_fk = fks[("job_id",)]
    assert job_fk.elements[0].target_fullname == "job_descriptions.id"
    assert job_fk.ondelete == "SET NULL"


def test_downgrade_drops_tables_in_reverse_dependency_order(monkeypatch) -> None:
    fake_op = _FakeOp()
    monkeypatch.setattr(_MIGRATION, "op", fake_op)

    _MIGRATION.downgrade()

    assert fake_op.dropped_tables == [
        "evidence_links",
        "resume_bullets",
        "resume_versions",
        "resumes",
    ]
