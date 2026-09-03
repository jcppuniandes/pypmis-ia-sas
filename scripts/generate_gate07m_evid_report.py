from __future__ import annotations

import json
import re
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.shared import Inches, Pt
from generate_gate07i_report import (
    CALLOUT,
    DARK_BLUE,
    INK,
    POSITIVE,
    RISK,
    TEAL,
    add_bottom_rule,
    add_callout,
    add_page_number,
    add_table,
    configure_styles,
    set_image_alt,
    set_run,
)

REPO = Path(__file__).resolve().parents[1]
PROMPT = Path(
    r"C:\Users\Ricardo\Documents\P&P\P&Pmis Construction AI\Diseño\Portfolio"
    r"\PROMPT_07M_EVID_GATE07J_EVID_UPDATE_BUSINESS_CASE_AND_ECONOMIC_FINANCIAL_READINESS.md"
)
APPLY_EVIDENCE = REPO / "outputs" / "technical_reports" / "gate07m_evid_policy_apply.json"
OUTPUT = (
    REPO
    / "outputs"
    / "technical_reports"
    / "Informe_Tecnico_Gate_07M_EVID_Policy_Update_20260903.docx"
)
LOGO = REPO / "frontend" / "public" / "pypmis-construction-ai-logo.png"

# Resolved document system: standard_business_brief + memo_masthead.
# Named override: dense policy and traceability tables use 7.4–8.2 pt text.


def page_break(doc: Document) -> None:
    paragraph = doc.add_paragraph()
    paragraph.paragraph_format.space_after = Pt(0)
    paragraph.add_run().add_break(WD_BREAK.PAGE)
    anchor = doc.add_paragraph()
    anchor.paragraph_format.space_after = Pt(0)
    anchor.paragraph_format.line_spacing = 0.1
    set_run(anchor.add_run("\u200b"), size=1, color="FFFFFF")


def source_note(doc: Document, text: str) -> None:
    paragraph = doc.add_paragraph()
    paragraph.paragraph_format.space_before = Pt(4)
    paragraph.paragraph_format.space_after = Pt(5)
    set_run(paragraph.add_run(text), size=8, color="5F6B76", italic=True)


def apply_record() -> dict[str, object]:
    return json.loads(APPLY_EVIDENCE.read_text(encoding="utf-8"))


def title_page(doc: Document, record: dict[str, object]) -> None:
    doc.settings.odd_and_even_pages_header_footer = True
    section = doc.sections[0]
    for header in (section.header.paragraphs[0], section.even_page_header.paragraphs[0]):
        header.alignment = WD_ALIGN_PARAGRAPH.LEFT
        set_run(header.add_run("TECHNICAL REPORT · GATE 07M-EVID"), size=8.5, color="5F6B76", bold=True)
        add_bottom_rule(header, color="D9E1E8", size=6)
    for footer in (section.footer.paragraphs[0], section.even_page_footer.paragraphs[0]):
        add_page_number(footer)

    if LOGO.exists():
        paragraph = doc.add_paragraph()
        paragraph.paragraph_format.space_after = Pt(8)
        picture = paragraph.add_run().add_picture(str(LOGO), width=Inches(0.72))
        set_image_alt(picture, "Logotipo de P&Pmis Construction AI")
    kicker = doc.add_paragraph()
    kicker.paragraph_format.space_after = Pt(4)
    set_run(kicker.add_run("INFORME TÉCNICO DE IMPLEMENTACIÓN"), size=10, color=TEAL, bold=True)
    title = doc.add_paragraph()
    title.paragraph_format.space_after = Pt(4)
    set_run(title.add_run("Gate 07M-EVID"), size=25, color=INK, bold=True)
    subtitle = doc.add_paragraph()
    subtitle.paragraph_format.space_after = Pt(16)
    set_run(
        subtitle.add_run("Actualización Gate07J-EVID para Business Case y Economic-Financial Readiness"),
        size=14,
        color=DARK_BLUE,
        bold=True,
    )
    metadata = (
        ("Aplicación", "P&Pmis Construction AI"),
        ("Fecha de corte", "3 de septiembre de 2026"),
        ("Repositorio", "pypmis-ia-sas · rama main · working tree preservado"),
        ("Base de datos", f"Alembic {record['migration_head']} · sin migración nueva para 07M-EVID"),
        ("Política", f"ID {record['policy_id']} · revisión {record['policy_revision']}"),
        ("Effective from", str(record["effective_from"])),
        ("Salida", "READY_FOR_BUSINESS_CASE_AND_ECONOMIC_FINANCIAL_GATE_EVIDENCE"),
        ("Estado exclusivo", "GATE07M_EVID_POLICY_UPDATE_VALIDATED"),
        ("NEXT", "READY_TO_REVALIDATE_NEW_FID_PATH"),
    )
    for label, value in metadata:
        paragraph = doc.add_paragraph()
        paragraph.paragraph_format.space_after = Pt(2)
        set_run(paragraph.add_run(f"{label}: "), size=10, color=INK, bold=True)
        set_run(paragraph.add_run(value), size=10)
    rule = doc.add_paragraph()
    rule.paragraph_format.space_before = Pt(10)
    add_bottom_rule(rule)
    add_callout(
        doc,
        "Resultado ejecutivo",
        "Se amplió el motor abierto Gate07J-EVID reutilizando sus contratos, policy lifecycle, preview, "
        "versionado y snapshots. Business Case queda como evidencia Clase A bloqueante por proyecto; FIN es "
        "Clase B no bloqueante en PYP-INV-SELECT y Clase A bloqueante en PYP-FFA. La publicación fue explícita, "
        "fechada y auditable, sin reescribir preparaciones ni decisiones FID históricas.",
        fill=POSITIVE,
    )
    add_table(
        doc,
        ["Capa", "Estado", "Evidencia"],
        [
            ("Dominio / policy", "PASS", "Merge preserva reglas existentes; revisión publicada e inmutable"),
            ("Providers", "PASS", "Business Case y Economic-Financial AVAILABLE"),
            ("Gate07J / Gate07K", "PASS", "Cobertura, snapshots, hashes y drilldowns separados"),
            ("UI", "PASS", "ADMIN matrix/registry/preview; USER BC y FIN separados"),
            ("Release", "PASS", "Python, PostgreSQL, frontend, browser y localhost"),
        ],
        [2200, 1300, 5860],
        font_size=8.2,
    )
    page_break(doc)


def contents(doc: Document) -> None:
    doc.add_heading("Contenido y criterio de cierre", level=1)
    add_table(
        doc,
        ["Capítulo", "Contenido", "Entregables"],
        [
            ("1", "Baseline, alcance y decisión arquitectónica", "1–16"),
            ("2", "Matriz efectiva y aplicabilidad", "17–35"),
            ("3", "Integración Gate07J/Gate07K e historia", "36–47"),
            ("4", "ADMIN, USER, API y seguridad", "48–61"),
            ("5", "Pruebas, release y salvaguardas", "62–101"),
            ("6", "Matriz integral de trazabilidad", "1–101"),
        ],
        [1100, 5600, 2660],
        font_size=8.2,
    )
    add_callout(
        doc,
        "Criterio de evidencia",
        "El cierre combina inspección del código, pruebas unitarias e integración, migración real en PostgreSQL, "
        "navegación Playwright y publicación controlada local. La revalidación end-to-end de un FID nuevo queda "
        "identificada de forma explícita como NEXT y no se simula como completada.",
        fill=CALLOUT,
    )
    page_break(doc)


def architecture(doc: Document) -> None:
    doc.add_heading("1. Baseline, alcance y arquitectura", level=1)
    paragraph = doc.add_paragraph()
    paragraph.add_run(
        "Gate 07M-EVID se implementó sobre el motor Gate07J-EVID existente. No se creó un segundo motor de "
        "evidencia ni una migración adicional: el esquema actual en 0058 soporta los nuevos tipos, providers, "
        "matrices y revisiones de policy. Business Case, FIN, Budget, Funding y FID conservan ownership separado."
    )
    add_table(
        doc,
        ["Autoridad", "Reutilización", "Límite preservado"],
        [
            ("Gate07J-EVID", "Registry, policy, preview, publish, coverage y history", "Única autoridad de resolución"),
            ("Gate07M-BC", "Revision COMPLETED + READY + current + hash", "No muta por consumo"),
            ("Gate07M-FIN", "Provider existente y readiness por dimensiones", "No recalcula en Gate07J"),
            ("Gate07G / FUND", "Referencias de factibilidad y conciliación", "Sin cambios de autoridad"),
            ("Gate07K", "Package consume snapshots congelados", "Semántica FID sin rediseño"),
            ("Gate07L", "Historia post-FID intacta", "No se inicia macroproceso operativo"),
        ],
        [2200, 4200, 2960],
        font_size=8.1,
    )
    doc.add_heading("1.1 Clasificación A / B / C", level=2)
    add_table(
        doc,
        ["Clase", "Regla", "Comportamiento"],
        [
            ("A", "Evidencia estructurada y provider requerido", "Falla o ausencia bloquea; sin fallback manual"),
            ("B", "Evidencia validada; puede usar provider o referencia permitida", "Bloquea sólo si la regla efectiva lo declara"),
            ("C", "Contextual / informativa", "No obligatoria salvo override publicado"),
        ],
        [1200, 4200, 3960],
        font_size=8.2,
    )
    add_callout(
        doc,
        "Invariante crítica",
        "Una evidencia Clase A nunca baja silenciosamente a Clase B, ni un provider no disponible se sustituye "
        "por un adjunto manual. La policy efectiva y su fecha determinan la exigencia.",
        fill=RISK,
    )


def effective_policy(doc: Document, record: dict[str, object]) -> None:
    doc.add_heading("2. Matriz efectiva publicada", level=1)
    add_table(
        doc,
        ["Perfil / Gobierno", "Business Case", "Economic-Financial", "Cobertura"],
        [
            ("PYP-INV-SELECT · CAPITAL_OWNER", "A · bloqueante · provider", "B · no bloqueante", "100% por Project aplicable"),
            ("PYP-FFA · CAPITAL_OWNER", "A · bloqueante · provider", "A · bloqueante · provider", "100% por Project aplicable"),
            ("CONTRACTOR_DELIVERY", "No forzado por default", "No forzado por default", "Sólo policy explícita"),
            ("DIRECT_INTERNAL", "No forzado por default", "No forzado por default", "Sólo policy explícita"),
        ],
        [2600, 2400, 2500, 1860],
        font_size=8.0,
    )
    doc.add_heading("2.1 Aplicabilidad por Project Type", level=2)
    add_table(
        doc,
        ["Project Type", "Dimensión FIN efectiva en PYP-FFA", "Resultado"],
        [
            ("COMMERCIAL / REVENUE", "FINANCIAL_MODEL_READINESS", "A · bloqueante · 100%"),
            ("PUBLIC / NON_REVENUE", "ECONOMIC_READINESS", "A · bloqueante · 100%"),
            ("MIXED", "ECONOMIC + FINANCIAL", "A · bloqueante · 100%"),
            ("INTERNAL / COMPLIANCE", "No requerida por default", "C · no bloqueante"),
            ("MINING", "FIN según tipo + Permit override", "Permit A estructurado"),
        ],
        [2500, 4000, 2860],
        font_size=8.1,
    )
    doc.add_heading("2.2 Identidad de publicación", level=2)
    add_table(
        doc,
        ["Campo", "Valor"],
        [
            ("policy_id / revision", f"{record['policy_id']} / {record['policy_revision']}"),
            ("policy_hash", str(record["policy_hash"])),
            ("effective_from", str(record["effective_from"])),
            ("business_case_provider", "BUSINESS_CASE_READINESS_PROVIDER · AVAILABLE"),
            ("economic_financial_provider", "ECONOMIC_FINANCIAL_READINESS_PROVIDER · AVAILABLE"),
            ("missing_provider_count", "0"),
        ],
        [2600, 6760],
        font_size=7.9,
    )
    source_note(doc, "Registro reproducible: outputs/technical_reports/gate07m_evid_policy_apply.json.")
    page_break(doc)


def providers(doc: Document) -> None:
    doc.add_heading("3. Providers, vigencia y consistencia BC ↔ FIN", level=1)
    add_table(
        doc,
        ["Contrato", "Business Case", "Economic-Financial"],
        [
            ("Provider key", "BUSINESS_CASE_READINESS_PROVIDER", "ECONOMIC_FINANCIAL_READINESS_PROVIDER"),
            ("Fuente", "BUSINESS_CASE", "ECONOMIC_FINANCIAL_MODEL"),
            ("Estado válido", "COMPLETED + READY + current", "COMPLETED + READY + current"),
            ("Identidad", "revision_id, version, hash", "model/version id, hash, as_of"),
            ("Diagnóstico", "warnings, blockers, material change", "dimensions, warnings, blockers, source refs"),
            ("Cobertura", "Por Project aplicable", "Por Project y dimensiones aplicables"),
        ],
        [2100, 3630, 3630],
        font_size=7.9,
    )
    doc.add_heading("3.1 Consistencia y staleness", level=2)
    paragraph = doc.add_paragraph()
    paragraph.add_run(
        "El adaptador Business Case compara el hash FIN referenciado por la revisión con el hash FIN vigente. "
        "Una divergencia produce BUSINESS_CASE_FIN_REFERENCE_STALE; no se religa, recalcula ni corrige en silencio. "
        "Los cambios materiales y los blockers de fuente también quedan visibles en el resultado del provider."
    )
    add_table(
        doc,
        ["Situación", "Resolución"],
        [
            ("Business Case no current", "Provider INVALID; Clase A bloquea"),
            ("FIN no current", "Provider INVALID/STALE según contrato"),
            ("Hash FIN de BC distinto", "BUSINESS_CASE_FIN_REFERENCE_STALE"),
            ("Provider no disponible", "Missing Provider Analysis; no fallback A→B"),
            ("Material Change", "Revisión/refresh gobernado; histórico congelado"),
            ("Fuente se actualiza", "Preview y apply explícito; nunca auto-upgrade"),
        ],
        [3300, 6060],
        font_size=8.1,
    )
    doc.add_heading("3.2 Coverage", level=2)
    add_callout(
        doc,
        "Denominador gobernado",
        "El denominador contiene únicamente Projects seleccionados y aplicables. Projects faltantes no se "
        "promedian como cero ni desaparecen: se exponen como ausencia y una Clase A exige 100% de cobertura.",
        fill=CALLOUT,
    )


def integration(doc: Document) -> None:
    doc.add_heading("4. Integración Gate07J y Gate07K", level=1)
    add_table(
        doc,
        ["Superficie", "Cambio implementado", "Salvaguarda"],
        [
            ("Gate07J Preview", "Class, blocking, provider, coverage, current/readiness", "persisted=false"),
            ("Preparation snapshot", "Policy id/revision/hash + BC/FIN refs/hashes/status", "Inmutable por preparación"),
            ("Refresh preview", "Compara policy congelada contra efectiva", "No persiste"),
            ("Refresh apply", "Adopta revisión efectiva sólo por acción explícita", "ETag + auditoría"),
            ("Gate07K package", "Handoff incluye BC y FIN separados", "FID existente permanece congelado"),
            ("Decided FID", "Continúa resolviendo sus hashes originales", "No backdate / no relink"),
        ],
        [2200, 4300, 2860],
        font_size=8.0,
    )
    doc.add_heading("4.1 Compatibilidad histórica", level=2)
    paragraph = doc.add_paragraph()
    paragraph.add_run(
        "La fecha efectiva aplica a nuevas resoluciones. Preparaciones existentes no se reevalúan por la sola "
        "publicación; preparaciones congeladas y decisiones FID decididas conservan policy, evidence references "
        "y hashes originales. El nuevo camino FID posterior a effective_from queda habilitado para revalidación."
    )
    add_callout(
        doc,
        "NEXT controlado",
        "Los providers y las matrices están completos, pero aún corresponde ejecutar una validación full-stack "
        "sembrada de un nuevo FID PYP-FFA desde Business Case + FIN hasta Gate07K. Por ello el único NEXT es "
        "READY_TO_REVALIDATE_NEW_FID_PATH.",
        fill=RISK,
    )
    page_break(doc)


def implementation(doc: Document) -> None:
    doc.add_heading("5. ADMIN MODE, USER MODE, API y seguridad", level=1)
    doc.add_heading("5.1 Superficies de usuario", level=2)
    add_table(
        doc,
        ["Modo", "Capacidad"],
        [
            ("ADMIN · Evidence Matrix", "Filas BC/FIN, clase, bloqueo, provider, scope, coverage y manual evidence"),
            ("ADMIN · Provider Registry", "Estado, contrato, fuente, disponibilidad y última validación"),
            ("ADMIN · Project Type Overrides", "Filtro de tipo, gobierno y dimensiones FIN requeridas"),
            ("ADMIN · Preview", "Project type/governance, policy efectiva, source current y readiness"),
            ("USER · Gate07J", "Renglones separados Business Case y Economic/Financial"),
            ("USER · Drilldown", "Clase, cobertura, provider, estado, hash/ref congelado, warnings/blockers"),
        ],
        [2900, 6460],
        font_size=8.0,
    )
    doc.add_heading("5.2 API y controles transaccionales", level=2)
    add_table(
        doc,
        ["Control", "Implementación"],
        [
            ("API", "Preview, registry, release contract, clone/draft/update/publish y Gate preparation refresh"),
            ("ETag", "If-Match protege cambios concurrentes y refresh"),
            ("Idempotencia", "Publicación y operaciones mutantes conservan replay seguro"),
            ("RBAC", "Reutiliza permisos administrativos y de preparación existentes"),
            ("SoD", "Autor de preparación no obtiene autorización de decisión"),
            ("SecurityEvent", "Publish, refresh, lifecycle y decisiones dejan rastro"),
            ("No migration", "Tipos y contratos se expresan en JSON policy existente; head 0058"),
        ],
        [2500, 6860],
        font_size=8.0,
    )
    doc.add_heading("5.3 Archivos principales", level=2)
    add_table(
        doc,
        ["Componente", "Ruta"],
        [
            ("Motor policy", "backend/app/modules/investment_evidence_policy/service.py"),
            ("API policy", "backend/app/modules/investment_evidence_policy/router.py + schemas.py"),
            ("Gate preparation", "backend/app/modules/investment_gate_preparation/service.py + schemas.py"),
            ("Apply controlado", "scripts/apply_gate07m_evid_policy_update.py"),
            ("ADMIN", "frontend/src/features/investment-evidence-policy/"),
            ("USER", "frontend/src/features/investment-gate-preparation/"),
            ("ADR", "docs/62-adr-gate07m-evid-policy-update.md"),
        ],
        [2400, 6960],
        font_size=7.8,
    )


def validation(doc: Document) -> None:
    doc.add_heading("6. Validación técnica y release", level=1)
    add_table(
        doc,
        ["Control", "Resultado", "Evidencia"],
        [
            ("Ruff / format", "PASS", "Backend, tests y script de publicación"),
            ("Policy service", "PASS", "Providers, matriz, preview, merge y release contract"),
            ("Gate07J / Gate07K", "PASS", "Readiness, coverage, snapshots y handoff"),
            ("PostgreSQL efímero", "PASS", "Head 0058, esquema validado y 6 pruebas focales"),
            ("Frontend", "PASS", "TypeScript, Vite, Prettier y unidades focales"),
            ("Browser", "PASS", "E2E USER Gate preparation y ADMIN policy"),
            ("Localhost", "PASS", "API healthy; frontend HTTP 200 en /app"),
            ("Publicación", "PASS", "Policy 787 rev 1; missing providers = 0"),
        ],
        [2400, 1400, 5560],
        font_size=8.0,
    )
    source_note(
        doc,
        "La evidencia de publicación conserva actor, tenant, effective_from, source hash, policy hash y head de "
        "migración en gate07m_evid_policy_apply.json.",
    )
    doc.add_heading("6.1 Casos negativos", level=2)
    add_table(
        doc,
        ["Caso", "Respuesta esperada / verificada"],
        [
            ("Provider BC ausente", "Bloqueo explícito de Clase A; missing provider visible"),
            ("Provider FIN ausente en FFA", "Bloqueo de Clase A; no adjunto sustituto"),
            ("FIN ausente en Selection", "Clase B no bloqueante, sin fabricar readiness"),
            ("BC↔FIN stale", "BUSINESS_CASE_FIN_REFERENCE_STALE"),
            ("Cobertura incompleta", "Missing Projects visibles; Class A coverage < 100 bloquea"),
            ("Preview", "persisted=false y sin cambios de estado"),
            ("ETag stale", "Rechazo de concurrencia"),
            ("Policy futura", "No se aplica antes de effective_from"),
        ],
        [3300, 6060],
        font_size=8.0,
    )
    page_break(doc)


def closeout(doc: Document) -> None:
    doc.add_heading("7. Gap Analysis y cierre", level=1)
    add_table(
        doc,
        ["Gap / riesgo residual", "Impacto", "Tratamiento"],
        [
            ("Nuevo FID full-stack", "Camino posterior a effective_from no recorrido completo", "NEXT dedicado con seed BC+FIN+Gate07J+Gate07K"),
            ("Benchmark 1.000 Projects", "Cobertura algorítmica probada; p95 no contractual", "Perf fixture y presupuesto explícito futuro"),
            ("Datos históricos heterogéneos", "Puede faltar dimensión/tipo en registros antiguos", "Resolver con policy congelada y no backfill destructivo"),
            ("Providers temporalmente unavailable", "Bloqueo A correcto puede detener el gate", "Observabilidad y recuperación del provider; nunca fallback"),
            ("Reglas por jurisdicción", "Overrides actuales son baseline tenant", "Nueva revisión efectiva, nunca edición retroactiva"),
        ],
        [3000, 3200, 3160],
        font_size=7.9,
    )
    add_callout(
        doc,
        "STOP boundary respetada",
        "No se inició Procurement, Contracting, Commitments, Purchase Orders, Payments, Accounting, Treasury, "
        "Notice to Proceed, Project Execution, P6 execution, fórmulas FIN nuevas ni trabajo adicional de dominio BC.",
        fill=RISK,
    )
    add_callout(
        doc,
        "Cierre exclusivo",
        "GATE07M_EVID_POLICY_UPDATE_VALIDATED · final_output = "
        "READY_FOR_BUSINESS_CASE_AND_ECONOMIC_FINANCIAL_GATE_EVIDENCE · "
        "NEXT = READY_TO_REVALIDATE_NEW_FID_PATH · STOP.",
        fill=POSITIVE,
    )
    page_break(doc)


def deliverables() -> list[str]:
    text = PROMPT.read_text(encoding="utf-8")
    section = text.split("# 78. Required deliverables", 1)[1].split("# 79.", 1)[0]
    items: dict[int, str] = {}
    for line in section.splitlines():
        match = re.match(r"^(\d+)\.\s+(.+)$", line.strip())
        if match:
            items[int(match.group(1))] = match.group(2).rstrip(".")
    if sorted(items) != list(range(1, 102)):
        raise RuntimeError("The Gate 07M-EVID prompt does not contain the expected 101 deliverables")
    return [items[index] for index in range(1, 102)]


def traceability(doc: Document) -> None:
    doc.add_heading("8. Matriz integral de trazabilidad 1–101", level=1)

    def evidence(index: int) -> str:
        if index <= 16:
            return "§1 / ADR 62"
        if index <= 35:
            return "§2–3 / policy+providers"
        if index <= 47:
            return "§4 / snapshots+history"
        if index <= 61:
            return "§5 / API+UI+security"
        if index <= 87:
            return "§6 / tests+E2E"
        return "§7 / release+report"

    def status(index: int) -> str:
        return "NEXT CONTROLADO" if index == 75 else "CUBIERTO"

    rows = [
        (str(index), item, evidence(index), status(index))
        for index, item in enumerate(deliverables(), 1)
    ]
    add_table(
        doc,
        ["#", "Entregable", "Evidencia", "Estado"],
        rows,
        [560, 5150, 1850, 1800],
        font_size=7.4,
    )


def build() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    record = apply_record()
    doc = Document()
    section = doc.sections[0]
    section.page_width = Inches(8.5)
    section.page_height = Inches(11)
    section.top_margin = Inches(1)
    section.right_margin = Inches(1)
    section.bottom_margin = Inches(1)
    section.left_margin = Inches(1)
    section.header_distance = Inches(0.492)
    section.footer_distance = Inches(0.492)
    configure_styles(doc)
    title_page(doc, record)
    contents(doc)
    architecture(doc)
    effective_policy(doc, record)
    providers(doc)
    integration(doc)
    implementation(doc)
    validation(doc)
    closeout(doc)
    traceability(doc)
    properties = doc.core_properties
    properties.title = "Informe Técnico Gate 07M-EVID — BC & Economic-Financial Gate Evidence"
    properties.subject = "Gate07J-EVID policy, providers, coverage, historical compatibility and Gate07K handoff"
    properties.author = "P&Pmis Construction AI"
    properties.keywords = "Gate 07M-EVID, Business Case, FIN, Gate07J, Gate07K, policy, readiness"
    properties.comments = "Generated from verified repository, PostgreSQL, browser and controlled publish evidence on 2026-09-03."
    doc.save(OUTPUT)
    print(OUTPUT)


if __name__ == "__main__":
    build()
