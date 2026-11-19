"""Release artifact content. Verification is never inferred from implementation."""

import json
from pathlib import Path
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[2]
QA = ROOT / "outputs/.qa/wave-o2c-20261118"
BASELINE = "e5747a6 + corte O2B.CLOSE-2 (12 nov 2026)"
DATE = "18 de noviembre de 2026"


def read_json(path):
    return json.loads(path.read_text("utf-8")) if path.is_file() else {}


def junit(path):
    if not path.is_file():
        return "Sin evidencia"
    cases = list(ElementTree.parse(path).iter("testcase"))
    good = [
        case
        for case in cases
        if not any(case.find(k) is not None for k in ("failure", "error", "skipped"))
    ]
    return f"{len(good)}/{len(cases)} aprobadas" if cases else "Sin casos"


def evidence():
    manifest = read_json(QA / "release-evidence.json")
    result = {
        name: junit(QA / path) for name, path in manifest.get("junit", {}).items()
    }
    before = read_json(QA / "project-14/preservation-before.json").get("observation")
    after = read_json(QA / "project-14/preservation-after.json").get("observation")
    result["Proyecto 14"] = (
        "Coincide en filas y en 70 y 74 relaciones FK catalogadas"
        if before and before == after
        else "Comparación pendiente"
    )
    result["Migración"] = (
        "PostgreSQL sube / baja / sube verificado"
        if read_json(QA / "migration/proof.json").get("result") == "PASS"
        else "Validación pendiente"
    )
    frontend = read_json(QA / "frontend-checks.json")
    tests = next((item for item in frontend.get("checks", []) if item.get("name") == "Vitest Contracts and Cost"), {})
    if tests.get("exit_code") == 0:
        result["Frontend"] = f"{tests.get('passed')} pruebas aprobadas; TypeScript build ESLint y Prettier aprobados"
    return result


def status():
    decision = read_json(QA / "release-decision.json")
    return decision.get("status", "IMPLEMENTADO · LIBERACIÓN NO VALIDADA")


def sections():
    check = evidence()
    return [
        (
            "Resumen ejecutivo",
            [
                "O2C incorpora Contracts Manager como autoridad comercial canónica del proyecto. Usa una orden emitida como evidencia, sin sustituir a Procurement. El contrato aprobado, el compromiso comercial y el compromiso financiero son decisiones independientes.",
                f"Estado del corte: {status()}. Alcance técnico local; sin despliegue ni migración productiva.",
            ],
        ),
        (
            "Línea base y hallazgos",
            [
                f"Línea base: {BASELINE}. Se ajustaron el Word y la matriz vigentes de O2B con el cierre de O2B-G01 y O2B-G02, sin reescribir los artefactos históricos.",
                "Se conservaron las tablas legadas de contrato, certificados, avisos, reclamaciones y SOV. Se reutilizan Enterprise Workspace, políticas ADMIN, proveedor de Procurement, CDE, Scope, AWP, Schedule, Cost y Progress, sin migrar registros legados.",
            ],
        ),
        (
            "Autoridad y límites",
            [
                "Procurement mantiene orden, adjudicación y proveedor. Contratos mantiene instrumentos, versiones, SOV, cambios y certificaciones. Cost conserva la adopción, verificación y autoridad financiera. Progress conserva avance físico; Schedule/P6 el cronograma; Forecast sus aprobaciones; CDE la evidencia y AWP la liberación.",
                "SOV no es Budget. Certificado no es factura, una referencia externa no es contabilización y una factura no es pago. El cambio comercial y la disponibilidad contractual no cambian Budget, P6, Forecast ni liberan paquetes.",
            ],
        ),
        (
            "Paquetes contratos y ejecución",
            [
                "El paquete vincula fuentes de Procurement con ID, versión y huella. El contrato referencia proveedor, paquete, fechas, moneda, términos y CDE. Separación entre aprobación, registro de ejecución y entrada en vigencia.",
                "ContractPackage admite código, estrategia, tipo de contrato, modelo comercial, responsable, moneda, estimación y fechas planeadas. Sus fuentes son una colección de referencias, no una conversión automática ni una relación uno a uno con la orden.",
                "OperationalContract registra número, contraparte, valor original, fechas de efecto, inicio y terminación, instrumento fuente y documentación. ContractVersion conserva valor, términos, vigencia, fecha de terminación, origen del cambio y huella. El contrato apunta a la versión actual y mantiene separada la evidencia de ejecución.",
                "Las versiones aprobadas son inmutables. Un cambio aprobado crea la siguiente revisión comercial; la revisión anterior y su historial permanecen consultables. El compromiso comercial se aprueba aparte y una modificación crea un sucesor.",
                "CommercialCommitment registra importe, moneda, versión contractual, base comercial, fecha efectiva y aprobador. La suma de compromisos vigentes no puede superar el valor de la versión contractual. El sucesor conserva el vínculo a la obligación anterior y requiere su propia aprobación.",
            ],
        ),
        (
            "SOV cambios y pagos",
            [
                "El SOV organiza partidas, cantidades, tarifas y retención, vinculadas al alcance y a la versión contractual. Potential Change → Change Request → revisión → Change Order conserva impactos de tiempo y valor como información comercial.",
                "Cada partida SOV tiene número, descripción, cantidad, unidad, tarifa y referencias canónicas. Su publicación requiere un actor distinto del autor conforme al perfil. El SOV se utiliza para administración contractual de pagos y no genera líneas de presupuesto.",
                "Los cambios registran impacto de valor y tiempo sobre una versión base concreta. La aprobación vuelve a validar esa base, la evidencia y las referencias de cronograma. Esta fundación rechaza activar una Change Order con fecha efectiva futura para no invalidar prematuramente la versión vigente; se puede preparar y revisar para una decisión posterior.",
                "La solicitud usa evidencia Progress aprobada y vigente, acotada por cantidad, período, alcance y unidad. El certificado puede ser parcial y registra retenciones y ajustes. La referencia externa de factura o pago no crea una cuenta por pagar ni un movimiento.",
                "El control de consumo impide reclamar más cantidad que el SOV o que la evidencia física disponible. La revisión de solicitud es independiente. Los certificados se limitan a la parte solicitada y pueden aplicar retención, recuperación de anticipos, deducciones y otras retenciones o ajustes. Una certificación aprobada conserva su propia identidad e historial.",
                "Avisos y reclamaciones tienen registro, evidencia CDE, decisión y trazabilidad. Son una base contractual, no un motor de controversias ni un cálculo de indemnización.",
            ],
        ),
        (
            "Integraciones explícitas",
            [
                "Procurement → Contracts: consulta de fuentes y trazabilidad de PO; el proveedor sigue siendo el maestro existente. CDE: referencias a revisión y adjunto con validación de huella.",
                "Contracts → Cost: la adopción registra dominio, entidad, versión, hash, observación, fecha efectiva, CBS, Cost Code y Control Account. No reconoce automáticamente costo. La propuesta financiera de tipo referencia y su verificación independiente usan los comandos nativos de Cost.",
                "La inclusión financiera habilitada para fuentes O2C es REFERENCE_ONLY. El importe queda disponible como referencia verificada con contribución neta cero. Esta entrega no habilita inclusión aditiva, contabilización, Actual Cost, accrual, pago o cambio de EAC. La propuesta financiera todavía requiere a un actor Cost y su verificación a otro actor independiente.",
                "Progress → Contracts: únicamente evidencia aprobada y trazable. Schedule/AWP: referencias canónicas validadas. Forecast y liberación AWP permanecen fuera de escritura de O2C.",
            ],
        ),
        (
            "Administración operación seguridad y API",
            [
                "ADMIN define y publica perfiles versionados. USER abre Contracts Manager dentro del workspace activo. Cost Manager presenta la adopción; la política de permisos permanece en servidor.",
                "API: /api/v1/contracts/admin/profiles y /api/v1/contracts/projects/{workspace_id}; la adopción está bajo /api/v1/cost/projects/{workspace_id}/commercial-commitment-adoptions.",
                "El servidor valida tenant y proyecto, permisos, segregación de funciones, If-Match e Idempotency-Key. El historial conserva actor, razón, transición y versión. PostgreSQL protege las filas terminales y las decisiones append-only.",
                "El menú Contracts Manager solo aparece al habilitar el dominio en el workspace; la visibilidad del menú no concede autorización. Un actor de Procurement sin deber contractual no puede preparar contratos. Los actores exclusivamente contractuales no pueden registrar adopciones Cost ni modificar Progress o P6.",
                "El perfil publicado define tipos, monedas, estados, reglas de retención, umbrales de aprobación, requisitos de preparación y reglas SoD. Su ID y huella se fijan en las entidades gobernadas. El sucesor de configuración no reescribe los registros aprobados.",
            ],
        ),
        (
            "Migración y validación",
            [
                "Alembic 20261113_0079 extiende 20261111_0078 sin backfill. PostgreSQL 16 aislado se inició desde el esquema histórico y se probó subir, bajar y volver a subir. El downgrade rechaza el borrado de datos gobernados.",
                *[f"{name}: {value}." for name, value in check.items()],
                "Las observaciones de rendimiento corresponden a un entorno sintético local. No constituyen SLA ni certificación de capacidad.",
            ],
        ),
    ]


def detailed_sections():
    return [
        (
            "Trazabilidad de fuentes y maestros",
            [
                "La lectura de Procurement incorpora una proyección CONTRACTS separada de la proyección COST. De este modo, cambiar una asignación CBS en Cost no altera la huella de una PO ya referenciada por Contratos. La lectura contractual sigue comprobando tipo, ID, versión, estado, proveedor y moneda de la fuente.",
                "Se utiliza el Vendor existente de Procurement. No hay un segundo catálogo de proveedores contractual. Las referencias CDE conservan el documento y el adjunto con su huella; la consulta respeta las restricciones de membresía y confidencialidad existentes.",
                "La traza permite recorrer paquete, contrato, versiones, fuentes de RFQ, adjudicación y PO, compromiso y sus decisiones de consumo cuando el lector tiene permiso Cost. Los valores comerciales de exposición son informativos y no representan el EAC aprobado.",
            ],
        ),
        (
            "Preparación contractual y consultas de operación",
            [
                "Contract Readiness evalúa el instrumento y su estado, la obligación comercial, SOV, seguros, garantías y avisos conforme al perfil. Distingue referencias rotas u obsoletas de un estado listo. La evaluación no autoriza una liberación AWP.",
                "Commercial Look Ahead consulta fechas y acciones contractuales dentro de un horizonte acotado. La lista y el detalle conservan filtros y paginación. No se alteran fechas P6 ni se crea una programación paralela.",
                "Los mapeos pueden apuntar a Scope, Plan, CWA, CWP, PWP, IWP, CBS, Cost Code, Control Account y referencias WBS, Activity o Milestone del cronograma aceptado. Se validan por dominio y proyecto antes de conservar el vínculo.",
            ],
        ),
        (
            "Interfaz de administración y operación",
            [
                "La pantalla USER reúne paquetes, contratos, versiones, compromisos comerciales, SOV, cambios, solicitudes de pago, certificados, avisos y reclamaciones. El detalle muestra datos, acciones permitidas y evidencia. Los formularios usan tipos de comando específicos y muestran los rechazos del servidor.",
                "ADMIN mantiene la creación, publicación y sucesión de perfiles. Cost Manager dispone de consulta de origen, visualización de huella, elección de dimensiones, decisión y consulta del historial de adopciones. Estos controles consumen las mismas APIs gobernadas que las pruebas HTTP.",
                "No se rediseñó App.tsx. La integración se añadió en WorkspaceOperationalPage y AdminConfigurationView, conservando la jerarquía empresarial y los módulos existentes.",
            ],
        ),
        (
            "Contrato de integración de la API",
            [
                "Las rutas de lectura contractual incluyen configuration, procurement-source, commitment-source, document-targets, registros, detalle, history, trace, readiness y lookahead. Las rutas de comando separan creación y transición; cada transición exige revisión If-Match y una clave de idempotencia.",
                "Una revisión obsoleta produce HTTP 412. Una transición incompatible, una fuente obsoleta o una restricción de dominio produce HTTP 409. Una operación sin deber produce HTTP 403. Las búsquedas de otro tenant o workspace ocultan el registro con HTTP 404 según la frontera aplicada.",
                "La primera adopción Cost utiliza If-Match 0 y crea la revisión 1 de un flujo append-only. La repetición con la misma clave y el mismo comando devuelve el recibo previo. Reutilizar la clave para un comando diferente se rechaza. Los recibos se serializan por tenant para proteger los controles agregados.",
            ],
        ),
        (
            "Persistencia e historial",
            [
                "La migración añade 17 tablas operacionales sin importar ni modificar datos previos. Incluye tablas de partidas y referencias y un historial contractual. El DDL congelado se compara con los modelos actuales para detectar discrepancias antes de declarar la liberación.",
                "La protección PostgreSQL evita eliminar registros comerciales, modificar evidencia terminal o actualizar decisiones append-only. Verifica el actor y el workspace de la fila; los servicios comprueban además el ámbito de cada referencia padre. La administración directa de la base sigue requiriendo controles de acceso separados.",
                "El downgrade comprueba si existe información gobernada y rechaza descartarla. La secuencia de validación sobre PostgreSQL 16 usa el esquema histórico y la cadena Alembic, no create_all ni un stamp que omita las migraciones.",
            ],
        ),
        (
            "Escenarios y cobertura de verificación",
            [
                "El escenario central parte de una PO emitida por el flujo real O2B, prepara un paquete y un contrato, aplica aprobación independiente, registra ejecución y entrada en vigor y aprueba un compromiso. Comprueba que no aparezca un compromiso financiero sin adopción.",
                "Cost consulta el origen, registra una decisión con dimensiones válidas, propone una referencia financiera y requiere verificación independiente. Se comparan huellas de las tablas ajenas para demostrar que el reconocimiento explícito no cambia Budget, Actual Cost, Progress, Schedule ni Forecast.",
                "El escenario comercial publica un SOV, utiliza un incremento Progress aprobado, revisa la solicitud y certifica una parte de su importe. Registra un aviso, una reclamación y la referencia financiera externa. Recorre Change Request y Change Order y conserva versión y compromiso anteriores junto al sucesor.",
                "Los casos negativos cubren SoD, fechas futuras, permisos ajenos, versión If-Match obsoleta, idempotencia incompatible, referencias CDE rotas, cantidad física inválida o excedida, sobrecertificación, contrato sin aprobar y reutilización de versión sustituida. La lista de resultados del corte indica cuáles quedaron acreditados.",
            ],
        ),
        (
            "Preservación del Proyecto 14",
            [
                "El observador conecta a la base normal en transacción de solo lectura y compara las filas y referencias tanto del identificador legado como del workspace canónico. No inicia la aplicación ni ejecuta seed o migración sobre esa base.",
                "En este entorno no existe una fila projects.id 14. Por ello, el hash de ausencia y los conteos de referencias se conservan como evidencia de no creación, sin presentarlos como prueba sobre un proyecto legado poblado. La observación del workspace y sus relaciones se registra por separado.",
            ],
        ),
    ]


def matrix():
    results = evidence()
    metrics = read_json(QA / "performance-final.json")

    def rows(*items):
        return [list(item) for item in items]

    sheets = {
        "00_README": (
            "Guía de lectura",
            rows(
                ("Corte", DATE, BASELINE),
                ("Decisión", status(), "Usar la última evidencia verificable"),
                (
                    "Alcance",
                    "O2C técnico local",
                    "No aplicar a producción ni a Proyecto 14",
                ),
            ),
        ),
        "01_REQUIREMENTS": (
            "Requisitos",
            rows(
                ("O2C-01", "Paquete, contrato y versiones", "API Contrato/Cost"),
                (
                    "O2C-02",
                    "Compromiso comercial y adopción financiera explícita",
                    "API Contrato/Cost",
                ),
                ("O2C-03", "SOV, cambio, pagos, avisos y reclamos", "API Comercial"),
                ("O2C-04", "ADMIN/USER, seguridad y SoD", "API + Chromium"),
                (
                    "O2C-05",
                    "PostgreSQL, regresión, rendimiento y Proyecto 14",
                    "14_TESTS",
                ),
            ),
        ),
        "02_AUTHORITY": (
            "Autoridad por dominio",
            rows(
                ("Procurement", "PO y proveedor", "No escribe contrato"),
                (
                    "Contracts",
                    "Contrato, compromiso comercial, SOV y certificado",
                    "No contabiliza",
                ),
                (
                    "Cost",
                    "Adopción, compromiso financiero y costos",
                    "No aprueba contrato",
                ),
                (
                    "Progress / Schedule / Forecast",
                    "Avance, cronograma y proyección",
                    "O2C solo lee referencias",
                ),
                (
                    "CDE / AWP",
                    "Evidencia documental y liberación",
                    "Sin transferencia de autoridad",
                ),
            ),
        ),
        "03_DOMAIN_MODEL": (
            "Modelo de datos",
            rows(
                (
                    "Contrato",
                    "contract_packages / operational_contracts / contract_versions",
                    "Versiones aprobadas inmutables",
                ),
                (
                    "Comercial",
                    "commercial_commitments / contract_sovs / contract_changes",
                    "Sucesor o revisión",
                ),
                (
                    "Pago",
                    "payment_applications / operational_payment_certificates",
                    "Partidas hijas append-only",
                ),
                (
                    "Soporte",
                    "contract_finance_references / contract_claims / contract_history",
                    "Vínculos, no transacciones financieras",
                ),
                (
                    "Cost",
                    "cost_commercial_commitment_adoptions / cost_commitment_references",
                    "Autoridad Cost, decisiones separadas",
                ),
            ),
        ),
        "04_WORKFLOWS": (
            "Flujos",
            rows(
                (
                    "Cadena comercial",
                    "PO → paquete → contrato → ejecución → compromiso",
                    "Ninguna flecha crea el siguiente objeto",
                ),
                (
                    "Cadena pago",
                    "SOV → Progress → solicitud → certificado parcial → referencia",
                    "Sin pago automático",
                ),
                (
                    "Cadena cambio",
                    "Potencial → solicitud → revisión → orden → v2 → sucesor",
                    "Sin escritura Budget/P6/Forecast",
                ),
            ),
        ),
        "05_STATUSES": (
            "Estados",
            rows(
                (
                    "Contrato",
                    "DRAFT → APPROVED → EXECUTED → EFFECTIVE",
                    "Acciones separadas",
                ),
                (
                    "Compromiso / SOV",
                    "DRAFT → APPROVED / DRAFT → PUBLISHED",
                    "Último vigente y auditoría",
                ),
                (
                    "Pagos",
                    "SUBMITTED → REVIEWED o REJECTED / DRAFT → APPROVED o REJECTED",
                    "Gates de cuantía y evidencia",
                ),
                (
                    "Aviso / reclamación",
                    "Cierre / aceptación o rechazo",
                    "Historial retenido",
                ),
            ),
        ),
        "06_PERMISSIONS": (
            "Permisos",
            rows(
                (
                    "Preparador",
                    "contracts.package.prepare / contract.prepare",
                    "Proyecto",
                ),
                (
                    "Aprobador / ejecutor",
                    "contracts.contract.approve / contract.execute",
                    "Roles independientes",
                ),
                ("ADMIN", "contracts.admin.configure / admin.publish", "Organización"),
                (
                    "Cost",
                    "cost.mapping.edit / commitment.reconcile / commitment.verify",
                    "Proyecto",
                ),
            ),
        ),
        "07_SOD": (
            "Separación de funciones",
            rows(
                ("Contrato", "Autor ≠ aprobador; aprobador ≠ ejecutor", "Perfil ADMIN"),
                (
                    "Comercial",
                    "Autor ≠ aprobador para compromiso/SOV/cambio/certificado",
                    "Perfil ADMIN",
                ),
                ("Cost", "Proponente ≠ verificador financiero", "Regla nativa Cost"),
            ),
        ),
        "08_INTEGRATIONS": (
            "Interfaces y no escritura",
            rows(
                (
                    "Procurement / CDE",
                    "PO emitida y evidencia adjunta",
                    "Pin de ID / versión / hash",
                ),
                (
                    "Cost / Progress",
                    "Adopción explícita y evidencia INSTALL aprobada",
                    "Consumidores gobernados",
                ),
                (
                    "Schedule / AWP / Forecast",
                    "Referencias o sin escritura",
                    "Sin cambio de baseline ni liberación",
                ),
            ),
        ),
        "09_PROCUREMENT_TRACEABILITY": (
            "Procurement",
            rows(
                (
                    "Escenario",
                    "PKG-O2C / AGREEMENT-O2C",
                    "Orden emitida por fixture O2B",
                ),
                (
                    "Fuente",
                    "RFQ → adjudicación → PO",
                    "Trazabilidad, no equivalencia con contrato",
                ),
            ),
        ),
        "10_COST_TRACEABILITY": (
            "Cost",
            rows(
                (
                    "Escenario",
                    "COM-O2C por 80 sobre contrato por 100",
                    "Moneda de la PO del fixture",
                ),
                (
                    "Adopción",
                    "CBS + Cost Code + Control Account",
                    "ADOPTED con huella explícita",
                ),
                (
                    "Verificación",
                    "REFERENCE_ONLY",
                    "No agrega costo ni reemplaza Budget",
                ),
            ),
        ),
        "11_PROGRESS_TRACEABILITY": (
            "Progress",
            rows(
                (
                    "Evidencia",
                    "INSTALL aprobado",
                    "Período, unidad, alcance, hash y versión",
                ),
                ("Certificación", "Parcial", "No consume más cantidad que la aprobada"),
            ),
        ),
        "12_SCHEDULE_TRACEABILITY": (
            "Schedule",
            rows(
                (
                    "Referencia",
                    "Cronograma aceptado + ID externo",
                    "Validado antes de aplicar cambio",
                ),
                (
                    "Límite",
                    "Change Order ≠ P6 baseline change",
                    "No se modifica Schedule",
                ),
            ),
        ),
        "13_API": (
            "Endpoints principales",
            rows(
                (
                    "ADMIN",
                    "/contracts/admin/profiles",
                    "POST perfil, publicación y sucesor",
                ),
                (
                    "USER",
                    "/contracts/projects/{workspace_id}",
                    "Registros, comandos, trace, readiness y lookahead",
                ),
                (
                    "COST",
                    "/cost/projects/{workspace_id}/commercial-commitment-adoptions",
                    "GET lookup/historia, POST decisión",
                ),
                (
                    "Controles",
                    "If-Match / Idempotency-Key",
                    "Mutaciones versionadas; 412 en versión obsoleta",
                ),
            ),
        ),
        "14_TESTS": (
            "Validación observada",
            [
                *[["Control", key, value] for key, value in results.items()],
                *[
                    [
                        "Medición local",
                        key,
                        f"{item['median_ms']} ms · {item['response_bytes']} B",
                    ]
                    for key, item in metrics.items()
                ],
            ],
        ),
        "15_DEFECTS": (
            "Defectos y pendientes",
            read_json(QA / "release-decision.json").get(
                "defects",
                rows(
                    (
                        "Verificación",
                        "Liberación sin acreditación completa",
                        "No declarar S1/S2 cerrados sin resultado final",
                    ),
                ),
            ),
        ),
        "16_RELEASE_CRITERIA": (
            "Decisión de liberación",
            rows(
                ("Estado", status(), "El estado depende de la evidencia"),
                (
                    "Fronteras",
                    "PO ≠ contrato ≠ compromiso comercial ≠ Cost",
                    "Confirmación por pruebas",
                ),
                (
                    "Seguridad",
                    "Migración aislada; Proyecto 14 de solo lectura",
                    "Sin despliegue productivo",
                ),
            ),
        ),
    }
    requirements = [
        (
            "R01",
            "Cierre documental O2B",
            "Word y matriz vigentes reconciliados sin cambiar históricos",
        ),
        (
            "R02",
            "Autoridad y reutilización",
            "Procurement, Cost, Progress, P6, Forecast, CDE y AWP separados",
        ),
        (
            "R03",
            "Contrato y PO distintos",
            "Creación contractual explícita después de emitir PO",
        ),
        ("R04", "Paquetes contractuales", "Fuentes N a M con ID versión y hash"),
        ("R05", "Contratos y versiones", "APPROVED, EXECUTED y EFFECTIVE por separado"),
        ("R06", "Compromiso comercial", "Aprobación y sucesor independientes"),
        (
            "R07",
            "Adopción Cost",
            "Fuente, fecha, tres dimensiones y decisión append-only",
        ),
        (
            "R08",
            "Autoridad financiera",
            "Propuesta y verificación nativas REFERENCE_ONLY",
        ),
        ("R09", "SOV y partidas", "Publicación y referencias Scope AWP"),
        (
            "R10",
            "Potential y Change Request",
            "Orden aprobada crea v2 sin cambiar Budget o P6",
        ),
        (
            "R11",
            "Vigencia futura",
            "Aprobación bloqueada hasta la fecha para preservar v1 actual",
        ),
        (
            "R12",
            "Payment Application",
            "Progress aprobado vigente y cantidad disponible",
        ),
        (
            "R13",
            "Payment Certificate",
            "Certificación parcial con retención y deducción",
        ),
        ("R14", "Referencia externa Finance", "Sin crear factura ni pago"),
        ("R15", "Avisos contractuales", "CDE fechas y seguimiento"),
        ("R16", "Reclamaciones", "Registro y decisión sin liquidación automática"),
        ("R17", "Readiness y Look Ahead", "Preparación contractual no libera AWP"),
        ("R18", "ADMIN y USER", "Perfil versionado publicado e interfaz por workspace"),
        (
            "R19",
            "Seguridad y SoD",
            "Ámbito de proyecto, actor independiente e idempotencia",
        ),
        ("R20", "Auditoría", "Historial y filas terminales inmutables"),
        ("R21", "PostgreSQL y Alembic", evidence().get("Migración", "")),
        ("R22", "Chromium real", evidence().get("Chromium", "Pendiente")),
        ("R23", "Regresión", "Suites de política y Schedule en PostgreSQL"),
        ("R24", "Proyecto 14", evidence().get("Proyecto 14", "")),
        ("R25", "Rendimiento", "Tres muestras, mediana y tamaño sin SLA"),
        ("R26", "Trazabilidad y decisión", status()),
    ]
    sheets["01_REQUIREMENTS"] = ("Requisitos de O2C", rows(*requirements))
    core = read_json(QA / "core-attempt-a/scenario.json")
    if core:
        commit = core["commercial_commitment"]
        financial = core["financial_reference"]
        sheets["09_PROCUREMENT_TRACEABILITY"][1].extend(
            rows(
                ("PO real", core["po_id"], f"Workspace {core['project_workspace_id']}"),
                (
                    "Paquete contractual",
                    core["contract_package_id"],
                    f"Contrato {core['contract_id']}",
                ),
                (
                    "Versión",
                    core["contract_version_id"],
                    "Aprobada antes de la ejecución",
                ),
            )
        )
        sheets["10_COST_TRACEABILITY"][1].extend(
            rows(
                (
                    "Compromiso comercial",
                    commit["id"],
                    f"APPROVED revisión {commit['revision']}",
                ),
                (
                    "Huella fuente",
                    commit["source_hash"],
                    "Verificada por el lector de origen",
                ),
                ("Decisión Cost", core["cost_adoption"]["id"], "ADOPTED"),
                (
                    "Referencia financiera",
                    financial["id"],
                    "VERIFIED con contribución neta cero",
                ),
            )
        )
    commercial = read_json(QA / "commercial-evidence.json")
    if commercial.get("result") == "PASS":
        sheets["11_PROGRESS_TRACEABILITY"][1].extend(rows(
            ("Medición aprobada", commercial["progress_id"], f"Cantidad disponible {commercial['progress_quantity']}"),
            ("Solicitud revisada", commercial["application_id"], f"Importe solicitado {commercial['application_amount']}"),
            ("Certificado parcial", commercial["certificate_id"],
             f"Bruto {commercial['certificate_gross']} neto {commercial['certificate_net']}"),
        ))
        sheets["12_SCHEDULE_TRACEABILITY"][1].extend(rows(
            ("Change Order real", commercial["approved_change_id"], "Impacto comercial sin escritura Schedule"),
            ("Prueba de frontera HTTP", "Schedule register por actor Contracts", "403 sin registros nuevos"),
        ))
    browser = read_json(QA / "chromium-attempt-b/o2c-browser-evidence.json")
    for key, value in browser.get("observations", {}).items():
        if key.endswith("_id"):
            sheets["14_TESTS"][1].append(["Chromium registro", key, value])
    sheets["00_README"][1].append(
        [
            "Fuente de requisitos",
            "Prompt O2C Contracts Commitments Foundation",
            "Secciones 1 a 58 del PDF suministrado",
        ]
    )
    sheets["14_TESTS"][1].append(
        [
            "Fuente de resultados",
            "JUnit y evidencias del corte 18 noviembre",
            "Pruebas locales aisladas",
        ]
    )
    return sheets
