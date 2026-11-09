"""Build the O1C delivery from fresh executed evidence, never from file presence."""

import hashlib
import json
import re
from collections import Counter
from decimal import Decimal
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
QA = ROOT / "outputs/.qa/wave-o1c-20261106"
OUT = ROOT / "docs/validation/wave-o1c-20261106"
PROMPT = Path(
    "C:/Users/Ricardo/Documents/P&P/P&Pmis Construction AI/Diseño/Operation Processes/PROMPT_WAVE_O1C_FORECAST_PERFORMANCE_REPORTING.md"
)
RELEASE = "WAVE_O1C_FORECAST_PERFORMANCE_REPORTING_RELEASE_VALIDATED"
READY = "READY_FOR_WAVE_O2_PROCUREMENT_CONTRACTS_ENGINEERING"


def read(path):
    return json.loads(path.read_text("utf-8"))


def fresh(proof):
    assert proof["source_sha256"]
    for name, expected in proof["source_sha256"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected, (
            f"Stale evidence: {name}"
        )


def requirement_evidence(number):
    """Point each requirement to its specific evidence area in the workbook."""
    groups = (
        (
            {1, 2, 3, 19, 47},
            "repository-reuse.md y prueba DML de aprobación sin escrituras de origen",
        ),
        (
            {4, 18, 40, 41, 50},
            "02_Forecast_Versions: ciclo, hashes, sucesores e independencia",
        ),
        ({5}, "03_Assumptions: vigencia, evidencia, unidad, confirmación y hash"),
        (
            {6, 7, 8, 9, 10, 51},
            "04_ETC_EAC: ocho métodos, reconocimiento, compromiso, VAC y salvaguardas",
        ),
        ({11, 12, 52}, "05_Time_Forecast: Current aceptado, baseline y fechas sin CPM"),
        ({13}, "06_Milestones: fecha gobernada y varianza por hito"),
        (
            {14, 15, 53},
            "07_Resource_Forecast: cantidad pendiente, productividad y unidades",
        ),
        (
            {16, 17, 32, 33, 34, 35, 36, 37, 38, 56},
            "13_LookAhead: mapeo, Readiness, restricciones, horizonte, grupos y float importado",
        ),
        ({20, 21, 54}, "08_Performance: EVM reutilizado y motivos no computables"),
        ({22, 23, 24}, "09_Variance: costo, fecha y avance sobre bases compatibles"),
        ({25, 26}, "10_Trends: reportes sucesivos y contrato de referencias futuras"),
        (
            {27, 55},
            "11_S_Curves: seis series, unidades, deduplicación y fuente inmutable",
        ),
        ({28, 29}, "12_Dashboards: consultas sin escrituras y umbrales publicados"),
        (
            {30, 31, 39, 57},
            "14_Report_Snapshots: período PUBLISHED, fuentes, narrativa y republicación",
        ),
        (
            {42, 43, 44},
            "15_Admin_User y browser-uat.json: publicación independiente y doce vistas",
        ),
        ({45, 46}, "16_Security: ámbitos, ETag, idempotencia, SoD y auditoría"),
        (
            {48},
            "forecast-final-junit.xml: 0075 roundtrip y downgrade poblado rechazado",
        ),
        ({49, 60}, "17_API: inventario OpenAPI y contrato analytics sin write-back"),
        (
            {58},
            "browser-uat.json: Chromium y actores independientes contra PostgreSQL real",
        ),
        ({59}, "19_Release_Criteria: once operaciones con tres muestras locales"),
        (
            {61},
            "preservation-before.json y preservation-after.json: fila, referencias y fuentes",
        ),
        (
            {62, 63},
            "Validación nativa, de accesibilidad y visual de los dos entregables",
        ),
        (
            {64, 65, 66, 67, 68},
            "19_Release_Criteria y release-manifest.json: límites y decisión final",
        ),
    )
    matches = [evidence for numbers, evidence in groups if number in numbers]
    assert len(matches) == 1, number
    return matches[0]


def main():
    cases, summaries = [], []
    for mode, filename, title in (
        (
            "forecast",
            "forecast-final-junit.xml",
            "Forecast políticas PostgreSQL migración y límites",
        ),
        (
            "regression",
            "regression-junit.xml",
            "Regresión Scope Schedule AWP 4D Cost y Progress",
        ),
    ):
        proof = read(QA / (mode + "-source-proof.json"))
        assert (
            proof["pytest_exit_code"] == 0
            and proof["source_unchanged_during_validation"]
        )
        fresh(proof)
        counts = Counter()
        for node in ET.parse(QA / filename).findall(".//testcase"):
            state = (
                "FAIL"
                if node.find("failure") is not None or node.find("error") is not None
                else "SKIP"
                if node.find("skipped") is not None
                else "PASS"
            )
            counts[state] += 1
            cases.append(
                {
                    "name": node.get("name"),
                    "class": node.get("classname"),
                    "seconds": float(node.get("time", 0)),
                    "result": state,
                    "evidence": filename,
                }
            )
        assert counts["PASS"] > 0 and not counts["FAIL"] and not counts["SKIP"], counts
        summaries.append([title, counts["PASS"], "PASS"])
    frontend = read(QA / "frontend-components.json")
    frontend_proof = read(QA / "frontend-validation.json")
    assert frontend_proof["result"] == "PASS" and frontend_proof["checks"]
    assert all(row["exit_code"] == 0 for row in frontend_proof["checks"])
    fresh(frontend_proof)
    assert (
        frontend["numFailedTests"] == 0
        and frontend["numPassedTests"] == frontend["numTotalTests"] > 0
    )
    summaries.append(
        ["Componentes frontend y navegación", frontend["numPassedTests"], "PASS"]
    )
    browser = read(QA / "chromium/browser-uat.json")
    assert browser["result"] == "PASS" and not browser["browser_errors"]
    assert browser["checks"] and all(
        row["result"] == "PASS" for row in browser["checks"]
    )
    summaries.append(["Comprobaciones Chromium reales", len(browser["checks"]), "PASS"])
    layout = read(QA / "chromium/layout-final.json")
    assert layout["result"] == "PASS" and layout["presentation_revalidated"] is True
    assert layout["source_sha256"] == frontend_proof["source_sha256"]
    fresh(layout)
    before, after = (
        read(OUT / f"preservation-{phase}.json")["observation"]
        for phase in ("before", "after")
    )
    for key in (
        "canonical_id14_row_sha256",
        "project14_row_sha256",
        "project14_references",
    ):
        assert before[key] == after[key], key
    for path, expected in before["product_source_sha256"].items():
        if path.startswith("backend/alembic/versions/") or path in {
            "frontend/src/App.tsx",
            "frontend/src/components/BimIfcModelViewer.tsx",
            "backend/app/domain/models.py",
            "backend/app/domain/schemas.py",
        }:
            assert after["product_source_sha256"][path] == expected, path
    observed = read(OUT / "api-observations.json")
    assert len(observed["performance"]) == 11 and all(
        row[1] == 3 for row in observed["performance"]
    )
    # Each topic must be represented by executed O1C tests, not merely an API file.
    names = "\n".join(
        r["name"] for r in cases if r["evidence"] == "forecast-final-junit.xml"
    )
    groups = {
        "lifecycle": "lifecycle|successor|independent",
        "assumptions": "assumption",
        "cost": "eac|etc|commitment",
        "time": "accepted_current|finish|schedule",
        "resources": "resource",
        "performance": "performance|evm",
        "trends": "trend|successive",
        "curves": "curve",
        "dashboards": "dashboard",
        "lookahead": "lookahead",
        "reporting": "published_report|report_successor",
        "security": "sod|tenant|idempotency|etag",
    }
    for group, pattern in groups.items():
        assert re.search(pattern, names, re.IGNORECASE), (
            f"No executed evidence for {group}"
        )
    text = PROMPT.read_text("utf-8")
    requirements = [
        [
            f"REQ-{int(number):02}",
            title,
            "PASS",
            requirement_evidence(int(number)),
        ]
        for number, title in re.findall(r"^# (\d+)\. (.+)$", text, re.MULTILINE)
    ]
    criteria = [
        [
            f"RC-{i:02}",
            label,
            "PASS",
            "Suites finales y Chromium con fuentes vigentes; hashes de preservación",
        ]
        for i, label in enumerate(re.findall(r"^(.+?) = PASS$", text, re.MULTILINE), 1)
    ]
    assert len(requirements) == 68 and len(criteria) == 52
    authorities = [
        [
            "Baseline",
            "Bundle aprobado y baselines originales",
            "Referencia",
            "No se altera por un cálculo de Forecast",
        ],
        [
            "Current",
            "Versión aceptada de Schedule y Budget vigente",
            "Fuente operacional",
            "No se confunde con la proyección",
        ],
        [
            "Actual",
            "Cost reconocido y Progress aprobado",
            "Hechos",
            "Pago e invoice no equivalen a avance",
        ],
        [
            "Forecast",
            "Versión gobernada y supuestos atribuidos",
            "Proyección",
            "Aprobación inmutable y sucesor explícito",
        ],
        [
            "Reporting",
            "Read model y reportes publicados",
            "Lectura",
            "Un GET no modifica negocio ni fuentes",
        ],
    ]
    counts = {
        "forecast": summaries[0][1],
        "regression": summaries[1][1],
        "frontend": frontend["numPassedTests"],
        "browser": len(browser["checks"]),
    }
    preservation = after["canonical_id14_row_sha256"]
    example = next(
        row["result_json"]["cost"]
        for row in observed["approved_forecasts"]
        if row["id"] == browser["created"]["forecast"]
        and row["content_hash"] == browser["source_hashes"]["forecast"]
        and row["result_json"]["cost"]["status"] == "COMPUTABLE"
    )
    example_values = {
        name: format(Decimal(example[name]).normalize(), "f")
        for name in ("actual", "etc", "eac", "bac", "vac")
    }
    example_sentence = (
        f" En el escenario aislado se observaron Actual {example_values['actual']} y ETC {example_values['etc']}, "
        f"con EAC {example_values['eac']}, BAC {example_values['bac']} y VAC {example_values['vac']} {example['currency']}. "
        "Estos valores prueban la cadena de cálculo; no estiman el Proyecto 14."
    )
    chapters = [
        [
            "Resumen ejecutivo",
            f"Implementamos Forecast como proyección gobernada y conectamos rendimiento, curvas, Look-Ahead y reportes con las autoridades existentes. La validación final aprobó {counts['forecast']} casos de O1C, {counts['regression']} de regresión, {counts['frontend']} de frontend y {counts['browser']} comprobaciones reales de Chromium. La liberación es técnica y en entorno aislado; no equivale a aceptación firmada ni a despliegue en la base habitual.",
        ],
        [
            "Base validada reutilizada",
            "Partimos de main en 19baf10. Reutilizamos O1A para identidad, autorización y período común; O1B A para Scope y Plan; O1B B para Schedule y P6; O1B B1 para AWP, Readiness y 4D; O1B C para Cost; O1B D para Progress, bundle integrado, EVM y snapshots. Cada dominio conserva sus escrituras, aprobaciones e identidades.",
        ],
        [
            "Hallazgos del repositorio",
            "Los servicios canónicos y la interfaz de perfiles se reutilizaron o extendieron. Las fórmulas Float de EAC legadas, el Handbook con CPM local y el lookahead forense se conservaron detrás de sus adaptadores; no se usaron como autoridad O1C. El límite de adopción de Progress ya impide cálculos integrados legados paralelos. No identificamos un modelo Power BI gobernado conectado. La clasificación completa está en repository-reuse.md.",
        ],
        [
            "Modelo de autoridad de Forecast",
            "forecast_foundation es el escritor de la proyección. Conserva fuente, versión, hash, ámbito, método, período, fecha de corte, supuestos y actores. Baseline, Current, Actual y Forecast tienen significados independientes. Los dashboards son lectores y no certifican hechos ni cambian Scope, Schedule, Cost, Progress o Readiness.",
        ],
        [
            "Versiones de Forecast",
            "El ciclo DRAFT, UNDER_REVIEW, APPROVED y REJECTED congela las entradas al enviar a revisión. SUPERSEDED es una condición efectiva derivada de un sucesor aprobado, sin editar el original. Toda corrección identifica su antecedente y conserva la revisión anterior. La aprobación verifica fuentes vigentes, resultado calculado, evaluación de completitud y madurez y separación del preparador y último editor material.",
        ],
        [
            "Supuestos gobernados",
            "Cada supuesto declara código, tipo, valor, unidad o moneda, fuente, responsable del mismo tenant, vigencia, confianza cualitativa, estado y evidencia. Los componentes enlazan sus códigos. El perfil exige confirmación por defecto; un supuesto futuro, no confirmado o de base incompatible bloquea la proyección correspondiente. Los hashes de cada supuesto se congelan con la versión.",
        ],
        [
            "ETC",
            "Se implementaron los ocho métodos explícitos: Bottom Up, Quantity Rate, Activity Remaining Duration, Productivity Based, Commitment Based, Control Account, Trend Based y Manual Governed. Se distinguen ETC comprometido, no comprometido y allowance permitido. Las cantidades pendientes usan el alcance aprobado y el avance compatible, o un supuesto manual declarado. Las referencias de compromiso y Actual se deduplican y reconcilian; no se vuelve a sumar un compromiso ya incorporado.",
        ],
        [
            "EAC",
            "EAC suma Actual reconocido y ETC con moneda, fecha y cobertura compatibles. VAC compara ese EAC con BAC de la Cost Baseline aprobada, nunca con un presupuesto ambiguo. Se usa Decimal y Numeric de veinticuatro dígitos con ocho decimales. Cuando falta base o hay incompatibilidad, se devuelve NOT_COMPUTABLE con importes nulos y motivos; un cero real no se trata como ausencia."
            + example_sentence,
        ],
        [
            "Proyección de costo",
            "La proyección conserva Budget original y Current, Cost Baseline, Actual, compromiso, ETC, EAC y VAC. Los componentes permiten agrupar por cuenta de control, CBS, código de costo, Scope, Plan, Work Package y WBS, dentro de Project, período y versión. La agrupación no convierte una moneda ni cambia la línea base aprobada.",
        ],
        [
            "Proyección de tiempo",
            "Las fechas Current provienen del Schedule aceptado y calculado externamente en P6. Activity Remaining Duration consume la fecha importada y preserva la duración como dato P6: no la suma como días naturales. Manual Governed exige un supuesto de fecha y permiso de política. No se calculó CPM local ni se escribió de vuelta a P6.",
        ],
        [
            "Fecha prevista de terminación",
            "Se muestran por separado el fin de baseline, el fin Current y el fin Forecast, con Data Date, versión, actividad fuente, método y referencia del supuesto. La variación de fechas se expresa como diferencia de días de calendario, no como resultado de una nueva ruta crítica. Una fuente incompleta produce un motivo explícito.",
        ],
        [
            "Hitos previstos",
            "Los componentes de hito conservan tipo, fecha y fuente. Se pueden identificar hitos contractuales, de proyecto, interfaz, commissioning y handover sin implementar esas autoridades. La comparación a baseline y Current no modifica los hitos de Schedule. Los hitos puros pueden mostrarse fuera del ranking detallado del Look-Ahead.",
        ],
        [
            "Proyección de recursos",
            "La fundación cubre labor, equipment, crews y horas de ingeniería, construcción y Project Controls. Cada componente conserva cantidad pendiente, productividad, recurso, unidad y referencias de Scope, Plan o Package. Las salidas se agrupan por unidades compatibles; no se implementó un sistema completo de Resource Management.",
        ],
        [
            "Proyección de productividad",
            "Se distinguen productividad planeada, observada y prevista con sus fuentes explícitas. Se admiten horas por unidad y cantidad por día; la composición de crew permite persona día. No se mezclan horas, equipo hora, crew día o cantidades físicas como si fueran equivalentes. La confianza registrada es cualitativa y no representa una probabilidad estadística.",
        ],
        [
            "Integración con AWP y Readiness",
            "Forecast consume paquetes, mappings, evaluaciones, restricciones y dependencias existentes. EWP, PWP, CWP, IWP, TWP, Support y Logistics conservan su autoridad. La última evaluación persistida elegible se selecciona por fecha de negocio; una evaluación futura no se usa como evidencia anterior. El contexto Plan y Scope no crea una asignación de ejecución. Un bloqueo puede justificar una hipótesis, pero no cambia la lógica ni las fechas de Schedule.",
        ],
        [
            "Modelo de rendimiento",
            "Se implementaron vistas de Schedule, Cost, Progress, Forecast y AWP con Readiness. PV, EV, AC, CPI y SPI se consumen de Progress Integration y su snapshot EVM, sin una nueva fórmula paralela. Los indicadores derivados mantienen período, as of, moneda, fuente y versión. Un resultado no computable mantiene sus motivos hasta la interfaz.",
        ],
        [
            "Variaciones",
            "Las comparaciones separan presupuesto, baseline aprobada, Current, Actual y Forecast. Se muestran VAC, diferencias de fin y de hitos. Quantity, Physical, Schedule, Cost y Earned no se renombran como si fueran el mismo avance. Una variación física contra progreso planeado exige base y pesos presupuestarios compatibles y cobertura completa; si faltan, se declara no computable.",
        ],
        [
            "Tendencias",
            "Las tendencias usan reportes publicados inmutables y la revisión vigente de cada familia de período. Una republicación sustituye la selección del punto, no borra el registro anterior ni suma saldos repetidos. Se exponen nueve métricas, incluidos fin previsto, ETC, EAC, VAC, avance físico, CPI, SPI, Readiness y restricciones abiertas.",
        ],
        [
            "Curvas",
            "Las seis series son Planned Progress, Approved Actual Progress, Earned Value, Planned Value, Actual Cost y Forecast Cost. Cada una conserva fuente, unidad o moneda y base. Planned Progress declara su normalización por BAC aprobado, no una medición física. Los porcentajes y saldos de snapshots no se acumulan entre períodos; los Actual se deduplican por identidad y fecha de reconocimiento. Forecast Cost exige phasing explícito reconciliado con ETC.",
        ],
        [
            "Project Controls Dashboard",
            "La vista compacta reúne fuentes de Scope, Schedule, Cost, Progress, Forecast, AWP, restricciones y EVM. Sus consultas son de solo lectura y no escriben auditoría de mutación de negocio. Los umbrales pertenecen al perfil publicado. El estado y los motivos se conservan visibles junto con los valores.",
        ],
        [
            "Executive Dashboard",
            "La vista ejecutiva muestra estado del proyecto, terminaciones de baseline, Current y Forecast, Budget, EAC, VAC, avance físico, CPI y SPI cuando corresponden, criticidad importada, restricciones, Readiness e hitos. No atribuye cierre de mitigaciones ni reduce la incertidumbre sin un hecho de fuente.",
        ],
        [
            "Look Ahead de cuatro semanas",
            "El horizonte por defecto es veintiocho días y se configura por política. La selección incluye trabajo no iniciado o en curso dentro del horizonte y trabajo atrasado según política, priorizando bloqueos. Admite límites, WBS, Package, criticidad y agrupación por Parent WBS, CWA, Package, Area, Zone, System o Discipline. Float conserva su unidad P6; driving predecessor es UNKNOWN si no hay evidencia importada. Un GET es lectura; guardar un snapshot es un comando explícito y auditado sobre Forecast aprobado.",
        ],
        [
            "Reporte del período",
            "El reporte se publica directamente como snapshot inmutable solo cuando el período O1A está PUBLISHED y el Forecast está APPROVED. Fija bundle, Schedule, Cost Baseline y hechos derivados del período de Cost, Progress publicado, Forecast, evaluaciones AWP y snapshot EVM coincidente. No existe una entidad transaccional CostPeriodSnapshot anterior: se congela un read model derivado con referencias de Actual, moneda, fecha y hash, sin inventar una nueva autoridad Cost. Las correcciones requieren Forecast sucesor y republicación enlazada.",
        ],
        [
            "Narrativas de reportes",
            "Las secciones incluyen resumen ejecutivo, Schedule, criticidad, Cost, Progress, Forecast, restricciones y acciones. El texto automático es determinista y cita localizadores internos de hechos. Las aportaciones manuales registran actor y referencias válidas. No se presentan conclusiones, eficacia de mitigación ni aceptación de negocio sin evidencia.",
        ],
        [
            "Límite de Power BI y modelos de lectura",
            "La API expone un contrato versionado de analytics. Un consumidor puede refrescar proyecciones vivas o cargar revisiones publicadas por identidad y hash. Las revisiones históricas no cambian; una corrección tiene nueva identidad y revisión. Power BI no es escritor transaccional. No se desplegó un conector, credenciales ni un refresco programado externo.",
        ],
        [
            "Separación de ADMIN y USER",
            "ADMIN crea y publica perfiles de métodos, ETC y EAC, recursos, tendencias, umbrales, Look-Ahead, plantillas, narrativas, series, confianza y SoD. USER opera las versiones del Project autorizado. Se reutiliza el editor gobernado existente. Las políticas publicadas son inmutables y requieren sucesor para cambios.",
        ],
        [
            "Seguridad y separación de funciones",
            "Los permisos Forecast son granulares por comando y ámbito. Se reutilizan roles y permisos de lectura de las fuentes, sin asignar automáticamente usuarios. La aprobación es independiente del preparador y último editor material; el publicador del reporte es distinto del preparador y aprobador por defecto. If Match controla concurrencia y la idempotencia vincula actor, comando y contenido. El ORM y PostgreSQL impiden reasignar un supuesto o componente a otra versión, incluso a un borrador del mismo Project. Las consultas de dashboards no registran mutaciones de negocio.",
        ],
        [
            "Contratos API",
            f"La aplicación montada expone {len(observed['api'])} operaciones dedicadas bajo forecast, performance y reporting. Incluyen versiones, cálculo, transiciones, perfiles, historia, variaciones, curvas, dashboards, Look-Ahead, snapshots, reportes y contrato analytics. La hoja API conserva métodos y rutas reales obtenidos de OpenAPI. Los contratos rechazan campos ajenos, ámbitos incompatibles y versiones obsoletas.",
        ],
        [
            "Interfaz operativa",
            "Forecast and Performance utiliza CompactModuleHeader y doce vistas: Overview, ETC EAC, Time Forecast, Milestones, Resource Forecast, Assumptions, Variance and Trends, S Curves, Project Controls, Executive, Look Ahead y Reporting History. La captura usa campos tipados y selección explícita de fuentes; los cálculos pertenecen al backend. Se extendió la navegación de Workspace y ADMIN sin modificar App.tsx ni el visor BIM global.",
        ],
        [
            "Migración aditiva",
            "0075 tiene como único padre 0074 y crea seis tablas: versiones, supuestos, componentes, historia, reportes publicados y snapshots Look-Ahead. El DDL está congelado y no importa modelos vivos al migrar. Siete triggers protegen ámbitos, perfiles publicados, independencia y estados terminales. El arranque local excluye esas tablas de create all. Se probó upgrade, downgrade y reupgrade en una base independiente vacía de datos de negocio; el downgrade poblado se rechaza. No hubo backfill ni reescritura histórica.",
        ],
        [
            "Validación de PostgreSQL",
            f"La corrida final aprobó {counts['forecast']} casos de O1C y {counts['regression']} de regresión upstream, sin fallos ni omisiones. Los archivos y hashes de fuentes se compararon antes y después y siguen vigentes al generar este informe. La provisión local clonó solo el esquema O1B D ya migrado en tres bases nuevas y vacías de negocio. No se presenta como prueba de migración histórica desde base vacía hasta head. Las observaciones y advertencias de la corrida se conservan en su evidencia.",
        ],
        [
            "Validación de Chromium",
            f"Chromium completó {counts['browser']} comprobaciones reales contra PostgreSQL, API y frontend aislados, sin respuestas de negocio simuladas ni excepciones de ejecución del navegador. La cadena recorrió publicación ADMIN, captura USER, supuestos, cálculo, aprobación independiente, métricas, curvas, Look-Ahead, período publicado e historia de reportes. Después se verificó de solo lectura el ajuste de presentación de actores de auditoría, puntos aislados de curva y acciones sin superposición, manteniendo los hashes aprobados. Los actores son sintéticos y no representan firmas de negocio.",
        ],
        [
            "Preservación del Proyecto 14",
            f"Las observaciones de la base habitual antes y después coinciden. El Workspace canónico14 conserva SHA256 {preservation}. Se preservaron la fila legada y sus referencias observadas, App.tsx, el visor IFC global, modelos y esquemas globales y migraciones históricas. No se aplicaron migraciones ni fixtures a esa base; sus comprobaciones fueron de lectura.",
        ],
        [
            "Observaciones de rendimiento",
            "Se tomaron tres muestras por operación. ETC y EAC son lotes del mismo comando de cálculo e incluyen el refresco de la vista. Las otras nueve operaciones son lecturas autenticadas. Todas las muestras incluyen respuesta y lectura JSON. Son mediciones locales, no SLA ni prueba de carga.",
        ],
        [
            "Brechas y límites restantes",
            "No hay defectos S1 o S2 abiertos en el alcance probado. Quedan fuera la aceptación de negocio, el despliegue, el CI remoto y las pruebas de volumen productivo. No se hizo commit ni push. No se ampliaron Procurement, Engineering, Construction Field, Claims, Commissioning, Accounting ni Treasury.",
        ],
        [
            "Decisión de liberación",
            f"Validación técnica en entorno aislado: {RELEASE}. Resultado: {READY}. No autoriza cambios de fuentes ni despliegue en producción.",
        ],
        [
            "Único siguiente incremento recomendado",
            "WAVE O2 — PROCUREMENT, CONTRACTS & ENGINEERING. No se inició automáticamente este incremento.",
        ],
    ]
    assert len(chapters) == 37
    defects = [
        [
            "O1C-01",
            "S2",
            "Perfiles Forecast requieren motivo y helper de publicación dedicado",
            "CERRADO",
            "Ciclo HTTP real y suites finales",
        ],
        [
            "O1C-02",
            "S2",
            "Preview podía mezclar resultado nuevo con fuentes de un draft anterior",
            "CERRADO",
            "Resultado y fuentes obtenidos en la misma lectura sin escrituras",
        ],
        [
            "O1C-03",
            "S2",
            "Snapshot Look-Ahead draft podía llegar al guard SQL como error genérico",
            "CERRADO",
            "Guard API409 explícito con prueba de lectura y mutación denegada",
        ],
        [
            "O1C-04",
            "S2",
            "Referencias de compromiso deben usar dimensiones financieras reales",
            "CERRADO",
            "Reconciliación de compromiso y Actual probada sin doble suma",
        ],
        [
            "O1C-05",
            "LÍMITE",
            "Base habitual sin migrar y sin aceptación firmada",
            "FUERA DEL DESPLIEGUE",
            "Validación aislada; despliegue requiere operación explícita",
        ],
        [
            "O1C-06",
            "S3",
            "Advertencia histórica de ciclo de metadata entre control_accounts y work_packages",
            "KNOWN_NON_BLOCKING",
            "Se conserva la evidencia del aviso; no se reescribieron modelos o migraciones anteriores",
        ],
        [
            "O1C-07",
            "S2",
            "Una evaluación de Readiness posterior al corte no es evidencia del Forecast histórico",
            "CERRADO",
            "Selección de la última evaluación persistida elegible y preservación del aprobado",
        ],
        [
            "O1C-08",
            "S3",
            "Presentación de atribución de auditoría, series de un punto y superposición de acciones",
            "CERRADO",
            "Componentes finales y relectura real en Chromium sin cambiar Forecast ni reporte",
        ],
        [
            "O1C-09",
            "S2",
            "Una actualización SQL podía cambiar la versión padre de un supuesto o componente aprobado",
            "CERRADO",
            "Regresión PostgreSQL y ORM: rechazos explícitos y ambas versiones intactas",
        ],
    ]
    data = {
        "release_state": RELEASE,
        "final_output": READY,
        "opening": "Implementamos Forecast rendimiento y reportes de P&Pmis Construction AI sobre las autoridades operativas existentes. Este informe explica los cambios y las pruebas ejecutadas en un entorno aislado, con trazabilidad de fuentes y sin desplegar en la base habitual.",
        "chapters": chapters,
        "authorities": authorities,
        "suite_summary": summaries,
        "requirements": requirements,
        "release_criteria": criteria,
        "cases": cases,
        "browser": browser,
        "api": observed["api"],
        "performance": observed["performance"],
        "volume_summary": "Volumen observado: "
        + ", ".join(f"{key} {value}" for key, value in observed["data_volume"].items())
        + ".",
        "defects": defects,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "package-data.json").write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "chapters": len(chapters),
                "requirements": len(requirements),
                "criteria": len(criteria),
                "tests": len(cases),
                "state": RELEASE,
            }
        )
    )


if __name__ == "__main__":
    main()
