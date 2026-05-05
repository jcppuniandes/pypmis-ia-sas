from pathlib import Path
from textwrap import wrap

from pypdf import PdfReader
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas


OUT = Path("docs/SDD_Analisis_Implementacion_P&Pmis_Ai_SaaS.pdf")
OUT.parent.mkdir(exist_ok=True)

W, H = A4
LEFT = 1.7 * cm
RIGHT = W - 1.7 * cm
TOP = H - 1.7 * cm
BOTTOM = 1.6 * cm
LINE = 13

c = canvas.Canvas(str(OUT), pagesize=A4)
c.setTitle("SDD Analisis Implementacion P&Pmis Ai SaaS")
c.setAuthor("Codex")
page_no = 0
y = TOP


def footer() -> None:
    c.setStrokeColor(colors.HexColor("#d8dee5"))
    c.line(LEFT, 1.25 * cm, RIGHT, 1.25 * cm)
    c.setFillColor(colors.HexColor("#667481"))
    c.setFont("Helvetica", 7.5)
    c.drawString(LEFT, 0.85 * cm, "P&Pmis Ai SaaS - Analisis SDD de implementacion")
    c.drawRightString(RIGHT, 0.85 * cm, f"Pagina {page_no}")


def new_page(title: str | None = None) -> None:
    global page_no, y
    if page_no:
        footer()
        c.showPage()
    page_no += 1
    y = TOP
    if title:
        c.setFillColor(colors.HexColor("#0f4c5c"))
        c.setFont("Helvetica-Bold", 16)
        c.drawString(LEFT, y, title)
        y -= 22
        c.setStrokeColor(colors.HexColor("#0f8b8d"))
        c.line(LEFT, y + 8, RIGHT, y + 8)
        y -= 8


def ensure_space(lines: int = 4) -> None:
    if y - lines * LINE < BOTTOM:
        new_page()


def heading(text: str) -> None:
    global y
    ensure_space(3)
    c.setFillColor(colors.HexColor("#17212b"))
    c.setFont("Helvetica-Bold", 12.5)
    c.drawString(LEFT, y, text)
    y -= 17


def para(text: str, width_chars: int = 104, gap: int = 5) -> None:
    global y
    c.setFont("Helvetica", 9.4)
    c.setFillColor(colors.HexColor("#243441"))
    for line in wrap(text, width_chars):
        ensure_space(1)
        c.drawString(LEFT, y, line)
        y -= LINE
    y -= gap


def bullet(items: list[str]) -> None:
    global y
    for item in items:
        lines = wrap(item, 96)
        ensure_space(len(lines))
        c.setFont("Helvetica", 9.2)
        c.setFillColor(colors.HexColor("#0f8b8d"))
        c.drawString(LEFT + 4, y, "-")
        c.setFillColor(colors.HexColor("#243441"))
        c.drawString(LEFT + 18, y, lines[0])
        y -= LINE
        for line in lines[1:]:
            c.drawString(LEFT + 18, y, line)
            y -= LINE
    y -= 4


def table_like(rows: list[tuple[str, str]], col1: float = 4.2 * cm) -> None:
    global y
    for key, value in rows:
        lines1 = wrap(key, 28)
        lines2 = wrap(value, 76)
        row_lines = max(len(lines1), len(lines2))
        height = row_lines * LINE + 8
        ensure_space(row_lines + 1)
        c.setFillColor(colors.HexColor("#f8fafb"))
        c.rect(LEFT, y - height + 7, RIGHT - LEFT, height, fill=1, stroke=0)
        c.setStrokeColor(colors.HexColor("#d8dee5"))
        c.rect(LEFT, y - height + 7, RIGHT - LEFT, height, fill=0, stroke=1)
        c.setFont("Helvetica-Bold", 8.6)
        c.setFillColor(colors.HexColor("#17212b"))
        yy = y
        for line in lines1:
            c.drawString(LEFT + 6, yy, line)
            yy -= LINE
        c.setFont("Helvetica", 8.6)
        c.setFillColor(colors.HexColor("#243441"))
        yy = y
        for line in lines2:
            c.drawString(LEFT + col1, yy, line)
            yy -= LINE
        y -= height + 3
    y -= 4


def build() -> None:
    global y
    new_page()
    c.setFillColor(colors.HexColor("#17212b"))
    c.setFont("Helvetica-Bold", 24)
    c.drawCentredString(W / 2, H - 5.0 * cm, "Analisis SDD de Implementacion")
    c.setFont("Helvetica", 12)
    c.setFillColor(colors.HexColor("#52616f"))
    c.drawCentredString(W / 2, H - 5.8 * cm, "P&Pmis Ai SaaS - Plataforma Project Controls basada en AACE TCM")
    c.drawCentredString(W / 2, H - 6.4 * cm, r"Repositorio: D:\\Documentos\\GitHub\\pypmis ia sas")
    c.drawCentredString(W / 2, H - 7.0 * cm, "Fecha de corte: 2026-05-05")
    c.setFillColor(colors.HexColor("#edf7f7"))
    c.roundRect(LEFT, H - 12.4 * cm, RIGHT - LEFT, 4.2 * cm, 8, fill=1, stroke=0)
    y = H - 8.8 * cm
    para(
        "Estado ejecutivo: la solucion ya demuestra el nucleo de producto. Un cronograma fuente XML/XER dispara un Business "
        "Process, el BP se enruta por workflow, el Control Core calcula desempeno EVM y el dashboard muestra "
        "decisiones, alertas y trazabilidad.",
        width_chars=92,
    )
    y = H - 10.2 * cm
    table_like(
        [
            ("Entrada maestra", "Carga de cronograma fuente en XER o XML. La UI lo presenta como Schedule XML/XER."),
            ("Flujo TCM", "Planeacion -> Cuentas de Control -> Ejecucion -> Control Core -> Decision -> Retroalimentacion."),
            ("Patron Unifier", "BP Log, Schedule Intake, workflow routing, ball-in-court, BP setup/uDesigner y audit trail inicial."),
        ],
        col1=4.5 * cm,
    )

    new_page("1. Resumen Ejecutivo")
    para("La aplicacion construida es una primera version funcional de una plataforma web de Project Controls tipo SaaS. Su proposito no es administrar tareas aisladas, sino operar como un sistema integrado de control que captura la realidad del proyecto, valida datos, analiza desempeno, genera alertas y transforma decisiones en acciones trazables.")
    para("El avance principal es que el disparador operativo ya no es un formulario manual ni una tarea suelta: el proceso inicia con la carga de un cronograma fuente XML/XER. Esa carga crea un Business Process de Schedule Intake, activa una compuerta de calidad de datos y permite enrutar el registro por pasos de workflow tipo Unifier.")
    heading("Capacidades implementadas")
    bullet([
        "Backend FastAPI con PostgreSQL, Redis/Celery y Docker Compose.",
        "Frontend React + TypeScript con dashboard de control, BP log y acciones de workflow.",
        "Modelo conectado: schedule, cost, progress, documents, changes, claims, KPI, alert y audit log.",
        "EVM engine con PV, EV, AC, SPI, CPI, SV, CV, EAC, ETC y VAC.",
        "Early warning con umbrales SPI/CPI y recomendaciones de control.",
        "Patrones tipo Unifier incorporados: BP records, ball-in-court, routing, setup de procesos y auditoria visible.",
    ])
    heading("Principio de diseno")
    para("La solucion debe seguir evolucionando como sistema nervioso de control de proyectos: datos conectados, decisiones gobernadas y accion temprana. La UI actual debe leerse como consola de Project Controls, no como app generica de tareas.")

    new_page("2. Alcance Implementado")
    table_like([
        ("Schedule Intake", "Carga de archivos .xer, .xml y reconocimiento .mpp. La importacion crea ScheduleImport, actividades importadas y relaciones logicas."),
        ("Business Process", "Cada importacion validada crea un BP SCH-INTAKE con record_no, estado, current_step y ball_in_court."),
        ("Workflow Routing", "Acciones route_to_approval, approve_baseline, reject_baseline y close_action."),
        ("BP Log", "El dashboard muestra todos los BusinessProcessInstance del proyecto, por ejemplo SCH-00001 y SCH-00002."),
        ("BP Setup / uDesigner", "Se exponen plantillas de procesos con formulario, pasos, roles y estado."),
        ("Audit Trail", "Se muestran acciones recientes desde AuditLog."),
        ("EVM y alertas", "ControlCoreService calcula KPIs y EarlyWarningService genera alertas."),
    ])
    heading("Validacion realizada")
    bullet([
        "docker compose up -d --build ejecutado correctamente.",
        "npm run build del frontend ejecutado correctamente.",
        "API responde en http://localhost:8000.",
        "Frontend responde en http://localhost:5173.",
        "Dashboard muestra fuente neutral: Schedule XML/XER, BP Setup / uDesigner, Audit Trail y BP Records.",
    ])

    new_page("3. Arquitectura Funcional TCM")
    para("El modelo operativo implementado respeta el flujo pedido: Planeacion -> Cuentas de Control -> Ejecucion -> Control Core -> Decision -> Retroalimentacion. La mejora clave es ubicar el cronograma como entrada maestra antes de Planeacion, con una compuerta de calidad que evita que el sistema analice datos sin una base temporal validada.")
    table_like([
        ("Planeacion", "WBS, actividades, baseline, logica FS/SS/FF/SF y critical path desde schedule import. Estado: parcial funcional."),
        ("Cuentas de Control", "ControlAccount enlaza actividades, presupuesto, costos y progreso. Estado: funcional demo."),
        ("Ejecucion", "ProgressRecord, CostRecord, recursos y documentos de evidencia. Estado: funcional demo."),
        ("Control Core", "EVM, cambios, claims, early warnings y AI brief. Estado: funcional."),
        ("Decision", "Workflow routing con aprobacion/rechazo y ball-in-court. Estado: funcional inicial."),
        ("Retroalimentacion", "Close Action Loop y auditoria de accion. Estado: inicial."),
    ])

    new_page("4. Arquitectura Tecnica")
    bullet([
        "API-first: FastAPI expone health, proyectos, schedule imports, schedule activities, dashboard, control cycle y workflow actions.",
        "Persistencia: SQLAlchemy sobre PostgreSQL, con creacion de tablas por Base.metadata.create_all en startup.",
        "Async-ready: Redis y Celery estan definidos en Docker Compose; worker puede ejecutar ciclos de control.",
        "Frontend: React + TypeScript, Vite, Recharts y Lucide para dashboard operacional.",
        "Infraestructura local: docker compose levanta db, redis, api, worker y frontend en localhost.",
    ])
    table_like([
        ("frontend :5173", "Dashboard SaaS, carga de cronograma, BP log, routing y visualizacion de control."),
        ("api :8000", "FastAPI, ingesta, control core, dashboard, workflows y auditoria."),
        ("db :5432", "PostgreSQL para entidades de proyecto, control y workflow."),
        ("redis :6379", "Broker para tareas asincronas."),
        ("worker", "Celery worker para ejecucion futura de control cycles y jobs."),
    ])

    new_page("5. Modelo De Datos")
    table_like([
        ("Project / Tenant", "Base multi-tenant y agrupacion del proyecto."),
        ("ScheduleImport", "Version importada del cronograma fuente. Guarda fuente, archivo, calidad y baseline."),
        ("ScheduleActivityMap / ActivityRelationship", "Actividades externas y relaciones logicas importadas del cronograma."),
        ("ControlAccount", "Objeto integrador schedule-cost-progress."),
        ("Budget / CostRecord / ProgressRecord", "Base para PV, EV, AC y medicion fisica."),
        ("KPI / Alert", "Resultados EVM y alertas tempranas."),
        ("ChangeRequest / Claim / Event", "Desviaciones, causalidad, impacto y contexto contractual."),
        ("Document", "Trazabilidad documental vinculada a entidades."),
        ("BusinessProcessInstance / WorkflowStepInstance", "Registro BP, routing, current step y ball-in-court."),
        ("AuditLog", "Acciones trazables de workflow y sistema."),
    ])

    new_page("6. Flujo Operativo Actual")
    bullet([
        "Abrir http://localhost:5173.",
        "Cargar un cronograma fuente XML/XER desde Schedule Intake Gate.",
        "El backend detecta fuente, parsea actividades/relaciones y calcula quality_score.",
        "Se crea un BP SCH-INTAKE con record_no y workflow inicial.",
        "El dashboard muestra BP Status, Current Step, Ball in Court y BP Records.",
        "El usuario enruta a aprobacion; la accion actualiza step, responsable y AuditLog.",
        "Control Core calcula KPIs EVM y genera alertas tempranas.",
    ])
    heading("Ejemplo verificado")
    table_like([
        ("SCH-00001", "Schedule Intake - CONTROL_BASELINE_00001.xer. Estado in_review, paso Impact Review."),
        ("SCH-00002", "Schedule Intake - Imported Schedule 00002.xml. Fuente visible neutral como Schedule XML/XER. Paso Approval, ball-in-court Control Manager."),
        ("AuditLog", "workflow.route_to_approval registrado para SCH-00002."),
    ])

    new_page("7. Evaluacion De Conformidad TCM")
    table_like([
        ("Entrada desde cronograma", "Conforme inicial. La carga del cronograma dispara el BP; no se inicia desde tareas manuales."),
        ("Integracion schedule-cost-progress", "Parcial conforme. ControlAccount conecta datos, pero falta mapeo automatico robusto de actividades a cuentas de control."),
        ("Control Core continuo", "Conforme inicial. CAPTURAR/VALIDAR/ANALIZAR/ALERTAR/DECIDIR/ACTUAR/REPETIR esta representado en servicios y dashboard."),
        ("EVM", "Conforme demo. Calculos implementados; falta manejo de periodos, curvas historicas y forecast granular."),
        ("Cambios y claims", "Parcial. Existen entidades y vista; falta workflow propio completo para cambios y reclamos."),
        ("Administracion contractual", "Inicial. Claims, Event y Document existen; faltan comunicaciones formales, notices y obligaciones."),
        ("Auditoria y gobierno", "Inicial conforme. AuditLog visible para acciones de workflow; falta historial completo por registro."),
    ])

    new_page("8. Referencia Unifier Incorporada")
    para("Los manuales de Unifier cargados por el usuario se usaron como referencia conceptual para orientar el producto, no como copia textual. Los patrones utiles identificados fueron: BP Log, registros BP, workflows y non-workflows, uDesigner para formularios, shells, permisos, setup de modulos, auditoria y EVM conectado a actividad.")
    table_like([
        ("BP Log", "Tabla BP Records con SCH-00001, SCH-00002 y registros vinculados a alertas, cambios y claims."),
        ("Workflow / Ball in Court", "BusinessProcessInstance.current_step y ball_in_court con acciones de routing."),
        ("uDesigner / formularios", "ProcessTemplateOut con form_schema, workflow_steps, roles y status."),
        ("Audit trail", "AuditLogOut visible en el dashboard."),
        ("EVM", "KPI y S-Curve con PV/EV/AC; engine EVM propio en backend."),
    ])

    new_page("9. Brechas, Riesgos Y Roadmap")
    heading("Brechas y riesgos")
    bullet([
        "Parser MPP: el formato .mpp se reconoce, pero requiere libreria/conversion especializada para lectura real.",
        "Migraciones: se usa create_all; para produccion se debe incorporar Alembic y versionado de esquema.",
        "Seguridad SaaS: falta autenticacion, autorizacion por rol y aislamiento multi-tenant endurecido.",
        "Mapeo control account: falta algoritmo configurable para mapear WBS/Activity/CBS desde el cronograma fuente a cuentas de control.",
        "Historico EVM: falta manejo de periodos de corte, snapshots y curvas historicas reales.",
        "Document control: falta almacenamiento real, versiones, transmittals y permisos documentales.",
        "Workflow engine: las acciones estan codificadas; falta motor configurable basado en definiciones de proceso.",
    ])
    heading("Roadmap recomendado")
    table_like([
        ("Fase 1", "Fortalecer ingestion schedule: parser XER completo, XML robusto, validaciones DCMA/AACE y log de errores."),
        ("Fase 2", "BP Engine configurable: uDesigner basico real con formularios, pasos, roles, transiciones y permisos."),
        ("Fase 3", "Control accounts automaticos: mapeo WBS/CBS/Activity, cost loading, baseline versioning y aprobacion."),
        ("Fase 4", "EVM historico y forecast: periodos de corte, curvas reales, productividad, EAC avanzado y escenarios."),
        ("Fase 5", "Contract & claims: notices, comunicaciones, eventos contractuales, causalidad, impacto y evidencia."),
        ("Fase 6", "SaaS empresarial: auth, RBAC, tenants, auditoria avanzada, API tokens, observabilidad y hardening."),
    ])

    new_page("10. Conclusion SDD")
    para("La implementacion actual ya prueba el nucleo del producto: un cronograma fuente XML/XER dispara un proceso de control, ese proceso se gobierna mediante workflow, el Control Core calcula desempeno y el dashboard traduce datos en decisiones accionables.")
    para("Todavia no es un Unifier completo ni un sistema productivo de Project Controls, pero la arquitectura ya apunta al comportamiento correcto: datos conectados, decisiones separadas de ejecucion, trazabilidad y retroalimentacion continua.")
    para("La prioridad tecnica recomendada es convertir las plantillas BP actuales en un motor configurable real, fortalecer la ingestion de cronogramas y consolidar el mapeo automatico hacia cuentas de control.")

    footer()
    c.save()


if __name__ == "__main__":
    build()
    reader = PdfReader(str(OUT))
    print(OUT.resolve())
    print(f"pages={len(reader.pages)}")
    print(f"bytes={OUT.stat().st_size}")
