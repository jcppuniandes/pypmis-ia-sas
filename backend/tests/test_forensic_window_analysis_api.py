from __future__ import annotations

from io import BytesIO
from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app


def test_window_analysis_37_endpoint_returns_windows_from_schedule_uploads() -> None:
    with TestClient(app) as client:
        headers = _auth_headers(client)
        project_id = _create_project(client, headers, uuid4().hex[:8])
        response = client.post(
            f"/api/v1/projects/{project_id}/claims/window-analysis-37",
            headers=headers,
            data={"near_critical_threshold_days": "5"},
            files=[
                ("files", ("baseline.xer", BytesIO(_xer("2026-01-01", "2026-01-20")), "text/plain")),
                ("files", ("update-01.xer", BytesIO(_xer("2026-01-11", "2026-01-25")), "text/plain")),
            ],
        )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["method_id"] == "AACE-RP29R-MIP-3.7"
    assert payload["summary"]["window_count"] == 1
    assert payload["windows"][0]["completion_slip_days"] == 5
    assert payload["rag_sources"]


def _xer(data_date: str, finish: str) -> bytes:
    return f"""%T\tPROJECT
%F\tproj_id\tproj_short_name\tlast_recalc_date\tcurrency_id
%R\t1\tPY-01\t{data_date} 08:00\tCOP
%T\tPROJWBS
%F\twbs_id\tproj_id\tseq_num\tproj_node_flag\tparent_wbs_id\twbs_short_name\twbs_name
%R\t1\t1\t1\tY\t\tPY-01\tProyecto
%R\t10\t1\t10\tN\t1\tENG\tIngenieria
%T\tTASK
%F\ttask_id\twbs_id\ttask_code\ttask_name\ttarget_start_date\ttarget_end_date\ttotal_float_hr_cnt
%R\t100\t10\tA100\tActividad critica\t2026-01-01 08:00\t{finish} 17:00\t0
""".encode()


def _auth_headers(client: TestClient) -> dict[str, str]:
    response = client.post("/api/v1/auth/login", json={"email": "ana.control@demo.local", "password": "1234"})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _create_project(client: TestClient, headers: dict[str, str], suffix: str) -> int:
    response = client.post(
        "/api/v1/projects",
        headers=headers,
        json={
            "code": f"WIN-{suffix}",
            "name": f"Proyecto Ventanas {suffix}",
            "phase": "Execution",
            "currency": "COP",
            "calendar_base": "5x8 Colombia",
            "owner": "Owner",
            "status": "authorized",
            "authorization_date": "2026-06-01",
            "authorization_ref": f"AFE-WIN-{suffix}",
            "configuration": {"claims_forensic_enabled": True},
            "start_date": "2026-06-01",
            "finish_date": "2026-12-31",
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["id"]
