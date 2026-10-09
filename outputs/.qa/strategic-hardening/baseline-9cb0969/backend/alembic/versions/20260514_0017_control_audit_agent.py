"""Add control audit agent run history."""

from alembic import op
import sqlalchemy as sa


revision = "20260514_0017"
down_revision = "20260514_0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())

    if "control_agent_runs" not in table_names:
        op.create_table(
            "control_agent_runs",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.Integer(), nullable=False, index=True),
            sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=False, index=True),
            sa.Column("agent_code", sa.String(length=80), nullable=False, index=True),
            sa.Column("agent_name", sa.String(length=160), nullable=False),
            sa.Column("run_mode", sa.String(length=40), nullable=False, server_default="deterministic"),
            sa.Column(
                "model_name", sa.String(length=120), nullable=False, server_default="deterministic-control-audit-v1"
            ),
            sa.Column("status", sa.String(length=40), nullable=False, server_default="completed"),
            sa.Column("score", sa.Integer(), nullable=False, server_default="100"),
            sa.Column("summary", sa.Text(), nullable=False, server_default=""),
            sa.Column("created_by", sa.String(length=160), nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )
    if "control_agent_findings" not in table_names:
        op.create_table(
            "control_agent_findings",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.Integer(), nullable=False, index=True),
            sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=False, index=True),
            sa.Column("run_id", sa.Integer(), sa.ForeignKey("control_agent_runs.id"), nullable=False, index=True),
            sa.Column("severity", sa.String(length=40), nullable=False, index=True),
            sa.Column("category", sa.String(length=80), nullable=False, index=True),
            sa.Column("title", sa.String(length=220), nullable=False),
            sa.Column("evidence", sa.Text(), nullable=False, server_default=""),
            sa.Column("recommendation", sa.Text(), nullable=False, server_default=""),
            sa.Column("owner_role", sa.String(length=120), nullable=False, server_default=""),
            sa.Column("entity_type", sa.String(length=80), nullable=False, server_default=""),
            sa.Column("entity_id", sa.Integer(), nullable=True),
            sa.Column("status", sa.String(length=40), nullable=False, server_default="open"),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )


def downgrade() -> None:
    op.drop_table("control_agent_findings")
    op.drop_table("control_agent_runs")
