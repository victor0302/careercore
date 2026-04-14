"""Unit tests: Project, Skill, Certification schema and migration contract."""

import importlib.util
import uuid
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import sqlalchemy as sa
from pydantic import ValidationError
from sqlalchemy.dialects import postgresql

from app.schemas.profile import (
    CertificationCreate,
    CertificationRead,
    ProjectCreate,
    ProjectRead,
    SkillCreate,
    SkillRead,
)

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


# ── Helpers ───────────────────────────────────────────────────────────────────


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
    return {e.name: e for e in elements if isinstance(e, sa.Column)}


def _foreign_keys(elements: tuple[object, ...]) -> list[sa.ForeignKeyConstraint]:
    return [e for e in elements if isinstance(e, sa.ForeignKeyConstraint)]


# ── Schema contract: ProjectCreate ────────────────────────────────────────────


def test_project_create_requires_name() -> None:
    with pytest.raises(ValidationError):
        ProjectCreate()  # type: ignore[call-arg]


def test_project_create_minimal() -> None:
    p = ProjectCreate(name="My Project")
    assert p.name == "My Project"
    assert p.description_raw is None
    assert p.url is None


def test_project_read_deserialises_from_orm_object() -> None:
    profile_id = uuid.uuid4()
    obj = MagicMock()
    obj.id = uuid.uuid4()
    obj.profile_id = profile_id
    obj.name = "Demo"
    obj.description_raw = None
    obj.url = None
    obj.bullets = None
    obj.skill_tags = None
    obj.tool_tags = None
    obj.domain_tags = None

    read = ProjectRead.model_validate(obj)
    assert read.name == "Demo"
    assert read.profile_id == profile_id


# ── Schema contract: SkillCreate ──────────────────────────────────────────────


def test_skill_create_requires_name() -> None:
    with pytest.raises(ValidationError):
        SkillCreate()  # type: ignore[call-arg]


def test_skill_create_minimal() -> None:
    s = SkillCreate(name="Python")
    assert s.name == "Python"
    assert s.category is None
    assert s.proficiency_level is None
    assert s.years_of_experience is None


def test_skill_read_deserialises_from_orm_object() -> None:
    obj = MagicMock()
    obj.id = uuid.uuid4()
    obj.profile_id = uuid.uuid4()
    obj.name = "Python"
    obj.category = "Programming"
    obj.proficiency_level = "expert"
    obj.years_of_experience = 5.0

    read = SkillRead.model_validate(obj)
    assert read.name == "Python"
    assert read.years_of_experience == 5.0


# ── Schema contract: CertificationCreate ─────────────────────────────────────


def test_certification_create_requires_name() -> None:
    with pytest.raises(ValidationError):
        CertificationCreate()  # type: ignore[call-arg]


def test_certification_create_minimal() -> None:
    c = CertificationCreate(name="AWS SAA")
    assert c.name == "AWS SAA"
    assert c.issued_date is None
    assert c.expiry_date is None


def test_certification_create_with_dates() -> None:
    c = CertificationCreate(
        name="AWS SAA",
        issued_date=date(2023, 6, 15),
        expiry_date=date(2026, 6, 15),
    )
    assert c.issued_date == date(2023, 6, 15)
    assert c.expiry_date == date(2026, 6, 15)


def test_certification_read_deserialises_from_orm_object() -> None:
    obj = MagicMock()
    obj.id = uuid.uuid4()
    obj.profile_id = uuid.uuid4()
    obj.name = "AWS SAA"
    obj.issuer = "Amazon"
    obj.issued_date = date(2023, 6, 15)
    obj.expiry_date = date(2026, 6, 15)
    obj.credential_id = "12345"
    obj.credential_url = "https://aws.amazon.com/verify/12345"

    read = CertificationRead.model_validate(obj)
    assert read.name == "AWS SAA"
    assert read.issued_date == date(2023, 6, 15)


# ── Migration shape: projects table ───────────────────────────────────────────


def test_projects_migration_shape(monkeypatch) -> None:
    fake_op = _FakeOp()
    monkeypatch.setattr(_MIGRATION, "op", fake_op)
    _MIGRATION.upgrade()

    assert "projects" in fake_op.tables
    cols = _columns(fake_op.tables["projects"])

    assert isinstance(cols["bullets"].type, postgresql.JSONB)
    assert isinstance(cols["skill_tags"].type, postgresql.ARRAY)
    assert isinstance(cols["tool_tags"].type, postgresql.ARRAY)
    assert isinstance(cols["domain_tags"].type, postgresql.ARRAY)
    assert cols["name"].nullable is False
    assert cols["description_raw"].nullable is True

    fks = {tuple(fk.column_keys): fk for fk in _foreign_keys(fake_op.tables["projects"])}
    assert fks[("profile_id",)].elements[0].target_fullname == "profiles.id"
    assert fks[("profile_id",)].ondelete == "CASCADE"
    assert fks[("source_file_id",)].ondelete == "SET NULL"

    assert ("ix_projects_profile_id", "projects", ["profile_id"], False) in fake_op.indexes


# ── Migration shape: skills table ─────────────────────────────────────────────


def test_skills_migration_shape(monkeypatch) -> None:
    fake_op = _FakeOp()
    monkeypatch.setattr(_MIGRATION, "op", fake_op)
    _MIGRATION.upgrade()

    assert "skills" in fake_op.tables
    cols = _columns(fake_op.tables["skills"])

    assert cols["name"].nullable is False
    assert cols["category"].nullable is True
    assert cols["proficiency_level"].nullable is True
    assert isinstance(cols["years_of_experience"].type, sa.Float)

    fks = {tuple(fk.column_keys): fk for fk in _foreign_keys(fake_op.tables["skills"])}
    assert fks[("profile_id",)].elements[0].target_fullname == "profiles.id"
    assert fks[("profile_id",)].ondelete == "CASCADE"

    assert ("ix_skills_profile_id", "skills", ["profile_id"], False) in fake_op.indexes


# ── Migration shape: certifications table ────────────────────────────────────


def test_certifications_migration_shape(monkeypatch) -> None:
    fake_op = _FakeOp()
    monkeypatch.setattr(_MIGRATION, "op", fake_op)
    _MIGRATION.upgrade()

    assert "certifications" in fake_op.tables
    cols = _columns(fake_op.tables["certifications"])

    assert cols["name"].nullable is False
    assert cols["issuer"].nullable is True
    assert isinstance(cols["issued_date"].type, sa.Date)
    assert isinstance(cols["expiry_date"].type, sa.Date)
    assert cols["credential_id"].nullable is True
    assert cols["credential_url"].nullable is True

    fks = {tuple(fk.column_keys): fk for fk in _foreign_keys(fake_op.tables["certifications"])}
    assert fks[("profile_id",)].elements[0].target_fullname == "profiles.id"
    assert fks[("profile_id",)].ondelete == "CASCADE"

    assert (
        "ix_certifications_profile_id",
        "certifications",
        ["profile_id"],
        False,
    ) in fake_op.indexes
