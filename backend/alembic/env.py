from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.core.config import get_settings
from app.database.session import Base
from app.domain import models  # noqa: F401
from app.modules.basic_data import models as basic_data_models  # noqa: F401
from app.modules.business_analysis import models as business_analysis_models  # noqa: F401
from app.modules.business_case import models as business_case_models  # noqa: F401
from app.modules.capital_planning import models as capital_planning_models  # noqa: F401
from app.modules.commercial_strategy import models as commercial_strategy_models  # noqa: F401
from app.modules.economic_financial_model import models as economic_financial_model_models  # noqa: F401
from app.modules.enterprise_structure import models as enterprise_structure_models  # noqa: F401
from app.modules.funds_manager import models as funds_manager_models  # noqa: F401
from app.modules.idea_demand import models as idea_demand_models  # noqa: F401
from app.modules.investment_decision import models as investment_decision_models  # noqa: F401
from app.modules.owner_capability import models as owner_capability_models  # noqa: F401
from app.modules.permit_readiness import models as permit_readiness_models  # noqa: F401
from app.modules.physical_workspace_creation import models as physical_workspace_creation_models  # noqa: F401
from app.modules.physical_workspace_initialization import (
    models as physical_workspace_initialization_models,  # noqa: F401
)
from app.modules.portfolio_planning import models as portfolio_planning_models  # noqa: F401
from app.modules.portfolio_review import models as portfolio_review_models  # noqa: F401
from app.modules.post_fid_governance import models as post_fid_governance_models  # noqa: F401
from app.modules.project_creation import models as project_creation_models  # noqa: F401
from app.modules.project_definition import models as project_definition_models  # noqa: F401
from app.modules.project_proposal import models as project_proposal_models  # noqa: F401
from app.modules.project_workspace_initialization import models as project_workspace_initialization_models  # noqa: F401
from app.modules.qra_foundation import models as qra_foundation_models  # noqa: F401
from app.modules.risk_readiness import models as risk_readiness_models  # noqa: F401
from app.modules.strategic_benefits import models as strategic_benefits_models  # noqa: F401
from app.modules.strategic_gate import models as strategic_gate_models  # noqa: F401
from app.modules.workspace_context import models as workspace_context_models  # noqa: F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

settings = get_settings()
config.set_main_option("sqlalchemy.url", settings.database_url)
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
