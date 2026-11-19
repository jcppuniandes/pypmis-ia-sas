"""Build the O2B report using the retained, verified O2A Word layout."""

import hashlib
import importlib.util
import io
import json
from copy import deepcopy
from datetime import UTC, datetime
from zipfile import ZipFile

from docx import Document
from evidence import OUT, QA, ROOT, observations
from report_content import chapters

REFERENCE = (
    ROOT
    / "outputs/wave-o2a-20261109/P&Pmis_Wave_O2A_Engineering_Foundation_Technical_Report.docx"
)
REFERENCE_SHA = "75884bf11112dfefd8bf692471d7d7e21666dd1f2beb2de26329e23a81308319"
REPORT = OUT / "P&Pmis_Wave_O2B_Procurement_Materials_Logistics_Technical_Report.docx"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    assert digest(REFERENCE) == REFERENCE_SHA
    render = ROOT / "outputs/.qa/wave-o2a-20261109/word-final-1/pages"
    proof = json.loads((render / "render-provenance.json").read_text("utf-8"))
    assert proof["input_docx_sha256"] == REFERENCE_SHA and len(proof["pages"]) == 7
    assert all(digest(render / name) == sha for name, sha in proof["pages"].items())
    contract = (
        (ROOT / "scripts/wave-o2/TEMPLATE_CONTRACT.md")
        .read_text("utf-8")
        .split("Slots:")[0]
    )
    (QA / "artifact.md").write_text(
        f"Retained reference: {REFERENCE}\nSHA-256: {REFERENCE_SHA}\n"
        f"7 prior rendered pages: {render}\n\n"
        + contract
        + "\nSlots: keep first logo drawing, page geometry and section. Replace the title, subtitle, 39 content "
        "sections and their native evidence tables. Replace core metadata and footer date. "
        "Preserve all other OOXML package parts byte-for-byte.\n",
        encoding="utf-8",
    )
    spec = importlib.util.spec_from_file_location(
        "o2b_components", ROOT / "scripts/wave-o1bb1/generate_report.py"
    )
    assert spec and spec.loader
    components = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(components)
    p, h, table = components.p, components.h, components.table
    e = observations()
    doc = Document(REFERENCE)
    doc.core_properties.title = "Wave O2B Compras materiales y logística"
    doc.core_properties.subject = "Informe técnico de P&Pmis Construction AI"
    doc.core_properties.keywords = "Procurement, Materials, Logistics, AWP, Engineering"
    doc.core_properties.comments = "Implementación y validación técnica de Wave O2B"
    doc.core_properties.created = doc.core_properties.modified = datetime.now(UTC)
    logo = deepcopy(doc.paragraphs[0]._p)
    section = deepcopy(doc._element.body.sectPr)
    for node in list(doc._element.body):
        doc._element.body.remove(node)
    doc._element.body.append(logo)
    doc._element.body.append(section)
    p(doc, "Wave O2B\nCompras materiales y logística", "Title")
    p(
        doc,
        "P&Pmis Construction AI\nInforme técnico de implementación\n11 noviembre 2026",
        "Subtitle",
    )
    sections = chapters(e)
    assert len(sections) == 39
    for index, (title, body) in enumerate(sections, 1):
        h(doc, f"{index} {title}")
        if index == 36 and e["operations"]:
            doc.paragraphs[-1].paragraph_format.page_break_before = True
        p(doc, body)
        if index == 4:
            table(
                doc,
                ["Autoridad", "Qué conserva", "Qué consume Procurement"],
                [
                    ["AWP", "Paquetes y liberación", "Identidad de PWP, CWP o IWP"],
                    [
                        "Engineering y CDE",
                        "IFC y archivos controlados",
                        "ID, revisión y huella de la fuente",
                    ],
                    [
                        "Scope y P6",
                        "Alcance y cronograma aceptado",
                        "Vínculos canónicos y versión P6",
                    ],
                    [
                        "Cost",
                        "Compromisos y costos reales",
                        "Clasificación por CBS y cuenta",
                    ],
                ],
                [1.4, 2.33, 2.37],
            )
        if index == 18:
            table(
                doc,
                ["Hecho", "Qué acredita", "Qué no cambia"],
                [
                    ["Llegada", "El embarque llegó", "Cantidad recibida"],
                    ["Recepción", "Cantidad física ingresada", "Cantidad aceptada"],
                    ["Aceptación", "Disposición de calidad", "Asignación vigente"],
                    [
                        "Disponibilidad",
                        "Cobertura aceptada y reservada",
                        "Liberación AWP",
                    ],
                ],
                [1.35, 2.35, 2.40],
            )
        if index == 36 and e["operations"]:
            table(
                doc,
                ["Operación", "Muestras ms", "Mediana ms", "Filas y bytes JSON"],
                [
                    [
                        row["operation"],
                        " / ".join(str(round(x, 1)) for x in row["samples_ms"]),
                        str(round(row["median_ms"], 1)),
                        f"{row.get('record_count', 'n/d')} / {row.get('response_json_bytes', 'n/d')}",
                    ]
                    for row in e["operations"]
                ],
                [2.4, 1.5, 1.0, 1.2],
            )
    for paragraph in doc.paragraphs:
        paragraph.paragraph_format.widow_control = True
        if paragraph.style.name == "Normal":
            paragraph.paragraph_format.keep_together = True
    OUT.mkdir(parents=True, exist_ok=True)
    buffer = io.BytesIO()
    doc.save(buffer)
    edited = {"word/document.xml", "docProps/core.xml", "word/footer1.xml"}
    with (
        ZipFile(REFERENCE) as reference,
        ZipFile(buffer) as generated,
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
                value = value.replace(b"10 noviembre 2026", b"11 noviembre 2026")
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
