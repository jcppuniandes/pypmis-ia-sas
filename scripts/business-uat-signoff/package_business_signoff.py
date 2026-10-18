"""Package controlled review documents; never records business acceptance."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "docs/validation/business-uat-signoff-20261018"
OUT = ROOT / "outputs/business-uat-signoff-20261018"
QA = ROOT / "outputs/.qa/business-uat-signoff-20261018"
SIGNOFF = "P&Pmis_Strategic_Macroprocess_Business_UAT_Signoff.docx"
REPORT = "P&Pmis_Informe_Tecnico_Business_UAT_Signoff_20261018.docx"
TRACKER = "P&Pmis_Strategic_Macroprocess_Business_UAT_Signoff_Tracker.xlsx"
TRACE = "P&Pmis_Strategic_Macroprocess_UAT_Traceability.xlsx"
ARCHIVE = "P&Pmis_Strategic_Macroprocess_Business_UAT_Release_Package.zip"


def digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def encoded(value) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def main():
    data = read_json(DATA / "review-pack-data.json")
    native = read_json(QA / "workbooks/workbook-verification.json")
    visual = read_json(DATA / "final-artifact-qa.json")
    scope = read_json(DATA / "final-scope-audit.json")
    assert native["result"] == "PASS", "Workbook native/visual review incomplete"
    assert visual["result"] == "PASS", "Final Word visual review incomplete"
    assert scope["result"] == "PASS_FINAL_SCOPE_AND_PRESERVATION_READ_ONLY", "Final source/runtime audit incomplete"
    assert data["counts"]["completed"] == 0 and data["counts"]["pending"] == 15
    assert not data["business_release_authorized"]
    assert data["release_state"] == "STRATEGIC_MACROPROCESS_TECHNICALLY_READY_UAT_SIGNOFF_PENDING"
    assert data["business_decision"] == "UAT_SIGNOFF_PENDING"
    assert data["next_recommendation"] == "COMPLETE AUTHORIZED BUSINESS UAT SIGN-OFF"
    assert all(data["counts"][key] == 0 for key in ["completed", "completion_percent", "accept", "accept_with_conditions", "reject", "accepted_conditions", "business_rejections"])
    for manifest in [read_json(QA / "documents-build-manifest.json"), read_json(QA / "workbooks/build-manifest.json"), visual]:
        assert manifest["data_sha256"] == digest((DATA / "review-pack-data.json").read_bytes())
        assert manifest["baseline_sha256"] == digest((DATA / "baseline.json").read_bytes())
    assert visual["workbook_native_and_visual_checks"]["sha256"] == digest((QA / "workbooks/workbook-verification.json").read_bytes())
    for prior in scope["preserved_prior_observations"]:
        assert digest((ROOT / prior["file"]).read_bytes()) == prior["sha256"]
    for source in scope["fourteen_source_hashes"]:
        assert digest((ROOT / source["file"]).read_bytes()) == source["expected_sha256"]
    members: dict[str, bytes] = {}
    files = []

    def add(path: Path, arcname: str, role: str):
        content = path.read_bytes()
        assert arcname not in members
        members[arcname] = content
        files.append({"archive_path": arcname, "source_path": path.relative_to(ROOT).as_posix(), "sha256": digest(content), "bytes": len(content), "role": role})

    evidence_by_id = {item["id"]: item for item in data["evidence_register"]}
    baseline_paths = {}
    for item in data["required_documents"]:
        path = ROOT / evidence_by_id[item["evidence_id"]]["path"]
        assert digest(path.read_bytes()) == item["sha256"], item["id"]
        arcname = "01_Fuentes_Baseline16/" + path.name
        add(path, arcname, "IMMUTABLE_TECHNICAL_SOURCE_NOT_BUSINESS_APPROVAL")
        baseline_paths[item["id"]] = arcname
    review_paths = {}
    for filename in [SIGNOFF, REPORT, TRACKER, TRACE]:
        path = OUT / filename
        expected = native["outputs"].get(filename) or visual["outputs"][filename]["sha256"]
        assert digest(path.read_bytes()) == expected, filename
        arcname = "02_Paquete_Revision/" + filename
        add(path, arcname, "PREPARED_REVIEW_WITHOUT_SIGNATURES")
        review_paths[filename] = arcname

    for eid in ["E17", "E20"]:
        item = evidence_by_id[eid]
        path = ROOT / item["path"]
        add(path, "03_Evidencia_Visual_UAT_16Oct/" + path.name, "HISTORICAL_APPLICATION_SCREENSHOT_NOT_NEW_BROWSER_TEST")
    for name in ["baseline.json", "runtime-readonly-20261018.json", "final-scope-audit.json", "final-artifact-qa.json"]:
        add(DATA / name, "04_Control_Del_Paquete/" + name, "READ_ONLY_AUDIT_OR_DOCUMENT_QA_NOT_BUSINESS_DECISION")

    signoff = review_paths[SIGNOFF]
    tracker = review_paths[TRACKER]
    logical = [
        {"id": 1, "name": "Executive Summary", "file": signoff, "locator": "A Resumen ejecutivo"},
        {"id": 2, "name": "Business Process", "file": baseline_paths["DOC01"], "locator": "Documento completo; complemento mapa R01-R35 en C del paquete"},
        {"id": 3, "name": "User Guide", "file": baseline_paths["DOC02"], "locator": "Leer junto con addendum J del paquete de revisión"},
        {"id": 4, "name": "Administration Guide", "file": baseline_paths["DOC03"], "locator": "Leer junto con addendum J; NO GO histórico pertenece al corte 15Oct"},
        {"id": 5, "name": "UAT Plan and Results", "file": baseline_paths["DOC04"], "locator": "Historia técnica 16Oct sin nueva aceptación"},
        {"id": 6, "name": "UAT Traceability", "file": review_paths[TRACE], "locator": "02_UAT_Cases AA:AE: referencias propuestas; A:Z y siete hojas restantes intactas"},
        {"id": 7, "name": "Final Release Closeout", "file": baseline_paths["DOC06"], "locator": "Cierre técnico 16Oct intacto; no agregar sign-off hasta decisiones reales"},
        {"id": 8, "name": "Business Signoff Matrix", "file": tracker, "locator": "01_Signoff_Matrix; formularios BA01-BA15 en K del Word"},
        {"id": 9, "name": "Acceptance Conditions Register", "file": tracker, "locator": "02_Acceptance_Conditions; ocho propuestas no aceptadas"},
        {"id": 10, "name": "Known Findings Register", "file": tracker, "locator": "03_Known_Findings; seis hallazgos abiertos y dos observaciones visuales"},
        {"id": 11, "name": "Final Business Release Decision", "file": tracker, "locator": "06_Final_Release_Decision; decisión humana vacía y cálculo UAT_SIGNOFF_PENDING"},
    ]
    index = []
    source_to_arc = {item["source_path"]: item["archive_path"] for item in files}
    for item in data["evidence_register"]:
        path = ROOT / item["path"]
        index.append({**item, "sha256": digest(path.read_bytes()), "bytes": path.stat().st_size, "archive_path": source_to_arc.get(item["path"]), "included_in_archive": item["path"] in source_to_arc, "review_claim": "PROPOSED_EVIDENCE_NOT_ATTESTED_REVIEWED"})
    manifest = {
        "schema_version": 1,
        "date": data["date"],
        "scope": data["scope"],
        "baseline_commit": "6672fd5da1f486e6bd571a74bb6d1e8b3337a405",
        "release_state": data["release_state"],
        "business_decision": data["business_decision"],
        "counts": data["counts"],
        "business_release_authorized": False,
        "next_recommendation": data["next_recommendation"],
        "logical_component_count": len(logical),
        "logical_components": logical,
        "traceability_lineage": {"immutable_technical_16Oct": baseline_paths["DOC05"], "prepared_review_18Oct": review_paths[TRACE], "relationship": "Controlled successor adds only proposed AA:AE business references. Neither workbook has business acceptance."},
        "files": files,
        "evidence_register": index,
        "not_included": "Other raw technical evidence remains at each repository path with SHA256. Internal document renders, QA PDFs, simulated signatures and credentials are not bundled.",
    }
    members["00_Manifiesto_Controlado.json"] = encoded(manifest)
    lines = [
        "# P&Pmis Construction AI — Paquete de revisión empresarial UAT",
        "",
        "Preparado el 18 de octubre de 2026. SIN FIRMAS. NO AUTORIZA LIBERACIÓN.",
        "",
        "Estado: " + data["release_state"],
        "Decisión empresarial: UAT_SIGNOFF_PENDING. Avance: 0/15 áreas (0%).",
        "ACCEPT: 0; ACCEPT_WITH_CONDITIONS: 0; REJECT: 0; pendientes: 15.",
        "Condiciones aceptadas: 0. Rechazos empresariales registrados: 0.",
        "",
        "## Cómo revisar",
        "",
        "1. Leer el Word Business UAT Signoff, secciones A-L y el addendum J.",
        "2. Revisar cada área BA01-BA15 con su representante realmente autorizado.",
        "3. Capturar identidad, autoridad, fecha, decisión, evidencia realmente revisada y aprobación en los formularios y tracker. Ninguno viene preaprobado.",
        "4. Reconocer expresamente S3-006, los cuatro MISSING no bloqueantes y las reglas de seguridad/SoD; no confundir referencias propuestas con revisión real.",
        "5. Registrar condiciones y rechazos materiales con responsable, plazo y referencia de autoridad. Las ocho condiciones iniciales son propuestas, no acuerdos.",
        "6. Revisar los seis documentos en 05_Document_Acceptance. Solo después de decisiones reales podrá actualizarse Final Release Closeout sin borrar su historia técnica.",
        "",
        "## Fuentes y vigencia",
        "",
        "01_Fuentes_Baseline16 conserva seis documentos byte-idénticos de 14/15/16Oct. El NO GO del Admin Guide es histórico del15; no sustituye el cierre técnico del16. El addendum J explica los límites y cambios posteriores.",
        "02_Paquete_Revision contiene los cuatro documentos preparados el18. Su trazabilidad es la vista vigente para revisar: mantiene toda la historia técnica y agrega solo AA:AE propuestas, sin decisiones humanas. La copia16 en baseline es evidencia inmutable, no otra versión de negocio activa.",
        "03_Evidencia_Visual_UAT_16Oct incluye dos capturas reales históricas de aplicación, no renders internos ni una prueba navegador nueva.",
        "04_Control_Del_Paquete contiene observaciones de solo lectura y QA de documentos. La continuidad SQL del18 NO es una nueva E2E ni un nuevo FID.",
        "El manifiesto contiene SHA256 y rutas de las23 evidencias. Solo documentos, dos capturas y controles de continuidad se incluyen; las demás pruebas técnicas se consultan en sus rutas del repositorio. No se empaquetan cadenas técnicas completas que podrían contener credenciales.",
        "",
        "## Once componentes lógicos sin duplicar registros",
        "",
    ]
    for item in logical:
        lines.append(f"{item['id']}. {item['name']}: `{item['file']}` — {item['locator']}.")
    lines.extend(["", "## Límites actuales", "", "Gate: 19 requisitos obligatorios, 15 VALID y 4 MISSING no bloqueantes; una fila opcional Class C NOT_REQUIRED. Los cuatro MISSING no se consideran satisfechos.", "Persisten S3-006, S4-001 a S4-005 y dos observaciones de consistencia UI. No hay aceptaciones tácitas ni correcciones de producto en este incremento.", "No se autoriza producción, Project Delivery, permisos/contratos reales ni activación por una firma simulada. No hubo commit ni push.", "", "Siguiente recomendación única: COMPLETE AUTHORIZED BUSINESS UAT SIGN-OFF.", ""])
    members["00_LEER_PRIMERO.md"] = "\n".join(lines).encode("utf-8")
    archive = OUT / ARCHIVE
    with ZipFile(archive, "w", ZIP_DEFLATED, compresslevel=9) as zipped:
        for name, content in members.items():
            zipped.writestr(name, content)
    with ZipFile(archive) as zipped:
        assert zipped.testzip() is None
        assert set(zipped.namelist()) == set(members)
        for name, content in members.items():
            assert zipped.read(name) == content
    result = {"result": "PASS", "archive": archive.relative_to(ROOT).as_posix(), "sha256": digest(archive.read_bytes()), "bytes": archive.stat().st_size, "member_count": len(members), "logical_components": 11, "counts": data["counts"], "source_documents_changed": 0, "business_release_authorized": False}
    (DATA / "package-verification.json").write_bytes(encoded(result))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
