# Borrador de evidencia para el informe técnico

> **Estado: reemplazado.** Este documento conserva una fotografía intermedia y contiene conclusiones pendientes ya superadas. La fuente de cierre es `docs/validation/strategic-hardening/release-validation.md`; no debe usarse este borrador para decidir el release ni para emitir señales.

## Hardening del macroproceso estratégico — separación ADMIN/USER y optimización de código

- Fecha de corte del borrador: 2026-09-14.
- Especificación evaluada: `PROMPT_STRATEGIC_MACROPROCESS_HARDENING_ADMIN_USER_CODE_OPTIMIZATION.md`.
- Repositorio: `pypmis-ia-sas`.
- Línea base solicitada: commit `9cb0969`.
- Rama y commit observados al corte: `main`, `HEAD = origin/main = 9cb0969`.
- Alembic head observado: `20260910_0059`.

Este documento es un insumo factual para el informe Word final. Usa `CONFIRMADO` únicamente cuando existe evidencia durable en código, matrices o artefactos bajo `outputs/.qa/strategic-hardening`. Un elemento marcado `PENDIENTE` no debe presentarse como aprobado en el informe final hasta que se adjunte su evidencia de ejecución.

## Estado ejecutivo de la evidencia

La separación declarativa ADMIN/USER está implementada en el frontend: existe una clasificación cerrada para cada nodo estratégico, una fuente canónica de navegación y rutas, un outlet central de vistas y una guarda para rutas ADMIN. La matriz auditable contiene 128 rutas/controles, todos en el modo esperado: 100 USER y 28 ADMIN; por clasificación son 92 `USER_TRANSACTION`, 27 `ADMIN_CONFIGURATION` y 9 `READ_ONLY_SHARED`; no hay divergencias entre modo actual y modo correcto.

El hardening de Business Analysis está implementado en frontend y backend: paginación por cursor, editor ADMIN estructurado, JSON crudo de solo lectura, validación de escala/criterios en backend y seed concurrente mediante upsert. Los cinco tests backend específicos aparecen aprobados en el JUnit actual. La validación PostgreSQL limpia registra 6/6 pruebas aprobadas, incluidas migración BA up/down/up y restricciones BA, Risk y Permit.

El diferencial global backend es favorable respecto a nuevas regresiones, pero no es una suite global verde. La línea base ejecutó 609 casos: 572 aprobados, 27 omitidos y 10 fallidos. El estado actual ejecutó 626 casos: 585 aprobados, 33 omitidos y 8 fallidos. No aparecieron fallas nuevas; permanecen ocho fallas heredadas. Las dos pruebas PostgreSQL de Risk/Permit que fallaban por ejecutarse con SQLite ahora se omiten correctamente en esa suite y pasan en la corrida PostgreSQL dedicada.

Al corte de este borrador permanecen pendientes la evidencia durable del gate frontend completo, los reportes E2E USER y ADMIN identificados por prueba, la medición de rendimiento posterior y la comparación de bundle antes/después. Por ello todavía no corresponde emitir las dos señales finales del hardening. El estado conservador de Gate07A-BA es `GATE07A_BA_RELEASE_PENDING_BASELINE_REGRESSION` hasta completar también los gates frontend/browser exigidos y resolver la política sobre las ocho fallas heredadas.

## 1. Resumen ejecutivo — `PARCIAL, CIERRE PENDIENTE`

Resultado implementado:

- clasificación exhaustiva de responsabilidad estratégica;
- separación de navegación USER y ADMIN derivada desde un único blueprint;
- protección de deep links ADMIN mediante `can_configure`;
- retiro de listas estratégicas duplicadas en `applicationNavigation.ts`;
- traslado del renderizado estratégico repetitivo desde `App.tsx` a `StrategicViewOutlet.tsx`;
- hardening BA de paginación, configuración estructurada, validación y concurrencia;
- aislamiento de temporales pytest dentro del repositorio;
- preservación explícita de modelos de gobierno alternativos, rutas alternativas y lecturas históricas;
- cero fallas backend nuevas frente al baseline comparable.

Condiciones de cierre aún no demostradas con artefactos durables:

- gate frontend completo;
- E2E browser USER y ADMIN con resultado por prueba;
- `performance-after.json` y comparación de bundle equivalente;
- resolución/aceptación formal de las ocho fallas globales heredadas.

## 2. Línea base real del repositorio — `CONFIRMADO`

La inspección al corte muestra:

| Dato | Valor observado | Evidencia |
|---|---:|---|
| Rama | `main` | `git status --branch` |
| HEAD/local remoto | `9cb0969` / `origin/main` | `git log -n 10` |
| Alembic head | `20260910_0059` | `backend/.venv/Scripts/python.exe -m alembic heads` |
| Entradas dirty visibles | 70 | `git status --porcelain=v1` al corte |
| Modificadas | 33 | mismo estado |
| Eliminadas | 12 | mismo estado; son artefactos temporales versionados |
| No rastreadas | 25 | mismo estado; incluye implementaciones y evidencia de prompts previos |
| Baseline extraído | `outputs/.qa/strategic-hardening/baseline-9cb0969/` | árbol local no destructivo |
| Archivo del baseline | `outputs/.qa/strategic-hardening/baseline-9cb0969.zip` | archivo local de comparación |

El repositorio real no era un checkout limpio del informe anterior. El hardening se desarrolló sobre cambios locales existentes y no debe describirse como un diff aislado exclusivamente de esta especificación.

## 3. Protección del working tree — `CONFIRMADO`

Se mantuvo el working tree dirty y se construyó una copia separada del commit `9cb0969` bajo `outputs/.qa/strategic-hardening/baseline-9cb0969`. No existe evidencia de `git reset --hard` ni de descarte masivo del trabajo del usuario. Los cambios no relacionados se conservaron.

Las doce eliminaciones visibles corresponden a artefactos pytest previamente versionados dentro de `.tmp/` y `backend/.tmp/`; no corresponden a código de dominio. Su limpieza definitiva debe hacerse de forma revisada porque varios presentan ACL de Windows con acceso denegado.

## 4. ADR de responsabilidades ADMIN/USER — `CONFIRMADO`

`docs/64-adr-strategic-admin-user-code-hardening.md` documenta:

- vocabulario cerrado `USER_TRANSACTION`, `ADMIN_CONFIGURATION`, `READ_ONLY_SHARED`;
- regla de acceso `authenticated` para USER/lecturas compartidas y `can_configure` para configuración ADMIN;
- navegación estratégica canónica en `strategicNavigationBlueprint.ts`;
- composición en `StrategicViewOutlet.tsx`;
- compatibilidad histórica y por modelo de gobierno;
- contratos HTTP y permisos separados;
- reglas de limpieza segura y decisión de no reescribir migración `0059`.

El ADR conserva el estado “validación integral pendiente”. Esa calificación sigue siendo coherente con los gates frontend/browser/performance pendientes, aunque su sección de diferencial backend debe actualizarse porque ya existe `current-pytest.xml`.

## 5. Inventario de módulos estratégicos — `CONFIRMADO`

La matriz cubre las fases 0–7:

| Fase | Capacidades inventariadas | Controles/rutas |
|---:|---|---:|
| 0 | Enterprise Foundation: estado, explorer, contexto, estructura, tipos, composición, objetivos, herencia, catálogo y perfiles | 11 |
| 1 | Idea & Demand, Business Analysis y sus configuraciones | 4 |
| 2 | Project Proposal y configuración | 2 |
| 3 | Strategic Gate y configuración | 2 |
| 4 | Portfolio Planning, Analysis, Investor Map, Scorecard y configuraciones | 11 |
| 5 | Budget, Resources, Convergence/Recommendation y configuraciones | 7 |
| 6 | FEL, Business Case, Funding, FIN, Risk, Permit y configuraciones | 70 |
| 7 | Evidence Policy, Gate07J, Gate07K/FID, Gate07L y configuraciones | 21 |
| **Total** | **Macroproceso estratégico completo** | **128** |

El inventario backend curado para estos dominios contiene 21 directorios de módulo, 132 archivos Python y 59.468 líneas al corte. Los dos paquetes frontend centrales del incremento contienen 8 archivos/2.016 líneas (`enterprise-strategy`) y 6 archivos/2.378 líneas (`business-analysis`).

## 6. Matriz USER/ADMIN/READ_ONLY_SHARED — `CONFIRMADO`

Evidencia primaria: `docs/validation/strategic-hardening/admin-user-control-matrix.csv`.

| Dimensión | Resultado |
|---|---:|
| Filas totales | 128 |
| Rutas únicas | 128 |
| Modo USER | 100 |
| Modo ADMIN | 28 |
| `USER_TRANSACTION` | 92 |
| `ADMIN_CONFIGURATION` | 27 |
| `READ_ONLY_SHARED` | 9 |
| Estado `IMPLEMENTED` | 128 |
| Divergencias Current Mode vs Correct Mode | 0 |

La matriz usa las trece columnas exigidas por la especificación: fase, módulo, ruta, superficie, acción, clasificación, modo actual, modo correcto, permiso, endpoint, estado, acción tomada y evidencia.

## 7. Hallazgos de contaminación — `CONFIRMADO EN CÓDIGO; BROWSER PENDIENTE`

Hallazgos comprobables en la línea base/código anterior:

- `applicationNavigation.ts` contenía definiciones estratégicas USER y ADMIN literales además de la nueva arquitectura, creando dos fuentes de orden, etiquetas y rutas.
- `App.tsx` concentraba imports y un bloque condicional de renderizado para numerosas vistas estratégicas.
- el acceso a modo ADMIN necesitaba una guarda explícita y homogénea para la navegación directa;
- Business Analysis ADMIN dependía de edición de JSON crudo en vez de controles gobernados;
- el listado BA no tenía un contrato frontend de páginas sucesivas acotadas;
- pytest heredaba temporales externos afectados por ACL de Windows.

No hay evidencia browser durable que demuestre una búsqueda exhaustiva de cada botón, icono, modal y menú de las 128 superficies. Por ello la contaminación visual completa sigue pendiente de cierre E2E.

## 8. Correcciones de contaminación — `IMPLEMENTADO; VALIDACIÓN BROWSER PENDIENTE`

- `applicationNavigation.ts` deriva USER y ADMIN mediante `buildStrategicMacroprocess("user" | "admin")`.
- `StrategicViewOutlet.tsx` resuelve la vista y ejecuta `canAccessStrategicNode` antes de renderizar.
- `App.tsx` bloquea el cambio USER→ADMIN cuando `canConfigure` es falso.
- USER conserva transacciones; ADMIN conserva configuración; lectura compartida se declara de forma explícita.
- el editor ADMIN BA expone campos estructurados y deja el JSON crudo en un `<pre>` de solo lectura.
- el E2E `strategic-workflow-navigation.spec.ts` incluye pruebas declaradas de contaminación cruzada y de ruta ADMIN directa sin `can_configure`.

## 9. Autorización por ruta directa — `PARCIALMENTE CONFIRMADO`

Implementación:

- `strategicRouteMatch` resuelve `/app/strategy/{view}` y `/app/admin/strategy/{view}`;
- `canAccessStrategicNode` exige `can_configure` cuando el permiso del nodo es ADMIN;
- `StrategicViewOutlet` devuelve una vista de acceso restringido antes de montar el componente protegido;
- `ApplicationModeToggle` queda deshabilitado y su handler retorna sin cambiar a ADMIN cuando falta `can_configure`.

Pruebas disponibles:

- `StrategicViewOutlet.test.tsx` declara un caso de denegación y uno autorizado;
- `strategicNavigationBlueprint.test.ts` declara la invariancia de ruta ADMIN;
- `test_gate07a_ba_user_role_cannot_access_admin_configuration` pasó en el JUnit backend actual;
- `test_gate07a_ba_config_admin_cannot_execute_user_transactions` pasó en el JUnit backend actual.

Pendiente: resultado durable del gate frontend y E2E por nombre de prueba.

## 10. Separación de permisos API — `PARCIALMENTE CONFIRMADO`

`api-compatibility-matrix.csv` inventaría 24 familias: 21 `IMPLEMENTED` y 3 `PRESERVED`. Distingue permisos transaccionales (`*.read`, `*.create`, `*.edit`, transiciones) de permisos de configuración (`*.admin.configure`, `*.admin.publish`). No registra eliminación de endpoint.

La separación BA está demostrada por dos casos backend aprobados: un rol USER no accede a configuración ADMIN y un actor solo configurador no ejecuta transacciones USER. Para las otras 23 familias la evidencia disponible es inspección de router/permissions y pruebas de dominio existentes; no existe un reporte único que ejecute la matriz completa de combinaciones rol×endpoint. El informe final debe evitar afirmar una prueba exhaustiva que no fue registrada.

## 11. Auditoría Foundation Status — `IMPLEMENTADO; E2E PENDIENTE`

La fase 0 contiene cuatro lecturas compartidas y siete configuraciones ADMIN. USER recibe:

- estado de Foundation;
- Enterprise Explorer;
- Workspace Context;
- consulta de estructura publicada.

ADMIN recibe estructura/workspaces, tipos, composición, objetivos, herencia, activación y perfiles. El blueprint y la matriz no ubican mutaciones de Foundation en USER. La validación visual exhaustiva queda pendiente de E2E.

## 12. Auditoría Strategic Objectives — `IMPLEMENTADO; E2E PENDIENTE`

El nodo `foundation-strategic-objectives` se resuelve desde ADMIN a `AdminEnterpriseStructurePage` con la pestaña de catálogos. USER puede consumir objetivos publicados a través de sus flujos de idea/selección, pero no existe nodo USER para editar el catálogo. La matriz clasifica la administración como `ADMIN_CONFIGURATION`.

## 13. Auditoría Business Analysis — `CONFIRMADO EN BACKEND; FRONTEND FINAL PENDIENTE`

Se preserva la cadena IDEA ACCEPTED → BUSINESS ANALYSIS → READY_FOR_PROJECT_PROPOSAL → PROJECT PROPOSAL y el contenido gobernado solicitado. Evidencia:

- 5 archivos backend BA, 1.992 líneas;
- 6 archivos frontend BA, 2.378 líneas;
- contrato USER y ADMIN separado en rutas y permisos;
- historial ADMIN de configuración separado del historial transaccional;
- `COMPLETED` y snapshots inmutables en pruebas;
- grandfathering y política por modelo de gobierno en prueba parametrizada;
- lineage hacia Project Proposal en modelo, migración y pruebas;
- cinco pruebas de hardening BA aprobadas dentro del JUnit global actual;
- pruebas PostgreSQL/migración BA incluidas en el gate dedicado 6/6.

Pendiente: gate frontend completo y E2E BA identificado por caso.

## 14. Auditoría de módulos Portfolio — `IMPLEMENTADO EN MATRIZ; REGRESIÓN GLOBAL SIN FALLAS NUEVAS`

Portfolio Intake/Planning, Evaluation/Prioritization, Analysis, Investor Map, Scorecard, Budget, Resources y Convergence/Recommendation están representados en las fases 4 y 5. Budget y Resources permanecen en paralelo antes de Convergence. Las familias API conservan sus contratos y no se retiró endpoint.

Las pruebas Portfolio presentes en `current-pytest.xml`, incluidas inmutabilidad de snapshots, reevaluación/versionado, escenarios y exclusión de modelos no owner, no aparecen entre las ocho fallas. No existe aún un reporte browser específico de toda la fase.

## 15. Auditoría FEL/BC/Funding/FIN/Risk/Permit — `PARCIALMENTE CONFIRMADO`

Los seis proveedores/contribuyentes están preservados en fase 6 y convergen hacia Gate07J. Resultados durables relevantes:

- Business Case: historia longitudinal y snapshot append-only pasan;
- FIN: ciclo comercial, readiness, provider e inmutabilidad pasan;
- Gate07J: segregación de funciones e inmutabilidad de revisión congelada pasan;
- Risk/Permit: restricciones/índices PostgreSQL pasan en gate dedicado;
- Funding, FEL, Risk y Permit no aparecen entre los ocho fallos globales actuales.

La suite global todavía falla en siete pruebas Gate07K durante la preparación de evidencia FEL manual, por `MANUAL_REFERENCE_NOT_ALLOWED`. Estas fallas ya existían en el baseline y no son nuevas, pero impiden declarar verde el recorrido completo hasta decisión.

## 16. Auditoría Gate07J/Gate07K/Gate07L — `PARCIAL`

- Gate07J permanece como preparación/evidencia, sin autoridad FID; Evidence Policy es mutación ADMIN y lectura efectiva USER.
- Gate07K permanece como decisión transaccional USER; reglas, autoridad, SoD y quorum son ADMIN.
- Gate07L conserva evaluación/refresh post-FID sin activar proyectos automáticamente.
- `test_valid_fid_persists_immutable_per_project_snapshots_idempotently` y `test_contractor_and_direct_governance_models_remain_unaffected` pasan.
- siete casos Gate07K permanecen fallidos por el mismo fixture/contrato heredado de evidencia manual observado en baseline.

Conclusión: arquitectura separada implementada; happy path global Gate07J→Gate07K no está limpio y no debe reportarse como aprobado.

## 17. Inventario de código — `CONFIRMADO`

Piezas principales del hardening:

- `frontend/src/features/enterprise-strategy/navigation/strategicControlClassification.ts`;
- `frontend/src/features/enterprise-strategy/navigation/strategicNavigationBlueprint.ts`;
- `frontend/src/features/enterprise-strategy/StrategicViewOutlet.tsx`;
- `frontend/src/navigation/applicationNavigation.ts`;
- `frontend/src/App.tsx`;
- paquete `frontend/src/features/business-analysis/`;
- paquete `backend/app/modules/business_analysis/`;
- migración `20260910_0059_gate07a_ba_business_analysis.py`;
- `backend/conftest.py` y `backend/tests/conftest.py`;
- pruebas frontend, E2E, SQLite y PostgreSQL relacionadas;
- ADR y cuatro matrices de validación.

Hotspots observados: `App.tsx` tiene 8.166 líneas, el blueprint 902, `BusinessAnalysisService` 1.507 y `StrategicViewOutlet` 289 con 48 imports. La extracción del render estratégico reduce responsabilidad de `App.tsx`, pero no elimina su deuda general ni convierte el outlet en un componente desacoplado.

## 18. Matriz de código muerto — `PENDIENTE DE NORMALIZACIÓN`

No se identificó un archivo o símbolo de dominio probado como `DEAD_CODE` y retirado durante este incremento. Se retiró duplicación demostrada, no capacidad funcional. Los artefactos pytest inaccesibles no son código de aplicación.

La matriz actual `code-cleanup-matrix.csv` no cumple todavía el esquema obligatorio de §38: usa `Area, Artifact, Finding, Decision, Status, Risk, Validation/Evidence` en lugar de `File/Symbol/Route, Layer, Current Classification, Evidence of Use, Governance Model Use, Historical Use, Action, Reason, Tests Covering Change`. Debe normalizarse antes del cierre.

## 19. Matriz de flujos deprecados — `PARCIAL`

Flujos retirados/consolidados:

- listas estratégicas USER literales supersedidas por `buildStrategicMacroprocess("user")`;
- lista estratégica ADMIN literal supersedida por `buildStrategicMacroprocess("admin")`;
- resolución de deep links estratégicos dispersa, reemplazada por el registro canónico.

No se eliminó endpoint ni se creó redirect/alias nuevo. Las rutas de Workspace/comerciales y la administración de plataforma se preservan explícitamente. Falta reflejar cada candidato con la clasificación obligatoria y evidencia de uso/historia/modelo en la matriz normalizada.

## 20. Matriz de flujos duplicados — `IMPLEMENTADO, DOCUMENTACIÓN A COMPLETAR`

Duplicaciones corregidas:

- dos registries de navegación estratégica literales (USER y ADMIN) → un builder canónico;
- cadena de render estratégico en `App.tsx` → `StrategicViewOutlet`;
- mapas de ruta y breadcrumbs → funciones del blueprint;
- lógica de acceso de nodos → `canAccessStrategicNode`;
- carga BA con respuesta/header → `apiFetchWithResponse` + `listPage`.

No se consolidaron a ciegas resolutores backend de readiness/configuración: no se demostró equivalencia semántica suficiente para retirar implementaciones históricas. Esto es coherente con la regla “proof before delete”.

## 21. Protección de rutas alternativas — `CONFIRMADO EN CÓDIGO`

Se conservan:

- `PROJECT_WORKSPACE_GOVERNANCE_MODULES` para workspaces/partners/vendors/commitments;
- `NON_STRATEGIC_USER_MODE_NAVIGATION_BLUEPRINT` para macroprocesos no estratégicos ya existentes;
- `PLATFORM_ADMINISTRATION_MODULES` para Organization & Security, configuración general y procesos;
- fallback `/app` y ruta específica `/app/schedule-control` fuera del alcance estratégico;
- aplicabilidad diferenciada para `CAPITAL_OWNER`, `CONTRACTOR_DELIVERY`, `DIRECT_INTERNAL` y `LEGACY_UNCLASSIFIED`.

No se fuerza el flujo owner-only a modelos alternativos.

## 22. Compatibilidad histórica — `PARCIALMENTE CONFIRMADO`

Casos aprobados en `current-pytest.xml`:

- BA snapshots/inmutabilidad;
- política BA snapshot y legacy-safe para cuatro modelos;
- Business Case snapshot e historia longitudinal;
- FIN provider/readiness/inmutabilidad;
- Gate07J revisión congelada inmutable;
- Post-FID snapshots inmutables e idempotentes;
- modelos Contractor/Direct sin afectación Post-FID.

La fixture 07B preserva explícitamente snapshots pre-BA para propuestas grandfathered, y sus pruebas no están entre los fallos actuales. Sin embargo, siete pruebas Gate07K siguen fallando antes de producir la decisión por el contrato heredado de referencia manual. La compatibilidad histórica global se considera parcial, no verde.

## 23. Matriz de compatibilidad de rutas — `PARCIALMENTE CONFORME`

`route-compatibility-matrix.csv` contiene 27 familias: 25 `IMPLEMENTED` y 2 `PRESERVED`. Cubre USER, ADMIN, rutas desconocidas seguras, fallback, deep links, trailing slash y modelos alternativos.

Gap documental: la especificación exige clasificar cada ruta cambiada como `KEEP`, `REDIRECT`, `ALIAS` o `REMOVE`. La matriz actual usa una decisión narrativa y `Status`, pero no una columna con ese vocabulario cerrado. Debe normalizarse antes de declarar completo el entregable.

## 24. Matriz de compatibilidad API — `CONFIRMADO COMO INVENTARIO; RUNTIME EXHAUSTIVO PENDIENTE`

`api-compatibility-matrix.csv` contiene 24 familias, 21 `IMPLEMENTED` y 3 `PRESERVED`. No registra eliminación de endpoint. Distingue contratos USER y ADMIN, permisos y decisión de compatibilidad para Foundation, Idea, BA, Proposal, Gate, Portfolio, fase 6 y fase 7.

El gate PostgreSQL y los tests BA demuestran contratos clave, pero no existe una ejecución matricial de cada método/rol de las 24 familias. La compatibilidad se respalda por inspección más regresión existente, no por un único contract-test exhaustivo.

## 25. Archivos y símbolos retirados — `CONFIRMADO CON ALCANCE LIMITADO`

- no se retiró archivo de dominio estratégico;
- no se retiró endpoint backend;
- se retiraron bloques literales duplicados de navegación estratégica en `applicationNavigation.ts`;
- se retiró la cadena repetitiva de composición estratégica de `App.tsx` y sus imports directos asociados;
- aparecen doce artefactos pytest versionados como eliminados, pendientes de limpieza ACL revisada.

No se debe atribuir al hardening la eliminación de otros archivos porque el working tree contiene cambios acumulados de prompts anteriores.

## 26. Archivos y símbolos refactorizados — `CONFIRMADO`

Refactor principal:

- `App.tsx`: delegación de vistas estratégicas y guarda de cambio de modo;
- `applicationNavigation.ts`: composición desde blueprint y preservación explícita no estratégica;
- `strategicNavigationBlueprint.ts`: fases, orden, rutas, breadcrumbs, clasificación, permiso y aplicabilidad;
- `StrategicViewOutlet.tsx`: mapping componente/vista y guarda central;
- `api/client.ts`: lectura de headers sin romper el helper existente;
- `BusinessAnalysisWorkspace.tsx`: paginación y append sin duplicados;
- `BusinessAnalysisAdminView.tsx`: formulario gobernado estructurado;
- BA router/service/schemas: cursor, validación y seed;
- conftests y tests PostgreSQL: aislamiento de entorno/dialecto.

## 27. Limpieza de navegación — `CONFIRMADO EN CÓDIGO`

`strategicNavigationBlueprint.ts` es la fuente estratégica única. USER y ADMIN se derivan de ella; rutas y breadcrumbs son deterministas; la navegación anidada usa `NavigationViewBranch`. Las rutas desconocidas no se coercionan a otra transacción.

El commit limpio `9cb0969` no contiene el blueprint en la ruta actual; este llegó como cambio no rastreado/acumulado del Frontend V2. La comparación debe interpretarse como consolidación del working tree real, no como una modificación exclusiva ya versionada.

## 28. Limpieza backend — `PARCIAL, CONSERVADORA`

Se registró el router BA en `backend/app/api/v1/router.py`, se reforzó validación y paginación, y se corrigió aislamiento pytest. No se retiraron servicios, schemas, routers ni read models históricos sin prueba de desuso. Tampoco se construyó microservicio, BPM engine ni motor genérico de gates; se conserva el monolito modular.

La revisión no produjo evidencia suficiente para consolidar resolutores transversales de readiness, provider o inheritance sin riesgo semántico. Por tanto se preservaron, lo cual debe documentarse como decisión deliberada y no como cleanup omitido accidentalmente.

## 29. Paginación/índice de cola BA — `IMPLEMENTADO / SIN NUEVO ÍNDICE`

Implementación:

- página por defecto 50, máximo 100;
- cursor opaco con orden estable `updated_at DESC, id DESC`;
- consulta `limit + 1` para detectar continuación;
- headers `X-Page-Limit`, `X-Page-Count`, `X-Next-Cursor`;
- frontend solicita 50 y agrega páginas sin duplicar registros;
- prueba `test_gate07a_ba_cursor_pagination_is_bounded_stable_and_rejects_invalid_ratings` aprobada.

Decisión de base de datos: no se agregó migración sucesora ni índice nuevo porque no existe un plan de ejecución/EXPLAIN durable que demuestre necesidad. La migración `0059` ya contiene índices de claves y `(tenant_id, source_idea_id)`, pero no un índice específico `(updated_at, id)`. La decisión debe reabrirse si la medición con volumen real demuestra degradación.

## 30. Hardening del editor ADMIN BA — `IMPLEMENTADO; FRONTEND GATE PENDIENTE`

`BusinessAnalysisAdminView.tsx` usa secciones y controles estructurados para modelos de gobierno, reglas de opciones, escala/valores permitidos, criterios/pesos, campos obligatorios y readiness. El JSON se presenta como evidencia avanzada de solo lectura mediante `<pre>`; no es el editor principal y no se expone en USER.

Existen pruebas unitarias/E2E declaradas para la edición estructurada, pero el resultado durable del gate frontend completo aún no estaba disponible al corte.

## 31. Validación de ratings BA — `CONFIRMADO`

Backend valida:

- valores finitos;
- mínimo/máximo publicados;
- `allowed_values`;
- criterios requeridos;
- pesos finitos, no negativos y suma 100;
- configuración de escala válida.

Los tests de cursor/ratings y configuración ADMIN inválida pasaron en la suite actual. La autoridad permanece en backend; frontend solo refleja la configuración.

## 32. Concurrencia del seed — `CONFIRMADO EN SQLITE; POSTGRESQL BA VERDE`

`ensure_business_analysis_seed_records` usa upsert específico por dialecto con `on_conflict_do_nothing`. La prueba lanza ocho sesiones concurrentes y pasó en el JUnit actual. El gate PostgreSQL BA también pasó, aunque el XML dedicado no identifica un caso separado de ocho procesos en PostgreSQL; por ello la afirmación estricta es determinismo concurrente probado en la suite actual y compatibilidad BA general probada en PostgreSQL.

## 33. Diferencial backend baseline/current — `CONFIRMADO, GLOBAL ROJO HEREDADO`

| Ejecución | Total | Aprobados | Omitidos | Fallidos | Duración |
|---|---:|---:|---:|---:|---:|
| Baseline `9cb0969` | 609 | 572 | 27 | 10 | 2517,723 s |
| Working tree actual | 626 | 585 | 33 | 8 | 2510,651 s |

Diferencial:

- nuevas fallas: 0;
- fallas heredadas sin cambio: 8;
- pruebas Risk/Permit que fallaban por dialecto SQLite: ahora omitidas en SQLite y aprobadas en PostgreSQL dedicado;
- errores JUnit: 0 en ambas corridas;
- casos adicionales actuales: 17.

Las ocho fallas actuales son una de Enterprise Structure (`valid = false`) y siete de Gate07K por `MANUAL_REFERENCE_NOT_ALLOWED`. Todas ya aparecen en el baseline. El criterio primario “0 nuevas fallas atribuibles al hardening” se cumple; el criterio de repositorio global limpio no.

Evidencia: `baseline-pytest.xml`, `current-pytest.xml`, sus logs y `postgres-gates-clean.xml`.

## 34. Corrección del entorno temp/pytest — `CONFIRMADO`

- `.gitignore` excluye temporales pytest locales;
- `backend/conftest.py` fuerza un `basetemp` por proceso dentro del repositorio;
- `backend/tests/conftest.py` configura SQLite y documentos por corrida bajo temporales controlados;
- se configuran `TMP`, `TEMP`, `TMPDIR` y `tempfile.tempdir` con rutas locales;
- las pruebas PostgreSQL Risk/Permit se omiten limpiamente cuando el dialecto es SQLite.

No hay coincidencias `PermissionError`, `Access is denied` ni `WinError 5` en los logs completos baseline/current controlados. Persisten artefactos antiguos con ACL inválida en el working tree, pero no contaminaron la corrida comparable actual.

## 35. Métricas de código antes/después — `PROVISIONAL Y REPRODUCIBLE`

Método del corte: conteo de archivos `.ts/.tsx/.css` bajo `frontend/src`; para “frontend estratégico” filtro de rutas que contienen `enterprise-strategy`, `business-analysis`, `portfolio`, `idea-demand` o `project-proposal`; backend bajo `backend/app`; backend estratégico como 21 módulos explícitos del inventario.

| Métrica | Baseline `9cb0969` | Actual | Delta |
|---|---:|---:|---:|
| Archivos frontend | 204 | 219 | +15 |
| LOC frontend | 73.302 | 77.647 | +4.345 |
| Archivos frontend estratégicos | 50 | 64 | +14 |
| LOC frontend estratégico | 13.588 | 18.022 | +4.434 |
| Archivos `backend/app` | 204 | 209 | +5 |
| LOC `backend/app` | 95.962 | 98.325 | +2.363 |
| Archivos backend estratégicos curados | 127 | 132 | +5 |
| LOC backend estratégico curado | 57.117 | 59.468 | +2.351 |
| `App.tsx` LOC | 8.234 | 8.166 | -68 |
| `applicationNavigation.ts` LOC | 740 | 614 | -126 |
| `strategicNavigationBlueprint.ts` LOC | no presente en commit limpio | 902 | +902 |
| `StrategicViewOutlet.tsx` LOC | no presente | 289 | +289 |

Interpretación: aumentó el código total por BA y la arquitectura Frontend V2; disminuyeron los dos archivos de orquestación/listado heredado. El objetivo alcanzado es separación de responsabilidades, no minimización artificial de LOC.

Métricas aún no cerradas: conteo OpenAPI real antes/después, errores/warnings finales de TypeScript/ESLint/Ruff, CSS no usado, símbolos backend muertos y componentes muertos eliminados. No existe evidencia de que se haya retirado CSS o símbolos backend muertos.

## 36. Comparación bundle/rendimiento — `PENDIENTE`

`performance-before.json` registra a 1440×900:

| Medición | Antes |
|---|---:|
| Navegación estratégica | 195,4 ms |
| Landing Enterprise Strategy | 1099,3 ms |
| Primera página BA | 11688,4 ms |
| Vista de evidencia Gate07J | 12724,1 ms |
| Fallas de medición | 0 |

El `frontend/dist/assets` actual contiene 10 archivos por 7.310.542 bytes, pero no existe un artefacto de bundle baseline equivalente dentro de la copia limpia. Tampoco existe `performance-after.json` al corte. No se puede concluir todavía “sin regresión de performance/bundle”.

## 37. Reporte de pruebas backend — `CONFIRMADO CON FALLAS HEREDADAS`

Resultados durables:

- suite global actual: 585 passed, 33 skipped, 8 failed, 0 errors, 626 total;
- suite global baseline: 572 passed, 27 skipped, 10 failed, 0 errors, 609 total;
- PostgreSQL limpio: 6 passed, 0 failed/skipped;
- BA hardening dentro de suite actual: cursor/ratings, configuración inválida, permisos cruzados y seed concurrente aprobados;
- no hay errores de permisos de temporales.

La suite global sigue roja por ocho fallas heredadas. No debe resumirse como “backend todo verde”.

## 38. Reporte de pruebas frontend — `PENDIENTE DE ARTEFACTO FINAL`

Existen 16 casos focales declarados en:

- 8 del blueprint estratégico;
- 2 de `StrategicViewOutlet`;
- 2 de `applicationNavigation`;
- 4 de `BusinessAnalysisWorkspace`.

También existen cambios de TypeScript, ESLint y Prettier preparados. Al corte no hay log/JUnit durable del gate frontend completo en `outputs/.qa/strategic-hardening`; la ejecución estaba en curso. No declarar aprobado hasta adjuntar el resultado.

## 39. Reporte browser USER — `PENDIENTE DE TRAZA IDENTIFICADA`

`strategic-workflow-navigation.spec.ts` declara:

- workflow estratégico USER/ADMIN;
- orden en tablet/mobile;
- ausencia de controles de responsabilidad opuesta;
- denegación de ruta ADMIN sin `can_configure`.

`business-analysis-governance.spec.ts` declara navegación separada y ciclo USER BA. `frontend/test-results/.last-run.json` tiene estado agregado `passed` con fecha 2026-09-11 13:26, pero no identifica las pruebas ejecutadas ni incluye trace/reporte. Por rigor, el informe USER permanece pendiente de una ejecución con reporter durable.

## 40. Reporte browser ADMIN — `PENDIENTE DE TRAZA IDENTIFICADA`

El E2E BA declara clone/edit/preview/publish de configuración mediante controles estructurados y el E2E estratégico declara auditoría de contaminación. La fuente demuestra intención de cobertura, no resultado. El estado agregado de Playwright no permite atribuir aprobación al escenario ADMIN; se requiere reporte por caso.

## 41. Regresión por Governance Model — `BACKEND CONFIRMADO; FRONTEND PENDIENTE`

En `current-pytest.xml` pasan los cuatro casos BA:

- `CAPITAL_OWNER` → BA requerida;
- `CONTRACTOR_DELIVERY` → BA no requerida por defecto;
- `DIRECT_INTERNAL` → BA no requerida por defecto;
- `LEGACY_UNCLASSIFIED` → BA no requerida/grandfathered.

También pasan Post-FID Contractor/Direct y opciones de creación para tres modelos. El blueprint declara test de aplicabilidad owner-only, pero su ejecución final debe quedar demostrada por el gate frontend.

## 42. Regresión histórica — `PARCIAL`

Confirmado por casos aprobados:

- BA `COMPLETED`/snapshot inmutable;
- política BA legacy-safe y Proposal grandfathering;
- Business Case snapshots/historia;
- FIN versión/ciclo inmutable;
- Gate07J frozen revision inmutable;
- Post-FID/FID snapshots inmutables e idempotentes.

No confirmado como happy path limpio: siete pruebas Gate07K fallan en setup de evidencia manual. Son heredadas y no implican pérdida histórica nueva, pero el gate obligatorio no está completamente verde.

## 43. Decisión de migración — `CONFIRMADO`

- head: `20260910_0059`;
- no se reescribió una migración aplicada como parte del hardening posterior;
- no se creó sucesora para paginación porque no existe evidencia de plan que justifique índice adicional;
- la prueba PostgreSQL `test_gate07a_ba_postgres_upgrade_downgrade_upgrade` pasó;
- la suite dedicada valida esquema/lineage/constraints BA y los índices/restricciones Risk/Permit.

La migración `0059` sigue apareciendo no rastreada en git; por tanto su inclusión/versionado sigue siendo una condición operacional de entrega aunque sus pruebas pasen localmente.

## 44. Documentación de arquitectura actualizada — `PARCIAL`

Disponibles:

- `docs/64-adr-strategic-admin-user-code-hardening.md`;
- `docs/frontend-strategic-workflow-navigation-v2.md`;
- `docs/gate07a-ba-business-analysis-governance.md`;
- `docs/61-adr-gate07a-ba-business-analysis-options.md`;
- matrices de control, rutas, API y cleanup;
- diferencial baseline/current.

Actualizaciones necesarias antes del Word final:

- ADR y `baseline-differential.md`: sustituir “current pendiente” por 626/585/33/8 y 0 nuevas;
- `code-cleanup-matrix.csv`: adoptar columnas obligatorias y cerrar estados obsoletos;
- `route-compatibility-matrix.csv`: agregar clasificación `KEEP/REDIRECT/ALIAS/REMOVE`;
- anexar resultado frontend/E2E/performance cuando exista.

## 45. Informe técnico final — `PENDIENTE`

Este Markdown es el borrador de evidencia, no el entregable Word. El documento final debe:

- cubrir explícitamente los 47 entregables;
- diferenciar implementación de validación;
- incluir las ocho fallas heredadas sin ocultarlas;
- incorporar artefactos frontend/browser/performance posteriores;
- no emitir señales finales antes de cumplir los criterios;
- renderizarse y verificarse visualmente antes de su entrega.

## 46. Estado de release Gate07A-BA — `PENDIENTE`

Evidencia favorable:

- focal BA backend aprobada;
- separación API BA aprobada;
- paginación, rating y seed aprobados;
- PostgreSQL/migración BA aprobados;
- diferencial global con 0 nuevas fallas.

Evidencia faltante/bloqueante:

- gate frontend completo;
- E2E USER/ADMIN identificado;
- política de release frente a ocho fallas baseline aún presentes.

Señal conservadora al corte:

`GATE07A_BA_RELEASE_PENDING_BASELINE_REGRESSION`

No emitir todavía:

- `STRATEGIC_MACROPROCESS_ADMIN_USER_AND_CODE_HARDENING_VALIDATED`;
- `STRATEGIC_MACROPROCESS_CLEAN_SEPARATED_AND_OPTIMIZED`;
- `GATE07A_BA_BUSINESS_ANALYSIS_RELEASE_VALIDATED`.

## 47. Recomendación para el siguiente incremento — `CONFIRMADO COMO BOUNDARY`

Primero cerrar los gaps documentales, frontend, E2E y performance de este hardening. Después, y solo con solicitud explícita, el siguiente incremento funcional es:

`ENHANCE_GATE07M_BC_WITH_FIVE_CASE_MODEL`

Este hardening no añadió microservicios, motor BPM, workflow engine genérico, nuevos macroprocesos operacionales ni un Five Case Model formal. Las rutas históricas de Business Case se conservaron por compatibilidad y no deben reinterpretarse como implementación del nuevo incremento.

## Registro de pendientes para el dueño del informe final

| ID | Pendiente | Evidencia requerida |
|---:|---|---|
| P-01 | Gate frontend completo | log/JUnit con Vitest, TypeScript, build, ESLint y Prettier |
| P-02 | E2E USER | reporter Playwright por caso, idealmente trace/screenshot |
| P-03 | E2E ADMIN | reporter Playwright por caso, idealmente trace/screenshot |
| P-04 | Performance posterior | `outputs/.qa/strategic-hardening/performance-after.json` |
| P-05 | Bundle comparable | tamaños producidos por el mismo build/config antes y después |
| P-06 | Matriz cleanup conforme | CSV con las nueve columnas obligatorias de §38 |
| P-07 | Matriz route conforme | columna `KEEP/REDIRECT/ALIAS/REMOVE` |
| P-08 | Docs de cierre actualizados | ADR y diferencial con resultados current |
| P-09 | Release signal | decisión solo tras P-01 a P-08 y política de fallas heredadas |

## Fuentes primarias

- `docs/64-adr-strategic-admin-user-code-hardening.md`
- `docs/validation/strategic-hardening/admin-user-control-matrix.csv`
- `docs/validation/strategic-hardening/code-cleanup-matrix.csv`
- `docs/validation/strategic-hardening/route-compatibility-matrix.csv`
- `docs/validation/strategic-hardening/api-compatibility-matrix.csv`
- `docs/validation/strategic-hardening/baseline-differential.md`
- `outputs/.qa/strategic-hardening/baseline-pytest.xml`
- `outputs/.qa/strategic-hardening/current-pytest.xml`
- `outputs/.qa/strategic-hardening/postgres-gates-clean.xml`
- `outputs/.qa/strategic-hardening/performance-before.json`
- `frontend/test-results/.last-run.json`
- `frontend/src/features/enterprise-strategy/`
- `frontend/src/features/business-analysis/`
- `backend/app/modules/business_analysis/`
- `backend/tests/test_business_analysis_gate07a_ba.py`
- `frontend/e2e/strategic-workflow-navigation.spec.ts`
- `frontend/e2e/business-analysis-governance.spec.ts`
