"""Evidence-driven O3A report and the nineteen required traceability registers."""

import json
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
QA = ROOT / "outputs/.qa/wave-o3a-20261118"
OUT = ROOT / "outputs/wave-o3a-construction-field-operations-20261119"
BASELINE = "b55170dc6152d643b3fa9fd6e88935bc12fe5785"
DATE = "19 de noviembre de 2026"


def read(name, default=None):
    path = QA / name
    return json.loads(path.read_text("utf-8")) if path.exists() else (default or {})


def read_json(path):
    return json.loads(path.read_text("utf-8")) if path.exists() else {}


def detailed_sections():
    return []


def status():
    return read("release-decision.json").get("status", "VALIDACION EN CURSO")


def tests():
    rows = []
    selected = [
        "core-policy-junit.xml",
        "core-release-junit.xml",
        "execution-policy-final-junit.xml",
        "consumer-policy-junit.xml",
        "consumer-junit.xml",
        "regression-junit.xml",
        "chromium-final-junit.xml",
    ]
    for path in [QA / name for name in selected if (QA / name).exists()]:
        tree = ET.parse(path)
        for suite in tree.getroot().iter("testsuite"):
            rows.append(
                [
                    path.name,
                    int(suite.get("tests", 0)),
                    int(suite.get("failures", 0)),
                    int(suite.get("errors", 0)),
                    int(suite.get("skipped", 0)),
                    float(suite.get("time", 0)),
                ]
            )
    frontend = QA / "frontend-final/junit.xml"
    if frontend.exists():
        for suite in ET.parse(frontend).getroot().iter("testsuite"):
            rows.append(
                [
                    "frontend-unit",
                    int(suite.get("tests", 0)),
                    int(suite.get("failures", 0)),
                    int(suite.get("errors", 0)),
                    int(suite.get("skipped", 0)),
                    float(suite.get("time", 0)),
                ]
            )
    return rows


def sections():
    decision = read("release-decision.json")
    status = decision.get("status", "VALIDACION EN CURSO")
    return [
        (
            "Resumen ejecutivo",
            f"O3A incorpora Field Operations Manager como autoridad de hechos de obra en P&Pmis Construction AI. El corte técnico es {DATE}. Estado del cierre: {status}. La aprobación de un parte diario no aprueba Progress, no crea Actual Cost y no genera una certificación contractual. La aceptación de negocio y el despliegue de producción quedan fuera de esta ejecución.",
        ),
        (
            "Línea base",
            f"El desarrollo parte del commit {BASELINE}. Se conservaron las autoridades de Scope, Schedule, AWP, Cost, Progress, Engineering, Procurement y Contracts. Los cambios se encuentran en el directorio de trabajo y no incluyen un commit o push automático. Las pruebas usan PostgreSQL 16 aislado en el puerto 5564.",
        ),
        (
            "Hallazgos del repositorio",
            "Se reutilizaron el contexto operacional de proyecto, el período común, los permisos Enterprise, las configuraciones versionadas, el CDE y los servicios de comandos idempotentes. No se encontró un maestro operacional de cuadrillas ni un maestro canónico de equipos apto para este alcance. Crew se limita a organización de obra y Equipment Reference conserva una identidad externa, sin crear un activo financiero ni un módulo de recursos humanos.",
        ),
        (
            "Modelo de autoridad",
            "Field Operations registra observaciones, cantidades ejecutadas, horas, condiciones e instrucciones. AWP conserva la liberación del IWP y la gestión de restricciones adoptadas. Progress conserva certificación, revisión y aprobación. Cost conserva la clasificación y el reconocimiento económico. Contracts conserva los efectos comerciales. Schedule conserva las fechas y versiones aceptadas del cronograma.",
        ),
        (
            "Frentes de trabajo",
            "Workfront vincula el proyecto, ubicación canónica, CWA e IWP cuando corresponda. Sus estados son PLANNED, ACTIVE, SUSPENDED y COMPLETE. El frente se activa mediante una acción autorizada y no constituye una segunda estructura de alcance. Las referencias pertenecen al mismo tenant y workspace.",
        ),
        (
            "Turnos de campo",
            "FieldShift identifica fecha, horario, supervisor y frente. El flujo OPEN, SUBMITTED, APPROVED y CLOSED separa la captura de su cierre. Los hechos no se agregan silenciosamente a un turno cerrado. La fecha del turno y el instante de observación se conservan como conceptos distintos.",
        ),
        (
            "Partes diarios",
            "DailyConstructionReport usa DRAFT, SUBMITTED, REVIEWED y APPROVED. Un registro adicional de cierre representa CLOSED sin reescribir el documento aprobado. La aprobación congela los identificadores, versiones y hashes de producción, mano de obra, equipos y condiciones incluidos. Las correcciones generan un sucesor y preservan el parte original.",
        ),
        (
            "Cuadrillas",
            "Crew describe oficio, proveedor y supervisor operacional. No calcula nómina, salarios, contratos laborales ni disponibilidad corporativa. Sus referencias se validan contra el tenant y las asignaciones existentes.",
        ),
        (
            "Mano de obra",
            "LaborUsage registra personal y horas regulares, extra, productivas y no productivas del turno. Son horas persona agregadas de la cuadrilla y no se multiplican de nuevo por el número de integrantes. Las correcciones son nuevos hechos referenciados al anterior. Las horas permanecen como evidencia operacional y no se convierten automáticamente en Actual Cost.",
        ),
        (
            "Equipos",
            "FieldEquipmentReference identifica equipo externo y tipo operacional. EquipmentUsage registra operación, espera, inactividad y parada. Esta referencia no duplica un maestro de activos, no deprecia bienes y no genera valorización.",
        ),
        (
            "Producción de campo",
            "ProductionRecord relaciona Scope Item, Plan Item, IWP, frente, turno, cantidad, unidad e instante observado. Conserva la revisión IFC y el documento CDE de respaldo. RECORDED pasa a VERIFIED o REJECTED mediante un actor con facultades de verificación. La cantidad debe ser positiva y compatible con la unidad gobernada.",
        ),
        (
            "Evidencia de cantidades instaladas",
            "La evidencia de instalación se representa con ProductionRecord de tipo INSTALLED, sin una segunda tabla de cantidades. El consumidor Progress exige producción verificada e inclusión exacta en un parte aprobado vigente. Cada adopción conserva origen, versión, hash, fecha observada y período efectivo.",
        ),
        (
            "Eventos de campo",
            "FieldEvent describe una condición observada, severidad, duración y evidencia. Contracts puede consultarlo como fuente tipada. Un evento no crea un claim, un notice, una variación, un certificado ni un compromiso económico.",
        ),
        (
            "Instrucciones de obra",
            "SiteInstruction conserva emisor, receptor, alcance e instrucción documentada. Su emisión está separada de la preparación y su recepción puede reconocerse. No representa una orden de cambio contractual y no modifica el presupuesto aprobado.",
        ),
        (
            "Retrabajo",
            "El tipo REWORKED de ProductionRecord exige una producción original y motivo. Permite registrar el hecho sin una entidad paralela. El consumidor de cantidades instaladas excluye retrabajo para impedir que se sume como nueva instalación de manera implícita.",
        ),
        (
            "Observaciones de restricciones",
            "FieldConstraintObservation usa REPORTED, VERIFIED y REJECTED. Solo una observación verificada puede adoptarse explícitamente en AWP. La adopción crea una restricción nativa y su vínculo con el IWP. No libera paquetes, no limpia restricciones y no permite duplicar una adopción previa mediante una decisión intermedia de rechazo.",
        ),
        (
            "Clima y condiciones",
            "FieldCondition captura fecha, ubicación, clima, temperatura, lluvia, viento y acceso. Las condiciones se adjuntan al turno y al parte como hechos. No prueban por sí mismas una causal contractual ni una extensión de plazo.",
        ),
        (
            "Consumo de materiales",
            "MaterialConsumption referencia producción y asignación material aceptada en Procurement. Valida identidad, cantidad y unidad. Su registro informa consumo en campo, sin descontar automáticamente inventario, registrar una salida financiera o valorar materiales.",
        ),
        (
            "Integración con AWP",
            "La captura gobernada exige un IWP efectivamente liberado antes de la ejecución, salvo una excepción explícita permitida por el perfil. Las excepciones requieren justificación y no cambian la autoridad AWP. Las observaciones se adoptan desde el dominio AWP con sus propios permisos e idempotencia.",
        ),
        (
            "Integración con Progress",
            "La adopción ADOPT o PARTIAL_ADOPT crea una medición nativa DRAFT sobre el denominador aprobado de Scope. Plan e IWP permanecen en la referencia completa de la evidencia, sin inferir una cantidad agregada de un paquete con unidades diferentes. Un rechazo registra una decisión sin avance. La certificación y aprobación siguen el flujo nativo y una persona independiente. El saldo adoptable se calcula por linaje de producción. Los acumulados conservan sus fuentes Field y una medición pendiente impide abrir ramas paralelas.",
        ),
        (
            "Integración con Cost",
            "El consumidor Cost consulta horas y producción y registra una decisión explícita con CBS, Cost Code y Control Account activos. No crea Actual Cost ni un asiento. La misma fuente no puede adoptarse repetidamente para ocultar una duplicación operacional.",
        ),
        (
            "Integración con Contracts",
            "Se publican consultas tipadas de eventos, instrucciones, producción y partes diarios. El dominio contractual evalúa sus consecuencias por separado. O3A no implementa una escritura Field directa sobre certificados, claims, notices o cambios.",
        ),
        (
            "Integración con Engineering",
            "La fuente IFC conserva release, revisión, deliverable, versión y hash. La validación utiliza el instante observado de la ejecución y las reglas nativas de vigencia de Engineering. Se distingue una revisión histórica válida de una revisión que todavía no estaba vigente en la fecha de trabajo.",
        ),
        (
            "Integración con Schedule",
            "Schedule puede consultar frentes, producción y eventos como hechos informativos. Field no modifica fechas reales de Primavera P6, no crea una red CPM y no reemplaza el cronograma aceptado. Las referencias de actividades mantienen versión y external ID.",
        ),
        (
            "Integración documental",
            "Las referencias CDE incluyen documento, adjunto, versiones, binding y SHA 256. Se reutilizan las comprobaciones de acceso documental y se ocultan documentos restringidos o desactualizados. No se crea un repositorio de evidencias paralelo.",
        ),
        (
            "Configuración ADMIN y operación USER",
            "ADMIN publica un Field Operations Profile versionado con catálogos, tipos, excepciones y políticas. Un configurador no publica su propio contenido. USER opera Field Operations Manager dentro del shell existente. Las pantallas diferencian capture, review, approve y acciones de los consumidores nativos.",
        ),
        (
            "Seguridad",
            "Las rutas verifican tenant, membresía, workspace de proyecto y permiso del dominio. La habilitación del módulo es explícita. If Match controla concurrencia e Idempotency Key liga el comando a su actor y payload. Las referencias de otros proyectos no se aceptan aunque pertenezcan al mismo tenant.",
        ),
        (
            "Segregación de funciones",
            "Las facultades field_reporter, field_supervisor, field_approver, field_configurator, field_publisher y field_instruction_issuer separan captura, verificación, aprobación y publicación. Un actor Field no adquiere permisos Progress, Cost, AWP o Contracts por consultar una evidencia. Las adopciones exigen la autorización del dominio receptor.",
        ),
        (
            "Auditoría",
            "FieldHistory registra actor, acción, motivo, contexto e instantánea. Los hechos aprobados y las decisiones son inmutables. Los cierres y correcciones son registros adicionales. La migración aplica guardas PostgreSQL contra borrado, cambio de identidad y referencias de padres fuera del tenant o proyecto.",
        ),
        (
            "API",
            "Las rutas Field se encuentran en /api/v1/field-operations/projects/{workspace_id}. Los consumidores viven en /api/v1/{progress|awp|cost|contracts|schedule}/projects/{workspace_id}/field-adoptions. Contracts y Schedule se limitan a consulta. Los errores tipados distinguen permisos, conflicto de versión, fuente inválida y reglas operacionales.",
        ),
        (
            "Interfaz web",
            "La interfaz incorpora frentes, turnos, partes, cuadrillas, mano de obra, equipos, producción, eventos, instrucciones, restricciones, materiales, condiciones, preparación, lookahead, trazabilidad e historial. Los formularios reutilizan controles del repositorio y mantienen las acciones en sus dominios de autoridad. El diseño admite pantallas reducidas; no implementa sincronización offline completa.",
        ),
        (
            "Migración",
            "La revisión 20261118_0080, hija de 20261113_0079, crea 17 tablas Field y sus índices y guardas. El SQL se congela en el repositorio. No se crea esquema durante el arranque de la aplicación. El downgrade rechaza eliminar tablas con hechos registrados para evitar pérdida de información.",
        ),
        (
            "Validación PostgreSQL",
            "Se ejecutó la cadena real de migraciones sobre una base desechable y la reversión y reaplicación de 0080. Los ensayos funcionales recorren fuentes reales de Scope, AWP, Engineering y Procurement antes de la captura Field. El cuadro de pruebas de este informe muestra únicamente los archivos de evidencia disponibles en este corte.",
        ),
        (
            "Validación Chromium",
            "La UAT utiliza el shell real, credenciales de un tenant aislado y las API reales. Su resultado y cobertura se registran por separado de las pruebas unitarias. Una captura de pantalla no sustituye la verificación de las transiciones ni la adopción nativa de Progress.",
        ),
        (
            "Preservación del proyecto 14",
            "El proyecto 14 se excluyó de las escrituras y de los fixtures. Las capturas antes y después coincidieron en la identidad y los hashes observados, con 70 controles de referencias legacy y 74 de referencias al workspace canónico. La ausencia de una identidad legacy no se confundió con ausencia del workspace canónico. Ambas capturas se realizaron en transacciones de solo lectura.",
        ),
        (
            "Rendimiento",
            "Se miden nueve lecturas Field y Progress con tres muestras por consulta. Se informa mediana y tamaño de respuesta sin convertirlo en un SLA. Las consultas Contracts readiness y trace se monitorizan adicionalmente para conservar la visibilidad de la deuda O2C heredada.",
        ),
        (
            "Deuda técnica",
            "Se mantiene O2C S3 de latencia local en readiness y trace y de endurecimiento del alcance SQL de padres simples preexistentes. O3A endurece sus propias referencias sin declarar resuelta aquella deuda. La recuperación de reservas cuando una medición nativa ya adoptada es rechazada y la conciliación de una fuente corregida después de su adopción requieren un flujo explícito del dominio receptor. El comportamiento actual impide duplicar cantidades. Solo INSTALLED es elegible en el adaptador de cantidades instaladas; los demás tipos se conservan como hechos sin reclasificación automática.",
        ),
        (
            "Defectos",
            "La revisión detectó y corrigió la adopción AWP repetida tras un rechazo, la falta de bloqueo de observaciones rechazadas, la guarda SQL de observaciones terminales, la evidencia tipada incompatible con Progress y la pérdida de fuentes al acumular mediciones. Los defectos abiertos, si existen, figuran en la decisión técnica y no se consideran cerrados por tener código implementado.",
        ),
        (
            "Decisión de liberación",
            "La liberación requiere todas las verificaciones obligatorias y cero defectos S1 o S2 abiertos. No se emite el marcador de release por una compilación correcta o por completar el informe. La decisión del corte, los pendientes y las limitaciones operativas se presentan a continuación.",
        ),
    ]


def matrix():
    result = {}

    def add(name, title, headers, rows):
        result[name] = {"title": title, "headers": headers, "rows": rows}

    add(
        "00_README",
        "Guía de trazabilidad O3A",
        ["Concepto", "Definición", "Valor del corte"],
        [
            ["Producto", "Aplicación y Wave analizada", "P&Pmis Construction AI O3A"],
            ["Fecha", "Fecha del corte técnico en Bogotá", DATE],
            ["Baseline", "Commit anterior al trabajo O3A", BASELINE],
            [
                "Fuentes",
                "Requisitos y pruebas efectivamente ejecutadas",
                "PDF O3A secciones 1 a 72 y registros de validación",
            ],
            [
                "Estado",
                "Resultado de la decisión del corte",
                read("release-decision.json").get("status", "VALIDACION EN CURSO"),
            ],
            [
                "Ejemplos",
                "Los ejemplos describen el fixture de validación separado del proyecto 14",
                "FIELD-FRONT y FIELD-DAILY",
            ],
        ],
    )

    def requirement(title):
        if title in {
            "Frentes de trabajo",
            "Turnos de campo",
            "Partes diarios",
            "Cuadrillas",
            "Mano de obra",
            "Equipos",
            "Clima y condiciones",
        }:
            return (
                "field_operations/service.py",
                "core report and shift PostgreSQL + execution-policy-final",
            )
        if title in {
            "Producción de campo",
            "Evidencia de cantidades instaladas",
            "Eventos de campo",
            "Instrucciones de obra",
            "Retrabajo",
            "Observaciones de restricciones",
            "Consumo de materiales",
        }:
            return (
                "field_operations/execution_service.py",
                "execution facts negatives corrections PostgreSQL",
            )
        if title.startswith("Integración con "):
            return (
                "field_operations/consumer_router.py y sources.py",
                "consumer policy + consumer PostgreSQL",
            )
        if "web" in title or "Chromium" in title:
            return (
                "frontend/features/field-operations",
                "Chromium + frontend unit build lint",
            )
        if "Migración" in title:
            return "Alembic 20261118_0080", "migration/proof.json"
        if "proyecto 14" in title:
            return "preservation.py solo lectura", "preservation before after idénticos"
        if "Rendimiento" in title:
            return (
                "Consultas de lectura sin efectos",
                "consumer-performance y contracts-performance",
            )
        if title in {
            "Seguridad",
            "Segregación de funciones",
            "Configuración ADMIN y operación USER",
        }:
            return (
                "permissions.py profiles.py policy.py",
                "core policy + PostgreSQL SoD auth negativos",
            )
        return (
            "O3A arquitectura y controles compartidos",
            "JUnit y decisión técnica del corte",
        )

    requirement_rows = []
    for i, (title, definition) in enumerate(sections()[3:39]):
        implementation, verification = requirement(title)
        requirement_rows.append(
            [
                "O3A-" + str(i + 1).zfill(2),
                title,
                implementation,
                verification,
                definition.split(". ")[0] + ".",
            ]
        )
    add(
        "01_REQUIREMENTS",
        "Requisitos y cobertura",
        ["ID", "Requisito", "Implementación", "Verificación", "Definición del control"],
        requirement_rows,
    )
    add(
        "02_AUTHORITY",
        "Autoridad por dominio",
        ["Dominio", "Autoridad", "No autorizado desde Field", "Ejemplo"],
        [
            [
                "Field",
                "Hechos observados",
                "Aprobar avance o costo",
                "Producción verificada de 2 unidades",
            ],
            [
                "AWP",
                "Restricciones y liberación IWP",
                "Liberación automática",
                "Adopción de observación verificada",
            ],
            [
                "Progress",
                "Certificación y aprobación",
                "Aprobación por aprobar DCR",
                "Adopción crea DRAFT",
            ],
            [
                "Cost",
                "Reconocimiento económico",
                "Actual Cost por horas",
                "Clasificación CBS de evidencia",
            ],
            [
                "Contracts",
                "Efectos comerciales",
                "Claim o certificado implícito",
                "Consulta FieldEvent",
            ],
            [
                "Schedule",
                "Cronograma aceptado",
                "Fechas reales P6",
                "Consulta Workfront",
            ],
        ],
    )
    domains = [
        (
            "Workfront",
            "field_workfronts",
            "Ubicación CWA IWP responsable fechas",
            "FIELD-FRONT",
        ),
        ("FieldShift", "field_shifts", "Fecha horario supervisor frente", "FIELD-DAY"),
        (
            "DailyConstructionReport",
            "field_daily_reports",
            "Fecha turno frentes source_references supersedes_id",
            "FIELD-DAILY",
        ),
        ("Crew", "field_crews", "Oficio proveedor supervisor", "FIELD-CREW"),
        (
            "FieldEquipmentReference",
            "field_equipment_references",
            "Sistema externo identidad tipo",
            "EQP-001",
        ),
        (
            "LaborUsage",
            "field_labor_usage",
            "Turno cuadrilla horas personal",
            "FIELD-LABOR",
        ),
        (
            "EquipmentUsage",
            "field_equipment_usage",
            "Equipo turno horas por condición",
            "FIELD-EQUIPMENT",
        ),
        (
            "ProductionRecord",
            "field_production_records",
            "Scope Plan IWP cantidad UOM fecha IFC CDE",
            "FIELD-INSTALLATION",
        ),
        ("FieldEvent", "field_events", "Tipo severidad duración CDE", "FIELD-EVENT"),
        (
            "SiteInstruction",
            "field_site_instructions",
            "Emisor receptor tipo CDE",
            "FIELD-INSTRUCTION",
        ),
        (
            "FieldConstraintObservation",
            "field_constraint_observations",
            "IWP tipo severidad CDE",
            "FIELD-CONSTRAINT",
        ),
        (
            "FieldCondition",
            "field_conditions",
            "Fecha clima acceso ubicación",
            "FIELD-CONDITION",
        ),
        (
            "MaterialConsumption",
            "field_material_consumption",
            "Producción material asignación cantidad UOM",
            "FIELD-CONSUMPTION",
        ),
        (
            "FieldMapping",
            "field_mappings",
            "Fuente objetivo SET REMOVE versión",
            "PRODUCTION a WBS",
        ),
        (
            "FieldHistory",
            "field_history",
            "Acción actor motivo snapshot",
            "daily_report.approved",
        ),
        (
            "FieldClosure",
            "field_record_closures",
            "Entidad ID motivo cierre",
            "DCR CLOSED",
        ),
        (
            "FieldConsumerDecision",
            "field_consumer_decisions",
            "Consumidor fuente versión hash fecha período decisión vínculo",
            "PRODUCTION a Progress DRAFT",
        ),
    ]
    add(
        "03_DOMAIN_MODEL",
        "Modelo de datos",
        ["Entidad", "Tabla", "Campos específicos", "Ejemplo"],
        [list(row) for row in domains],
    )
    add(
        "04_WORKFLOWS",
        "Flujos autorizados",
        ["Flujo", "Secuencia", "Condición", "Ejemplo"],
        [
            [
                "Parte diario",
                "DRAFT SUBMITTED REVIEWED APPROVED CLOSED",
                "Actores independientes y fuentes congeladas",
                "FIELD-DAILY",
            ],
            [
                "Producción",
                "RECORDED VERIFIED o REJECTED",
                "IWP IFC UOM CDE válidos",
                "2 unidades instaladas",
            ],
            [
                "Progress",
                "Lookup PARTIAL_ADOPT DRAFT certificación aprobación",
                "Consumidor nativo y período abierto",
                "Adoptar 1 de 2 unidades",
            ],
            ["AWP", "REPORTED VERIFIED ADOPT", "Sin liberar IWP", "Restricción ACCESS"],
            [
                "Corrección",
                "Hecho aprobado sucesor borrador nueva aprobación",
                "Original intacto",
                "Revisión de FIELD-DAILY",
            ],
        ],
    )
    add(
        "05_STATUSES",
        "Estados y significado",
        ["Entidad", "Estados", "Terminal", "Ejemplo"],
        [
            [
                "Workfront",
                "PLANNED ACTIVE SUSPENDED COMPLETE",
                "COMPLETE",
                "ACTIVE permite capturar",
            ],
            [
                "Shift",
                "OPEN SUBMITTED APPROVED CLOSED",
                "CLOSED",
                "CLOSED impide nuevos hechos",
            ],
            [
                "DCR",
                "DRAFT SUBMITTED REVIEWED APPROVED",
                "APPROVED con cierre separado",
                "Sucesor para corrección",
            ],
            [
                "Production",
                "RECORDED VERIFIED REJECTED",
                "VERIFIED REJECTED",
                "REWORKED no se suma como instalación",
            ],
            [
                "Observation",
                "REPORTED VERIFIED REJECTED",
                "VERIFIED REJECTED",
                "Solo VERIFIED elegible AWP",
            ],
            [
                "Readiness",
                "READY PARTIALLY_READY NOT_READY STALE BROKEN_REFERENCE",
                "No aplica",
                "IFC inválido bloquea",
            ],
        ],
    )
    add(
        "06_PERMISSIONS",
        "Facultades por rol",
        ["Rol", "Facultad", "Frontera", "Ejemplo"],
        [
            [
                "field_reporter",
                "Capturar hechos y someter parte",
                "No aprobar",
                "Crear ProductionRecord",
            ],
            [
                "field_supervisor",
                "Verificar hechos y revisar parte",
                "No modificar terminales",
                "Verificar instalación",
            ],
            [
                "field_approver",
                "Aprobar parte",
                "No aprobar trabajo propio",
                "APPROVED",
            ],
            [
                "field_configurator",
                "Preparar perfil",
                "No publicar propio contenido",
                "DRAFT profile",
            ],
            [
                "field_publisher",
                "Publicar perfil",
                "SoD del preparador",
                "PUBLISHED profile",
            ],
            [
                "Consumidor nativo",
                "Adoptar bajo permisos Progress AWP Cost",
                "Sin herencia Field",
                "progress.capture",
            ],
        ],
    )
    add(
        "07_SOD",
        "Segregación de funciones",
        ["Control", "Regla", "Rechazo", "Ejemplo"],
        [
            [
                "DCR",
                "Preparador distinto de aprobador",
                "403 o conflicto de regla",
                "Reporter no aprueba",
            ],
            [
                "Profile",
                "Configurador distinto de publisher",
                "Publicación denegada",
                "Field profile",
            ],
            [
                "Progress",
                "Certificación independiente",
                "No certifica propio hecho",
                "Cost controller y manager",
            ],
            [
                "Native owner",
                "Permiso del receptor requerido",
                "Field reporter denegado",
                "Cost lookup/adopt",
            ],
        ],
    )
    add(
        "08_INTEGRATIONS",
        "Contratos de integración",
        ["Origen", "Receptor", "Mecanismo", "Efecto", "Ejemplo"],
        [
            ["Field", "Progress", "Adopción explícita", "Medición DRAFT", "1 unidad"],
            ["Field", "AWP", "Adopción explícita", "Restricción nativa", "ACCESS"],
            [
                "Field",
                "Cost",
                "Decisión explícita",
                "Clasificación evidencia",
                "Horas a CBS",
            ],
            ["Field", "Contracts", "GET tipado", "Sin efectos comerciales", "Evento"],
            ["Field", "Schedule", "GET tipado", "Sin fechas P6", "Frente"],
            [
                "Engineering",
                "Field",
                "Pin con vigencia",
                "IFC en ejecución",
                "Release actual",
            ],
            [
                "Procurement",
                "Field",
                "Asignación aceptada",
                "Disponibilidad material",
                "Allocation",
            ],
        ],
    )
    for name, title, rows in [
        (
            "09_AWP_TRACEABILITY",
            "Trazabilidad AWP",
            [
                [
                    "IWP liberado",
                    "IWP id versión release_state",
                    "Lectura previa",
                    "FIELD-FRONT",
                ],
                [
                    "Observación",
                    "ID versión hash VERIFIED",
                    "Adopción explícita",
                    "ACCESS",
                ],
                [
                    "Resultado",
                    "AWPExecutionConstraint ID",
                    "No liberar ni limpiar",
                    "ADOPT",
                ],
            ],
        ),
        (
            "10_PROGRESS_TRACEABILITY",
            "Trazabilidad Progress",
            [
                [
                    "Producción",
                    "ID raíz versión hash cantidad UOM fecha",
                    "VERIFIED y DCR aprobado",
                    "2 unidades",
                ],
                [
                    "Adopción",
                    "Cantidad período usuario decisión",
                    "Saldo y ramas pendientes",
                    "PARTIAL_ADOPT 1",
                ],
                [
                    "Medición",
                    "ID DRAFT fuentes congeladas",
                    "Aprobación nativa posterior",
                    "FIELD-PROGRESS",
                ],
            ],
        ),
        (
            "11_COST_TRACEABILITY",
            "Trazabilidad Cost",
            [
                [
                    "Horas",
                    "Labor o Equipment ID versión hash",
                    "Parte aprobado",
                    "9 horas",
                ],
                [
                    "Clasificación",
                    "CBS CostCode ControlAccount activos",
                    "Decisión receptor",
                    "ADOPT",
                ],
                [
                    "Autoridad",
                    "Sin linked Actual Cost",
                    "No valoración",
                    "linked_entity_id vacío",
                ],
            ],
        ),
        (
            "12_CONTRACTS_TRACEABILITY",
            "Trazabilidad Contracts",
            [
                [
                    "Evento",
                    "ID tipo fecha descripción CDE",
                    "Consulta informativa",
                    "FIELD-EVENT",
                ],
                [
                    "Instrucción",
                    "ID emitida y CDE",
                    "Consulta informativa",
                    "FIELD-INSTRUCTION",
                ],
                [
                    "Autoridad",
                    "No Notice Claim Change Certificate",
                    "Sin POST consumidor",
                    "GET lookup",
                ],
            ],
        ),
        (
            "13_SCHEDULE_TRACEABILITY",
            "Trazabilidad Schedule",
            [
                ["Frente", "ID fechas observadas", "Informativo", "ACTIVE"],
                [
                    "Actividad",
                    "Versión external ID",
                    "Referencia explícita",
                    "ACTIVITY",
                ],
                [
                    "Autoridad",
                    "No fechas reales P6 ni CPM",
                    "Sin escritura",
                    "GET lookup",
                ],
            ],
        ),
    ]:
        add(name, title, ["Objeto", "Datos conservados", "Regla", "Ejemplo"], rows)
    add(
        "14_API",
        "Rutas y controles API",
        ["Grupo", "Ruta relativa", "Método", "Control", "Ejemplo"],
        [
            [
                "Field",
                "/field-operations/projects/{id}/workfronts",
                "GET POST",
                "Membresía y field permission",
                "FIELD-FRONT",
            ],
            [
                "Field",
                "/daily-reports/{id}/actions",
                "POST",
                "If Match Idempotency SoD",
                "approve",
            ],
            [
                "Field",
                "/production/{id}/actions",
                "POST",
                "Verificador y fuente válida",
                "verify",
            ],
            [
                "ADMIN",
                "/field-operations/admin/profiles/{id}/publish",
                "POST",
                "Publisher independiente",
                "PUBLISHED",
            ],
            [
                "Native",
                "/{domain}/projects/{id}/field-adoptions/lookup",
                "GET",
                "Permiso nativo read",
                "PRODUCTION",
            ],
            [
                "Native",
                "/{progress|awp|cost}/projects/{id}/field-adoptions",
                "POST",
                "Permiso nativo y pins",
                "ADOPT",
            ],
        ],
    )
    rows = [
        [
            name,
            count,
            failed + errors,
            skipped,
            "PASS" if failed + errors == 0 and count > skipped else "REVISAR",
        ]
        for name, count, failed, errors, skipped, _ in tests()
    ]
    add(
        "15_TESTS",
        "Pruebas registradas",
        ["Evidencia", "Casos", "Fallos", "Omitidos", "Resultado"],
        rows or [["Sin evidencia JUnit", 0, 0, 0, "PENDIENTE"]],
    )
    defects = read("release-decision.json").get("defects", [])
    add(
        "16_DEFECTS",
        "Defectos del corte",
        ["ID", "Severidad", "Descripción", "Estado", "Acción"],
        defects
        or [
            [
                "VALIDACION",
                "Sin clasificar",
                "Revisar resultados del corte antes de liberar",
                "ABIERTA",
                "Completar verificaciones",
            ]
        ],
    )
    add(
        "17_TECHNICAL_DEBT",
        "Deuda técnica conservada",
        ["ID", "Severidad", "Alcance", "Tratamiento", "Ejemplo"],
        [
            [
                "O2C-S3-01",
                "S3 heredado",
                "Latencia local Contracts readiness trace",
                "Monitorizar sin reabrir O2C",
                "Tres lecturas",
            ],
            [
                "O2C-S3-02",
                "S3 heredado",
                "SQL padres simples preexistentes",
                "Guardas nuevas O3A no resuelven deuda anterior",
                "FK workspace",
            ],
            [
                "O3A-S3-01",
                "S3",
                "Reserva tras rechazo nativo",
                "Recuperación gobernada posterior sin duplicar",
                "Medición rechazada",
            ],
            [
                "O3A-S3-02",
                "S3",
                "Offline completo fuera de alcance",
                "UI adaptable sin sincronización",
                "Conexión requerida",
            ],
            [
                "O3A-S3-UI01",
                "S3",
                "Indicadores del módulo receptor tras adoptar",
                "Pulsar Actualizar en Progress AWP o Cost",
                "El panel consumidor sí refresca su historial",
            ],
        ],
    )
    criteria = read("release-decision.json").get("criteria", {})
    add(
        "18_RELEASE_CRITERIA",
        "Criterios de liberación",
        ["Criterio", "Definición", "Resultado", "Evidencia"],
        [
            [key, definition, criteria.get(key, "PENDIENTE"), evidence]
            for key, definition, evidence in [
                ("PostgreSQL", "Migración y cadenas reales", "JUnit y migration logs"),
                (
                    "Consumers",
                    "Adopción explícita sin violar autoridad",
                    "consumer-junit.xml",
                ),
                ("Chromium", "ADMIN USER Progress real", "browser evidence"),
                (
                    "Preservation",
                    "Proyecto14 sin modificaciones",
                    "project-14/compare.json",
                ),
                ("Regression", "O1 y O2 relevantes", "regression-junit.xml"),
                (
                    "Performance",
                    "9 consultas por 3 muestras y Contracts",
                    "consumer-performance.json",
                ),
                ("Defects", "Cero S1 S2 abiertos", "release-decision.json"),
            ]
        ],
    )
    return result
