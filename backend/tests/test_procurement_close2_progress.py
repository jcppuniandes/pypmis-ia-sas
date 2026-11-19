"""HTTP/SQL evidence that historical Progress pins cannot be re-adopted as current."""

import json
import os
from pathlib import Path

from sqlalchemy import text
from tests.engineering_release_fixture import request
from tests.procurement_release_fixture import REASON
from tests.test_procurement_consumer_release import decide, decision, lookup, root, signatures
from tests.test_procurement_consumer_release import governed as governed
from tests.test_procurement_o2b_release import expect, get, mapping

from app.database.session import SessionLocal

PROGRESS_TABLES = (
    "progress_measurements",
    "progress_history",
    "project_controls_periods",
    "procurement_material_receipts",
    "procurement_material_receipt_lines",
    "procurement_material_acceptances",
    "procurement_shipments",
    "procurement_shipment_lines",
)


def adoption_rows(f, source_id, period_id):
    with SessionLocal() as db:
        db.execute(text("SET TRANSACTION READ ONLY"))
        return list(
            db.scalars(
                text(
                    """
                    SELECT to_jsonb(a)
                    FROM operational_procurement_adoptions a
                    WHERE tenant_id = :tenant AND project_workspace_id = :workspace
                      AND consumer = 'PROGRESS' AND source_entity_type = 'DISPATCH'
                      AND source_entity_id = :source AND period_id = :period
                    ORDER BY version
                    """
                ),
                {"tenant": f.tenant_id, "workspace": f.project_workspace_id, "source": source_id, "period": period_id},
            )
        )


def write_proof(proof):
    if path := os.getenv("PYPMIS_CLOSE2_EVIDENCE"):
        target = Path(path).resolve() / "progress-lineage.json"
        parent = Path(__file__).resolve().parents[2] / "outputs" / ".qa"
        assert target.is_relative_to(parent) and target.relative_to(parent).parts[0].startswith("wave-o2b-close2-")
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("x", encoding="utf-8") as handle:
            json.dump(proof, handle, indent=2)


def test_progress_rejects_superseded_procurement_lineage_but_retains_history(governed):
    f = governed
    period = f.current_period["id"]
    shipment = f.chain["shipment"]["id"]
    package = f.chain["package"]["id"]
    context = {"period_id": period}
    before = signatures(f, PROGRESS_TABLES)
    assert adoption_rows(f, shipment, period) == []

    retired_iwp = expect(
        request(
            f,
            "POST",
            f.awp_root + "/packages",
            actor="admin",
            payload={
                **REASON,
                "package_code": "CLOSE2-PROGRESS-PREDECESSOR",
                "package_type": "IWP",
                "name": "Predecessor IWP for a governed Progress evidence reference",
                "cwa_id": f.cwas[0]["id"],
            },
        ),
        201,
    )
    old_link = mapping(f, "PACKAGE", package, "IWP", retired_iwp["id"])
    source = lookup(f, "progress", "DISPATCH", shipment, **context)
    original = decision(source, **context)
    assert source["source_version"] > 1
    assert source["consumer_status"] == "NOT_ADOPTED"
    assert any(link["id"] == old_link["id"] for link in source["related_mappings"])
    stale_version = decide(f, "progress", original | {"source_version": original["source_version"] - 1}, status=409)
    assert stale_version["detail"] == "PROCUREMENT_CONSUMER_SOURCE_VERSION_MISMATCH"
    wrong_hash = decide(f, "progress", original | {"source_hash": "0" * 64}, status=409)
    assert wrong_hash["detail"] == "PROCUREMENT_CONSUMER_SOURCE_HASH_MISMATCH"
    decide(f, "progress", original, workspace=f.workspaces["other_project"].id, status=403)
    decide(f, "progress", original, actor="foreign", status=404)
    prior = decide(f, "progress", original)
    [prior_sql] = adoption_rows(f, shipment, period)
    assert prior_sql["id"] == prior["id"] and prior_sql["version"] == prior["version"] == 1
    assert prior_sql["tenant_id"] == f.tenant_id and prior_sql["project_workspace_id"] == f.project_workspace_id
    assert prior_sql["created_by"] == f.users["manager"].id and prior_sql["created_at"]
    assert prior_sql["period_id"] == period and prior_sql["source_hash"] == source["source_hash"]
    assert prior_sql["source_snapshot"]["facts"]["source_event_id"] == source["facts"]["source_event_id"]

    superseded = expect(
        request(
            f,
            "POST",
            f"{f.awp_root}/packages/{retired_iwp['id']}/transition",
            actor="admin",
            payload={**REASON, "status": "SUPERSEDED"},
            version=retired_iwp["version"],
        ),
        200,
    )
    assert superseded["status"] == "SUPERSEDED"
    inactive = decide(f, "progress", original, version=prior["version"], status=409)
    assert inactive["detail"] == "PROCUREMENT_CONSUMER_INACTIVE_IWP_MAPPING"
    assert adoption_rows(f, shipment, period) == [prior_sql]
    remove_link = mapping(f, "PACKAGE", package, "IWP", retired_iwp["id"], action="REMOVE")
    next_link = mapping(f, "PACKAGE", package, "IWP", f.iwp["id"])
    assert old_link["version"] < remove_link["version"] < next_link["version"]
    mappings = get(f, "/mappings", source_kind="PACKAGE", source_id=package)["items"]
    assert {row["id"]: row["active"] for row in mappings if row["id"] in {old_link["id"], next_link["id"]}} == {
        old_link["id"]: False,
        next_link["id"]: True,
    }

    current = lookup(f, "progress", "DISPATCH", shipment, **context)
    assert current["source_version"] == source["source_version"]  # Same physical dispatch event.
    assert current["facts"] == source["facts"] and current["observed_at"] == source["observed_at"]
    assert current["source_hash"] != source["source_hash"] and current["consumer_status"] == "NOT_ADOPTED"
    assert next_link["id"] in {row["id"] for row in current["related_mappings"]}
    assert old_link["id"] not in {row["id"] for row in current["related_mappings"]}
    rejected = decide(f, "progress", original, version=prior["version"], status=409)
    assert rejected["detail"] == "PROCUREMENT_CONSUMER_SOURCE_HASH_MISMATCH"
    assert adoption_rows(f, shipment, period) == [prior_sql]
    successor = decide(f, "progress", decision(current, **context), version=prior["version"])
    assert successor["id"] != prior["id"] and successor["version"] == 2
    assert lookup(f, "progress", "DISPATCH", shipment, **context)["consumer_status"] == "ADOPTED"
    assert expect(request(f, "GET", root(f, "progress"), actor="manager"), 200)["items"] == [successor, prior]
    prior_after, current_sql = adoption_rows(f, shipment, period)
    assert prior_after == prior_sql
    assert current_sql["id"] == successor["id"] and current_sql["period_id"] == period
    assert current_sql["source_hash"] == current["source_hash"]
    after = signatures(f, PROGRESS_TABLES)
    assert before == after
    write_proof(
        {
            "control": "CLOSE-PROG-LINEAGE",
            "result": "PASS",
            "workspace": f.project_workspace_id,
            "tenant": f.tenant_id,
            "native_physical_event": {
                "type": "DISPATCH",
                "source_id": shipment,
                "event_id": source["facts"]["source_event_id"],
                "version": source["source_version"],
                "observed_at": source["observed_at"],
            },
            "lineage": {"predecessor": old_link["id"], "retired_by": remove_link["id"], "successor": next_link["id"]},
            "lineage_versions": [old_link["version"], remove_link["version"], next_link["version"]],
            "historical_decision": {
                key: prior_sql[key] for key in ("id", "period_id", "created_by", "created_at", "source_hash")
            },
            "historical_decision_unchanged": prior_after == prior_sql,
            "current_decision_id": current_sql["id"],
            "current_source_hash": current_sql["source_hash"],
            "rejected": {
                "old_version": 409,
                "invalid_hash": 409,
                "inactive_iwp": 409,
                "superseded_lineage": 409,
                "wrong_workspace": 403,
                "wrong_tenant": 404,
            },
            "protected_before": before,
            "protected_after": after,
        }
    )
