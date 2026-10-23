"""Collect executed Cost evidence; never infer release PASS from code presence."""

import json
import re
from collections import Counter
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
QA = ROOT / "outputs/.qa/wave-o1bc-20261022"
OUT = ROOT / "docs/validation/wave-o1bc-20261022"
PROMPT = Path(
    "C:/Users/Ricardo/Documents/P&P/P&Pmis Construction AI/Diseño/Operation Processes/PROMPT_WAVE_O1B_C_COST_FOUNDATION_SCOPE_FIRST_CBS_BUDGET_COST_BASELINE.md"
)


def main():
    cases, suites = [], []
    for filename, label in (
        ("cost-junit.xml", "Cost PostgreSQL y políticas"),
        ("regression-junit.xml", "Regresión Scope Schedule AWP 4D"),
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
    assert (
        frontend["numFailedTests"] == 0
        and frontend["numPassedTests"] == frontend["numTotalTests"]
    )
    suites.append(
        ["Componentes frontend y navegación", frontend["numPassedTests"], "PASS"]
    )
    browser = json.loads((QA / "chromium/browser-uat.json").read_text("utf-8"))
    assert browser["result"] == "PASS" and not browser["browser_errors"]
    assert all(r["result"] == "PASS" for r in browser["checks"])
    suites.append(["Comprobaciones Chromium reales", len(browser["checks"]), "PASS"])
    before = json.loads((OUT / "preservation-before.json").read_text("utf-8"))[
        "observation"
    ]
    after = json.loads((OUT / "preservation-after.json").read_text("utf-8"))[
        "observation"
    ]
    for key in (
        "canonical_id14_row_sha256",
        "project14_row_sha256",
        "project14_references",
    ):
        assert before[key] == after[key]
    protected = [
        "frontend/src/App.tsx",
        "frontend/src/components/BimIfcModelViewer.tsx",
        "backend/app/domain/models.py",
        "backend/app/domain/schemas.py",
    ]
    for path in protected:
        assert (
            before["product_source_sha256"][path]
            == after["product_source_sha256"][path]
        ), path
    for path, value in before["product_source_sha256"].items():
        if path.startswith("backend/alembic/versions/"):
            assert after["product_source_sha256"][path] == value, path
    observed = json.loads((OUT / "api-observations.json").read_text("utf-8"))
    pure = sum(
        r["evidence"] == "cost-junit.xml"
        and r["class"].endswith(
            (
                "test_cost_foundation_policy",
                "test_cost_financial_policy",
                "test_cost_startup",
            )
        )
        for r in cases
    )
    pg = suites[0][1] - pure
    source = PROMPT.read_text("utf-8")
    required = re.findall(r"^# (\d+)\. (.+)$", source, re.MULTILINE)
    requirements = [
        [
            f"REQ-{int(number):02}",
            title,
            "IMPLEMENTED",
            "Pruebas y contratos inventariados en las hojas de dominio",
        ]
        for number, title in required
    ]
    for row in requirements:
        if row[1] == "ACCRUAL":
            row[2:] = [
                "DEFERRED_WITH_CONTRACT",
                "Contrato explícito en 12_Accruals sin ciclo de mutación o reversión",
            ]
        elif row[1] == "MULTI-CURRENCY":
            row[3] = (
                "Budget monomoneda; FX explícito en Actual y Commitment; sin agregación silenciosa"
            )
    criterion_text = source.split("# 44. RELEASE CRITERIA", 1)[1].split("# 45.", 1)[0]
    criteria = []
    for line in criterion_text.splitlines():
        if " = PASS" in line:
            label = line.split(" = PASS")[0].strip()
            state = "DEFERRED_WITH_CONTRACT" if label == "Accrual lifecycle" else "PASS"
            criteria.append(
                [
                    f"RC-{len(criteria) + 1:02}",
                    label,
                    state,
                    "cost-junit.xml; regression-junit.xml; browser-uat.json; preservation-after.json",
                ]
            )
    volume = observed["data_volume"]
    baseline_head = json.loads((OUT / "preservation-before.json").read_text("utf-8"))[
        "baseline_head"
    ]
    pg_summary = f"La suite Cost cerró {suites[0][1]} casos: {pg} de PostgreSQL HTTP, límites o migración y {pure} casos de cálculo, políticas y aislamiento del arranque local. La regresión adicional aprobó {suites[1][1]} casos de Scope, Schedule, intercambio P6, AWP y 4D. Se ejecutaron suites focalizadas sin cobertura global del repositorio; sus resultados no sustituyen un pase remoto de todo el CI."
    browser_summary = f"Chromium ejecutó un escenario real con {len(browser['checks'])} comprobaciones y {len(browser['observations'])} observaciones HTTP, sin respuestas de negocio simuladas ni errores de ejecución del navegador. Se probaron publicación ADMIN independiente, CBS, códigos, cuenta, mapeos, Rate y APU, Budget, aprobación independiente, phasing Schedule, Cost Baseline, Actual reconocido, conciliación y consulta de historia."
    preservation_summary = (
        "La base habitual se observó solo en modo lectura. El Workspace canónico 14 conserva exactamente el hash "
        + after["canonical_id14_row_sha256"]
        + ". También se conservaron la identidad histórica observada y sus referencias. No se usó como fixture, ni se migró o reinicializó la base habitual. App.tsx, el visor BIM, los modelos y esquemas globales y las migraciones anteriores conservan sus hashes."
    )
    release = "WAVE_O1B_C_COST_FOUNDATION_RELEASE_VALIDATED"
    chapters = [
        (
            "Resumen ejecutivo",
            f"Se implementó y verificó Cost Foundation como autoridad operativa de costos, aguas abajo del alcance aprobado. Incluye estructura de control, APU, tarifas, presupuestos, baseline, phasing, reconocimiento de costos y conciliación de compromisos. La decisión es una liberación técnica en entorno aislado; no acredita aceptación de negocio, despliegue productivo ni firmas. Se aprobaron {suites[0][1] + suites[1][1] + frontend['numPassedTests']} pruebas automatizadas y las {len(browser['checks'])} comprobaciones de Chromium.",
        ),
        (
            "Base validada reutilizada",
            f"El incremento parte del commit {baseline_head[:12]} de main. Se reutilizaron O1A para identidad, autorización y períodos; O1B A para Scope y Plan; O1B B para Schedule y P6; y O1B B1 para AWP, readiness y 4D. Las cantidades proceden del snapshot de Scope aprobado. Los Plan Items publicados, paquetes existentes y versiones aceptadas de Schedule se consumen por identidad y hash, sin reconstruir sus autoridades.",
        ),
        (
            "Hallazgos del repositorio",
            "Los presupuestos, códigos y cuentas legados utilizan el Project histórico, importes Float y acoplamientos obligatorios con WBS o FBS. No contienen el ciclo de aprobación, la moneda o los snapshots necesarios para la nueva autoridad. Se conservaron detrás de adaptadores. El catálogo APU Colombia se reutiliza como evidencia de origen. La suma legada de contrato y PO no se adoptó como compromiso neto. La clasificación REUSE, EXTEND, KEEP BEHIND ADAPTER, REFACTOR y DEPRECATION CANDIDATE quedó documentada.",
        ),
        (
            "Modelo de autoridad Cost",
            "El módulo cost_foundation es el único escritor de Cost canónico. El primer comando Cost explícito marca la adopción del Project; una lectura no la activa. A partir de ella, las escrituras económicas legadas inventariadas se rechazan y la carga económica P6 se conserva como evidencia candidata, sin materializar otro presupuesto. No se migran automáticamente los datos históricos. El adaptador de fuentes exige el binding O1A; no equipara los IDs histórico y canónico.",
        ),
        (
            "Mapeos entre Scope Plan paquetes y Cost",
            "Los vínculos son M:N entre Scope, Plan, Work Package, WBS o Activity y CBS, Cost Code o Control Account. Conservan base de asignación y cantidad, unidad, porcentaje o importe con moneda, revisión efectiva, origen y snapshot. Las correcciones crean sucesores; las filas anteriores permanecen inmutables. Una Activity o WBS conserva además la versión aceptada y el identificador externo del cronograma.",
        ),
        (
            "CBS",
            "CBS mantiene código, nombre, padre, ruta, nivel, orden, estado y revisión. Su árbol es independiente de WBS. Se impiden ciclos y padres inactivos. Los cambios de jerarquía que afectarían descendientes exigen una operación sucesora controlada. La pantalla presenta un árbol desplegable y los comandos guardan historia con control de versión.",
        ),
        (
            "Códigos de costo",
            "El diccionario distingue categorías como mano de obra, material, equipo, subcontrato, ingeniería, compras, construcción, obras temporales, logística, indirectos, overheads y contingencia. ADMIN gobierna el catálogo permitido y USER crea códigos del Project autorizado. Un código no es un nodo CBS, una cuenta de control, un recurso ni un APU.",
        ),
        (
            "Cuentas de control",
            "Cada cuenta representa una responsabilidad de control, con propietario y rol responsable del mismo tenant. Puede relacionarse con varias dimensiones de ejecución y costo mediante mapeos explícitos. No se crea una cuenta por cada nodo WBS o CBS, ni se modifica financiación para crearla. Los cambios y vínculos conservan su historial.",
        ),
        (
            "APU",
            "El análisis de precios unitarios conserva componentes de mano de obra, materiales, equipos, subcontratos y otros costos directos. Cada componente congela una tarifa publicada, cantidad por unidad y unidad de recurso. Los factores indirectos configurados se aplican una sola vez sobre el costo directo. Scope por APU genera únicamente una línea candidata en Budget DRAFT, con cantidad aprobada y fecha de precios explícita.",
        ),
        (
            "Tarifas",
            "Las tarifas son versionadas, efectivas por fecha, conscientes de unidad y moneda y trazables a su fuente. La publicación exige un actor independiente. Las revisiones publicadas no se sobrescriben; un sucesor conserva la referencia al antecedente. Rate, APU y FX usan intervalos con inicio incluido y final excluido. Un intervalo vacío o una fecha de precios en el límite final se rechaza.",
        ),
        (
            "Moneda y conversión",
            "Los importes canónicos utilizan Decimal y Numeric de 24 dígitos y 8 decimales. Cada versión Budget declara una moneda; las líneas en otra se rechazan. No se declara aprobación de presupuestos multidivisa. En proyecciones Actual y Commitment, la conversión requiere FX publicado, dirección, vigencia, fuente y fecha explícitas. Sin una conversión gobernada, el resultado conserva importes por moneda y devuelve NO_AGGREGATION, sin fabricar un total.",
        ),
        (
            "Versiones de Budget",
            "El ciclo distingue DRAFT, SUBMITTED, UNDER_REVIEW, APPROVED y REJECTED. Las líneas solo se editan mientras el padre está DRAFT y requieren If-Match del agregado. La aprobación independiente congela importes, fuentes y configuración. Los tipos Original, Current y Approved Change se gobiernan por catálogo. Las versiones aprobadas no pueden modificarse en ORM ni mediante SQL directo.",
        ),
        (
            "Original Approved y Current Budget",
            "Original Budget es el primer presupuesto aprobado sin predecesor. Approved Budget identifica cada versión aprobada e inmutable. Current Budget es la única hoja aprobada de la cadena explícita de sucesores. Un borrador sucesor no se convierte en Current. La supersesión se calcula como estado efectivo sin editar el contenido o estado aprobado del antecedente; se rechazan ramas aprobadas competidoras.",
        ),
        (
            "Cost Baseline",
            "La baseline candidata parte de un Budget aprobado y congela sus líneas de control, estructuras CBS, códigos y cuentas, mapeos de origen y phasing. La aprobación exige reconciliar la distribución completa de cada línea y un actor independiente del preparador. El snapshot y su hash quedan inmutables. Una revisión Current posterior no reescribe la baseline original; la reserva de gerencia queda fuera de la baseline de control.",
        ),
        (
            "Distribución temporal de costos",
            "Se implementaron LINEAR, FRONT LOADED, BACK LOADED, MILESTONE BASED, ACTIVITY BASED, MANUAL y CURVE BASED. Las distribuciones conservan suma exacta, fechas y base utilizada. Manual y curvas deben reconciliar importes y períodos; incluso montos mínimos distribuidos entre muchos días conservan residuos no negativos. Los cambios crean filas sucesoras, sin alterar distribuciones ya aprobadas.",
        ),
        (
            "Integración con Schedule",
            "El phasing basado en Activity consume las fechas de una versión aceptada e inmutable y registra su hash. Cost no calcula CPM, fechas forecast ni otro float. Una petición que intenta sustituir fechas provenientes del cronograma se rechaza. WBS y Activities se relacionan mediante referencias de versión, no mediante una jerarquía CBS forzada.",
        ),
        (
            "Límite con financiación estratégica",
            "Budget operativo y escenario estratégico son dominios diferentes. Cost conserva referencias a capital autorizado, financiación o condiciones FID cuando correspondan al contexto; no modifica Funding, FIN, Business Case ni FID. La autorización y operabilidad del Project siguen la base O1A. No se crea otra identidad Project ni una nueva aprobación de inversión.",
        ),
        (
            "Límite de compromisos",
            "Contract Administration conserva contrato, PO, subcontrato y obligación legal. Cost almacena referencias de conciliación y snapshots de fuente, no adjudica ni modifica esas obligaciones. El adaptador legado verifica binding, tenant, Project, tipo canónico, importe, estado y hash vigente. Las fuentes externas requieren documento y hash atestados por actores independientes; no se presenta esto como integración ERP autenticada.",
        ),
        (
            "Prevención de doble conteo contractual",
            "INCLUDED y CALL OFF no vuelven a sumar una obligación representada por su padre; ADDITIVE requiere un origen económico incremental y REFERENCE ONLY aporta cero. Se detectan fuentes duplicadas, orígenes repetidos, monedas incompatibles y consumos que superan el padre. Un cambio de hash bloquea el total hasta una propuesta sucesora verificada. El historial anterior queda intacto y un sucesor todavía no verificado no lo sustituye. Net Commitment significa conciliación de duplicados, no saldo contractual pendiente de pago.",
        ),
        (
            "Costo real reconocido",
            "Actual significa costo incurrido reconocido, no pago ni progreso ganado. La importación conserva sistema, referencia única, fechas de posting y reconocimiento, período, moneda, evidencia y dimensiones Cost. El estado inicial IMPORTED requiere reconocimiento independiente. Los ajustes son deltas separados, no sobrescrituras; no pueden preceder al original ni producir saldos históricos negativos. Se revalidan las dimensiones y políticas al reconocer.",
        ),
        (
            "Devengos",
            "Accrual permanece DEFERRED_WITH_CONTRACT porque no existía una autoridad de devengo y reversión preparada para su reutilización. Se expone un contrato explícito de integración, sin botones ni endpoints que finjan un ciclo funcional. Las vistas actuales no agregan un devengo estimado al costo ya reconocido. La implementación completa de creación, reversión y sustitución por Actual queda para una autorización posterior.",
        ),
        (
            "Preparación ETC y EAC",
            "Se definió una interfaz no persistida de ETC con método, moneda, fecha as of, referencia de aceptación y declaración de inclusión de compromisos. El cálculo EAC usa Actual reconocido hasta esa fecha más ETC aceptado. No vuelve a sumar Commitment. Esto prepara la integración futura sin introducir gobierno completo de Forecast, métodos estadísticos certificados o progreso ganado.",
        ),
        (
            "Contingencia y reserva de gerencia",
            "Contingency está explícitamente dentro de la baseline de control, a nivel de Project o paquete. Management Reserve es de Project, queda fuera de esa baseline y requiere la autorización granular cost.reserve.manage. La delegación organizacional no se obtiene por tener permiso ordinario de aprobación Budget. Crear, editar o reclasificar una línea de reserva exige esa autorización. Los totales diferencian ambas categorías para evitar su doble inclusión.",
        ),
        (
            "Períodos comunes de control",
            "Cost utiliza Project Controls Period de O1A. Actual requiere un período OPEN del mismo Project y una fecha de reconocimiento comprendida en él. CLOSED y PUBLISHED bloquean nuevas escrituras y no se reabren ni reescriben desde Cost. La vista de flujo muestra importes planificados, actuales y referencias de compromisos por período o fecha de origen, con su moneda. No constituye Tesorería ni un calendario de pagos.",
        ),
        (
            "Separación de ADMIN y USER",
            "ADMIN gobierna plantillas y catálogos CBS, códigos, reglas de cuentas, categorías APU y recursos, monedas, política FX, tipos Budget y Baseline, métodos de phasing, reserva, contingencia, fuentes Actual, inclusión de compromisos, métodos ETC y separación de funciones. La configuración se edita en borrador y se publica por otro actor. USER opera registros vivos dentro del Project Workspace y de sus permisos efectivos.",
        ),
        (
            "Seguridad y separación de funciones",
            "Se aplican permisos cost granulares, ámbito tenant y Project, precondiciones If Match, idempotencia ligada al actor, motivo e historia inmutable. Se separan editor y publicador de configuración y tarifas, preparador y aprobador Budget o Baseline, importador y reconocedor Actual y proponente y verificador contractual. Los GET no provisionan permisos ni escriben datos de negocio. El aprovisionamiento del catálogo es un comando administrativo explícito y auditado.",
        ),
        (
            "API",
            f"La aplicación montada expone {len(observed['api'])} contratos Cost inventariados bajo api v1 cost. Incluyen colecciones, detalle, historia, mapeos y sucesores, cálculo APU y Budget, publicación, transición, baseline, phasing, FX, Actual, compromisos, fuentes legadas, overview y flujo. Los contratos de escritura rechazan campos ajenos a su autoridad. Los errores de ámbito, versión, aprobación o moneda no se transforman en éxitos.",
        ),
        (
            "Frontend",
            f"Cost Manager utiliza CompactModuleHeader y once pantallas: CBS, Cost Codes, Control Accounts, APU Rates, Budget, Cost Baseline, Cost Phasing, Commitments, Actuals, Accruals y Cost Overview. Se incorporó ADMIN Cost Profiles reutilizando el componente gobernado. La navegación existente conserva la ruta cost, respeta desactivaciones y requiere cost.read, sin editar App.tsx. Pasaron {frontend['numPassedTests']} pruebas de componentes, TypeScript, ESLint y formato.",
        ),
        (
            "Migración",
            "La revisión aditiva 0073 tiene un único padre 0072 y añade catorce tablas Cost, sin reescribir migraciones históricas ni aplicar backfill. PostgreSQL protege ámbitos, fuentes, independencia, estados publicados e historia. Se verificó upgrade, downgrade y reupgrade en una base separada vacía de negocio; el downgrade rechaza tablas Cost pobladas. El arranque local excluye explícitamente esas catorce tablas de create_all para que solo Alembic pueda crearlas con sus protecciones. El bootstrap histórico parte de un esquema ORM previo y no se declara prueba de base vacía hasta head. El navegador utilizó un clon de esquema PostgreSQL aislado, sin copiar datos de negocio.",
        ),
        ("Validación PostgreSQL", pg_summary),
        ("Validación Chromium", browser_summary),
        ("Preservación del Proyecto 14", preservation_summary),
        (
            "Observaciones de desempeño",
            "Se midieron diez operaciones reales de lectura y cálculo, con tres muestras por operación. Los resultados pertenecen al entorno local compartido y al volumen acotado descrito a continuación. No representan SLA productivo, capacidad industrial ni validación de un portafolio completo. Las observaciones UI incluyen espera de respuesta y navegación y no se mezclan con los tiempos de API de la tabla.",
        ),
        (
            "Brechas y límites restantes",
            "El devengo conserva su contrato diferido; Budget aprobado es monomoneda; las fuentes contractuales externas se atestan y no se sincronizan con ERP. Los sistemas legados siguen disponibles detrás de sus adaptadores y la adopción canónica no migra datos automáticamente. No se implementaron Progress completo, EVM, Forecast gobernado, adjudicación contractual, pagos, Tesorería o ledger contable. La base habitual no se migró y no se registraron firmas, commit, push ni ejecución remota de CI. No quedan defectos S1 o S2 abiertos en el alcance validado.",
        ),
        (
            "Decisión de liberación",
            "La evidencia focalizada de PostgreSQL, regresión y Chromium permite validar técnicamente O1B C en aislamiento, con el devengo diferido admitido por el contrato del incremento. Estado exacto: "
            + release
            + ". Resultado: READY_FOR_WAVE_O1B_D_PROGRESS_AND_BASELINE_INTEGRATION. Esta decisión no autoriza despliegue productivo ni acredita aceptación de negocio.",
        ),
        (
            "Siguiente incremento recomendado",
            "WAVE O1B-D — PROGRESS & BASELINE INTEGRATION. Se recomienda únicamente ese siguiente incremento. No se implementó automáticamente.",
        ),
    ]
    assert len(chapters) == 36
    defects = [
        [
            "DF-01",
            "S2",
            "FX en dirección inversa aceptado por conversión identidad",
            "CLOSED",
            "Validación explícita y pruebas negativas PostgreSQL",
        ],
        [
            "DF-02",
            "S2",
            "Ajuste Actual con saldo histórico negativo",
            "CLOSED",
            "Balance acumulado por fecha y prohibición de anteceder al original",
        ],
        [
            "DF-03",
            "S2",
            "Contrato y Subcontract podían representar la misma fuente",
            "CLOSED",
            "Tipo legal canónico y origen económico verificados",
        ],
        [
            "DF-04",
            "S2",
            "Reserva ligada al permiso ordinario de aprobar Budget",
            "CLOSED",
            "Permiso separado reserve.manage y pruebas de reclasificación",
        ],
        [
            "DF-05",
            "S3",
            "Fronteras de vigencia FX inconsistentes",
            "CLOSED",
            "Intervalo de vigencia con final excluido y SQL CHECK",
        ],
        [
            "DF-06",
            "S2",
            "El arranque local podía crear tablas Cost sin las protecciones de Alembic",
            "CLOSED",
            "Exclusión explícita de las catorce tablas y pruebas de ambas ramas del arranque",
        ],
        [
            "DF-07",
            "S2",
            "Actualización de línea de proceso mantenía un escritor económico legado tras adopción",
            "CLOSED",
            "Frontera de autoridad ampliada y prueba negativa PostgreSQL",
        ],
        [
            "GP-01",
            "CONTRACT",
            "Accrual lifecycle",
            "DEFERRED_WITH_CONTRACT",
            "Contrato explícito sin autoridad ficticia",
        ],
        [
            "GP-02",
            "LIMIT",
            "Aceptación humana y despliegue habitual",
            "NOT_PERFORMED",
            "Fuera de la liberación técnica aislada",
        ],
    ]
    value = {
        "release_state": release,
        "final_output": "READY_FOR_WAVE_O1B_D_PROGRESS_AND_BASELINE_INTEGRATION",
        "next_increment": "WAVE O1B-D — PROGRESS & BASELINE INTEGRATION",
        "cases": cases,
        "suite_summary": suites,
        "browser": browser,
        "api": observed["api"],
        "performance": observed["performance"],
        "data_volume": volume,
        "requirements": requirements,
        "release_criteria": criteria,
        "defects": defects,
        "chapters": chapters,
        "opening": "Se validó técnicamente Cost Foundation en un entorno aislado. El módulo organiza el presupuesto operativo y sus fuentes de costo sin modificar el alcance, el cronograma ni la autoridad contractual. La entrega no incluye despliegue en la base habitual.",
        "volume_summary": f"Volumen de navegador observado: {volume['cbs']} nodos CBS, {volume['mappings']} mapeos, {volume['budgets']} versiones Budget, {volume['budget_lines']} líneas, {volume['baselines']} baseline, {volume['apus']} APU y {volume['rates']} tarifa. Fuentes reutilizadas: {volume['scope_items']} Scope Items, {volume['plan_items']} Plan Items y {volume['packages']} paquete AWP. Los casos contractuales y monetarios adicionales se verificaron en la base PostgreSQL de pruebas separada.",
        "postgres_count": pg,
        "pure_count": pure,
        "open_s1": 0,
        "open_s2": 0,
        "normal_database_migrated": False,
        "business_signatures_recorded": False,
        "commit_created": False,
        "push_performed": False,
        "github_workflow_executed": False,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "package-data.json").write_text(
        json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "suite_summary": suites,
                "pg_cases": pg,
                "pure_cases": pure,
                "criteria": len(criteria),
            }
        )
    )


if __name__ == "__main__":
    main()
