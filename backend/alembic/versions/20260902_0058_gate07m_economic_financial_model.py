"""add Gate 07M-FIN governed economic-financial model and readiness

Revision ID: 20260902_0058
Revises: 20260902_0057
Create Date: 2026-09-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.database.session import Base
from app.modules.economic_financial_model import models as _economic_financial_models  # noqa: F401
from app.modules.portfolio_budget import models as _portfolio_budget_models  # noqa: F401

revision: str = "20260902_0058"
down_revision: str | None = "20260902_0057"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = (
    "economic_financial_models",
    "economic_financial_model_versions",
    "financial_model_assumptions",
    "financial_model_periods",
    "financial_model_financing_instruments",
    "financial_model_investors",
    "financial_model_scenarios",
    "financial_model_scenario_overrides",
    "financial_model_cash_flows",
    "financial_model_debt_schedules",
    "financial_model_metric_results",
    "financial_model_sensitivity_results",
)


def upgrade() -> None:
    bind = op.get_bind()
    existing = set(sa.inspect(bind).get_table_names())
    for table_name in TABLES:
        if table_name not in existing:
            Base.metadata.tables[table_name].create(bind=bind, checkfirst=True)
    foreign_keys = {item["name"] for item in sa.inspect(bind).get_foreign_keys("economic_financial_models")}
    if "fk_economic_financial_model_current_version" not in foreign_keys:
        op.create_foreign_key(
            "fk_economic_financial_model_current_version",
            "economic_financial_models",
            "economic_financial_model_versions",
            ["current_version_id"],
            ["id"],
            ondelete="RESTRICT",
        )


def downgrade() -> None:
    bind = op.get_bind()
    existing = set(sa.inspect(bind).get_table_names())
    if "economic_financial_models" in existing:
        foreign_keys = {item["name"] for item in sa.inspect(bind).get_foreign_keys("economic_financial_models")}
        if "fk_economic_financial_model_current_version" in foreign_keys:
            op.drop_constraint(
                "fk_economic_financial_model_current_version",
                "economic_financial_models",
                type_="foreignkey",
            )
    for table_name in reversed(TABLES):
        if table_name in existing:
            op.drop_table(table_name)
