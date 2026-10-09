"""Prepare a disposable PostgreSQL database with the revision 0044 shape."""

from sqlalchemy import inspect

from app.database.session import Base, engine
from app.domain import models as domain_models  # noqa: F401
from app.modules.enterprise_structure import models as enterprise_models  # noqa: F401
from app.modules.idea_demand import models as idea_models  # noqa: F401
from app.modules.physical_workspace_creation import models as physical_creation_models  # noqa: F401
from app.modules.physical_workspace_initialization import models as physical_initialization_models  # noqa: F401
from app.modules.portfolio_evaluation import models as portfolio_evaluation_models  # noqa: F401
from app.modules.portfolio_planning import models as portfolio_planning_models  # noqa: F401
from app.modules.project_creation import models as project_creation_models  # noqa: F401
from app.modules.project_proposal import models as project_proposal_models  # noqa: F401
from app.modules.project_workspace_initialization import models as project_initialization_models  # noqa: F401
from app.modules.strategic_gate import models as strategic_gate_models  # noqa: F401
from app.modules.workspace_context import models as workspace_context_models  # noqa: F401


def main() -> None:
    if engine.dialect.name != "postgresql" or engine.url.database != "gate07e":
        raise RuntimeError("Gate 07E baseline preparation requires the disposable gate07e PostgreSQL database")
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        if "portfolio_project_evaluations" in inspect(connection).get_table_names():
            connection.exec_driver_sql("DROP TABLE portfolio_project_evaluations CASCADE")


if __name__ == "__main__":
    main()
