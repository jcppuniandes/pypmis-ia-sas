from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app
from app.services.colombia_apu_catalog import ColombiaApuCatalogService


def test_colombia_apu_catalog_syncs_public_rows_and_suggests_bim_budget_items(monkeypatch) -> None:
    public_rows = [
        {
            "code": "1.05.0101",
            "name": "Muro en concreto reforzado e=0.15 m",
            "unit": "m2",
            "group": "Edificaciones",
            "chapter": "Muros",
            "region": "Subregion Centro",
            "price": 45200,
            "source_url": "https://datacauca.gov.co/apu/apu/apu/query",
        },
        {
            "code": "1.06.0201",
            "name": "Losa maciza en concreto reforzado",
            "unit": "m2",
            "group": "Edificaciones",
            "chapter": "Losas",
            "region": "Subregion Centro",
            "price": 98600,
            "source_url": "https://datacauca.gov.co/apu/apu/apu/query",
        },
        {
            "code": "1.99.9999",
            "name": "Partida publica con descripcion extendida " + "para catalogos APU detallados " * 18,
            "unit": "un",
            "group": "Validacion",
            "chapter": "Catalogo",
            "region": "Colombia",
            "price": 1,
            "source_url": "https://datacauca.gov.co/apu/apu/apu/query",
        },
        {
            "code": "1.07.0301",
            "name": "DemoliciÃ³n con compresor de placas de piso en concreto",
            "unit": "m2",
            "group": "Edificaciones",
            "chapter": "ACTIVIDADES PRELIMINARES",
            "region": "SubregiÃ³n Centro",
            "price": 24448,
            "source_url": "https://datacauca.gov.co/apu/apu/apu/query",
        },
    ]
    monkeypatch.setattr(ColombiaApuCatalogService, "fetch_public_rows", lambda self, limit=500: public_rows)

    with TestClient(app) as client:
        headers = _auth_headers(client)
        suffix = uuid4().hex[:8]
        project_id = _create_project(client, headers, suffix)

        sync_response = client.post(
            f"/api/v1/projects/{project_id}/colombia-apu-catalog/sync",
            headers=headers,
        )
        catalog_response = client.get(
            f"/api/v1/projects/{project_id}/colombia-apu-catalog",
            headers=headers,
            params={"search": "muro concreto"},
        )
        mojibake_response = client.get(
            f"/api/v1/projects/{project_id}/colombia-apu-catalog",
            headers=headers,
            params={"search": "demolicion concreto"},
        )
        upload_response = client.post(
            f"/api/v1/projects/{project_id}/quantity-takeoffs/import",
            headers=headers,
            files={
                "file": (
                    "bim-wall.xlsx",
                    _quantity_xlsx(
                        [
                            ["element_guid", "ifc_class", "category", "family", "type_name", "quantity", "unit"],
                            ["GUID-APU-001", "IfcWall", "Muros", "Concreto", "Muro 15 cm", "12.5", "m2"],
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
        suggestion_response = client.post(
            f"/api/v1/projects/{project_id}/quantity-takeoff-runs/{run['id']}/apu-suggestions",
            headers=headers,
            json={"line_ids": [line["id"]], "apply_best": True},
        )
        refreshed_line = client.get(
            f"/api/v1/projects/{project_id}/quantity-takeoff-runs/{run['id']}/lines",
            headers=headers,
        ).json()[0]
        approval_response = client.post(
            f"/api/v1/projects/{project_id}/quantity-takeoff-runs/{run['id']}/apu-approvals",
            headers=headers,
            json={"line_ids": [line["id"]]},
        )
        approved_line = approval_response.json()[0]

    assert sync_response.status_code == 200
    assert sync_response.json()["created_count"] == 4
    assert sync_response.json()["source_key"] == "datacauca_public_apu"
    assert (
        sync_response.json()["license_note"]
        == "Fuente publica gratuita; validar vigencia y oficialidad antes de aprobar presupuesto."
    )

    assert catalog_response.status_code == 200
    catalog_items = catalog_response.json()
    assert catalog_items[0]["item_code"] == "1.05.0101"
    assert catalog_items[0]["item_name"] == "Muro en concreto reforzado e=0.15 m"
    assert catalog_items[0]["unit"] == "m2"
    assert catalog_items[0]["unit_rate"] == 45200
    assert catalog_items[0]["currency"] == "COP"
    assert catalog_items[0]["source_key"] == "datacauca_public_apu"
    structure = catalog_items[0]["raw_data"]["apu_structure"]
    assert [line["component_type"] for line in structure] == ["LABOR", "MATERIAL", "EQUIPMENT", "TRANSPORT"]
    assert sum(line["amount"] for line in structure) == 45200
    assert catalog_items[0]["raw_data"]["structure_status"] == "review_required"

    assert mojibake_response.status_code == 200
    mojibake_items = mojibake_response.json()
    mojibake_item = next(item for item in mojibake_items if item["item_code"] == "1.07.0301")
    assert mojibake_item["item_name"] == "Demolición con compresor de placas de piso en concreto"
    assert mojibake_item["region"] == "Subregión Centro"

    assert suggestion_response.status_code == 200
    suggestion = suggestion_response.json()[0]
    assert suggestion["line_id"] == line["id"]
    assert suggestion["cost_item_code"] == "1.05.0101"
    assert suggestion["cost_item_name"] == "Muro en concreto reforzado e=0.15 m"
    assert suggestion["budget_unit"] == "m2"
    assert suggestion["unit_rate"] == 45200
    assert suggestion["quantity"] == 12.5
    assert suggestion["budget_amount"] == 565000
    assert suggestion["match_score"] >= 70
    assert suggestion["source_key"] == "datacauca_public_apu"
    assert suggestion["review_note"].startswith("Sugerencia automatica")
    assert [line["component_type"] for line in suggestion["apu_structure"]] == [
        "LABOR",
        "MATERIAL",
        "EQUIPMENT",
        "TRANSPORT",
    ]

    applied = refreshed_line["raw_data"]["apu_suggestion"]
    assert applied["cost_item_code"] == "1.05.0101"
    assert applied["budget_amount"] == 565000
    assert applied["status"] == "suggested"
    assert applied["structure_status"] == "review_required"
    assert [line["component_type"] for line in applied["apu_structure"]] == [
        "LABOR",
        "MATERIAL",
        "EQUIPMENT",
        "TRANSPORT",
    ]
    assert approval_response.status_code == 200
    assert approved_line["raw_data"]["budget_item_assignment"]["status"] == "assigned"
    assert approved_line["raw_data"]["budget_item_assignment"]["cost_item_code"] == "1.05.0101"
    assert approved_line["raw_data"]["budget_item_assignment"]["budget_unit"] == "m2"
    assert approved_line["raw_data"]["budget_item_assignment"]["quantity"] == 12.5
    assert approved_line["raw_data"]["budget_item_assignment"]["budget_amount"] == 565000
    assert approved_line["raw_data"]["budget_item_assignment"]["source_key"] == "datacauca_public_apu"
    assert approved_line["raw_data"]["budget_item_assignment"]["match_score"] >= 70


def test_dimensional_ifc_count_requires_controlled_geometry_before_apu(monkeypatch) -> None:
    monkeypatch.setattr(
        ColombiaApuCatalogService,
        "fetch_public_rows",
        lambda self, limit=500: [
            {
                "code": "1.06.0201",
                "name": "Losa maciza en concreto reforzado",
                "unit": "m2",
                "group": "Edificaciones",
                "chapter": "Losas",
                "region": "Colombia",
                "price": 98600,
                "source_url": "https://example.test/apu",
            }
        ],
    )

    with TestClient(app) as client:
        headers = _auth_headers(client)
        suffix = uuid4().hex[:8]
        project_id = _create_project(client, headers, suffix)
        client.post(f"/api/v1/projects/{project_id}/colombia-apu-catalog/sync", headers=headers)
        upload_response = client.post(
            f"/api/v1/projects/{project_id}/quantity-takeoffs/import",
            headers=headers,
            files={
                "file": (
                    "slab-count.xlsx",
                    _quantity_xlsx(
                        [
                            [
                                "element_guid",
                                "ifc_class",
                                "category",
                                "family",
                                "type_name",
                                "quantity",
                                "unit",
                                "measurement_rule",
                            ],
                            ["GUID-SLAB-001", "IfcSlab", "Losas", "Concreto", "Losa maciza", "1", "ea", "ElementCount"],
                        ]
                    ),
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )
        run = upload_response.json()
        line = client.get(
            f"/api/v1/projects/{project_id}/quantity-takeoff-runs/{run['id']}/lines",
            headers=headers,
        ).json()[0]
        blocked_suggestion = client.post(
            f"/api/v1/projects/{project_id}/quantity-takeoff-runs/{run['id']}/apu-suggestions",
            headers=headers,
            json={"line_ids": [line["id"]], "apply_best": True},
        )
        measurement_response = client.post(
            f"/api/v1/projects/{project_id}/quantity-takeoff-runs/{run['id']}/controlled-measurements",
            headers=headers,
            json={
                "line_ids": [line["id"]],
                "measurement_rule": "GeometryMeshArea",
                "quantity": 18.5,
                "unit": "m2",
                "source": "IFC geometry inspection",
            },
        )
        suggestion_response = client.post(
            f"/api/v1/projects/{project_id}/quantity-takeoff-runs/{run['id']}/apu-suggestions",
            headers=headers,
            json={"line_ids": [line["id"]], "apply_best": True},
        )
        approval_response = client.post(
            f"/api/v1/projects/{project_id}/quantity-takeoff-runs/{run['id']}/apu-approvals",
            headers=headers,
            json={"line_ids": [line["id"]]},
        )

    assert blocked_suggestion.status_code == 400
    assert "valid IFC measurement" in blocked_suggestion.json()["detail"]
    assert measurement_response.status_code == 200
    assert measurement_response.json()[0]["raw_data"]["quantity_rule"]["preferred_unit"] == "m2"
    assert suggestion_response.status_code == 200
    assert suggestion_response.json()[0]["quantity"] == 18.5
    assert suggestion_response.json()[0]["budget_unit"] == "m2"
    assert approval_response.status_code == 200
    assert approval_response.json()[0]["raw_data"]["budget_item_assignment"]["quantity"] == 18.5


def test_colombia_apu_catalog_filters_by_public_source(monkeypatch) -> None:
    public_rows = [
        {
            "code": "200.1",
            "name": "DESMONTE Y LIMPIEZA EN BOSQUE",
            "unit": "Ha",
            "group": "INVIAS / ANTIOQUIA",
            "chapter": "Explanaciones",
            "region": "ANTIOQUIA",
            "price": 4239281.35,
            "source_key": "invias_reference_apu",
            "source_url": "https://hermes.invias.gov.co/arcgis/rest/services/SEIV_GEIV/APUs/FeatureServer/1/query",
        },
        {
            "code": "IDU-ESP-PUB-001",
            "name": "Anden en concreto",
            "unit": "m2",
            "group": "IDU / Espacio publico",
            "chapter": "Andenes",
            "region": "Bogota D.C.",
            "price": 0,
            "source_key": "idu_reference_apu",
            "source_url": "https://www.idu.gov.co/page/siipviales/economico/portafolio",
        },
    ]
    monkeypatch.setattr(ColombiaApuCatalogService, "fetch_public_rows", lambda self, limit=500: public_rows)

    with TestClient(app) as client:
        headers = _auth_headers(client)
        suffix = uuid4().hex[:8]
        project_id = _create_project(client, headers, suffix)
        sync_response = client.post(f"/api/v1/projects/{project_id}/colombia-apu-catalog/sync", headers=headers)
        invias_response = client.get(
            f"/api/v1/projects/{project_id}/colombia-apu-catalog",
            headers=headers,
            params={"source_key": "invias_reference_apu"},
        )
        idu_response = client.get(
            f"/api/v1/projects/{project_id}/colombia-apu-catalog",
            headers=headers,
            params={"source_key": "idu_reference_apu"},
        )

    assert sync_response.status_code == 200
    assert sync_response.json()["created_count"] == 2
    assert invias_response.status_code == 200
    assert idu_response.status_code == 200
    assert [item["source_key"] for item in invias_response.json()] == ["invias_reference_apu"]
    assert [item["source_key"] for item in idu_response.json()] == ["idu_reference_apu"]
    assert len(invias_response.json()[0]["raw_data"]["apu_structure"]) == 4
    assert invias_response.json()[0]["raw_data"]["apu_structure"][2]["component"] == "Equipo y herramienta"


def _auth_headers(client: TestClient) -> dict[str, str]:
    response = client.post("/api/v1/auth/login", json={"email": "ana.control@demo.local", "password": "1234"})
    assert response.status_code == 200
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _create_project(client: TestClient, headers: dict[str, str], suffix: str) -> int:
    response = client.post(
        "/api/v1/projects",
        headers=headers,
        json={
            "code": f"APU-{suffix}",
            "name": f"Proyecto APU {suffix}",
            "phase": "Planning",
            "currency": "COP",
            "calendar_base": "5x8 Colombia",
            "owner": "Owner",
            "status": "authorized",
            "authorization_date": "2026-06-01",
            "authorization_ref": f"AFE-APU-{suffix}",
            "configuration": {"funding_required": True},
            "start_date": "2026-06-01",
            "finish_date": "2026-12-31",
        },
    )
    assert response.status_code == 200
    return response.json()["id"]


def _quantity_xlsx(rows: list[list[str]]) -> bytes:
    from io import BytesIO
    from zipfile import ZIP_DEFLATED, ZipFile

    shared_strings: list[str] = []
    string_index: dict[str, int] = {}

    def shared(value: str) -> int:
        if value not in string_index:
            string_index[value] = len(shared_strings)
            shared_strings.append(value)
        return string_index[value]

    def column_name(index: int) -> str:
        name = ""
        index += 1
        while index:
            index, remainder = divmod(index - 1, 26)
            name = chr(65 + remainder) + name
        return name

    sheet_rows = []
    for row_idx, row in enumerate(rows, start=1):
        cells = []
        for col_idx, value in enumerate(row):
            ref = f"{column_name(col_idx)}{row_idx}"
            try:
                numeric = float(value)
            except ValueError:
                cells.append(f'<c r="{ref}" t="s"><v>{shared(value)}</v></c>')
            else:
                cells.append(f'<c r="{ref}"><v>{numeric}</v></c>')
        sheet_rows.append(f'<row r="{row_idx}">{"".join(cells)}</row>')
    shared_xml = "".join(f"<si><t>{value}</t></si>" for value in shared_strings)
    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as zf:
        zf.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            '<Override PartName="/xl/sharedStrings.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/>'
            "</Types>",
        )
        zf.writestr(
            "_rels/.rels",
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>',
        )
        zf.writestr(
            "xl/workbook.xml",
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheets><sheet name="QTO" sheetId="1" r:id="rId1" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"/></sheets></workbook>',
        )
        zf.writestr(
            "xl/_rels/workbook.xml.rels",
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/sharedStrings" Target="sharedStrings.xml"/></Relationships>',
        )
        zf.writestr(
            "xl/sharedStrings.xml",
            f'<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" count="{len(shared_strings)}" uniqueCount="{len(shared_strings)}">{shared_xml}</sst>',
        )
        zf.writestr(
            "xl/worksheets/sheet1.xml",
            f'<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>{"".join(sheet_rows)}</sheetData></worksheet>',
        )
    return buffer.getvalue()
