# Informe técnico Wave 3A — Periodic Portfolio Review and Governance Cycle

**Producto:** P&Pmis Construction AI  
**Macroproceso:** Capital Portfolio and Investment Governance  
**Fecha de corte:** 2026-10-07 (America/Bogota)  
**Estado actual:** PERIODIC_PORTFOLIO_REVIEW_AND_GOVERNANCE_CYCLE_RELEASE_VALIDATED

Wave 3A quedó implementado y validado localmente con 69 criterios de aceptación aprobados. Este informe registra arquitectura, límites de autoridad, persistencia y pruebas reproducibles, además de las deudas de rendimiento y alcance. La aprobación local no representa una ejecución de CI remota ni una certificación de rendimiento en producción.

## 1. Resumen ejecutivo

Wave 3A incorpora un ciclo periódico de gobierno del portafolio sin crear un nuevo motor de ranking, presupuesto, recursos o decisión de inversión. La unidad de gobierno es `PortfolioReviewSession`: una sesión ligada a un portafolio que prepara y congela evidencia con linaje, admite conclusiones controladas, registra acciones con owner y fecha objetivo, y conserva una lectura histórica independiente de las fuentes live.

La implementación mantiene dos superficies estrictas. ADMIN configura y publica políticas reutilizables; USER opera sesiones, snapshots, conclusiones, acciones, comparación e historia. El backend compone los read models para evitar stitching y N+1 en el navegador. Las acciones de Review son solicitudes/instrucciones: no escriben directamente sobre las tablas de Portfolio Evaluation, Budget, Resource, Gate07I, Gate07J, Gate07K ni Wave 2A.

## 2. Baseline real del repositorio

La inspección previa registró:

| Evidencia | Baseline |
|---|---|
| Rama | `main` |
| Commit HEAD | `9cb0969abb5d48cc25b0c6a935b11e6bd7afd16f` |
| Upstream | `origin/main` |
| Working tree | Con trabajo local previo, preservado sin reset ni descarte |
| Alembic baseline anterior | `20261001_0063`; `alembic heads` local observado: `20261005_0064 (head)` |
| Release anterior | `STRATEGIC_CAPITAL_BUCKETS_AND_ALLOCATION_FRAMEWORK_RELEASE_VALIDATED` |
| Output anterior | `READY_FOR_STRATEGIC_CAPITAL_ALLOCATION_AND_PORTFOLIO_BALANCE_ANALYSIS` |
| Stack normal inicial | Docker: PostgreSQL, Redis, API, worker, beat y frontend; frontend 5173 HTTP 200 y API 8000 `/api/v1/health` `ok` (2026-10-06). Esa API inicial todavía no contenía Wave 3A |
| Actualización aditiva normal | 2026-10-07: SQL y `alembic current` confirman cabeza `20261005_0064`; API/worker/beat usan imagen nueva. Readiness 8000 confirma API, PostgreSQL y Redis; OpenAPI registra 31 rutas Wave 3A y frontend 5173 `/app` responde HTTP 200 |

Se inspeccionaron `git status`, `git diff --stat` y `git log -n 15`. El diff del baseline reportó 74 archivos tracked modificados (7.148 inserciones, 947 eliminaciones) y numerosos untracked previos; no es un conteo final exclusivo de Wave 3A. Los cambios son aditivos sobre ese árbol sucio, sin reset ni descarte. Las señales del release anterior se toman de `docs/73-wave2a-strategic-capital-buckets-allocation-release.md`; en este cierre se ejecutó además una regresión local de 63 pruebas que incluye Waves 1/2A y los dominios estratégicos relacionados. El HEAD fue reconfirmado el 2026-10-07 y permanece sin cambios.

## 3. ADR Wave 3A

La decisión formal está en `docs/74-adr-wave3a-periodic-portfolio-review.md`. Define un agregado raíz de Review, snapshot estructurado e inmutable, conclusiones y acciones; usa `AdminConfiguration` para política y conserva `strategicNavigationBlueprint.ts` como única fuente de navegación.

La decisión privilegia referencias, hashes y resúmenes necesarios para auditoría en lugar de copiar bases completas. Los dominios fuente siguen siendo soberanos. Cuando no existe un comando gobernado de ejecución, una acción queda como solicitud rastreable.

## 4. Posición en el proceso objetivo

La capacidad pertenece a la fase 4, `PORTFOLIO PLANNING & REVIEW`, después de recommendation y antes de que el flujo continúe con Business Case / Investment Development y FID. Es un bucle recurrente, no una etapa que todos los proyectos deban cruzar una sola vez.

Una misma sesión puede observar proyectos en distintas madureces. La revisión responde si la mezcla, asignación, capacidad y prioridad relativas siguen siendo adecuadas; no vuelve a decidir la madurez intrínseca de cada inversión.

## 5. Frontera Portfolio Review vs Project Gate

| Dimensión | Portfolio Review | Project Gate |
|---|---|---|
| Unidad | Portafolio colectivo | Una inversión |
| Evidencia | Snapshot transversal y comparación histórica | Evidencia Gate07J del proyecto |
| Resultado | Conclusiones y acciones de gobierno | Decisión formal Gate07K |
| HOLD | `HOLD_FOR_CAPACITY`, instrucción de portafolio | `HOLD`, decisión de inversión |
| Recalcula rank | No | No; usa su evidencia gobernada |
| Emite FID | Nunca | Solo Gate07K cuando corresponde |

La UI etiqueta por separado `Investment Decision Status` y `Portfolio Governance Action`. Ninguna acción Wave 3A se presenta como GO/HOLD/RECYCLE/KILL o FID.

## 6. Matriz de autoridad de dominio

| Dominio | Autoridad | Uso Wave 3A | Mutación Wave 3A |
|---|---|---|---|
| Membership | Portfolio Planning | Alcance activo | No |
| Rank | Portfolio Evaluation | Lectura y staleness | No |
| Scorecard | Portfolio Analysis | Contexto | No |
| Buckets/Allocation | Wave 2A | Target/current/recommended/approved/variance | No directa |
| Budget | Portfolio Budget | Escenario y factibilidad | No |
| Resource | Portfolio Resource | Capacidad y overload | No |
| Recommendation | Gate07I | Alternativa recomendada/hash | No |
| Preparation | Gate07J | READY/BLOCKED/STALE | No |
| Decision/FID | Gate07K | Estado/condiciones/FID | No |
| Review | Wave 3A | Sesión/snapshot/conclusiones/acciones | Sí, solo su agregado |

## 7. REUSE BEFORE CREATE

Se reutilizan Membership, Evaluation/Rank, Analysis, Budget, Resource, Convergence, Gate07J, Gate07K, Risk/readiness summaries y el contrato de snapshot Wave 2A mediante adaptadores de lectura. También se reutilizan `AdminConfiguration`, `AdminNumberSequence`, RBAC, `SecurityEvent`, ETag, idempotencia y el blueprint estratégico.

Se crean únicamente entidades cuya identidad, lifecycle o inmutabilidad no podían representarse de forma segura como datos derivados: session, snapshot, conclusion y action. No existe tabla por tipo, agenda, source ni threshold.

## 8. Review Session aggregate

`PortfolioReviewSession` es el agregado raíz. Conserva identificador técnico, `review_number` estable, `portfolio_id`, ciclo y allocation plan opcionales, tipo, período, fechas planeada/real/siguiente, status, chair, secretary, scope Workspace, agenda, revisión/hash de configuración, snapshot actual, actor, timestamps y `revision_version`.

La numeración visible usa el patrón `PRV-######` y el mecanismo de secuencias administrativas existente. El portafolio es obligatorio; Wave 3A no crea una sesión enterprise-wide de alcance mixto.

## 9. Review lifecycle

```text
DRAFT → PREPARING → READY_FOR_REVIEW → IN_REVIEW → COMPLETED
                    ↘ RETURNED
DRAFT / PREPARING / READY_FOR_REVIEW / IN_REVIEW / RETURNED → CANCELLED
READY_FOR_REVIEW / IN_REVIEW / STALE → RETURNED
Sesión no terminal → SUPERSEDED (sucesora explícita)
```

Las transiciones son backend-owned, auditadas e idempotentes. Return/cancel/supersede exigen reason, ETag e idempotency key. `COMPLETED` bloquea cambios a sesión, snapshot y conclusiones; una corrección requiere otra revisión. Las acciones pueden continuar después de completar, pero no mutarse en reviews `CANCELLED` o `SUPERSEDED`.

## 10. Review types

Los tipos `SCHEDULED`, `MONTHLY`, `QUARTERLY`, `SEMIANNUAL`, `ANNUAL`, `AD_HOC` y `EXCEPTION` son ejemplos de configuración, no enums empresariales inmutables. ADMIN publica los códigos aplicables, labels, vigencia y reglas de uso. USER solo selecciona tipos efectivos para el contexto.

## 11. Cadence

La cadencia usa `frequency_days` de política publicada y resolución jerárquica de scope. La aplicabilidad soporta governance model, status y mínimo de proyectos. No hay motor automático de cadencia por capital, riesgo o importancia estratégica. Review registra cumplimiento de revisiones planeadas, completadas, tardías y próxima fecha sin convertirse en calendario corporativo.

## 12. Scheduling semantics

Se distinguen `planned_review_date`, `actual_review_date` y `next_planned_review_date`. Si al completar se omite la próxima fecha, se deriva de la fecha real más `frequency_days`. No crea automáticamente otra sesión, tareas enterprise ni cambios de fechas de proyecto.

## 13. Snapshot contract

El snapshot es JSON estructurado, inmutable y con hash canónico. Incluye identidad/version/hash del Allocation Plan, ciclo/scope, configuración de Buckets, posiciones target/current/recommended/approved, variance, exposición unclassified, Membership, Evaluation/Rank, Scorecard, Budget, Resource, Convergence, Gate07I, Gate07J, Gate07K, readiness y timestamps `as_of`.

Las referencias fuente conservan dominio, tipo, ID, versión/hash y actualidad. No se copian bases completas; se congela suficiente contexto para auditoría, decisión y lectura histórica.

## 14. Snapshot adapters

Los adaptadores de lectura se agrupan en Portfolio Core, Allocation, Budget, Resource, Scenario Recommendation, Gate y Risk/Readiness. El servicio Wave 3A orquesta consultas y normaliza el contrato. Reutiliza `PortfolioResourceService.scenario()` como proyección read-only: instanciar ese servicio no ejecuta comandos de recursos ni crea un motor paralelo.

La composición ocurre en backend. La UI recibe un read model consistente por sesión y no realiza N+1 ni decide precedencia entre fuentes.

## 15. Source-current y staleness

Antes de `READY_FOR_REVIEW`, el backend valida fuentes obligatorias, `source_current`, versión/hash y compatibilidad de portafolio, ciclo, plan y escenarios seleccionados. Las fuentes opcionales ausentes generan warnings; las obligatorias ausentes o stale generan blockers. Freshness de Gate y Risk/Readiness se configura en días. La política define el contexto mínimo; no exige toda fuente opcional por defecto.

Cuando cambia una fuente material después del freeze, el payload histórico no cambia. Una sesión live pasa a `STALE` cuando la policy lo exige y requiere nuevo preview/freeze antes de completar.

## 16. Snapshot Preview / Freeze

`snapshot-preview` compone evidencia sin persistir y declara `persisted=false`. Expone diferencias de membership, rank, budget, resource, allocation, recommended/approved, Gate y nuevos warnings/blockers.

`freeze-snapshot` persiste JSON, referencias y hash solo en estados permitidos. Reintentos con la misma idempotency key retornan el mismo resultado. Una sesión completada rechaza preview aplicable o reemplazo de snapshot.

## 17. Agenda model

La agenda publicada puede incluir Strategic Alignment, Capital Allocation Balance, Portfolio Priority, Budget Position, Resource Capacity, Gate/FID Status, Risk/Readiness, Exceptions, Projects Requiring Decision, Portfolio Actions y Follow-up Actions. Se almacena como estructura flexible dentro de política/sesión; no hay tabla o formulario Gate por sección.

## 18. Review readiness

El backend produce readiness de snapshot, allocation context, portfolio data, budget, resource, Gate y agenda, más un overall. Su pregunta es “¿está completo el paquete para gobernanza?”, nunca “¿debe aprobarse el portafolio?”.

Wave 3A no se registra como provider Gate07J y no modifica su policy. Readiness de Review solo gobierna el lifecycle propio.

## 19. Portfolio conclusions

Las conclusiones admiten códigos publicados como `PORTFOLIO_BALANCED`, `PORTFOLIO_REBALANCING_REQUIRED`, `CAPITAL_CONSTRAINED`, `RESOURCE_CONSTRAINED`, `STRATEGIC_MISALIGNMENT`, `EXCESS_UNCLASSIFIED_EXPOSURE`, `PORTFOLIO_REASSESSMENT_REQUIRED` y `NO_MATERIAL_CHANGE`.

Cada conclusión conserva rationale, actor y timestamps. No se interpreta como una decisión de proyecto.

## 20. Review Action aggregate

`PortfolioReviewAction` conserva ID, sesión, subject type/id y `subject_key` (bucket estable), action type, rationale, priority, owner, due date, status, evidencia, autoridad solicitada, referencia de solicitud/ejecución, creador/aprobador, timestamps y versión.

La sesión puede cerrarse con acciones abiertas. La cola transversal usa índices por sesión, estado, owner y vencimiento sin convertirse en un task manager genérico.

## 21. Action types

La configuración puede publicar `RETAIN_PRIORITY`, `ACCELERATE`, `DEFER`, `HOLD_FOR_CAPACITY`, `REQUEST_REASSESSMENT`, `REMOVE_FROM_ACTIVE_PORTFOLIO`, `MOVE_BETWEEN_BUCKETS`, `REBALANCE_CAPITAL`, `REBALANCE_RESOURCES`, `REQUEST_GATE_REVALIDATION`, `REQUEST_BUSINESS_CASE_REVALIDATION`, `REQUEST_BENEFITS_REVALIDATION` y otros códigos controlados.

La aplicabilidad valida subject, estado, governance model y autorización. El catálogo no se hardcodea como una lista que ADMIN no pueda evolucionar.

## 22. Action lifecycle

```text
OPEN → ACCEPTED → IN_PROGRESS → COMPLETED
  ├→ REJECTED
  └→ CANCELLED
```

Cada transición usa ETag/If-Match, permisos y auditoría. `approve` y `dispatch` son operaciones distintas: aprobar una instrucción no implica que el dominio solicitado haya ejecutado el cambio.

## 23. Action authority/dispatch boundary

Una acción es una instrucción o solicitud de gobierno. `HOLD_FOR_CAPACITY` no crea Gate07K HOLD; `REQUEST_REASSESSMENT` no recalcula score/rank; `REBALANCE_CAPITAL` no edita Budget; `REBALANCE_RESOURCES` no nivela recursos; `REQUEST_GATE_REVALIDATION` no crea RECYCLE.

Por defecto, dispatch conserva la solicitud en Wave 3A y registra la autoridad destino. El response declara si hubo ejecución externa o si continúa request-only.

## 24. Source-authority adapter rules

Un adaptador ejecutable solo es válido si el dominio dueño ya publica un comando gobernado, el actor posee permiso específico, la policy permite invocarlo y el request es idempotente. El adaptador llama el servicio público; nunca escribe tablas ajenas.

Solo se implementa `REQUEST_ONLY`: dispatch devuelve `REQUEST_RECORDED`, `external_execution=false` y una referencia local `PORTFOLIO_REVIEW_REQUEST:...`. Esa referencia prueba registro de solicitud, no ejecución en la autoridad fuente. No hay adaptador ejecutable habilitado ni escrituras externas directas.

## 25. Allocation integration

El snapshot reutiliza el read model Wave 2A: target, current demand, current portfolio, recommended, approved, variance, bucket status y unclassified exposure. La sesión almacena referencia/version/hash del Allocation Plan y no reimplementa sus cálculos.

El endurecimiento de cierre filtra las opciones de Allocation Plan por tenant y workspace autorizado. La selección automática conserva el plan del portafolio revisado aunque exista otro plan más reciente dentro del mismo enterprise. Un plan explícito sin portfolio no evade su scope: un actor fuera de alcance recibe 403 y un scope sibling incompatible es rechazado con 422. No se interpreta compartir enterprise como pertenecer al mismo portafolio.

El ciclo de planificación también se valida aunque no se seleccione Allocation Plan. Se admiten ciclos de scope global o de un nivel ancestral compatible, sin exigir al actor un grant directo sobre ese ancestor. Se rechazan ciclos sibling explícitos, inferidos del plan o encontrados durante la selección automática. La construcción del snapshot vuelve a validar el linaje, incluidos registros previos malformados. El recheck final aprobó los tres casos focales en SQLite (88,71 s) y PostgreSQL (132,37 s), con las autoridades fuente intactas.

## 26. Bucket variance integration

Review identifica buckets under-target/over-target, current vs recommended, recommended vs approved, exposición sin clasificar y proyectos que contribuyen a la variance. Los thresholds generan warnings y agenda flags, no cambios automáticos de clasificación.

`MOVE_BETWEEN_BUCKETS` queda request-only salvo un futuro adaptador explícito al comando gobernado Wave 2A.

## 27. Budget integration

Se consume read-only Budget Target, escenario seleccionado/FROZEN, estados de selección, waterline, CAPEX/Expense y totales por moneda. Review no crea scenario, no mueve waterline y no modifica target o proyectos seleccionados.

Los tests comparan los hashes/filas Budget antes y después de acciones para probar ausencia de mutación.

## 28. Resource integration

Se consume read-only Capacity Plan, Resource Scenario, demanda/capacidad, overloads, timing shifts y factibilidad. Review no ejecuta leveling ni cambia fechas de proyecto. `HOLD_FOR_CAPACITY` registra la restricción en el portafolio sin alterar el escenario.

## 29. Gate07I integration

Se consume alternativa recomendada, factibilidad combinada, conjuntos aligned/misaligned, conflictos forzados y recommendation hash. No se crea una segunda recomendación ni se modifica la selección Gate07I.

## 30. Gate07J integration

Se consume el estado READY/BLOCKED/STALE y resúmenes de preparación. Wave 3A no crea `PORTFOLIO_REVIEW_READINESS_PROVIDER`, no altera criterios de evidencia y no registra un resultado Review como evidencia de inversión.

## 31. Gate07K integration

Se consume la última decisión formal, flags FID y condiciones. Las acciones de Review permanecen en su namespace, incluso cuando solicitan revalidación. No se genera GO/HOLD/RECYCLE/KILL ni FID desde Wave 3A.

## 32. Gate HOLD vs Portfolio HOLD

La representación distingue explícitamente:

```text
Investment Decision Status = Gate07K
Portfolio Governance Action = Wave 3A
```

El código `HOLD_FOR_CAPACITY` y el label de UI nunca se reducen a `HOLD`. La prueba de semántica comprueba que no aparece una nueva fila o versión de `InvestmentDecision`.

## 33. Project Matrix

El endpoint de matriz genera una fila por proyecto activo con Project, rank, bucket, contribución a variance, budget/resource status, Gate stage/readiness, Investment Decision, FID, risk/readiness, recommendation, approved context y acción vigente.

Soporta paginación estable y filtros server-side por bucket, rango de rank, tipo, Gate/FID, Budget, Resource, acción, owner, blocked/stale y unclassified. La carga de fuentes se hace por lotes.

## 34. Portfolio summary

El summary expone tamaño, proyectos por estado/bucket, capital por bucket y moneda, variance, factibilidad Budget/Resource, distribuciones Gate/FID, blockers, reassessment, acciones abiertas y vencidas. No introduce score propietario.

## 35. Thresholds/alerts

ADMIN publica tolerancias de bucket variance, exposición UNCLASSIFIED, overload de recursos, freshness de evidencia Gate/Risk, conteo de proyectos blocked y días de vencimiento de acciones. No se implementa threshold monetario de proyectos blocked. Son warnings/readiness/agenda, nunca decisiones automáticas de inversión.

## 36. Multi-currency behavior

Los montos se agrupan por currency. Si hay más de una moneda y no existe normalización gobernada, se retorna `NOT_EVALUABLE`, currencies agrupadas y warning; no se suma COP, USD u otras monedas en un total falso.

El caso ampliado `test_wave3a_multicurrency_allocation_is_grouped_and_unclassified_membership_is_preserved` aprobó en PostgreSQL (1 PASS; 89,16 s) y SQLite (1 PASS; 83,34 s) el 2026-10-07. Con COP/USD/COP conservó totales por moneda, porcentajes no evaluables y las tres memberships. El proyecto STANDALONE sin Idea mantuvo UNCLASSIFIED en matriz y snapshot; el filtro identificó exactamente un unclassified y dos classified, sin cambios a las autoridades fuente.

## 37. Historical snapshots

Una sesión completada conserva identidad, fecha, scope, configuración, agenda, snapshot, conclusiones, acciones al cierre, source references/hashes y `as_of`. Los endpoints históricos leen ese payload congelado y no consultan fuentes live para reinterpretarlo.

## 38. Period comparison

La comparación permite Current Review frente a Previous Completed Review; la actual no necesariamente está completada. Usa snapshots existentes y deltas de membership, rank observado, Bucket, variance, factibilidad Budget/Resource, Gate/FID y acciones. No muta ni recalcula snapshots con configuración posterior.

## 39. Trends

Las tendencias opcionales se calculan solo sobre revisiones completadas: variance por fecha, unclassified exposure, valor/conteo, blocked count, overload count, open actions y progresión FID. No se interpolan períodos faltantes.

## 40. Action tracking

La API y UI permiten colas Open, Due Soon, Overdue, Completed y filtros por owner, project, bucket y review. El estado de acción permanece separado del status de Review y de las fuentes externas.

## 41. ADMIN configuration

La ruta ADMIN edita General, Review Types, Cadence, Applicability, Agenda, Required Sources/Freshness, Readiness, Conclusions, Actions/Applicability, Thresholds, Bucket/Unclassified, Budget/Resource/Gate, Authority, SoD, Numbering, Inheritance, Preview e History. Solo soporta `SINGLE_PORTFOLIO_AUTHORITY`, quorum 1 y `NOT_REQUIRED` voting; otros modelos se rechazan, no se simula comité. Las reglas de owner son controles activos fijos de autorización, no un motor configurable.

El workflow usa clone → update DRAFT → effective preview `persisted=false` → publish → archive. No contiene botones de crear, congelar, conducir o completar sesiones live.

## 42. USER workflow

La ruta USER permite calendario/sesiones, Overview, Snapshot, Strategic Allocation, Project Matrix, Budget & Resources, Gate/FID, Exceptions, Conclusions, Actions, History y Trends. No expone clone/publish/archive de configuración.

El flujo normal es crear → preparar → preview → freeze → ready → start review → registrar conclusiones/acciones → complete → consultar historia/comparación.

## 43. ADMIN/USER matrix

| Capacidad | ADMIN | USER |
|---|---:|---:|
| Definir tipos/cadencia | Sí | No |
| Publicar thresholds/SoD | Sí | No |
| Effective preview de política | Sí | No |
| Crear sesión live | No | Sí |
| Freeze snapshot | No | Sí, con permiso |
| Registrar conclusión/acción | No | Sí, con permiso |
| Completar Review | No | Sí, autoridad separada |

Un actor con ambos roles debe cambiar de modo; los permisos no se heredan por conveniencia visual.

## 44. Roles/permissions

El catálogo contempla `portfolio_review.read`, `.create`, `.prepare`, `.freeze_snapshot`, `.submit`, `.conduct`, `.complete`, `.action.create`, `.action.approve`, `.action.update`, `.admin.configure` y `.admin.publish`. Los routers aplican permisos a cada comando, no solo a la visibilidad del menú.

## 45. SoD

Cuando la policy lo exige, el preparer no puede ser autoridad final. El owner no recibe aprobación implícita. La regla se resuelve desde configuración efectiva; no se hardcodea una persona u organización. La aprobación exige permiso separado y no se elude mediante update de status. ADMIN scoped no escapa su jerarquía y grants distintos no se combinan para ampliar scope.

## 46. ETag

Las entidades mutables exponen `revision_version` y ETag. Todo update/transición recibe `If-Match`; una versión stale retorna HTTP 412 con `ETAG_MISMATCH`. El snapshot de una sesión completada no admite un nuevo ETag de escritura porque es inmutable.

## 47. Idempotency

Creación de sesión, freeze, complete, creación/aprobación/dispatch de acción aceptan `Idempotency-Key`. El backend persiste o reutiliza el resultado lógico de cada comando para evitar sesiones, snapshots, conclusiones o acciones duplicadas durante reintentos.

## 48. SecurityEvent

Se auditan create/update/prepare/freeze/start/complete, conclusión, action lifecycle/dispatch y configuración clone/update/publish/archive. Cada evento conserva actor, acción, entidad, outcome y metadata sin registrar secretos.

## 49. Persistence

La persistencia separa session, snapshot, conclusion y action, más `portfolio_review_commands`, ledger de idempotencia. Los snapshots usan JSON, source reference index y hash. Se indexan portfolio/status/date, session/hash, session/conclusion, session/action status/owner/due date y claves idempotentes.

La configuración reusable continúa en `AdminConfiguration`; no se añade una tabla por agenda, source o action type.

## 50. Migration

`20261005_0064_wave3a_periodic_portfolio_review.py` sucede a `20261001_0063`; `alembic heads` local devolvió una sola cabeza 0064. La prueba PostgreSQL ejecutó DDL real upgrade/down/upgrade de 0064 sobre la superficie mínima FK de 0063: 1 PASS en 51,30 s, con evidencia Docker recuperada el 2026-10-07. Verificó cinco tablas/índices/constraints y conservó filas sentinel de Allocation/Membership/InvestmentDecision. No pretende reconstruir la historia completa de las 64 migraciones. La suite funcional usa metadata actual en otra base efímera; no se confunde stamp con una migración ejecutada.

El 2026-10-07 también se aplicó upgrade real de `20261001_0063` a `20261005_0064` en la base PostgreSQL principal existente. Antes se conservó un backup de 1.872.635 bytes en `outputs/.qa/wave3a-portfolio-review/backups/postgres-before-wave3a-20261007.dump`; no se reinicializó la base ni se descartaron datos. Las comprobaciones SQL y `alembic current` posteriores confirmaron `20261005_0064 (head)` y cero review sessions/actions creadas. No se eliminaron contenedores orphan previos del stack normal.

La política reusable se provisionó explícitamente mediante `python -m app.modules.portfolio_review.bootstrap --tenant-id 1 --actor-id 1`. El comando reutiliza `AdminConfiguration` y `AdminNumberSequence`, y confirmó `WAVE3A_POLICY_PROVISIONED` con `live_reviews_created=0`. No construye sesiones ni acciones live y evita sembrar configuración durante GET de usuarios viewer.

## 51. API

USER usa `/api/v1/portfolio-reviews` para list/create/detail/update/lifecycle, snapshot preview/freeze, matrices/read models, history, comparison, trends y actions. Las acciones individuales usan `/api/v1/portfolio-review-actions`.

ADMIN usa `/api/v1/portfolio-reviews/admin/...` para configurations, effective preview, clone, update, publish y archive. Los responses mutables exponen ETag y los comandos de alto riesgo exigen idempotencia.

Después del upgrade principal y bootstrap del 2026-10-07 se levantaron API, worker y beat con la nueva imagen. `GET http://127.0.0.1:8000/api/v1/health/ready` confirmó `ready` para API, database y Redis; el catálogo OpenAPI confirmó 31 paths Wave 3A y `GET http://127.0.0.1:5173/app` respondió HTTP 200. Estas comprobaciones confirman el servicio local actualizado, pero no sustituyen las pruebas funcionales ni Chromium, que se ejecuta sobre el stack efímero separado 5516/8813.

La comprobación PostgreSQL del endurecimiento final de scope Allocation aprobó 3 casos en 248,19 s. API, worker y beat se recrearon con la última imagen y la comprobación posterior confirmó readiness de API/database/Redis, frontend 5173 `/app` HTTP 200 y 31 paths OpenAPI Wave 3A. Los cuatro workers de API completaron el arranque. Hubo peticiones de sondeo con timeout durante warming, no en el estado final confirmado. La base principal conserva la actualización aditiva descrita en la sección anterior; el navegador de release usa exclusivamente la base efímera.

El control adicional de compatibilidad Planning Cycle aprobó el recheck en SQLite y PostgreSQL. API, worker y beat se recrearon con la imagen que incluye ese control, sin recrear PostgreSQL ni Redis. Las comprobaciones finales confirmaron API/database/Redis ready, frontend 5173 `/app` HTTP 200, migración 0064 y cero Review Sessions/Actions de prueba en la base principal. Chromium completo aprobó sobre su base independiente.

## 52. Navigation

`strategicNavigationBlueprint.ts` incorpora `Periodic Portfolio Review` bajo Portfolio Planning & Review en USER y `Portfolio Planning & Review Configuration → Periodic Portfolio Review` en ADMIN. Todas las subviews se derivan del mismo blueprint y se resuelven por `StrategicViewOutlet`.

`App.tsx` no contiene rutas ni componentes Wave 3A. `applicationNavigation.ts` continúa proyectando `buildStrategicMacroprocess("user")` y `buildStrategicMacroprocess("admin")`.

## 53. PostgreSQL happy path

La suite PostgreSQL prepara un portfolio CAPITAL_OWNER con múltiples proyectos y fuentes Wave 2A/Gate07x; publica policy, crea sesión, preview/freeze, valida hashes, inicia revisión, consulta matrices, registra conclusiones, completa y verifica historia inmutable. Las pruebas parametrizadas verifican cinco tipos de acción en sesiones independientes; el caso Chromium aprobado añadió tres acciones distintas en una misma sesión real.

PostgreSQL 16 efímero, mediante `docker-compose.wave3a.yml`, obtuvo 31 PASS en 642,10 s: 30 casos funcionales compartidos y un control de dialecto, tablas, índices y constraints. Incluye denegación de mutaciones de acciones en sesiones CANCELLED/SUPERSEDED, owner-only con roles adicionales y grants de scope que no se multiplican. El caso multimoneda/standalone añadido después obtuvo 1 PASS en 89,16 s. El recheck final de scope obtuvo 3 PASS en 248,19 s: dos casos nuevos y el happy path repetido. Son 34 casos funcionales/schema únicos aprobados acumulados en tres ejecuciones, no una única ejecución de 34. La migración real separada obtuvo 1 PASS en 51,30 s; los resultados están conservados en los logs Docker.

La ejecución focal SQLite del 2026-10-06 obtuvo 30 casos PASS en 246,39 s, sin coverage; el caso ampliado del 2026-10-07 obtuvo 1 PASS en 83,34 s. El recheck scope obtuvo 3 PASS en 131,15 s, de los que solo dos son casos nuevos: 33 casos únicos SQLite acumulados en tres ejecuciones. El wrapper PostgreSQL ejecutó esa suite y su control de schema. No se considera que SQLite sustituya el happy path PostgreSQL ni la prueba real de migración. El entorno funcional y el de migración usan bases separadas sobre tmpfs; el browser usa exclusivamente `wave3a_browser` y guard `PYPMIS_WAVE3A_BROWSER_FIXTURE=disposable-only`.

Después del control de ciclos se repitieron opciones scope, selección automática ampliada y el lifecycle de dos actores: SQLite 3 PASS en 88,71 s y PostgreSQL 3 PASS en 132,37 s. No son casos nuevos independientes: los acumulados permanecen en 33 únicos SQLite y 34 únicos PostgreSQL, ahora en cuatro ejecuciones aprobadas por motor. Los primeros intentos del test ampliado detectaron dos defectos de fixture (lectura de CycleOut en lugar de la entidad ORM y ausencia de grants de los proyectos); sus logs se conservan y no se cuentan como aprobados.

El servicio `wave3a-browser-frontend` compila el mismo código con `npm run build -- --outDir /tmp/wave3a-browser-dist` y sirve ese bundle con preview. El build final de esta superficie aprobó en 22,46 s y HTTP 5516 confirmó el servidor preview. Mantiene API real 8813, `VITE_FRONTEND_VALIDATION_MODE=false` y bind del repositorio en solo lectura; no hay route interception ni API mocks en los casos release. La CI permite hasta 300 s de arranque para API/frontend, con probes curl de máximo 10 s cada uno.

## 54. Action-semantics tests

`test_wave3a_action_semantics_are_request_only_without_source_mutations` es parametrizado con cinco acciones, incluidas `HOLD_FOR_CAPACITY`, `REQUEST_REASSESSMENT` y `REBALANCE_CAPITAL`. `_authorities()` compara todos los valores persistidos, no solo conteos, de 21 tablas Portfolio, Budget, Resource, Convergence, Gate, Risk y Waves 1/2A; también compara la proyección de rank. Esos casos aprobaron tanto en SQLite como en PostgreSQL. Chromium también aprobó las tres acciones citadas en una misma sesión real.

## 55. Bucket action test

`MOVE_BETWEEN_BUCKETS` se guarda como request Wave 2A con `subject_key` controlado. Dispatch no cambia clasificación ni Allocation Plan: registra referencia local `PORTFOLIO_REVIEW_REQUEST:...` y `external_execution=false`.

## 56. Gate-revalidation action test

`REQUEST_GATE_REVALIDATION` no genera una decisión formal RECYCLE/HOLD, no modifica Gate07J y no crea FID. El action record identifica la autoridad destino y permanece trazable.

## 57. Snapshot staleness test

Después de freeze se cambia una fuente material en fixture. La sesión live reporta `STALE`; el snapshot persistido y su hash permanecen idénticos, mientras un nuevo preview muestra la diferencia.

## 58. Completed-review immutability

`test_wave3a_completed_history_trends_and_comparison_never_reinterpret_live_sources` cambia Membership después del cierre, verifica completion hash/payload y snapshot históricos, compara períodos de tres y dos proyectos y prueba trends sin interpolación. Las acciones al cierre permanecen en el completion payload: la cola live puede avanzar follow-up, sin reescribir ese histórico. Formó parte de los 30 PASS SQLite.

## 59. Portfolio Rank regression

Se registra el hash/estado de Evaluation y Rank antes y después del happy path y las acciones. No se invoca calculate/recalculate y no cambia ninguna fila de autoridad. La regresión independiente de Gate07E aprobó siete casos: scoring determinista, ranking contextual, aislamiento entre portafolios, exclusión de memberships inactivos, historia y preview ADMIN.

## 60. Budget regression

El escenario Budget y sus proyectos conservan ID, versión, estado, selección y montos. `REBALANCE_CAPITAL` es una solicitud, no una edición de Budget Target/Scenario. La regresión independiente aprobó cinco casos Gate07G y tres Gate07G-A sobre target/scenarios, currency guardrail, historia, waterline y dependencias.

## 61. Resource regression

Capacity Plan, Resource Scenario, demanda y períodos conservan versión y valores. `HOLD_FOR_CAPACITY` no ejecuta leveling ni cambia fechas. Siete casos Gate07H aprobaron overload/timing/comparison, demanda ausente, unidades, staleness, historia, exclusión de modelos no habilitados y preview ADMIN.

## 62. Gate07I regression

Recommendation, alternative y hash de Convergence permanecen sin cambios. Review los referencia en snapshot y no produce una recommendation paralela. Cuatro casos Gate07I aprobaron recommendation, conflictos, inmutabilidad/clone y preview de configuración sin persistencia.

## 63. Gate07K regression

InvestmentDecision, outcome, flags FID y conditions permanecen sin cambios. El namespace de Review nunca emite GO/HOLD/RECYCLE/KILL. Nueve casos Gate07K aprobaron selección sin FID, FID único PYP/FFA, idempotencia, criterios congelados, HOLD/RECYCLE/KILL, SoD y reglas de comité existentes del dominio Gate; Review no añade ese modelo de comité.

## 64. Wave 2A regression

Allocation Plan, líneas, clasificaciones, target/current/recommended/approved, variance y unclassified exposure mantienen su autoridad. Review reutiliza su contrato y no reescribe la lógica de cálculo. Los siete casos de `test_capital_allocation_wave2a.py` aprobaron porcentaje/multimoneda/UNCLASSIFIED, precedence/linaje, configuración versionada, Gate07I/FID y controles HTTP/RBAC.

## 65. Wave 1 regression

Planning Cycle, Demand, Theme y Demand→Idea lineage conservan identidad, lifecycle y datos. Wave 3A solo referencia contexto cuando está disponible. Cinco casos Wave 1 y uno HTTP RBAC aprobaron lifecycle, origen atómico, idempotencia, SoD, configuración, herencia y compatibilidad de ideas históricas.

## 66. Governance Model regression

La capacidad queda habilitada por policy para `CAPITAL_OWNER`. `CONTRACTOR_DELIVERY` y `DIRECT_INTERNAL` no se fuerzan; la compatibilidad legacy se conserva. Diez casos de creación multi-source verificaron independencia entre governance model y project type, origen Contract/Direct/Standalone, materialización, autorización y linaje; se complementan con el caso focal opt-in de Review.

## 67. Browser USER E2E

Chromium navegó USER MODE → Enterprise Strategy Manager → Portfolio Planning & Review → Periodic Portfolio Review y verificó create, preview, freeze, Allocation, Matrix, Budget/Resources, Gate/FID, Exceptions, Conclusions, Actions, complete, History y comparison. Dos actores completaron las revisiones PRV-000006 y PRV-000007; la segunda registró HOLD_FOR_CAPACITY, REQUEST_REASSESSMENT y REBALANCE_CAPITAL. La superficie USER no expuso controles ADMIN.

## 68. Browser ADMIN E2E

Chromium navegó ADMIN MODE → Portfolio Planning & Review Configuration → Periodic Portfolio Review y verificó sections, preview `persisted=false`, clone scoped, edición de Review/SoD, publish y archive. La superficie no ofreció operaciones live. El caso completo USER/ADMIN y el caso independiente de ruta directa aprobaron juntos: 2 PASS en 5,1 minutos, con trazas guardadas.

## 69. Direct-route security

`test_wave3a_http_etag_idempotency_and_admin_user_approval_dispatch_rbac` verificó HTTP 403 para USER sin configure en ADMIN, config-only en mutación live y preparer sin aprobación/dispatch. Los tests de tenant/workspace y scopes combinados impiden grants que crucen alcances. Formaron parte de los 30 PASS SQLite. La denegación de ruta directa también aprobó en la ejecución Chromium final.

Los dos casos de cierre `test_wave3a_options_do_not_disclose_allocation_plans_outside_workspace_or_tenant_scope` y `test_wave3a_automatic_allocation_selection_never_uses_another_portfolios_enterprise_plan` aprobaron junto con la repetición del happy path de dos actores: SQLite 3 PASS en 131,15 s y PostgreSQL 3 PASS en 248,19 s. Se verificaron opciones fuera de tenant/workspace vacías, solicitud explícita denegada, plan propio seleccionado y rechazo de plan genérico sibling. Los dos warnings SQLite son ACL de `.pytest_cache`, sin fallos funcionales.

El tercer intento Chromium aprobó el caso independiente de ruta ADMIN directa: USER sin configuración encontró denegación de acceso y no pudo cambiar a ADMIN MODE. El caso largo combinado USER/ADMIN alcanzó el timeout global de 360 s, con la primera sesión COMPLETED y la segunda IN_REVIEW; ese avance parcial no se contabiliza como happy path aprobado y no se reportó error funcional HTTP como causa. El siguiente intento conserva todas las aserciones, aumenta solo el presupuesto global a 720 s y sirve el bundle compilado del mismo frontend/API sobre el stack disposable.

El intento con preview y 720 s aprobó la ruta directa pero venció la aserción visual de 30 s después de Start Review. La traza mostró el POST todavía sin respuesta, mientras SQL confirmó IN_REVIEW; no mostró un HTTP 200 descartado por React ni un GET posterior. Una consulta simultánea de tendencias tardó 31,67 s. El reintento sincronizado espera hasta 120 s la respuesta HTTP de start/complete, exige HTTP 200 y el status correcto, y después mantiene la comprobación visual de 30 s. El timeout global sigue en 720 s y no se eliminan aserciones.

La segunda detención se aisló en selectores de prueba: `getByLabel(..., exact=true)` incluía el texto de las opciones de un select anidado dentro del label. El snapshot mostraba los combobox habilitados y con catálogo completo. Se cambió únicamente Action type y Subject type a `getByRole("combobox", {name, exact:true})`, conservando la selección de valores publicados y todas las aserciones. No se deshabilitó seguridad ni se cambiaron permisos para lograr el recorrido.

## 70. Performance observation

La matriz y summary usan agregación backend, consultas por lotes, paginación e índices. El test UI `uses the server matrix filters and stable pagination without querying individual Projects` verifica ausencia de llamadas por proyecto desde el navegador. La suite SQLite focal ejecutó 30 casos en 246,39 s sin coverage, y la regresión cruzada obtuvo 63 PASS en 891,29 s. Son observaciones funcionales del proceso de pruebas, no un SLA por endpoint ni un benchmark de cientos/miles de proyectos. La fixture funcional tiene tres proyectos; la carga masiva sigue como deuda.

La traza Chromium de cierre observó una consulta de tendencias de 31,67 s con peticiones simultáneas y una respuesta start-review pendiente después del commit. Se conservan como observaciones de latencia del entorno local; no se atribuyen al rendimiento de producción ni se ocultan con el timeout global. El test sincroniza los comandos con su respuesta HTTP, pero el perfilado de proyecciones concurrentes y la prueba de carga siguen pendientes.

## 71. Deuda técnica

- Benchmark de miles de proyectos con distribución realista de fuentes.
- Perfilado de las proyecciones concurrentes de Review y de la latencia observada en tendencias.
- Adaptadores de dispatch ejecutable solo cuando cada dominio publique un comando gobernado.
- Materialización o cache de tendencias si el volumen histórico lo exige.
- Ampliación de fixtures PostgreSQL más allá del caso COP/USD/UNCLASSIFIED aprobado, con más monedas, períodos y estados Gate.
- Validación visual adicional en motores distintos de Chromium.

Ninguna deuda habilita mutaciones cruzadas o relaja la inmutabilidad.

## 72. Análisis final de brechas estratégicas

| Incremento candidato | Dependencia/valor | Reuso | Complejidad y riesgo de duplicación |
|---|---|---|---|
| Wave 2B — Risk Appetite / Capacity / Thresholds + Basic Data Readiness | Mejora la calidad de evidencia temprana y de blockers antes de FID | Alto sobre readiness, policy y snapshots | Media; debe respetar Risk y Gate07J |
| Wave 3B — Owner Capability Readiness | Aporta capacidad organizacional a la decisión | Medio sobre Workspaces/RBAC/readiness | Media; depende de datos organizacionales consistentes |
| Wave 4 — QRA / Confidence | Cuantifica incertidumbre avanzada | Medio sobre Risk/FIN/snapshots | Alta; prematura sin appetite y basic data sólidos |

El orden lógico favorece cerrar primero la base de riesgo y calidad de datos. QRA antes de esos prerrequisitos aumentaría complejidad y produciría confianza aparente sobre evidencia incompleta.

## 73. Estado final de release

Estado exclusivo: `PERIODIC_PORTFOLIO_REVIEW_AND_GOVERNANCE_CYCLE_RELEASE_VALIDATED`.

Final output: `READY_FOR_GOVERNED_PERIODIC_PORTFOLIO_REVIEW`.

Las 69 filas de la matriz están en PASS, respaldadas por las ejecuciones locales y los logs siguientes. Se preservan los intentos fallidos para explicar el cierre; no se suman como pruebas aprobadas.

Evidencia estática reconfirmada el 2026-10-07: `WAVE3A_RELEASE_GUARDRAILS=PASS` y `WAVE3A_YAML_PARSE=PASS`. Los logs estáticos iniciales del 2026-10-06 están en `outputs/.qa/wave3a-portfolio-review/static-guardrails.log` y `yaml-parse.log`. Verifican arquitectura/presencia/cableado, no declaran por sí mismos semántica funcional, PostgreSQL ni navegador. La CI incluye job PostgreSQL aislado, preservación de logs, cabeza 0064 en smoke y un stack Chromium disposable separado del stack normal.

| Ejecución | Fecha Bogotá | Resultado observado | Alcance |
|---|---|---|---|
| Backend focal SQLite | 2026-10-06 | 30 pruebas aprobadas; 246,39 s | Lifecycle, fuentes, historia, acciones, ETag, idempotencia y RBAC |
| SQLite ampliación multimoneda | 2026-10-07 | 1 prueba aprobada; 83,34 s | COP/USD agrupados, NOT_EVALUABLE y STANDALONE/UNCLASSIFIED conservado |
| SQLite cierre scope Allocation | 2026-10-07 | 3 pruebas aprobadas; 131,15 s; 2 warnings cache ACL | Dos casos nuevos de scope/selección y repetición del happy path: 33 casos SQLite únicos acumulados, no 36 |
| SQLite cierre scope Planning Cycle | 2026-10-07 | 3 pruebas aprobadas; 88,71 s | Ciclos globales/ancestrales y rechazo de sibling explícito, inferido, automático y registro legacy; sin nuevos casos únicos |
| Backend regresión cruzada | 2026-10-06 | 63 pruebas aprobadas; 891,29 s | Waves 1/2A, Evaluation, Budget, Resource, Convergence, Gate07J/K, Governance Model y lifecycle Review |
| PostgreSQL 16 funcional | Log Docker recuperado el 2026-10-07 | 31 pruebas aprobadas; 642,10 s | 30 casos focales, incluido hardening de seguridad, y un control schema/dialecto |
| PostgreSQL 16 ampliación multimoneda | 2026-10-07 | 1 prueba aprobada; 89,16 s | COP/USD agrupados, NOT_EVALUABLE y STANDALONE/UNCLASSIFIED conservado |
| PostgreSQL 16 cierre scope Allocation | 2026-10-07 | 3 pruebas aprobadas; 248,19 s | Dos casos nuevos y repetición del happy path: 34 casos PG únicos acumulados en tres ejecuciones |
| PostgreSQL 16 cierre scope Planning Cycle | 2026-10-07 | 3 pruebas aprobadas; 132,37 s | Mismo test ampliado y happy path repetido; 34 casos PG únicos acumulados en cuatro ejecuciones |
| PostgreSQL 16 migración | Log Docker recuperado el 2026-10-07 | 1 prueba aprobada; 51,30 s | Upgrade/down/upgrade real 0064, FK surface 0063 y sentinels preservados |
| Frontend Vitest anterior | 2026-10-06 | 50 pruebas aprobadas; 70,32 s; 7 archivos | API Review, UI/ADMIN Review, blueprint, Allocation y Capital Planning |
| Frontend Vitest cierre | 2026-10-07 | 50 pruebas aprobadas; 37,39 s; 7 archivos | 11 API Review, 10 UI/ADMIN Review, 11 blueprint, 10 Allocation y 8 Capital Planning; reconfirmación final |
| Frontend Vitest código final | 2026-10-07 | 50 pruebas aprobadas; 83,53 s; 7 archivos | Incluye correcciones de Overdue histórico y fechas civiles; repetición de la misma suite, no 50 casos adicionales |
| Frontend typecheck/lint/formato | 2026-10-07 | Todos exit 0 | Comprobados después de la corrección de regex de prueba; sin errores de tipado, lint ni formato |
| Frontend build y formato | 2026-10-07 | Vite PASS en 53,23 s; Prettier PASS | Build de producción; warning de tiempo consumido por plugins CSS, sin error |
| Bundle browser build/preview | 2026-10-07 | Build PASS en 22,46 s; HTTP 5516 sirve preview | Bundle en `/tmp/wave3a-browser-dist`, API 8813 real y código montado en solo lectura |
| Chromium intento 3 parcial | 2026-10-07 | Ruta ADMIN directa aprobada; flujo largo alcanzó timeout global 360 s | Intento histórico sin PASS USER/ADMIN; el recorrido completo aprobó posteriormente con las mismas aserciones |
| Chromium final accesible y sincronizado | 2026-10-07 | 2 pruebas aprobadas; 5,1 min | Dos actores, dos Reviews COMPLETED, tres acciones en la segunda, historia/comparison, ADMIN preview/clone/update/publish/archive y ruta directa denegada |
| Guardrails y YAML | 2026-10-07 | Ambos PASS | Límites arquitectónicos, contrato de 74 secciones/69 criterios y cableado CI/Compose |

La regresión cruzada es reproducible en `outputs/.qa/wave3a-portfolio-review/backend-regressions.log`. La evidencia Docker PostgreSQL está en `postgres-acceptance.log`, `postgres-multicurrency.log`, `postgres-allocation-scope-recheck.log` y `postgres-cycle-scope-verified.log` del mismo directorio; SQLite scope está en `backend-allocation-scope-recheck.log` y `backend-cycle-scope-verified.log`. El cierre frontend incluye `frontend-vitest-verified.log`, `frontend-prettier-verified.log` y `frontend-vite-build-final.log`; su preview está en `frontend-production-preview-build.log`. El despliegue principal final está en `normal-cycle-scope-deploy.log`, `normal-cycle-scope-sql.log`, `normal-cycle-scope-health.log` y `normal-cycle-scope-frontend.log`. Chromium completo USER/ADMIN y la ruta directa aprobaron en `chromium-accessible.log`; sus trazas están en `browser-artifacts-accessible`. Los tiempos de suite no se presentan como tiempos de respuesta de la aplicación.

Finalizada la validación PostgreSQL, se retira únicamente el proyecto Docker efímero `pypmis-wave3a` y su almacenamiento tmpfs; se conservan sus logs, el stack principal y `pypmis-wave3a-browser`. No se eliminan volúmenes o datos del usuario.

Comandos de validación desde la raíz, con Python del entorno backend y Node disponibles:

```text
backend/.venv/Scripts/python.exe scripts/validate_wave3a_release_guardrails.py
cd backend
.venv/Scripts/python.exe -m pytest -o addopts= --no-cov -q tests/test_portfolio_review_wave3a.py
.venv/Scripts/python.exe -m pytest -o addopts= --no-cov -q tests/test_capital_planning_wave1.py tests/test_capital_planning_wave1_rbac_http.py tests/test_capital_allocation_wave2a.py tests/test_portfolio_evaluation_gate07e.py tests/test_portfolio_budget_gate07g.py tests/test_portfolio_budget_gate07g_a.py tests/test_portfolio_resource_gate07h.py tests/test_portfolio_convergence_gate07i.py tests/test_investment_gate_preparation_gate07j.py tests/test_investment_decision_gate07k.py tests/test_project_creation_process.py tests/test_portfolio_review_wave3a.py::test_wave3a_two_actor_lifecycle_snapshot_preview_freeze_idempotency_and_sod
cd ../frontend
npx vitest run src/features/portfolio-review src/features/enterprise-strategy/navigation/strategicNavigationBlueprint.test.ts src/features/capital-allocation src/features/capital-planning
```

La prueba PostgreSQL aislada se ejecuta con `docker compose -p pypmis-wave3a-ci -f docker-compose.wave3a.yml up --build --abort-on-container-exit --exit-code-from wave3a-validation wave3a-validation`. Chromium usa el profile `browser` y URLs 5516/8813, no la base normal de usuario. La CI preserva la evidencia de fallo sin confundir una ejecución local aprobada con un workflow remoto ya ejecutado.

| Criterio | Estado | Evidencia |
|---|---|---|
| Periodic Portfolio Review domain | PASS | SQLite focal: lifecycle de dos actores y read models |
| Review Session stable identity | PASS | Lifecycle: PRV estable y replay de create conserva ID |
| Review tied to Portfolio | PASS | Lifecycle y denegación tenant/workspace de read models |
| Review cadence configurable | PASS | ADMIN clone/effective preview scoped y keys reales; frequency_days publicada |
| Review lifecycle governed | PASS | Lifecycle y return/cancel/supersede idempotentes |
| Completed Review immutable | PASS | Historia/comparison/trends no reinterpretan fuentes live |
| Frozen snapshot | PASS | Preview no persiste; freeze idempotente e inmutable |
| Snapshot source lineage/hashes | PASS | Lifecycle: contract_version, source_index y candidate hash |
| Snapshot staleness | PASS | Membership cambia: STALE, hash anterior intacto y refreeze versionado |
| Portfolio Review not Project Gate | PASS | Semántica request-only y guardrail de autoridad |
| HOLD_FOR_CAPACITY not Gate07K HOLD | PASS | Caso parametrizado: InvestmentDecision intacto y namespace explícito |
| No new Project ranking | PASS | Guardrail AST/patrones; rank pertenece a Evaluation |
| No Portfolio Evaluation mutation | PASS | Cinco acciones: valores de 21 tablas y rank iguales antes/después |
| No Budget mutation | PASS | Semántica request-only y regresión Gate07G/G-A |
| No Resource Scenario mutation | PASS | Semántica request-only y regresión Gate07H |
| No Gate07I mutation | PASS | Semántica request-only y regresión Gate07I |
| No Gate07K mutation | PASS | Semántica request-only y regresión Gate07K |
| No FID creation | PASS | InvestmentDecision completo permanece idéntico tras acciones |
| Wave 2A Allocation reused | PASS | Snapshot source_index y normalizador API Wave 2A |
| Target/current/recommended/approved reused | PASS | Read model Allocation congelado y regresión Wave 2A |
| Bucket variance reused | PASS | Endpoint y test API conserva posiciones agrupadas |
| UNCLASSIFIED exposure preserved | PASS | Caso PG/SQLite COP/USD: unclassified preserva conteo, moneda y NOT_EVALUABLE |
| Portfolio Membership reused | PASS | Snapshot, filtros stale y diferencia histórica de membership |
| Portfolio Rank read-only | PASS | ranking_projection y filas Evaluation intactas |
| Budget read-only | PASS | Comparación de filas antes/después y regresión Budget |
| Resources read-only | PASS | Comparación de filas antes/después y regresión Resource |
| Gate07I read-only | PASS | Comparación de filas Convergence antes/después |
| Gate07J status read-only | PASS | Comparación de InvestmentGatePreparation y regresión 07J |
| Gate07K status read-only | PASS | Comparación de InvestmentDecision y regresión 07K |
| Project Matrix backend-owned | PASS | Lifecycle matriz; API normaliza una sola página backend |
| No UI N+1 | PASS | Vitest filtros/paginación sin consultar proyectos individuales |
| Portfolio conclusions | PASS | Lifecycle crea conclusión; completed rechaza actualización |
| Portfolio Review Actions | PASS | Create/replay/approve/dispatch y cola de acciones |
| Action lifecycle | PASS | Aprobación separada, no bypass por update; follow-up independiente |
| Action owner/due date | PASS | Owner/due persistidos; vencimiento y autorización owner-only |
| Action no silent source mutation | PASS | Cinco acciones comparan valores de 21 tablas autoridad |
| Source-authority adapter boundary | PASS | Guardrail: no comandos fuente; REQUEST_ONLY |
| HOLD_FOR_CAPACITY test | PASS | Semántica parametrizada request-only |
| REQUEST_REASSESSMENT test | PASS | Semántica parametrizada y rank sin cambios |
| REBALANCE_CAPITAL test | PASS | Semántica parametrizada y Budget sin cambios |
| MOVE_BETWEEN_BUCKETS authority test | PASS | Semántica y subject_key/source authority controlados |
| REQUEST_GATE_REVALIDATION authority test | PASS | Semántica parametrizada y Gate/FID sin cambios |
| Review action tracking | PASS | Filtro overdue backend y UI separa follow-up del histórico |
| Period comparison | PASS | Comparación de snapshots con tres/dos memberships |
| Historical snapshots not reinterpreted | PASS | Completion payload/hash/historia inmutables tras mutación fuente |
| Multi-currency no silent aggregation | PASS | PG 1 PASS/89,16 s y SQLite 1 PASS/83,34 s; grouping COP/USD sin FX |
| Standalone/UNCLASSIFIED projects preserved | PASS | Caso ampliado: origen STANDALONE sin Idea, membership y snapshot intactos |
| ADMIN config only | PASS | HTTP 403 config-only en live y Vitest ADMIN sin controles sesión |
| USER live Reviews only | PASS | HTTP 403 preparer en ADMIN y separación API/UI |
| Direct-route security | PASS | Chromium final: ruta ADMIN denegada a USER; HTTP tests tenant/workspace/ETag/RBAC |
| SoD | PASS | Preparador no completa ni creador aprueba su propia acción |
| ETag | PASS | HTTP 412 ETAG_MISMATCH tras update y headers obligatorios |
| Idempotency | PASS | Replay create/freeze/complete/action/approve/dispatch y drift 409 |
| SecurityEvent | PASS | Historia incluye snapshot.frozen y auditoría gobernada |
| Migration reversible | PASS | PostgreSQL DDL 0064 up/down/up: 1 PASS; 51,30 s; sentinels intactos |
| Navigation source of truth | PASS | Guardrail: blueprint único y outlet |
| App.tsx not expanded | PASS | Guardrail: sin tokens/rutas Wave 3A |
| PostgreSQL happy path | PASS | PG16: 34 casos únicos acumulados en cuatro ejecuciones; happy path repetido tras controles de plan y ciclo |
| Browser USER | PASS | Chromium final: dos actores, dos Reviews COMPLETED, tres acciones, historia y comparison |
| Browser ADMIN | PASS | Chromium final: secciones, preview persisted=false, clone scoped, update, publish y archive; sin operaciones live |
| Wave 2A regression | PASS | Siete casos Wave 2A en regresión cruzada 63 PASS |
| Wave 1 regression | PASS | Seis casos Wave 1/RBAC en regresión cruzada 63 PASS |
| Strategic Portfolio regression | PASS | Evaluation/Budget/Resource/Convergence/Gate07J/K y creación multifuente: 63 PASS |
| No Gate07J provider/policy change | PASS | Guardrail: sin provider Review ni comandos Gate |
| No Risk Appetite implementation | PASS | Guardrail STOP scope Wave 3A |
| No Basic Data implementation | PASS | Guardrail STOP scope Wave 3A |
| No QRA implementation | PASS | Guardrail STOP scope Wave 3A |
| No Owner Capability implementation | PASS | Guardrail STOP scope Wave 3A |
| No operational scope | PASS | Revisión read-only del módulo Review; sin ejecución externa |

## 74. Única recomendación del siguiente incremento

**Única recomendación:** implementar Wave 2B — Risk Appetite / Capacity / Thresholds y Basic Data Readiness como el siguiente incremento, porque son dependencias fundacionales para elevar la calidad de evidencia FID, reutilizan policy/readiness/snapshot sin duplicar Wave 3A y reducen el riesgo de introducir QRA o Owner Capability sobre datos todavía incompletos.
