"""Author the 36 O2A sections in the retained P&Pmis Word layout."""

import hashlib
import importlib.util
import io
import json
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from zipfile import ZipFile

from docx import Document
from report_content import chapters

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "outputs/wave-o2a-20261109"
QA = ROOT / "outputs/.qa/wave-o2a-20261109"
REPORT = OUT / "P&Pmis_Wave_O2A_Engineering_Foundation_Technical_Report.docx"
REFERENCE = (
    ROOT
    / "outputs/wave-o1c-20261106/P&Pmis_Wave_O1C_Forecast_Performance_Reporting_Technical_Report.docx"
)
REFERENCE_SHA = "e2a6b9811af92ac064235e7aef29d7c8df69c23723c0548d1551d4c48d183cd6"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    assert digest(REFERENCE) == REFERENCE_SHA
    render = ROOT / "outputs/.qa/wave-o1c-20261106/word-pages-v2"
    proof = json.loads((render / "render-provenance.json").read_text("utf-8"))
    assert proof["input_docx_sha256"] == REFERENCE_SHA and len(proof["pages"]) == 7
    assert all(digest(render / name) == sha for name, sha in proof["pages"].items())
    contract = (
        (ROOT / "scripts/wave-o2/TEMPLATE_CONTRACT.md")
        .read_text("utf-8")
        .split("Slots:")[0]
    )
    (QA / "artifact.md").write_text(
        contract.replace("for O2", "for O2A")
        + "Slots: retain first drawing and section; replace body with 36 O2A headings, narrative and two native evidence tables. "
        "Replace core metadata and the footer date literal. Preserve all other OOXML package parts byte-for-byte.\n",
        encoding="utf-8",
    )
    evidence = json.loads((QA / "release-evidence.json").read_text("utf-8-sig"))
    spec = importlib.util.spec_from_file_location(
        "components", ROOT / "scripts/wave-o1bb1/generate_report.py"
    )
    assert spec and spec.loader
    components = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(components)
    p, h, table = components.p, components.h, components.table
    doc = Document(REFERENCE)
    doc.core_properties.title = "Fundamentos de Ingeniería Wave O2A"
    doc.core_properties.subject = "Informe técnico de P&Pmis Construction AI"
    doc.core_properties.keywords = (
        "Engineering, deliverables, review, IFC release, AWP, readiness"
    )
    doc.core_properties.comments = "Implementación y evidencia técnica de Wave O2A"
    doc.core_properties.created = doc.core_properties.modified = datetime.now(UTC)
    logo = deepcopy(doc.paragraphs[0]._p)
    section = deepcopy(doc._element.body.sectPr)
    for node in list(doc._element.body):
        doc._element.body.remove(node)
    doc._element.body.append(logo)
    doc._element.body.append(section)
    p(doc, "Wave O2A\nFundamentos de Ingeniería", "Title")
    p(
        doc,
        "P&Pmis Construction AI\nInforme técnico de implementación\n10 noviembre 2026",
        "Subtitle",
    )
    sections = chapters(evidence)
    assert len(sections) == 36
    for index, (title, body) in enumerate(sections, 1):
        h(doc, f"{index} {title}")
        p(doc, body)
        if index == 4:
            table(
                doc,
                ["Autoridad", "Qué gobierna", "Qué conserva el enlace"],
                [
                    [
                        "Ingeniería",
                        "Entregable, revisión y liberación IFC",
                        "Evidencia y fecha efectiva",
                    ],
                    [
                        "AWP",
                        "EWP, restricciones y release del paquete",
                        "Referencia a evidencia técnica",
                    ],
                    [
                        "CDE",
                        "Documento, adjunto y permisos",
                        "Identidad y huella del adjunto",
                    ],
                    [
                        "Scope y P6",
                        "Plan, WBS y actividad aceptada",
                        "ID canónico y versión P6",
                    ],
                ],
                [1.12, 2.72, 2.26],
            )
        if index == 27:
            p(
                doc,
                "Los comandos usan If-Match e Idempotency-Key. Un ETag vencido devuelve 412; un estado incompatible o una llave reutilizada con otro contenido devuelve 409. El servicio aplica 403 o 404 según la autorización y el ocultamiento del objeto.",
            )
            p(
                doc,
                "Las rutas se agrupan bajo /api/v1/engineering. El prefijo de proyecto es /projects/{workspace_id}; por ejemplo, POST /revisions/{identity}/review-action registra la decisión y POST /revisions/{identity}/ifc-release emite el hecho separado. El inventario completo se entrega en la hoja 13_API.",
            )
        if index == 29:
            table(
                doc,
                ["Tabla nueva", "Responsabilidad"],
                [
                    [
                        "engineering_design_packages",
                        "Agrupación de entregables técnicos",
                    ],
                    ["engineering_deliverables", "Identidad y revisión más reciente"],
                    ["engineering_revisions", "Contenido versionado y referencia CDE"],
                    ["engineering_reviews", "Rondas y decisiones técnicas"],
                    ["engineering_review_comments", "Comentarios, respuestas y cierre"],
                    ["engineering_releases", "Hechos IFC y snapshots inmutables"],
                    ["engineering_interfaces", "Interfaces y referencias externas"],
                    ["engineering_history", "Eventos de auditoría"],
                    [
                        "engineering_mappings",
                        "Enlaces tipados con historial append-only",
                    ],
                ],
                [3.0, 3.1],
            )
        if index == 30:
            suites = evidence.get("postgresql", {}).get("suites", {})
            if suites:
                p(
                    doc,
                    "La suite combina pruebas HTTP y SQL persistidas con reglas deterministas y regresiones de O1. No se cuentan las pruebas de política como si cada una fuese un ciclo transaccional completo. Los casos de vencimiento y sucesión adelantan solo el reloj de observación después de persistir los hechos; no desactivan los triggers.",
                )
                table(
                    doc,
                    ["Suite", "Aprobadas"],
                    [
                        [name.removeprefix("tests.test_"), str(states.get("PASS", 0))]
                        for name, states in suites.items()
                    ],
                    [5.1, 1.0],
                )
                p(
                    doc,
                    "El JUnit final, la salida del proceso y la prueba de frescura de fuentes se conservaron bajo outputs/.qa/wave-o2a-20261109. Las corridas de diagnóstico fallidas siguen separadas y no cuentan como evidencia de liberación.",
                )
        if index == 31:
            uat = evidence.get("browser", {}).get("uat", {})
            observation = uat.get("observations", {})
            if observation:
                p(
                    doc,
                    f"La ejecución registra la fecha UTC {uat.get('as_of_utc')}, el perfil {observation.get('profile_id')}, el entregable {observation.get('deliverable_id')} y la revisión {observation.get('revision_id')}. La evaluación AWP {observation.get('awp_assessment_id')} quedó {observation.get('awp_readiness_state')}; el paquete permaneció {observation.get('awp_release_state')}. Son identidades del escenario sintético, no del Proyecto 14.",
                )
                p(
                    doc,
                    "El recorrido conserva capturas de ADMIN, fuente CDE, correcciones, aprobación independiente, IFC, proveedor de Readiness, consumo AWP e historial. La prueba verifica huellas de las fuentes antes y después para distinguir el ensayo preliminar de la ejecución final congelada.",
                )
        if index == 33:
            operations = (
                evidence.get("browser", {}).get("performance", {}).get("operations", [])
            )
            if operations:
                table(
                    doc,
                    ["Operación", "Muestras en ms", "Mediana en ms"],
                    [
                        [
                            row["operation"],
                            " / ".join(str(round(x, 1)) for x in row["samples_ms"]),
                            str(round(row["median_ms"], 1)),
                        ]
                        for row in operations
                    ],
                    [2.7, 2.12, 1.28],
                )
        if index == 35:
            table(
                doc,
                ["Comprobación de cierre", "Resultado"],
                [
                    [label, evidence.get("gate_status", {}).get(key, "PENDING")]
                    for key, label in (
                        ("postgresql", "PostgreSQL y migración"),
                        ("chromium_uat", "Chromium UAT"),
                        ("performance", "Rendimiento local"),
                        ("preservation", "Proyecto 14"),
                        ("protected_diff", "Perímetro protegido"),
                        ("frontend", "Verificación frontend"),
                        ("open_defects", "Defectos abiertos S1 y S2"),
                    )
                ],
                [4.6, 1.5],
            )
    for paragraph in doc.paragraphs:
        paragraph.paragraph_format.widow_control = True
        if paragraph.style.name == "Normal":
            paragraph.paragraph_format.keep_together = True
    OUT.mkdir(parents=True, exist_ok=True)
    memory = io.BytesIO()
    doc.save(memory)
    edited = {"word/document.xml", "docProps/core.xml", "word/footer1.xml"}
    with (
        ZipFile(REFERENCE) as reference,
        ZipFile(memory) as generated,
        ZipFile(REPORT, "w") as output,
    ):
        for part in reference.infolist():
            value = (
                generated
                if part.filename in edited - {"word/footer1.xml"}
                else reference
            ).read(part.filename)
            if part.filename == "word/footer1.xml":
                assert b"PAGE" in value
                for old in (b"9 noviembre 2026", b"6 noviembre 2026"):
                    value = value.replace(old, b"10 noviembre 2026")
            output.writestr(part, value)
    with ZipFile(REFERENCE) as reference, ZipFile(REPORT) as output:
        assert reference.namelist() == output.namelist()
        changed = {
            part
            for part in reference.namelist()
            if reference.read(part) != output.read(part)
        }
        assert {"word/document.xml", "docProps/core.xml"} <= changed <= edited
    assert digest(REFERENCE) == REFERENCE_SHA
    print(
        json.dumps(
            {
                "sections": len(sections),
                "sha256": digest(REPORT),
                "changed_parts": sorted(changed),
            }
        )
    )


if __name__ == "__main__":
    main()
