"""Deterministic, read-only inventory and fingerprints for controlled CORE gates."""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import MetaData, Table, inspect, select
from sqlalchemy.orm import Session

from app.domain.models import (
    AdminConfiguration,
    EnterpriseWorkspace,
    SecurityEvent,
    Tenant,
    UserAccount,
    WorkspaceModuleSetting,
)
from app.modules.enterprise_structure.models import (
    EnterpriseCoreRelease,
    EnterpriseStrategicObjective,
    EnterpriseWorkspaceClassification,
    EnterpriseWorkspaceLink,
)

PROTECTED_MODELS = {
    "tenants": Tenant,
    "enterprise_workspaces": EnterpriseWorkspace,
    "enterprise_workspace_classifications": EnterpriseWorkspaceClassification,
    "enterprise_workspace_links": EnterpriseWorkspaceLink,
    "workspace_module_settings": WorkspaceModuleSetting,
    "admin_configurations": AdminConfiguration,
    "security_events": SecurityEvent,
    "user_accounts": UserAccount,
}
FINGERPRINT_EXCLUDED_COLUMNS = {
    "enterprise_workspaces": {"external_key"},
}


def capture_inventory(db: Session) -> dict[str, Any]:
    tables = {name: _rows(db, model) for name, model in PROTECTED_MODELS.items()}
    objectives = (
        _rows(db, EnterpriseStrategicObjective)
        if EnterpriseStrategicObjective.__tablename__ in inspect(db.get_bind()).get_table_names()
        else []
    )
    releases = (
        _rows(db, EnterpriseCoreRelease)
        if EnterpriseCoreRelease.__tablename__ in inspect(db.get_bind()).get_table_names()
        else []
    )
    return {
        "algorithm": "ordered-primary-key/canonical-json-v1",
        "tables": tables,
        "supplemental": {
            "enterprise_strategic_objectives": objectives,
            "enterprise_core_releases": releases,
        },
    }


def capture_fingerprints(db: Session) -> dict[str, Any]:
    inventory = capture_inventory(db)
    fingerprints = {
        name: {
            "rows": len(rows),
            "sha256": _sha256(_fingerprint_rows(name, rows)),
        }
        for name, rows in inventory["tables"].items()
    }
    protected_payload = {
        name: {"rows": value["rows"], "sha256": value["sha256"]}
        for name, value in sorted(fingerprints.items())
    }
    return {
        "algorithm": inventory["algorithm"],
        "tables": fingerprints,
        "protected_source_hash": _sha256(protected_payload),
    }


def protected_source_hash(db: Session) -> str:
    return str(capture_fingerprints(db)["protected_source_hash"])


def _rows(db: Session, model: type[Any]) -> list[dict[str, Any]]:
    table = Table(model.__tablename__, MetaData(), autoload_with=db.get_bind())
    records = list(db.execute(select(table).order_by(table.c.id)).mappings().all())
    return [
        {column.name: _jsonable(record[column.name]) for column in table.columns}
        for record in records
    ]


def _fingerprint_rows(table_name: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    excluded = FINGERPRINT_EXCLUDED_COLUMNS.get(table_name, set())
    return [
        {key: value for key, value in row.items() if key not in excluded}
        for row in rows
    ]


def _jsonable(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


def _sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
