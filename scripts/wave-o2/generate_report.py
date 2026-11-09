"""Build the technical report with the retained native Word components."""

import hashlib
import importlib.util
import io
import json
from copy import deepcopy
from datetime import UTC, datetime
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from collect_evidence import QA, ROOT, digest, read
from docx import Document
from report_content import chapters

OUT = ROOT / "outputs/wave-o2-20261109"
REPORT = OUT / "P&Pmis_Wave_O2_Master_Architecture_Technical_Report.docx"
REFERENCE = (
    ROOT
    / "outputs/wave-o1c-20261106/P&Pmis_Wave_O1C_Forecast_Performance_Reporting_Technical_Report.docx"
)
REFERENCE_SHA = "e2a6b9811af92ac064235e7aef29d7c8df69c23723c0548d1551d4c48d183cd6"
NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}


def distill():
    assert digest(REFERENCE) == REFERENCE_SHA
    render = ROOT / "outputs/.qa/wave-o1c-20261106/word-pages-v2"
    proof = read(render / "render-provenance.json")
    assert proof["input_docx_sha256"] == REFERENCE_SHA and len(proof["pages"]) == 7
    assert all(digest(render / file) == sha for file, sha in proof["pages"].items())
    with ZipFile(REFERENCE) as archive:
        xml = ET.fromstring(archive.read("word/document.xml"))
        sections = [
            ET.tostring(x, encoding="unicode") for x in xml.findall(".//w:sectPr", NS)
        ]
        assert len(sections) == 1
        assert b"PAGE" in archive.read("word/footer1.xml")
        inventory = [
            {
                "part": name,
                "bytes": len(archive.read(name)),
                "sha256": hashlib.sha256(archive.read(name)).hexdigest(),
            }
            for name in archive.namelist()
        ]
        styles = ET.fromstring(archive.read("word/styles.xml"))
        roles = {
            name: ET.tostring(
                styles.find(f"w:style[@w:styleId='{name}']", NS), encoding="unicode"
            )
            for name in ("Title", "Subtitle", "Normal", "Heading1")
        }
    QA.mkdir(parents=True, exist_ok=True)
    (QA / "artifact.md").write_text(
        (ROOT / "scripts/wave-o2/TEMPLATE_CONTRACT.md").read_text("utf-8"),
        encoding="utf-8",
    )
    (QA / "template-evidence.json").write_text(
        json.dumps(
            {
                "reference": str(REFERENCE),
                "sha256": REFERENCE_SHA,
                "source_pages": 7,
                "sections": sections,
                "roles": roles,
                "parts": inventory,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(json.dumps({"source_pages": 7, "template_parts": len(inventory)}))


def main():
    assert (
        read(QA / "template-evidence.json")["sha256"]
        == digest(REFERENCE)
        == REFERENCE_SHA
    )
    assert (QA / "artifact.md").is_file()
    data = read(QA / "package-data.json")
    headings = chapters(data)
    assert len(headings) == 39
    spec = importlib.util.spec_from_file_location(
        "retained_components", ROOT / "scripts/wave-o1bb1/generate_report.py"
    )
    assert spec and spec.loader
    components = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(components)
    p, h, table = components.p, components.h, components.table
    doc = Document(REFERENCE)
    doc.core_properties.title = "Arquitectura maestra de Ingeniería Compras y Contratos"
    doc.core_properties.subject = "Informe técnico Wave O2"
    doc.core_properties.keywords = (
        "O2, Engineering, Procurement, Contracts, SOV, Project Cost Sheet, AWP"
    )
    doc.core_properties.comments = (
        "Decisiones de arquitectura y trazabilidad de Wave O2"
    )
    doc.core_properties.created = doc.core_properties.modified = datetime.now(UTC)
    logo = deepcopy(doc.paragraphs[0]._p)
    section = deepcopy(doc._element.body.sectPr)
    for node in list(doc._element.body):
        doc._element.body.remove(node)
    doc._element.body.append(logo)
    doc._element.body.append(section)
    p(doc, "Wave O2\nArquitectura maestra de Ingeniería Compras y Contratos", "Title")
    p(
        doc,
        "P&Pmis Construction AI\nInforme técnico de arquitectura\n9 noviembre 2026",
        "Subtitle",
    )
    p(
        doc,
        "Este informe fija los límites que deberán respetar las próximas olas. La decisión de arquitectura mantiene las autoridades de O1 y define cómo rastrear una obligación desde el instrumento contractual hasta su distribución por costo.",
    )
    for index, (title, body) in enumerate(headings, 1):
        h(doc, f"{index} {title}")
        p(doc, body)
        if index == 4:
            table(
                doc,
                ["Dominio", "Hecho que gobierna", "Límite"],
                [
                    ["Engineering", "Entrega y liberación técnica", "AWP conserva EWP"],
                    ["Procurement", "Adquisición y adjudicación", "No crea PO"],
                    ["Materials", "Disponibilidad e inspección", "No reconoce Actual"],
                    ["Logistics", "Movimiento y entrega", "No escribe P6"],
                    [
                        "Contracts",
                        "Instrumento, SOV y obligación",
                        "Cost solo consolida",
                    ],
                ],
                [1.25, 2.7, 2.15],
            )
        if index == 17:
            p(
                doc,
                "En el caso de diseño, 100 USD de contrato más 10 USD de subcontrato aditivo dan 110 USD. El SOV de 100 USD, la PO incluida y el call-off cubierto aportan cero adicional. El detalle conserva la referencia al importe original.",
            )
        if index == 36:
            table(
                doc,
                ["Ola", "Prueba de salida prevista"],
                [
                    ["O2A", "Revisión técnica aprobada, IFC explícito y enlace EWP"],
                    ["O2B", "Sourcing sin PO y disponibilidad tras inspección"],
                    [
                        "O2C",
                        "SOV sucesor, compromiso sin duplicar y detalle en ambos sentidos",
                    ],
                    [
                        "O2D",
                        "Evidencia vigente, evaluación y release AWP independiente",
                    ],
                ],
                [0.9, 5.2],
            )
    for paragraph in doc.paragraphs:
        paragraph.paragraph_format.widow_control = True
        if paragraph.style.name == "Normal":
            paragraph.paragraph_format.keep_together = True
    OUT.mkdir(parents=True, exist_ok=True)
    working = io.BytesIO()
    doc.save(working)
    edited = {"word/document.xml", "docProps/core.xml"}
    with (
        ZipFile(REFERENCE) as original,
        ZipFile(working) as generated,
        ZipFile(REPORT, "w") as target,
    ):
        for part in original.infolist():
            target.writestr(
                part,
                (generated if part.filename in edited else original).read(
                    part.filename
                ),
            )
    with ZipFile(REFERENCE) as original, ZipFile(REPORT) as final:
        assert final.namelist() == original.namelist()
        assert {
            n for n in final.namelist() if final.read(n) != original.read(n)
        } == edited
    print(
        json.dumps(
            {
                "chapters": len(headings),
                "docx_sha256": digest(REPORT),
                "reference_preserved": True,
            }
        )
    )


if __name__ == "__main__":
    import sys

    if sys.argv[1:] == ["--distill"]:
        distill()
    else:
        assert not sys.argv[1:]
        main()
