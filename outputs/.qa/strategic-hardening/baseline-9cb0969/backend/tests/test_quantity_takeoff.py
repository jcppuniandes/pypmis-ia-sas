from io import BytesIO
from uuid import uuid4
from zipfile import ZIP_DEFLATED, ZipFile

from fastapi.testclient import TestClient

from app.database.session import SessionLocal
from app.domain.models import WorkPackage
from app.main import app
from app.services.quantity_takeoff import QuantityTakeoffService


def test_quantity_takeoff_uploads_excel_and_marks_mapping_status() -> None:
    with TestClient(app) as client:
        headers = _auth_headers(client)
        suffix = uuid4().hex[:8]
        project_id = _create_project(client, headers, suffix)
        wbs = client.post(
            f"/api/v1/projects/{project_id}/wbs",
            headers=headers,
            json={"code": f"QTO-WBS-{suffix}", "name": "Civil concrete", "level": 2, "status": "active"},
        ).json()
        cbs = client.post(
            f"/api/v1/projects/{project_id}/cbs",
            headers=headers,
            json={"code": f"QTO-CBS-{suffix}", "cost_category": "Concrete", "level": 2, "status": "active"},
        ).json()
        fbs = client.post(
            f"/api/v1/projects/{project_id}/fbs",
            headers=headers,
            json={
                "code": f"QTO-FBS-{suffix}",
                "name": "AFE concrete",
                "source_of_funds": "Corporate Budget",
                "funding_type": "CAPEX",
                "authorization_ref": f"AFE-{suffix}",
                "amount": 100000,
                "currency": "USD",
                "status": "approved",
            },
        ).json()

        upload_response = client.post(
            f"/api/v1/projects/{project_id}/quantity-takeoffs/import",
            headers=headers,
            files={
                "file": (
                    "bim-quantities.xlsx",
                    _quantity_xlsx(
                        [
                            [
                                "element_guid",
                                "ifc_class",
                                "category",
                                "family",
                                "type",
                                "instance",
                                "storey",
                                "system",
                                "zone",
                                "assembly",
                                "classification_system",
                                "classification_code",
                                "quantity",
                                "unit",
                                "measurement_rule",
                                "wbs_code",
                                "cbs_code",
                                "fbs_code",
                                "package_code",
                            ],
                            [
                                "GUID-001",
                                "IfcWall",
                                "Muros",
                                "Muro concreto",
                                "20 cm",
                                "Muro eje A",
                                "Nivel 1",
                                "",
                                "Zona A",
                                "Modulo Civil",
                                "MasterFormat",
                                "03 30 00",
                                "12.5",
                                "m3",
                                "NetVolume",
                                wbs["code"],
                                cbs["code"],
                                fbs["code"],
                                "CWP-CIV-001",
                            ],
                            [
                                "GUID-002",
                                "IfcDoor",
                                "Puertas",
                                "Puerta madera",
                                "90x210",
                                "Puerta oficina",
                                "Nivel 1",
                                "",
                                "Zona A",
                                "Modulo Arquitectura",
                                "MasterFormat",
                                "08 11 00",
                                "3",
                                "und",
                                "Count",
                                "UNKNOWN-WBS",
                                "",
                                fbs["code"],
                                "CWP-ARQ-001",
                            ],
                            [
                                "GUID-003",
                                "IfcSlab",
                                "Losas",
                                "Losa concreto",
                                "15 cm",
                                "Losa nivel 1",
                                "Nivel 1",
                                "",
                                "Zona A",
                                "Modulo Civil",
                                "MasterFormat",
                                "03 30 00",
                                "5",
                                "m3",
                                "NetVolume",
                                wbs["code"],
                                cbs["code"],
                                fbs["code"],
                                "",
                            ],
                        ]
                    ),
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )
        run = upload_response.json()
        lines_response = client.get(
            f"/api/v1/projects/{project_id}/quantity-takeoff-runs/{run.get('id', 0)}/lines",
            headers=headers,
        )

    assert upload_response.status_code == 200
    assert run["source_file_name"] == "bim-quantities.xlsx"
    assert run["source_type"] == "xlsx"
    assert run["row_count"] == 3
    assert run["mapped_line_count"] == 1
    assert run["unmapped_line_count"] == 2
    assert run["total_quantity"] == 20.5
    assert "1 mapped" in run["validation_summary"]
    assert lines_response.status_code == 200
    lines = lines_response.json()
    assert len(lines) == 3
    mapped = next(line for line in lines if line["element_guid"] == "GUID-001")
    assert mapped["mapping_status"] == "mapped"
    assert mapped["ifc_class"] == "IfcWall"
    assert mapped["raw_data"]["quantity_rule"]["status"] == "valid"
    assert mapped["raw_data"]["quantity_rule"]["confidence"] == "Media"
    assert mapped["raw_data"]["quantity_rule"]["source"] == "Plantilla Excel/CSV controlada"
    assert "m2" in mapped["raw_data"]["quantity_rule"]["expected_units"]
    assert mapped["category"] == "Muros"
    assert mapped["family"] == "Muro concreto"
    assert mapped["type_name"] == "20 cm"
    assert mapped["instance_name"] == "Muro eje A"
    assert mapped["storey"] == "Nivel 1"
    assert mapped["classification_system"] == "MasterFormat"
    assert mapped["classification_code"] == "03 30 00"
    assert mapped["wbs_code"] == wbs["code"]
    assert mapped["cbs_code"] == cbs["code"]
    assert mapped["fbs_code"] == fbs["code"]
    assert mapped["wbs_id"] == wbs["id"]
    assert mapped["cbs_id"] == cbs["id"]
    assert mapped["fbs_id"] == fbs["id"]
    assert mapped["work_package_id"] is None
    unmapped = next(line for line in lines if line["element_guid"] == "GUID-002")
    assert unmapped["mapping_status"] == "needs_mapping"
    assert "Unknown WBS" in unmapped["validation_notes"]
    assert "Missing CBS" in unmapped["validation_notes"]
    missing_package = next(line for line in lines if line["element_guid"] == "GUID-003")
    assert missing_package["mapping_status"] == "needs_mapping"
    assert "Missing package" in missing_package["validation_notes"]


def test_quantity_takeoff_controlled_measurement_approval_versions_lines() -> None:
    with TestClient(app) as client:
        headers = _auth_headers(client)
        suffix = uuid4().hex[:8]
        project_id = _create_project(client, headers, suffix)
        upload_response = client.post(
            f"/api/v1/projects/{project_id}/quantity-takeoffs/import",
            headers=headers,
            files={
                "file": (
                    "controlled-quantities.xlsx",
                    _quantity_xlsx(
                        [
                            [
                                "element_guid",
                                "ifc_class",
                                "category",
                                "quantity",
                                "unit",
                                "measurement_rule",
                                "wbs_code",
                                "cbs_code",
                                "fbs_code",
                                "package_code",
                            ],
                            [
                                "GUID-APPROVE-001",
                                "IfcWall",
                                "Muros",
                                "12.5",
                                "m2",
                                "NetSideArea",
                                "WBS-PENDING",
                                "CBS-PENDING",
                                "FBS-PENDING",
                                "IWP-CIV-001",
                            ],
                        ]
                    ),
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )
        run = upload_response.json()
        lines = client.get(
            f"/api/v1/projects/{project_id}/quantity-takeoff-runs/{run.get('id', 0)}/lines",
            headers=headers,
        ).json()
        line_id = lines[0]["id"]

        approval_response = client.post(
            f"/api/v1/projects/{project_id}/quantity-takeoff-runs/{run['id']}/controlled-measurements",
            headers=headers,
            json={
                "line_ids": [line_id],
                "measurement_rule": "NetSideArea",
                "source": "Quantity table review",
                "note": "Validated against BIM quantity table",
            },
        )
        second_response = client.post(
            f"/api/v1/projects/{project_id}/quantity-takeoff-runs/{run['id']}/controlled-measurements",
            headers=headers,
            json={
                "line_ids": [line_id],
                "measurement_rule": "GeometryAreaBBox",
                "quantity": 13.75,
                "unit": "m2",
                "source": "IFC geometry inspection",
                "note": "Reviewer changed the accepted rule",
            },
        )

    assert upload_response.status_code == 200
    assert approval_response.status_code == 200
    approved = approval_response.json()[0]
    assert approved["quantity"] == 12.5
    assert approved["unit"] == "m2"
    assert approved["raw_data"]["controlled_measurement"]["status"] == "approved"
    assert approved["raw_data"]["controlled_measurement"]["version"] == 1
    assert approved["raw_data"]["controlled_measurement"]["source"] == "Quantity table review"
    assert approved["raw_data"]["controlled_measurement"]["approved_by"]
    assert "Controlled measurement approved v1" in approved["validation_notes"]

    assert second_response.status_code == 200
    revised = second_response.json()[0]
    assert revised["raw_data"]["controlled_measurement"]["version"] == 2
    assert revised["raw_data"]["controlled_measurement"]["measurement_rule"] == "GeometryAreaBBox"
    assert revised["raw_data"]["controlled_measurement"]["quantity"] == 13.75
    assert revised["raw_data"]["controlled_measurement"]["unit"] == "m2"
    assert revised["raw_data"]["controlled_measurement"]["source_quantity"] == 12.5
    assert revised["raw_data"]["controlled_measurement"]["source_unit"] == "m2"
    assert revised["raw_data"]["controlled_measurement_history"][0]["version"] == 1
    assert "Controlled measurement approved v2" in revised["validation_notes"]
    assert revised["raw_data"]["quantity_rule"]["status"] == "valid"
    assert revised["raw_data"]["quantity_rule"]["source"] == "Calculo geometrico desde IFC"
    assert revised["raw_data"]["quantity_rule"]["preferred_measure"] == "area"
    assert revised["raw_data"]["quantity_rule"]["preferred_unit"] == "m2"


def test_quantity_takeoff_assigns_control_codes_to_approved_lines() -> None:
    with TestClient(app) as client:
        headers = _auth_headers(client)
        suffix = uuid4().hex[:8]
        project_id = _create_project(client, headers, suffix)
        wbs = client.post(
            f"/api/v1/projects/{project_id}/wbs",
            headers=headers,
            json={"code": f"QTO-WBS-{suffix}", "name": "Civil area", "level": 2, "status": "active"},
        ).json()
        cbs = client.post(
            f"/api/v1/projects/{project_id}/cbs",
            headers=headers,
            json={"code": f"QTO-CBS-{suffix}", "cost_category": "Concrete", "level": 2, "status": "active"},
        ).json()
        fbs = client.post(
            f"/api/v1/projects/{project_id}/fbs",
            headers=headers,
            json={
                "code": f"QTO-FBS-{suffix}",
                "name": "AFE civil",
                "source_of_funds": "Corporate Budget",
                "funding_type": "CAPEX",
                "authorization_ref": f"AFE-{suffix}",
                "amount": 100000,
                "currency": "USD",
                "status": "approved",
            },
        ).json()
        package_code = f"IWP-CIV-{suffix}"
        package_id = 0
        with SessionLocal() as db:
            package = WorkPackage(
                tenant_id=1,
                project_id=project_id,
                wbs_id=wbs["id"],
                control_account_id=None,
                parent_id=None,
                package_type="IWP",
                code=package_code,
                title="Civil install package",
                description="",
                discipline="Civil",
                sequence_no=1,
                path_of_construction="Civil workface release",
                owner_role="Workface Planner",
                readiness_status="constraint_review",
                main_constraints="",
                progress_percent=0,
            )
            db.add(package)
            db.flush()
            package_id = package.id
            db.commit()

        upload_response = client.post(
            f"/api/v1/projects/{project_id}/quantity-takeoffs/import",
            headers=headers,
            files={
                "file": (
                    "pending-control-codes.xlsx",
                    _quantity_xlsx(
                        [
                            ["element_guid", "ifc_class", "category", "quantity", "unit", "measurement_rule"],
                            ["GUID-CONTROL-001", "IfcWall", "Muros", "12.5", "m2", "NetSideArea"],
                        ]
                    ),
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )
        run = upload_response.json()
        line = client.get(
            f"/api/v1/projects/{project_id}/quantity-takeoff-runs/{run.get('id', 0)}/lines",
            headers=headers,
        ).json()[0]

        assignment_response = client.post(
            f"/api/v1/projects/{project_id}/quantity-takeoff-runs/{run['id']}/control-code-assignments",
            headers=headers,
            json={
                "line_ids": [line["id"]],
                "wbs_code": wbs["code"],
                "cbs_code": cbs["code"],
                "fbs_code": fbs["code"],
                "package_code": package_code,
                "cost_item_code": f"PART-CIV-{suffix}",
                "cost_item_name": "Muro concreto 20 cm",
                "budget_unit": "m2",
                "unit_rate": 180.5,
                "currency": "COP",
                "catalog_item_id": 77,
                "source_key": "invias_reference_apu",
                "source_url": "https://example.test/apu/77",
                "license_note": "Referencia publica; validar vigencia.",
                "apu_structure": [
                    {
                        "component": "Materiales",
                        "component_type": "MATERIAL",
                        "description": "Concreto y acero",
                        "quantity": 1,
                        "unit": "m2",
                        "unit_rate": 120.5,
                        "amount": 120.5,
                    },
                    {
                        "component": "Mano de obra",
                        "component_type": "LABOR",
                        "description": "Cuadrilla",
                        "quantity": 1,
                        "unit": "m2",
                        "unit_rate": 60,
                        "amount": 60,
                    },
                ],
                "note": "Mapped from BIM quantity table",
            },
        )

    assert upload_response.status_code == 200
    assert assignment_response.status_code == 200
    assigned = assignment_response.json()[0]
    assert assigned["mapping_status"] == "mapped"
    assert assigned["wbs_code"] == wbs["code"]
    assert assigned["cbs_code"] == cbs["code"]
    assert assigned["fbs_code"] == fbs["code"]
    assert assigned["package_code"] == package_code
    assert assigned["wbs_id"] == wbs["id"]
    assert assigned["cbs_id"] == cbs["id"]
    assert assigned["fbs_id"] == fbs["id"]
    assert assigned["work_package_id"] == package_id
    assert "Missing WBS" not in assigned["validation_notes"]
    assert "Missing CBS" not in assigned["validation_notes"]
    assert "Missing FBS" not in assigned["validation_notes"]
    assert "Missing package" not in assigned["validation_notes"]
    assert assigned["raw_data"]["control_code_assignment"]["status"] == "assigned"
    assert assigned["raw_data"]["control_code_assignment"]["note"] == "Mapped from BIM quantity table"
    assert assigned["raw_data"]["control_code_assignment"]["wbs_id"] == wbs["id"]
    assert assigned["raw_data"]["control_code_assignment"]["cbs_id"] == cbs["id"]
    assert assigned["raw_data"]["control_code_assignment"]["fbs_id"] == fbs["id"]
    assert assigned["raw_data"]["control_code_assignment"]["work_package_id"] == package_id
    assert assigned["raw_data"]["budget_item_assignment"]["cost_item_code"] == f"PART-CIV-{suffix}"
    assert assigned["raw_data"]["budget_item_assignment"]["cost_item_name"] == "Muro concreto 20 cm"
    assert assigned["raw_data"]["budget_item_assignment"]["quantity"] == 12.5
    assert assigned["raw_data"]["budget_item_assignment"]["budget_unit"] == "m2"
    assert assigned["raw_data"]["budget_item_assignment"]["unit_rate"] == 180.5
    assert assigned["raw_data"]["budget_item_assignment"]["budget_amount"] == 2256.25
    assert assigned["raw_data"]["budget_item_assignment"]["currency"] == "COP"
    assert assigned["raw_data"]["budget_item_assignment"]["catalog_item_id"] == 77
    assert assigned["raw_data"]["budget_item_assignment"]["source_key"] == "invias_reference_apu"
    assert len(assigned["raw_data"]["budget_item_assignment"]["apu_structure"]) == 2


def test_quantity_takeoff_uploads_ifc_base_quantities() -> None:
    with TestClient(app) as client:
        headers = _auth_headers(client)
        suffix = uuid4().hex[:8]
        project_id = _create_project(client, headers, f"IFC-{suffix}")

        upload_response = client.post(
            f"/api/v1/projects/{project_id}/quantity-takeoffs/import",
            headers=headers,
            files={"file": ("model.ifc", _ifc_with_quantities(), "application/octet-stream")},
        )
        run = upload_response.json()
        lines_response = client.get(
            f"/api/v1/projects/{project_id}/quantity-takeoff-runs/{run.get('id', 0)}/lines",
            headers=headers,
        )

    assert upload_response.status_code == 200
    assert run["source_type"] == "ifc"
    assert run["row_count"] == 2
    assert run["mapped_line_count"] == 0
    assert run["unmapped_line_count"] == 2
    assert run["total_quantity"] == 15.25
    lines = lines_response.json()
    assert [line["measurement_rule"] for line in lines] == ["NetSideArea", "NetVolume"]
    assert {line["unit"] for line in lines} == {"m2", "m3"}
    assert all(line["element_guid"] == "WALLGUID" for line in lines)
    assert all(line["ifc_class"] == "IfcWall" for line in lines)
    assert all(line["storey"] == "Nivel 1" for line in lines)
    assert all(line["mapping_status"] == "needs_mapping" for line in lines)
    area_line = next(line for line in lines if line["measurement_rule"] == "NetSideArea")
    calculation = area_line["raw_data"]["quantity_calculation"]
    assert calculation["source"] == "IFC Quantity Set publicado"
    assert calculation["confidence"] == "Alta"
    assert calculation["source_quantity"] == 12.5
    assert calculation["source_unit"] == "m2"
    assert calculation["recommended_quantity"] == 12.5
    assert calculation["recommended_unit"] == "m2"
    assert calculation["status"] == "usable"


def test_quantity_takeoff_serves_stored_ifc_source_file() -> None:
    ifc_content = _ifc_with_quantities()
    with TestClient(app) as client:
        headers = _auth_headers(client)
        suffix = uuid4().hex[:8]
        project_id = _create_project(client, headers, f"IFC-FILE-{suffix}")

        upload_response = client.post(
            f"/api/v1/projects/{project_id}/quantity-takeoffs/import",
            headers=headers,
            files={"file": ("stored-model.ifc", ifc_content, "application/octet-stream")},
        )
        run = upload_response.json()
        file_response = client.get(
            f"/api/v1/projects/{project_id}/quantity-takeoff-runs/{run.get('id', 0)}/ifc-file",
            headers=headers,
        )

    assert upload_response.status_code == 200
    assert file_response.status_code == 200
    assert file_response.content == ifc_content
    assert file_response.headers["content-type"].startswith("application/octet-stream")
    assert "stored-model.ifc" in file_response.headers["content-disposition"]


def test_quantity_takeoff_ifc_file_endpoint_rejects_non_ifc_runs() -> None:
    with TestClient(app) as client:
        headers = _auth_headers(client)
        suffix = uuid4().hex[:8]
        project_id = _create_project(client, headers, f"XLSX-FILE-{suffix}")

        upload_response = client.post(
            f"/api/v1/projects/{project_id}/quantity-takeoffs/import",
            headers=headers,
            files={
                "file": (
                    "bim-quantities.xlsx",
                    _quantity_xlsx(
                        [
                            ["element_guid", "ifc_class", "quantity", "unit", "measurement_rule"],
                            ["GUID-001", "IfcWall", "12.5", "m3", "NetVolume"],
                        ]
                    ),
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )
        run = upload_response.json()
        file_response = client.get(
            f"/api/v1/projects/{project_id}/quantity-takeoff-runs/{run.get('id', 0)}/ifc-file",
            headers=headers,
        )

    assert upload_response.status_code == 200
    assert file_response.status_code == 404


def test_quantity_takeoff_uploads_ifc_product_inventory_when_quantities_are_missing() -> None:
    with TestClient(app) as client:
        headers = _auth_headers(client)
        suffix = uuid4().hex[:8]
        project_id = _create_project(client, headers, f"IFC-INV-{suffix}")

        upload_response = client.post(
            f"/api/v1/projects/{project_id}/quantity-takeoffs/import",
            headers=headers,
            files={"file": ("model-without-qto.ifc", _ifc_without_quantities(), "application/octet-stream")},
        )
        run = upload_response.json()
        lines_response = client.get(
            f"/api/v1/projects/{project_id}/quantity-takeoff-runs/{run.get('id', 0)}/lines",
            headers=headers,
        )

    assert upload_response.status_code == 200
    assert run["source_type"] == "ifc"
    assert run["row_count"] == 1
    assert run["total_quantity"] == 1
    lines = lines_response.json()
    assert len(lines) == 1
    assert lines[0]["ifc_class"] == "IfcWallStandardCase"
    assert lines[0]["quantity"] == 1
    assert lines[0]["unit"] == "ea"
    assert lines[0]["measurement_rule"] == "ElementCount"
    assert lines[0]["raw_data"]["quantity_rule"]["status"] == "blocked"
    assert lines[0]["raw_data"]["quantity_rule"]["source"] == "Conteo fallback"
    assert lines[0]["raw_data"]["quantity_rule"]["confidence"] == "Media"
    assert lines[0]["raw_data"]["quantity_calculation"]["source"] == "Conteo fallback"
    assert lines[0]["raw_data"]["quantity_calculation"]["confidence"] == "Media"
    assert lines[0]["raw_data"]["quantity_calculation"]["source_quantity"] == 1
    assert lines[0]["raw_data"]["quantity_calculation"]["source_unit"] == "ea"
    assert lines[0]["raw_data"]["quantity_calculation"]["recommended_quantity"] is None
    assert lines[0]["raw_data"]["quantity_calculation"]["fallback_rule"] == "GeometryAreaBBox"
    assert lines[0]["raw_data"]["quantity_calculation"]["fallback_unit"] == "m2"
    assert lines[0]["raw_data"]["quantity_calculation"]["status"] == "requires_controlled_measurement"
    assert "No published IFC quantity found" in lines[0]["validation_notes"]


def test_quantity_takeoff_enriches_ifc_inventory_from_type_relationships() -> None:
    with TestClient(app) as client:
        headers = _auth_headers(client)
        suffix = uuid4().hex[:8]
        project_id = _create_project(client, headers, f"IFC-TYPE-{suffix}")

        upload_response = client.post(
            f"/api/v1/projects/{project_id}/quantity-takeoffs/import",
            headers=headers,
            files={"file": ("typed-model.ifc", _ifc_with_type_relationships(), "application/octet-stream")},
        )
        run = upload_response.json()
        lines_response = client.get(
            f"/api/v1/projects/{project_id}/quantity-takeoff-runs/{run.get('id', 0)}/lines",
            headers=headers,
        )

    assert upload_response.status_code == 200
    assert run["row_count"] == 2
    lines = lines_response.json()
    member = next(line for line in lines if line["element_guid"] == "MEMBERGUID")
    column = next(line for line in lines if line["element_guid"] == "COLUMNGUID")

    assert member["ifc_class"] == "IfcMember"
    assert member["category"] == "Montante de fachada"
    assert member["family"] == "Rectangular Mullion"
    assert member["type_name"] == "50 x 150mm"
    assert member["instance_name"] == "Rectangular Mullion:50 x 150mm:123"
    assert member["raw_data"]["ifc_type_entity"] == "IFCMEMBERTYPE"
    assert member["raw_data"]["ifc_predefined_type"] == "MULLION"

    assert column["ifc_class"] == "IfcColumn"
    assert column["category"] == "Columna"
    assert column["family"] == "UC-Universal Columns-Column"
    assert column["type_name"] == "UC305x305x97"
    assert column["raw_data"]["ifc_type_entity"] == "IFCCOLUMNTYPE"
    assert column["raw_data"]["ifc_predefined_type"] == "COLUMN"


def test_quantity_takeoff_accepts_ifc_quantity_export_above_legacy_guard() -> None:
    legacy_ifc_guard_bytes = 8 * 1024 * 1024
    service = QuantityTakeoffService(db=None)  # type: ignore[arg-type]

    service._validate_ifc_takeoff_size(b" " * (legacy_ifc_guard_bytes + 1))


def _auth_headers(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "ana.control@demo.local", "password": "1234", "tenant_slug": "demo-energy"},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _create_project(client: TestClient, headers: dict[str, str], suffix: str) -> int:
    response = client.post(
        "/api/v1/projects",
        headers=headers,
        json={
            "code": f"QTO-{suffix}",
            "name": "Quantity takeoff project",
            "phase": "Planning",
            "currency": "USD",
            "calendar_base": "5x8 Colombia",
            "owner": "Owner PMO",
            "status": "authorized",
            "authorization_ref": f"AFE-QTO-{suffix}",
        },
    )
    assert response.status_code == 200
    return int(response.json()["id"])


def _quantity_xlsx(rows: list[list[str]]) -> bytes:
    shared_strings: list[str] = []
    shared_index: dict[str, int] = {}

    def shared(value: str) -> int:
        if value not in shared_index:
            shared_index[value] = len(shared_strings)
            shared_strings.append(value)
        return shared_index[value]

    sheet_rows: list[str] = []
    for row_idx, row in enumerate(rows, start=1):
        cells = []
        for col_idx, value in enumerate(row, start=1):
            ref = f"{_column_name(col_idx)}{row_idx}"
            cells.append(f'<c r="{ref}" t="s"><v>{shared(value)}</v></c>')
        sheet_rows.append(f'<row r="{row_idx}">{"".join(cells)}</row>')

    content = BytesIO()
    with ZipFile(content, "w", ZIP_DEFLATED) as archive:
        archive.writestr(
            "[Content_Types].xml",
            """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
  <Override PartName="/xl/sharedStrings.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/>
</Types>""",
        )
        archive.writestr(
            "_rels/.rels",
            """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>""",
        )
        archive.writestr(
            "xl/workbook.xml",
            """<?xml version="1.0" encoding="UTF-8"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets><sheet name="Quantities" sheetId="1" r:id="rId1"/></sheets>
</workbook>""",
        )
        archive.writestr(
            "xl/_rels/workbook.xml.rels",
            """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
</Relationships>""",
        )
        archive.writestr(
            "xl/sharedStrings.xml",
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            + "".join(f"<si><t>{value}</t></si>" for value in shared_strings)
            + "</sst>",
        )
        archive.writestr(
            "xl/worksheets/sheet1.xml",
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            f"<sheetData>{''.join(sheet_rows)}</sheetData></worksheet>",
        )
    return content.getvalue()


def _column_name(index: int) -> str:
    name = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        name = chr(65 + remainder) + name
    return name


def _ifc_with_quantities() -> bytes:
    return b"""ISO-10303-21;
HEADER;
FILE_DESCRIPTION(('ViewDefinition [CoordinationView]'),'2;1');
ENDSEC;
DATA;
#10=IFCBUILDINGSTOREY('STOREYGUID',$,'Nivel 1',$,$,$,$,$,$);
#20=IFCWALL('WALLGUID',$,'Muro A',$,$,$,$,$,$);
#30=IFCQUANTITYAREA('NetSideArea',$,$,12.5,$);
#31=IFCQUANTITYVOLUME('NetVolume',$,$,2.75,$);
#40=IFCELEMENTQUANTITY('QTOGUID',$,'BaseQuantities',$,$,(#30,#31));
#50=IFCRELDEFINESBYPROPERTIES('RELQ',$,$,$,(#20),#40);
#60=IFCRELCONTAINEDINSPATIALSTRUCTURE('RELSTOREY',$,$,$,(#20),#10);
ENDSEC;
END-ISO-10303-21;
"""


def _ifc_without_quantities() -> bytes:
    geometry_noise = "\n".join(f"#{1000 + index}=IFCCARTESIANPOINT(({index}.0,0.,0.));" for index in range(1500))
    return f"""ISO-10303-21;
HEADER;
FILE_DESCRIPTION(('ViewDefinition [CoordinationView]'),'2;1');
ENDSEC;
DATA;
#10=IFCPROJECT('PROJECTGUID',$,'Wellness Center',$,$,$,$,$,$);
#20=IFCSITE('SITEGUID',$,'Main Site',$,$,$,$,$,$,$,$,$,$,$);
#30=IFCBUILDING('BUILDINGGUID',$,'Building A',$,$,$,$,$,$,$,$,$);
#40=IFCBUILDINGSTOREY('STOREYGUID',$,'Nivel 1',$,$,$,$,$,$);
#50=IFCWALLSTANDARDCASE('WALLGUID',$,'Muro exterior',$,$,$,$,$,$);
#60=IFCRELCONTAINEDINSPATIALSTRUCTURE('RELSTOREY',$,$,$,(#50),#40);
{geometry_noise}
ENDSEC;
END-ISO-10303-21;
""".encode()


def _ifc_with_type_relationships() -> bytes:
    return b"""ISO-10303-21;
HEADER;
FILE_DESCRIPTION(('ViewDefinition [CoordinationView]'),'2;1');
ENDSEC;
DATA;
#10=IFCPROJECT('PROJECTGUID',$,'Wellness Center',$,$,$,$,$,$);
#40=IFCBUILDINGSTOREY('STOREYGUID',$,'Ground floor',$,$,$,$,$,$);
#50=IFCMEMBER('MEMBERGUID',$,'Rectangular Mullion:50 x 150mm:123',$,'Rectangular Mullion:50 x 150mm',$,$,$,'123');
#60=IFCMEMBERTYPE('TYPEGUID',$,'Rectangular Mullion:50 x 150mm',$,$,$,$,'8486',$,.MULLION.);
#70=IFCRELDEFINESBYTYPE('RELT',$,$,$,(#50),#60);
#80=IFCCOLUMN('COLUMNGUID',$,'UC-Universal Columns-Column:UC305x305x97:552739',$,'UC-Universal Columns-Column:UC305x305x97',$,$,$,'552739');
#90=IFCCOLUMNTYPE('COLTYPEGUID',$,'UC-Universal Columns-Column:UC305x305x97',$,$,$,$,'12190',$,.COLUMN.);
#100=IFCRELDEFINESBYTYPE('RELC',$,$,$,(#80),#90);
#110=IFCRELCONTAINEDINSPATIALSTRUCTURE('RELSTOREY',$,$,$,(#50,#80),#40);
ENDSEC;
END-ISO-10303-21;
"""
