"""Compile the additive O3A DDL for freezing and review without connecting to a DB."""

import app.main  # noqa: F401
from app.database.session import Base
from app.modules.field_operations.consumer_models import FieldConsumerDecision
from app.modules.field_operations.execution_models import MODELS
from app.modules.field_operations.models import CORE_MODELS
from sqlalchemy import create_mock_engine


def emit(statement, *args, **kwargs):
    print(str(statement.compile(dialect=engine.dialect)).strip() + ";\n")


engine = create_mock_engine("postgresql://", emit)
Base.metadata.create_all(
    engine,
    tables=[row.__table__ for row in (*CORE_MODELS, *MODELS, FieldConsumerDecision)],
    checkfirst=False,
)
