"""Structured content for the Gate 07J-FEL technical report."""

SECTIONS = [
    (1, "Resumen ejecutivo", "Se implementó Project Definition / FEL Manager como fuente gobernada de definición y madurez para Projects. El módulo administra etapas FEL, evaluaciones versionadas, gaps, acciones, evidencia y readiness sin asumir autoridad de inversión.", "Backend, PostgreSQL, frontend, navegador, Docker y CI local: PASS."),
    (2, "Objetivo funcional", "La capacidad convierte la definición progresiva del Project en evidencia trazable y consumible por Investment Gate Preparation. Su resultado informa preparación; no aprueba inversión ni activa ejecución.", "Salida de capacidad: evidencia gobernada de Project Definition/FEL."),
    (3, "ADR de arquitectura", "El ADR 51 registra ownership, límites, lifecycle, extensibilidad de frameworks, integración por contrato y separación respecto de Gate 07J.", "docs/51-adr-gate07j-fel-project-definition.md"),
    (4, "Baseline reutilizada", "Se extendió el head 20260826_0049 y se conservaron los cambios previos de Portfolio, Gate 07J, AdminConfiguration, RBAC, SecurityEvent y Workspace Context.", "No se reescribieron migraciones ni motores existentes."),
    (5, "REUSE BEFORE CREATE", "Se reutilizaron configuración versionada, resolución por scope, idempotencia, ETag, eventos, navegación USER/ADMIN y el adaptador de fuentes de Investment Gate Preparation.", "La integración añade una fuente; no duplica Gate 07J."),
    (6, "Project lifecycle vs. Project Definition", "Project Definition/FEL mide desarrollo de definición y evidencia previa. No crea, inicializa, activa ni ejecuta Projects y no cambia estados operativos del Project lifecycle.", "Guardrail explícito en servicio, schemas, UI, ADR y pruebas."),
    (7, "FEL stage vs. definition maturity", "La etapa FEL expresa posición en la secuencia configurada; la madurez expresa calidad de definición calculada por evaluación. Ambos valores se persisten y muestran de forma independiente.", "UI: FEL Stage no es Maturity; readiness evalúa ambas dimensiones."),
    (8, "PDRI-compatible vs. contenido licenciado", "Los tipos PDRI_COMPATIBLE y FEL_INDEX_COMPATIBLE aceptan metadatos autorizados suministrados por el tenant. El starter no contiene preguntas, pesos, fórmulas ni material propietario de CII o IPA.", "Framework starter CUSTOM, no propietario y DRAFT."),
    (9, "Governance models", "CAPITAL_OWNER es el modelo predeterminado. Contractor Delivery y Direct Internal son opcionales y sólo aplican si una configuración publicada los habilita; Legacy se mantiene compatible sin forzar FEL.", "Prueba de aplicabilidad y exclusión: PASS."),
    (10, "Autoridad y STOP boundary", "El módulo no implementa Funds, Funding, Investment Decision, FID, GO/HOLD/RECYCLE/KILL, Project Initialization, Activation, Execution, CPM ni P6.", "can_enter_fid=false y límites visibles en USER/ADMIN."),
    (11, "Framework starter", "P&Pmis Custom Project Definition define FEL-1, FEL-2 y FEL-3, categorías genéricas, elementos de referencia, método WEIGHTED_SCORE y dirección HIGHER_IS_BETTER.", "Se crea como DRAFT; nunca se publica automáticamente."),
    (12, "Tipos de framework", "CUSTOM, PDRI_COMPATIBLE y FEL_INDEX_COMPATIBLE comparten el contrato técnico, pero cada framework conserva identidad, versión, dirección de score y umbrales propios.", "La evaluación no cruza umbrales entre frameworks."),
    (13, "Stage structure", "Cada etapa configura código, nombre, secuencia, madurez mínima, threshold, evaluación requerida y evidencia mínima. La progresión normal es secuencial.", "FEL-1 40, FEL-2 65 y FEL-3 80 en el starter CUSTOM."),
    (14, "Controlled stage skip", "Un Project importado puede saltar una etapa sólo cuando el framework lo permite y aporta justificación y referencias de evidencia.", "Prueba negativa sin soporte y prueba positiva controlada: PASS."),
    (15, "Project type mapping", "La configuración decide tipos de Project y governance models aplicables. El selector efectivo se resuelve por contexto y no aplica el framework fuera de su mapping.", "Preview expone aplicabilidad sin persistencia."),
    (16, "Assessment categories", "Las categorías agrupan elementos de definición sin imponer taxonomías propietarias. El starter usa business-basis, scope-definition y delivery-basis.", "Configurables y versionadas por revisión de framework."),
    (17, "Assessment elements", "Cada elemento contiene clave, categoría, nombre, peso, obligatoriedad, evidencia requerida y etapas aplicables. Los resultados conservan score, madurez, comentario, evidencia, blocking y action_required.", "Snapshot de elementos aplicables congelado en cada evaluación."),
    (18, "Scoring direction", "HIGHER_IS_BETTER y LOWER_IS_BETTER se evalúan dentro del framework efectivo. La dirección forma parte del snapshot para impedir reinterpretaciones históricas.", "Pruebas sintéticas de PDRI/FEL-index: PASS."),
    (19, "Framework-specific thresholds", "Los thresholds y niveles de madurez pertenecen a la revisión del framework. Un resultado no reutiliza umbrales globales ni los de otro framework.", "Aislamiento de thresholds validado con tests."),
    (20, "Definition assessment aggregate", "ProjectDefinitionAssessment persiste tenant, Project Workspace, revisión, número, etapa FEL, framework/version, resultados, score, madurez, cobertura, blockers, snapshots, hash, ETag e idempotencia.", "Tabla project_definition_assessments."),
    (21, "Assessment lifecycle", "Los estados DRAFT e IN_PROGRESS permiten edición controlada. COMPLETED calcula resultado y sella la evaluación; REEVALUATION crea una nueva revisión en lugar de alterar historia.", "Completed es inmutable y no eliminable."),
    (22, "Evidence coverage", "La cobertura se calcula sobre elementos aplicables con evidencia requerida. Evidencia ausente genera advertencias o blockers según la configuración del elemento y de la etapa.", "Readiness expone porcentaje y cobertura por evaluación."),
    (23, "Blocking elements", "Un elemento marcado blocking impide readiness aunque el score agregado alcance el threshold. No existe compensación automática por otros elementos.", "Prueba de elemento blocking: PASS."),
    (24, "Definition actions", "ProjectDefinitionAction gestiona gaps con owner, fechas, status, severidad implícita por blocking, evidencia y referencia al elemento/evaluación.", "Tabla project_definition_actions; ETag e idempotencia."),
    (25, "Action blocking policy", "Acciones OPEN o IN_PROGRESS configuradas como blocking impiden readiness. RESOLVED cierra el gap sin borrar el historial.", "Prueba de acción blocking y resolución: PASS."),
    (26, "FEL status aggregate", "ProjectFELStatus conserva etapa actual, estado, framework, source revision/hash, revisión, actores de review y evidencia de skip controlado.", "Tabla project_fel_statuses con una fila vigente por Project Workspace."),
    (27, "Stage review", "El lifecycle soporta IN_STAGE, READY_FOR_STAGE_REVIEW y COMPLETED. Submit review exige readiness; complete exige reviewer distinto cuando la política SOD está activa.", "Segregation of duties validada."),
    (28, "Readiness engine", "El motor produce NOT_STARTED, BLOCKED, STALE o READY considerando etapa, evaluación completada, threshold, madurez, blockers, evidencia, acciones y source freshness.", "No existe bypass manual de blockers."),
    (29, "Staleness", "Cambios en framework efectivo, revisión de source o hash de definición marcan la evidencia previa como STALE. Refresh Preview muestra el impacto antes de aplicar.", "Prueba de staleness: PASS."),
    (30, "Refresh Preview", "La previsualización calcula cambios de configuración, revisión y readiness con persisted=false. No modifica evaluaciones, acciones ni FEL status.", "ADMIN browser: Preview completed with persisted=false."),
    (31, "Lineage y hashes", "framework hash, source snapshot, assessment hash y definition_readiness_hash permiten demostrar qué configuración y evidencia produjeron cada resultado.", "Hashes incluidos en API, history y contrato Gate 07J."),
    (32, "Source adapter para Gate 07J", "Investment Gate Preparation resuelve PROJECT_DEFINITION_READINESS, FEL_STAGE_READINESS y PDRI_OR_DEFINITION_ASSESSMENT mediante ProjectDefinitionService.", "Cambio acotado al adaptador _governed_payload; core Gate 07J intacto."),
    (33, "Evidence contract", "El contrato entrega source_module PROJECT_DEFINITION_FEL, status, stage, maturity, threshold, coverage, blockers, source freshness, hashes y referencias.", "can_supply_investment_gate_evidence sólo es true con readiness READY."),
    (34, "Immutability", "Listeners ORM impiden update/delete de evaluaciones COMPLETED incluso por rutas internas. Las reevaluaciones generan una revisión nueva.", "Prueba de inmutabilidad: PASS."),
    (35, "Concurrency", "revision_version e If-Match protegen assessments, actions, FEL status y configuraciones. Los conflictos responden 412 y no aplican last-write-wins silencioso.", "ETag presente en mutaciones controladas."),
    (36, "Idempotency", "Las operaciones start, complete, reevaluate, create action y transiciones de etapa aceptan claves idempotentes con unicidad tenant-scoped.", "Reintentos no duplican agregados."),
    (37, "Roles", "Se añadieron Project Definition Manager, Definition Assessor, Definition Reviewer, Project Definition Viewer y Project Definition Configuration Admin.", "Organization Administrator conserva acceso integral."),
    (38, "Permissions", "El catálogo cubre read, start/edit/complete assessment, manage actions, stage review/complete, refresh, evidence y configuración/publish.", "Workspace Navigator aplica project_definition.read."),
    (39, "Security events", "Los eventos registran configuración, assessment lifecycle, actions, refresh, stage transitions y resolución de evidencia con target IDs y hashes relevantes.", "Auditoría tenant-scoped y sin payload opaco."),
    (40, "API USER", "Las rutas exponen overview, start FEL, assessments, complete, reevaluate, actions, readiness, refresh preview, stage review/complete/return e Investment Gate evidence.", "Contratos Pydantic tipados y permisos por endpoint."),
    (41, "API ADMIN", "ADMIN lista configuraciones, previsualiza, clona DRAFT, actualiza con If-Match y publica revisiones gobernadas.", "Ninguna acción ADMIN crea Project, inversión o FID."),
    (42, "USER MODE", "La pantalla incluye My Projects, FEL Overview, Definition Assessments, Maturity Trend, Gaps & Actions, Evidence, Stage Readiness e History.", "Navegador real confirmó ocho vistas y límites visibles."),
    (43, "USER actions", "Start FEL, Start Assessment, Save/Complete, Reevaluation, Add/Resolve Action, Refresh Preview, Submit Review, Complete Stage y Resolve Evidence se habilitan según estado.", "Acciones deshabilitadas cuando el prerequisite no se cumple."),
    (44, "ADMIN MODE", "La pantalla presenta General, Frameworks, FEL Stages, Project Type Mapping, Assessment Categories, Assessment Elements, Scoring/Maturity, Thresholds, Blocking Elements, Evidence Requirements, Actions, Stage Review, Inheritance, Permissions y Preview.", "Navegador real confirmó quince áreas."),
    (45, "Navigation", "Project Definition / FEL Manager aparece bajo Enterprise Strategy Manager en USER MODE y como configuración homónima en ADMIN MODE.", "applicationNavigation.ts y workspace_context/navigator.py actualizados."),
    (46, "Persistence", "Alembic 20260826_0050 crea tres tablas aditivas con FKs tenant-scoped, checks de status, índices de lookup, unicidades e idempotencia.", "Migración reversible a 20260826_0049."),
    (47, "PostgreSQL schema validation", "PostgreSQL 16 confirmó tablas, columnas, constraints, hashes, lifecycle, inmutabilidad, evidencia e integración source adapter.", "Migration chain y schema validator: PASS."),
    (48, "Regression suite", "La pipeline efímera ejecutó regresión existente y Gates 07E-07J con FEL sobre PostgreSQL real.", "69/69 regression + 47/47 gates/FEL = 116/116 PASS."),
    (49, "Migration cycle", "El ciclo upgrade a 0050, downgrade a 0049 y upgrade nuevamente a 0050 finalizó sin pérdida de artefactos previos.", "0049 -> 0050 -> 0049 -> 0050: PASS."),
    (50, "Frontend validation", "Prettier, ESLint, TypeScript y build Vite de producción finalizaron correctamente. Vitest aprobó 206 casos en la suite completa; el único timeout de carga fue revalidado de forma aislada con todas sus aserciones y recibió un presupuesto CI de 300 segundos.", "0 errores ESLint; 206 suite + 1 isolated PASS; build production PASS."),
    (51, "Browser E2E release closeout", "Tres ejecuciones consecutivas recorrieron USER y ADMIN contra API y PostgreSQL reales: lifecycle FEL, evaluaciones, gaps, SoD, evidencia, clone/save/preview/publish, ETag, inmutabilidad e inheritance.", "3/3 PASS; 0 console errors; 0 page errors; 0 respuestas HTTP inesperadas."),
    (52, "Docker y localhost", "API, worker, beat y frontend permanecen activos. PostgreSQL y Redis están healthy; la base persistente está en 20260826_0050 head.", "App: http://localhost:5173/app; API ready: http://localhost:8000/api/v1/health/ready."),
    (53, "Riesgos y deuda técnica", "Para volúmenes altos se recomienda paginación o virtualización de histories y matrices. Frameworks PDRI/FEL comerciales deben ingresar sólo mediante contenido autorizado y versionado por tenant.", "Las 8 advertencias ESLint preexistentes del visor IFC permanecen dentro del umbral CI de 10; Gate 07J-FEL no tiene defectos abiertos."),
    (54, "Estado final exclusivo y STOP", "GATE07J_FEL_RELEASE_VALIDATED", "Gate 07J-FEL-H PASS. STOP: no implementar Funds/Funding, Investment Decision/FID, GO/HOLD/RECYCLE/KILL, Project Initialization, Activation, Execution, CPM o P6 sin autorización explícita posterior."),
]


CLOSEOUT_RUNS = [
    ("Run 1", "PASS", "USER + ADMIN", "1,0 min", "Fixture R1 aislado"),
    ("Run 2", "PASS", "USER + ADMIN", "1,1 min", "Fixture R2 aislado"),
    ("Run 3", "PASS", "USER + ADMIN", "1,0 min", "Fixture R3 aislado"),
]


CLOSEOUT_ACCEPTANCE = [
    ("USER-01", "Inicio FEL y evaluación", "PASS", "FEL-1 / DRAFT"),
    ("USER-02", "Guardar 95 y completar", "PASS", "Score 95; hash sellado"),
    ("USER-03", "Acción blocking y resolución", "PASS", "BLOCKED -> READY"),
    ("USER-04", "Segregation of duties", "PASS", "409 mismo actor; reviewer válido"),
    ("USER-05", "Historia, trend y reevaluation", "PASS", "v2 en FEL-2; completed inmutable"),
    ("USER-06", "Contrato Gate 07J", "PASS", "PROJECT_DEFINITION_FEL; hashes vigentes"),
    ("NEG-01", "ETag, source stale y evidence faltante", "PASS", "412 / 409 controlados"),
    ("NEG-02", "Stage skip y modelos opcionales", "PASS", "Bypass y aplicabilidad bloqueados"),
    ("ADMIN-01", "Clone DRAFT y edición", "PASS", "Threshold, blocker y evidencia"),
    ("ADMIN-02", "Preview sin efectos", "PASS", "persisted=false; historia intacta"),
    ("ADMIN-03", "Save, stale ETag y publish", "PASS", "v2; 412; rev 2 publicada"),
    ("ADMIN-04", "Inmutabilidad e inheritance", "PASS", "Published protegida; hash efectivo"),
    ("SAFE-01", "Controles fuera de alcance", "PASS", "Sin FID, Funds, activación, CPM o P6"),
    ("SAFE-02", "Consola, página y red", "PASS", "0 errores / 0 respuestas inesperadas"),
]


REMEDIATIONS = [
    ("UI-01", "Edición sobrescrita por recarga tardía", "La matriz sólo se expone después de cargar el draft canónico."),
    ("UI-02", "Complete podía congelar valores previos", "Complete persiste siempre la matriz antes de sellar."),
    ("UI-03", "Selección ADMIN podía revertir por carrera", "La selección explícita se conserva mediante referencia estable."),
    ("API-01", "Metadata required_evidence inválida producía 500", "Preview reporta blocker controlado y save valida la forma."),
    ("E2E-01", "Sincronización y selectors no determinísticos", "Las esperas dependen de estado visible, respuesta y versión."),
    ("TEST-01", "Teardown con orden FK inseguro", "Actions, FEL status y assessments se eliminan antes de configuración."),
]


BASELINE_FACTS = [
    ("Admin configurations", "77", "77", "MATCH"),
    ("Enterprise workspaces", "14", "14", "MATCH"),
    ("User accounts", "9", "9", "MATCH"),
    ("FEL statuses / assessments / actions", "0 / 0 / 0", "0 / 0 / 0", "MATCH"),
    ("Project workspaces", "1", "1", "MATCH"),
    ("Project 14 defaults MD5", "eea3648c6908a267d1e0651828ff4459", "eea3648c6908a267d1e0651828ff4459", "MATCH"),
    ("Alembic head", "20260826_0050", "20260826_0050", "MATCH"),
]
