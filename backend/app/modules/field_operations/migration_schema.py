"""Governed Field tables require Alembic, never application startup create_all."""

from app.modules.field_operations.consumer_models import FieldConsumerDecision
from app.modules.field_operations.execution_models import MODELS
from app.modules.field_operations.models import CORE_MODELS

FIELD_MIGRATION_TABLE_NAMES = {model.__tablename__ for model in (*CORE_MODELS, *MODELS, FieldConsumerDecision)}
