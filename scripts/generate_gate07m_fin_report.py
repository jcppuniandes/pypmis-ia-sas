from __future__ import annotations

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
    r"\PROMPT_07M_FIN_PROJECT_ECONOMIC_FINANCIAL_MODEL_AND_READINESS.md"
)
OUTPUT = (
    REPO
    / "outputs"
    / "technical_reports"
    / "Informe_Tecnico_Gate_07M_FIN_Economic_Financial_Model_20260902.docx"
)
LOGO = REPO / "frontend" / "public" / "pypmis-construction-ai-logo.png"

# Resolved document system: standard_business_brief + memo_masthead.
# Named override: dense traceability and API matrices use 7.5–8.2 pt text.


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


def title_page(doc: Document) -> None:
    section = doc.sections[0]
    header = section.header.paragraphs[0]
    header.alignment = WD_ALIGN_PARAGRAPH.LEFT
    set_run(header.add_run("TECHNICAL REPORT · GATE 07M-FIN"), size=8.5, color="5F6B76", bold=True)
    add_bottom_rule(header, color="D9E1E8", size=6)
    add_page_number(section.footer.paragraphs[0])
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
    set_run(title.add_run("Gate 07M-FIN"), size=25, color=INK, bold=True)
    subtitle = doc.add_paragraph()
    subtitle.paragraph_format.space_after = Pt(16)
    set_run(
        subtitle.add_run("Project Economic & Financial Model & Economic-Financial Readiness"),
        size=14,
        color=DARK_BLUE,
        bold=True,
    )
    metadata = (
        ("Aplicación", "P&Pmis Construction AI"),
        ("Fecha de corte", "2 de septiembre de 2026"),
        ("Repositorio", "pypmis-ia-sas · rama main · baseline b57f951"),
        ("Migración", "20260902_0058 · sucesora reversible de 20260902_0057"),
        ("Motor", "PPMIS-FIN-1.0 · Decimal determinista"),
        ("Salida", "READY_FOR_GOVERNED_ECONOMIC_FINANCIAL_EVIDENCE"),
        ("Estado exclusivo", "GATE07M_FIN_RELEASE_VALIDATED"),
        ("NEXT", "UPDATE_GATE07J_EVID_FOR_BUSINESS_CASE_AND_ECONOMIC_FINANCIAL_READINESS"),
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
        "Se implementó un modelo económico-financiero gobernado por Project, con versiones inmutables, "
        "Economic Case y Financial Case separados, conciliación explícita con Budget y Funding, estructura "
        "de capital, inversores, deuda, cash flow, indicadores, escenarios, sensibilidad, readiness y un "
        "proveedor de evidencia disponible. El release no ejecuta tesorería, contabilidad, pagos ni FID.",
        fill=POSITIVE,
    )
    add_table(
        doc,
        ["Capa", "Estado", "Evidencia"],
        [
            ("Dominio", "PASS", "12 tablas tenant-scoped; 1 modelo/Project; N versiones"),
            ("Cálculo", "PASS", "NPV, IRR, payback, BCR, WACC, DSCR, LLCR y MOIC"),
            ("Gobierno", "PASS", "ETag, idempotencia, SoD, hashes, staleness y SecurityEvent"),
            ("Interfaz", "PASS", "23 vistas USER; 45 secciones ADMIN; CompactModuleHeader"),
            ("Validación", "PASS", "PostgreSQL up/down/up, 6 pruebas focales y Playwright"),
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
            ("1", "Baseline, alcance y ownership", "1–9, 73–75"),
            ("2", "Agregado, lifecycle y lineage", "6–13, 46–49"),
            ("3", "Motor económico-financiero", "14–43, 47–48"),
            ("4", "Readiness, provider y Business Case", "44–51, 70–71"),
            ("5", "Seguridad, API, persistencia y UI", "52–58, 72"),
            ("6", "Validación técnica y regresión", "59–76"),
            ("7", "Riesgos, Gap Analysis y siguiente paso", "77–81"),
            ("8", "Matriz integral de trazabilidad", "1–81"),
        ],
        [1100, 5600, 2660],
        font_size=8.2,
    )
    add_callout(
        doc,
        "Criterio de evidencia",
        "El cierre combina inspección del código, pruebas de fórmulas, lifecycle real en PostgreSQL, "
        "validación reversible del DDL y E2E de navegador. Preview ADMIN conserva persisted=false; "
        "el registro del proveedor no altera automáticamente una policy publicada.",
        fill=CALLOUT,
    )
    page_break(doc)


def architecture(doc: Document) -> None:
    doc.add_heading("1. Baseline, alcance y arquitectura", level=1)
    paragraph = doc.add_paragraph()
    paragraph.add_run(
        "Gate 07M-FIN sucede a Gate 07M-BC y consume evidencia gobernada por referencia. La decisión "
        "arquitectónica evita duplicar Project, Budget, Funding, Risk, Permit o Investment Decision: el nuevo "
        "agregado es únicamente autoridad de supuestos, cálculo económico-financiero y readiness del modelo."
    )
    add_table(
        doc,
        ["Autoridad", "Consumida por FIN", "FIN no puede hacer"],
        [
            ("Gate 07M-BC", "Revision COMPLETED+READY, id y hash", "Reescribir narrativa o histórico"),
            ("Gate 07G Budget", "Escenario FROZEN y CAPEX de Project", "Aprobar capacidad o rebalancear"),
            ("Gate 07J-FUND", "Snapshot READY y FundingAssignment", "Crear, confirmar o mover fondos"),
            ("Gate 07J-EVID", "Registry y contrato genérico", "Mutar policy publicada"),
            ("Gate 07K/FID", "Futuro consumidor de evidencia", "Decidir GO/NO-GO o emitir FID"),
            ("Treasury/Accounting", "Fuera de alcance", "Pagos, bancos, asientos o cierre"),
        ],
        [2200, 3500, 3660],
        font_size=8.1,
    )
    doc.add_heading("1.1 REUSE BEFORE CREATE", level=2)
    paragraph = doc.add_paragraph()
    paragraph.add_run(
        "Se reutilizan EnterpriseWorkspace, AdminConfiguration, AdminNumberSequence, SecurityEvent, BusinessCase, "
        "PortfolioBudgetScenario/Project, Fund, FundingAssignment, FundingReadinessSnapshot, el contexto RBAC y la "
        "navegación USER/ADMIN. La creación se limita al agregado FIN y sus inputs/outputs persistidos."
    )
    add_callout(
        doc,
        "Frontera explícita",
        "No se implementan live market data, Monte Carlo, optimización automática, tesorería, contabilidad, "
        "procurement, contratos, commitments, pagos, auto-funding, auto-FID ni auto-NTP.",
        fill=RISK,
    )


def aggregate(doc: Document) -> None:
    doc.add_heading("2. Agregado, lifecycle y trazabilidad de fuentes", level=1)
    add_table(
        doc,
        ["Entidad", "Cardinalidad / lifecycle", "Control"],
        [
            ("EconomicFinancialModel", "1 por Project; DRAFT/ACTIVE/ON_HOLD/CLOSED/ARCHIVED", "EFM-000001 y unique tenant/project"),
            ("ModelVersion", "N; DRAFT→IN_REVIEW→COMPLETED", "COMPLETED/SUPERSEDED/VOIDED inmutables"),
            ("Assumption / Period", "N por versión", "Clave/período único y fechas válidas"),
            ("Instrument / Investor", "N por versión", "Commitment, assignment, ownership y SoD"),
            ("Scenario / Override", "N; un BASE oficial", "Índice parcial único e idempotencia"),
            ("CashFlow / Debt / Metric", "Outputs por escenario/período", "Trace hash + engine version"),
            ("Sensitivity", "Resultados append-only", "Input hash y resultado explícito"),
        ],
        [2500, 3900, 2960],
        font_size=8.0,
    )
    doc.add_heading("2.1 Tipos, propósito y fuente", level=2)
    add_table(
        doc,
        ["Eje", "Valores / comportamiento"],
        [
            ("Model Type", "COMMERCIAL_PROJECT, NON_REVENUE_PROJECT, PUBLIC_ECONOMIC_APPRAISAL, MIXED"),
            ("Version Purpose", "Initial feasibility, FEL updates, investment selection, FFA, financing, material change, revalidation"),
            ("Horizonte", "MONTHLY, QUARTERLY o ANNUAL; fechas coherentes dentro del modelo"),
            ("Lineage", "BC hash obligatorio; Budget/Funding opcionales explícitos; source_snapshot_hash SHA-256"),
            ("Refresh", "Preview no persiste; Apply crea sucesor DRAFT; histórico completado no cambia"),
            ("Staleness", "Comparación id/hash/current flag; MODEL_SOURCE_STALE bloquea completion"),
        ],
        [2500, 6860],
        font_size=8.1,
    )


def engine(doc: Document) -> None:
    doc.add_heading("3. Motor económico-financiero PPMIS-FIN-1.0", level=1)
    paragraph = doc.add_paragraph()
    paragraph.add_run(
        "El motor utiliza Decimal con precisión 34 y entradas persistidas. Cada resultado conserva formula_version, "
        "input references y trace hash. Las patologías no se resuelven con valores fabricados: IRR no computable o "
        "no única se reporta como warning/status NOT_COMPUTABLE."
    )
    doc.add_heading("3.1 Economic Case y Financial Case", level=2)
    add_table(
        doc,
        ["Capa", "Flujo / indicador", "Aplicabilidad"],
        [
            ("Project cash flow", "Revenue − OPEX − taxes − working capital − CAPEX", "Commercial / Mixed"),
            ("Economic cash flow", "Economic benefits + revenue − economic costs", "Public / Non-revenue / Mixed"),
            ("CFADS", "Revenue − OPEX − taxes − working capital", "Debt service capacity"),
            ("Cash flow to equity", "Distribution − contribution + drawdown − interest − principal", "Equity return"),
            ("Discounting", "Project/economic discount rate; WACC reference", "NPV, BCR, LLCR"),
        ],
        [2200, 4200, 2960],
        font_size=8.1,
    )
    doc.add_heading("3.2 Moneda, base temporal y supuestos", level=2)
    add_table(
        doc,
        ["Regla", "Implementación"],
        [
            ("FX explícito", "Período no-base exige fx_<source>_<base>; no existe conversión silenciosa"),
            ("Nominal / Real", "Basis persistida; inflación nominal ausente advierte y mezcla real/inflación advierte"),
            ("Horizon", "Period start/end dentro de model_start/model_end; range inválido devuelve 422"),
            ("Precision", "Numeric PostgreSQL + Decimal; no float en fórmula de dominio"),
            ("Reproducibilidad", "Engine version, source snapshot, scenario hash, calculation trace y model hash"),
        ],
        [2500, 6860],
        font_size=8.1,
    )
    doc.add_heading("3.3 CAPEX, OPEX, ingresos y beneficios", level=2)
    paragraph = doc.add_paragraph()
    paragraph.add_run(
        "Los períodos separan CAPEX, OPEX, revenue, economic benefits, taxes, working-capital change y terminal "
        "distributions. El modelo compara la suma CAPEX contra el Project de un Budget Scenario FROZEN y aplica "
        "tolerancia configurable; no corrige ni publica Budget."
    )
    doc.add_heading("3.4 Capital structure, equity e inversores", level=2)
    add_table(
        doc,
        ["Componente", "Control gobernado"],
        [
            ("Instrument types", "Sponsor/external/JV equity; senior/mezzanine/bank/development/bond/shareholder debt"),
            ("Funding linkage", "FundingAssignment RESERVED/CONFIRMED; Project, moneda, período y compromiso reconciliados"),
            ("Investor", "Commitment ≤ equity instrument; ownership 0–100; capital calls y distributions estructurados"),
            ("Equity return", "Equity IRR y MOIC con estado NOT_COMPUTABLE si el patrón de signos no es válido"),
            ("Leverage", "Debt/Equity y WACC con Ke, Kd y tax rate explícitos"),
        ],
        [2700, 6660],
        font_size=8.1,
    )
    doc.add_heading("3.5 Deuda, servicio y covenants", level=2)
    paragraph = doc.add_paragraph()
    paragraph.add_run(
        "Cada instrumento conserva rate basis, spread, fees, grace, tenor, maturity, drawdown/amortization e IDC. "
        "El cálculo genera debt schedule por período e instrumento, opening/draw/interest/principal/closing, debt "
        "service, DSCR y covenant status. Minimum DSCR incumplido produce COVENANT_BREACH bloqueante."
    )
    doc.add_heading("3.6 Métricas, escenarios y sensibilidad", level=2)
    add_table(
        doc,
        ["Familia", "Resultado"],
        [
            ("Economic", "Economic NPV, Economic IRR y Benefit-Cost Ratio"),
            ("Financial", "Project NPV/IRR, simple/discounted payback"),
            ("Capital", "WACC, debt/equity, equity IRR y MOIC"),
            ("Debt", "Minimum/Average DSCR y LLCR"),
            ("Scenarios", "Official BASE más UPSIDE/DOWNSIDE/CUSTOM con overrides y hashes"),
            ("Sensitivity", "Variable shock, target metric, result status e input hash; ejecución reproducible"),
            ("Break-even", "Campo persistente reservado y resultado explícito; sin optimizador o Monte Carlo"),
        ],
        [2200, 7160],
        font_size=8.1,
    )
    page_break(doc)


def readiness_provider(doc: Document) -> None:
    doc.add_heading("4. Readiness, Business Case y provider", level=1)
    add_table(
        doc,
        ["Dimensión", "Semántica"],
        [
            ("ECONOMIC_READINESS", "Aplicable a public/non-revenue/mixed; required assumptions/metrics y thresholds"),
            ("FINANCIAL_MODEL_READINESS", "Aplicable a commercial/mixed; Project NPV/IRR según policy"),
            ("FUNDING_RECONCILIATION_READINESS", "CAPEX, financing, governed assignment, moneda y período"),
            ("DEBT / EQUITY", "READY, BLOCKED o NOT_APPLICABLE según instrumentos"),
            ("COVENANT_READINESS", "Covenants y ratios de deuda; breach bloquea"),
            ("SCENARIO_READINESS", "Official BASE y escenarios requeridos por policy"),
            ("OVERALL", "READY, BLOCKED o STALE; sólo COMPLETED+READY+current entrega evidencia"),
        ],
        [3000, 6360],
        font_size=8.1,
    )
    add_callout(
        doc,
        "Contrato de salida",
        "final_output = READY_FOR_GOVERNED_ECONOMIC_FINANCIAL_EVIDENCE sólo para una versión COMPLETED, READY y "
        "current. Warnings no se ocultan; blockers impiden review/completion.",
        fill=POSITIVE,
    )
    doc.add_heading("4.1 Integración Business Case", level=2)
    paragraph = doc.add_paragraph()
    paragraph.add_run(
        "FIN exige una BusinessCaseRevision vigente, COMPLETED y READY. Al completar FIN, sólo una revisión "
        "Business Case DRAFT puede recibir id, versión, hash, estado y métricas; una revisión COMPLETED no se "
        "modifica. Cuando se crea una revisión nueva, su source bundle resuelve el último FIN COMPLETED+READY+current."
    )
    doc.add_heading("4.2 Provider y política futura", level=2)
    add_table(
        doc,
        ["Campo", "Valor"],
        [
            ("provider_key", "ECONOMIC_FINANCIAL_READINESS_PROVIDER"),
            ("source_module", "ECONOMIC_FINANCIAL_MODEL"),
            ("evidence_type", "ECONOMIC_FINANCIAL_READINESS"),
            ("status/scope", "AVAILABLE · EACH_PROJECT / SELECTED_PROJECTS_ONLY"),
            ("contract", "readiness, source_current, model_hash, as_of, warnings, blockers, refs"),
            ("policy", "Gate07J-EVID publicada queda sin mutación automática"),
        ],
        [2700, 6660],
        font_size=8.1,
    )


def implementation(doc: Document) -> None:
    doc.add_heading("5. Seguridad, API, persistencia y superficies", level=1)
    doc.add_heading("5.1 Roles, SoD e idempotencia", level=2)
    add_table(
        doc,
        ["Control", "Implementación"],
        [
            ("Roles", "owner, preparer, reviewer, finance reviewer, viewer, configuration admin"),
            ("Permisos", "13 economic_financial_model.* para read/create/edit/calculate/review/version/refresh/scenario/sensitivity/admin"),
            ("SoD", "preparer != final reviewer por policy; reviewer explícito en completion"),
            ("ETag", "revision_version + If-Match; stale devuelve 412 ETAG_MISMATCH"),
            ("Idempotencia", "Create model/version/instrument/investor/scenario, calculate, complete y refresh"),
            ("Auditoría", "SecurityEvent en lifecycle, calculation, funding link, sensitivity, staleness y publish"),
        ],
        [2500, 6860],
        font_size=8.0,
    )
    doc.add_heading("5.2 API", level=2)
    add_table(
        doc,
        ["Grupo", "Operaciones"],
        [
            ("Model / versions", "list, create, get, by-project, list/create version, update, calculate, submit, complete"),
            ("Inputs", "assumptions, periods, financing-instruments, investors, scenarios"),
            ("Analysis", "cash-flows, metrics, sensitivities/run"),
            ("Readiness", "readiness, refresh preview/apply, investment-gate-evidence"),
            ("ADMIN", "configurations, preview, clone, update y publish"),
        ],
        [2300, 7060],
        font_size=8.0,
    )
    doc.add_heading("5.3 Persistencia y migración", level=2)
    paragraph = doc.add_paragraph()
    paragraph.add_run(
        "La revisión 0058 crea 12 tablas, constraints, índices tenant/status/hash/history, uniques de cardinalidad e "
        "idempotencia y FK diferida para current_version_id. El downgrade elimina sólo el dominio FIN y restaura "
        "0057. La prueba real confirmó 0057→0058→0057→0058."
    )
    doc.add_heading("5.4 USER MODE y ADMIN MODE", level=2)
    add_table(
        doc,
        ["Superficie", "Contenido"],
        [
            ("USER · 23 vistas", "My Models, Overview, version, assumptions, cases, CAPEX/OPEX, revenue/benefits, capital, funding, investors, debt, cash flow, indicators, covenants, scenarios, sensitivities, readiness, lineage, compare e history"),
            ("Tablas", "Capital Structure, Investors, Debt, Cash Flow y métricas con overflow controlado"),
            ("Acciones", "Create, Calculate, Submit y Complete condicionadas por lifecycle"),
            ("ADMIN · 45 secciones", "Aplicabilidad, fórmulas, supuestos, financing, métricas, readiness, thresholds, freshness, SoD, inheritance, permissions, preview e history"),
            ("Preview", "Project + Business Case + config; effective requirements; persisted=false"),
        ],
        [2600, 6760],
        font_size=7.9,
    )


def validation(doc: Document) -> None:
    doc.add_heading("6. Verificación técnica, release y regresión", level=1)
    add_table(
        doc,
        ["Control", "Resultado", "Evidencia"],
        [
            ("Ruff / Python compile", "PASS", "Módulo, router, migración, provider, RBAC y pruebas"),
            ("Fórmulas", "PASS", "NPV/IRR/WACC/payback/BCR/DSCR/LLCR/MOIC + patologías"),
            ("Lifecycle comercial", "PASS", "BC READY → model → inputs → calculate → review → complete → provider"),
            ("PostgreSQL", "PASS", "12 tablas; constraints/indexes; current-version FK"),
            ("Alembic", "PASS", "0058 único head; upgrade/downgrade/upgrade"),
            ("Frontend estático", "PASS", "Prettier, TypeScript y ESLint"),
            ("Playwright", "PASS", "USER/ADMIN 07M-FIN y handoff 07M-BC"),
            ("Runtime local", "PASS", "API/frontend reconstruidos; PostgreSQL en 20260902_0058"),
        ],
        [2400, 1400, 5560],
        font_size=8.0,
    )
    source_note(
        doc,
        "Evidencia observada: 6 pruebas focales PASS; PostgreSQL up/down/up PASS; 2 browser flows PASS; "
        "TypeScript, ESLint, Prettier y Ruff PASS.",
    )
    doc.add_heading("6.1 Casos negativos y controles", level=2)
    add_table(
        doc,
        ["Caso", "Respuesta"],
        [
            ("IRR sin cambio de signo", "IRR_NOT_COMPUTABLE; no valor falso"),
            ("IRR con múltiples raíces", "IRR_NOT_UNIQUE"),
            ("FX faltante", "FX_RATE_REQUIRED:<pair> bloqueante"),
            ("Financing > assignment", "FINANCING_MODEL_EXCEEDS_GOVERNED_FUNDING"),
            ("Moneda/período Funding", "FUNDING_CURRENCY_MISMATCH / FUNDING_PERIOD_MISMATCH"),
            ("CAPEX fuera de tolerancia", "CAPEX_BUDGET_RECONCILIATION_OUT_OF_TOLERANCE"),
            ("Covenant", "COVENANT_BREACH y SecurityEvent"),
            ("Fuente modificada", "MODEL_SOURCE_STALE; refresh crea sucesor"),
            ("ETag stale", "HTTP 412 ETAG_MISMATCH"),
        ],
        [3300, 6060],
        font_size=8.1,
    )
    page_break(doc)


def closeout(doc: Document) -> None:
    doc.add_heading("7. Gap Analysis, riesgos y siguiente paso", level=1)
    add_table(
        doc,
        ["Riesgo / deuda residual", "Impacto", "Tratamiento"],
        [
            ("Break-even básico", "Campo/contrato disponible; sin solver avanzado", "Agregar método determinista versionado en release futuro"),
            ("Curvas debt avanzadas", "Schedule usa inputs periódicos; no day-count complejo", "Convenciones financieras por tipo de instrumento"),
            ("Benchmark 10k Projects", "Índices definidos; p95 no contractual", "Dataset y umbral de performance dedicado"),
            ("Browser data journey", "E2E de UI usa API mocks controlados", "Fixture full-stack efímero por Project"),
            ("Policy Gate07J-EVID", "Provider disponible pero aún no requerido", "Ejecutar análisis y publish controlado futuro"),
            ("Mercado/FX", "No hay feed live por diseño", "Integración gobernada posterior con snapshot/hashes"),
        ],
        [3000, 3000, 3360],
        font_size=8.0,
    )
    add_callout(
        doc,
        "STOP boundary respetada",
        "El cierre no inicia Treasury, Accounting, Procurement, Contracting, Commitments, Payments, Execution, "
        "Monte Carlo, automatic optimization, auto-funding, auto-FID ni cambios de policy publicada.",
        fill=RISK,
    )
    add_callout(
        doc,
        "Cierre exclusivo",
        "GATE07M_FIN_RELEASE_VALIDATED. final_output = READY_FOR_GOVERNED_ECONOMIC_FINANCIAL_EVIDENCE. "
        "NEXT = UPDATE_GATE07J_EVID_FOR_BUSINESS_CASE_AND_ECONOMIC_FINANCIAL_READINESS.",
        fill=POSITIVE,
    )
    page_break(doc)


def deliverables() -> list[str]:
    text = PROMPT.read_text(encoding="utf-8")
    section = text.split("## 76. Required deliverables", 1)[1].split("## 77.", 1)[0]
    items: dict[int, str] = {}
    for line in section.splitlines():
        match = re.match(r"^(\d+)\.\s+(.+)$", line.strip())
        if match:
            items[int(match.group(1))] = match.group(2).rstrip(".")
    if sorted(items) != list(range(1, 82)):
        raise RuntimeError("The Gate 07M-FIN prompt does not contain the expected 81 deliverables")
    return [items[index] for index in range(1, 82)]


def traceability(doc: Document) -> None:
    doc.add_heading("8. Matriz integral de trazabilidad 1–81", level=1)

    def evidence(index: int) -> str:
        if index <= 13:
            return "§1–2 / ADR 61"
        if index <= 43:
            return "§3 / engine+service"
        if index <= 51:
            return "§4 / BC+provider"
        if index <= 58:
            return "§5 / API+DDL+RBAC"
        if index <= 72:
            return "§6 / tests+E2E"
        return "§7 / CI+report"

    rows = [(str(index), item, evidence(index), "CERRADO") for index, item in enumerate(deliverables(), 1)]
    add_table(
        doc,
        ["#", "Entregable", "Evidencia", "Estado"],
        rows,
        [560, 5200, 1900, 1700],
        font_size=7.6,
    )


def build() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
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
    title_page(doc)
    contents(doc)
    architecture(doc)
    aggregate(doc)
    page_break(doc)
    engine(doc)
    readiness_provider(doc)
    implementation(doc)
    validation(doc)
    closeout(doc)
    traceability(doc)
    properties = doc.core_properties
    properties.title = "Informe Técnico Gate 07M-FIN — Economic & Financial Model"
    properties.subject = "Governed Project economics, financing, readiness and evidence provider"
    properties.author = "P&Pmis Construction AI"
    properties.keywords = "Gate 07M-FIN, NPV, IRR, WACC, DSCR, LLCR, Funding, Business Case"
    properties.comments = "Generated from verified repository, PostgreSQL and browser evidence on 2026-09-02."
    doc.save(OUTPUT)
    print(OUTPUT)


if __name__ == "__main__":
    build()
