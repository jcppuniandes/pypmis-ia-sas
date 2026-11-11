"""Narrative and evidence slots for the O2A technical report."""

NEXT = "WAVE O2B — PROCUREMENT, MATERIALS & LOGISTICS FOUNDATION"


def chapters(data):
    gates = data.get("gate_status", {})
    pg = data.get("postgresql", {}).get("counts", {})
    browser = data.get("browser", {})
    uat = browser.get("uat", {})
    obs = uat.get("observations", {})
    perf = browser.get("performance", {})
    release = data.get("release_marker") or "Sin estado de release validado"
    confirmed = (
        gates
        and all(x == "PASS" for x in gates.values())
        and release.startswith("WAVE_O2A_")
    )

    def state(name):
        return gates.get(name, "PENDING")

    def counts():
        if not pg.get("total", pg.get("tests", 0)):
            return "La ejecución final todavía no aporta un JUnit verificable."
        return f"JUnit: {pg.get('total', 0)} casos, {pg.get('passed', 0)} aprobados, {pg.get('failed', 0)} fallos, {pg.get('errors', 0)} errores y {pg.get('skipped', 0)} omitidos."

    return [
        (
            "Resumen ejecutivo",
            "Ingeniería gestiona la identidad técnica del entregable, su revisión, su aprobación y su liberación IFC. AWP sigue siendo dueño del paquete y de su liberación operativa. "
            + (
                "Los controles de cierre exigidos quedaron verificados en el entorno aislado."
                if confirmed
                else "El estado de cierre depende de las comprobaciones descritas en las secciones 29 a 35."
            ),
        ),
        (
            "Línea base O1 y O2",
            "Se reutilizó el árbol de fuentes 3889d71. O1 conserva el contexto operativo del proyecto, Scope y Plan, cronograma P6, Cost, Progress y Forecast. Se aplicó la separación de autoridades de la arquitectura maestra O2.",
        ),
        (
            "Hallazgos del repositorio",
            "El gestor documental, AWP y los comandos del contexto operativo ya resolvían almacenamiento, paquetes, identidad, permisos y concurrencia. Faltaba un registro técnico con revisiones, revisión independiente, liberaciones y enlaces versionados. Se añadió esa autoridad sin replicar servicios existentes.",
        ),
        (
            "Autoridad de Ingeniería",
            "El entregable define qué se emite. La revisión fija el contenido y la liberación IFC fija el hecho utilizable en construcción. Design Package agrupa entregables técnicos; un EWP es un paquete de AWP y conserva su ciclo independiente.",
        ),
        (
            "Registro de entregables",
            "Código único en el proyecto, tipo, disciplina, título, responsable y fechas se registran con auditoría. La lista admite filtros y cursor; los comandos de actualización verifican ETag y permisos. Una configuración publicada habilita el trabajo en el proyecto.",
        ),
        (
            "Tipos y disciplinas",
            "ADMIN define catálogos y códigos mediante el perfil de Ingeniería. El servicio valida las selecciones frente a la revisión publicada. No añade a los catálogos valores escritos por el usuario en un entregable.",
        ),
        (
            "Modelo de revisiones",
            "Cada revisión pertenece a un único entregable y conserva su código, propósito, estado y versión. Una revisión aprobada o rechazada no se reescribe. Para cambiar el contenido se crea una sucesora enlazada.",
        ),
        (
            "Propósito de emisión",
            "El propósito identifica el uso previsto de la revisión. Un propósito de construcción no aprueba la revisión, no emite IFC y no cambia el estado de un paquete.",
        ),
        (
            "Límite con el gestor documental",
            "Se enlazan el documento y su adjunto existente en CDE. Ingeniería fija sus identificadores y huella SHA-256, comprueba acceso y vigencia de la fuente, y evita duplicar binarios. Una carga no equivale a aprobación técnica ni a liberación IFC.",
        ),
        (
            "Flujo de revisión",
            "La ronda pasa por envío, inicio, aceptación técnica y verificación antes de la aprobación. También admite devolver a corrección o rechazar. El historial distingue las rondas y retiene las decisiones anteriores.",
        ),
        (
            "Comentarios y respuestas",
            "El revisor registra comentarios por disciplina y severidad. El responsable responde y un actor autorizado cierra el comentario. Los comentarios bloqueantes impiden aceptar la ronda hasta que se resuelvan.",
        ),
        (
            "Aprobación independiente",
            "La aprobación es un comando separado y requiere la verificación previa y el permiso correspondiente. La política controla separación entre los actores de preparación, revisión, verificación, aprobación y liberación; el contenido aprobado queda fijo.",
        ),
        (
            "Liberación IFC",
            "Un actor autorizado emite la liberación IFC de manera explícita, con fecha efectiva y referencia. El hecho inmutable fija el identificador de revisión y de aprobación, la fuente documental y la huella del snapshot. El estado de aprobación no se usa como sustituto del hecho IFC.",
        ),
        (
            "Sucesión de revisiones",
            "La revisión más reciente y el IFC efectivo son hechos distintos. Una sucesora aprobada o con liberación futura no desplaza el IFC anterior antes de la fecha efectiva. Una sucesora pendiente puede figurar vencida aunque el IFC anterior continúe vigente.",
        ),
        (
            "Integración con EWP",
            "Los enlaces entre revisiones o grupos de diseño y paquetes AWP conservan ambos identificadores y su historial de altas y retiros. Las relaciones admiten varios paquetes y entregables; Ingeniería no crea EWP ni modifica su estado.",
        ),
        (
            "Integración con Scope y Plan",
            "Los enlaces usan identificadores canónicos de elementos Scope y Plan del mismo proyecto. La validación se hace contra la autoridad existente; el registro técnico no cambia cantidades, geometría, estrategia ni baseline.",
        ),
        (
            "Integración con Schedule",
            "WBS y actividad se fijan a una versión P6 aceptada y al identificador externo exacto. La sustitución de esa versión marca el enlace para revisión si el objeto subsiste, o como roto si desaparece. No se remapea por nombre ni se escribe P6.",
        ),
        (
            "Límite con Cost",
            "Las referencias de costo apuntan al objeto autorizado cuando aplica. El módulo no calcula ni cambia presupuesto, costo real, compromiso, SOV, pago ni baseline. Las pruebas de consumidores comparan los datos de origen antes y después.",
        ),
        (
            "Límite con Progress",
            "Progress puede usar una liberación IFC como evidencia explícita de un hito cuando el hash, el período y los enlaces Scope y Plan coinciden. No se convierte en cantidad medida ni calcula avance físico por sí sola.",
        ),
        (
            "Límite con Forecast",
            "Forecast puede aceptar como insumo explícito la fecha prevista de una revisión identificada y su hash. Rechaza fechas discrepantes y fuentes sustituidas. La aprobación y la inmutabilidad de la versión siguen bajo la autoridad de Forecast.",
        ),
        (
            "Engineering Readiness",
            "El proveedor evalúa cobertura, vigencia, fecha de corte, integridad de la liberación y trazabilidad. AWP incorpora la referencia de evidencia a su propia evaluación y mantiene sus demás restricciones. Una evaluación READY no libera un paquete.",
        ),
        (
            "Restricciones de ejecución",
            "La liberación IFC no cierra restricciones. Un comando AWP autorizado puede hacerlo al verificar que el paquete esté vinculado, la fuente siga elegible y la referencia corresponda al hash vigente.",
        ),
        (
            "Interfaces y consultas técnicas",
            "El registro mínimo conserva interfaces e identificadores externos. Las consultas técnicas y RFI no se convirtieron en otro sistema documental ni en autoridad contractual; su ciclo autónomo queda fuera del incremento.",
        ),
        (
            "Separación ADMIN y USER",
            "ADMIN crea y publica revisiones gobernadas de los catálogos, políticas y permisos. USER opera Ingeniería dentro de un proyecto habilitado y solo recibe acciones que puede ejecutar. La configuración publicada no se cambia mediante las rutas genéricas.",
        ),
        (
            "Seguridad y separación de funciones",
            "Cada operación se resuelve en tenant y proyecto, valida permisos y verifica la separación de actores cuando corresponde. ETag evita sobrescrituras y la llave de idempotencia identifica reintentos. Los controles de PostgreSQL respaldan la inmutabilidad y la coherencia de referencias.",
        ),
        (
            "Auditoría",
            "Los eventos registran actor, acción, motivo, alcance, instante y referencia de la entidad. Las relaciones se versionan por adición y los hechos terminales no se sobrescriben. Las consultas operativas no crean eventos ni cambian las fuentes.",
        ),
        (
            "API",
            "La API de Ingeniería expone 39 operaciones sobre 30 rutas: 34 de proyecto y cinco administrativas. Los comandos comparten la infraestructura operativa de autorización y concurrencia. Register, estado, Look-Ahead, fuentes, Readiness e historial se consultan sin mutar registros.",
        ),
        (
            "Interfaz web",
            "Engineering Manager se incorpora a USER con vistas de registro, grupos de diseño, revisiones, revisiones técnicas, IFC, interfaces, enlaces, estado, Look-Ahead e historial. ADMIN publica el perfil en su panel. Las colas de Review e IFC son vistas de la misma proyección de estado.",
        ),
        (
            "Migración",
            "Alembic 20261109_0076 agrega nueve tablas y diez triggers sobre la revisión 20261106_0075. El arranque normal no crea las tablas nuevas automáticamente. El ensayo de ida y vuelta usa una base distinta de la de pruebas de negocio y no incluye backfill ni despliegue en producción.",
        ),
        (
            "Validación PostgreSQL",
            f"Estado: {state('postgresql')}. {counts()} La validación usa bases PostgreSQL aisladas y vincula el resultado con las huellas de los archivos de aplicación y pruebas.",
        ),
        (
            "Validación Chromium",
            f"Estado: {state('chromium_uat')}. Se usan un navegador real, API y PostgreSQL aislados. Escenario: {len(uat.get('checks', []))} comprobaciones registradas; proyecto de prueba {uat.get('project_workspace_id') or 'sin evidencia final'}. El recorrido no se declara exitoso a partir de pruebas simuladas.",
        ),
        (
            "Preservación del Proyecto 14",
            f"Estado: {state('preservation')}. La comparación toma huellas canónicas, registros legacy y referencias de Proyecto 14 antes y después, mediante consultas de solo lectura. No se utilizó ese proyecto para las pruebas de escritura.",
        ),
        (
            "Observaciones de rendimiento",
            f"Estado: {state('performance')}. {len(perf.get('operations', []))} operaciones registradas; tamaño del registro: {perf.get('register_size') or obs.get('register_size') or 'sin medición final'}. Son tiempos del entorno aislado. Las dos colas usan la misma consulta de estado; las cifras no constituyen un SLA de producción.",
        ),
        (
            "Brechas y límites",
            "Interfaces es un registro mínimo y RFI/TQ conserva su autoridad externa. Los selectores de destinos, documentos y grupos muestran la primera página acotada del API; su paginación completa queda pendiente para registros mayores. Las etiquetas opcionales de estado se guardan en ADMIN, pero USER muestra códigos canónicos. Estado y Look-Ahead recorren registros del proyecto; estas mediciones no sustituyen una prueba de escala. SQLAlchemy conserva una advertencia legacy por el ciclo de claves foráneas control_accounts y work_packages. Estos límites no cambian los comandos ni sus controles de seguridad. No se implementaron Procurement, contratos, materiales ni logística.",
        ),
        (
            "Decisión de liberación",
            f"{release}. "
            + (
                f"{data.get('next_increment')}. Validación técnica del incremento en ambiente aislado; no implica despliegue en producción."
                if confirmed
                else "No se declara el cierre técnico mientras falte evidencia exigida o exista un criterio fallido."
            ),
        ),
        ("Siguiente incremento recomendado", NEXT + ". Este incremento no se inició."),
    ]
