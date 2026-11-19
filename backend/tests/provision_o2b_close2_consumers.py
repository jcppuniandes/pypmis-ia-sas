"""Populate a fresh browser-only tenant with adopted consumer references."""

import json
import os
from datetime import timedelta
from pathlib import Path

from fastapi.testclient import TestClient
from tests.engineering_release_fixture import TODAY
from tests.o2b_close_isolation import is_close_consumer_database
from tests.test_procurement_consumer_release import create_governed_fixture, decide, decision, lookup
from tests.test_procurement_o2b_release import cmd

from app.database.session import SessionLocal
from app.main import app


def main():
    assert os.getenv("PYPMIS_O2B_CLOSE2_BROWSER_FIXTURE") == "disposable-only"
    target = Path(os.environ["PYPMIS_CLOSE2_BROWSER_MANIFEST"]).resolve()
    assert target.name == "consumer-fixture.json" and ".qa" in target.parts and "private" in target.parts
    with SessionLocal() as db, TestClient(app) as client:
        assert is_close_consumer_database(db)
        f = create_governed_fixture(db, client, credentials=True)
        period = f.current_period["id"]
        source_context = {"period_id": period}
        receipt = lookup(f, "progress", "RECEIPT", f.chain["receipt"]["id"], **source_context)
        receipt_adoption = decide(f, "progress", decision(receipt, **source_context))
        milestone = cmd(
            f,
            "/vendor-milestones",
            {
                "po_line_id": f.chain["po_line"]["id"],
                "code": "CLOSE2-MANUFACTURE",
                "planned_date": (TODAY + timedelta(days=4)).isoformat(),
                "forecast_date": (TODAY + timedelta(days=5)).isoformat(),
            },
            actor="material",
        )
        forecast_context = source_context | {
            "consumer_version_id": f.draft_forecast["id"],
            "signal_key": "forecast_date",
        }
        signal = lookup(f, "forecast", "MILESTONE_FORECAST", milestone["id"], **forecast_context)
        signal_adoption = decide(
            f,
            "forecast",
            decision(
                signal,
                **forecast_context,
                consumer_version=f.draft_forecast["version"],
            ),
        )
        document = {
            "tenant_id": f.tenant_id,
            "project_workspace_id": f.project_workspace_id,
            "password": f.password,
            "users": {"manager": {"email": f.users["manager"].email}},
            "progress": source_context
            | {
                "source_entity_type": "RECEIPT",
                "source_entity_id": receipt["source_id"],
                "source_hash": receipt["source_hash"],
                "adoption_id": receipt_adoption["id"],
            },
            "forecast": forecast_context
            | {
                "source_entity_type": "MILESTONE_FORECAST",
                "source_entity_id": signal["source_id"],
                "source_hash": signal["source_hash"],
                "source_forecast_date": signal_adoption["source_forecast_date"],
                "adoption_id": signal_adoption["id"],
            },
        }
        with target.open("x", encoding="utf-8") as file:
            json.dump(document, file, indent=2)


if __name__ == "__main__":
    main()
