"""Print PostgreSQL DDL derived from O2B models; never connect or run DDL."""

import json
import sys
from pathlib import Path

from sqlalchemy.dialects.postgresql import dialect
from sqlalchemy.schema import (
    AddConstraint,
    CreateIndex,
    CreateTable,
    sort_tables_and_constraints,
)

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.database.session import Base
from app.modules.procurement_foundation import (  # noqa: F401 - register all migration metadata
    integration,
    integration_models,
    materials_models,
    sourcing_models,
)


def main():
    tables = [
        table
        for name, table in Base.metadata.tables.items()
        if name.startswith("procurement_")
    ]
    assert len(tables) == 27
    pg = dialect()
    rows = []
    deferred = []
    for table, constraints in sort_tables_and_constraints(tables):
        if table is None:
            deferred.extend(
                str(AddConstraint(c).compile(dialect=pg)).strip()
                for c in sorted(constraints, key=lambda c: c.name)
            )
            continue
        create = str(
            CreateTable(table, include_foreign_key_constraints=constraints).compile(
                dialect=pg
            )
        ).strip()
        indexes = [
            str(CreateIndex(index).compile(dialect=pg)).strip()
            for index in sorted(table.indexes, key=lambda i: i.name)
        ]
        rows.append({"name": table.name, "sql": create, "indexes": indexes})
    print(json.dumps({"tables": rows, "deferred": deferred}))


if __name__ == "__main__":
    main()
