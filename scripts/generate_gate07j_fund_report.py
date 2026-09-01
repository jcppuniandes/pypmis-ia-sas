from __future__ import annotations

from pathlib import Path

from docx import Document
from docx.shared import Inches

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
    / "Informe_Tecnico_Gate_07J_FUND_Funds_Manager_20260828.docx"
)
LOGO = REPO / "frontend" / "public" / "pypmis-construction-ai-logo.png"


def add_title_page(doc: Document) -> None:
    section = doc.sections[0]
    footer = section.footer.paragraphs[0]
    add_page_number(footer)
    # LibreOffice omits static even-page footer text while retaining PAGE fields.
    # Keep a page-number-only footer so Word and the canonical renderer stay identical.
    footer.runs[0].text = ""

    if LOGO.exists():
        paragraph = doc.add_paragraph()
        paragraph.paragraph_format.space_after = 8
        picture = paragraph.add_run().add_picture(str(LOGO), width=Inches(0.72))
        set_image_alt(picture, "Logotipo de P&Pmis Construction AI")

    kicker = doc.add_paragraph()
    set_run(kicker.add_run("INFORME TÉCNICO DE IMPLEMENTACIÓN"), size=10, color=TEAL, bold=True)
    title = doc.add_paragraph()
    set_run(title.add_run("Gate 07J-FUND"), size=25, color=INK, bold=True)
    subtitle = doc.add_paragraph()
    subtitle.paragraph_format.space_after = 16
    set_run(subtitle.add_run("Funds Manager / Funding Readiness"), size=15, color=DARK_BLUE, bold=True)

    for label, value in (
        ("Aplicación", "P&Pmis Construction AI"),
        ("Fecha", "30 de agosto de 2026"),
        ("Repositorio", "pypmis-ia-sas - branch main"),
        ("Migración", "20260827_0051 (head)"),
        ("Estado", "GATE07J_FUND_RELEASE_VALIDATED"),
    ):
        paragraph = doc.add_paragraph()
        paragraph.paragraph_format.space_after = 2
        set_run(paragraph.add_run(f"{label}: "), size=10.5, color=INK, bold=True)
        set_run(paragraph.add_run(value), size=10.5)

    rule = doc.add_paragraph()
    add_bottom_rule(rule)
    add_callout(
        doc,
        "Resultado ejecutivo",
        "GATE07J_FUND_RELEASE_VALIDATED. El cierre H confirma el lifecycle de Sources, Funds y Assignments, "
        "tres recorridos Browser E2E completos USER + ADMIN y la restauración exacta del baseline persistente. "
        "Funds Manager entrega evidencia trazable para Gate 07J sin asumir autoridad de Tesorería, "
        "Contabilidad, compromisos, pagos, FID o activación de Projects.",
        fill=POSITIVE,
    )
    add_table(
        doc,
        ["Capa", "Resultado", "Evidencia"],
        [
            ("Backend / API", "PASS", "Dominio, lifecycles, readiness, ETag, idempotencia y adapter Gate 07J"),
            ("PostgreSQL", "PASS", "126/126; migración 0051 -> 0050 -> 0051"),
            ("Frontend", "PASS", "Ruff, Prettier, ESLint, TypeScript, Vite y Vitest focalizado"),
            ("Browser E2E", "PASS", "3/3 FLOW_PASS contra API y PostgreSQL reales"),
            ("Localhost", "ACTIVE", "Frontend 5173; API 8000; PostgreSQL head 0051"),
        ],
        [1900, 1300, 6160],
        font_size=9.0,
    )
    doc.add_page_break()


def add_scope_and_architecture(doc: Document) -> None:
    doc.add_heading("1. Alcance, arquitectura y límites", level=1)
    add_callout(
        doc,
        "Objetivo funcional",
        "Implementar Funds Manager como proveedor gobernado de FUNDING_READINESS para Portfolios y Projects. "
        "La capacidad relaciona fuentes, fondos y asignaciones con el requerimiento derivado de la recomendación "
        "de Portfolio, manteniendo lineage, hashes y snapshots reproducibles.",
    )
    add_table(
        doc,
        ["Origen", "Funds Manager", "Consumidor"],
        [
            ("Gate 07I: alternativa recomendada y requerimiento", "Readiness por Portfolio, Project y periodo", "Gate 07J Investment Gate Preparation"),
            ("Gate 07G: escenario presupuestal", "Referencia de necesidad; nunca fuente de dinero", "Paquete de evidencia gobernada"),
            ("AdminConfiguration publicada", "Política efectiva por scope y governance model", "UI USER/ADMIN, API y auditoría"),
        ],
        [2950, 3210, 3200],
        font_size=8.7,
    )
    add_table(
        doc,
        ["Regla de dominio", "Decisión implementada"],
        [
            ("Budget != Funding", "Los presupuestos expresan necesidad; sólo las asignaciones de fondos expresan cobertura."),
            ("Modelo predeterminado", "CAPITAL_OWNER. Contractor Delivery y Direct Internal no son obligatorios."),
            ("Moneda", "No existe conversión FX silenciosa; monedas incompatibles generan blocker."),
            ("Autoridad", "El módulo prepara evidencia; no aprueba inversión, paga, compromete ni activa ejecución."),
        ],
        [2750, 6610],
        font_size=9.0,
    )

    doc.add_heading("1.1 Capas implementadas", level=2)
    add_table(
        doc,
        ["Capa", "Componente", "Responsabilidad"],
        [
            ("Dominio", "models.py", "Fuentes estratégicas, fondos, asignaciones y snapshots"),
            ("Aplicación", "service.py", "Lifecycles, reglas financieras, readiness, hashes y eventos"),
            ("Contrato", "schemas.py / router.py", "DTOs tipados y endpoints USER/ADMIN"),
            ("Integración", "investment_gate_preparation/service.py", "Adapter de evidencia FUNDING_READINESS"),
            ("Experiencia", "frontend/src/features/funds-manager", "Workspace USER y configuración ADMIN"),
        ],
        [1500, 2920, 4940],
        font_size=8.8,
    )
    add_callout(
        doc,
        "REUSE BEFORE CREATE",
        "Se reutilizaron AdminConfiguration, resolución por scope, RBAC, SecurityEvent, ETag, idempotencia, "
        "Workspace Context y el motor de requisitos de Gate 07J. La tabla FBS existente funding_sources se preservó; "
        "la nueva entidad se denominó StrategicFundingSource para evitar duplicidad semántica y técnica.",
        fill=CAUTION,
    )
def add_domain(doc: Document) -> None:
    doc.add_heading("2. Modelo de dominio y persistencia", level=1)
    add_table(
        doc,
        ["Agregado", "Propósito", "Controles principales"],
        [
            ("StrategicFundingSource", "Origen gobernado del capital", "FSRC, moneda, restricciones, elegibilidad, status, ETag"),
            ("Fund", "Vehículo o bolsa disponible", "FUND, source FK, moneda, capacidad, vigencia, status, ETag"),
            ("FundingAssignment", "Cobertura de Portfolio/Project/periodo", "FASN, amount, condition, reservation, idempotency"),
            ("FundingReadinessSnapshot", "Resultado reproducible", "source hashes, requirement hash, coverage, blockers, stale"),
        ],
        [2350, 3250, 3760],
        font_size=8.8,
    )
    doc.add_heading("2.1 Lifecycles controlados", level=2)
    add_table(
        doc,
        ["Entidad", "Estados / transición", "Efecto"],
        [
            ("Fuente", "DRAFT -> ACTIVE -> SUSPENDED/CLOSED", "Sólo ACTIVE puede soportar financiación vigente."),
            ("Fondo", "DRAFT -> ACTIVE -> SUSPENDED/CLOSED", "Valida fuente, moneda, capacidad y periodo."),
            ("Asignación", "DRAFT -> RESERVED/CONFIRMED -> RELEASED", "RELEASED devuelve disponibilidad; CANCELLED sólo anula asignación no efectiva."),
            ("Readiness", "NOT_STARTED / BLOCKED / STALE / READY", "READY habilita evidencia; los demás estados no."),
        ],
        [1900, 3210, 4250],
        font_size=8.7,
    )
    add_callout(
        doc,
        "Integridad financiera",
        "La suma de asignaciones activas no puede superar la capacidad del fondo ni contar dos veces el mismo tramo. "
        "Las cancelaciones quedan auditadas; no se borran para corregir historia.",
        fill=POSITIVE,
    )
    doc.add_heading("2.2 Decisión de lifecycle del cierre H", level=2)
    add_table(
        doc,
        ["Entidad", "Estado candidato", "Decisión", "Rationale"],
        [
            ("Funding Source", "AUTHORIZED", "KEEP CURRENT", "ACTIVE ya representa autorización y activación gobernadas."),
            ("Fund", "AUTHORIZED", "PERSISTED", "La autorización Four-Eyes cambia acciones y precede la activación."),
            ("Fund", "EXHAUSTED", "DERIVED", "available_amount = 0 es reversible y evita desincronización."),
            ("Fund", "SUPERSEDED", "RESERVED", "CLOSED, historia y revisiones preservan reemplazo sin una acción nueva."),
            ("Assignment", "RELEASED", "PERSISTED", "Devuelve capacidad y conserva significado de auditoría distinto de CANCELLED."),
            ("Assignment", "EXPIRED", "DERIVED", "Las fechas excluyen cobertura actual sin borrar el registro histórico."),
        ],
        [1660, 1760, 1660, 4280],
        font_size=8.2,
    )
    add_callout(
        doc,
        "ADR 53 - KEEP_CURRENT",
        "Se persisten únicamente estados que cambian acciones, disponibilidad, readiness o significado de auditoría. "
        "EXHAUSTED y EXPIRED se derivan; no se requirió migración sucesora ni se modificó 20260827_0051.",
        fill=CAUTION,
    )
    doc.add_heading("2.3 Migración Alembic", level=2)
    add_table(
        doc,
        ["Artefacto", "Resultado"],
        [
            ("20260827_0051_gate07j_funds_manager.py", "Cuatro tablas aditivas con FKs tenant-scoped, checks, uniques e índices."),
            ("Upgrade", "0046 -> 0047 -> 0048 -> 0049 -> 0050 -> 0051 validado."),
            ("Reversibilidad", "0051 -> 0050 -> 0051 validado sin afectar objetos previos."),
            ("Baseline persistente", "Datos previos y hash de Project 14 permanecieron idénticos."),
        ],
        [3600, 5760],
        font_size=8.9,
    )
def add_readiness(doc: Document) -> None:
    doc.add_heading("3. Motor de Funding Readiness", level=1)
    add_table(
        doc,
        ["Paso", "Cálculo / validación", "Salida"],
        [
            ("1", "Resolver recomendación Gate 07I y escenario presupuestal Gate 07G", "Requerimiento y lineage"),
            ("2", "Seleccionar fuentes, fondos y asignaciones vigentes del mismo tenant/scope", "Cobertura elegible"),
            ("3", "Aplicar moneda, restricciones, condiciones, periodo y no doble conteo", "Warnings y blockers"),
            ("4", "Agregar por Portfolio, Project y periodo", "Confirmed, reserved, gap y porcentajes"),
            ("5", "Sellar hashes de source, requirement y readiness", "Snapshot reproducible"),
            ("6", "Comparar fuentes actuales contra snapshot", "READY, BLOCKED, STALE o NOT_STARTED"),
        ],
        [1000, 5320, 3040],
        font_size=8.6,
    )
    doc.add_heading("3.1 Criterios de decisión", level=2)
    add_table(
        doc,
        ["Estado", "Criterio resumido", "Gate 07J"],
        [
            ("READY", "100% confirmado, moneda coherente, fuentes actuales, sin blocker abierto", "Puede suministrar evidencia"),
            ("BLOCKED", "Gap, restricción incumplida, condición bloqueante o moneda incompatible", "No suministra evidencia"),
            ("STALE", "Cambió recomendación, presupuesto, configuración, fondo o asignación", "Requiere refresh"),
            ("NOT_STARTED", "No existe requerimiento/snapshot evaluable", "No suministra evidencia"),
        ],
        [1500, 5300, 2560],
        font_size=8.7,
    )
    add_callout(
        doc,
        "Salida contractual exclusiva",
        "El estado READY produce final_output = READY_FOR_GOVERNED_FUNDING_EVIDENCE y "
        "can_supply_investment_gate_evidence = true. No produce GO, FID ni autorización de gasto.",
        fill=POSITIVE,
    )
    doc.add_heading("3.2 Trazabilidad y vigencia", level=2)
    add_table(
        doc,
        ["Control", "Evidencia persistida"],
        [
            ("Source lineage", "source_convergence_id, recommendation hash y project-set hash"),
            ("Budget lineage", "budget_scenario_id, budget hash y requirement hash"),
            ("Funding lineage", "source/fund/assignment snapshot y source hash"),
            ("Resultado", "coverage summaries, warnings, blockers y funding_readiness_hash"),
            ("Freshness", "source_current y comparación determinística de hashes"),
        ],
        [2600, 6760],
        font_size=9.0,
    )
def add_governance(doc: Document) -> None:
    doc.add_heading("4. Gobierno, seguridad y concurrencia", level=1)
    add_table(
        doc,
        ["Control", "Implementación"],
        [
            ("Configuración", "Starter DRAFT; clone/edit/preview/publish; resolución por tenant/scope."),
            ("Herencia", "Enterprise, Portfolio y Project con política efectiva y hash de source."),
            ("RBAC", "Permisos separados para lectura, gestión, confirmación, readiness y configuración."),
            ("Four Eyes", "Acciones de confirmación/publicación respetan segregación cuando la política la exige."),
            ("ETag", "If-Match evita last-write-wins silencioso y responde 412 en conflicto."),
            ("Idempotencia", "Claves tenant-scoped impiden duplicados en reintentos."),
            ("Auditoría", "SecurityEvent conserva actor, target, transición, hashes y contexto."),
        ],
        [2450, 6910],
        font_size=8.8,
    )
    doc.add_heading("4.1 Restricciones y condiciones", level=2)
    add_table(
        doc,
        ["Dimensión", "Comportamiento"],
        [
            ("Elegibilidad", "Fuentes o fondos no elegibles quedan excluidos y explicados."),
            ("Uso restringido", "El destino debe satisfacer etiquetas y condiciones de uso."),
            ("Condiciones", "Open blocking impide READY; no blocking se presenta como warning."),
            ("Vigencia", "Fechas fuera del periodo requerido bloquean la cobertura correspondiente."),
            ("Moneda", "Sin FX explícito no se agrega una moneda diferente."),
        ],
        [2450, 6910],
        font_size=8.9,
    )
    add_callout(
        doc,
        "Modelo de gobierno",
        "CAPITAL_OWNER es el comportamiento predeterminado. Ningún flujo obliga a que Contractor Delivery o "
        "Direct Internal administren financiación; sólo una configuración publicada y aplicable puede habilitar variantes.",
        fill=CAUTION,
    )
def add_api_ui(doc: Document) -> None:
    doc.add_heading("5. API, interfaz y navegación", level=1)
    add_table(
        doc,
        ["Superficie", "Capacidades"],
        [
            ("USER API", "Overview, sources, funds, assignments, readiness, refresh y evidence."),
            ("ADMIN API", "List/clone/update/preview/publish de configuración efectiva."),
            ("USER UI", "Overview, Sources, Funds, Assignments, Coverage, Restrictions, Conditions y Evidence."),
            ("ADMIN UI", "General, policies, thresholds, governance models, inheritance, permissions y preview."),
            ("Workspace Context", "Funds en Portfolio y Project Funding en Project."),
        ],
        [2500, 6860],
        font_size=8.9,
    )
    doc.add_heading("5.1 Integración con Gate 07J", level=2)
    add_table(
        doc,
        ["Contrato", "Contenido"],
        [
            ("source_module", "FUNDS_MANAGER"),
            ("requirement_type", "FUNDING_READINESS"),
            ("status", "READY / BLOCKED / STALE / NOT_STARTED"),
            ("payload", "Coverage, gap, project/period summaries, restrictions, conditions y hashes"),
            ("habilitación", "Sólo READY + source_current + ausencia de blockers"),
        ],
        [2500, 6860],
        font_size=9.0,
    )
    add_callout(
        doc,
        "Experiencia consistente",
        "La capacidad se integró al árbol de macroprocesos, módulos y submódulos existente sin duplicar pantallas. "
        "USER MODE opera evidencia; ADMIN MODE configura políticas. El selector de modo y la navegación previa se conservan.",
    )


def add_validation(doc: Document) -> None:
    doc.add_heading("6. Validación y despliegue", level=1)
    add_table(
        doc,
        ["Prueba", "Resultado", "Detalle"],
        [
            ("Backend focalizado", "PASS", "8 passed; 1 skipped (PostgreSQL opt-in)"),
            ("PostgreSQL transversal", "PASS", "69/69"),
            ("PostgreSQL Gates 07E-07J", "PASS", "57/57"),
            ("Total PostgreSQL", "PASS", "126/126"),
            ("Migration cycle", "PASS", "0051 -> 0050 -> 0051"),
            ("Ruff / compile", "PASS", "0 errores en el alcance"),
            ("ESLint", "PASS", "0 errores en alcance; spec E2E fuera del patrón de lint"),
            ("TypeScript / Vite", "PASS", "2405 módulos; build de producción"),
            ("Vitest", "PASS", "Funds Manager 2/2; regresión global sin fallos de alcance observados"),
            ("Browser E2E", "PASS", "3/3 FLOW_PASS USER + ADMIN; 8,1 min"),
        ],
        [2650, 1300, 5410],
        font_size=8.3,
    )
    doc.add_heading("6.1 Protección del baseline persistente", level=2)
    add_table(
        doc,
        ["Control", "Antes", "Después", "Resultado"],
        [
            ("Admin configurations", "77", "77", "MATCH"),
            ("Enterprise workspaces", "14", "14", "MATCH"),
            ("User accounts", "9", "9", "MATCH"),
            ("Project 14 defaults MD5", "eea3648c6908a267d1e0651828ff4459", "eea3648c6908a267d1e0651828ff4459", "MATCH"),
            ("Strategic sources / funds", "0 / 0", "0 / 0", "MATCH"),
            ("Assignments / snapshots", "0 / 0", "0 / 0", "MATCH"),
            ("Alembic head", "0051", "0051", "MATCH"),
        ],
        [2500, 2600, 2600, 1660],
        font_size=8.1,
    )


def add_lifecycle_browser_closeout(doc: Document) -> None:
    doc.add_heading("7. Lifecycle & Browser E2E Release Closeout", level=1)
    add_callout(
        doc,
        "Decisión de release",
        "Los criterios del PROMPT 07J-FUND-H quedaron cubiertos sin expandir alcance. La suite Browser usa "
        "frontend, API y PostgreSQL reales, sin mocks de negocio, y fue ejecutada tres veces de forma consecutiva.",
        fill=POSITIVE,
    )

    doc.add_heading("7.1 Flujo USER validado", level=2)
    add_table(
        doc,
        ["Área", "Evidencia Browser E2E", "Resultado"],
        [
            ("Funding Source", "Código, tipo, moneda, vigencia, status, restricciones y evidencia", "PASS"),
            ("Fund", "Source, capacidad autorizada, assigned/available, vigencia y restricciones", "PASS"),
            ("Assignment", "DRAFT -> RESERVED -> CONFIRMED; número estable y ETag cambiante", "PASS"),
            ("Coverage", "Required 100, Confirmed 100, Reserved 0, Gap 0, Coverage 100%", "PASS"),
            ("Readiness", "READY, source_current=true, hash presente, sin blockers", "PASS"),
            ("Gate 07J", "FUNDS_MANAGER / FUNDING_READINESS / GOVERNED_SOURCE", "PASS"),
            ("Release", "Histórico preservado; coverage baja y disponibilidad aumenta", "PASS"),
            ("Expiry", "Asignación histórica visible; contribución actual cero; readiness recalculado", "PASS"),
        ],
        [1850, 6160, 1350],
        font_size=8.3,
    )

    doc.add_heading("7.2 Casos negativos y guardrails", level=2)
    add_table(
        doc,
        ["Caso", "Comportamiento comprobado", "Resultado"],
        [
            ("Partial funding", "Confirmed 70%, potential 90%, gap 30; no READY automático", "PASS"),
            ("Currency mismatch", "COP vs USD sin normalización produce CURRENCY_NOT_COMPARABLE", "PASS"),
            ("Restriction mismatch", "Fondo inelegible se excluye con razón explícita", "PASS"),
            ("Blocking condition", "OPEN bloquea; al satisfacerse, readiness se recalcula", "PASS"),
            ("Stale source", "Cambios de source exponen STALE y delta antes de refresh", "PASS"),
            ("Over-allocation", "70 + 70 sobre 100 se rechaza transaccionalmente", "PASS"),
            ("No double count", "Subasignaciones explican distribución y no duplican cobertura", "PASS"),
            ("CONTRACTOR_DELIVERY", "Funding readiness no es obligatorio por defecto", "PASS"),
        ],
        [2070, 5940, 1350],
        font_size=8.3,
    )

    doc.add_heading("7.3 Flujo ADMIN y controles de plataforma", level=2)
    add_table(
        doc,
        ["Control", "Evidencia", "Resultado"],
        [
            ("Clone/Edit", "Configuración efectiva clonada a DRAFT y campos gobernados editados", "PASS"),
            ("Preview", "persisted=false; no crea Source, Fund, Assignment ni Snapshot", "PASS"),
            ("Save", "If-Match, revision_version y ETag; permanece DRAFT", "PASS"),
            ("Stale ETag", "Segunda sesión obtiene 412 ETAG_MISMATCH sin overwrite", "PASS"),
            ("Publish", "Nueva revisión PUBLISHED; anterior inmutable; hash efectivo cambia", "PASS"),
            ("Inheritance", "Nearest published override resuelto por Tenant/Enterprise/Portfolio", "PASS"),
            ("Four-Eyes", "Mismo actor rechazado; segundo actor autorizado completa la acción", "PASS"),
            ("Idempotency", "Retry de create/confirm no duplica asignación ni coverage", "PASS"),
            ("Console/network", "0 errores no controlados; sólo conflictos negativos esperados", "PASS"),
        ],
        [2100, 5910, 1350],
        font_size=8.2,
    )

    doc.add_heading("7.4 Estabilidad, datos efímeros y baseline", level=2)
    add_table(
        doc,
        ["Ejecución", "Preparación determinística", "Browser", "Teardown"],
        [
            ("FLOW 1", "Prerequisites READY", "PASS", "MATCH"),
            ("FLOW 2", "Prerequisites READY", "PASS", "MATCH"),
            ("FLOW 3", "Prerequisites READY", "PASS", "MATCH"),
        ],
        [1500, 3760, 1700, 2400],
        font_size=8.6,
    )
    add_callout(
        doc,
        "Protección persistente",
        "El fixture creó datos aislados para tres copias, reutilizó prerequisites idempotentes y eliminó "
        "configuraciones, workspaces, sources, funds, assignments, snapshots y recomendaciones. "
        "PERSISTENT_BASELINE_MATCH=True; Project 14 no fue usado destructivamente.",
        fill=POSITIVE,
    )

    doc.add_heading("7.5 Defectos mínimos corregidos", level=2)
    add_table(
        doc,
        ["Hallazgo", "Corrección aplicada", "Impacto"],
        [
            ("Semántica de release", "RELEASED diferenciado de CANCELLED y cubierto por auditoría", "Disponibilidad e historia correctas"),
            ("Expiry", "Estado derivado por vigencia y exclusión de coverage", "Sin estado persistido redundante"),
            ("Capital owner applicability", "Resolución por membresía activa del Portfolio", "CONTRACTOR opcional por defecto"),
            ("Blocking precedence", "Condiciones bloqueantes preceden estados no aplicables", "Readiness consistente"),
            ("Preview UI", "Mensaje de acción ya no se sobrescribe y persisted=false queda visible", "Contrato ADMIN verificable"),
            ("Fixture E2E", "Prerequisites 07F/07G/07H/07I/FUND idempotentes y teardown circular seguro", "Tres corridas reproducibles"),
        ],
        [2250, 4460, 2650],
        font_size=8.0,
    )


def add_acceptance_matrix(doc: Document) -> None:
    doc.add_heading("8. Matriz de aceptación", level=1)
    criteria = [
        "Funding Source lifecycle decision", "Fund AUTHORIZED decision", "Fund EXHAUSTED decision",
        "Fund SUPERSEDED decision", "Assignment RELEASED decision", "Assignment EXPIRED decision",
        "Lifecycle ADR completed", "USER Funding Source flow", "USER Fund flow",
        "Assignment DRAFT->RESERVED->CONFIRMED", "Funding Coverage", "Funding Readiness READY",
        "Gate07J governed evidence", "Release semantics", "Expiry semantics", "Partial funding",
        "Currency mismatch", "Restriction mismatch", "Blocking condition", "Stale source",
        "Over-allocation protection", "No double count", "CONTRACTOR_DELIVERY optional",
        "ADMIN Clone DRAFT", "ADMIN Edit", "ADMIN Preview persisted=false", "ADMIN Save",
        "ADMIN stale ETag", "ADMIN Publish", "ADMIN inheritance", "Four-Eyes / SoD", "Idempotency",
        "No Treasury/Accounting", "No Commitments/Payments", "No Investment/FID controls",
        "No Initialization/Activation", "Browser console/network", "Playwright 3 consecutive runs",
        "PostgreSQL regression", "Frontend regression", "Persistent baseline protected",
    ]
    add_table(
        doc,
        ["Criterio", "Resultado"],
        [(criterion, "PASS") for criterion in criteria],
        [7810, 1550],
        font_size=8.2,
    )
    add_callout(
        doc,
        "Estado exclusivo final",
        "GATE07J_FUND_RELEASE_VALIDATED",
        fill=POSITIVE,
    )
    add_callout(
        doc,
        "Despliegue activo",
        "Docker Compose mantiene API, worker, beat y frontend activos; PostgreSQL y Redis están healthy. "
        "Aplicación: http://localhost:5173/app. API readiness: http://localhost:8000/api/v1/health/ready.",
        fill=POSITIVE,
    )
def add_closeout(doc: Document) -> None:
    doc.add_heading("9. Cierre técnico, riesgos y STOP", level=1)
    add_table(
        doc,
        ["Aspecto", "Estado", "Observación"],
        [
            ("Arquitectura", "CLOSED", "Límites y lifecycle documentados en ADR 52 y ADR 53."),
            ("Funcionalidad", "CLOSED", "Sources -> Funds -> Assignments -> Readiness -> Evidence."),
            ("Persistencia", "CLOSED", "Migración aditiva y reversible, schema validado."),
            ("Seguridad", "CLOSED", "RBAC, Four Eyes, ETag, idempotencia y eventos."),
            ("Release local", "CLOSED", "Servicios healthy y 3/3 FLOW_PASS."),
            ("Escalabilidad", "WATCH", "Paginar histories y matrices cuando aumente el volumen."),
            ("FX", "STOP", "No habilitar conversión hasta definir fuente, fecha y política de tasa."),
        ],
        [2250, 1450, 5660],
        font_size=8.8,
    )
    add_callout(
        doc,
        "Estado final",
        "GATE07J_FUND_RELEASE_VALIDATED",
        fill=POSITIVE,
    )
    add_callout(
        doc,
        "STOP boundary",
        "No implementar ni inferir Investment Decision/FID, GO/HOLD/RECYCLE/KILL, Tesorería, Contabilidad, "
        "compromisos, pagos, Project Initialization, Activation o Execution. Funds Manager se detiene en "
        "evidencia gobernada de funding readiness.",
        fill=RISK,
    )

    doc.add_heading("9.1 Inventario técnico", level=2)
    add_table(
        doc,
        ["Componente", "Ruta"],
        [
            ("Backend", "backend/app/modules/funds_manager/{models,schemas,service,router}.py"),
            ("Migración", "backend/alembic/versions/20260827_0051_gate07j_funds_manager.py"),
            ("Adapter", "backend/app/modules/investment_gate_preparation/service.py"),
            ("Frontend", "frontend/src/features/funds-manager/*"),
            ("Navegación", "frontend/src/navigation/applicationNavigation.ts"),
            ("Tests", "backend/tests/*funds_manager* y frontend/e2e/funds-manager.spec.ts"),
            ("ADR", "docs/52-adr-gate07j-fund-funds-manager.md y docs/53-adr-gate07j-fund-lifecycle-closeout.md"),
            ("CI", ".github/workflows/ci.yml y docker-compose.gate07e.yml"),
        ],
        [2250, 7110],
        font_size=8.8,
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
    add_scope_and_architecture(doc)
    add_domain(doc)
    add_readiness(doc)
    add_governance(doc)
    add_api_ui(doc)
    add_validation(doc)
    add_lifecycle_browser_closeout(doc)
    add_acceptance_matrix(doc)
    add_closeout(doc)

    properties = doc.core_properties
    properties.title = "Informe Técnico Gate 07J-FUND - Funds Manager"
    properties.subject = "Lifecycle & Browser E2E Release Closeout de Funding Readiness gobernado"
    properties.author = "P&Pmis Construction AI"
    properties.keywords = "Gate 07J, Funds Manager, Funding Readiness, Portfolio, Project, evidence"
    properties.comments = "Updated from verified repository evidence on 2026-08-30."
    doc.save(OUTPUT)
    print(OUTPUT)


if __name__ == "__main__":
    build()
