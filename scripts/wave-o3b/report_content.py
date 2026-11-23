"""Evidence-linked O3B technical report and twenty-sheet traceability source."""

import ast
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
QA = ROOT / "outputs/.qa/wave-o3b-20261119"
OUT = ROOT / "outputs/wave-o3b-quality-management-inspection-20261122"
DATE = "22 de noviembre de 2026"
BASELINE = "5c9a550189dd58c17df0e9f9c4c73830885df7e0"
PROMPT = Path(
    r"C:\Users\Ricardo\Documents\P&P\P&Pmis Construction AI\Diseño\Operation Processes\P&Pmis_Wave_O3B_Quality_Management_Inspection_Foundation_Prompt_Codex.pdf"
)
MARKER = "WAVE_O3B_QUALITY_MANAGEMENT_INSPECTION_FOUNDATION_RELEASE_VALIDATED"


def read(name):
    path = QA / name
    return json.loads(path.read_text("utf-8-sig")) if path.exists() else {}


# Compatibility for the retained O2C typography helpers. Its report entry point
# is not invoked; O3B owns every narrative section and evidence selection.
read_json = read


def detailed_sections():
    return []


def tests():
    rows = []
    index = read("verified-suites.json").get("suites", [])
    candidates = (
        [(QA / row["path"], row.get("class_filter")) for row in index]
        if index
        else [
            (path, None)
            for pattern in (
                "*junit*.xml",
                "backend-core*/*junit*.xml",
                "regression/*junit*.xml",
                "frontend-final*/*junit*.xml",
            )
            for path in QA.glob(pattern)
        ]
    )
    for path, class_filter in sorted(candidates, key=lambda row: str(row[0])):
        if any(part in path.parts for part in ("node_modules", "attempts")):
            continue
        tree = ET.parse(path).getroot()
        suites = list(tree.iter("testsuite"))
        if not suites and tree.tag == "testsuite":
            suites = [tree]
        fields = [
            sum(int(suite.get(key, 0)) for suite in suites)
            for key in ("tests", "failures", "errors", "skipped")
        ]
        if class_filter:
            cases = [
                case
                for case in tree.iter("testcase")
                if case.get("classname") == class_filter
            ]
            fields = [
                len(cases),
                sum(case.find("failure") is not None for case in cases),
                sum(case.find("error") is not None for case in cases),
                sum(case.find("skipped") is not None for case in cases),
            ]
        rows.append(
            [
                str(path.relative_to(QA)),
                *fields,
                "PASS" if fields[0] and not any(fields[1:3]) else "NO PASS",
            ]
        )
    return rows


def requirement_reference(number):
    """Implementation and evidence contracts for each of the 68 source clauses."""
    groups = [
        (
            {1},
            "scripts/wave-o3b/microclose_o3a.py y mjs",
            "Microcierre sin alterar las once páginas ni las diecinueve hojas originales",
            "microclose/complete.json",
        ),
        (
            {2, 55},
            "scripts/wave-o3b/contracts_performance.py",
            "Seguimiento O2C y conservación explícita de las cuatro deudas O2C O3A",
            "contracts-performance.json y 18_TECHNICAL_DEBT",
        ),
        (
            {3, 4, 24, 63, 64},
            "quality/consumer_router.py y adaptadores nativos",
            "Ninguna inspección o aceptación crea avance release costo o consecuencia contractual",
            "consumer-evidence.json y suites PostgreSQL",
        ),
        (
            {5, 18, 20, 22, 49},
            "quality/execution_service.py y sources.py",
            "FAIL NCR disposición REWORK Field real reinspección verificación cierre y sucesora",
            "execution/real-remediation.json",
        ),
        (
            {6, 19},
            "quality/sources.py y EngineeringReadinessReader",
            "IFC vigente al inspeccionar y USE_AS_IS sin proveedor específico bloqueado",
            "backend-pg-release-20261122-core/fixture-proof.json y pruebas negativas",
        ),
        (
            {7, 8, 9, 10},
            "quality/models.py y service.py",
            "Plan e ITP versionados aplicabilidad canónica y HOLD explícito vigente",
            "suite test_quality_core_release",
        ),
        (
            {11, 12, 33},
            "quality/schemas.py service.py y QualityForms.tsx",
            "Solicitud separada checklist congelado respuestas y cierre independiente",
            "suite core y pasos Chromium",
        ),
        (
            {13, 14, 34, 35},
            "quality/TestRequest TestRecord y FieldEquipmentReference",
            "Mediciones múltiples límites unidad laboratorio y calibración temporal",
            "suite core y ensayo Chromium",
        ),
        (
            {15, 16, 50},
            "quality/sources.py support_router.py y Procurement",
            "Recepción técnica lote tipado y aceptación sin alterar logística",
            "suite execution y suite consumer",
        ),
        (
            {17},
            "quality/QualityNCR",
            "Objeto NCR vinculado al resultado y requisito de un sujeto exacto",
            "execution/real-remediation.json",
        ),
        (
            {21},
            "quality/QualityCorrectiveAction",
            "PREVENTIVE IMPROVEMENT mínimos sin cierre automático de NCR",
            "suite test_quality_execution_policy",
        ),
        (
            {23},
            "quality/QualityAcceptance y acceptance_state",
            "Cantidad unidad hash y versión exactos con controles completos",
            "consumer-evidence.json y ejecución NCR",
        ),
        (
            {25},
            "quality/QualityPunchItem",
            "Finalización y verificación PASS independiente antes de aceptación",
            "execution/real-remediation.json",
        ),
        (
            {26},
            "quality/readiness y QualityReadinessAssessment",
            "Cinco estados consulta pura y snapshot solo por comando explícito",
            "consumer-performance.json y pruebas de vigencia",
        ),
        (
            {27, 51},
            "quality/consumer_sources.py y awp/service.py",
            "Decisión propia AWP sin clear release ni invalidación circular por evaluar",
            "consumer-evidence.json y Chromium",
        ),
        (
            {28, 48},
            "progress_foundation policy service y quality consumer",
            "Política opcional aceptación exacta reconciliación sin doble cantidad",
            "consumer-evidence.json y Chromium",
        ),
        (
            {29, 52},
            "Contracts quality-adoptions lookup",
            "Lectura informativa sin Notice Claim Change ni Certificate",
            "consumer-evidence.json y Chromium Contracts",
        ),
        (
            {30},
            "Cost quality-adoptions",
            "Clasificación CBS Code Control Account sin Actual Cost",
            "suite test_quality_consumer_release",
        ),
        (
            {31},
            "FieldSourceMixin y ScheduleVersion aceptada",
            "Referencia por versión y external_id sin modificar P6",
            "suite core de referencias y aislamiento",
        ),
        (
            {32},
            "FieldSourceMixin.resolve_document y CDE",
            "Identidad revisión adjunto hash y acceso sin duplicar binarios",
            "suite core y suite execution",
        ),
        (
            {36, 37},
            "quality/execution_service lookahead trace",
            "Filtros canónicos y traza de fuentes resultados NCR y consumidores",
            "consumer-performance.json y Chromium trace",
        ),
        (
            {38, 39, 40, 41},
            "quality/profiles.py permissions.py y rutas dedicadas",
            "ADMIN independiente RBAC SoD 403 404 409 412 e idempotencia",
            "suites core execution consumer y política",
        ),
        (
            {42, 43, 56, 57},
            "Alembic 0081 y diecisiete tablas Quality",
            "Triggers de ámbito terminales inmutables round trip y downgrade poblado rechazado",
            "migration/round-trip.json y populated-refusal.json",
        ),
        (
            {44, 45},
            "API v1 Quality y quality-adoptions nativos",
            "Queries separadas de commands con permisos del propietario",
            "15_API y suites PostgreSQL",
        ),
        (
            {46, 47, 58},
            "frontend/features/quality y shell operacional",
            "ADMIN USER formularios estructurados móvil y navegador real",
            "browser-summary.json y frontend-final-v2",
        ),
        (
            {53},
            "Pruebas core execution consumer",
            "Negativos de alcance tiempo hash unidad estados SoD e integración duplicada",
            "verified-suites.json",
        ),
        (
            {54},
            "scripts/wave-o3b/regression_validation.py",
            "Regresión de políticas y API O3A relevante conservando evidencia histórica",
            "regression y frontend-final-v2",
        ),
        (
            {59, 67},
            "scripts/wave-o3b/preservation.py",
            "Proyecto 14 solo lectura base habitual sin migraciones O3B y sin producción",
            "project-14/preservation-after.json",
        ),
        (
            {60},
            "Mediciones de lecturas Quality y Contracts",
            "Tres muestras mediana bytes filas y cero SQL DML sin declarar SLA",
            "consumer-performance.json y contracts-performance.json",
        ),
        (
            {61, 62},
            "build_report.py y build_matrix.mjs",
            "Treinta y nueve capítulos y veinte hojas con campos ejemplos y revisión visual",
            "word-qa.json y matrix-qa.json",
        ),
        (
            {65, 66, 68},
            "Cierre técnico condicionado a controles obligatorios",
            "Cero S1 S2 abiertos y sin iniciar la Wave siguiente",
            "release-decision.json",
        ),
    ]
    return next(
        (implementation, control, proof)
        for numbers, implementation, control, proof in groups
        if number in numbers
    )


def status():
    return read("release-decision.json").get(
        "status", "VALIDACIÓN EN CURSO SIN DECLARACIÓN DE RELEASE"
    )


def sections():
    # Every chapter describes implementation separately from the measured results below.
    display_status = "VALIDADO EN ENTORNO AISLADO" if status() == MARKER else status()
    return [
        (
            "01 Resumen ejecutivo",
            [
                "O3B incorpora Quality Manager al entorno operacional de P&Pmis Construction AI. El módulo gobierna planes de calidad, ITP, inspecciones, ensayos, no conformidades y aceptación de cantidades identificadas. Reutiliza las autoridades de Field Operations, Engineering, Procurement, AWP, Progress y CDE.",
                "El estado de este corte es "
                + display_status
                + ". Las validaciones se ejecutan sobre PostgreSQL aislado y proyectos sintéticos. El resultado técnico no equivale a aprobación de negocio ni a autorización de producción.",
            ],
        ),
        (
            "02 Baseline y alcance",
            [
                "La referencia del repositorio es "
                + BASELINE
                + ". El trabajo conserva las funcionalidades anteriores y añade una migración incremental 0081 sobre 0080. No incluye la siguiente Wave, un sistema de inventario, una segunda planificación P6 ni sincronización offline.",
                "Antes de desarrollar O3B se completó el microcierre documental de O3A. Sus once páginas originales permanecieron visualmente idénticas y se añadió una página de cierre. Se conservaron las diecinueve hojas históricas de la matriz, el estado VALIDADO EN ENTORNO AISLADO y las deudas abiertas.",
            ],
        ),
        (
            "03 Hallazgos del repositorio",
            [
                "El repositorio ya contenía identidad de tenant y workspace, membresías, permisos granulares, perfiles ADMIN versionados, comandos idempotentes, evidencia CDE y lectores de fuentes canónicas. O3B utiliza esas piezas en lugar de crear otro shell o almacén de documentos.",
                "Los resultados de inspección y la aceptación técnica necesitaban autoridad propia. Se añadieron diecisiete tablas de Quality. Una fila por revisión representa Plan e ITP; la reinspección reutiliza InspectionRequest con vínculo al resultado fallido y a la acción correctiva. Las plantillas de checklist se congelan en los puntos de control y en sus ejecuciones.",
            ],
        ),
        (
            "04 Modelo de autoridad",
            [
                "Field Operations conserva los hechos ejecutados. Engineering conserva diseño y liberaciones IFC. Quality determina cumplimiento; Progress reconoce avance y AWP decide readiness y liberación de paquetes. Procurement conserva recepción y logística, Contracts la consecuencia contractual, Cost el reconocimiento financiero, Forecast sus versiones y P6 el cronograma.",
                "Las consultas cruzadas no conceden facultades de escritura. Los adaptadores verifican tenant, workspace, versión, hash y fecha aplicable. Las decisiones de los consumidores quedan en un registro inmutable bajo sus permisos nativos.",
            ],
        ),
        (
            "05 Plan de calidad",
            [
                "QualityPlan registra código, revisión, alcance, responsable, vigencia, referencias operacionales y evidencia documental. El flujo DRAFT a SUBMITTED y APPROVED separa preparación y aprobación conforme al perfil.",
                "Una aprobación no se edita. El cambio exige una revisión sucesora con vínculo explícito y nueva aprobación. La historia conserva actor, razón, estado y versión.",
            ],
        ),
        (
            "06 Plan de inspección y ensayo ITP",
            [
                "El ITP fija el plan de calidad, disciplina, vigencia, fuentes Engineering y referencias de Scope, Plan o IWP. Cada ITPItem define actividad, requisito, criterio de aceptación, responsable, tipo de control, evidencia y requisitos de inspección o ensayo.",
                "Los ítems solo se modifican mientras el ITP está en borrador. La aprobación congela sus reglas y checklist. Un sucesor aprobado reemplaza su aplicabilidad sin borrar los resultados asociados a la revisión anterior.",
            ],
        ),
        (
            "07 Puntos de control",
            [
                "El perfil define HOLD, WITNESS, REVIEW, SURVEILLANCE y RECORD. La decisión RELEASED o WAIVED se registra como hecho append only con resultado y documentos fijados. Un resultado PASS por sí solo no levanta un HOLD.",
                "Una liberación previa no cubre un fallo posterior. La aceptación exige los controles aplicables vigentes y la política impide utilizar una exención para eludir un HOLD prohibido. Esta liberación pertenece a Quality, no al paquete AWP.",
            ],
        ),
        (
            "08 Solicitudes de inspección",
            [
                "InspectionRequest distingue solicitud y ejecución. Registra punto ITP, sujeto exacto, cantidad y unidad cuando corresponden, fecha solicitada, inspector y documentos. Su flujo permite presentar, programar, iniciar y cancelar bajo controles de estado.",
                "El inspector asignado debe estar activo y dentro del tenant. Las fuentes ajenas al workspace permanecen ocultas. La petición completada se conserva; la reinspección crea otra solicitud.",
            ],
        ),
        (
            "09 Inspecciones",
            [
                "InspectionRecord conserva resultado PASS, FAIL, CONDITIONAL o NOT_APPLICABLE, fecha observada, requisito Engineering y respuestas estructuradas del checklist congelado. Las respuestas exigidas y sus evidencias se verifican antes de cerrar.",
                "El flujo separa captura, presentación y cierre independiente. Una inspección cerrada no admite modificación ni borrado. Un fallo continúa visible aunque una reinspección posterior apruebe el mismo trabajo.",
            ],
        ),
        (
            "10 Ensayos",
            [
                "TestRequest y TestRecord son objetos distintos. El registro fija método, norma, unidad, límites y mediciones múltiples o cualitativas, además de laboratorio y referencia de equipo cuando aplican.",
                "Los criterios numéricos no se sustituyen por una respuesta cualitativa para evitar un límite. La calibración debe ser válida al momento del ensayo y tener evidencia. Un resultado de ensayo no aprueba un cambio de diseño.",
            ],
        ),
        (
            "11 Calidad de materiales",
            [
                "La inspección de recepción consume la línea, aceptación o asignación real de Procurement. Verifica material, requerimiento, unidad, cantidad recibida y fecha de recepción. La aprobación técnica de Quality no modifica la aceptación logística.",
                "QualityMapping enlaza material recibido y producción mediante referencias tipadas de lote, batch, heat o serial. Los vínculos admiten sucesión SET o REMOVE y conservan documento, cantidad y unidad. No constituyen un nuevo maestro de inventario.",
            ],
        ),
        (
            "12 No conformidades NCR",
            [
                "El ciclo gobernado es DRAFT, ISSUED, UNDER_REVIEW, DISPOSITIONED, CORRECTED, VERIFIED y CLOSED. La NCR fija requisito incumplido, severidad, responsable, sujeto, resultado fallido y documentos. Rechazo o cancelación tienen transiciones controladas.",
                "El cierre exige disposición aprobada, corrección demostrada y verificación independiente. Emitir una NCR no crea un claim, cambio contractual, costo real ni avance negativo.",
            ],
        ),
        (
            "13 Disposiciones",
            [
                "Se contemplan REWORK, REPAIR, USE_AS_IS, REJECT, RETURN_TO_VENDOR y OTHER, con autorización y evidencia. Preparación y aprobación de la disposición son facultades separadas.",
                "USE_AS_IS queda bloqueado si no existe una decisión técnica nativa Engineering vinculada a esa NCR. Una liberación IFC genérica no reemplaza esa decisión. El camino probado de reparación utiliza REWORK y hechos reales de Field Operations.",
            ],
        ),
        (
            "14 Acciones correctivas",
            [
                "La acción identifica NCR, responsable, vencimiento, tipo y documentos. Completar una acción correctiva exige evidencia de corrección o retrabajo emitida por Field Operations después de la disposición aplicable.",
                "La finalización y la verificación son pasos diferentes. La verificación fija un resultado PASS y evidencia documental, con separación respecto de quien completó. Se preparan acciones preventivas y de mejora sin simular un CAPA avanzado.",
                "Una NCR de material no puede cerrarse enlazando un retrabajo Field que coincida por número. Su corrección logística queda bloqueada hasta disponer de un proveedor Procurement tipado; no se inventa una devolución o movimiento de inventario.",
            ],
        ),
        (
            "15 Reinspección",
            [
                "La reinspección reutiliza el ciclo de InspectionRequest e InspectionRecord, vinculando reinspection_of_id al FAIL original y corrective_action_id a la corrección. Debe conservar el mismo punto ITP y sujeto aplicable.",
                "El PASS nuevo puede sustentar la verificación de la acción y de la NCR. No reemplaza el FAIL ni cierra automáticamente la no conformidad.",
            ],
        ),
        (
            "16 Aceptación de calidad",
            [
                "QualityAcceptance fija el ITP, sujeto exacto, versión y hash de la fuente, cantidad, unidad, vigencia, perfil y base de readiness. Solo se emite cuando todos los controles obligatorios están satisfechos y no quedan NCR o punch bloqueantes.",
                "La cantidad aceptada no puede superar la cantidad explícitamente inspeccionada o ensayada para ninguno de los controles obligatorios. Una cantidad nula no representa todo el lote. La unidad y el pin exacto deben coincidir; la lectura vuelve a verificar la cobertura y marca obsoleta una aceptación que ya no cumple.",
                "La aceptación es inmutable. Su sucesora conserva linaje. La lectura distingue CURRENT, SUPERSEDED, STALE o BROKEN_REFERENCE; una evidencia que pierde vigencia requiere una nueva decisión del consumidor.",
            ],
        ),
        (
            "17 Punch y deficiencias",
            [
                "QualityPunchItem registra defecto, localización, responsable, plazo y evidencia. El ciclo OPEN, IN_PROGRESS, READY_FOR_VERIFICATION y CLOSED requiere finalización explícita y verificación PASS independiente.",
                "Una deficiencia abierta bloquea la aceptación del sujeto relacionado. Su cierre conserva documentos de terminación y de verificación, sin certificar cantidades ni liberar un IWP.",
            ],
        ),
        (
            "18 Integración con Field Operations",
            [
                "La fuente de inspección es una ProductionRecord VERIFIED, incluido el retrabajo tipado por separado. La inspección en sitio puede ocurrir antes de la aprobación del parte diario; el lector Progress mantiene su requisito propio de parte aprobado.",
                "La corrección se ejecuta por un actor Field y debe existir después de la disposición. Quality solo la referencia. Los adaptadores identifican raíz y versión exacta para asociar NCR y mantener la trazabilidad del trabajo.",
            ],
        ),
        (
            "19 Integración con Engineering",
            [
                "Las inspecciones fijan una liberación IFC elegible al momento observado y el requisito correspondiente. La fecha de inspección no puede utilizar una revisión futura. Las revisiones sustituidas invalidan el uso vigente sin borrar historia.",
                "Engineering conserva la aprobación técnica del diseño. El resultado Quality y los documentos de ensayo no crean liberaciones IFC ni conceden autorización USE_AS_IS sin la decisión NCR específica.",
            ],
        ),
        (
            "20 Integración con AWP",
            [
                "AWP consulta una aceptación o un QualityReadinessAssessment persistido. ADOPT o RECONCILE usa la facultad awp.readiness.assess y el IWP exacto de la fuente para crear una evaluación nativa de readiness.",
                "La evidencia vigente se incorpora a los hashes de la evaluación. Si se vuelve obsoleta, la lectura deja de considerarla lista. El adaptador no despeja restricciones ni invoca release; conserva la decisión de paquete en AWP.",
                "Las referencias IWP y CWP fijan el contexto técnico del paquete, no el contador de evaluaciones de readiness. Una evaluación AWP no invalida por sí sola la evidencia que acaba de consumir. Cambiar el alcance técnico o sustituir el paquete sí exige revisión; las referencias históricas se verifican sin reescribir registros gobernados.",
            ],
        ),
        (
            "21 Integración con Progress",
            [
                "El consumo Quality vincula una aceptación a una medición pendiente ya existente, con la producción fijada, Scope y unidad exactos. No crea otra medición ni reserva cantidad por segunda vez. La aprobación continúa en el flujo nativo Progress.",
                "El perfil Progress admite quality_policy.require_acceptance_for_approval. Los perfiles publicados anteriores conservan su contenido y hash. Cuando la política exige aceptación, la aprobación valida vigencia y cobertura granular; la evidencia obsoleta requiere reconciliación explícita.",
                "La cobertura corresponde a las cantidades realmente adoptadas desde Field, separadas por producción, versión y hash. El avance histórico ya reconocido no se vuelve a exigir como producción nueva. Una aceptación de otro lote no puede completar el faltante y dos aceptaciones sin segmentación no duplican la cobertura disponible.",
            ],
        ),
        (
            "22 Integración con Contracts",
            [
                "El contrato de lectura expone NCR emitidas, inspecciones y ensayos cerrados y aceptaciones identificadas. El lector usa contracts.read y el workspace del contrato, sin conceder escritura sobre Quality.",
                "La consulta no emite Notice, Claim, Change Order ni Payment Certificate. Cualquier consecuencia posterior debe registrarse mediante el flujo contractual y sus permisos.",
            ],
        ),
        (
            "23 Integración con Procurement",
            [
                "Los adaptadores consultan material, requerimiento, recepción, aceptación y asignación canónicos. La inspección de recepción y la aceptación Quality conservan la identidad de la línea recibida.",
                "Las pruebas comparan hashes de las tablas nativas antes y después para detectar cambios logísticos indebidos. Las referencias de lote y los documentos no duplican recibos, cantidades de inventario o proveedores.",
            ],
        ),
        (
            "24 Límite con Schedule",
            [
                "Los vínculos WBS, Activity y Milestone exigen versión de cronograma aceptada y external_id. Son referencias de trazabilidad para inspecciones y lookahead.",
                "O3B no calcula CPM, no mueve fechas P6 y no deduce retrasos contractuales. El lector Schedule de evidencia Quality es informativo y no dispone de un comando de adopción que escriba el cronograma.",
            ],
        ),
        (
            "25 Evidencia documental CDE",
            [
                "Los planes, ITP, resultados, NCR, acciones, disposiciones y aceptaciones conservan document_id, attachment_id y hash. La revisión y el acceso se validan en CDE antes de utilizar la evidencia.",
                "No se duplican binarios. Un adjunto eliminado, ajeno o inválido no puede sostener una nueva aprobación. La interfaz conserva la diferencia entre cargar un documento y aprobar una inspección.",
            ],
        ),
        (
            "26 Configuración ADMIN y uso USER",
            [
                "Quality Management Profile utiliza AdminConfiguration con kind quality_management_profile, revisión, vigencia, hash y publicación independiente. Contiene catálogos de inspección, ensayo, puntos de control, resultados, severidad, disposición, acciones, punch y aceptación.",
                "Las rutas genéricas ADMIN remiten al contrato dedicado y no permiten modificar este perfil por un permiso de configuración global antiguo. USER utiliza el perfil publicado aplicable, sin editar plantillas ya ejecutadas.",
            ],
        ),
        (
            "27 Seguridad",
            [
                "Las rutas separan tenant, workspace activo, membresía y facultad específica. Las referencias externas se resuelven dentro del mismo contexto. La fuente fuera de alcance se oculta con 404; la falta de permiso se comunica como 403.",
                "Las escrituras exigen Idempotency-Key y, en transiciones o streams, If-Match. Un cuerpo diferente con la misma clave devuelve 409. Una versión vencida devuelve 412 y no modifica el registro.",
            ],
        ),
        (
            "28 Separación de funciones",
            [
                "El catálogo contempla quality_reporter, quality_inspector, quality_reviewer, quality_approver, quality_configurator, quality_publisher, ncr_owner y quality_manager. Los perfiles mantienen reglas específicas para aprobación de Plan e ITP, cierre de resultados, liberación de controles y aceptación.",
                "La disposición de NCR, la terminación de la acción y su verificación son decisiones independientes. Un actor Quality no obtiene facultades para escribir Progress, liberar AWP, generar Actual Cost, modificar contratos o escribir P6 por consultar sus fuentes.",
            ],
        ),
        (
            "29 Auditoría e inmutabilidad",
            [
                "QualityHistory y SecurityEvent registran actor, acción, entidad, workspace, versión, razón y estados anterior y nuevo. Las aceptaciones, decisiones de puntos de control, vínculos y decisiones consumidoras son append only.",
                "La protección existe tanto en servicios y eventos ORM como en PostgreSQL. Los triggers validan identidad, tenant y workspace de los padres. Un resultado terminal no puede actualizarse por una sentencia SQL directa.",
            ],
        ),
        (
            "30 API",
            [
                "El contrato principal reside en /api/v1/quality/projects/{workspace_id}. Incluye planes, ITP, ítems, solicitudes, inspecciones, ensayos, NCR, disposiciones, acciones correctivas, punch, aceptaciones, readiness, lookahead, trace e historia.",
                "Las rutas /{dominio}/projects/{workspace_id}/quality-adoptions separan consulta de fuente, historia y decisión. Progress, AWP y Cost tienen comandos limitados por su autoridad. Contracts, Field Operations y Schedule exponen consulta informativa.",
            ],
        ),
        (
            "31 Interfaz web",
            [
                "Quality Manager se integra al navigator operacional existente y su entrada requiere módulo habilitado y quality.read. La pantalla utiliza formularios para checklists congelados, mediciones múltiples, NCR, acciones, aceptación, lotes y evaluaciones persistidas.",
                "Los controles de comandos dependen de las facultades recibidas. Los paneles consumidores refrescan su contexto nativo después de guardar; un fallo de refresco se informa separado del resultado de escritura. El diseño reducido permite futura utilización en tablet y móvil sin prometer trabajo offline.",
                "Look-Ahead deriva solicitudes de inspección y ensayo, NCR, acciones, reinspecciones, HOLD o WITNESS sin decisión y aceptaciones pendientes. Aplica fechas y dimensiones operacionales canónicas antes de evaluar cada sujeto; consultar no crea evaluaciones, liberaciones ni aceptaciones.",
            ],
        ),
        (
            "32 Migración",
            [
                "Alembic 0081 crea diecisiete tablas Quality y protecciones SQL sobre el HEAD 0080. El arranque de la aplicación no ejecuta create_all para estas tablas ni rellena datos históricos.",
                "La secuencia real upgrade, downgrade vacío y upgrade se conserva en migration/round-trip.json. El downgrade revisa todas las tablas y rechaza eliminar hechos de Quality. Las claves circulares se retiran solo de las tablas vacías revisadas, sin un CASCADE general.",
            ],
        ),
        (
            "33 Validación PostgreSQL",
            [
                "Las cadenas críticas usan PostgreSQL 16 en el puerto aislado 5567 y tenants sintéticos. Los fixtures recorren los ciclos reales de Scope, Schedule, Cost, Engineering, Procurement y Field Operations antes de capturar Quality.",
                "El inventario de suites de este informe distingue pruebas aprobadas, fallidas y omitidas. Los primeros intentos y sus fallos permanecen en el historial de QA; solo los resultados finales respaldan la decisión de release.",
            ],
        ),
        (
            "34 Validación Chromium",
            [
                "La UAT utiliza Chromium y APIs reales sobre un proyecto sintético. Recorre publicación ADMIN, ITP, solicitud, inspección y ensayo, NCR, corrección Field, acción, reinspección, aceptación y decisiones Progress y AWP.",
                "La evidencia combina segmentos de la misma cadena persistente. Los intentos iniciales y las correcciones del arnés se conservan; no se presentan como una única ejecución continua aprobada. browser-summary.json identifica segmentos, pasos, capturas, errores e identidades verificadas. La vista móvil no representa sincronización offline.",
            ],
        ),
        (
            "35 Preservación del Proyecto 14",
            [
                "El Proyecto 14 se mantiene fuera de fixtures y escrituras. La observación independiente compara conteos y hashes legacy, workspace canónico y referencias antes y después del trabajo.",
                "La base habitual no recibe migraciones O3B en este procedimiento. Los resultados de preservación deben permanecer iguales para autorizar el cierre técnico del entorno aislado.",
            ],
        ),
        (
            "36 Rendimiento",
            [
                "Se miden tres lecturas de Dashboard, ITP Register, Inspection Queue, Test Register, NCR Register, Readiness, Lookahead, Trace y lookup de Progress y AWP. Cada resultado conserva muestras, mediana, bytes, filas y entorno.",
                "El seguimiento adicional de Contracts observa readiness y trace heredados. Estas mediciones locales no establecen un SLA ni justifican cerrar una deuda de latencia sin evidencia específica. Las consultas no deben crear decisiones ni hechos.",
            ],
        ),
        (
            "37 Deuda técnica",
            [
                "O2C-S3-01 y O2C-S3-02 mantienen su seguimiento de latencia y protecciones de padres simples. O3A-S3-UI01 y O3A-S3-01 conservan la limitación de refresco y recuperación de sus consumidores anteriores.",
                "Los nuevos paneles Quality distinguen comando guardado de refresco fallido. Esa mejora local no cierra por sí misma la deuda de un panel O3A que no fue modificado y revalidado. USE_AS_IS permanece condicionado al proveedor técnico NCR específico.",
            ],
        ),
        (
            "38 Defectos",
            [
                "La matriz de defectos conserva severidad, estado, evidencia y acción. Los fallos de preparación de fixtures por concurrencia del catálogo se distinguen de un fallo funcional de Quality y deben repetirse tras serializar la preparación.",
                "El release exige cero S1 y S2 abiertos. Los S3 y S4 solo son admisibles si no afectan autoridad, seguridad, integridad, trazabilidad o el camino crítico. Un caso aún no ejecutado no se presenta como aprobado.",
            ],
        ),
        (
            "39 Decisión de release",
            [
                display_status,
                "La validación completa exige los controles PostgreSQL, consumidores, negativos, regresión, Chromium, preservación y revisión documental. No se inicia automáticamente otra Wave. No se despliega producción ni se migra una base de producción con este trabajo.",
            ],
        ),
    ]


def domain_rows():
    rows = []
    for file in ("models.py", "execution_models.py", "consumer_models.py"):
        tree = ast.parse(
            (ROOT / "backend/app/modules/quality" / file).read_text("utf-8")
        )
        for node in tree.body:
            if not isinstance(node, ast.ClassDef):
                continue
            table, fields = None, []
            for item in node.body:
                if isinstance(item, ast.Assign) and any(
                    isinstance(target, ast.Name) and target.id == "__tablename__"
                    for target in item.targets
                ):
                    table = ast.literal_eval(item.value)
                if isinstance(item, ast.AnnAssign) and isinstance(
                    item.target, ast.Name
                ):
                    fields.append(item.target.id)
            if table:
                rows.append(
                    [
                        node.name,
                        table,
                        ", ".join(fields),
                        "tenant_id y project_workspace_id más padres canónicos",
                        "SQL scope guard y protección de terminal o append only",
                    ]
                )
    return rows


def matrix():
    from pypdf import PdfReader

    text = "\n".join(page.extract_text() for page in PdfReader(PROMPT).pages)
    requirements = re.findall(r"(?m)^(\d+)\. ([A-ZÁÉÍÓÚÑ0-9 /&()_—-]+)$", text)
    decision = read("release-decision.json")
    state = (
        "VALIDADO EN ENTORNO AISLADO"
        if status() in {MARKER, "VALIDADO EN ENTORNO AISLADO"}
        else "IMPLEMENTADO VALIDACIÓN EN CURSO"
    )
    data = {}

    def add(name, title, headers, rows):
        assert rows and all(len(row) == len(headers) for row in rows), name
        data[name] = {"title": title, "headers": headers, "rows": rows}

    add(
        "00_README",
        "Quality Management e Inspection O3B",
        ["Campo", "Valor"],
        [
            ["Fecha del informe", DATE],
            ["Estado del corte", status()],
            ["Baseline", BASELINE],
            ["Fuente", PROMPT.name + " apartados 1 a 68"],
            ["Entorno", "PostgreSQL 16 aislado 127.0.0.1 puerto 5567"],
            [
                "Uso de la matriz",
                "Referencias de implementación y resultados del corte. Los ejemplos funcionales proceden de fixtures reales.",
            ],
            ["Límite", "Sin despliegue de producción ni escrituras en Proyecto 14"],
            [
                "O3A",
                "Microcierre documental preservado en copias con historia y deudas originales",
            ],
        ],
    )
    add(
        "01_REQUIREMENTS",
        "Requisitos del prompt y control de cumplimiento",
        [
            "ID",
            "Requisito",
            "Implementación o autoridad",
            "Control",
            "Evidencia",
            "Estado",
        ],
        [
            [
                f"O3B-{int(number):02}",
                title,
                *requirement_reference(int(number)),
                state,
            ]
            for number, title in requirements
        ],
    )
    authorities = [
        [
            "Field Operations",
            "Producción y retrabajo",
            "Quality consulta ProductionRecord VERIFIED",
            "No escribe hechos Field",
        ],
        [
            "Engineering",
            "Diseño y IFC",
            "Requisito y liberación vigente al inspeccionar",
            "Resultado PASS no aprueba diseño",
        ],
        [
            "Quality",
            "Inspección ensayo NCR aceptación",
            "ITP resultado control y aceptación explícitos",
            "No transfiere autoridad",
        ],
        [
            "AWP",
            "Readiness restricciones release",
            "Decisión Quality nativa y evaluación AWP",
            "No libera IWP automáticamente",
        ],
        [
            "Progress",
            "Medición certificación y avance",
            "Aceptación ligada a medición pendiente",
            "No crea cantidad adicional",
        ],
        [
            "Procurement",
            "Recepción material logística",
            "Línea real y aceptación logística como fuente",
            "No crea inventario",
        ],
        [
            "Contracts",
            "Notices cambios certificados",
            "Consulta NCR resultado y aceptación",
            "No crea consecuencia contractual",
        ],
        [
            "Cost",
            "Presupuesto compromisos Actual Cost",
            "Clasificación explícita CBS Code Control Account",
            "No crea Actual Cost",
        ],
        [
            "P6",
            "Cronograma aceptado",
            "WBS Activity Milestone como referencias",
            "No modifica fechas",
        ],
        [
            "Forecast",
            "Forecast aprobado",
            "Se conserva autoridad existente",
            "Sin reconocimiento automático",
        ],
        [
            "CDE",
            "Documentos y adjuntos",
            "Identidad revisión hash y acceso",
            "No duplica binarios",
        ],
    ]
    add(
        "02_AUTHORITY",
        "Autoridades conservadas",
        ["Dominio", "Autoridad", "Integración O3B", "Límite"],
        authorities,
    )
    add(
        "03_DOMAIN_MODEL",
        "Modelo físico Quality",
        ["Entidad", "Tabla", "Campos propios", "Relaciones", "Protección"],
        domain_rows(),
    )
    flows = [
        [
            "Plan e ITP",
            "DRAFT SUBMITTED APPROVED",
            "Autor distinto del aprobador",
            "Sucesor por revisión",
        ],
        [
            "InspectionRequest",
            "DRAFT SUBMITTED SCHEDULED IN_INSPECTION COMPLETED",
            "Inspector asignado y fuente vigente",
            "Inspección nueva por solicitud",
        ],
        [
            "Inspection y Test",
            "DRAFT SUBMITTED CLOSED",
            "Respuestas mediciones CDE y cierre independiente",
            "FAIL terminal preservado",
        ],
        [
            "ControlPoint",
            "RELEASED o WAIVED",
            "Último resultado aplicable y política de punto",
            "No es liberación AWP",
        ],
        [
            "NCR",
            "DRAFT ISSUED UNDER_REVIEW DISPOSITIONED CORRECTED VERIFIED CLOSED",
            "Disposición corrección y verificación explícitas",
            "No cierra con acción sola",
        ],
        [
            "Acción",
            "OPEN IN_PROGRESS COMPLETED VERIFIED CLOSED",
            "Field rework y reinspección independiente",
            "No reemplaza NCR",
        ],
        [
            "Punch",
            "OPEN IN_PROGRESS READY_FOR_VERIFICATION CLOSED",
            "CDE finalización y verificación PASS",
            "Abierto bloquea aceptación",
        ],
        [
            "Acceptance",
            "APPROVED y sucesora explícita",
            "Readiness READY cantidad y unidad exactas",
            "Hecho inmutable",
        ],
    ]
    add(
        "04_WORKFLOWS",
        "Flujos implementados",
        ["Objeto", "Secuencia", "Precondición", "Preservación"],
        flows,
    )
    add(
        "05_STATUSES",
        "Estados de resultados y vigencia",
        ["Familia", "Estado", "Significado", "Ejemplo"],
        [
            ["Resultado", value, meaning, "InspectionRecord o TestRecord cerrado"]
            for value, meaning in [
                ("PASS", "Criterios satisfechos"),
                ("FAIL", "Incumplimiento conservado"),
                ("CONDITIONAL", "No equivale a aprobación completa"),
                ("NOT_APPLICABLE", "Control no aplicable según política"),
            ]
        ]
        + [
            ["Readiness", value, meaning, "Evaluación del ITP y sujeto exacto"]
            for value, meaning in [
                ("READY", "Controles completos sin bloqueos"),
                ("PARTIALLY_READY", "Controles parciales o pendientes"),
                ("NOT_READY", "No cumple precondiciones"),
                ("STALE", "Cambió la base aplicable"),
                ("BROKEN_REFERENCE", "Referencia conocida no resoluble"),
            ]
        ],
    )
    add(
        "06_PERMISSIONS",
        "Facultades Quality y consumidores",
        ["Rol o facultad", "Uso", "Ejemplo de comando", "Límite"],
        [
            [
                "quality_reporter",
                "Plan ITP solicitudes NCR",
                "POST inspection-requests",
                "No cierra su inspección",
            ],
            [
                "quality_inspector",
                "Programar y ejecutar",
                "POST inspections",
                "No aprueba su resultado",
            ],
            [
                "quality_reviewer",
                "Cerrar y verificar",
                "POST inspections id actions close",
                "No verifica su propia terminación",
            ],
            [
                "quality_approver",
                "Plan ITP controles aceptación",
                "POST acceptances",
                "SoD de inspector y aprobador",
            ],
            [
                "quality_configurator",
                "Preparar perfil",
                "POST admin profiles",
                "No autopublica",
            ],
            [
                "quality_publisher",
                "Publicar perfil",
                "POST profiles id publish",
                "Sin captura de obra",
            ],
            [
                "ncr_owner",
                "Responsable de corrección",
                "POST corrective-actions id actions complete",
                "No verifica su finalización",
            ],
            [
                "quality_manager",
                "Gestión y readiness",
                "POST readiness assess",
                "No recibe autoridad Progress o AWP release",
            ],
            [
                "progress.capture",
                "Vincular aceptación a medición pendiente",
                "POST progress quality-adoptions",
                "No aprueba avance",
            ],
            [
                "awp.readiness.assess",
                "Decisión de evidencia Quality",
                "POST awp quality-adoptions",
                "No libera IWP",
            ],
            [
                "cost.mapping.edit",
                "Clasificación de evidencia",
                "POST cost quality-adoptions",
                "No registra Actual Cost",
            ],
        ],
    )
    policy = ast.parse(
        (ROOT / "backend/app/modules/quality/policy.py").read_text("utf-8")
    )
    sod = next(
        ast.literal_eval(node.value)
        for node in policy.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "SOD_KEYS"
            for target in node.targets
        )
    )
    sod_examples = {
        "plan_author_cannot_approve": "Autor del plan distinto de quien lo aprueba",
        "itp_author_cannot_approve": "Autor del ITP distinto de quien lo aprueba",
        "requester_cannot_inspect": "Solicitante distinto del inspector asignado",
        "inspector_cannot_close": "Inspector distinto de quien cierra el resultado",
        "control_releaser_cannot_be_inspector": "Inspector distinto de quien libera HOLD o WITNESS",
        "ncr_author_cannot_dispose": "Autor de NCR distinto de quien aprueba su disposición",
        "ncr_author_cannot_verify": "Autor de NCR distinto de quien verifica la corrección",
        "ncr_disposer_cannot_verify": "Aprobador de disposición distinto de quien verifica NCR",
        "disposition_author_cannot_approve": "Proponente de disposición distinto de su aprobador",
        "action_completer_cannot_verify": "Quien completa la acción no verifica su trabajo",
        "punch_author_cannot_verify": "Autor del punch distinto de su verificador",
        "punch_owner_cannot_verify": "Responsable del punch distinto de su verificador",
        "acceptance_inspector_cannot_approve": "Inspector distinto del aprobador de aceptación",
        "acceptance_itp_author_cannot_approve": "Autor del ITP distinto del aprobador de aceptación",
        "acceptance_result_approver_cannot_approve": "Revisor del resultado distinto del aprobador de aceptación",
    }
    assert set(sod_examples) == sod
    add(
        "07_SOD",
        "Reglas de separación de funciones",
        ["Regla", "Control", "Respuesta", "Ejemplo"],
        [
            [
                key,
                "Comparar actor con autores o decisores fijados",
                "403 cuando la política exige independencia",
                sod_examples[key],
            ]
            for key in sorted(sod)
        ],
    )
    add(
        "08_INTEGRATIONS",
        "Contratos cruzados y límites",
        ["Consumidor", "Fuente", "Decisión", "Efecto permitido"],
        [
            [
                "Progress",
                "ACCEPTANCE",
                "ADOPT REJECT RECONCILE",
                "Vincular evidencia sin crear medición",
            ],
            [
                "AWP",
                "READINESS ACCEPTANCE NCR",
                "ADOPT REJECT RECONCILE",
                "Evaluación nativa sin release ni clear automático",
            ],
            [
                "Cost",
                "NCR ACCEPTANCE INSPECTION TEST",
                "ADOPT REJECT RECONCILE",
                "Clasificar sin Actual Cost",
            ],
            [
                "Contracts",
                "NCR ACCEPTANCE INSPECTION TEST",
                "Solo consulta",
                "Fuente documental para decisión contractual propia",
            ],
            [
                "Field Operations",
                "ACCEPTANCE READINESS",
                "Solo consulta",
                "Conservar hechos ejecutados",
            ],
            [
                "Schedule",
                "NCR ACCEPTANCE READINESS",
                "Solo consulta",
                "Trazabilidad sin cambiar fechas",
            ],
        ],
    )
    consumer = read("consumer-evidence.json")
    add(
        "09_FIELD_TRACEABILITY",
        "Hechos Field y corrección",
        ["Fuente", "Estado exigido", "Identidad fijada", "Ejemplo implementado"],
        [
            [
                "ProductionRecord",
                "VERIFIED",
                "ID versión hash Scope IWP cantidad unidad",
                "FIELD_PRODUCTION usado por inspección de instalación",
            ],
            [
                "Rework ProductionRecord",
                "VERIFIED REWORKED",
                "Original y raíz de producción",
                "Creado después de la disposición REWORK",
            ],
            [
                "DailyConstructionReport",
                "APPROVED para consumo Progress",
                "Parte y sus fuentes fijadas",
                "La inspección en sitio no exige aprobar antes el parte",
            ],
            [
                "FieldEquipmentReference",
                "AVAILABLE",
                "Equipo externo y fuente de calibración",
                "Calibración válida al momento del ensayo",
            ],
        ],
    )
    add(
        "10_ENGINEERING_TRACEABILITY",
        "Requisitos Engineering",
        ["Fuente", "Identidad", "Control temporal", "Ejemplo"],
        [
            [
                "IFC_RELEASE",
                "ID versión hash liberación y revisión",
                "Elegible al inspeccionar",
                "ITP de instalación con IFC real",
            ],
            [
                "ENGINEERING_REVISION",
                "ID y hash aprobado",
                "Aprobación no posterior al instante observado",
                "Metadatos no sustituyen IFC",
            ],
            [
                "USE_AS_IS",
                "Decisión técnica ligada a NCR",
                "Bloqueo si el proveedor no existe",
                "IFC genérico rechazado como aprobación USE_AS_IS",
            ],
        ],
    )
    add(
        "11_AWP_TRACEABILITY",
        "Decisión Quality bajo autoridad AWP",
        ["Campo", "Valor de ejemplo", "Regla"],
        [
            [
                "source_entity_type",
                "READINESS",
                "ID de QualityReadinessAssessment persistido",
            ],
            [
                "source_entity_id",
                consumer.get("assessment_id", "Evaluación creada por el fixture real"),
                "Mismo tenant y workspace",
            ],
            [
                "work_package_id",
                "IWP exacto de la fuente",
                "Sin extrapolar a otro paquete",
            ],
            ["decision", "ADOPT", "Permiso awp.readiness.assess"],
            [
                "Efecto",
                "Evaluación AWP con hash Quality",
                "Sin clear ni release automáticos",
            ],
        ],
    )
    add(
        "12_PROGRESS_TRACEABILITY",
        "Aceptación ligada a medición nativa",
        ["Campo", "Valor de ejemplo", "Regla"],
        [
            ["source_entity_type", "ACCEPTANCE", "Aceptación vigente"],
            [
                "source_entity_id",
                consumer.get("acceptance_id", "Aceptación creada por el fixture real"),
                "Hash y versión fijados",
            ],
            [
                "measurement_id",
                "Medición pendiente creada por Progress",
                "Producción Scope y unidad exactos",
            ],
            [
                "quality_policy",
                "require_acceptance_for_approval true",
                "Política nativa opcional con compatibilidad anterior",
            ],
            [
                "Efecto",
                "Solo vínculo de evidencia",
                "Certificación y aprobación permanecen en Progress",
            ],
        ],
    )
    add(
        "13_CONTRACTS_TRACEABILITY",
        "Fuentes Quality para Contracts",
        ["Fuente", "Estado requerido", "Lectura", "Hechos que no se crean"],
        [
            [
                "NCR",
                "Emitida o posterior",
                "contracts quality-adoptions lookup",
                "Notice Claim Change Certificate",
            ],
            [
                "Inspection y Test",
                "CLOSED",
                "Resultado y requisito fijados",
                "Aprobación de pago",
            ],
            [
                "QualityAcceptance",
                "Identidad y vigencia expuestas",
                "Aceptación exacta y evidencia CDE",
                "Cambio contractual automático",
            ],
        ],
    )
    add(
        "14_PROCUREMENT_TRACEABILITY",
        "Materiales recibidos y calidad técnica",
        ["Objeto canónico", "Lectura Quality", "Validación", "Preservación"],
        [
            [
                "MaterialReceiptLine",
                "Sujeto de inspección RECEIVING",
                "Material unidad cantidad y fecha real",
                "No se duplica receipt",
            ],
            [
                "MaterialAcceptance",
                "Aceptación logística como fuente",
                "Hash y cantidad aceptada",
                "No se confunde con aceptación Quality",
            ],
            [
                "MaterialAllocation",
                "IWP y cantidad asignada",
                "Vigencia e identidad recibida",
                "No modifica stock ni logística",
            ],
            [
                "QualityMapping",
                "Lote batch heat serial a producción",
                "Pins actuales CDE y stream versionado",
                "Sin maestro paralelo de lotes",
            ],
        ],
    )
    add(
        "15_API",
        "Rutas representativas y comandos",
        ["Método", "Ruta relativa", "Facultad", "Control"],
        [
            [
                "GET",
                "/quality/projects/ws/itps",
                "quality.read",
                "Tenant workspace y paginación",
            ],
            [
                "POST",
                "/quality/projects/ws/inspection-requests",
                "quality.inspection.request",
                "Fuente e ITP actuales e idempotencia",
            ],
            [
                "POST",
                "/quality/projects/ws/inspections/id/actions",
                "quality.inspection.close",
                "If Match SoD y checklist",
            ],
            [
                "POST",
                "/quality/projects/ws/ncrs/id/actions",
                "quality.ncr según transición",
                "Flujo protegido y evidencia",
            ],
            [
                "POST",
                "/quality/projects/ws/acceptances",
                "quality.acceptance.approve",
                "Controles completos cantidad unidad y CDE",
            ],
            ["GET", "/quality/projects/ws/readiness", "quality.read", "Sin escrituras"],
            [
                "POST",
                "/quality/projects/ws/readiness/assess",
                "quality.readiness.assess",
                "Snapshot explícito y stream ETag",
            ],
            [
                "POST",
                "/progress/projects/ws/quality-adoptions",
                "progress.capture",
                "No crea cantidad",
            ],
            [
                "POST",
                "/awp/projects/ws/quality-adoptions",
                "awp.readiness.assess",
                "No libera paquete",
            ],
        ],
    )
    rows = tests()
    add(
        "16_TESTS",
        "Resultados de las suites registradas",
        ["Suite o evidencia", "Casos", "Fallos", "Errores", "Omitidos", "Resultado"],
        rows or [["Validación en curso", 0, 0, 0, 0, "PENDIENTE"]],
    )
    add(
        "17_DEFECTS",
        "Defectos y acciones del corte",
        ["ID", "Severidad", "Descripción", "Estado", "Acción o evidencia"],
        decision.get(
            "defects",
            [
                [
                    "O3B-VALIDATION",
                    "PENDIENTE",
                    "Faltan resultados finales de controles obligatorios",
                    "OPEN",
                    "No emitir marcador de release hasta completar evidencia",
                ]
            ],
        ),
    )
    add(
        "18_TECHNICAL_DEBT",
        "Deuda heredada y límites conservados",
        ["ID", "Dominio", "Descripción", "Estado", "Seguimiento"],
        [
            [
                "O2C-S3-01",
                "Contracts",
                "Latencia readiness y trace",
                "MONITORED NOT CLOSED",
                "Tres muestras por consulta sin SLA",
            ],
            [
                "O2C-S3-02",
                "Contracts",
                "Protección de padres simples heredada",
                "RETAINED",
                "O3B añade guardas propias sin cambiar esquema O2C",
            ],
            [
                "O3A-S3-UI01",
                "Field consumidores",
                "Refresco del contexto nativo anterior",
                "RETAINED",
                "No cerrar por mejorar solo los paneles Quality",
            ],
            [
                "O3A-S3-01",
                "Field consumidores",
                "Recuperación de evidencias y drafts anteriores",
                "RETAINED",
                "Preservar diagnóstico del release O3A",
            ],
            [
                "O3B-USE-AS-IS",
                "Engineering",
                "Proveedor de decisión técnica ligada a NCR",
                "FAIL CLOSED",
                "No usar IFC genérico como sustituto",
            ],
            [
                "O3B-MATERIAL-CORRECTION",
                "Procurement",
                "Proveedor tipado de corrección logística de material",
                "FAIL CLOSED",
                "No cerrar NCR de material con un retrabajo Field de ID coincidente",
            ],
        ],
    )
    add(
        "19_RELEASE_CRITERIA",
        "Criterios de cierre O3B",
        ["Criterio", "Evidencia requerida", "Estado del corte"],
        [
            ["Microcierre O3A", "Copias y hashes históricos conservados", "COMPLETADO"],
            [
                "Migración PostgreSQL",
                "Upgrade downgrade upgrade y rechazo populated",
                state,
            ],
            ["Camino central", "Inspección y aceptación con decisión Progress", state],
            ["Camino NCR", "REWORK real reinspección y cierre explícito", state],
            [
                "Materiales",
                "Recepción real y aceptación Quality sin logística mutada",
                state,
            ],
            ["AWP y Contracts", "Decisiones y lecturas bajo autoridad propia", state],
            ["Seguridad y negativos", "403 404 409 412 y SQL inmutable", state],
            ["Regresión", "O1 O2 O3A relevante y consumidores", state],
            ["Chromium", "ADMIN USER móvil y cadena crítica", state],
            ["Proyecto 14", "Conteos y hashes antes después iguales", state],
            ["Defectos", "Cero S1 y S2 abiertos", state],
            [
                "Decisión",
                "Solo emitir marcador con todos los controles aprobados",
                status(),
            ],
        ],
    )
    assert len(data) == 20
    return data
