"""Generate an apply_patch with frozen six-table DDL, not live ORM migrations."""

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
from app.modules.cost_foundation import (
    financial_models as cost_financial_models,  # noqa: F401
)
from app.modules.cost_foundation import models as cost_models  # noqa: F401
from app.modules.forecast_foundation import models, reporting_models
from app.modules.operational_context import models as operational_models  # noqa: F401
from app.modules.progress_foundation import (
    integration_models as progress_models,  # noqa: F401
)
from app.modules.schedule_foundation import models as schedule_models  # noqa: F401


def main():
    tables = []
    for cls in (
        models.ForecastVersion,
        models.ForecastAssumption,
        models.ForecastComponent,
        models.ForecastHistory,
        reporting_models.ForecastReportSnapshot,
        reporting_models.ForecastLookAheadSnapshot,
    ):
        table = cls.__table__
        columns = []
        for column in table.columns:
            kind = column.type
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
                raise TypeError((table.name, column.name, str(kind)))
            columns.append(
                (
                    column.name,
                    typ,
                    args,
                    column.nullable,
                    column.primary_key,
                    [fk.target_fullname for fk in column.foreign_keys],
                    column.index is True,
                )
            )
        tables.append(
            {
                "name": table.name,
                "columns": columns,
                "unique": [
                    (c.name, [col.name for col in c.columns])
                    for c in table.constraints
                    if isinstance(c, UniqueConstraint)
                ],
                "checks": [
                    (c.name, str(c.sqltext))
                    for c in table.constraints
                    if isinstance(c, CheckConstraint)
                ],
            }
        )
    prefix = '''"""Governed Forecast projection and immutable reporting, additive only.

Revision ID: 20261106_0075
Revises: 20261104_0074
"""

import sqlalchemy as sa
from alembic import op

revision = "20261106_0075"
down_revision = "20261104_0074"
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
        for spec in FROZEN_TABLES:
            op.execute(f"CREATE TRIGGER tr_{spec['name']}_o1c BEFORE INSERT OR UPDATE OR DELETE ON {spec['name']} FOR EACH ROW EXECUTE FUNCTION o1c_forecast_guard()")


def downgrade():
    connection = op.get_bind()
    for spec in FROZEN_TABLES:
        if connection.scalar(sa.text(f"SELECT count(*) FROM {spec['name']}")):
            raise RuntimeError("Forecast or reporting contains business records; downgrade refused")
    if connection.dialect.name == "postgresql":
        op.execute("DROP TRIGGER tr_forecast_profile_o1c ON admin_configurations")
    for spec in reversed(FROZEN_TABLES):
        op.drop_table(spec["name"])
    if connection.dialect.name == "postgresql":
        op.execute("DROP FUNCTION o1c_forecast_profile_guard()")
        op.execute("DROP FUNCTION o1c_forecast_guard()")
"""
    source = prefix + pprint.pformat(tables, width=115, sort_dicts=False) + suffix
    target = ROOT / "backend/alembic/versions/20261106_0075_forecast_foundation.py"
    assert not target.exists(), "Never overwrite a reviewed frozen migration"
    print(
        "*** Begin Patch\n*** Add File: "
        + target.as_posix()
        + "\n"
        + "\n".join("+" + line for line in source.splitlines())
        + "\n*** End Patch"
    )


if __name__ == "__main__":
    main()
