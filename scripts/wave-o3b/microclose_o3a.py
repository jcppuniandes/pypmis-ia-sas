"""Append documentary closure without rewriting O3A results or original artifacts."""

import hashlib
import json
from pathlib import Path

from docx import Document
from docx.shared import Pt

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "outputs/wave-o3a-construction-field-operations-20261119"
OUT = ROOT / "outputs/wave-o3a-documentary-closeout-20261119"
QA = ROOT / "outputs/.qa/wave-o3b-20261119/microclose"
MARKER = "WAVE_O3A_CONSTRUCTION_FIELD_OPERATIONS_FOUNDATION_RELEASE_VALIDATED"
NAME = "P&Pmis_Wave_O3A_Construction_Field_Operations_Technical_Report"


def main():
    QA.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    release = json.loads(
        (ROOT / "outputs/.qa/wave-o3a-20261118/release-decision.json").read_text(
            "utf-8"
        )
    )
    assert release["release_marker"] == MARKER and release["artifacts_reviewed"]
    original = SOURCE / (NAME + ".docx")
    digest = hashlib.sha256(original.read_bytes()).hexdigest()
    assert digest == release["artifacts"][original.name]
    doc = Document(original)
    before = [p.text for p in doc.paragraphs]
    heading = doc.add_heading("Cierre documental O3A", level=1)
    heading.paragraph_format.page_break_before = True
    for text in [
        "Se explicita el cierre técnico O3A con el marcador siguiente, consistente con los controles de la matriz de release del corte del 19 de noviembre de 2026.",
        MARKER,
        "Se conserva como antecedente el estado VALIDADO EN ENTORNO AISLADO. Este complemento documental no repite las regresiones ni modifica los resultados, las evidencias o el alcance de la validación histórica.",
        "O3A-S3-UI01 continúa ABIERTO: después de adoptar evidencia, los indicadores del módulo receptor requieren usar su acción Actualizar. O3A-S3-01 continúa ABIERTO: la recuperación de reservas y conciliación de fuentes adoptadas requiere una decisión gobernada del receptor. Ambos son pendientes S3 no bloqueantes del corte y no se declaran resueltos.",
        "El cierre técnico no autoriza despliegue ni migración de producción, no constituye aceptación formal de negocio y no modifica el proyecto 14.",
    ]:
        paragraph = doc.add_paragraph(text)
        paragraph.paragraph_format.space_after = Pt(10)
        paragraph.paragraph_format.line_spacing = 1.12
    target = OUT / (NAME + "_Documentary_Closeout.docx")
    if target.exists():
        previous = json.loads((QA / "word-proof.json").read_text("utf-8"))
        assert (
            hashlib.sha256(target.read_bytes()).hexdigest()
            == previous["updated_sha256"]
        ), "Do not overwrite user edits"
    doc.save(target)
    assert [p.text for p in Document(target).paragraphs][: len(before)] == before
    assert hashlib.sha256(original.read_bytes()).hexdigest() == digest
    (QA / "word-proof.json").write_text(
        json.dumps(
            {
                "original_sha256": digest,
                "original_preserved": True,
                "historical_paragraphs_unchanged": True,
                "release_marker": MARKER,
                "updated_sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(target)


if __name__ == "__main__":
    main()
