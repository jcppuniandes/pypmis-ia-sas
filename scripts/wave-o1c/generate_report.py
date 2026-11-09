"""O1C report from retained native Word components and executed evidence."""

import hashlib
import importlib.util
import io
import json
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from zipfile import ZipFile

from docx import Document

ROOT = Path(__file__).resolve().parents[2]
REFERENCE = (
    ROOT
    / "outputs/wave-o1bd-20261104/P&Pmis_Wave_O1B_D_Progress_and_Baseline_Integration_Technical_Report.docx"
)
REFERENCE_SHA = "ea1934490194120ed7d6ae6045145e12b4e219dfb5d41816cf6b4e33f670e0a0"
OUT = ROOT / "outputs/wave-o1c-20261106"
QA = ROOT / "outputs/.qa/wave-o1c-20261106"
DATA = ROOT / "docs/validation/wave-o1c-20261106/package-data.json"
spec = importlib.util.spec_from_file_location(
    "retained_components", ROOT / "scripts/wave-o1bb1/generate_report.py"
)
components = importlib.util.module_from_spec(spec)
spec.loader.exec_module(components)
p, h, table = components.p, components.h, components.table


def main():
    assert hashlib.sha256(REFERENCE.read_bytes()).hexdigest() == REFERENCE_SHA
    data = json.loads(DATA.read_text("utf-8"))
    assert (QA / "artifact.md").exists()
    assert len(data["chapters"]) == 37
    document = Document(REFERENCE)
    document.core_properties.title = (
        "Forecast rendimiento y reportes de P&Pmis Construction AI"
    )
    document.core_properties.subject = "Informe técnico Wave O1C"
    document.core_properties.keywords = (
        "Forecast, ETC, EAC, Performance, Reporting, O1C"
    )
    document.core_properties.comments = (
        "Implementación y validación técnica de Forecast rendimiento y reportes"
    )
    document.core_properties.created = datetime.now(UTC)
    document.core_properties.modified = document.core_properties.created
    logo = deepcopy(document.paragraphs[0]._p)
    section = deepcopy(document._element.body.sectPr)
    for node in list(document._element.body):
        document._element.body.remove(node)
    document._element.body.append(logo)
    document._element.body.append(section)
    p(document, "Wave O1C\nForecast rendimiento y reportes", "Title")
    p(
        document,
        "P&Pmis Construction AI\nInforme técnico de implementación\n9 noviembre 2026",
        "Subtitle",
    )
    p(document, data["opening"])
    for index, (title, body) in enumerate(data["chapters"], 1):
        h(document, f"{index} {title}")
        for paragraph in body.split("\n\n"):
            p(document, paragraph)
        if index == 4:
            table(
                document,
                ["Dimensión", "Fuente", "Regla"],
                [[row[0], row[1], row[3]] for row in data["authorities"]],
                [1.0, 2.4, 2.5],
            )
        if index == 31:
            table(
                document,
                ["Suite", "Casos", "Resultado"],
                data["suite_summary"],
                [3.6, 0.8, 1.5],
            )
        if index == 34:
            p(document, data["volume_summary"])
            table(
                document,
                ["Operación", "N", "Mediana ms", "Máximo ms"],
                [
                    [r[0], str(r[1]), f"{r[3]:.2f}", f"{r[4]:.2f}"]
                    for r in data["performance"]
                ],
                [3.15, 0.7, 1.15, 1.15],
            )
    for paragraph in document.paragraphs:
        paragraph.paragraph_format.widow_control = True
        if paragraph.style.name == "Normal":
            paragraph.paragraph_format.keep_together = True
    OUT.mkdir(parents=True, exist_ok=True)
    QA.mkdir(parents=True, exist_ok=True)
    buffer = io.BytesIO()
    document.save(buffer)
    target_path = (
        OUT / "P&Pmis_Wave_O1C_Forecast_Performance_Reporting_Technical_Report.docx"
    )
    with (
        ZipFile(REFERENCE) as source,
        ZipFile(buffer) as generated,
        ZipFile(target_path, "w") as target,
    ):
        for entry in source.infolist():
            payload = source.read(entry.filename)
            if entry.filename == "word/footer1.xml":
                assert payload.count(b"5 noviembre 2026") == 1
                payload = payload.replace(b"5 noviembre 2026", b"9 noviembre 2026")
            target.writestr(
                entry,
                generated.read(entry.filename)
                if entry.filename in {"word/document.xml", "docProps/core.xml"}
                else payload,
            )
    with ZipFile(REFERENCE) as source, ZipFile(target_path) as target:
        changed = [
            name for name in source.namelist() if source.read(name) != target.read(name)
        ]
        assert set(changed) == {
            "word/document.xml",
            "word/footer1.xml",
            "docProps/core.xml",
        }
        assert source.read("word/footer1.xml").replace(
            b"5 noviembre 2026", b"9 noviembre 2026"
        ) == target.read("word/footer1.xml")
    proof = {
        "reference_sha256": REFERENCE_SHA,
        "output_sha256": hashlib.sha256(target_path.read_bytes()).hexdigest(),
        "changed_parts": changed,
        "chapters": 37,
    }
    (QA / "documents-build-manifest.json").write_text(
        json.dumps(proof, indent=2), encoding="utf-8"
    )
    print(json.dumps(proof))


if __name__ == "__main__":
    main()
