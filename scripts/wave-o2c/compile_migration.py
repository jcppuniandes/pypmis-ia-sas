"""Compile a frozen O2C migration schema for source review, without a database."""

from sqlalchemy import create_mock_engine

import app.main  # noqa: F401
from app.database.session import Base
from app.modules.contracts_foundation.commercial_models import MODELS
from app.modules.contracts_foundation.cost_consumer_models import CostCommercialAdoption
from app.modules.contracts_foundation.models import CORE_MODELS


def compile_statement(statement, *args, **kwargs):
    print(str(statement.compile(dialect=engine.dialect)).strip() + ";\n")


engine = create_mock_engine("postgresql://", compile_statement)
Base.metadata.create_all(
    engine, tables=[model.__table__ for model in (*CORE_MODELS, *MODELS, CostCommercialAdoption)], checkfirst=False
)
