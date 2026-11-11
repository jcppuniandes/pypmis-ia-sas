"""Print static Alembic table specs from the reviewed O2A schema; never run DDL."""

import json
import sys
from pathlib import Path

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Date,
    DateTime,
    Integer,
    String,
    Text,
    UniqueConstraint,
)

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
from app.modules.engineering_foundation import integration_models, models
from app.modules.schedule_foundation import (
    models as schedule_models,  # noqa: F401
)


def column_spec(column):
    kind = column.type
    if isinstance(kind, JSON):
        label, args = "JSON", []
    elif isinstance(kind, Text):
        label, args = "Text", []
    elif isinstance(kind, String):
        label, args = "String", [kind.length]
    elif isinstance(kind, Integer):
        label, args = "Integer", []
    elif isinstance(kind, DateTime):
        label, args = "DateTime", []
    elif isinstance(kind, Date):
        label, args = "Date", []
    else:
        raise TypeError((column.table.name, column.name, kind))
    return [
        column.name,
        label,
        args,
        column.nullable,
        column.primary_key,
        sorted(key.target_fullname for key in column.foreign_keys),
    ]


def main():
    tables = [
        cls.__table__
        for cls in (
            models.EngineeringDesignPackage,
            models.EngineeringDeliverable,
            models.EngineeringRevision,
            models.EngineeringReview,
            models.EngineeringReviewComment,
            models.EngineeringRelease,
            models.EngineeringInterface,
            models.EngineeringHistory,
            integration_models.EngineeringMapping,
        )
    ]
    result = []
    for table in tables:
        result.append(
            {
                "name": table.name,
                "columns": [column_spec(column) for column in table.columns],
                "unique": sorted(
                    [c.name, [column.name for column in c.columns]]
                    for c in table.constraints
                    if isinstance(c, UniqueConstraint)
                ),
                "checks": sorted(
                    [c.name, str(c.sqltext)]
                    for c in table.constraints
                    if isinstance(c, CheckConstraint)
                ),
                "indexes": [
                    [
                        i.name,
                        [column.name for column in i.columns],
                        i.unique,
                        str(i.dialect_options["postgresql"]["where"])
                        if i.dialect_options["postgresql"]["where"] is not None
                        else None,
                    ]
                    for i in sorted(table.indexes, key=lambda i: i.name)
                ],
            }
        )
    print(json.dumps(result))


if __name__ == "__main__":
    main()
