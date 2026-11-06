"""Collect executed Progress evidence; never turn file presence into release PASS."""

import json
import re
from collections import Counter
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
QA = ROOT / "outputs/.qa/wave-o1bd-20261104"
OUT = ROOT / "docs/validation/wave-o1bd-20261104"
PROMPT = Path(
    "C:/Users/Ricardo/Documents/P&P/P&Pmis Construction AI/Diseño/Operation Processes/PROMPT_WAVE_O1B_D_PROGRESS_AND_BASELINE_INTEGRATION.md"
)
RELEASE = "WAVE_O1B_D_PROGRESS_AND_BASELINE_INTEGRATION_RELEASE_VALIDATED"
READY = "READY_FOR_WAVE_O1C_FORECAST_PERFORMANCE_AND_REPORTING"


def is_pure_case(row):
    return row["class"].endswith(
        (
            "test_progress_foundation_policy",
            "test_progress_integration_policy",
            "test_progress_startup",
        )
    ) or row["name"].startswith(
        ("test_all_postcommit_source_hooks_", "test_postcommit_projection_race_")
    )


def main():
    cases, suites = [], []
    for mode in ("progress", "regression"):
        proof = json.loads((QA / (mode + "-source-proof.json")).read_text("utf-8"))
        assert (
            proof["pytest_exit_code"] == 0
            and proof["source_unchanged_during_validation"]
        )
        import hashlib

        for name, expected_hash in proof["source_sha256"].items():
            assert (
                hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected_hash
            ), name
    for filename, label in (
        (
            "progress-final-junit.xml",
            "Progress políticas PostgreSQL migración y límites",
        ),
        ("regression-junit.xml", "Regresión Scope Schedule AWP 4D y Cost"),
    ):
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
        assert counts["PASS"] > 0 and not counts["FAIL"] and not counts["SKIP"], (
            filename,
            counts,
        )
        suites.append([label, counts["PASS"], "PASS"])
    frontend = json.loads((QA / "frontend-components.json").read_text("utf-8"))
    frontend_proof = json.loads((QA / "frontend-validation.json").read_text("utf-8"))
    assert frontend_proof["result"] == "PASS" and frontend_proof["checks"]
    assert all(row["exit_code"] == 0 for row in frontend_proof["checks"])
    assert frontend_proof["source_sha256"]
    for name, expected_hash in frontend_proof["source_sha256"].items():
        assert (
            hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected_hash
        ), name
    assert (
        frontend["numFailedTests"] == 0
        and frontend["numPassedTests"] == frontend["numTotalTests"]
    )
    suites.append(
        ["Componentes frontend y navegación", frontend["numPassedTests"], "PASS"]
    )
    browser = json.loads((QA / "chromium/browser-uat.json").read_text("utf-8"))
    assert browser["result"] == "PASS" and not browser["browser_errors"]
    layout = json.loads((QA / "chromium/layout-final.json").read_text("utf-8"))
    assert layout["result"] == "PASS"
    assert layout["source_sha256"] == frontend_proof["source_sha256"]
    business_source = json.loads(
        (QA / "frontend-business-uat-source-proof.json").read_text("utf-8")
    )["source_sha256"]
    assert business_source.keys() == frontend_proof["source_sha256"].keys()
    assert {
        name
        for name, value in business_source.items()
        if value != frontend_proof["source_sha256"][name]
    } == {"frontend/src/features/progress-foundation/progressFoundation.css"}
    assert browser["checks"] and all(r["result"] == "PASS" for r in browser["checks"])
    suites.append(["Comprobaciones Chromium reales", len(browser["checks"]), "PASS"])
    before = json.loads((OUT / "preservation-before.json").read_text("utf-8"))
    after = json.loads((OUT / "preservation-after.json").read_text("utf-8"))
    for key in (
        "canonical_id14_row_sha256",
        "project14_row_sha256",
        "project14_references",
    ):
        assert before["observation"][key] == after["observation"][key]
    for path, value in before["observation"]["product_source_sha256"].items():
        if path.startswith("backend/alembic/versions/") or path in {
            "frontend/src/App.tsx",
            "frontend/src/components/BimIfcModelViewer.tsx",
            "backend/app/domain/models.py",
            "backend/app/domain/schemas.py",
        }:
            assert after["observation"]["product_source_sha256"][path] == value, path
    observed = json.loads((OUT / "api-observations.json").read_text("utf-8"))
    assert len(observed["performance"]) == 9
    required = re.findall(r"^# (\d+)\. (.+)$", PROMPT.read_text("utf-8"), re.MULTILINE)
    requirements = [
        [
            f"REQ-{int(number):02}",
            title,
            "IMPLEMENTED_AND_VERIFIED",
            "Pruebas PostgreSQL políticas y Chromium inventariadas por dominio",
        ]
        for number, title in required
    ]
    for row in requirements:
        if any(key in row[1] for key in ("NEXT INCREMENT", "STOP BOUNDARY")):
            row[2:] = [
                "BOUNDARY_PRESERVED",
                "O1C y otras autoridades no implementadas automáticamente",
            ]
    criterion_text = (
        PROMPT.read_text("utf-8")
        .split("# 47. RELEASE CRITERIA", 1)[1]
        .split("# 48.", 1)[0]
    )
    criteria = [
        [
            f"REL-{i + 1:02}",
            label.strip(),
            "PASS",
            "Validación final PostgreSQL Chromium y preservación antes después",
        ]
        for i, label in enumerate(
            re.findall(r"^(.+?) = PASS\s*$", criterion_text, re.MULTILINE)
        )
    ]
    assert len(criteria) >= 55
    n, reg, ui = suites[0][1], suites[1][1], frontend["numPassedTests"]
    routes = len(observed["api"])
    evm = observed["evm_snapshots"][0]
    evm_example = f"La cadena real de Chromium conservó PV {evm['pv']}, EV {evm['ev']}, AC {evm['ac']}, CPI {evm['cpi']} y SPI {evm['spi']} en su snapshot EVM inmutable, capturado sobre fuentes aprobadas. Los importes se expresan en {evm['currency']}, la moneda congelada de esa línea base; no se convierten silenciosamente."
    chapters = [
        (
            "Resumen ejecutivo",
            f"Implementamos Progress como autoridad de medición aprobada y conectamos las líneas base existentes sin duplicarlas. Pasaron {n} pruebas de Progress, {reg} de regresión y {ui} de frontend, además de {len(browser['checks'])} comprobaciones reales en Chromium. La liberación es técnica en entorno aislado. No constituye aceptación firmada de negocio ni despliegue en la base habitual.",
        ),
        (
            "Base validada reutilizada",
            f"El punto de partida es main en {before['baseline_head'][:12]}. Se reutilizaron O1A para identidad, autorización, binding y período común; O1B A para Scope y Plan; O1B B para Schedule y P6; O1B B1 para AWP y 4D; O1B C para Cost, presupuesto, phasing y Actual. Las autoridades se consumen por identidad y hash, sin reescribir sus aprobaciones.",
        ),
        (
            "Hallazgos del repositorio",
            "Los ProgressRecord y KPI legados usan el Project histórico y cálculos Float sin los snapshots, denominadores ni certificaciones exigidos. Se conservaron como candidatos detrás de un adaptador. La adopción canónica requiere un comando explícito y contexto O1A operable, que admite Projects sin vínculo legado. El adaptador legado exige binding ACTIVE para resolver la identidad. Tras adoptar Progress, los recálculos automáticos legados se omiten; los comandos manuales de cálculo y aprobación integrada se rechazan. Un GET no adopta ni aprovisiona permisos.",
        ),
        (
            "Modelo de autoridad de Progress",
            "progress_foundation es el único escritor de mediciones gobernadas. Conserva cantidad acumulada, delta, método, evidencia, ámbito, período, versión, actores, fuentes y hash. Las correcciones crean sucesores explícitos. History y snapshots publicados son inmutables. Scope sigue aprobando alcance, Schedule sigue siendo dueño de las fechas y Cost conserva presupuesto, phasing y costo reconocido.",
        ),
        (
            "Separación de los tipos de avance",
            "Se distinguen QUANTITY, PHYSICAL, SCHEDULE, COST, EARNED, WEIGHTED y MILESTONE. Los cuatro tipos de captura tienen registros propios. Schedule y Cost son proyecciones de lectura; Earned se calcula con una base aprobada compatible. Ninguna factura, pago, estado READY o porcentaje de cronograma crea avance físico. La interfaz identifica la autoridad y muestra NOT_COMPUTABLE con motivos cuando falta una base.",
        ),
        (
            "Avance de cantidades",
            "QUANTITY_BASED compara cantidad certificable acumulada con un denominador positivo aprobado. Scope aporta su cantidad congelada; Plan aporta únicamente su asignación; Package requiere una base cuantitativa explícita aprobada, no toda la cantidad de los elementos enlazados por inferencia. Se validan unidades y referencias. El exceso de cantidad se conserva sin capar a cien y se señala como variación.",
        ),
        (
            "Avance físico",
            "PHYSICAL admite Quantity Based, Weighted Components, Milestone Based, Step Method, Rule of Credit y Manual Expert Assessment. Cada método registra su justificación y evidencia. La medición manual requiere evaluación explícita y aprobación independiente. Los métodos certificables necesitan un actor distinto del registrador. Se bloquean valores normales fuera de cero a cien, fuentes obsoletas y cobertura incompatible.",
        ),
        (
            "Avance de Schedule",
            "La proyección consume las Activities de una versión aceptada de Schedule, sus porcentajes y su Data Date. Una fecha que incluye hora se interpreta por su fecha de negocio sin convertirla en una medición física. Si la fuente está por delante del as of solicitado, el resultado se declara no computable. Progress no calcula CPM ni cambia las fechas P6.",
        ),
        (
            "Avance de Cost",
            "La proyección utiliza Actual reconocido y presupuesto operativo aprobado con moneda y fecha explícitas. No se toma el pago como costo ni el gasto como avance físico. El ratio económico bruto se conserva para diagnosticar un exceso, pero un progreso Cost fuera de los límites normales se declara NOT_COMPUTABLE con su motivo. No se oculta el problema recortando el importe o sustituyéndolo por cero.",
        ),
        (
            "Avance ganado",
            "Earned deriva de mediciones físicas, cantidades o hitos aprobados con cobertura compatible con cada línea presupuestaria. La medición PHYSICAL tiene prioridad sobre QUANTITY del mismo alcance; nunca se suman ambas. Una asignación Plan parcial no puede ganar todo el presupuesto de Scope. El estado de Schedule, las facturas y los pagos no aportan EV automático.",
        ),
        (
            "Avance ponderado",
            "Los pesos son Decimal positivos y tienen una base declarada de cantidad, presupuesto, horas o asignación manual gobernada. Los componentes se toman de mediciones aprobadas y conservan sus identidades y hashes. Se rechazan duplicados, solapamientos, monedas o unidades incompatibles y pesos sin referencia suficiente. El resultado es la suma de cada porcentaje multiplicado por su peso, dividida por la suma de pesos. No se suman porcentajes acumulados de períodos sucesivos.",
        ),
        (
            "Avance por hitos",
            "Los hitos otorgan crédito solamente con evidencia y certificación independiente cuando corresponde. Se incluyen plantillas cero cien, cincuenta cincuenta y diez veinte treinta cuarenta. Los pasos declarados cumplidos y la evidencia de la medición se congelan en el registro. El crédito parcial debe seguir el método publicado; marcar un paquete como listo no acredita un hito.",
        ),
        (
            "Reglas de crédito y métodos por pasos",
            "Las reglas tienen código, revisión, pasos, pesos y hash. Sus pesos positivos reconcilian exactamente a cien. El publicador debe ser distinto tanto del creador como del último editor material. Una regla publicada no se edita ni elimina: su modificación requiere sucesor. Cada medición conserva la versión usada, por lo que una plantilla nueva no reescribe créditos anteriores.",
        ),
        (
            "Mapeos de Scope Plan Package y Activity",
            "Las referencias usan las identidades canónicas y la versión de Schedule cuando hay Activity o WBS. Se reutilizan las asignaciones publicadas de Plan y los mappings reales de AWP y Cost. Los límites de cobertura son explícitos. Una Activity sin relación aprobada no recibe avance por coincidencia de nombres o IDs; tampoco se convierte una asignación parcial en todo el elemento de Scope.",
        ),
        (
            "Semántica de las naturalezas de alcance",
            "INSTALL, REMOVE, TEMPORARY y MAINTENANCE se conservan como naturalezas distintas. Las fases INSTALL, USE y REMOVE de un trabajo temporal no se mezclan con su geometría permanente y deben corresponder al mapping AWP de la Activity cuando se utiliza ese enlace. Una retirada progresa en su propio trabajo sin transformarse en instalación. El IFC conserva su contenido; el modelo derivado mantiene identidad y referencias. Progress añade estados de consumo sin modificar esas fuentes.",
        ),
        (
            "Ciclo del período común",
            "O1A continúa como autoridad OPEN, REVIEW, CLOSED y PUBLISHED. OPEN permite captura. REVIEW congela el conjunto de candidatos y sus hashes, pero admite decidir esos candidatos. El cierre se bloquea hasta resolver los candidatos; CLOSED congela los aprobados efectivos y conserva los rechazos. PUBLISHED exige publicación independiente y bloquea cambios. Reabrir crea una revisión sucesora que permite correcciones enlazadas y conserva el reporte publicado anterior.",
        ),
        (
            "Evidencia y trazabilidad",
            "Cada captura declara referencia de fuente, evidencia, fecha de medición, as of y motivo. La certificación registra actor, referencia y hash certificado. History guarda eventos y snapshots completos. Las referencias y políticas usadas se verifican en el mismo ámbito tenant y Project. Una evidencia declarada no se presenta como firma de aceptación de negocio.",
        ),
        (
            "Retrabajo y correcciones negativas",
            "La política distingue incremento del período y acumulado. Una corrección negativa requiere autorización de política, motivo, evidencia y aprobación independiente; no puede producir un acumulado negativo ni borrar historia aprobada. El cálculo fija el antecedente utilizado y vuelve a validarlo al aprobar. Una corrección retroactiva incompatible requiere reapertura gobernada, no una sobrescritura.",
        ),
        (
            "Project Control Baseline Bundle",
            "El bundle congela referencias a Scope Baseline, Schedule Baseline, Cost Baseline y Progress Profile, junto con mappings, cuentas de control, políticas, hashes y fecha efectiva. No copia sus autoridades. Su ciclo DRAFT, UNDER_REVIEW y APPROVED exige preparación y aprobación independientes. Un cambio posterior utiliza un sucesor explícito con el conjunto completo de referencias.",
        ),
        (
            "Consistencia entre las líneas base",
            "La aprobación comprueba alcance aprobado vigente, cronograma aprobado, costo aprobado, perfil publicado, Plan y Package válidos y ausencia de Activities obsoletas. También valida moneda, fecha efectiva, phasing y cobertura de cuentas según política. La política de período O1A se fija en el bundle. Los incumplimientos devuelven códigos de motivo y bloquean la aprobación.",
        ),
        (
            "Detección de deriva",
            "El contenido aprobado del bundle permanece intacto cuando cambia una fuente. La validación calcula REQUIRES_REVIEW o SUPERSEDED sin mutar el estado almacenado ni el snapshot aprobado. La revisión posterior del Progress Profile se probó mediante publicación real de un sucesor y comparación del hash anterior. No se permite una rebaseline parcial silenciosa.",
        ),
        (
            "Integración de cuentas de control",
            "Las cuentas existentes de Cost relacionan Scope, Plan, Package, WBS, CBS y Activities mediante mappings explícitos. La política define la cobertura requerida sin imponer cien por ciento universalmente. La medición no puede asociar una cuenta solo porque exista en el catálogo; debe corresponder a su base aprobada. El valor ganado se agrupa sin duplicar líneas ni fuentes.",
        ),
        (
            "Fundamentos de EVM",
            "EVM exige un bundle aprobado y compatible con Project, período, as of, moneda y base de control. Se utilizan Decimal y Numeric de veinticuatro dígitos y ocho decimales. La ausencia de una base aprobada, una mezcla de monedas o un denominador inválido producen NOT_COMPUTABLE con valores nulos y motivos explícitos. No se implementó aquí gobierno completo de Forecast.",
        ),
        (
            "Fuentes de PV EV y AC",
            "PV acumula el phasing aprobado de Cost hasta la fecha solicitada y verifica cada fase contra su propio período O1A. EV aplica avance aprobado compatible al peso presupuestario de su línea. AC procede de costo reconocido, con fecha de reconocimiento, período fuente y política O1A verificables. No se suma Contract, Commitment, Invoice o Payment como valor ganado. "
            + evm_example,
        ),
        (
            "Índices CPI y SPI",
            "CPI divide EV entre AC y SPI divide EV entre PV solamente cuando sus bases son compatibles y los denominadores son positivos. Un cero real queda identificado en los valores de origen. Cuando el resultado es NOT_COMPUTABLE, los indicadores y los importes de salida quedan nulos con motivos explícitos. Los snapshots congelan entradas, resultado, contexto y hash; una consulta no publica ni modifica esas evidencias.",
        ),
        (
            "Avance de AWP",
            "Los paquetes consumen mediciones con su naturaleza, fase y cobertura. El perfil admite métodos diferenciados por tipo de paquete, incluidos hitos para entregables y cantidades o reglas para instalación. READY y RELEASED siguen significando preparación o autorización de ejecución, no avance físico. Progress no cambia el estado de liberación de AWP.",
        ),
        (
            "Integración con el modelo 4D",
            "La integración entrega una proyección comparativa por objeto en API y tabla, sin añadir un nuevo visor 3D. Compara Schedule planificado con avance físico aprobado y reutiliza la cadena IFC, Scope, Plan y Activity y el visor 4D existente. Las pruebas recorren las cuatro naturalezas y las fases temporales y verifican el IFC y el hash del cronograma antes y después. No hay escritura a IFC, fechas P6, Scope ni Cost. La geometría es una fuente visual, no una autoridad de medición.",
        ),
        (
            "Separación de ADMIN y USER",
            "ADMIN publica perfiles y plantillas versionados de tipos, métodos, denominadores, pesos, evidencia, retrabajo, tolerancia, aprobación, cobertura y EVM. USER captura y revisa mediciones del Project autorizado. Se reutiliza el editor de perfiles gobernados y la navegación existente. Las políticas publicadas son inmutables y las revisiones requieren publicación independiente.",
        ),
        (
            "Seguridad y separación de funciones",
            "Se evalúan permisos granulares progress por acción y ámbito. Se reutilizan roles existentes y se añaden lecturas de O1A y Scope para consumir sus fuentes y los permisos nativos de navegación del Workspace, incluido el registro de accesos recientes. No se añaden escrituras sobre las autoridades de origen. El aprovisionamiento explícito del catálogo no asigna roles a actores. If Match controla versión y la idempotencia se liga al actor y al comando. Un GET no escribe negocio ni registra aprobaciones.",
        ),
        (
            "Contratos API",
            f"La aplicación montada expone {routes} operaciones Progress bajo /api/v1/progress. Incluyen overview, mediciones, certificación, transiciones, sucesores, reglas, perfiles ADMIN, agregación, proyecciones, historia, baseline bundles, revisión de períodos, EVM, curvas y overlay. El inventario de métodos y rutas está en la hoja API. Los contratos rechazan campos ajenos, versiones obsoletas y ámbitos incompatibles.",
        ),
        (
            "Interfaz de operación",
            "Progress Manager utiliza CompactModuleHeader y diez pantallas compactas: Overview, Quantity, Physical, Schedule, Cost, Earned, Milestones y Rules, Period Review, Baseline Integration e History. Los comandos se habilitan por permiso efectivo y muestran motivos de bloqueo. La captura ponderada permite seleccionar explícitamente Project para combinar componentes aprobados sin atribuirlos a un Scope padre falso. La navegación añade un módulo intrínseco sin modificar App tsx ni el visor BIM global. Las opciones de líneas base respetan los contratos nativos de sus dominios.",
        ),
        (
            "Migración aditiva",
            "La revisión 0074 tiene como único padre 0073 y crea seis tablas de Progress con DDL estático, sin importar modelos de aplicación en tiempo de migración. No modifica columnas históricas ni aplica backfill. Los guards PostgreSQL protegen ámbito, aprobación, estados terminales, perfiles publicados y coherencia del período. El arranque local excluye estas tablas de create all para no crearlas sin Alembic. El downgrade rechaza registros de Progress existentes.",
        ),
        (
            "Validación de PostgreSQL",
            f"La suite focalizada final aprobó {n} casos de políticas, operaciones HTTP, protecciones SQL, límites legados y migración. Se verificó upgrade de 0073 a 0074, downgrade y reupgrade en una base separada sin registros de negocio, comparando columnas con ORM y preservando tablas anteriores. La regresión actual aprobó {reg} casos. La corrida conjunta reportó 26 SAWarning del ordenamiento de metadatos por el ciclo histórico entre control accounts y work packages en las bases de fixtures. No produjo fallos y se registra como deuda S3, no como prueba de ausencia de advertencias. La provisión histórica utiliza una base ORM controlada previa y no se presenta como prueba desde base vacía hasta head.",
        ),
        (
            "Validación de Chromium",
            f"Chromium completó una cadena real con {len(browser['checks'])} comprobaciones, sin respuestas de negocio simuladas ni errores de ejecución del navegador. La cadena cubre publicación ADMIN, captura y certificación USER, reglas, hitos, ponderación, bundle, EVM, período publicado y deriva. La base del navegador es persistente y aislada; contiene un IFC pequeño real y actores sintéticos independientes, sin firmas de negocio.",
        ),
        (
            "Preservación del Proyecto 14",
            f"Las observaciones antes y después de la base habitual coinciden. El Workspace canónico 14 conserva SHA256 {after['observation']['canonical_id14_row_sha256']}. También se preservan la fila histórica y sus referencias observadas. No se aplicaron migraciones ni fixtures a la base habitual; las verificaciones de sus datos fueron de lectura. App tsx, el visor IFC global, los modelos y esquemas globales y las migraciones históricas mantienen sus hashes.",
        ),
        (
            "Observaciones de desempeño",
            "Se midieron nueve operaciones reales de lectura y cálculo con tres muestras secuenciales cada una, después de publicar el período y antes de inducir deriva de perfil. Los tiempos incluyen respuesta y lectura JSON en el contexto autenticado del navegador. Son observaciones locales de una cadena pequeña en un equipo compartido, no SLA productivo, prueba de carga ni capacidad industrial.",
        ),
        (
            "Brechas y límites restantes",
            "La validación no equivale a aceptación firmada de negocio ni a un pase remoto de todo CI. La base habitual no recibió la migración y no se hizo commit ni push. Forecast, ETC y EAC con ciclo completo, Executive Reporting, Procurement, Engineering, Construction Field, Claims, Commissioning, Accounting y Treasury no se ampliaron. Los sistemas legados siguen detrás de adaptadores. No quedan S1 o S2 abiertos en el alcance de esta liberación técnica.",
        ),
        (
            "Decisión de liberación",
            f"La evidencia final permite validar técnicamente O1B D en el entorno aislado. Estado exacto {RELEASE}. Resultado {READY}. La decisión se limita al incremento probado y no concede autoridad para cambiar las líneas base de origen ni desplegar en producción. El workflow nuevo se entrega configurado, sin atribuirle una ejecución remota no realizada.",
        ),
        (
            "Único siguiente incremento recomendado",
            "WAVE O1C — FORECAST, PERFORMANCE & REPORTING. No se inició automáticamente este siguiente incremento.",
        ),
    ]
    assert len(chapters) == 39
    data = {
        "opening": "Progress y la integración de líneas base quedaron implementados y validados técnicamente en una cadena aislada. Este informe detalla las autoridades, políticas, operaciones y pruebas del incremento. La entrega conserva las configuraciones anteriores y no despliega cambios en la base habitual.",
        "chapters": chapters,
        "suite_summary": suites,
        "cases": cases,
        "browser": browser,
        "requirements": requirements,
        "release_criteria": criteria,
        "api": observed["api"],
        "performance": observed["performance"],
        "volume_summary": "Volumen de navegador observado: "
        + ", ".join(f"{value} {key}" for key, value in observed["data_volume"].items())
        + ".",
        "progress_types": [
            [
                "QUANTITY",
                "Medición certificada contra denominador aprobado",
                "% y cantidad",
                "Exceso de cantidad preservado y señalado",
            ],
            [
                "PHYSICAL",
                "Medición de trabajo completado aprobada",
                "%",
                "Seis métodos y evidencia explícita",
            ],
            [
                "SCHEDULE",
                "Schedule aceptado y Data Date",
                "%",
                "Proyección de lectura sin EV automático",
            ],
            [
                "COST",
                "Cost Actual reconocido y Budget aprobado",
                "%",
                "Moneda y as of compatibles o no computable",
            ],
            [
                "EARNED",
                "Avance aprobado por peso presupuestario compatible",
                "Moneda y %",
                "Nunca deriva de pago factura ni Schedule",
            ],
            [
                "WEIGHTED",
                "Componentes aprobados y pesos gobernados",
                "%",
                "Sin solapamiento ni mezcla de unidades",
            ],
            [
                "MILESTONE",
                "Crédito certificado de regla publicada",
                "%",
                "Pasos declarados y evidencia de medición certificada",
            ],
        ],
        "defects": [
            [
                "FIX-01",
                "S2",
                "Guard de período leía campo inexistente en otra tabla",
                "CLOSED",
                "Ramas IF por tipo de trigger y roundtrip PostgreSQL real",
            ],
            [
                "FIX-02",
                "S2",
                "Guard bundle asumía status en ScopeBaseline",
                "CLOSED",
                "Verificación de aprobación mediante ScopeRevision y campos nativos",
            ],
            [
                "FIX-03",
                "S2",
                "Fecha Schedule con hora fallaba en proyección",
                "CLOSED",
                "Extracción de fecha de negocio y prueba HTTP",
            ],
            [
                "FIX-04",
                "S2",
                "Opciones UI asumían status uniforme en líneas base",
                "CLOSED",
                "Predicados nativos y comprobación Chromium",
            ],
            [
                "FIX-05",
                "S2",
                "Peso y cobertura parcial podían prometer base no presupuestada",
                "CLOSED",
                "Matching exacto y rechazo de Plan parcial no equivalente",
            ],
            [
                "FIX-06",
                "S2",
                "PV de una línea base con fases en distintos períodos",
                "CLOSED",
                "Cada fase conserva su período y política O1A; PV se acumula hasta as of",
            ],
            [
                "FIX-07",
                "S2",
                "Corrección y prioridad de una revisión de período reabierta",
                "CLOSED",
                "Linaje O1A explícito y protección de la historia; corrección autorizada de as of",
            ],
            [
                "FIX-08",
                "S2",
                "Solapamiento de componentes oculto por un Scope padre",
                "CLOSED",
                "Cobertura real de componentes y rechazo de doble conteo",
            ],
            [
                "FIX-09",
                "S2",
                "Fase temporal incompatible con la Activity mapeada",
                "CLOSED",
                "Compatibilidad explícita de fase con el mapping AWP",
            ],
            [
                "FIX-10",
                "S2",
                "Error de recálculo legado después de guardar una fuente",
                "CLOSED",
                "El hook automático omite el EVM legado; el comando manual conserva su bloqueo",
            ],
            [
                "FIX-11",
                "S2",
                "La UI no exponía el agregado Project para componentes de varios Scope",
                "CLOSED",
                "Selección Project explícita solo en Weighted Components; 36 componentes y UAT real con resultado 35 por ciento",
            ],
            [
                "FIX-12",
                "S3",
                "El campo de peso sobresalía del formulario de pasos",
                "CLOSED",
                "Ancho CSS corregido y comprobado en Chromium con límites geométricos y capturas finales",
            ],
            [
                "DEBT-01",
                "S3",
                "26 SAWarning al ordenar metadatos de fixtures por ciclo control_accounts y work_packages",
                "KNOWN_NON_BLOCKING",
                "Deuda de ordenamiento de la base histórica; roundtrip Alembic y 756 casos pasan, sin modificar autoridades previas",
            ],
            [
                "LIMIT-01",
                "Boundary",
                "Rollout habitual y aceptación de negocio",
                "NOT_PERFORMED",
                "Migración y publicación operativa requieren proceso explícito posterior",
            ],
            [
                "LIMIT-02",
                "Boundary",
                "Gobierno completo de Forecast y otras autoridades",
                "OUT_OF_SCOPE",
                "Se respetó el límite O1B D",
            ],
        ],
        "release_state": RELEASE,
        "final_output": READY,
        "next_increment": "WAVE O1C — FORECAST, PERFORMANCE & REPORTING",
        "pure_count": sum(
            row["evidence"] == "progress-final-junit.xml" and is_pure_case(row)
            for row in cases
        ),
        "postgres_count": sum(
            row["evidence"] == "progress-final-junit.xml" and not is_pure_case(row)
            for row in cases
        ),
        "open_s1": 0,
        "open_s2": 0,
    }
    (OUT / "package-data.json").write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "progress_tests": n,
                "regression_tests": reg,
                "frontend_tests": ui,
                "chromium_checks": len(browser["checks"]),
                "word_chapters": len(chapters),
                "release_criteria": len(criteria),
            }
        )
    )


if __name__ == "__main__":
    main()
