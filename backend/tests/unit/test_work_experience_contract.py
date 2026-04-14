"""Focused WorkExperience model/schema/migration contract tests."""

import uuid
import importlib.util
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from app.schemas.profile import WorkExperienceCreate, WorkExperienceUpdate

_MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "20260413_0003_create_profile_tables.py"
)
_SPEC = importlib.util.spec_from_file_location("profile_migration_0003", _MIGRATION_PATH)
assert _SPEC is not None
assert _SPEC.loader is not None
_MIGRATION = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MIGRATION)


class _FakeOp:
    def __init__(self) -> None:
        self.tables: dict[str, tuple[object, ...]] = {}
        self.indexes: list[tuple[str, str, list[str], bool]] = []

    def create_table(self, name: str, *elements: object) -> None:
        self.tables[name] = elements

    def create_index(
        self, name: str, table_name: str, columns: list[str], unique: bool = False
    ) -> None:
        self.indexes.append((name, table_name, columns, unique))

    def drop_index(self, name: str, table_name: str) -> None:
        return None

    def drop_table(self, name: str) -> None:
        return None

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


def test_work_experience_create_update_schemas_include_source_file_id() -> None:
    source_file_id = uuid.uuid4()

    created = WorkExperienceCreate(
        source_file_id=source_file_id,
        employer="CareerCore",
        role_title="Engineer",
        start_date="2024-01-01",
    )
    updated = WorkExperienceUpdate(source_file_id=None)

    assert created.source_file_id == source_file_id
    assert created.model_dump()["source_file_id"] == source_file_id
    assert "source_file_id" in updated.model_dump(exclude_unset=True)
    assert updated.model_dump(exclude_unset=True)["source_file_id"] is None


def test_profile_migration_work_experience_shape_matches_model(monkeypatch) -> None:
    fake_op = _FakeOp()
    monkeypatch.setattr(_MIGRATION, "op", fake_op)

    _MIGRATION.upgrade()

    assert "work_experiences" in fake_op.tables

    cols = _columns(fake_op.tables["work_experiences"])
    assert cols["source_file_id"].nullable is True
    assert isinstance(cols["bullets"].type, postgresql.JSONB)
    assert isinstance(cols["skill_tags"].type, postgresql.ARRAY)
    assert isinstance(cols["tool_tags"].type, postgresql.ARRAY)
    assert isinstance(cols["domain_tags"].type, postgresql.ARRAY)

    fks = {tuple(fk.column_keys): fk for fk in _foreign_keys(fake_op.tables["work_experiences"])}
    profile_fk = fks[("profile_id",)]
    source_file_fk = fks[("source_file_id",)]

    assert profile_fk.elements[0].target_fullname == "profiles.id"
    assert profile_fk.ondelete == "CASCADE"
    assert source_file_fk.elements[0].target_fullname == "uploaded_files.id"
    assert source_file_fk.ondelete == "SET NULL"

    assert ("ix_work_experiences_profile_id", "work_experiences", ["profile_id"], False) in fake_op.indexes
