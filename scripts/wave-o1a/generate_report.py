"""Source-derived technical Word report; findings come from saved O1A evidence."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import io
import json
from copy import deepcopy
from pathlib import Path
from zipfile import ZipFile

from docx import Document
from docx.shared import Pt
from lxml import etree

ROOT = Path(__file__).resolve().parents[2]
QA = ROOT / "outputs/.qa/wave-o1a-20261019"
OUT = ROOT / "outputs/wave-o1a-20261019"
REFERENCE = (
    ROOT
    / "outputs/business-uat-signoff-20261018/P&Pmis_Informe_Tecnico_Business_UAT_Signoff_20261018.docx"
)
REFERENCE_SHA = "475c1674cf398f005e3239df01cf84c3e649951d8a45b3056d9f0fddf6c7f3a7"
spec = importlib.util.spec_from_file_location(
    "o1a_document_components",
    ROOT / "scripts/business-uat-signoff/generate_signoff_documents.py",
)
assert spec and spec.loader
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)
base.REFERENCE, base.prose = REFERENCE, str
p, h, table = base.paragraph, base.heading, base.table


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def section(doc, number, title, *paragraphs):
    h(doc, f"{number} {title}")
    for paragraph in paragraphs:
        p(doc, paragraph)


def evidence(doc, text):
    result = p(doc, "Evidencia: " + text)
    for run in result.runs:
        run.font.size = Pt(9)


def save(doc, output):
    stream = io.BytesIO()
    doc.save(stream)
    with (
        ZipFile(REFERENCE) as source,
        ZipFile(stream) as generated,
        ZipFile(output, "w") as destination,
    ):
        footer = source.read("word/footer1.xml").replace(
            b"18 octubre 2026", b"20 octubre 2026"
        )
        assert footer != source.read("word/footer1.xml")
        for entry in source.infolist():
            payload = (
                generated.read("word/document.xml")
                if entry.filename == "word/document.xml"
                else footer
                if entry.filename == "word/footer1.xml"
                else source.read(entry.filename)
            )
            destination.writestr(entry, payload)
    with ZipFile(REFERENCE) as source, ZipFile(output) as final:
        assert source.namelist() == final.namelist()
        changed = [
            name for name in source.namelist() if source.read(name) != final.read(name)
        ]
        assert set(changed) == {"word/document.xml", "word/footer1.xml"}
        ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        a, b = [
            etree.fromstring(archive.read("word/document.xml"))
            for archive in (source, final)
        ]
        for path in ("w:body/w:sectPr", "w:body/w:p"):
            assert etree.tostring(a.find(path, ns)) == etree.tostring(b.find(path, ns))
    return {
        "path": str(output),
        "sha256": digest(output),
        "parts_preserved": 17,
        "changed_parts": changed,
    }


def build(data):
    doc = Document(REFERENCE)
    logo, section_properties = (
        deepcopy(doc.paragraphs[0]._p),
        deepcopy(doc._element.body.sectPr),
    )
    for element in list(doc._element.body):
        doc._element.body.remove(element)
    doc._element.body.append(logo)
    doc._element.body.append(section_properties)
    p(doc, "Wave O1A\nContexto operacional y períodos de control", "Title")
    p(
        doc,
        "P&Pmis Construction AI\nInforme técnico de implementación\n20 de octubre de 2026",
        "Subtitle",
    )
    lead = "Implementamos la base operacional canónica de Project Controls y verificamos sus límites de identidad, autorización y período en una instalación PostgreSQL aislada. "
    lead += (
        "La validación técnica O1A quedó cerrada; la siguiente implementación requiere autorización expresa."
        if data["release_validated"]
        else "La implementación está guardada, pero la liberación técnica permanece pendiente de los resultados y bloqueos indicados en este informe."
    )
    p(doc, lead)
    p(
        doc,
        "Estado técnico: "
        + data["release_state"]
        + ". El estado estratégico y las firmas de negocio permanecen sin cambios.",
    )

    section(
        doc,
        1,
        "Resumen ejecutivo",
        "O1A incorpora un contexto operacional basado en enterprise_workspaces de tipo PROJECT, un vínculo explícito hacia el agregado heredado projects, un resolutor de autorización por modelo de gobierno, perfiles ADMIN y un período común de control. No crea otro maestro de proyectos ni convierte la igualdad numérica de identificadores en una relación de negocio.",
        "Las operaciones materiales requieren permisos, contexto, estado vigente y control de concurrencia. Los perfiles publicados y las cabeceras publicadas son inmutables; los reintentos conservan el resultado original mediante recibos de comando. El recorrido del navegador usa la API y PostgreSQL reales, sin respuestas simuladas. Las pruebas de componentes se presentan separadamente y no sustituyen esa evidencia.",
        "El alcance termina en esta fundación. No se implementaron baselines de Scope, Schedule o Cost, aprobación de Progress o Change, Forecast, EVM ni adjudicación Procurement. No se reanudó el signoff estratégico ni se aplicó una migración a la base local del usuario.",
    )
    section(
        doc,
        2,
        "Línea base",
        f"El corte parte del commit {data['baseline_head']} en main. Se preservó el trabajo documental anterior y se capturaron huellas de {data['baseline_source_files']} archivos de producto antes de las modificaciones O1A. La arquitectura previa y sus matrices permanecen como línea base; este informe describe el incremento ejecutado posteriormente.",
        "La base local pypmis se consultó en transacciones READ ONLY para conservar el Proyecto 14. La validación funcional empleó los servicios separados de docker-compose.wave-o1a.yml: PostgreSQL o1a, PostgreSQL o1a_migration, API en 8851 y frontend en 5511. Sus volúmenes son independientes de los servicios habituales 8000 y 5173. Los escenarios usan tenants y actores de prueba, no registros de producción.",
    )
    evidence(
        doc,
        "docs/validation/wave-o1a-20261019/preservation-before.json y preservation-identity-before.json; outputs/.qa/wave-o1a-20261019/final-ddl-refresh.json.",
    )
    section(
        doc,
        3,
        "Hallazgos del repositorio",
        "La aplicación existente conserva capacidades operacionales reales que dependen de projects.id: cantidades BIM/APU, cronogramas, cuentas de control, costos, progreso, contratos, documentos y trabajos de cálculo. La creación canónica de Project Workspace intencionalmente no crea esa fila heredada. Reutilizar esos consumidores exige un adaptador explícito y no una coincidencia de nombres, códigos o IDs.",
        "Se reutilizaron AdminConfiguration, EnterprisePermissionContext, SecurityEvent, la infraestructura de autenticación, el formato ETag y el contexto Workspace. No se sobrecargó una tabla de período heredada con semántica diferente. El nuevo módulo concentra los comandos O1A y conserva la autoridad de cada fuente estratégica y operativa.",
    )
    section(
        doc,
        4,
        "Identidad canónica del proyecto",
        "OperationalProjectContext resuelve tenant, ID canónico, external_key, Record Code, estado, Governance Model, Project Type, autorización, binding, perfil efectivo, revisión de política, período actual, roles, comandos y bloqueos. El identificador canónico continúa siendo enterprise_workspaces.id con workspace_type_code=project; projects.id sigue siendo únicamente una referencia operacional heredada.",
        "Los casos aislados usan deliberadamente números diferentes para las dos identidades. Un proyecto puede operar en O1A sin fila legacy cuando la política lo permite. NO_LEGACY_BINDING_REQUIRED es una decisión explícita; MISSING informa una vinculación todavía no resuelta. La activación no genera una fila ni un enlace como efecto oculto.",
    )
    section(
        doc,
        5,
        "Dependencias heredadas identificadas",
        f"El inventario estático registra {data['inventory_counts']['fk_entities']} entidades con FK a projects.id, {data['inventory_counts']['backend_function_candidates']} funciones candidatas backend y {data['inventory_counts']['frontend_route_references']} referencias explícitas frontend. Son 642 registros de distinta granularidad, no 642 funcionalidades independientes. Los predicados de búsqueda y las huellas de origen están conservados para distinguir el inventario inicial de la implementación nueva.",
        "Cada registro incluye consciencia canónica y destino de migración. Las 70 entidades corresponden a la línea base anterior a O1A; OperationalProjectBinding añade su propia FK de adaptación. El inventario cubre referencias directas, no demuestra por sí solo accesibilidad transitoria de cada rama. No se eliminaron consumidores ni se refactorizaron todos sus agregados.",
    )
    table(
        doc,
        ["Clasificación", "Registros"],
        [[key, str(value)] for key, value in data["migration_counts"].items()],
        [5.6, 1.46],
    )
    section(
        doc,
        6,
        "Arquitectura del vínculo operacional",
        "OperationalProjectBinding registra tenant, Workspace canónico, Project legacy opcional, estado, revisión, versión, autor, validador, fuente, motivo y vigencia. La autoridad del vínculo pertenece a O1A, no al legado ni a una proyección QRA. La creación, reconciliación y revocación son comandos explícitos auditados.",
        "La reconciliación admite una selección autorizada o una relación previa verificable en referencias forward/reverse existentes. Si aparecen varios candidatos, otra relación vigente o un registro incompatible, no elige arbitrariamente el primero. Las revisiones sustituidas y revocadas conservan identidad e historia; no hay borrado del Project original.",
    )
    section(
        doc,
        7,
        "Invariantes del vínculo",
        "Se validan tenant, existencia y tipo canónico, estado operacional admisible, existencia y tenant del legado, compatibilidad de referencias y unicidad activa en ambos sentidos. Las restricciones e índices PostgreSQL refuerzan la unicidad; los triggers rechazan cruces de tenant/tipo y alteraciones de la historia. Una referencia extranjera usa respuestas no reveladoras conforme a la plataforma.",
        "If-Match protege la revisión esperada. La primera creación usa versión 0 del vínculo ausente; las posteriores usan la versión actual. Una clave de idempotencia con el mismo actor y contenido devuelve el recibo original; reutilizarla con otra petición se rechaza. La reconciliación respeta la separación de funciones configurada.",
    )
    section(
        doc,
        8,
        "Contrato común de autorización",
        "OperationalAuthorizationDecision entrega si el contexto puede operar, ruta, fuente, referencia, as_of, vigencia, alcance, bloqueos, restricciones de compromiso, advertencias y hash de la fuente. Los errores distinguen vínculo requerido o ambiguo, proyecto no activo y acceso no autorizado. Las consultas nuevas no provisionan permisos ni mutan estado de negocio.",
        "ACTIVE no se traduce en autorización para gastar, adjudicar, publicar un baseline o aprobar avance. commitment_authorized no se activa por defecto. El resultado proyecta restricciones hacia futuros comandos O2, pero no implementa esos comandos ni sustituye sus controles de dominio.",
    )
    section(
        doc,
        9,
        "Ruta Capital Owner",
        "CAPITAL_OWNER lee la decisión vigente Gate07K y el estado PostFID correspondiente, verifica actualidad de hashes/configuración y conserva la diferencia entre condiciones que bloquean activación y condiciones que restringen compromisos. Una fuente ausente, obsoleta o incompatible impide la entrada operacional; no se copia una aprobación FID a una bandera operacional editable.",
        f"Las pruebas positivas atravesaron las decisiones y activación canónicas reales en tenants aislados {data['owner_current']['tenant_id']} y {data['owner_commitment']['tenant_id']}. Los Workspace fueron {data['owner_current']['project_workspace_id']} y {data['owner_commitment']['project_workspace_id']}, con inicializador y activador distintos. El segundo caso conserva O1A-COM-01 OPEN como commitment-only sin bloquear contexto. La evidencia Class B controlada es una fixture UAT y no aceptación productiva ni firma humana.",
    )
    section(
        doc,
        10,
        "Ruta Contractor Delivery",
        "CONTRACTOR_DELIVERY reutiliza la fuente contractual de la creación canónica: cliente, contrato, alcance y autorización de movilización/NTP según la ruta existente. No exige un FID Owner ni inventa Funding o FEL cuando no corresponden. Las fechas futuras o vencidas declaradas en la autorización fallan de forma cerrada.",
        "La validación comprueba autorización legítima, ausencia de autorización y contexto independiente de Owner. No se construyó un segundo registro de contratos ni una adjudicación comercial nueva dentro de O1A.",
    )
    section(
        doc,
        11,
        "Ruta Direct Internal",
        "DIRECT_INTERNAL consume referencia de autorización interna y sponsor aprobados, con fecha efectiva y alcance/contexto disponibles. Conserva el hash de esa fuente y la política aplicable; el permiso de entrada no habilita compromisos, presupuesto ni baseline. No impone las puertas exclusivas de Capital Owner.",
        "Las fixtures diferencian proyecto activo autorizado, proyecto inactivo y fuente interna faltante, futura o vencida. Los permisos siguen limitados por el Workspace asignado; pertenecer al mismo tenant no permite operar otro proyecto.",
    )
    section(
        doc,
        12,
        "Perfil operacional reutilizable",
        "El Operational Profile reutiliza AdminConfiguration con kind=operational_profile. Incluye alcance e herencia, Governance Model y Project Type, vigencia, setup requerido, cadencia, zona horaria, cutoff, reglas de Data Date, binding, referencias futuras de baseline/change/progress/forecast, horizonte lookahead, evidencia y separación de funciones.",
        "Las referencias downstream son contratos de configuración, no funcionalidades O1B/O1C terminadas. El resolutor considera tenant, contexto, aplicabilidad, alcance y ventana efectiva; no selecciona simplemente la última fila. Perfiles de igual prioridad incompatibles producen un error explícito en vez de una elección arbitraria.",
    )
    section(
        doc,
        13,
        "Período común de Project Controls",
        "ProjectControlsPeriod pertenece al Workspace canónico. Registra código, inicio/fin, cutoff con offset, zona IANA, estado, revisión, versión, actores y fechas de las transiciones, schedule_data_date opcional, política exacta y referencia de reapertura. La política de calendario admite weekly, biweekly, monthly y custom; no se codificó un único calendario mensual global.",
        "La fecha de datos de P6 permanece independiente del cutoff. Tampoco se equipara con fecha contable, ocurrencia de evento o recepción. La zona de negocio se conserva incluso cuando PostgreSQL normaliza el instante del cutoff para almacenamiento.",
    )
    section(
        doc,
        14,
        "Ciclo del período y publicación",
        "OPEN permite la captura futura conforme a las reglas de cada dominio. REVIEW representa el corte candidato para revisión; CLOSED fija las referencias de cabecera aprobadas; PUBLISHED emite metadatos de cabecera inmutables. Las transiciones son comandos, no un PATCH genérico de estado. Una política normal permite un OPEN/REVIEW por proyecto y perfil; el paralelismo exige una configuración explícita.",
        "La publicación O1A no fabrica snapshots de Cost, Schedule, Progress, Forecast o EVM ni un informe integral de Project Controls. Reopen crea una nueva revisión y mantiene la publicación anterior y su política original. El período publicado no se edita ni se reabre en su misma fila.",
    )
    section(
        doc,
        15,
        "Ciclo y vigencia de políticas",
        "DRAFT es editable con versión actual; PUBLISHED es inmutable y requiere un sucesor DRAFT para cualquier modificación. Las revisiones publicadas tienen vigencia y aplicabilidad verificadas. Los períodos históricos conservan configuration_id, revisión y hash resueltos al abrirse, aunque una revisión posterior entre en vigor.",
        "La separación de funciones no se limita al creador original: cuando está configurada, el autor y el último editor material de la revisión no pueden autopublicarla. La procedencia del editor se obtiene del recibo de comando inmutable, no de un campo que el cliente pueda falsificar. Las rutas genéricas de configuración derivan esta clase de política a su API gobernada.",
    )
    section(
        doc,
        16,
        "Separación entre Admin y User",
        "ADMIN configura y publica perfiles reutilizables. USER resuelve un proyecto, consulta autorización, realiza onboarding autorizado y gestiona períodos según sus deberes. El cambio de modo de presentación no constituye una concesión de autoridad: cada endpoint vuelve a validar permiso y alcance.",
        "La pantalla administrativa se integró en Process Configuration mediante Operational Profiles. Operational Setup se abre con la identidad canónica dentro de Workspace Context. No se creó otra fuente de navegación ni se publicaron menús reservados como funciones desarrolladas.",
    )
    section(
        doc,
        17,
        "Seguridad y separación de funciones",
        "Se provisionan deberes granulares para administrador operacional, administrador de proyecto, Project Manager, Project Controls Manager, Planner, Cost Controller, Progress Engineer y Executive Viewer. Las asignaciones mantienen tenant y alcance; las políticas de cierre, publicación y reconciliación aplican separación de funciones donde está configurada.",
        "La compatibilidad legacy exige además legacy.execute para escrituras materiales y conserva los permisos específicos del dominio. Los workers vuelven a validar actor, vínculo y autorización. El ciclo diario anónimo se omite con OPERATIONAL_EXECUTION_ACTOR_REQUIRED, sin inventar un usuario de automatización ni escribir KPI.",
    )
    section(
        doc,
        18,
        "Cambios de API",
        f"La API O1A incorpora {len(data['api'])} rutas bajo /api/v1/operational: opciones, contexto, autorización, binding/historia, períodos y perfiles ADMIN. Los comandos requieren Idempotency-Key; las modificaciones y transiciones gobernadas exigen If-Match. Un ETag obsoleto devuelve 412 y una transición o relación incompatible devuelve el código de dominio correspondiente.",
        "La frontera HTTP distingue los cuatro routers legacy inspeccionados de los routers canónicos estratégicos, aunque compartan nombres de parámetros. Primero conserva las comprobaciones de tenant/membership; luego resuelve el vínculo canónico antes de ejecutar la escritura heredada. Las lecturas preexistentes mantienen su comportamiento caracterizado.",
    )
    evidence(
        doc,
        "backend/app/modules/operational_context/router.py; legacy_boundary.py; service.py; README.md; matriz 07_API_Inventory del workbook.",
    )
    section(
        doc,
        19,
        "Cambios de frontend",
        "Operational Setup muestra identidad, modelo, autorización, condiciones, vínculo y legado, perfil vigente, período e historia. Expone únicamente comandos autorizados y explica que ACTIVE no concede compromisos. Los formularios conservan claves de idempotencia durante reintentos y envían versiones actuales.",
        "Operational Profiles permite crear/editar borradores, consultar historia, publicar independientemente y crear sucesores. Se reutilizó CompactModuleHeader y el catálogo de navegación. App.tsx no cambió. El login de la prueba Chromium usa autenticación real con tenant_id explícito y almacena la sesión legítima emitida por la API, porque el login visual actual no ofrece selector multitenant; no simula respuestas ni autorización.",
    )
    section(
        doc,
        20,
        "Esquema y migración",
        "La revisión 20261019_0069 es un sucesor único de 20261011_0068. Añade operational_project_bindings, project_controls_periods y operational_context_commands, junto con índices, restricciones y triggers de inmutabilidad/alcance. Reutiliza AdminConfiguration y no crea operational_projects ni reescribe fuentes históricas.",
        "Se verificó upgrade, downgrade de tablas O1A vacías y re-upgrade en o1a_migration. La cadena histórica requiere un esquema ORM inicial: el intento de ejecutarla desde una base completamente vacía falla en su primera revisión por ausencia de tenants. Por ello la prueba acredita la migración aditiva desde el esquema pre-O1A, no una instalación histórica vacía hasta head. La base local del usuario no fue migrada.",
    )
    section(
        doc,
        21,
        "Validación de PostgreSQL",
        "Las pruebas HTTP usan autenticación, RBAC y PostgreSQL reales, sin overrides de permisos ni fuentes Owner falsas. Cubren vínculos, tenant, unicidad, ambigüedad, historia, idempotencia, ETag, rutas de gobierno, estados y calendarios del período, política, GET sin escrituras y accesos directos. Las protecciones de publicación también se prueban con SQL directo contra los triggers.",
        "Las regresiones estratégicas de creación/inicialización/activación se separan de las fixtures que representan estados ya existentes. Las pruebas Owner recorren reconciliación, freeze, FID, PostFID, inicialización y activación con actores independientes. Esa distinción evita presentar una fila de fixture active como prueba de activación gobernada.",
    )
    table(
        doc,
        ["Conjunto", "Casos", "PASS", "FAIL", "SKIP"],
        [
            [
                suite["name"],
                str(suite["tests"]),
                str(suite["passed"]),
                str(suite["failed"]),
                str(suite["skipped"]),
            ]
            for suite in data["suites"]
        ],
        [4.1, 0.74, 0.74, 0.74, 0.74],
    )
    p(
        doc,
        f"El inventario contiene {data['distinct_test_cases']} casos distintos: 229 backend/PostgreSQL y 11 frontend. Las nueve comprobaciones de la ejecución dedicada de seguridad también están incluidas en la matriz final de 98; no se suman dos veces al total.",
    )
    section(
        doc,
        22,
        "Validación de Chromium",
        f"El recorrido real registra {len(data['browser'].get('checks', []))} comprobaciones explícitas y resultado {data['browser'].get('result')}. ADMIN configura el perfil y otro actor lo publica; USER muestra contexto canónico, vincula IDs diferentes y abre/revisa/cierra el período; un actor independiente publica y crea una nueva revisión. Executive Viewer no obtiene comandos materiales y los accesos directos indebidos se rechazan.",
        "Los intentos iniciales detectaron selectores estrictos ambiguos y un error del harness de evidencia. La infraestructura Vite sobre Windows también presentó EIO/ENOMEM del watcher. Se corrigieron los selectores y el harness, y se verificó el bundle de producción mediante preview. Los fallos iniciales se conservaron; el recorrido final ejecutó todas las comprobaciones sin mocks.",
    )
    section(
        doc,
        23,
        "Observaciones de rendimiento",
        "Las mediciones locales del navegador incluyen contexto operacional, binding, autorización, lista de períodos y lectura del período actual a través del contexto. Se registran tiempos y estados de las consultas reales. Son observaciones de desarrollo con arranque/importación y entorno compartido; no establecen un SLA, capacidad productiva, percentiles bajo carga ni equivalencia con producción.",
        "Los índices nuevos atienden lookup tenant/proyecto, unicidad de binding, estado/fecha del período y recibos idempotentes. La política reutiliza los índices existentes de AdminConfiguration; no se inventó otro almacén de configuración. La matriz conserva los tiempos de cada observación para análisis posterior.",
    )
    table(
        doc,
        ["Consulta", "N", "Mín ms", "Mediana ms", "Máx ms"],
        [
            [row[0], str(row[1]), *(f"{value:.2f}" for value in row[2:])]
            for row in data["performance"]
        ],
        [2.76, 0.5, 1.26, 1.28, 1.26],
    )
    section(
        doc,
        24,
        "Conservación del Proyecto 14",
        f"El Proyecto 14 canónico conserva code={data['project14']['code']}, external_key={data['project14']['external_key']}, Record Code={data['project14']['record_code']}, status={data['project14']['status']} y version={data['project14']['version']}. La comparación antes/después devuelve {'PASS' if data['project14_preserved'] else 'FAIL'}. Su huella SHA256 de fila es {data['project14_sha256']}.",
        "No existe un Project legacy con ID 14 en la base consultada; los agregados legacy del entorno habitual son 1 a 4. El chequeo no confunde esa ausencia con el Workspace 14. Ninguna fixture lo usó como dato destructivo. Las consultas de conservación se ejecutaron READ ONLY y la implementación no aplicó backfill ni aprovisionamiento a ese proyecto.",
    )
    section(
        doc,
        25,
        "Inventario y destino de consumidores legacy",
        "La hoja 06_Legacy_Consumers conserva los 642 registros y sus referencias de archivo/línea. Las categorías distinguen MIGRATE_IN_O1B, MIGRATE_LATER, KEEP_BEHIND_ADAPTER, READ_ONLY_LEGACY, DEPRECATION_CANDIDATE y UNKNOWN cuando corresponden. Las categorías sin registros no se rellenaron con candidatos inventados.",
        "Los dominios siguen leyendo sus fuentes existentes; O1A no los migra en masa. Las escrituras legacy requieren onboarding explícito con vínculo y permisos antes de ejecutarse. Este cambio de precondición es intencional y exige un rollout controlado: no se crean relaciones para todos los proyectos al desplegar ni se desactiva la seguridad para mantener escrituras anónimas.",
    )
    section(
        doc,
        26,
        "Brechas y límites remanentes",
        "La instalación local habitual permanece sin migración ni bindings automáticos. El despliegue requiere respaldo, upgrade aditivo, aprovisionamiento explícito por un administrador existente y asignación/onboarding controlados. El login visual multitenant y la automatización periódica con principal gobernado no se ampliaron en este incremento.",
        "O1B/O1C siguen pendientes: baselines/fuentes, intercambio P6 gobernado, métodos y aprobación de progreso, integración de Change, Forecast y reporting integral. El esquema histórico desde vacío mantiene su limitación inicial documentada. El signoff estratégico continúa pendiente de representantes y firmas; las fixtures y el resultado técnico O1A no lo sustituyen.",
        "Permanece una observación visual P3 no bloqueante: ACTIVE_IS_NOT_COMMITMENT_AUTHORITY puede mostrarse repetida al combinar avisos del contexto y autorización. No altera permisos, condiciones ni persistencia. No hay S1/S2 abiertos en el alcance revisado.",
    )
    table(
        doc,
        ["Hallazgo", "Estado"],
        [[row[0] + " " + row[2], row[3]] for row in data["defects"]],
        [5.5, 1.56],
    )
    section(
        doc,
        27,
        "Decisión de liberación",
        "Estado exacto: " + data["release_state"] + ".",
        "Salida: " + data["final_output"] + ".",
        "La decisión acredita exclusivamente el incremento O1A verificado. No declara completo el macroproceso operacional ni Project Controls y no equivale a aceptación de negocio. Se conserva "
        + data["strategic_state"]
        + ".",
        "Los ADR O 001 y O 010 avanzan únicamente en identidad/vínculo y autorización O1A. ADR O 002 avanza solo en la fundación de contexto/período. Los ADR de baselines, P6, Progress, Change y Forecast no se marcaron implementados.",
    )
    section(
        doc,
        28,
        "Siguiente incremento recomendado",
        data["next_recommendation"] + ".",
        "No se inicia automáticamente. La siguiente ejecución requiere autorización explícita y debe reutilizar contexto, binding, política y período O1A antes de extender los dominios fuente.",
    )
    return doc


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--authoring-marker-confirmed", action="store_true")
    args = parser.parse_args()
    assert args.authoring_marker_confirmed
    assert digest(REFERENCE) == REFERENCE_SHA
    data_path = ROOT / "docs/validation/wave-o1a-20261019/package-data.json"
    data = json.loads(data_path.read_text(encoding="utf-8"))
    assert len(data["api"]) == 18 and len(data["legacy_consumers"]) == 642
    OUT.mkdir(parents=True, exist_ok=True)
    output = (
        OUT / "P&Pmis_Wave_O1A_Operational_Context_and_Period_Technical_Report.docx"
    )
    result = save(build(data), output)
    assert digest(REFERENCE) == REFERENCE_SHA
    (QA / "documents-build-manifest.json").write_text(
        json.dumps(
            {
                "reference_sha256": REFERENCE_SHA,
                "data_sha256": digest(data_path),
                "output": result,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(json.dumps(result))


if __name__ == "__main__":
    main()
