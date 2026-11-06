"""Emit an apply_patch for frozen additive DDL, never import ORM at migration time."""

import pprint
import sys
from pathlib import Path

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
from app.modules.awp import models as awp_models  # noqa: F401
from app.modules.cost_foundation import models as cost_models  # noqa: F401
from app.modules.operational_context import (
    models as operational_models,  # noqa: F401
)
from app.modules.progress_foundation import integration_models, models
from app.modules.schedule_foundation import models as schedule_models  # noqa: F401


def main():
    result = []
    for cls in (
        models.ProgressRule,
        models.ProgressMeasurement,
        models.ProgressHistory,
        integration_models.ProjectControlBaselineBundle,
        integration_models.ProgressPeriodSnapshot,
        integration_models.EarnedValueSnapshot,
    ):
        table = cls.__table__
        columns = []
        for col in table.columns:
            kind = col.type
            if isinstance(kind, JSON):
                typ, args = "JSON", []
            elif isinstance(kind, Text):
                typ, args = "Text", []
            elif isinstance(kind, String):
                typ, args = "String", [kind.length]
            elif isinstance(kind, Numeric):
                typ, args = "Numeric", [kind.precision, kind.scale]
            elif isinstance(kind, Boolean):
                typ, args = "Boolean", []
            elif isinstance(kind, Integer):
                typ, args = "Integer", []
            elif isinstance(kind, DateTime):
                typ, args = "DateTime", [kind.timezone]
            elif isinstance(kind, Date):
                typ, args = "Date", []
            else:
                raise TypeError((table.name, col.name, str(kind)))
            columns.append(
                (
                    col.name,
                    typ,
                    args,
                    col.nullable,
                    col.primary_key,
                    [fk.target_fullname for fk in col.foreign_keys],
                    col.index is True,
                )
            )
        unique = [
            (constraint.name, [col.name for col in constraint.columns])
            for constraint in table.constraints
            if isinstance(constraint, UniqueConstraint)
        ]
        checks = [
            (constraint.name, str(constraint.sqltext))
            for constraint in table.constraints
            if isinstance(constraint, CheckConstraint)
        ]
        result.append(
            {"name": table.name, "columns": columns, "unique": unique, "checks": checks}
        )
    prefix = '''"""Progress authority and integrated baseline references, additive only.

Revision ID: 20261104_0074
Revises: 20261022_0073
"""

import sqlalchemy as sa
from alembic import op

revision = "20261104_0074"
down_revision = "20261022_0073"
branch_labels = None
depends_on = None

FROZEN_TABLES = '''
    suffix = """

GUARD_SQL = ""


def upgrade():
    for spec in FROZEN_TABLES:
        columns = []
        for name, kind, args, nullable, primary, references, _index in spec["columns"]:
            typ = sa.DateTime(timezone=args[0]) if kind == "DateTime" else getattr(sa, kind)(*args)
            columns.append(sa.Column(name, typ, *(sa.ForeignKey(ref) for ref in references), nullable=nullable, primary_key=primary))
        constraints = [sa.UniqueConstraint(*fields, name=name) for name, fields in spec["unique"]]
        constraints += [sa.CheckConstraint(sql, name=name) for name, sql in spec["checks"]]
        op.create_table(spec["name"], *columns, *constraints)
        for name, _kind, _args, _nullable, _primary, _refs, index in spec["columns"]:
            if index:
                op.create_index(f"ix_{spec['name']}_{name}", spec["name"], [name])
    if op.get_bind().dialect.name == "postgresql":
        op.execute(GUARD_SQL)


def downgrade():
    connection = op.get_bind()
    for spec in FROZEN_TABLES:
        if connection.scalar(sa.text(f"SELECT count(*) FROM {spec['name']}")):
            raise RuntimeError("Progress authority contains business records; downgrade refused")
    for spec in reversed(FROZEN_TABLES):
        op.drop_table(spec["name"])
"""
    source = prefix + pprint.pformat(result, width=115, sort_dicts=False) + suffix
    target = ROOT / "backend/alembic/versions/20261104_0074_progress_foundation.py"
    assert not target.exists(), "Do not overwrite the reviewed frozen migration"
    print(
        "*** Begin Patch\n*** Add File: "
        + str(target).replace("\\", "/")
        + "\n"
        + "\n".join("+" + line for line in source.splitlines())
        + "\n*** End Patch"
    )


if __name__ == "__main__":
    main()
