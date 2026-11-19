"""Read-only material evidence consumed by AWP, with no release authority."""

from sqlalchemy import inspect, select

from app.modules.procurement_foundation.integration_models import ProcurementMapping


def material_reader(db, tenant, workspace):
    if not inspect(db.connection()).has_table(ProcurementMapping.__tablename__):
        return None
    mapped = db.scalar(
        select(ProcurementMapping.id)
        .where(
            ProcurementMapping.tenant_id == tenant,
            ProcurementMapping.project_workspace_id == workspace,
            ProcurementMapping.source_kind == "MATERIAL_REQUIREMENT",
            ProcurementMapping.target_kind.in_(("CWP", "IWP")),
        )
        .limit(1)
    )
    if mapped is None:
        return None
    from app.modules.procurement_foundation.availability import material_availability

    cache = {}

    def resolve(package, as_of=None):
        if package.package_type not in {"CWP", "IWP"}:
            return None
        key = (package.id, as_of)
        if key not in cache:
            result = material_availability(db, tenant, workspace, package.id, as_of=as_of)
            # Procurement details and CDE references are not AWP disclosure rights.
            cache[key] = (
                {
                    field: result[field]
                    for field in (
                        "provider_key",
                        "work_package_id",
                        "status",
                        "as_of",
                        "coverage",
                        "reason_codes",
                        "evidence_hash",
                    )
                }
                if result
                else None
            )
        return cache[key]

    return resolve
