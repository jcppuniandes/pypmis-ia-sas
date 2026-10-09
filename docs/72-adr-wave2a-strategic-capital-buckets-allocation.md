# ADR Wave 2A — Strategic Capital Buckets and Allocation Framework

**Estado:** Aceptado para implementación y validación  
**Fecha:** 2026-10-01  
**Producto:** P&Pmis Construction AI  
**Macroproceso:** Capital Portfolio and Investment Governance  
**Incremento:** Wave 2A — Strategic Capital Buckets and Strategic Capital Allocation Framework

## Decisión

P&Pmis amplía la autoridad de Capital Planning con dos conceptos separados:

1. un catálogo reusable y versionado de `Strategic Capital Bucket`, administrado en ADMIN MODE; y
2. un agregado transaccional `Strategic Capital Allocation Plan`, operado en USER MODE y ligado a un `CapitalPlanningCycle`.

El Bucket expresa una categoría estratégica de agrupación de capacidad de capital. El Allocation Plan expresa intención de distribución por Bucket para un ciclo y un alcance. Ninguno decide qué Project gana, aprueba Budget, asigna Funding, crea un Resource Scenario ni registra FID.

```text
Strategic Objective
  -> Strategic Investment Theme
  -> Capital Planning Cycle
  -> Strategic Capital Demand
  -> Strategic Capital Allocation Plan
  -> Strategic Capital Bucket
  -> Target / Current / Recommended / Approved comparison
```

Investment Origination conserva su cadena independiente:

```text
Capital Demand -> explicit Originate Idea -> Idea -> Business Analysis -> Project Proposal
```

## Baseline y compatibilidad

El incremento parte de Wave 1 validada, con cabeza esperada `20260929_0062`. La implementación es aditiva, conserva una sola cabeza de Alembic y no reescribe la migración 0062. Los cambios locales preexistentes se preservan.

Wave 1 sigue siendo autoridad de Planning Cycle, Strategic Capital Demand, Theme y lineage Demand → Idea. Las Ideas históricas o standalone permanecen válidas. La incorporación de Buckets no cambia la identidad ni el lifecycle de Demand, Idea, Project, Portfolio Membership, Budget Scenario, Resource Scenario, Portfolio Recommendation o Investment Decision.

## Límites de autoridad

| Concepto | Autoridad | Uso en Wave 2A | Mutación permitida |
|---|---|---|---|
| Strategic Objective | Enterprise Strategy | Referencia y validación de alineación | No |
| Strategic Investment Theme | Capital Planning Wave 1 | Mapeo permitido o sugerencia de clasificación | No se duplica |
| Capital Planning Cycle | Capital Planning Wave 1 | Contexto obligatorio del Allocation Plan | Solo por su autoridad existente |
| Strategic Capital Demand | Capital Planning Wave 1 | Posición current demand y clasificación primaria | Solo la cross-classification gobernada |
| Strategic Capital Bucket | Capital Planning ADMIN | Catálogo reusable versionado | Sí, en configuración draft/publicación/archivo |
| Strategic Capital Allocation Plan | Capital Planning USER | Target estratégico y comparación | Sí, mediante lifecycle/revisión |
| Portfolio Membership | Portfolio Planning | Fuente read-only de current portfolio | No |
| Portfolio Evaluation / Rank | Portfolio Evaluation | Contexto read-only | No |
| Budget Scenario | Portfolio Budget | Fuente read-only cuando aplica | No |
| Resource Scenario | Portfolio Resource | Contexto read-only cuando aplica | No |
| Gate07I Recommendation | Portfolio Convergence | Fuente read-only de recommended position | No |
| Gate07K InvestmentDecision | Investment Decision | Fuente read-only de approved position | No |
| Funding / FIN | Sus dominios existentes | Fuera de alcance | No |

Reglas de frontera:

```text
Bucket != Theme
Bucket != Strategic Objective
Bucket != Project Rank
Strategic Allocation != Budget approval
Strategic Allocation != Funding
Strategic Allocation != Resource Scenario
Strategic Allocation != FID
```

## REUSE BEFORE CREATE

Wave 2A reutiliza antes de crear:

| Capacidad existente | Decisión de reutilización |
|---|---|
| `CapitalPlanningCycle` | FK/contexto obligatorio del plan; no segundo calendario. |
| `StrategicCapitalDemand` | Fuente de current demand y denominador de cobertura. |
| Theme configuration | Mapeo Theme → Bucket; no segundo catálogo de Themes. |
| Strategic Objective | Referencia por código/ID; no copia ni mutación. |
| Portfolio Membership | Fuente de Projects activos; no segundo membership. |
| Portfolio Evaluation / Rank | Se consulta sin crear score, rank o winner. |
| Budget Scenario | Se consulta sin crear ni editar scenario/target. |
| Resource Scenario | Se consulta sin crear ni editar capacity/scenario. |
| Gate07I Recommendation | Fuente de recommended position; selección inmutable desde Wave 2A. |
| Gate07K InvestmentDecision | Fuente de approved position; se respetan `is_fid`, `full_funds_authorized` e `investment_authorized`. |
| `AdminConfiguration` | Catálogo, mapping, policy, preview, clone, publish y archive de Buckets. |
| `AdminNumberSequence` | Numeración visible del Allocation Plan. |
| RBAC | Extensión del catálogo de permisos existente, sin nuevo motor. |
| `SecurityEvent` | Auditoría de configuración, lifecycle y clasificación. |
| ETag / If-Match | Concurrencia optimista y error `412 ETAG_MISMATCH`. |
| Idempotency-Key | Reintentos seguros de create, revision, endorse y classify. |
| `strategicNavigationBlueprint.ts` | Única fuente de navegación USER/ADMIN. |
| Currency guardrails | Montos por moneda, sin conversión FX silenciosa. |

Solo se crean agregados persistentes cuando se necesita identidad, lifecycle, inmutabilidad histórica, concurrencia o consulta eficiente. El catálogo Bucket permanece en `AdminConfiguration` mientras esa arquitectura satisface versionado y aplicabilidad.

## Strategic Capital Bucket

Un Bucket es una clasificación estratégica reusable. La configuración publicada puede contener código, nombre, descripción, propósito, orden, vigencia, estado, Themes permitidos, Strategic Objectives permitidos, Governance Models, Project Types, scopes, ciclos aplicables, basis permitidas, reglas min/target/max, tolerancias, política de clasificación, política de `UNCLASSIFIED`, herencia, SoD y numeración.

Los ejemplos Growth, Sustaining Capital, Asset Integrity, Safety / Regulatory u otros no son valores de dominio hardcodeados. Los valores productivos se publican por ADMIN.

Un Bucket publicado o usado se archiva; no se elimina físicamente cuando está referenciado por snapshots históricos.

## Theme, Objective y Bucket

Theme describe la naturaleza estratégica de la necesidad. Bucket describe cómo se agrupa o distribuye capacidad de capital. Un Theme puede mapear a uno, varios o ningún Bucket permitido. El mapeo puede producir una sugerencia; nunca una reasignación opaca.

Strategic Objective continúa bajo Enterprise Strategy. Bucket puede referenciar uno o varios Objectives y validar alineación, pero no los reevalúa ni modifica.

## Aggregate Strategic Capital Allocation Plan

El agregado live contiene, como mínimo:

- identidad técnica y número visible estable;
- `planning_cycle_id` obligatorio;
- scope `ENTERPRISE`, `BUSINESS_UNIT` o `PORTFOLIO`;
- `scope_workspace_id` y `portfolio_id` opcional según scope/policy;
- basis `PERCENTAGE`, `INDICATIVE_AMOUNT` o `PERCENTAGE_AND_AMOUNT` controlada por configuración;
- moneda base opcional, sin implicar conversión FX;
- estado, revisión, ETag y claves idempotentes;
- revisión/hash de configuración y snapshot de policy;
- actor, timestamps, supuestos y constraints;
- líneas target por Bucket;
- snapshot/hash terminal para una revisión endorsed.

Los valores monetarios son strategic planning envelope o target indicativo. La API y la UI deben declarar que no son Approved Budget, executable CAPEX ni Funding Assignment.

## Lifecycle e inmutabilidad

```text
DRAFT -> IN_REVIEW -> ENDORSED
  ^          |
  |          v
  +------ RETURNED

DRAFT/RETURNED -> CANCELLED
ENDORSED -> SUPERSEDED mediante una nueva revisión
```

Un plan endorsed es inmutable. Un cambio material crea una revisión sucesora DRAFT y conserva la versión anterior. El author no puede ejecutar el endorsement final cuando la policy de SoD está activa. Un actor ADMIN no recibe por implicación permisos USER.

## Allocation line y porcentaje

Cada línea representa exactamente un Bucket dentro de la revisión del plan. Puede contener target percentage/amount, minimum/maximum, currency, rationale, Objective links, assumptions, constraints y priority note. No contiene Project IDs.

La validación de porcentaje usa policy explícita. Si la configuración exige 100 %, el backend rechaza otro total. Si permite reserve o partial horizon, el backend aplica esa regla sin normalización silenciosa. Min/target/max son guías estratégicas; no son límites duros de Budget, Funding o contratos.

## Clasificación primaria y no doble conteo

La clasificación de Demand pertenece a Capital Planning y se guarda como cross-reference gobernada en el contexto efectivo del Allocation Plan. Una Demand tiene como máximo un Bucket primario por contexto para impedir contar el 100 % de su Indicative Capital Need en múltiples Buckets.

La fuente puede ser:

- clasificación manual;
- default derivado de Theme; o
- sugerencia derivada por regla.

La respuesta expone source y rationale. `UNCLASSIFIED` es un resultado explícito y siempre permanece en el denominador. La cobertura usa cantidad de Demands elegibles y, cuando es evaluable, exposición monetaria por currency. La policy decide si una cobertura insuficiente bloquea endorsement o produce warning.

Para Projects standalone o históricos se usa una cross-classification explícita de Project Workspace o Portfolio Membership cuando no existe lineage resoluble. Bucket no se agrega a la identidad de `EnterpriseWorkspace`.

## Precedencia de clasificación

El backend es la única autoridad de resolución y aplica orden determinista:

1. clasificación explícita y gobernada del contexto Project/Portfolio;
2. clasificación primaria de la Strategic Capital Demand de origen;
3. default permitido por Theme-to-Bucket;
4. `UNCLASSIFIED`.

Una sugerencia nunca reemplaza silenciosamente una clasificación explícita. La comparación expone la fuente usada, la versión y la razón.

## Read model canónico de comparación

Una única operación backend agrega, por Bucket:

| Posición | Fuente autoritativa | Semántica |
|---|---|---|
| TARGET | Allocation Plan actual | Intención estratégica. |
| CURRENT_DEMAND | Demands elegibles según policy | Pipeline de necesidad indicativa. |
| CURRENT_PORTFOLIO | Portfolio Membership + lineage/cross-classification | Posición live de cartera. |
| RECOMMENDED | Gate07I / scenario recommendation existente | Recomendación, no aprobación. |
| APPROVED | Gate07K con autoridad real de capital | Inversión formalmente autorizada. |

Approved incluye únicamente decisiones cuya semántica representa autorización. Un `PYP-INV-SELECT + GO` no equivale a full approved capital. Para `PYP-FFA + GO` se reutilizan `is_fid`, `full_funds_authorized` e `investment_authorized`.

La respuesta expone target, current demand, current portfolio, recommended, approved, variance contra target, estado derivado, drilldown y lineage. El drilldown es read-only y no se convierte en editor de ranking.

## Currency y estado derivado

No se calculan porcentajes ni totales que mezclen monedas incompatibles. Sin una normalización gobernada, los montos se agrupan por currency y el estado es `NOT_EVALUABLE` para cualquier comparación que requiera consolidación. No se inventan tasas FX.

Los estados derivados permitidos son `UNDER_TARGET`, `WITHIN_RANGE`, `OVER_TARGET`, `UNCLASSIFIED_EXPOSURE` y `NOT_EVALUABLE`. Solo describen balance estratégico; no expresan readiness de Project, Gate decision, Budget compliance ni Funding compliance.

## Source-current, staleness y snapshot histórico

El plan endorsed congela identidad y versión, Cycle, scope, Bucket definitions, targets, configuración/hash, policy de clasificación, supuestos, source context y comparación disponible. La evolución posterior del catálogo no reinterpreta el snapshot.

Un cambio material de configuración puede marcar la vista actual como `STALE` y exigir una nueva revisión. `Refresh Preview` es read-only y devuelve `persisted=false`; muestra deltas de Bucket, clasificación, target y posiciones. `Apply` crea una revisión DRAFT y nunca muta un plan endorsed.

## Readiness ligero

Wave 2A puede derivar `BUCKET_COVERAGE`, `TARGET_ALLOCATION`, `CLASSIFICATION_COVERAGE`, `CURRENCY_EVALUABILITY`, `STRATEGIC_ALIGNMENT` y `OVERALL_ALLOCATION_PLAN_READINESS`. Esta lectura no se registra como provider Gate07J y no cambia la evidence policy publicada.

## RBAC, concurrencia, idempotencia y auditoría

Permisos de dominio esperados:

```text
capital_planning.allocation.read
capital_planning.allocation.create
capital_planning.allocation.edit
capital_planning.allocation.submit
capital_planning.allocation.review
capital_planning.allocation.endorse
capital_planning.bucket.classify
capital_planning.admin.bucket.configure
capital_planning.admin.bucket.publish
```

El backend valida permisos incluso por acceso directo a rutas. Las mutaciones usan `If-Match`; una revisión obsoleta devuelve `412 ETAG_MISMATCH`. Create Plan, new revision, endorse y classify Demand/Project context usan `Idempotency-Key` y no duplican registros ante retries.

`SecurityEvent` registra tenant, actor, acción, target, versión, outcome y detalle mínimo para configuración, lifecycle, clasificación y revisión. La auditoría no reemplaza snapshots de negocio.

## Persistencia y migración

La persistencia live puede usar `StrategicCapitalAllocationPlan`, líneas/versiones y cross-classifications, según el diseño final inspeccionado. Los snapshots JSON/hashes preservan historia; las tablas normalizadas preservan integridad, lifecycle e índices para agregación. El catálogo Bucket reutiliza `AdminConfiguration`.

La migración Wave 2A debe ser sucesora única de `20260929_0062`, aditiva, reversible, sin backfill destructivo y verificable `up -> down -> up` en PostgreSQL y SQLite cuando el repositorio lo soporta. Los índices cubren tenant, Cycle, scope, status, Bucket, Demand/Project context y consultas de posición.

## Navegación

`frontend/src/features/enterprise-strategy/navigation/strategicNavigationBlueprint.ts` permanece como fuente única de verdad.

```text
USER MODE
-> Enterprise Strategy Manager
-> Strategic Capital Planning & Demand
   -> Planning Cycles
   -> Capital Demand Pipeline
   -> Strategic Capital Allocation
   -> Allocation History
```

```text
ADMIN MODE
-> Enterprise Strategy Manager
-> Strategic Capital Planning & Demand Configuration
   -> Strategic Capital Buckets
```

La UI USER no presenta publish/archive de configuración; la UI ADMIN no presenta create/submit/endorse de planes live. `App.tsx` no recibe routing o lógica Wave 2A; el outlet estratégico consume el blueprint.

## Contrato futuro Periodic Portfolio Review

Wave 2A prepara un contrato estable, pero no implementa Review:

```text
allocation_plan_id
allocation_plan_number
allocation_plan_revision
allocation_plan_hash
planning_cycle_id
scope
bucket_configuration_revision/hash
bucket_definition_snapshot
target_allocation_snapshot
current_portfolio_position_snapshot
recommended_position_snapshot
approved_position_snapshot
variance_snapshot
unclassified_exposure
source_as_of
```

Periodic Portfolio Review podrá congelar ese contrato sin recalcular o mutar un plan histórico. No se crean Review Session, Review Action ni un lifecycle de Review en Wave 2A.

## Exclusiones y STOP boundary

Wave 2A no implementa Periodic Portfolio Review, Risk Appetite/Capacity/Thresholds, Basic Data Readiness, QRA/Confidence, Owner Capability Readiness, Gate07J provider/policy changes, Budget optimization, Portfolio optimizer, un nuevo ranking, Funding, FIN, Procurement, Project Delivery, Operational Readiness ni Benefits Realization.

Tampoco muta Portfolio Rank, Budget Scenario, Resource Scenario, Gate07I Recommendation o Gate07K InvestmentDecision.

## Consecuencias

La organización obtiene una intención de asignación estratégica versionada y puede compararla con pipeline, Portfolio, recommendation y approved capital sin convertir esa intención en una decisión transaccional de otros dominios. El costo es un agregado adicional con snapshots, clasificación contextual, agregación cross-domain y controles de vigencia. La separación de autoridad evita duplicar los motores maduros de evaluación, escenario y decisión.

## Criterio de release

El release solo puede usar el estado exclusivo solicitado cuando hayan pasado migración reversible, happy path PostgreSQL, pruebas negativas, regresiones, guardrails, frontend, Chromium USER y ADMIN, ETag, idempotencia, SoD, auditoría y ausencia de side effects. Un requisito no ejecutado permanece `NO VALIDADO` y bloquea el estado final.

