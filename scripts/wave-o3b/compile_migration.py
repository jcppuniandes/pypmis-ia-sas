"""Compile reviewed O3B DDL without opening a database connection."""

import app.main  # noqa: F401
from app.database.session import Base
from app.modules.quality.consumer_models import MODELS as SUPPORT_MODELS
from app.modules.quality.execution_models import MODELS as EXECUTION_MODELS
from app.modules.quality.models import CORE_MODELS
from sqlalchemy import create_mock_engine


def emit(statement, *args, **kwargs):
    compiled = str(statement.compile(dialect=engine.dialect)).strip()
    # Metadata-level legacy enum hooks are not owned by this additive migration.
    if compiled.startswith("CREATE TYPE"):
        return
    print(compiled + ";\n")


engine = create_mock_engine("postgresql://", emit)
Base.metadata.create_all(
    engine,
    tables=[
        row.__table__ for row in (*CORE_MODELS, *EXECUTION_MODELS, *SUPPORT_MODELS)
    ],
    checkfirst=False,
)
