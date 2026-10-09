# ADR Wave 3A — Periodic Portfolio Review and Governance Cycle

**Estado:** Aceptado para implementación y validación  
**Fecha de revisión:** 2026-10-07 (America/Bogota)  
**Producto:** P&Pmis Construction AI  
**Macroproceso:** Capital Portfolio and Investment Governance  
**Incremento:** Wave 3A — Periodic Portfolio Review and Governance Cycle

## Decisión

P&Pmis incorpora un agregado gobernado `PortfolioReviewSession` para representar una revisión periódica formal de un portafolio específico. La sesión congela evidencia de contexto, registra conclusiones y administra acciones de gobierno, pero no sustituye las autoridades que originan la información consumida.

La capacidad se separa en dos superficies:

- **ADMIN MODE:** política reusable de tipos, cadencia, agenda, fuentes obligatorias, freshness, readiness, conclusiones, acciones, umbrales, autoridad, SoD, numeración, herencia y publicación.
- **USER MODE:** sesiones live, snapshot preview/freeze, revisión, conclusiones, acciones, cierre, historia, comparación y tendencias.

La navegación se deriva exclusivamente de `strategicNavigationBlueprint.ts`. Las rutas USER se ubican bajo `/app/strategy/portfolio-review-*` y la ruta ADMIN bajo `/app/admin/strategy/portfolio-review-configuration`.

## Posición en el proceso

Wave 3A pertenece a la fase 4, Portfolio Planning & Review, y opera como ciclo recurrente:

```text
Strategic Capital Planning & Demand
→ Strategic Capital Allocation
→ Investment Origination & Shaping
→ Strategic Gate
→ Portfolio Intake / Evaluation / Prioritization
→ Portfolio Analysis and Scenarios
→ Portfolio Recommendation
→ Periodic Portfolio Review
↺ recurring governance cycle
```

No es una nueva transición de madurez de proyecto ni un Project Gate.

## Frontera de autoridad

```text
Portfolio Review
= gobierna el portafolio como conjunto
= congela contexto y linaje
= registra conclusiones y solicitudes
= hace seguimiento a acciones

Portfolio Review
≠ recalcula score o rank
≠ crea escenarios Budget o Resource
≠ decide GO / HOLD / RECYCLE / KILL
≠ emite FID
≠ modifica Business Case, FEL/PDRI, FIN, Funding, Risk o Permit
```

`HOLD_FOR_CAPACITY` es una acción de gobierno de portafolio. No es ni genera `Gate07K HOLD`. `REQUEST_REASSESSMENT` no recalcula ranking. `REBALANCE_CAPITAL` no edita un Budget Scenario. `MOVE_BETWEEN_BUCKETS` y `REQUEST_GATE_REVALIDATION` permanecen como solicitudes salvo que exista un adaptador explícito, autorizado e idempotente hacia el servicio dueño.

## Matriz de autoridad

| Capacidad | Autoridad fuente | Consumo Wave 3A | Escritura desde Review |
|---|---|---|---|
| Portfolio Membership | Portfolio Planning | Proyectos activos y alcance | No |
| Evaluation / Rank | Portfolio Evaluation | Rank y staleness | No |
| Investor Map / Scorecard | Portfolio Analysis | Resumen histórico | No |
| Allocation Plan / Buckets | Capital Planning Wave 2A | Target, current, recommended, approved, variance y unclassified | Solo adaptador explícito; por defecto no |
| Budget Scenario | Portfolio Budget | Escenario seleccionado, waterline y factibilidad | No |
| Resource Scenario | Portfolio Resource | Capacidad, overloads y factibilidad | No |
| Recommendation | Gate07I / Portfolio Convergence | Alternativa y hash recomendados | No |
| Gate preparation | Gate07J | READY, BLOCKED o STALE | No |
| Investment Decision / FID | Gate07K | Decisión formal, condiciones y FID | No |
| Portfolio Review | Wave 3A | Sesión, snapshot, conclusiones y acciones | Sí, dentro de su agregado |

## REUSE BEFORE CREATE

La solución reutiliza `PortfolioProjectMembership`, `PortfolioProjectEvaluation`, servicios de análisis, Budget, Resource, Convergence, Gate07J, Gate07K y el contrato de snapshot de Wave 2A mediante adaptadores de lectura. Reutiliza además `AdminConfiguration`, `AdminNumberSequence`, RBAC, `SecurityEvent`, ETag/If-Match, idempotencia y el blueprint de navegación estratégico.

Solo se crean cuatro conceptos persistentes cuando identidad, lifecycle, historia o consulta eficiente lo exigen:

- `PortfolioReviewSession`;
- `PortfolioReviewSnapshot` inmutable y con hash;
- `PortfolioReviewConclusion`;
- `PortfolioReviewAction`.

La configuración permanece en `AdminConfiguration`; no se crea tabla por sección de agenda, fuente ni tipo de acción.

## Lifecycle e inmutabilidad

```text
DRAFT → PREPARING → READY_FOR_REVIEW → IN_REVIEW → COMPLETED
READY_FOR_REVIEW / IN_REVIEW / STALE → RETURNED
Sesión no terminal → CANCELLED
Sesión no terminal → SUPERSEDED (sucesora explícita)
```

Un `COMPLETED` es inmutable. Las correcciones requieren una nueva sesión o sucesora. Las acciones pueden continuar abiertas después del cierre de la revisión; cierre de sesión y cierre de acciones son lifecycles distintos.

La sesión usa número visible estable `PRV-######`, `revision_version`, ETag e idempotencia. Cuando la política SoD está activa, el preparador no puede ser autoridad final. Return/cancel/supersede son comandos gobernados con reason; acciones de reviews CANCELLED/SUPERSEDED no admiten cambios. Solo se soporta autoridad individual `SINGLE_PORTFOLIO_AUTHORITY`, quorum 1 y `NOT_REQUIRED` voting; modelos comité/votación se rechazan explícitamente.

## Snapshot y staleness

El snapshot persiste JSON estructurado, un índice de referencias, hashes de fuentes, `as_of` y hash canónico. Reutiliza el contrato Wave 2A y añade referencias a Membership, Rank, Investor Map/Scorecard, Budget, Resource, Convergence, Gate07J, Gate07K y readiness.

Antes de `READY_FOR_REVIEW` se valida existencia, compatibilidad de portfolio/ciclo/plan/escenario, versión/hash y `source_current`. Fuentes requeridas ausentes/stale bloquean; fuentes opcionales ausentes generan warnings. La policy define freshness y contexto mínimo. Un cambio material posterior puede marcar una sesión live como `STALE` sin modificar el payload congelado. `snapshot-preview` es `persisted=false`; freeze crea una nueva versión de snapshot solo cuando el lifecycle lo permite.

La compatibilidad de Planning Cycle se comprueba incluso sin Allocation Plan, y cuando se infiere el ciclo de un plan explícito o automático. Su scope puede ser global o ancestral respecto del portafolio, pero no sibling; un grant de lectura directo al ancestor no es necesario para esa referencia compatible. La construcción del snapshot revalida el linaje de sesiones existentes. Los rechecks de opciones, selección y happy path aprobaron en SQLite y PostgreSQL tras este control; no se modifican autoridades fuente.

Los históricos, la comparación período contra período y las tendencias leen snapshots congelados; nunca reinterpretan una revisión cerrada con reglas o fuentes live.

## Acciones y dispatch

`PortfolioReviewAction` registra sujeto, tipo, rationale, prioridad, owner, vencimiento, estado, evidencia y autoridad solicitada. Su lifecycle es `OPEN → ACCEPTED → IN_PROGRESS → COMPLETED`, con `REJECTED` y `CANCELLED` controlados.

En esta implementación el dispatch es exclusivamente `REQUEST_ONLY`: registra `REQUEST_RECORDED`, referencia local `PORTFOLIO_REVIEW_REQUEST:...` y `external_execution=false`. No se habilita ejecución externa. Un futuro adaptador exigiría operación gobernada fuente y permisos separados; nunca escritura directa en tablas externas. Las operaciones de comandos persistidas usan idempotencia y los cambios generan `SecurityEvent`.

## Read models

El backend compone read models que evitan llamadas del navegador por cada proyecto:

- resumen agregado del portafolio;
- Project Matrix paginada y filtrable;
- allocation, budget/resources y Gate/FID read models;
- cola de acciones por estado, owner, proyecto, bucket y revisión;
- comparación con la revisión completada anterior;
- tendencias basadas solo en datos observados.

Los montos multimoneda se agrupan por moneda. Sin una normalización gobernada, el total consolidado es `NOT_EVALUABLE`; no hay FX silencioso.

## Persistencia y migración

La migración aditiva `20261005_0064` sucede a `20261001_0063` y añade session/snapshot/conclusion/action más el ledger `portfolio_review_commands` para idempotencia. No modifica tablas de Portfolio Evaluation, Budget, Resource, Convergence, Gate07J, Gate07K ni Wave 2A. Su prueba reversible PostgreSQL ejecuta upgrade/down/upgrade sobre una superficie mínima de claves externas de 0063 y filas sentinel; no reconstruye la cadena histórica completa. La suite funcional usa metadata actual en otra base efímera y no confunde `stamp head` con migraciones ejecutadas.

El stack Chromium también es disposable y separado de la base principal. Sirve el bundle frontend compilado mediante preview desde `/tmp/wave3a-browser-dist`, manteniendo el bind del código en solo lectura, API real 8813 y validation mode desactivado. El cambio elimina transformaciones dev/HMR del recorrido de release, no cambia permisos ni aserciones. La CI espera readiness hasta 300 s con cada probe curl limitado a 10 s; estos presupuestos de arranque no son SLA del producto.

## Seguridad

Se introducen permisos separados de lectura, creación, preparación, freeze, submit, conduct, complete, creación/aprobación/actualización de acciones y configuración/publicación ADMIN. Ser ADMIN no concede operaciones USER y viceversa. Las rutas directas deben negar:

- acceso ADMIN sin configuración;
- mutación live para actor config-only;
- aprobación de acción sin permiso;
- dispatch sin permiso de adaptador.

## Consecuencias

La organización obtiene evidencia reproducible y comparable de cada revisión, con trazabilidad de acciones y separación estricta de autoridad. La contrapartida es el costo de mantener adaptadores de lectura y políticas de freshness para varias fuentes. Este costo es preferible a duplicar cálculos o reinterpretar históricos.

La cadencia usa frecuencia publicada y scope jerárquico, no reglas automáticas por capital/riesgo/importancia. Las reglas de ownership son controles de autorización activos, no un motor configurable. PortfolioResourceService se reutiliza solo para su lectura `scenario()`. La evidencia de ejecución y los límites pendientes se registran en el informe de release; este ADR no constituye una declaración PASS.

## Fuera de alcance

No se implementan ranking u optimización nuevos, Risk Appetite/Capacity/Thresholds, Basic Data Readiness, QRA/Confidence, Owner Capability Readiness, cambios de Gate07J, Procurement, Project Delivery, Operational Readiness ni Benefits Realization.
