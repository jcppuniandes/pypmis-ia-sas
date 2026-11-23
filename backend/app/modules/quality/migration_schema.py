"""Quality governance requires Alembic constraints and triggers, never startup DDL."""

from app.modules.quality.consumer_models import MODELS as SUPPORT_MODELS
from app.modules.quality.execution_models import MODELS as EXECUTION_MODELS
from app.modules.quality.models import CORE_MODELS

QUALITY_MIGRATION_TABLE_NAMES = {row.__tablename__ for row in (*CORE_MODELS, *EXECUTION_MODELS, *SUPPORT_MODELS)}
