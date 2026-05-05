from pathlib import Path
from textwrap import wrap

from pypdf import PdfReader
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas


OUT = Path("docs/Manual_de_Uso_P&Pmis_Ai_SaaS.pdf")
OUT.parent.mkdir(exist_ok=True)

W, H = A4
LEFT = 1.65 * cm
RIGHT = W - 1.65 * cm
TOP = H - 1.55 * cm
BOTTOM = 1.55 * cm
LINE = 12.8

c = canvas.Canvas(str(OUT), pagesize=A4)
c.setTitle("Manual de Uso - P&Pmis Ai SaaS")
c.setAuthor("Codex")
page_no = 0
y = TOP


def clean(text: str) -> str:
    return (
        text.replace("->", "->")
        .replace("Planeacion", "Planeacion")
        .replace("Ejecucion", "Ejecucion")
    )


def footer() -> None:
    c.setStrokeColor(colors.HexColor("#d8dee5"))
    c.line(LEFT, 1.22 * cm, RIGHT, 1.22 * cm)
    c.setFillColor(colors.HexColor("#667481"))
    c.setFont("Helvetica", 7.5)
    c.drawString(LEFT, 0.82 * cm, "P&Pmis Ai SaaS - Manual de uso")
    c.drawRightString(RIGHT, 0.82 * cm, f"Pagina {page_no}")


def new_page(title: str | None = None) -> None:
    global page_no, y
    if page_no:
        footer()
        c.showPage()
    page_no += 1
    y = TOP
    if title:
        c.setFillColor(colors.HexColor("#17212b"))
        c.setFont("Helvetica-Bold", 16)
        c.drawString(LEFT, y, title)
        y -= 19
        c.setStrokeColor(colors.HexColor("#0f8b8d"))
        c.setLineWidth(1.4)
        c.line(LEFT, y + 7, RIGHT, y + 7)
        y -= 8


def ensure_space(lines: int = 4) -> None:
    if y - lines * LINE < BOTTOM:
        new_page()


def heading(text: str) -> None:
    global y
    ensure_space(3)
    c.setFillColor(colors.HexColor("#0f4c5c"))
    c.setFont("Helvetica-Bold", 12.2)
    c.drawString(LEFT, y, text)
    y -= 16


def subheading(text: str) -> None:
    global y
    ensure_space(2)
    c.setFillColor(colors.HexColor("#17212b"))
    c.setFont("Helvetica-Bold", 10.3)
    c.drawString(LEFT, y, text)
    y -= 14


def para(text: str, width_chars: int = 102, gap: int = 5) -> None:
    global y
    c.setFont("Helvetica", 9.1)
    c.setFillColor(colors.HexColor("#243441"))
    for line in wrap(clean(text), width_chars):
        ensure_space(1)
        c.drawString(LEFT, y, line)
        y -= LINE
    y -= gap


def bullet(items: list[str]) -> None:
    global y
    for item in items:
        lines = wrap(clean(item), 94)
        ensure_space(len(lines) + 1)
        c.setFont("Helvetica", 9)
        c.setFillColor(colors.HexColor("#0f8b8d"))
        c.drawString(LEFT + 4, y, "-")
        c.setFillColor(colors.HexColor("#243441"))
        c.drawString(LEFT + 18, y, lines[0])
        y -= LINE
        for line in lines[1:]:
            c.drawString(LEFT + 18, y, line)
            y -= LINE
    y -= 3


def numbered(items: list[str]) -> None:
    global y
    for index, item in enumerate(items, start=1):
        lines = wrap(clean(item), 92)
        ensure_space(len(lines) + 1)
        c.setFont("Helvetica-Bold", 9)
        c.setFillColor(colors.HexColor("#0f8b8d"))
        c.drawString(LEFT + 2, y, f"{index}.")
        c.setFont("Helvetica", 9)
        c.setFillColor(colors.HexColor("#243441"))
        c.drawString(LEFT + 20, y, lines[0])
        y -= LINE
        for line in lines[1:]:
            c.drawString(LEFT + 20, y, line)
            y -= LINE
    y -= 3


def table(rows: list[tuple[str, str]], col1: float = 4.0 * cm) -> None:
    global y
    for key, value in rows:
        lines1 = wrap(clean(key), 28)
        lines2 = wrap(clean(value), 76)
        row_lines = max(len(lines1), len(lines2))
        height = row_lines * LINE + 8
        ensure_space(row_lines + 2)
        c.setFillColor(colors.HexColor("#f8fafb"))
        c.rect(LEFT, y - height + 7, RIGHT - LEFT, height, fill=1, stroke=0)
        c.setStrokeColor(colors.HexColor("#d8dee5"))
        c.setLineWidth(0.6)
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


def callout(title: str, text: str) -> None:
    global y
    lines = wrap(clean(text), 90)
    height = (len(lines) + 1) * LINE + 16
    ensure_space(len(lines) + 3)
    c.setFillColor(colors.HexColor("#edf7f7"))
    c.roundRect(LEFT, y - height + 7, RIGHT - LEFT, height, 7, fill=1, stroke=0)
    c.setFillColor(colors.HexColor("#0b6f71"))
    c.setFont("Helvetica-Bold", 9.4)
    c.drawString(LEFT + 10, y, title)
    yy = y - LINE
    c.setFillColor(colors.HexColor("#243441"))
    c.setFont("Helvetica", 8.9)
    for line in lines:
        c.drawString(LEFT + 10, yy, line)
        yy -= LINE
    y -= height + 4


def build() -> None:
    global y
    new_page()
    c.setFillColor(colors.HexColor("#17212b"))
    c.setFont("Helvetica-Bold", 25)
    c.drawCentredString(W / 2, H - 4.4 * cm, "Manual de Uso")
    c.setFont("Helvetica-Bold", 17)
    c.setFillColor(colors.HexColor("#0f8b8d"))
    c.drawCentredString(W / 2, H - 5.25 * cm, "P&Pmis Ai SaaS")
    c.setFont("Helvetica", 11.2)
    c.setFillColor(colors.HexColor("#52616f"))
    c.drawCentredString(W / 2, H - 6.0 * cm, "Project Controls basado en AACE TCM")
    c.drawCentredString(W / 2, H - 6.6 * cm, "Version local de demostracion - localhost:5173")
    c.drawCentredString(W / 2, H - 7.2 * cm, "Fecha de corte: 2026-05-05")

    y = H - 9.1 * cm
    callout(
        "Idea operativa",
        "La aplicacion no inicia desde tareas manuales. El disparador del flujo es la carga del cronograma "
        "fuente. Desde ahi el sistema valida datos, abre el Business Process, enruta responsables y alimenta "
        "el Control Core.",
    )
    table(
        [
            ("Entrada maestra", "Cronograma fuente en XER o XML validado antes de Planeacion."),
            ("Flujo obligatorio", "Planeacion -> Cuentas de Control -> Ejecucion -> Control Core -> Decision -> Retroalimentacion."),
            ("Loop de control", "Capturar -> Validar -> Analizar -> Alertar -> Decidir -> Actuar -> Repetir."),
            ("URL de uso", "http://localhost:5173"),
        ],
        col1=4.5 * cm,
    )

    new_page("1. Para Quien Es Este Manual")
    para(
        "Este manual esta dirigido a Project Controls Managers, planificadores, control de costos, "
        "administradores contractuales, responsables de avance, control documental y gerencia de proyecto."
    )
    heading("Objetivo")
    para(
        "Explicar como usar la aplicacion local para iniciar un flujo de control desde el cronograma, "
        "leer el dashboard, revisar el workflow, interpretar indicadores EVM y dar seguimiento a decisiones."
    )
    heading("Concepto base")
    para(
        "P&Pmis Ai SaaS se comporta como una consola integrada de Project Controls. El cronograma es la "
        "estructura temporal que conecta actividades, cuentas de control, progreso, costos, cambios, reclamos "
        "y documentos. Por eso la carga del cronograma aparece primero en la pantalla."
    )
    heading("Roles sugeridos")
    table(
        [
            ("Planner", "Carga cronogramas, valida logica, fechas, baseline y actividades."),
            ("Controls Engineer", "Revisa calidad de datos, cuentas de control, avance y consistencia."),
            ("Cost Controller", "Carga o valida costos reales, compromisos y forecast."),
            ("Contract Manager", "Revisa eventos contractuales, comunicaciones y soporte para reclamos."),
            ("Control Manager", "Aprueba baseline, decide acciones y gobierna el flujo."),
            ("Execution Lead", "Ejecuta acciones correctivas y retroalimenta el ciclo."),
        ],
        col1=4.2 * cm,
    )

    new_page("2. Acceso Y Pantalla Principal")
    heading("Como abrir la aplicacion")
    numbered(
        [
            "Verifique que Docker este levantado con docker compose up -d --build.",
            "Abra el navegador en http://localhost:5173.",
            "Espere a que cargue el Proyecto Demo - Control Integrado TCM.",
            "Si la pantalla conserva datos anteriores despues de una actualizacion, use Ctrl + F5.",
        ]
    )
    heading("Orden de lectura del dashboard")
    numbered(
        [
            "Encabezado del proyecto: muestra nombre, codigo, fase y estado SPI/CPI.",
            "Schedule Intake Gate: primer bloque operativo. Desde aqui se carga el cronograma fuente.",
            "Control Summary: fecha de control, baseline, alertas abiertas y variacion forecast.",
            "Flujo TCM: muestra el estado Planeacion, Cuentas de Control, Ejecucion, Control Core, Decision y Retroalimentacion.",
            "Business Processes y Workflow Routing: muestra el BP creado por la carga del cronograma y su ball-in-court.",
            "KPIs, S-Curve, alertas, cambios, reclamos, documentos, configuracion de procesos y auditoria.",
        ]
    )
    callout(
        "Regla de uso",
        "Si no hay cronograma cargado, el resto del sistema debe considerarse pendiente. El dashboard puede mostrar "
        "datos demo, pero el flujo real debe iniciar con Schedule Intake Gate.",
    )

    new_page("3. Cargar El Cronograma")
    heading("Formatos recomendados")
    table(
        [
            ("XER", "Formato recomendado para cronogramas Primavera P6 exportados como XER."),
            ("XML", "Formato recomendado para cronogramas exportados desde herramientas de planificacion."),
            ("MPP", "El archivo binario MPP se reconoce, pero la lectura profunda de actividades requiere exportarlo a XML o incorporar un parser especializado."),
        ],
        col1=3.2 * cm,
    )
    heading("Paso a paso")
    numbered(
        [
            "En la parte superior del dashboard ubique Schedule Intake Gate.",
            "Pulse Upload Schedule.",
            "Seleccione el archivo del cronograma fuente, preferiblemente .xer o .xml.",
            "Espere a que el sistema procese el archivo.",
            "Revise Source, Baseline, Data Date, Quality y Activities / Logic.",
            "Verifique el mensaje de validacion, por ejemplo actividades importadas, relaciones logicas y actividades sin fechas.",
        ]
    )
    heading("Que ocurre despues de cargar")
    bullet(
        [
            "Se crea un registro ScheduleImport.",
            "Se extraen actividades y relaciones logicas cuando el formato lo permite.",
            "Se calcula un score de calidad.",
            "Se abre un Business Process Schedule Intake.",
            "Se genera un record number tipo SCH-00002.",
            "El workflow entra a Data Quality, Impact Review o Approval segun el estado.",
        ]
    )

    new_page("4. Entender El Workflow")
    para(
        "El workflow esta inspirado en patrones tipo Unifier: cada registro tiene proceso, numero, titulo, estado, "
        "paso actual y ball-in-court. El objetivo es que cada decision tenga un responsable visible y trazabilidad."
    )
    heading("Pasos del Schedule Intake")
    table(
        [
            ("Creation", "Recepcion del cronograma fuente."),
            ("Data Quality", "Validacion de calendario, logica, baseline y mapeo de actividades."),
            ("Impact Review", "Analisis de impacto en plazo, costo, progreso y exposicion contractual."),
            ("Approval", "Decision del Control Manager sobre la aceptacion del baseline."),
            ("Action", "Forecast, lookahead, comunicaciones y actualizacion de auditoria."),
        ],
        col1=3.8 * cm,
    )
    heading("Como usar los botones")
    table(
        [
            ("Route to Approval", "Mueve el BP desde Impact Review hacia Approval."),
            ("Approve Baseline", "Aprueba el baseline y deja el flujo listo para accion/cierre."),
            ("Reject", "Rechaza la version cargada y obliga a corregir el cronograma."),
            ("Close Action", "Cierra el ciclo de accion cuando la decision fue ejecutada."),
        ],
        col1=4.0 * cm,
    )
    callout(
        "Ball in Court",
        "Ball in Court indica quien debe actuar ahora. No es solo una etiqueta: en una version productiva debe gobernar "
        "notificaciones, permisos, tiempos de respuesta y auditoria.",
    )

    new_page("5. Leer El Control Core")
    heading("KPIs principales")
    table(
        [
            ("PV", "Planned Value. Valor planificado a la fecha de control."),
            ("EV", "Earned Value. Valor ganado por avance fisico reconocido."),
            ("AC", "Actual Cost. Costo real registrado."),
            ("SPI", "Schedule Performance Index. Menor que 0.90 indica alerta de plazo."),
            ("CPI", "Cost Performance Index. Menor que 0.90 indica alerta de costo."),
            ("EAC", "Estimate at Completion. Proyeccion del costo total al cierre."),
            ("VAC", "Variance at Completion. Diferencia entre presupuesto y EAC."),
        ],
        col1=2.6 * cm,
    )
    heading("Como interpretar semaforos")
    bullet(
        [
            "Rojo: desviacion critica o umbral incumplido. Requiere decision.",
            "Ambar: desviacion preventiva. Requiere seguimiento y causa probable.",
            "Verde: indicador dentro de rango. Mantener monitoreo.",
        ]
    )
    heading("S-Curve")
    para(
        "La S-Curve compara PV, EV y AC. Si EV queda por debajo de PV, hay atraso de avance. Si AC queda por encima "
        "de EV, existe sobrecosto o baja productividad. El usuario debe revisar la causa en alertas, cambios, reclamos "
        "y documentos vinculados."
    )

    new_page("6. Alertas, Cambios Y Reclamos")
    heading("Early Warning")
    para(
        "El sistema aplica el flujo Identify -> Monitor -> Analyze -> Alert -> Act. Las reglas actuales detectan "
        "SPI bajo, CPI bajo y estado dentro de umbrales. Cada alerta debe tener causa probable, recomendacion y estado."
    )
    heading("Change Management")
    numbered(
        [
            "Identifique la desviacion en el dashboard o en el BP Log.",
            "Revise impacto tecnico, costo y plazo.",
            "Clasifique si requiere aprobacion contractual.",
            "Vincule documentos de soporte.",
            "Apruebe, rechace o deje en seguimiento.",
            "Retroalimente forecast, baseline o cuenta de control segun corresponda.",
        ]
    )
    heading("Claims / Forensic")
    numbered(
        [
            "Registre el evento y fecha de ocurrencia.",
            "Vincule correspondencia, reportes de campo y evidencia.",
            "Analice causalidad e impacto.",
            "Cuantifique plazo, costo o productividad.",
            "Defina posicion contractual.",
            "Mantenga trazabilidad hasta cierre o reclamacion formal.",
        ]
    )

    new_page("7. Documentos, Setup Y Auditoria")
    heading("Document Control")
    para(
        "Los documentos deben estar vinculados a entidades de control: cronograma, actividad, cuenta de control, cambio, "
        "reclamo, evento o BP. La regla es simple: ninguna decision importante debe quedar sin soporte documental."
    )
    heading("BP Setup / uDesigner")
    para(
        "La seccion BP Setup / uDesigner muestra procesos configurados, formularios, pasos, roles y estado. En esta "
        "version sirve como vista de diseno funcional. En una version productiva debe permitir configurar procesos, "
        "campos, reglas, permisos y rutas de aprobacion."
    )
    heading("Audit Trail")
    para(
        "La auditoria registra acciones relevantes como importacion de cronograma, ruteo, aprobacion, rechazo y cierre. "
        "Debe usarse para explicar quien hizo que, cuando lo hizo y sobre que registro."
    )
    heading("Buenas practicas")
    bullet(
        [
            "Cargue siempre una version controlada del cronograma.",
            "Use nombres de archivo con codigo de proyecto, fecha y version.",
            "Revise el quality score antes de aprobar.",
            "No apruebe baseline con actividades sin fechas o logica insuficiente.",
            "Vincule documentos antes de decisiones contractuales.",
            "Cierre acciones solo cuando exista evidencia de ejecucion.",
        ]
    )

    new_page("8. Solucion De Problemas")
    table(
        [
            ("No carga la app", "Verifique que frontend este arriba en Docker y abra http://localhost:5173."),
            ("No responde API", "Revise http://localhost:8000/docs y los logs de docker compose logs api."),
            ("El cronograma no importa actividades", "Use XER o XML y revise que el archivo incluya WBS, actividades, fechas y relaciones."),
            ("Quality sale bajo", "Revise actividades sin fechas, relaciones abiertas, baseline incompleto y logica faltante."),
            ("Veo datos anteriores", "Actualice con Ctrl + F5 o pulse el boton de refresh del dashboard."),
            ("El BP queda rechazado", "Corrija el archivo fuente y cargue una nueva version desde Schedule Intake Gate."),
        ],
        col1=4.0 * cm,
    )
    heading("Comandos utiles")
    bullet(
        [
            "Levantar plataforma: docker compose up -d --build",
            "Ver servicios: docker compose ps",
            "Logs API: docker compose logs --tail=80 api",
            "Logs frontend: docker compose logs --tail=80 frontend",
            "Abrir API: http://localhost:8000/docs",
        ]
    )

    new_page("9. Cierre Operativo")
    para(
        "La forma correcta de usar P&Pmis Ai SaaS es comenzar cada ciclo con un cronograma fuente, validar su calidad, "
        "enrutar la decision y dejar que el Control Core conecte avance, costo, documentos, cambios, reclamos y alertas. "
        "El valor del sistema no esta en mostrar indicadores aislados, sino en convertir datos en decisiones y decisiones "
        "en accion temprana."
    )
    callout(
        "Principio final",
        "Cronograma -> Workflow -> Control Core -> Decision -> Accion -> Retroalimentacion. Ese es el sistema nervioso "
        "de control que la plataforma debe proteger.",
    )


build()
footer()
c.save()

reader = PdfReader(str(OUT))
print(f"created={OUT}")
print(f"pages={len(reader.pages)}")
print(f"bytes={OUT.stat().st_size}")
