from __future__ import annotations

from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Inches, Pt

from generate_gate07i_report import (
    CALLOUT,
    CAUTION,
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
OUTPUT = (
    REPO
    / "outputs"
    / "technical_reports"
    / "Informe_Tecnico_Gate_07J_RISK_Risk_Readiness_Provider_20260831.docx"
)
LOGO = REPO / "frontend" / "public" / "pypmis-construction-ai-logo.png"

# Resolved design tokens:
# preset=standard_business_brief; first-page pattern=memo_masthead.
# Letter portrait; 1 in margins; 0.492 in header/footer; 9360 DXA tables;
# 120 DXA table indent; Calibri 11 pt; body 6 pt after / 1.10 line.
# Named override: dense traceability/status matrices use 7.4-8.4 pt.


def add_title_page(doc: Document) -> None:
    section = doc.sections[0]
    # Word may preserve an even/odd header setting from its default template.
    # Define both stories explicitly so the running masthead and footer are
    # deterministic in native Word, LibreOffice, and PDF renderers.
    doc.settings.odd_and_even_pages_header_footer = True
    for header in (section.header.paragraphs[0], section.even_page_header.paragraphs[0]):
        header.alignment = WD_ALIGN_PARAGRAPH.LEFT
        set_run(
            header.add_run("TECHNICAL REPORT · GATE 07J-RISK"),
            size=8.5,
            color="5F6B76",
            bold=True,
        )
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
    title.paragraph_format.keep_with_next = True
    set_run(title.add_run("Gate 07J-RISK"), size=25, color=INK, bold=True)
    subtitle = doc.add_paragraph()
    subtitle.paragraph_format.space_after = Pt(16)
    set_run(
        subtitle.add_run("Risk Readiness Governed Provider"),
        size=15,
        color=DARK_BLUE,
        bold=True,
    )
    for label, value in (
        ("Aplicación", "P&Pmis Construction AI"),
        ("Fecha de corte", "31 de agosto de 2026"),
        ("Repositorio", "pypmis-ia-sas · branch main · base fde6027"),
        ("Migración", "20260830_0053"),
        ("Salida funcional", "READY_FOR_GOVERNED_RISK_EVIDENCE"),
        ("Estado exclusivo", "GATE07J_RISK_RELEASE_VALIDATED"),
    ):
        paragraph = doc.add_paragraph()
        paragraph.paragraph_format.space_after = Pt(2)
        set_run(paragraph.add_run(f"{label}: "), size=10.5, color=INK, bold=True)
        set_run(paragraph.add_run(value), size=10.5)
    rule = doc.add_paragraph()
    rule.paragraph_format.space_before = Pt(10)
    rule.paragraph_format.space_after = Pt(14)
    add_bottom_rule(rule)
    add_callout(
        doc,
        "Resultado ejecutivo",
        "Se implementó el proveedor gobernado RISK_READINESS_PROVIDER sobre un único registro ProjectRisk y "
        "evaluaciones versionadas e inmutables. PYP-FFA conserva Class A, bloqueo, 100% de cobertura, 90 días y "
        "cero fallback manual; PYP-INV-SELECT conserva Class B no bloqueante. La entrega no crea ERM, QRA, Permit "
        "Readiness, Investment Decision ni FID.",
        fill=POSITIVE,
    )
    add_table(
        doc,
        ["Capa", "Resultado", "Evidencia verificable"],
        [
            ("Dominio / API", "PASS", "ProjectRisk, assessments, readiness Project/Set, 19 rutas OpenAPI"),
            ("Gate 07J-EVID", "PASS", "Provider AVAILABLE; GOVERNED_SOURCE; no fallback Class A"),
            ("PostgreSQL", "PASS", "69/69 + 74/74; upgrade/downgrade/upgrade 0053"),
            ("Frontend", "PASS", "8 USER views; 16 ADMIN tabs; filters y matrices completas"),
            ("Browser", "PASS", "Chromium USER/ADMIN; 0 uncaught; no controles FID"),
            ("Localhost", "ACTIVE", "Frontend 5173; API 8000 ready; Alembic 0053"),
        ],
        [1900, 1300, 6160],
        font_size=8.6,
    )
    doc.add_page_break()


def add_contents(doc: Document) -> None:
    heading = doc.add_heading("Contenido y trazabilidad", level=1)
    heading.paragraph_format.space_before = Pt(0)
    add_table(
        doc,
        ["Capítulo", "Tema", "Entregables"],
        [
            ("1", "Baseline, alcance y decisiones de reutilización", "1-6"),
            ("2", "Dominio Project Risk y lifecycle", "7-16"),
            ("3", "Política y cálculo de Risk Readiness", "17-28"),
            ("4", "Proveedor Gate 07J y perfiles", "29-35"),
            ("5", "ADMIN, USER, seguridad y APIs", "36-46"),
            ("6", "Pruebas, regresión y baseline persistente", "47-64"),
            ("7", "Riesgos, gap analysis y cierre", "65-69"),
        ],
        [1050, 5600, 2710],
        font_size=9.0,
    )
    add_callout(
        doc,
        "Cómo leer este informe",
        "El capítulo 8 contiene una matriz final de los 69 entregables del PROMPT 07J-RISK. Los resultados de "
        "pruebas corresponden a comandos ejecutados en esta entrega y el baseline local se midió antes y después.",
        fill=CALLOUT,
    )
    doc.add_page_break()


def add_baseline_reuse(doc: Document) -> None:
    doc.add_heading("1. Baseline, alcance y REUSE BEFORE CREATE", level=1)
    add_table(
        doc,
        ["Baseline", "Estado de entrada", "Decisión"],
        [
            ("Alembic", "20260830_0052", "Sucesora aditiva y reversible 0053"),
            ("Gate 07J-EVID", "Risk provider RESERVED / UNAVAILABLE", "Registrar provider real y conservar policy"),
            ("PYP-INV-SELECT", "Risk B · no block · 90 d", "Sin cambio"),
            ("PYP-FFA", "Risk A · block · 100% · 90 d", "Sin cambio; no manual fallback"),
            ("Gate 07J", "READY_FOR_INVESTMENT_DECISION", "Sólo consumir evidencia; can_enter_fid=false"),
        ],
        [2000, 3200, 4160],
        font_size=8.6,
    )
    doc.add_heading("1.1 Inventario reutilizado", level=2)
    add_table(
        doc,
        ["Capacidad existente", "Uso en 07J-RISK"],
        [
            ("EnterpriseWorkspace(PROJECT)", "Identidad canónica; no se creó un Project master paralelo"),
            ("Gate 07I", "Recommended Project Set y hash para agregación"),
            ("Gate 07F / 07E", "Métricas de riesgo como referencias read-only"),
            ("Gate 07J-FEL", "Dependencia de freshness configurable; no duplica madurez FEL"),
            ("Gate 07G / 07J-FUND", "Riesgos pueden referenciarlos; no recalculan Budget/Funding"),
            ("AdminConfiguration", "DRAFT/PUBLISHED/SUPERSEDED, herencia, hash, preview y publish"),
            ("RBAC / SecurityEvent", "Permisos, roles, SoD y auditoría existentes"),
            ("ETag / idempotency", "revision_version, If-Match y claves transaccionales"),
            ("Gate07J provider contracts", "InvestmentGateRiskEvidenceOut integrado al resolver"),
        ],
        [3000, 6360],
        font_size=8.6,
    )
    add_callout(
        doc,
        "Decisión de modelo",
        "No existía un Risk Register reutilizable. Se creó ProjectRisk como único master de riesgo y "
        "RiskReadinessAssessment como evidencia versionada separada. Risk Record != Risk Readiness.",
        fill=CAUTION,
    )


def add_domain(doc: Document) -> None:
    doc.add_heading("2. Dominio Project Risk y lifecycle", level=1)
    add_table(
        doc,
        ["Objeto", "Responsabilidad", "Controles"],
        [
            ("ProjectRisk", "Identificación, categoría, owner, inherente, tratamiento, residual, aceptación", "Tenant + Project; RSK-00001; ETag"),
            ("RiskReadinessAssessment", "Snapshot de fuente/configuración, gaps, vigencia y readiness", "RRA-00001; versión; COMPLETED inmutable"),
            ("ProjectRiskReadiness", "Último resultado Project vigente", "READY/BLOCKED/STALE/EXPIRED"),
            ("PortfolioReadiness", "Agrega Recommended Project Set exacto", "Cobertura 100%; no promedia faltantes"),
        ],
        [2400, 4460, 2500],
        font_size=8.4,
    )
    doc.add_heading("2.1 Riesgo inherente, tratamiento y residual", level=2)
    add_table(
        doc,
        ["Dimensión", "Implementación"],
        [
            ("Inherent Risk", "likelihood_before + impact_before → matriz publicada; nunca se sobrescribe"),
            ("Treatment", "AVOID/REDUCE/TRANSFER/ACCEPT; owner, fecha, estado y evidencia en el Risk"),
            ("Residual Risk", "likelihood_after + impact_after; preservado aparte del inherente"),
            ("Acceptance", "Actor, fecha, comentario y autoridad; no equivale a Investment Approval"),
            ("SoD", "Owner no acepta su propio HIGH/CRITICAL cuando policy lo prohíbe"),
        ],
        [2300, 7060],
        font_size=8.8,
    )
    doc.add_heading("2.2 Lifecycles y catálogos", level=2)
    add_table(
        doc,
        ["Componente", "Estados / catálogo"],
        [
            ("Risk", "DRAFT → OPEN → UNDER_TREATMENT / MONITORING → CLOSED; VOIDED"),
            ("Treatment", "OPEN · IN_PROGRESS · COMPLETED · CANCELLED"),
            ("Assessment", "DRAFT · IN_PROGRESS · COMPLETED · SUPERSEDED · VOIDED"),
            ("Readiness", "NOT_STARTED · READY · BLOCKED · STALE · EXPIRED"),
            ("Ratings", "LOW · MODERATE · HIGH · CRITICAL, calculados por matriz configurable"),
            ("Categories", "19 starter values configurables; sin taxonomía sectorial hardcoded"),
        ],
        [2300, 7060],
        font_size=8.7,
    )


def add_readiness(doc: Document) -> None:
    doc.add_heading("3. Cálculo gobernado de Risk Readiness", level=1)
    add_table(
        doc,
        ["Chequeo Project", "Resultado controlado"],
        [
            ("Register ausente", "RISK_REGISTER_REQUIRED"),
            ("HIGH/CRITICAL sin owner", "HIGH_CRITICAL_OWNER_REQUIRED:<risk>"),
            ("Tratamiento exigido e incompleto", "TREATMENT_REQUIRED:<risk>"),
            ("Tratamiento crítico vencido", "OVERDUE_TREATMENT:<risk>"),
            ("Residual requerido no evaluado", "RESIDUAL_ASSESSMENT_REQUIRED:<risk>"),
            ("Residual sin aceptación", "RESIDUAL_ACCEPTANCE_REQUIRED:<risk>"),
            ("Evidencia bajo threshold", "RISK_EVIDENCE_COVERAGE_BELOW_THRESHOLD"),
            ("Fuente/configuración cambió", "STALE_RISK_SOURCE"),
            ("Fecha > valid_until", "RISK_READINESS_EXPIRED"),
        ],
        [3700, 5660],
        font_size=8.5,
    )
    add_callout(
        doc,
        "Regla semántica",
        "READY no significa ausencia de riesgos HIGH. Significa identificación, owners, tratamientos, residual, "
        "aceptaciones, evidencia y fuentes vigentes conforme a policy. Un residual HIGH aceptado puede permanecer READY.",
        fill=POSITIVE,
    )
    doc.add_heading("3.1 Cobertura de Project Set", level=2)
    add_table(
        doc,
        ["Caso", "Cálculo", "Readiness"],
        [
            ("A READY · B READY · C missing", "2/3 = 66,67%", "BLOCKED"),
            ("A READY · B BLOCKED · C STALE", "1/3 válido", "BLOCKED; contadores separados"),
            ("Todos READY y current", "N/N = 100%", "READY si no existen blockers"),
        ],
        [3500, 2600, 3260],
        font_size=8.8,
    )
    doc.add_heading("3.2 Freshness, hashes y reassessment", level=2)
    add_table(
        doc,
        ["Control", "Contenido"],
        [
            ("risk_source_hash", "Project/type/governance, riesgos, tratamiento, residual, aceptación, evidencia y config"),
            ("risk_readiness_hash", "Assessment/version, source/config hashes, counts, coverage, warnings y blockers"),
            ("Refresh Preview", "Deltas de fuente, riesgos, ratings, owners, tratamientos y aceptación; persisted=false"),
            ("Reassessment", "Nueva versión; nunca reescribe el snapshot COMPLETED histórico"),
            ("Validity", "90 días compatible con PYP-FFA; expirado no suministra evidencia"),
        ],
        [2700, 6660],
        font_size=8.4,
    )


def add_provider(doc: Document) -> None:
    doc.add_heading("4. Gate 07J evidence provider e integración", level=1)
    add_table(
        doc,
        ["Contrato", "Valor / regla"],
        [
            ("provider_key", "RISK_READINESS_PROVIDER"),
            ("source_module", "RISK_READINESS"),
            ("evidence_type", "RISK_READINESS"),
            ("status", "AVAILABLE"),
            ("scope", "PROJECT_SET; contrato soporta portfolio/project context"),
            ("payload", "Hashes, fechas, coverage, counts, warnings, blockers, source_current"),
            ("supply", "Sólo READY + current + 100% + sin blockers"),
            ("FID boundary", "can_enter_fid=false siempre en esta entrega"),
        ],
        [2500, 6860],
        font_size=8.7,
    )
    doc.add_heading("4.1 Perfiles preservados", level=2)
    add_table(
        doc,
        ["Gate Profile", "Class", "Blocking", "Coverage", "Validity", "Fallback"],
        [
            ("PYP-INV-SELECT", "B", "No por defecto", "Policy contextual", "90 días", "Governed/manual B según policy"),
            ("PYP-FFA", "A", "Sí", "100%", "90 días", "Manual prohibido"),
        ],
        [2000, 800, 1500, 1700, 1400, 1960],
        font_size=8.2,
    )
    doc.add_heading("4.2 Resolución en Gate 07J-EVID", level=2)
    add_table(
        doc,
        ["Fuente", "Estado Evidence Item"],
        [
            ("READY + current + 100%", "VALID · evidence_origin=GOVERNED_SOURCE"),
            ("BLOCKED", "BLOCKED"),
            ("STALE", "STALE · SOURCE_STALE"),
            ("EXPIRED", "EXPIRED"),
            ("Provider ausente", "SOURCE_PROVIDER_MISSING"),
            ("Payload presente pero inválido", "INVALID; nunca VALID por mera existencia"),
        ],
        [3500, 5860],
        font_size=8.7,
    )
    add_callout(
        doc,
        "Gap analysis actualizado",
        "Risk PYP-FFA deja de ser un missing provider. El resultado siguiente es contextual: Permit Readiness sólo "
        "donde la policy publicada todavía lo eleva a Class A; en los demás contextos, READY_TO_DESIGN_GATE07K. "
        "No se inició ninguno de los dos.",
        fill=CAUTION,
    )


def add_surfaces_security(doc: Document) -> None:
    doc.add_heading("5. Superficies USER/ADMIN, seguridad y APIs", level=1)
    add_table(
        doc,
        ["USER MODE — 8 vistas", "Función principal"],
        [
            ("My Risk Work", "Resumen operativo y brechas"),
            ("Project Set Risk Readiness", "Matriz Project por fecha, gaps, cobertura y readiness"),
            ("Project Risk Register", "Alta, filtros, tabla completa y detalle"),
            ("Risk Assessments", "Start, complete, versiones e inmutabilidad"),
            ("Treatments", "Owner, estrategia, estado y vencimiento"),
            ("Residual Risk & Acceptance", "Residual, autoridad y aceptación"),
            ("Risk Readiness Dashboard", "Chips compactos y blockers/warnings"),
            ("History / Audit", "Refresh Preview y contrato Gate 07J"),
        ],
        [3600, 5760],
        font_size=8.5,
    )
    doc.add_heading("5.1 ADMIN MODE — 16 tabs", level=2)
    add_table(
        doc,
        ["Grupo", "Tabs"],
        [
            ("General", "Configuration Overview · Risk Categories"),
            ("Scoring", "Likelihood Scale · Impact Scale · Risk Matrix · Rating Bands"),
            ("Rules", "Owner Rules · Treatment Rules · Residual Risk Rules · Acceptance Authority"),
            ("Readiness", "Readiness Criteria · Evidence Rules · Validity / Expiry · Gate Compatibility"),
            ("Governance", "Inheritance / Overrides · Versioning / Publish"),
        ],
        [2200, 7160],
        font_size=8.6,
    )
    add_callout(
        doc,
        "UI requerida cerrada",
        "Risk Register incluye filtros Open, High/Critical, No Owner, No Treatment, Overdue, Needs Acceptance y "
        "Expired Evidence, además de Due Date, Evidence y Warnings. La matriz de Project Set no usa tarjetas gigantes.",
        fill=POSITIVE,
    )
    doc.add_heading("5.2 RBAC, SoD, ETag e idempotencia", level=2)
    add_table(
        doc,
        ["Área", "Implementación"],
        [
            ("Roles", "risk_manager, owner, assessor, reviewer, acceptance_authority, viewer, configuration_admin"),
            ("Permissions", "risk read/create/edit/status/treatment/residual/accept + readiness create/edit/complete/refresh/admin"),
            ("Allowed actions", "Backend devuelve capacidades; frontend consume el contrato"),
            ("SoD", "Owner no autoacepta HIGH/CRITICAL; CRITICAL exige autoridad configurada"),
            ("ETag", "If-Match/revision_version; stale = 412 ETAG_MISMATCH"),
            ("Idempotency", "Create risk, acceptance, assessment, complete, reassess y refresh apply"),
            ("Audit", "SecurityEvent para creación, cambios, tratamientos, residual, aceptación, assessments y config"),
        ],
        [2500, 6860],
        font_size=8.3,
    )
    doc.add_heading("5.3 API pública", level=2)
    add_table(
        doc,
        ["Grupo", "Rutas implementadas"],
        [
            ("Risks", "GET/POST projects/{id}/risks · GET/PUT risks/{id} · status · accept"),
            ("Assessments", "GET/POST project assessments · GET/PUT assessment · complete · reassess"),
            ("Refresh", "project refresh/preview · project refresh apply"),
            ("Aggregation", "portfolio readiness · portfolio projects · investment-gate-evidence"),
            ("ADMIN", "overview · configurations · clone · update · publish · preview"),
        ],
        [2300, 7060],
        font_size=8.4,
    )


def add_persistence_validation(doc: Document) -> None:
    doc.add_heading("6. Persistencia, migración y validación", level=1)
    add_table(
        doc,
        ["Elemento", "Implementación"],
        [
            ("Migration", "20260830_0053; down_revision 0052; aditiva, reversible, tenant-scoped"),
            ("Tables", "project_risks · risk_readiness_assessments"),
            ("Uniqueness", "Risk number/idempotency; assessment number/version/idempotency"),
            ("Active assessment", "Índice único parcial por tenant + Project para DRAFT/IN_PROGRESS"),
            ("Checks", "Lifecycles, ratings, acceptance pair, coverage 0-100 y COMPLETED integrity"),
            ("Immutability", "ORM rechaza update/delete de COMPLETED/SUPERSEDED/VOIDED"),
            ("Performance", "Índices tenant/Project/status/rating y agregación por counts; sin portfolio risk score sintético"),
        ],
        [2500, 6860],
        font_size=8.3,
    )
    doc.add_heading("6.1 Evidencia de pruebas", level=2)
    add_table(
        doc,
        ["Validación", "Resultado", "Cobertura"],
        [
            ("PostgreSQL baseline", "69/69 PASS", "07D, Project Governance, workspace y Gate 07J base"),
            ("PostgreSQL portfolio", "74/74 PASS", "07E-07J-RISK, EVID, FEL, FUND y persistencia"),
            ("Risk Readiness final", "8/8 PASS", "Happy, stale, SoD, policy, config, blockers, expiry y coverage"),
            ("EVID regression", "7/7 PASS", "Provider source, stale, A/B y gap analysis"),
            ("Migration", "PASS", "0052→0053→0052→0053 + validadores"),
            ("Frontend targeted", "2/2 PASS", "Register, filtros/columnas, 16 tabs, preview"),
            ("Frontend AppFlow", "28/28 PASS", "Navegación y módulos históricos"),
            ("Browser Chromium", "1/1 PASS", "USER + ADMIN + no FID + 0 page errors"),
            ("Build / static", "PASS", "TypeScript, Vite, ESLint, Ruff, py_compile/import"),
            ("Local health", "PASS", "/app 200; API ready; DB/Redis ok; 19 risk paths"),
        ],
        [2850, 1550, 4960],
        font_size=7.9,
    )
    doc.add_heading("6.2 Baseline persistente antes/después", level=2)
    add_table(
        doc,
        ["Medida", "Antes", "Después", "Conclusión"],
        [
            ("Alembic head", "0052", "0053", "Migración esperada"),
            ("Enterprise Workspaces", "14", "14", "Inalterado"),
            ("Project Workspaces", "1", "1", "Inalterado"),
            ("AdminConfiguration", "80", "81", "+1 starter DRAFT"),
            ("Risk configurations", "0", "1 DRAFT / 0 published", "No auto-publish"),
            ("Project risks", "Tabla ausente", "0", "Sin datos de prueba"),
            ("Risk assessments", "Tabla ausente", "0", "Sin datos de prueba"),
            ("Gate07J Preparation / Evidence", "0 / 0", "0 / 0", "Inalterado"),
            ("FEL / Funds / Funding", "0 / 0 / 0", "0 / 0 / 0", "Inalterado"),
            ("Budget / Resource scenarios", "0 / 0", "0 / 0", "Inalterado"),
            ("Number sequences", "12", "12", "Preview no consumió números"),
            ("Project ID14 defaults MD5", "eea3648c6908a267d1e0651828ff4459", "igual", "Inalterado"),
        ],
        [2500, 1900, 2400, 2560],
        font_size=7.5,
    )


def add_risks_closeout(doc: Document) -> None:
    doc.add_heading("7. Riesgos técnicos, gap analysis y cierre", level=1)
    add_table(
        doc,
        ["Riesgo / deuda", "Estado y tratamiento"],
        [
            ("Tratamientos múltiples", "No implementados: el starter usa un tratamiento por Risk; ampliar sólo con caso aprobado"),
            ("Escala 100k Risks", "Diseño indexado y sin N+1; falta benchmark volumétrico dedicado"),
            ("Browser de reloj controlado", "Expiry/stale/SoD se validan en servicio; añadir fixture browser full-stack como hardening"),
            ("Concurrencia multi-worker", "ETag, versioning e índices protegen; ampliar carreras de alta carga en CI nocturno"),
            ("Permit provider", "Sigue fuera de alcance y sólo es siguiente gap donde policy lo eleva a Class A"),
        ],
        [3200, 6160],
        font_size=8.3,
    )
    add_callout(
        doc,
        "Safeguards verificados",
        "No se implementaron ERM, Monte Carlo/QRA, P50/P80, contingencia probabilística, Permit provider, "
        "Investment Decision/FID, GO/HOLD/RECYCLE/KILL, Project Initialization, Activation ni Execution.",
        fill=RISK,
    )
    add_callout(
        doc,
        "Decisión siguiente contextual",
        "Si el contexto mantiene un provider Class A faltante: NEXT = BUILD_MISSING_GOVERNED_PROVIDER · "
        "provider = PERMIT_READINESS_PROVIDER. En los demás contextos: NEXT = READY_TO_DESIGN_GATE07K. STOP: "
        "ninguno se inicia en esta entrega.",
        fill=CAUTION,
    )
    add_callout(
        doc,
        "Estado exclusivo",
        "GATE07J_RISK_RELEASE_VALIDATED · final_output = READY_FOR_GOVERNED_RISK_EVIDENCE · "
        "provider = RISK_READINESS_PROVIDER · status = AVAILABLE · can_enter_fid=false.",
        fill=POSITIVE,
    )


def add_deliverable_trace(doc: Document) -> None:
    doc.add_heading("8. Trazabilidad de entregables 1-69", level=1)
    items = [
        "Executive summary",
        "ADR Gate07J-RISK",
        "Baseline assessment",
        "Gate07J-EVID contract review",
        "REUSE BEFORE CREATE",
        "Risk model reuse/create decision",
        "Risk Register model",
        "Risk lifecycle",
        "Risk categories",
        "Risk Matrix",
        "Inherent/Residual separation",
        "Treatment architecture",
        "Risk Acceptance architecture",
        "Acceptance Authority",
        "RiskReadinessAssessment model",
        "Assessment lifecycle",
        "Readiness statuses/checks/policy",
        "High/Critical handling",
        "ProjectRiskReadiness model",
        "Project Set aggregation",
        "Coverage rules",
        "No synthetic portfolio score ADR",
        "Gate07I/Gate07F/Gate07E relationship",
        "FEL relationship",
        "Budget/Funding relationship",
        "Freshness/validity",
        "Source/readiness hashes",
        "Refresh/Reassessment/history",
        "Evidence origin",
        "Gate07J evidence contract",
        "PYP-FFA integration",
        "PYP-INV-SELECT compatibility",
        "Provider Registry update",
        "Missing Provider Analysis refresh",
        "Contextual can_design_investment_decision_gate",
        "ADMIN MODE",
        "USER MODE",
        "Workspace Navigator",
        "Risk Register/Detail UI",
        "Readiness Dashboard/Matrix",
        "Allowed actions",
        "Roles/permissions/SoD",
        "ETag/idempotency/audit",
        "APIs",
        "Persistence/numbering/migration",
        "Constraints/concurrency",
        "PostgreSQL happy path",
        "Critical no-owner/no-treatment tests",
        "Residual acceptance tests",
        "Overdue treatment test",
        "Expiry/stale tests",
        "Project Set coverage/mixed readiness tests",
        "SoD test",
        "Gate07J integration tests",
        "Gate07J-EVID gap reanalysis",
        "Frontend tests",
        "Browser USER E2E",
        "Browser SoD/stale/expiry E2E",
        "Browser ADMIN E2E",
        "Browser Gate07J integration",
        "Performance",
        "No-QRA/No-FID/No-Permit safeguards",
        "Regression",
        "Baseline before/after",
        "Risks/technical debt",
        "Updated Gate07J-EVID gap analysis",
        "Recommendation for next step",
        "Updated technical report",
        "Final exclusive status",
    ]

    def evidence(index: int) -> str:
        if index <= 6:
            return "Portada / §1 / ADR 56"
        if index <= 16:
            return "§2"
        if index <= 28:
            return "§3"
        if index <= 35:
            return "§4"
        if index <= 46:
            return "§5"
        if index <= 64:
            return "§6"
        return "§7 / Documento"

    rows = [(str(index), item, evidence(index), "CERRADO") for index, item in enumerate(items, 1)]
    # Fixed splits guarantee a visible header at each continuation in both
    # Word and LibreOffice; automatic tblHeader repetition is renderer-specific.
    for index, chunk in enumerate((rows[:7], rows[7:41], rows[41:])):
        if index:
            doc.add_page_break()
        add_table(
            doc,
            ["#", "Entregable", "Evidencia", "Estado"],
            chunk,
            [560, 5200, 1900, 1700],
            font_size=7.4,
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
    add_title_page(doc)
    add_contents(doc)
    add_baseline_reuse(doc)
    add_domain(doc)
    add_readiness(doc)
    add_provider(doc)
    add_surfaces_security(doc)
    add_persistence_validation(doc)
    add_risks_closeout(doc)
    add_deliverable_trace(doc)
    properties = doc.core_properties
    properties.title = "Informe Técnico Gate 07J-RISK — Risk Readiness Governed Provider"
    properties.subject = "Project Risk, Risk Readiness y evidencia gobernada para Gate 07J"
    properties.author = "P&Pmis Construction AI"
    properties.keywords = "Gate 07J-RISK, Risk Readiness, Project Risk, Gate 07J-EVID, PYP-FFA"
    properties.comments = "Generated from verified repository and localhost evidence on 2026-08-31."
    doc.save(OUTPUT)
    print(OUTPUT)


if __name__ == "__main__":
    build()
