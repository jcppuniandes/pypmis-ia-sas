"""Prepare revision 0042 from current metadata in an ephemeral Gate 07D database.

This script is intentionally destructive and must only run against the disposable
PostgreSQL database created by ``docker-compose.gate07d.yml``.
"""

from sqlalchemy import inspect

from app.database.session import Base, engine
from app.domain import models as domain_models  # noqa: F401
from app.modules.enterprise_structure import models as enterprise_models  # noqa: F401
from app.modules.idea_demand import models as idea_models  # noqa: F401
from app.modules.physical_workspace_creation import models as physical_creation_models  # noqa: F401
from app.modules.physical_workspace_initialization import models as physical_initialization_models  # noqa: F401
from app.modules.portfolio_planning import models as portfolio_planning_models  # noqa: F401
from app.modules.project_creation import models as project_creation_models  # noqa: F401
from app.modules.project_proposal import models as project_proposal_models  # noqa: F401
from app.modules.project_workspace_initialization import models as project_initialization_models  # noqa: F401
from app.modules.strategic_gate import models as strategic_gate_models  # noqa: F401
from app.modules.workspace_context import models as workspace_context_models  # noqa: F401

GATE07D_COLUMNS = (
    "source_context_type",
    "strategic_gate_decision_id",
    "source_project_proposal_id",
    "source_idea_id",
    "source_decision_hash",
    "source_readiness_hash",
    "strategic_target_portfolio_workspace_id",
    "strategic_mapping_configuration_id",
    "strategic_mapping_revision",
    "strategic_mapping_hash",
    "strategic_source_snapshot_json",
)

MULTI_SOURCE_COLUMNS = (
    "governance_model",
    "source_context_id",
    "source_external_key",
    "idempotency_key",
    "source_snapshot_json",
    "source_hash",
    "creation_policy_id",
    "creation_policy_revision",
    "creation_policy_hash",
)


def main() -> None:
    if engine.dialect.name != "postgresql" or engine.url.database != "gate07d":
        raise RuntimeError("Gate 07D baseline preparation requires the disposable gate07d PostgreSQL database")
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        if "portfolio_project_memberships" in inspect(connection).get_table_names():
            connection.exec_driver_sql("DROP TABLE portfolio_project_memberships CASCADE")
        connection.exec_driver_sql(
            "ALTER TABLE project_creation_requests DROP CONSTRAINT IF EXISTS uq_project_creation_strategic_decision"
        )
        for column in (*GATE07D_COLUMNS, *MULTI_SOURCE_COLUMNS):
            connection.exec_driver_sql(
                f'ALTER TABLE project_creation_requests DROP COLUMN IF EXISTS "{column}" CASCADE'
            )


if __name__ == "__main__":
    main()
