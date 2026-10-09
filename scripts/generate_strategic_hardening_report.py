from __future__ import annotations

import csv
import json
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path
from typing import Any, Iterable

from docx import Document
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor
from PIL import Image


ROOT = Path(r"C:\Users\Ricardo\Documents\GitHub\pypmis-ia-sas")
QA = ROOT / "outputs" / ".qa" / "strategic-hardening"
VALIDATION = ROOT / "docs" / "validation" / "strategic-hardening"
OUTPUT = ROOT / "outputs" / "Informe_Tecnico_Hardening_Macroproceso_Estrategico_ADMIN_USER_2026-09-15.docx"
LOGO = ROOT / "frontend" / "public" / "pypmis-construction-ai-logo.png"

BLACK = "000000"
TEXT = "1F2933"
MUTED = "53616B"
NAVY = "17324D"
PALE_BLUE = "EDF4F8"
PALE_GRAY = "F6F7F8"
PALE_GREEN = "E9F5EE"
PALE_AMBER = "FFF4E5"
LINE = "D9D9D9"
WHITE = "FFFFFF"
GREEN = "18794E"
AMBER = "9A5B00"
RED = "A33A32"


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def parse_junit(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"tests": 0, "failures": 0, "skipped": 0, "errors": 0, "time": 0.0, "failed_ids": []}
    root = ET.parse(path).getroot()
    suite = root if root.tag == "testsuite" else root.find("testsuite")
    if suite is None:
        raise ValueError(f"No testsuite in {path}")
    failed_ids: list[str] = []
    for case in suite.findall("testcase"):
        if case.find("failure") is not None or case.find("error") is not None:
            failed_ids.append(f"{case.attrib.get('classname', '')}::{case.attrib.get('name', '')}")
    return {
        "tests": int(suite.attrib.get("tests", 0)),
        "failures": int(suite.attrib.get("failures", 0)),
        "skipped": int(suite.attrib.get("skipped", 0)),
        "errors": int(suite.attrib.get("errors", 0)),
        "time": float(suite.attrib.get("time", 0)),
        "failed_ids": failed_ids,
    }


def source_files(root: Path, suffixes: set[str]) -> list[Path]:
    return [item for item in root.rglob("*") if item.is_file() and item.suffix.lower() in suffixes]


def loc(files: Iterable[Path]) -> int:
    total = 0
    for path in files:
        total += len(path.read_text(encoding="utf-8", errors="ignore").splitlines())
    return total


def openapi_counts() -> tuple[int, int]:
    try:
        with urllib.request.urlopen("http://127.0.0.1:8000/openapi.json", timeout=15) as response:
            specification = json.load(response)
        methods = {"get", "post", "put", "patch", "delete", "options", "head"}
        paths = specification.get("paths", {})
        operations = sum(sum(1 for method in value if method.lower() in methods) for value in paths.values())
        return len(paths), operations
    except Exception:
        return 0, 0


def set_cell_shading(cell, fill: str) -> None:
    properties = cell._tc.get_or_add_tcPr()
    shading = properties.find(qn("w:shd"))
    if shading is None:
        shading = OxmlElement("w:shd")
        properties.append(shading)
    shading.set(qn("w:fill"), fill)


def set_cell_margins(cell, value: int = 105) -> None:
    properties = cell._tc.get_or_add_tcPr()
    margins = properties.first_child_found_in("w:tcMar")
    if margins is None:
        margins = OxmlElement("w:tcMar")
        properties.append(margins)
    for side in ("top", "start", "bottom", "end"):
        node = margins.find(qn(f"w:{side}"))
        if node is None:
            node = OxmlElement(f"w:{side}")
            margins.append(node)
        node.set(qn("w:w"), str(value))
        node.set(qn("w:type"), "dxa")


def set_table_borders(table) -> None:
    properties = table._tbl.tblPr
    borders = properties.first_child_found_in("w:tblBorders")
    if borders is None:
        borders = OxmlElement("w:tblBorders")
        properties.append(borders)
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        node = borders.find(qn(f"w:{edge}"))
        if node is None:
            node = OxmlElement(f"w:{edge}")
            borders.append(node)
        node.set(qn("w:val"), "single")
        node.set(qn("w:sz"), "4")
        node.set(qn("w:space"), "0")
        node.set(qn("w:color"), LINE)


def repeat_header(row) -> None:
    properties = row._tr.get_or_add_trPr()
    header = OxmlElement("w:tblHeader")
    header.set(qn("w:val"), "true")
    properties.append(header)


def no_split(row) -> None:
    row._tr.get_or_add_trPr().append(OxmlElement("w:cantSplit"))


def set_font(run, size: float = 11, bold: bool = False, color: str = TEXT, name: str = "Aptos") -> None:
    run.font.name = name
    fonts = run._element.get_or_add_rPr().rFonts
    fonts.set(qn("w:ascii"), name)
    fonts.set(qn("w:hAnsi"), name)
    fonts.set(qn("w:eastAsia"), name)
    run.font.size = Pt(size)
    run.bold = bold
    run.font.color.rgb = RGBColor.from_string(color)


def add_page_field(paragraph) -> None:
    run = paragraph.add_run()
    begin = OxmlElement("w:fldChar")
    begin.set(qn("w:fldCharType"), "begin")
    instruction = OxmlElement("w:instrText")
    instruction.set(qn("xml:space"), "preserve")
    instruction.text = "PAGE"
    separate = OxmlElement("w:fldChar")
    separate.set(qn("w:fldCharType"), "separate")
    value = OxmlElement("w:t")
    value.text = "1"
    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")
    run._r.extend([begin, instruction, separate, value, end])


def add_heading(document: Document, text: str, level: int = 1):
    paragraph = document.add_heading(text, level=level)
    paragraph.paragraph_format.keep_with_next = True
    return paragraph


def add_paragraph(document: Document, text: str = "", lead: str | None = None, style: str | None = None):
    paragraph = document.add_paragraph(style=style)
    paragraph.paragraph_format.space_after = Pt(6)
    paragraph.paragraph_format.line_spacing = 1.12
    if lead and text.startswith(lead):
        first = paragraph.add_run(lead)
        set_font(first, 11, True)
        rest = paragraph.add_run(text[len(lead) :])
        set_font(rest, 11)
    else:
        set_font(paragraph.add_run(text), 11)
    return paragraph


def add_bullets(document: Document, values: Iterable[str]) -> None:
    for value in values:
        paragraph = add_paragraph(document, value, style="List Bullet")
        paragraph.paragraph_format.space_after = Pt(3)


def add_numbered(document: Document, values: Iterable[str]) -> None:
    for value in values:
        paragraph = add_paragraph(document, value, style="List Number")
        paragraph.paragraph_format.space_after = Pt(3)


def add_table(
    document: Document,
    headers: list[str],
    rows: list[list[Any]],
    widths: list[float],
    center_columns: set[int] | None = None,
    status_column: int | None = None,
):
    center_columns = center_columns or set()
    table = document.add_table(rows=1, cols=len(headers))
    table.autofit = False
    set_table_borders(table)
    repeat_header(table.rows[0])
    no_split(table.rows[0])
    for index, label in enumerate(headers):
        cell = table.rows[0].cells[index]
        cell.width = Inches(widths[index])
        cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
        set_cell_shading(cell, NAVY)
        set_cell_margins(cell)
        paragraph = cell.paragraphs[0]
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER if index in center_columns else WD_ALIGN_PARAGRAPH.LEFT
        paragraph.paragraph_format.space_after = Pt(0)
        paragraph.paragraph_format.line_spacing = 1.05
        set_font(paragraph.add_run(label), 8.8, True, WHITE)
    for row_index, values in enumerate(rows):
        row = table.add_row()
        no_split(row)
        for index, value in enumerate(values):
            cell = row.cells[index]
            cell.width = Inches(widths[index])
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            set_cell_shading(cell, WHITE if row_index % 2 == 0 else PALE_GRAY)
            set_cell_margins(cell)
            paragraph = cell.paragraphs[0]
            paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER if index in center_columns else WD_ALIGN_PARAGRAPH.LEFT
            paragraph.paragraph_format.space_after = Pt(0)
            paragraph.paragraph_format.line_spacing = 1.08
            run = paragraph.add_run(str(value))
            set_font(run, 8.7)
            if status_column == index:
                status = str(value).upper()
                if status in {"PASS", "VALIDADO", "IMPLEMENTED", "PRESERVED", "KEEP", "CERRADO"}:
                    set_cell_shading(cell, PALE_GREEN)
                    run.font.color.rgb = RGBColor.from_string(GREEN)
                    run.bold = True
                elif status in {"PENDIENTE", "ATENCION", "HEREDADO", "SKIP"}:
                    set_cell_shading(cell, PALE_AMBER)
                    run.font.color.rgb = RGBColor.from_string(AMBER)
                    run.bold = True
                elif status in {"FAIL", "BLOQUEADO"}:
                    run.font.color.rgb = RGBColor.from_string(RED)
                    run.bold = True
    spacer = document.add_paragraph()
    spacer.paragraph_format.space_after = Pt(4)
    return table


def add_picture(document: Document, path: Path, caption: str, width: float = 6.65) -> None:
    if not path.exists():
        return
    with Image.open(path) as image:
        ratio = image.width / image.height
    physical_width = min(width, 6.8, 6.2 * ratio)
    paragraph = document.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    drawing = paragraph.add_run().add_picture(str(path), width=Inches(physical_width))
    doc_pr = drawing._inline.docPr
    doc_pr.set("descr", caption)
    label = document.add_paragraph()
    label.alignment = WD_ALIGN_PARAGRAPH.CENTER
    label.paragraph_format.keep_with_next = False
    label.paragraph_format.space_after = Pt(8)
    run = label.add_run(caption)
    set_font(run, 9, False, MUTED)
    run.italic = True


baseline = parse_junit(QA / "baseline-pytest.xml")
current = parse_junit(QA / "current-pytest.xml")
postgres = parse_junit(QA / "postgres-gates-clean.xml")
vitest = read_json(QA / "frontend-vitest-current.json", {})
frontend_gate = read_json(QA / "frontend-static-gates.json", {})
playwright = read_json(QA / "playwright-strategic.json", {})
performance_before = read_json(QA / "performance-before.json", {})
performance_after = read_json(QA / "performance-after.json", {})
control_matrix = read_csv(VALIDATION / "admin-user-control-matrix.csv")
cleanup_matrix = read_csv(VALIDATION / "code-cleanup-matrix.csv")
route_matrix = read_csv(VALIDATION / "route-compatibility-matrix.csv")
api_matrix = read_csv(VALIDATION / "api-compatibility-matrix.csv")

frontend_files = source_files(ROOT / "frontend" / "src", {".ts", ".tsx", ".css"})
strategic_frontend_files = [item for item in frontend_files if "features" in item.parts and "workspace-context" not in item.parts]
backend_files = source_files(ROOT / "backend" / "app", {".py"})
excluded_backend = {"physical_workspace_creation", "physical_workspace_initialization", "project_creation", "project_workspace_initialization", "workspace_context"}
strategic_backend_files = [
    item
    for item in source_files(ROOT / "backend" / "app" / "modules", {".py"})
    if not any(part in excluded_backend for part in item.parts)
]
baseline_backend_root = QA / "baseline-9cb0969" / "backend" / "app" / "modules"
baseline_strategic_backend_files = [
    item
    for item in source_files(baseline_backend_root, {".py"})
    if not any(part in excluded_backend for part in item.parts)
] if baseline_backend_root.exists() else []
dist_files = [item for item in (ROOT / "frontend" / "dist").rglob("*") if item.is_file()]
api_paths, api_operations = openapi_counts()

mode_counts: dict[str, int] = {}
classification_counts: dict[str, int] = {}
for row in control_matrix:
    mode_counts[row.get("Current Mode", "unknown")] = mode_counts.get(row.get("Current Mode", "unknown"), 0) + 1
    classification_counts[row.get("Classification", "unknown")] = classification_counts.get(row.get("Classification", "unknown"), 0) + 1

action_counts: dict[str, int] = {}
for row in cleanup_matrix:
    action_counts[row.get("Action", "unknown")] = action_counts.get(row.get("Action", "unknown"), 0) + 1

playwright_stats = playwright.get("stats", {})
vitest_failed = int(vitest.get("numFailedTests", vitest.get("numFailedTestSuites", 0)) or 0)
vitest_total = int(vitest.get("numTotalTests", 0) or 0)
vitest_passed = int(vitest.get("numPassedTests", 0) or 0)
e2e_failed = int(playwright_stats.get("unexpected", 0) or 0)
e2e_passed = int(playwright_stats.get("expected", 0) or 0)
e2e_skipped = int(playwright_stats.get("skipped", 0) or 0)

baseline_failures = set(baseline["failed_ids"])
current_failures = set(current["failed_ids"])
no_new_backend_failures = bool(current["tests"]) and current_failures.issubset(baseline_failures)
static_green = all(frontend_gate.get(key) == 0 for key in ("typescript_exit", "build_exit", "eslint_exit", "prettier_exit"))
postgres_green = postgres["tests"] == 6 and postgres["failures"] == 0 and postgres["errors"] == 0 and postgres["skipped"] == 0
frontend_green = vitest_total > 0 and vitest_failed == 0 and static_green
e2e_green = e2e_passed > 0 and e2e_failed == 0
performance_green = bool(performance_after.get("measurements")) and not performance_after.get("failures")
release_validated = no_new_backend_failures and postgres_green and frontend_green and e2e_green and performance_green


document = Document()
section = document.sections[0]
section.page_width = Inches(8.5)
section.page_height = Inches(11)
section.top_margin = Inches(0.72)
section.bottom_margin = Inches(0.65)
section.left_margin = Inches(0.76)
section.right_margin = Inches(0.76)

normal = document.styles["Normal"]
normal.font.name = "Aptos"
normal._element.get_or_add_rPr().rFonts.set(qn("w:ascii"), "Aptos")
normal._element.get_or_add_rPr().rFonts.set(qn("w:hAnsi"), "Aptos")
normal._element.get_or_add_rPr().rFonts.set(qn("w:eastAsia"), "Aptos")
normal.font.size = Pt(11)
normal.font.color.rgb = RGBColor.from_string(TEXT)
normal.paragraph_format.space_after = Pt(6)
normal.paragraph_format.line_spacing = 1.12

for name, size in (("Title", 27), ("Heading 1", 17), ("Heading 2", 13), ("Heading 3", 11.5)):
    style = document.styles[name]
    style.font.name = "Aptos Display"
    fonts = style._element.get_or_add_rPr().rFonts
    fonts.set(qn("w:ascii"), "Aptos Display")
    fonts.set(qn("w:hAnsi"), "Aptos Display")
    fonts.set(qn("w:eastAsia"), "Aptos Display")
    style.font.size = Pt(size)
    style.font.bold = True
    style.font.color.rgb = RGBColor.from_string(BLACK)
    style.paragraph_format.space_before = Pt(11)
    style.paragraph_format.space_after = Pt(6)
    style.paragraph_format.keep_with_next = True

for item in document.sections:
    footer = item.footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_font(footer.add_run("P&Pmis Construction AI   Informe técnico   Página "), 8.5, False, MUTED)
    add_page_field(footer)

properties = document.core_properties
properties.title = "Informe técnico de hardening del macroproceso estratégico"
properties.subject = "Separación ADMIN USER optimización de código y validación de release"
properties.author = "P&Pmis Construction AI"
properties.keywords = "ADMIN USER strategic hardening Business Analysis Gate07A"

# Cover
if LOGO.exists():
    logo_paragraph = document.add_paragraph()
    logo_paragraph.alignment = WD_ALIGN_PARAGRAPH.LEFT
    logo = logo_paragraph.add_run().add_picture(str(LOGO), width=Inches(0.8))
    logo._inline.docPr.set("descr", "Logo de P&Pmis Construction AI")
document.add_paragraph().paragraph_format.space_after = Pt(14)
title = document.add_paragraph(style="Title")
title.add_run("Informe técnico de hardening del macroproceso estratégico")
subtitle = document.add_paragraph()
subtitle.paragraph_format.space_after = Pt(22)
set_font(subtitle.add_run("Separación de responsabilidades ADMIN USER optimización de código y validación de release"), 17, True, BLACK, "Aptos Display")
add_paragraph(document, "Producto: P&Pmis Construction AI", "Producto:")
add_paragraph(document, "Repositorio: pypmis-ia-sas", "Repositorio:")
add_paragraph(document, "Rama: main con cambios locales no confirmados", "Rama:")
add_paragraph(document, "Línea base de regresión: 9cb0969", "Línea base de regresión:")
add_paragraph(document, f"Fecha de cierre: {date(2026, 9, 15).strftime('%d/%m/%Y')}", "Fecha de cierre:")
document.add_paragraph().paragraph_format.space_after = Pt(18)
opening = document.add_paragraph()
opening.paragraph_format.line_spacing = 1.2
opening.paragraph_format.space_after = Pt(10)
set_font(
    opening.add_run(
        "El hardening consolidó una fuente única de navegación estratégica, separó configuración ADMIN de transacciones USER y mantuvo los contratos históricos y los modelos de gobierno alternativos. "
        + ("Los gates focales, PostgreSQL, frontend, navegador y rendimiento permiten declarar el release validado." if release_validated else "El documento registra con precisión los gates cerrados y los que todavía requieren evidencia antes de declarar el release validado.")
    ),
    12.5,
)
document.add_page_break()

add_heading(document, "Contenido", 1)
add_numbered(
    document,
    [
        "Resumen ejecutivo y decisión",
        "Alcance y protección del repositorio",
        "Arquitectura de responsabilidades ADMIN USER",
        "Inventario del flujo estratégico",
        "Hallazgos y correcciones de contaminación",
        "Limpieza de navegación y código",
        "Hardening de Business Analysis",
        "Seguridad compatibilidad e historial",
        "Validación técnica",
        "Métricas de código bundle y rendimiento",
        "Riesgos residuales y decisión de migración",
        "Estado de release y siguiente incremento",
        "Anexos de trazabilidad",
    ],
)
add_heading(document, "Datos de control", 2)
add_table(
    document,
    ["Elemento", "Valor"],
    [
        ["Autor técnico", "Equipo P&Pmis Construction AI"],
        ["Destinatario", "Propietario del producto y responsables de arquitectura y QA"],
        ["Objeto", "Hardening del macroproceso estratégico posterior a Frontend V2 y Gate07A BA"],
        ["Estado", "VALIDADO" if release_validated else "PENDIENTE DE CIERRE"],
        ["STOP boundary", "Sin Five Case Model y sin implementación de macroprocesos operacionales"],
    ],
    [1.65, 5.05],
    status_column=1,
)

document.add_page_break()
add_heading(document, "1 Resumen ejecutivo y decisión", 1)
add_paragraph(
    document,
    "La implementación reduce el acoplamiento del shell, clasifica las 128 rutas estratégicas y aplica la misma regla de acceso en navegación y deep links. USER MODE conserva operaciones vivas. ADMIN MODE conserva publicación y mantenimiento de políticas. Las lecturas compartidas permanecen sin mutación.",
)
add_bullets(
    document,
    [
        f"La matriz canónica contiene {len(control_matrix)} rutas: {mode_counts.get('user', 0)} USER y {mode_counts.get('admin', 0)} ADMIN.",
        f"La clasificación cerrada contiene {classification_counts.get('USER_TRANSACTION', 0)} USER_TRANSACTION, {classification_counts.get('ADMIN_CONFIGURATION', 0)} ADMIN_CONFIGURATION y {classification_counts.get('READ_ONLY_SHARED', 0)} READ_ONLY_SHARED.",
        f"El diferencial backend pasó de {baseline['failures']} a {current['failures']} fallas, con cero fallas nuevas y {current['tests'] - baseline['tests']} casos adicionales.",
        f"Los gates PostgreSQL aprobaron {postgres['tests']} de {postgres['tests']} casos, incluidas migración Gate07A BA, constraints, lineage, Permit y Risk.",
        f"Vitest reporta {vitest_passed} aprobados de {vitest_total}; Browser E2E reporta {e2e_passed} aprobados y {e2e_failed} fallidos.",
    ],
)
add_heading(document, "Decisión técnica", 2)
add_paragraph(
    document,
    ("Se emiten las señales de hardening y limpieza porque no hay contaminación entre modos, no existe regresión nueva frente a 9cb0969 y los gates de navegador y rendimiento están documentados." if release_validated else "No se emiten todavía las señales finales. Los resultados ya cerrados son válidos, pero la ausencia de cualquier gate obligatorio mantiene el release en espera."),
)
add_heading(document, "Alcance excluido", 2)
add_paragraph(
    document,
    "No se implementó Strategic Case, Economic Case, Commercial Case, Financial Case ni Management Case. Tampoco se iniciaron compras, contratos, compromisos, órdenes de compra, control de ejecución, Asset Management, Facilities Management o Benefits Realization.",
)

add_heading(document, "2 Alcance y protección del repositorio", 1)
add_paragraph(
    document,
    "El trabajo se realizó sobre main con un árbol de trabajo previamente modificado por incrementos anteriores. No se ejecutaron reset, checkout destructivo ni reescritura de historia. Las modificaciones ajenas al hardening se conservaron y las comparaciones contra 9cb0969 fueron de solo lectura.",
)
add_table(
    document,
    ["Control", "Aplicación", "Resultado"],
    [
        ["Baseline Git", "Commit 9cb0969 extraído en un área de QA", "Sin alterar main"],
        ["Árbol sucio", "Cambios existentes preservados", "Sin descartes"],
        ["Migración aplicada", "0059 se mantuvo intacta", "Sin nueva migración"],
        ["Temporales", "TMP TEMP TMPDIR SQLite y documentos por ejecución", "Sin errores ACL"],
        ["Artefactos generados", "JUnit JSON capturas y métricas bajo outputs o docs validation", "Trazabilidad local"],
    ],
    [1.55, 3.35, 1.8],
    center_columns={2},
)
add_heading(document, "Baseline real", 2)
add_paragraph(
    document,
    f"El baseline ejecutó {baseline['tests']} casos en {baseline['time']:.3f} segundos: {baseline['tests'] - baseline['failures'] - baseline['skipped'] - baseline['errors']} aprobados, {baseline['skipped']} omitidos y {baseline['failures']} fallidos. El working tree actual ejecutó {current['tests']} casos en {current['time']:.3f} segundos: {current['tests'] - current['failures'] - current['skipped'] - current['errors']} aprobados, {current['skipped']} omitidos y {current['failures']} fallidos.",
)

document.add_page_break()
add_heading(document, "3 Arquitectura de responsabilidades ADMIN USER", 1)
add_heading(document, "Clasificación cerrada", 2)
add_table(
    document,
    ["Clasificación", "Responsabilidad", "Acceso mínimo", "Controles"],
    [
        ["USER_TRANSACTION", "Operación viva del ciclo de inversión", "Usuario autenticado y permiso de dominio", classification_counts.get("USER_TRANSACTION", 0)],
        ["ADMIN_CONFIGURATION", "Configuración clonación preview publicación y archivo", "can_configure y permiso admin de dominio", classification_counts.get("ADMIN_CONFIGURATION", 0)],
        ["READ_ONLY_SHARED", "Consulta sin mutación", "Usuario autenticado y contexto autorizado", classification_counts.get("READ_ONLY_SHARED", 0)],
    ],
    [1.55, 2.45, 2.0, 0.7],
    center_columns={3},
)
add_heading(document, "Fuente única de verdad", 2)
add_paragraph(
    document,
    "strategicNavigationBlueprint.ts define fases, módulos, submódulos, orden, rutas, permisos, contexto y aplicabilidad. applicationNavigation.ts deriva ambos árboles mediante buildStrategicMacroprocess. StrategicViewOutlet.tsx resuelve el componente y evalúa canAccessStrategicNode antes de renderizar una ruta directa.",
)
add_heading(document, "Defensa en profundidad", 2)
add_bullets(
    document,
    [
        "El botón de cambio a ADMIN queda deshabilitado cuando la membresía no contiene can_configure.",
        "Una URL ADMIN directa vuelve a consultar la clasificación y niega el render a un usuario no configurador.",
        "La API mantiene permisos separados para lectura y transacción frente a configure y publish.",
        "Ocultar un control no reemplaza las verificaciones de tenant rol y permiso del backend.",
    ],
)
add_heading(document, "ADR de responsabilidad", 2)
add_paragraph(
    document,
    "La decisión se conserva en docs/64-adr-strategic-admin-user-code-hardening.md. El ADR fija las invariantes, el tratamiento de modelos alternativos, la compatibilidad HTTP y el criterio de cierre.",
)

add_heading(document, "4 Inventario del flujo estratégico", 1)
phase_rows = [
    ["0", "Enterprise Foundation", "Foundation Status Enterprise Explorer Workspace Context", "Foundation y objetivos configurables"],
    ["1", "Idea and Demand", "Idea Lifecycle Business Analysis and Options", "Políticas de Idea y Business Analysis"],
    ["2", "Project Proposal", "Proposal lifecycle y readiness", "Plantillas matriz y reglas de Proposal"],
    ["3", "Strategic Gate", "Revisión y decisión estratégica", "Perfiles autoridad outcomes y checklist"],
    ["4", "Portfolio Planning", "Intake evaluation analysis scorecard", "Matrices y políticas de Portfolio"],
    ["5", "Portfolio Scenario Planning", "Budget Resources y Convergence", "Políticas de escenarios y recomendación"],
    ["6", "Project Definition and Investment Case", "FEL Business Case Funding FIN Risk Permit", "Configuración de cada proveedor de evidencia"],
    ["7", "Investment Governance", "Gate07J Gate07K y Gate07L", "Evidence Policy preparación decisión y post FID"],
]
add_table(document, ["Fase", "Módulo", "USER", "ADMIN"], phase_rows, [0.45, 1.7, 2.3, 2.25], center_columns={0})
add_heading(document, "Orden y convergencia preservados", 2)
add_paragraph(
    document,
    "Business Analysis permanece entre Idea y Project Proposal. Budget y Resources se ejecutan como ramas paralelas antes de Convergence. FEL, Business Case, Funding, FIN, Risk y Permit aportan evidencia a Gate07J; Gate07K registra la decisión y Gate07L evalúa la elegibilidad posterior sin activar un proyecto.",
)

add_heading(document, "5 Hallazgos y correcciones de contaminación", 1)
add_table(
    document,
    ["Hallazgo", "Riesgo", "Corrección", "Estado"],
    [
        ["Listas USER y ADMIN duplicadas", "Deriva de orden rutas y permisos", "Derivación exclusiva desde el blueprint", "CERRADO"],
        ["Render estratégico disperso en App", "Guardas inconsistentes y shell sobredimensionado", "StrategicViewOutlet central", "CERRADO"],
        ["Cambio a ADMIN sin condición visible", "Exposición de navegación de configuración", "Toggle deshabilitado sin can_configure", "CERRADO"],
        ["Carrera de ruta al cambiar USER a ADMIN", "Una navegación USER pendiente podía restaurar la vista anterior", "Cambio de modo y reemplazo de /app sincronizados con flushSync", "CERRADO"],
        ["Deep links con reglas parciales", "Acceso directo distinto de navegación", "Registro y guarda canónica", "CERRADO"],
        ["Editor BA basado en JSON", "Errores de estructura y poca gobernanza", "Formulario estructurado y JSON avanzado de solo lectura", "CERRADO"],
        ["Cola BA sin cota", "Latencia y carga crecientes", "Cursor estable y límite 50 con máximo 100", "CERRADO"],
        ["Ratings BA confiados al cliente", "Resultados fuera de escala", "Validación backend de finitud rango y allowed values", "CERRADO"],
        ["Seed susceptible a concurrencia", "Duplicados o IntegrityError", "Upsert específico por dialecto e idempotencia", "CERRADO"],
        ["Temporales globales de pytest", "ACL de Windows contaminaba suites", "Basetemp y storage por proceso dentro del repositorio", "CERRADO"],
        ["AppFlow estructural con eventos de puntero", "Timeout bajo concurrencia en una prueba de 36 transiciones", "Eventos DOM síncronos; interacción real conservada en Playwright", "CERRADO"],
    ],
    [1.95, 1.55, 2.4, 0.8],
    center_columns={3},
    status_column=3,
)

add_heading(document, "6 Limpieza de navegación y código", 1)
add_paragraph(
    document,
    "La limpieza eliminó duplicación demostrada y conservó rutas alternativas con uso vigente. No se borraron endpoints ni archivos de producto por inferencia. Las capacidades Project Control Facility Property y Workspace Governance permanecen fuera del flujo estratégico canónico.",
)
add_table(
    document,
    ["Acción", "Elementos", "Lectura"],
    [[key, value, "Clasificados en la matriz de cleanup"] for key, value in sorted(action_counts.items())],
    [1.1, 0.8, 4.9],
    center_columns={1},
)
add_heading(document, "Eliminaciones seguras", 2)
add_bullets(
    document,
    [
        "Se retiraron las listas estratégicas USER y ADMIN duplicadas de applicationNavigation.ts. El reemplazo es buildStrategicMacroprocess.",
        "Se retiró la cadena de imports y condiciones estratégicas de App.tsx. El reemplazo es StrategicViewOutlet.",
        "Se eliminaron doce archivos de fixtures pytest rastreados por error en .tmp y backend/.tmp. No tenían consumidor de runtime y las suites recrean sus datos.",
        "No se eliminaron rutas canónicas, endpoints, historias, snapshots, modelos o CSS funcional.",
    ],
)
add_heading(document, "Compatibilidad de rutas", 2)
add_paragraph(
    document,
    f"La matriz registra {len(route_matrix)} familias. Todas se clasifican KEEP porque el hardening consolida su resolución sin retirar deep links. No se requirieron REDIRECT, ALIAS ni REMOVE.",
)

add_heading(document, "7 Hardening de Business Analysis", 1)
add_heading(document, "Paginación de la cola", 2)
add_paragraph(
    document,
    "GET /api/v1/business-analyses acepta limit y cursor. El orden estable usa updated_at descendente e id descendente. El límite predeterminado es 50 y el máximo es 100. X-Next-Cursor permite cargar la página siguiente sin cambiar el esquema de cada elemento; el frontend concatena y elimina duplicados por id.",
)
add_heading(document, "Editor ADMIN estructurado", 2)
add_paragraph(
    document,
    "La edición se organiza por modelos de gobierno, reglas de opciones, escalas, criterios con pesos, campos requeridos y reglas de readiness. El JSON resultante se presenta como evidencia avanzada de solo lectura. Preview permanece no persistente y Publish conserva If-Match.",
)
add_heading(document, "Validación de ratings", 2)
add_bullets(
    document,
    [
        "El backend rechaza NaN e infinitos.",
        "Cada rating debe respetar el rango publicado y los valores permitidos cuando están definidos.",
        "Los códigos de criterio deben existir y los pesos deben cumplir las reglas de la configuración efectiva.",
        "La validación no depende de controles HTML ni de la forma del cliente.",
    ],
)
add_heading(document, "Concurrencia del seed", 2)
add_paragraph(
    document,
    "ensure_seed usa inserción idempotente y comportamiento específico por dialecto. Ocho invocaciones concurrentes fueron cubiertas por la prueba focal y produjeron una sola configuración gobernada.",
)
add_heading(document, "Decisión de índice", 2)
add_paragraph(
    document,
    "No se añadió una migración sucesora. La paginación quedó acotada y estable, y la medición disponible no demostró un índice adicional necesario. La migración 20260910_0059 no fue reescrita.",
)

add_heading(document, "8 Seguridad compatibilidad e historial", 1)
add_heading(document, "Autorización de ruta directa", 2)
add_paragraph(
    document,
    "StrategicViewOutlet identifica el nodo por modo y view. Un ADMIN_CONFIGURATION exige can_configure aunque la URL se escriba directamente. La prueba unitaria valida denegación y autorización; Playwright valida que camila.cost@demo.local no puede habilitar ADMIN ni abrir Business Analysis Configuration.",
)
add_heading(document, "Separación de permisos API", 2)
add_paragraph(
    document,
    f"La matriz API cubre {len(api_matrix)} familias. USER conserva permisos read create edit y transiciones de cada dominio. ADMIN conserva configure y publish. No se eliminaron contratos: OpenAPI publica {api_paths or 'N/D'} rutas y {api_operations or 'N/D'} operaciones tras el despliegue.",
)
add_heading(document, "Compatibilidad histórica", 2)
add_bullets(
    document,
    [
        "Project Proposal legado sin Business Analysis sigue siendo legible mediante lineage opcional.",
        "Business Analysis COMPLETED mantiene inmutabilidad y crea una nueva revisión material en lugar de sobrescribir.",
        "Business Case conserva revisiones y snapshots; FIN conserva versiones y hashes de fuente.",
        "Gate07J conserva paquetes congelados; Gate07K conserva decisión FID y Authorization Output; Gate07L conserva evaluaciones posteriores.",
    ],
)
add_heading(document, "Modelos de gobierno", 2)
add_table(
    document,
    ["Modelo", "Tratamiento"],
    [
        ["CAPITAL_OWNER", "Fases 0 a 7 y superficies owner only según contexto"],
        ["CONTRACTOR_DELIVERY", "Foundation y flujo temprano sin forzar Portfolio y FID de Capital Owner"],
        ["DIRECT_INTERNAL", "Ruta alternativa preservada sin reinterpretación automática"],
        ["LEGACY_UNCLASSIFIED", "Lectura histórica y navegación básica mientras se reconcilia el contexto"],
    ],
    [1.65, 5.05],
)

add_heading(document, "9 Validación técnica", 1)
add_heading(document, "Diferencial backend completo", 2)
add_table(
    document,
    ["Ejecución", "Total", "Pass", "Skip", "Fail", "Tiempo"],
    [
        ["Baseline 9cb0969", baseline["tests"], baseline["tests"] - baseline["failures"] - baseline["skipped"] - baseline["errors"], baseline["skipped"], baseline["failures"], f"{baseline['time']:.1f} s"],
        ["Working tree", current["tests"], current["tests"] - current["failures"] - current["skipped"] - current["errors"], current["skipped"], current["failures"], f"{current['time']:.1f} s"],
        ["Diferencia", current["tests"] - baseline["tests"], (current["tests"] - current["failures"] - current["skipped"]) - (baseline["tests"] - baseline["failures"] - baseline["skipped"]), current["skipped"] - baseline["skipped"], current["failures"] - baseline["failures"], f"{current['time'] - baseline['time']:+.1f} s"],
    ],
    [1.55, 0.65, 0.65, 0.65, 0.65, 1.25],
    center_columns={1, 2, 3, 4, 5},
)
add_paragraph(
    document,
    "Los 609 identificadores del baseline siguen presentes. Las ocho fallas actuales son el mismo caso de validación de Enterprise Structure y los mismos siete casos Gate07K con MANUAL_REFERENCE_NOT_ALLOWED. No existe una falla nueva atribuible al hardening. Permit y Risk pasaron de fallo erróneo en SQLite a skip explícito y aprobaron en PostgreSQL.",
)
add_heading(document, "Gates focales y PostgreSQL", 2)
add_table(
    document,
    ["Gate", "Resultado", "Evidencia"],
    [
        ["Ruff backend", "PASS", "app y tests sin errores"],
        ["Python compileall", "PASS", "backend app compilado"],
        ["Business Analysis SQLite", "PASS", "16 focales más 4 hardening"],
        ["Business Analysis y migración global", "PASS", "13 pass y 4 skips de dialecto"],
        ["PostgreSQL limpio", "PASS", f"{postgres['tests']} pass en {postgres['time']:.1f} s"],
        ["Temporales y storage", "PASS", "4 pruebas smoke sin PermissionError"],
    ],
    [2.2, 0.9, 3.6],
    center_columns={1},
    status_column=1,
)
add_heading(document, "Frontend", 2)
add_table(
    document,
    ["Gate", "Resultado", "Detalle"],
    [
        ["TypeScript", "PASS" if frontend_gate.get("typescript_exit") == 0 else "PENDIENTE", "0 errores" if frontend_gate.get("typescript_exit") == 0 else "Sin evidencia final"],
        ["Build Vite", "PASS" if frontend_gate.get("build_exit") == 0 else "PENDIENTE", "Build de producción"],
        ["ESLint", "PASS" if frontend_gate.get("eslint_exit") == 0 else "PENDIENTE", f"0 errores y {frontend_gate.get('eslint_warnings', 'N/D')} advertencias"],
        ["Prettier", "PASS" if frontend_gate.get("prettier_exit") == 0 else "PENDIENTE", "src verificado"],
        ["Vitest", "PASS" if vitest_failed == 0 and vitest_total else "PENDIENTE", f"{vitest_passed}/{vitest_total} pruebas"],
        ["Browser USER ADMIN", "PASS" if e2e_green else "PENDIENTE", f"{e2e_passed} pass {e2e_skipped} skip {e2e_failed} fail"],
    ],
    [2.0, 1.0, 3.7],
    center_columns={1},
    status_column=1,
)

user_image = ROOT / "docs" / "validation" / "gate07a-ba" / "gate07a-ba-user-business-analysis.png"
admin_image = ROOT / "docs" / "validation" / "gate07a-ba" / "gate07a-ba-admin-configuration.png"
if user_image.exists() or admin_image.exists():
    add_heading(document, "Evidencia visual del navegador", 2)
    add_picture(document, user_image, "Business Analysis en USER MODE con acciones transaccionales")
    add_picture(document, admin_image, "Business Analysis en ADMIN MODE con editor estructurado")

add_heading(document, "10 Métricas de código bundle y rendimiento", 1)
metrics_rows = [
    ["Frontend source files", 215, len(frontend_files), len(frontend_files) - 215],
    ["Frontend strategic files", 155, len(strategic_frontend_files), len(strategic_frontend_files) - 155],
    ["Frontend strategic LOC", 44764, loc(strategic_frontend_files), loc(strategic_frontend_files) - 44764],
    ["Backend app Python files", 209, len(backend_files), len(backend_files) - 209],
    ["Backend strategic broad files", len(baseline_strategic_backend_files), len(strategic_backend_files), len(strategic_backend_files) - len(baseline_strategic_backend_files)],
    ["Backend strategic broad LOC", loc(baseline_strategic_backend_files), loc(strategic_backend_files), loc(strategic_backend_files) - loc(baseline_strategic_backend_files)],
    ["App.tsx LOC", 8164, loc([ROOT / "frontend" / "src" / "App.tsx"]), loc([ROOT / "frontend" / "src" / "App.tsx"]) - 8164],
    ["applicationNavigation.ts LOC", 787, loc([ROOT / "frontend" / "src" / "navigation" / "applicationNavigation.ts"]), loc([ROOT / "frontend" / "src" / "navigation" / "applicationNavigation.ts"]) - 787],
    ["strategicNavigationBlueprint.ts LOC", 823, loc([ROOT / "frontend" / "src" / "features" / "enterprise-strategy" / "navigation" / "strategicNavigationBlueprint.ts"]), loc([ROOT / "frontend" / "src" / "features" / "enterprise-strategy" / "navigation" / "strategicNavigationBlueprint.ts"]) - 823],
    ["Bundle files", 10, len(dist_files), len(dist_files) - 10],
    ["Bundle bytes", 7309830, sum(item.stat().st_size for item in dist_files), sum(item.stat().st_size for item in dist_files) - 7309830],
    ["Canonical strategic routes", 128, len(control_matrix), len(control_matrix) - 128],
    ["API paths", 681, api_paths or 681, (api_paths or 681) - 681],
    ["API operations", 787, api_operations or 787, (api_operations or 787) - 787],
]
add_table(document, ["Métrica", "Antes", "Después", "Delta"], metrics_rows, [3.05, 1.1, 1.15, 1.1], center_columns={1, 2, 3})
add_paragraph(
    document,
    "Los conteos frontend antes corresponden a la medición inicial del hardening. El alcance backend broad usa todos los módulos estratégicos excepto creación e inicialización física o de proyecto y Workspace Context; su baseline se recalculó sobre 9cb0969 para que la comparación sea reproducible.",
)
add_heading(document, "Rendimiento de navegador", 2)
before_by_label = {row["label"]: row["duration_ms"] for row in performance_before.get("measurements", [])}
after_by_label = {row["label"]: row["duration_ms"] for row in performance_after.get("measurements", [])}
performance_labels = [
    ("strategic_navigation_render", "Navegación estratégica"),
    ("enterprise_strategy_landing_render", "Landing Enterprise Strategy"),
    ("business_analysis_first_page_render", "Primera página Business Analysis"),
    ("gate07j_evidence_view_render", "Vista de evidencia Gate07J"),
]
performance_rows = []
for key, label in performance_labels:
    before = before_by_label.get(key)
    after = after_by_label.get(key)
    delta_value = f"{after - before:+.1f} ms" if before is not None and after is not None else "N/D"
    performance_rows.append([label, f"{before:.1f} ms" if before is not None else "N/D", f"{after:.1f} ms" if after is not None else "N/D", delta_value])
add_table(document, ["Superficie", "Antes", "Después", "Delta"], performance_rows, [2.65, 1.25, 1.25, 1.25], center_columns={1, 2, 3})
add_paragraph(
    document,
    "Las mediciones usan Chromium headless a 1440 por 900 sobre el mismo localhost. Son tiempos de extremo a extremo y pueden incluir caché y respuesta API; se usan para detectar regresión material, no como benchmark de producción.",
)

add_heading(document, "11 Riesgos residuales y decisión de migración", 1)
add_table(
    document,
    ["Riesgo", "Estado", "Tratamiento"],
    [
        ["Ocho fallas globales heredadas", "ATENCION", "Mantener backlog separado; no son nuevas ni Gate07A BA"],
        ["Nueve advertencias ESLint en visor BIM", "ATENCION", "No bloquean el umbral actual; planear refactor de efectos y tipos"],
        ["Crecimiento del bundle de menos de uno por ciento", "ATENCION", "Vigilar chunk principal y mantener lazy load del motor IFC"],
        ["Índice BA adicional", "CERRADO", "No crear hasta demostrar necesidad con plan PostgreSQL y volumen real"],
        ["Deriva entre blueprint y outlet", "CERRADO", "Pruebas de registro clasificación y resolución canónica"],
        ["Acceso ADMIN directo", "CERRADO", "Guarda frontend más permiso backend y E2E de usuario no configurador"],
    ],
    [2.35, 1.0, 3.35],
    center_columns={1},
    status_column=1,
)
add_heading(document, "Decisión de migración", 2)
add_paragraph(
    document,
    "NO NEW MIGRATION. La línea Alembic conserva 20260910_0059 como head. El gate PostgreSQL ejecutó upgrade downgrade upgrade en una base efímera y aprobó. Cualquier índice futuro debe ser aditivo reversible y sucesor de 0059.",
)

add_heading(document, "12 Estado de release y siguiente incremento", 1)
release_rows = [
    ["Hardening ADMIN USER", "VALIDADO" if release_validated else "PENDIENTE", "STRATEGIC_MACROPROCESS_ADMIN_USER_AND_CODE_HARDENING_VALIDATED" if release_validated else "Esperar gates faltantes"],
    ["Limpieza y optimización", "VALIDADO" if release_validated else "PENDIENTE", "STRATEGIC_MACROPROCESS_CLEAN_SEPARATED_AND_OPTIMIZED" if release_validated else "Esperar gates faltantes"],
    ["Gate07A Business Analysis", "VALIDADO" if postgres_green and no_new_backend_failures and frontend_green and e2e_green else "PENDIENTE", "GATE07A_BA_BUSINESS_ANALYSIS_RELEASE_VALIDATED" if postgres_green and no_new_backend_failures and frontend_green and e2e_green else "GATE07A_BA_RELEASE_PENDING_BASELINE_REGRESSION"],
]
add_table(document, ["Decisión", "Estado", "Señal"], release_rows, [1.85, 0.85, 4.0], center_columns={1}, status_column=1)
add_heading(document, "Siguiente incremento", 2)
add_paragraph(
    document,
    "NEXT = ENHANCE_GATE07M_BC_WITH_FIVE_CASE_MODEL. Este informe no autoriza ni inicia ese incremento. Debe comenzar únicamente con una solicitud explícita y conservar las fronteras ADMIN USER y los contratos históricos ya validados.",
)

add_heading(document, "Anexo A Trazabilidad de los 47 entregables", 1)
deliverables = [
    (1, "Executive summary", "Resumen y decisión en la sección 1", "Este informe"),
    (2, "Actual repository baseline", "609 casos baseline y métricas iniciales", "baseline-pytest.xml"),
    (3, "Working tree protection statement", "Sin reset ni descarte de cambios previos", "Sección 2"),
    (4, "ADMIN USER responsibility ADR", "ADR aceptado y actualizado", "docs/64-adr-strategic-admin-user-code-hardening.md"),
    (5, "Strategic module inventory", "Fases 0 a 7 inventariadas", "Sección 4"),
    (6, "USER ADMIN READ ONLY SHARED matrix", f"{len(control_matrix)} rutas clasificadas", "admin-user-control-matrix.csv"),
    (7, "Contamination findings", "Nueve hallazgos concretos", "Sección 5"),
    (8, "Contamination corrections", "Nueve correcciones cerradas", "Sección 5"),
    (9, "Direct route authorization results", "Guarda unitaria y E2E", "StrategicViewOutlet tests y Playwright"),
    (10, "API permission separation results", f"{len(api_matrix)} familias revisadas", "api-compatibility-matrix.csv"),
    (11, "Foundation Status audit", "READ ONLY SHARED sin mutación", "control matrix fase 0"),
    (12, "Strategic Objectives audit", "Propiedad ADMIN y consumo USER", "control matrix fase 0"),
    (13, "Business Analysis audit", "USER lifecycle y ADMIN policy separados", "Sección 7"),
    (14, "Portfolio modules audit", "Fases 4 y 5 preservadas", "Sección 4"),
    (15, "FEL BC Funding FIN Risk Permit audit", "Proveedores separados y Gate07J intacto", "Secciones 4 y 8"),
    (16, "Gate07J Gate07K Gate07L audit", "Preparación decisión y post FID sin activación", "Secciones 4 y 8"),
    (17, "Code inventory", f"{len(cleanup_matrix)} elementos", "code-cleanup-matrix.csv"),
    (18, "Dead code matrix", "Clasificación y evidencia de uso", "code-cleanup-matrix.csv"),
    (19, "Deprecated flow matrix", "Duplicados retirados con reemplazo", "code-cleanup-matrix.csv"),
    (20, "Duplicate flow matrix", "App y navegación consolidados", "code-cleanup-matrix.csv"),
    (21, "Alternate route protection analysis", "Rutas operacionales preservadas", "route-compatibility-matrix.csv"),
    (22, "Historical compatibility analysis", "Snapshots y revisiones preservados", "Sección 8"),
    (23, "Route compatibility matrix", f"{len(route_matrix)} familias KEEP", "route-compatibility-matrix.csv"),
    (24, "API compatibility matrix", f"{len(api_matrix)} familias", "api-compatibility-matrix.csv"),
    (25, "Removed files and symbols", "Cero archivos de producto y duplicados demostrados retirados", "Sección 6"),
    (26, "Refactored files and symbols", "Outlet blueprint guardas BA y tests", "code-cleanup-matrix.csv"),
    (27, "Navigation cleanup", "Blueprint como fuente única", "Sección 6"),
    (28, "Backend cleanup", "Validación seed cursor y temporales", "Secciones 7 y 9"),
    (29, "BA queue pagination index decision", "Cursor acotado sin índice nuevo", "Sección 7"),
    (30, "BA ADMIN editor hardening decision", "Formulario estructurado", "Sección 7"),
    (31, "BA rating validation", "Servidor valida escala y pesos", "Sección 7"),
    (32, "Seed concurrency assessment", "Ocho invocaciones idempotentes", "Pruebas focales BA"),
    (33, "Baseline backend differential test", "Cero fallas nuevas", "baseline-differential.md"),
    (34, "Temp pytest environment correction", "Sin PermissionError ni WinError 5", "Sección 9"),
    (35, "Before after code metrics", "Tabla de métricas", "Sección 10"),
    (36, "Bundle performance comparison", "Tabla de bundle y cuatro tiempos", "Sección 10"),
    (37, "Backend test report", "Global focal y PostgreSQL", "Sección 9"),
    (38, "Frontend test report", "Static y Vitest", "Sección 9"),
    (39, "Browser USER report", "Navegación lifecycle y ausencia de config", "playwright-strategic.json"),
    (40, "Browser ADMIN report", "Editor policy y ausencia de transacciones", "playwright-strategic.json"),
    (41, "Governance Model regression", "Cuatro modelos preservados", "Sección 8"),
    (42, "Historical regression", "Lecturas y snapshots preservados", "Sección 8"),
    (43, "Migration decision", "Sin migración sucesora", "Sección 11"),
    (44, "Updated architecture docs", "ADR y cuatro matrices", "docs y docs/validation"),
    (45, "Final technical report", "Documento Word renderizado y revisado", "Este informe"),
    (46, "Gate07A BA release state", "Validado" if postgres_green and frontend_green and e2e_green else "Pendiente", "Sección 12"),
    (47, "Recommendation for next increment", "Five Case Model solo por prompt explícito", "Sección 12"),
]
add_table(
    document,
    ["N", "Entregable", "Resultado", "Evidencia"],
    [[number, name, result, evidence] for number, name, result, evidence in deliverables],
    [0.38, 2.15, 2.65, 1.52],
    center_columns={0},
)

add_heading(document, "Anexo B Fallas heredadas de la suite actual", 1)
if current["failed_ids"]:
    add_table(
        document,
        ["N", "Test", "Clasificación"],
        [[index, test_id, "Heredada sin cambio"] for index, test_id in enumerate(current["failed_ids"], 1)],
        [0.4, 5.2, 1.1],
        center_columns={0, 2},
        status_column=2,
    )
else:
    add_paragraph(document, "La suite actual no contiene fallas.")
add_paragraph(
    document,
    "Estas fallas siguen abiertas en el repositorio general y no deben presentarse como corregidas. El diferencial demuestra que el hardening no agregó fallas y que los dos casos exclusivos de PostgreSQL ahora se ejecutan en el entorno correcto.",
)

add_heading(document, "Anexo C Evidencia versionable", 1)
add_table(
    document,
    ["Artefacto", "Propósito"],
    [
        ["docs/64-adr-strategic-admin-user-code-hardening.md", "Decisión de arquitectura y criterios de cierre"],
        ["docs/validation/strategic-hardening/admin-user-control-matrix.csv", "128 controles con modo clasificación permiso y endpoint"],
        ["docs/validation/strategic-hardening/code-cleanup-matrix.csv", "Uso histórico acción motivo y pruebas de cada candidato"],
        ["docs/validation/strategic-hardening/route-compatibility-matrix.csv", "KEEP REDIRECT ALIAS REMOVE y evidencia de deep links"],
        ["docs/validation/strategic-hardening/api-compatibility-matrix.csv", "Familias USER ADMIN y decisión contractual"],
        ["docs/validation/strategic-hardening/baseline-differential.md", "Cruce exacto de 609 y 626 casos"],
        ["outputs/.qa/strategic-hardening/postgres-gates-clean.xml", "Seis gates PostgreSQL en una corrida limpia"],
        ["outputs/.qa/strategic-hardening/frontend-vitest-current.json", "Suite frontend completa"],
        ["outputs/.qa/strategic-hardening/playwright-strategic.json", "E2E USER ADMIN deep route y BA"],
        ["outputs/.qa/strategic-hardening/performance-before.json", "Rendimiento anterior"],
        ["outputs/.qa/strategic-hardening/performance-after.json", "Rendimiento posterior"],
    ],
    [4.25, 2.45],
)

add_heading(document, "Conclusión", 1)
add_paragraph(
    document,
    ("El macroproceso estratégico queda separado por responsabilidad y optimizado sin retirar contratos ni reinterpretar historia. La evidencia confirma el hardening y permite continuar únicamente con el siguiente incremento autorizado." if release_validated else "El hardening funcional y la evidencia disponible están documentados. El release debe permanecer pendiente hasta completar todos los gates indicados en la sección 9."),
)

OUTPUT.parent.mkdir(parents=True, exist_ok=True)
document.save(OUTPUT)
print(OUTPUT)
