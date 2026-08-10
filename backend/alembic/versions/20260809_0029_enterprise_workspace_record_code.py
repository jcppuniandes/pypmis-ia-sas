"""add visible hierarchical record code to enterprise workspaces

Revision ID: 20260809_0029
Revises: 20260806_0028
Create Date: 2026-08-09
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260809_0029"
down_revision: str | None = "20260806_0028"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _segment(sequence: int) -> str:
    return f"{sequence:02d}"


def _backfill_tenant(bind: sa.Connection, workspace: sa.TableClause, tenant_rows: list[dict]) -> None:
    ids = {int(row["id"]) for row in tenant_rows}
    children: dict[int | None, list[dict]] = defaultdict(list)
    for row in tenant_rows:
        parent_id = row["parent_id"] if row["parent_id"] in ids else None
        children[parent_id].append(row)

    assigned: set[int] = set()

    def assign(parent_id: int | None, prefix: str | None) -> None:
        siblings = sorted(
            children.get(parent_id, []),
            key=lambda item: (item["sort_order"] or 0, str(item["name"]).casefold(), item["id"]),
        )
        for index, row in enumerate(siblings, start=1):
            record_code = f"{prefix}.{_segment(index)}" if prefix else _segment(index)
            bind.execute(
                sa.update(workspace).where(workspace.c.id == row["id"]).values(record_code=record_code)
            )
            assigned.add(int(row["id"]))
            assign(int(row["id"]), record_code)

    assign(None, None)
    if assigned != ids:
        raise RuntimeError("Cannot backfill record_code while the hierarchy contains a cycle")


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("enterprise_workspaces")}
    if "record_code" not in columns:
        op.add_column("enterprise_workspaces", sa.Column("record_code", sa.String(length=255), nullable=True))

    workspace = sa.table(
        "enterprise_workspaces",
        sa.column("id", sa.Integer),
        sa.column("tenant_id", sa.Integer),
        sa.column("parent_id", sa.Integer),
        sa.column("sort_order", sa.Integer),
        sa.column("name", sa.String),
        sa.column("record_code", sa.String),
    )
    rows = list(
        bind.execute(
            sa.select(
                workspace.c.id,
                workspace.c.tenant_id,
                workspace.c.parent_id,
                workspace.c.sort_order,
                workspace.c.name,
            ).order_by(workspace.c.tenant_id, workspace.c.id)
        ).mappings()
    )
    by_tenant: dict[int, list[dict]] = defaultdict(list)
    for row in rows:
        by_tenant[int(row["tenant_id"])].append(dict(row))

    for tenant_rows in by_tenant.values():
        _backfill_tenant(bind, workspace, tenant_rows)

    with op.batch_alter_table("enterprise_workspaces") as batch:
        batch.alter_column("record_code", existing_type=sa.String(length=255), nullable=False)
        batch.create_unique_constraint(
            "uq_enterprise_workspace_record_code",
            ["tenant_id", "record_code"],
        )


def downgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("enterprise_workspaces")}
    if "record_code" in columns:
        with op.batch_alter_table("enterprise_workspaces") as batch:
            batch.drop_constraint("uq_enterprise_workspace_record_code", type_="unique")
            batch.drop_column("record_code")
