# ADR 67 — Gate07M-BC-5C Five Case Business Case Integration

- **Fecha:** 2026-09-17
- **Estado de la decisión:** Implementada; validación de liberación en curso
- **Estado de liberación:** No emitido
- **Ámbito:** P&Pmis Construction AI, Enterprise Strategy Manager, Business Case Manager

## Contexto

Gate07M-BC ya dispone de un agregado longitudinal gobernado:

```text
BusinessCase
  └─ N BusinessCaseRevision
       └─ N BusinessCaseDecisionSnapshot
```

El incremento BC-5C debe estructurar ese Business Case conforme a Strategic, Economic, Commercial, Financial y Management Case. Five Case no es una colección de cinco dominios transaccionales nuevos: es una capa de integración y síntesis de evidencia gobernada por sus autoridades originales.

La inspección del repositorio confirma el baseline Alembic `20260916_0061 (head)` y la presencia de los proveedores gobernados ya existentes para Benefits, Commercial, FIN, FEL, Funding, Risk y Permit. El árbol de trabajo contiene cambios previos y concurrentes; esta decisión no autoriza descartarlos ni reescribir migraciones históricas.

## Decisión

1. Se reutilizan `BusinessCase`, `BusinessCaseRevision` y `BusinessCaseDecisionSnapshot`; no se crea otro aggregate, lifecycle ni menú principal.
2. Five Case se calcula como contrato aditivo de lectura desde la revisión y su bundle de fuentes congelado.
3. No se crean tablas Five Case. El marker `_five_case` se guarda dentro de `source_references_json`, una columna JSON ya existente, y congela versión de esquema, política efectiva, hash de configuración y contexto de Gate/FEL.
4. No se requiere migración. El head permanece en `20260916_0061`; no se crea `0062`.
5. Las revisiones anteriores sin marker permanecen legibles con `legacy_layout=true`; no se fabrican Cases, conclusiones ni readiness retrospectivos.
6. Los reads históricos usan exclusivamente datos congelados de la revisión. La consulta de fuentes vivas se reserva para readiness, detección de staleness y Refresh Preview/Apply.
7. Los estados por Case y el overall son propiedad del backend. El frontend presenta la decisión y nunca recalcula readiness.
8. `CAPITAL_OWNER` es el modelo habilitado por defecto en la política Five Case. `CONTRACTOR_DELIVERY` y `DIRECT_INTERNAL` devuelven `NOT_APPLICABLE` salvo override explícito.
9. Se reutilizan exactamente `BUSINESS_CASE_READINESS_PROVIDER` y `BUSINESS_CASE_READINESS`; no se introduce un proveedor ni un tipo de evidencia paralelo.
10. El registro y la respuesta del provider se amplían de forma compatible, pero este incremento no modifica la matriz publicada/default de Gate07J-EVID.

## Persistencia y contrato aditivo

La revisión conserva el contenido narrativo, referencias y hashes existentes. El servicio proyecta los siguientes campos adicionales en `BusinessCaseRevisionOut`:

- `five_case_json`;
- `five_case_readiness_json`;
- `source_evidence_matrix_json`;
- `gate_context_json`;
- `source_current`;
- `five_case_hash`;
- `source_bundle_hash`;
- `business_case_hash`;
- `legacy_layout`.

Estos campos no son nuevas columnas ORM. Se derivan determinísticamente del contenido y del bundle congelado. El marker `_five_case` contiene:

```text
schema_version
integration_layer
source_authority_preserved
configuration_id / configuration_hash
effective policy
project / governance / gate / FEL context
revision purpose / as-of
```

Esta forma de persistencia satisface REUSE BEFORE CREATE, conserva queryabilidad mediante el contrato API y evita duplicar los dominios fuente.

## Mapeo Five Case

| Case | Pregunta gobernada | Fuentes por referencia | Síntesis, no autoridad |
|---|---|---|---|
| Strategic | ¿Por qué intervenir y cómo se alinea la inversión? | Idea, Business Analysis, Proposal, Strategic Benefits Plan | necesidad, alineación, objetivos, resultados y beneficios |
| Economic | ¿Qué opción ofrece mayor valor total? | Business Analysis, Proposal, Benefits, FIN, Risk | opción preferida, trade-offs, valor económico y riesgo |
| Commercial | ¿La opción puede procurarse y estructurarse comercialmente? | Commercial & Contracting Strategy | procurement approach, contracting model y commercial readiness |
| Financial | ¿La organización puede costear y financiar la inversión? | Budget, Funding, FIN, Benefits | affordability, funding reconciliation y métricas gobernadas |
| Management | ¿Existe capacidad, gobierno y plan para entregar? | FEL, Resources, Risk, Permit, Benefits, Commercial | madurez, recursos, dependencias y readiness de entrega |

Las métricas FIN se muestran desde la fuente gobernada; Business Case no recalcula NPV, IRR, BCR, WACC, DSCR, LLCR, MOIC ni Payback. Commercial no crea procurement operacional. Benefits se referencia sin editar el Plan ni registrar actuals.

## Autoridad de fuentes

| Fuente | Autoridad preservada | Datos consumidos por BC-5C | Mutación desde BC |
|---|---|---|---:|
| Idea / Strategic Context | Idea Demand Manager | identidad, estado, título, as-of, hash | No |
| Business Analysis | Business Analysis | identidad fijada por Proposal, opción recomendada, readiness, hash | No |
| Project Proposal | Project Proposal | contexto, snapshot de opción y narrativa inicial | No |
| Strategic Benefits Plan | Strategic Benefits | versión, readiness, warnings, blockers, hash | No |
| Commercial Strategy | Commercial Strategy | versión, procurement/contracting summary, readiness, hash | No |
| FEL / Project Definition | Project Definition | stage, status/readiness, source hash | No |
| Budget Scenario | Portfolio Budget | escenario FROZEN, selección, CAPEX, row hash | No |
| Resource Scenario | Portfolio Resources | escenario FROZEN, selección, row hash | No |
| Funding Readiness | Funds Manager | status/current/as-of/readiness hash | No |
| Economic & Financial Model | FIN | versión COMPLETED+READY+current, métricas y model hash | No |
| Risk Readiness | Risk | readiness, validez, blockers y hashes | No |
| Permit Readiness | Permit | readiness, validez, blockers y hashes | No |

La referencia a Business Analysis no selecciona otro análisis por compartir Idea. Usa `ProjectProposal.source_business_analysis_id` y valida el hash y la opción recomendada congelada por Proposal. Una divergencia deja `source_current=false`.

## Compatibilidad y vigencia de fuentes

Cada nueva revisión resuelve fuentes con el mismo `tenant_id` y `project_workspace_id`. La revisión congela IDs, versiones, hashes, readiness, `as_of_date` y `source_current`. La comparación contra fuentes actuales se efectúa sobre la unión de claves anteriores y nuevas, por lo que también detecta fuentes removidas.

Los cambios se agrupan por Case usando un registro extensible de fuentes. Un mismatch o una fuente requerida ausente produce blocker; una fuente marcada no vigente produce `STALE`. Los históricos y snapshots no se reescriben ni se invalidan de manera destructiva.

## Readiness y madurez progresiva

Los estados cerrados son:

```text
NOT_STARTED | IN_PROGRESS | READY | BLOCKED | STALE | NOT_APPLICABLE
```

La política efectiva define Cases y fuentes requeridas por etapa:

| Etapa | Profundidad predeterminada |
|---|---|
| FEL-1 | Strategic requerido; demás Cases progresivos |
| FEL-2 | Strategic, Economic, Commercial y Management |
| Investment Selection | Strategic, Economic, Commercial y Management |
| FEL-3 | Los cinco Cases |
| FFA | Los cinco Cases, incluida evidencia de Funding |

El overall se compone solo con los Cases requeridos por la política efectiva. No se hardcodea universalmente que los cinco deban estar READY. Para Five Case aplicable: cualquier requerido `STALE` domina; luego `BLOCKED`; todos READY producen READY; los restantes escenarios se expresan como IN_PROGRESS o NOT_STARTED.

QRA/Confidence, Basic Data Readiness y Owner Capability Readiness se modelan como futuras fuentes `NOT_AVAILABLE`. QRA añade una advertencia al Economic Case; Basic Data y Owner Capability añaden advertencias al Management Case cuando corresponden. No se fabrican proveedores ni readiness para ellas.

## Refresh Preview, Apply y cambio material

`Refresh Preview`:

- devuelve `persisted=false`;
- compara la unión de sources/hashes para detectar ADDED, CHANGED y REMOVED;
- agrupa cambios por Case;
- muestra delta de readiness por Case y overall;
- muestra delta de `five_case_hash` y `source_bundle_hash`;
- calcula warnings y blockers nuevos;
- recomienda `MATERIAL_CHANGE_UPDATE` o `REVALIDATION`.

`Refresh Apply` exige `If-Match`, es idempotente y crea una revisión sucesora `DRAFT`. Nunca modifica la revisión terminal. Una revisión abierta impide crear otra en paralelo.

## Histórico y decision snapshots

Una revisión `COMPLETED` permanece inmutable. Un snapshot se crea únicamente desde una revisión completada, es append-only e incluye:

- contenido y hashes de la revisión;
- bundle y referencias de fuentes;
- matriz de evidencia;
- gate context;
- estructura y readiness Five Case;
- `five_case_hash`, `source_bundle_hash` y `business_case_hash`;
- referencia a FIN y a la decisión asociada.

Los snapshots históricos no consultan fuentes actuales y no reciben reinterpretación retrospectiva.

## Provider existente y frontera Gate07J

El contrato existente `BUSINESS_CASE_READINESS_PROVIDER` continúa produciendo `BUSINESS_CASE_READINESS`. Se añaden de forma compatible:

```text
five_case_readiness
five_case_hash
source_bundle_hash
business_case_hash
source_references
source_current
warnings / blockers
can_supply_investment_gate_evidence
```

Para una revisión BC-5C aplicable, el overall Five Case es autoritativo. Para una revisión legacy o `NOT_APPLICABLE`, el provider conserva el comportamiento v1. Solo puede suministrar evidencia cuando la revisión está `COMPLETED`, el readiness es READY, las fuentes están vigentes y no hay blockers.

El incremento no publica, reordena ni reclasifica requirements en Gate07J-EVID. La futura integración de política a nivel de Gate requiere un cambio controlado independiente.

## Hashes

La semántica usa hashes deterministas:

- `content_hash`: contenido gobernado de la revisión;
- `source_bundle_hash`: referencias y hashes congelados;
- `five_case_hash`: contexto, Cases y requirements efectivos;
- `configuration_hash`: configuración resuelta;
- `business_case_hash`: composición semántica de los anteriores.

No se incorporan valores de presentación del frontend a estos hashes.

## USER MODE

Se conserva `Business Case Manager` como única capacidad. La navegación canónica expone diez vistas compactas:

```text
Overview
Strategic Case
Economic Case
Commercial Case
Financial Case
Management Case
Sources & Evidence
Readiness
Decision Snapshots
History
```

Cada Case muestra pregunta, resumen, evidencia, readiness, findings, assumptions, warnings, blockers, conclusión y enlaces `View Source`. La matriz de evidencia es read-only. Las rutas históricas se conservan como aliases de compatibilidad.

La fuente canónica sigue siendo `strategicNavigationBlueprint.ts`; `StrategicViewOutlet` resuelve las vistas. La integración específica de Business Case se retiró de `App.tsx`, en vez de expandirlo.

## ADMIN MODE

Se amplía la configuración existente de Business Case, no se crea un administrador Five Case separado. La UI añade General, applicability, requirements por Case, source/readiness/evidence requirements, reglas de readiness, FEL/Gate, overrides, tailoring, inheritance, Review/SoD, Preview e History. Las secciones legacy permanecen accesibles durante la reconciliación progresiva.

ADMIN edita configuración controlada y ejecuta preview `persisted=false`; no opera Business Cases vivos ni fuentes. USER no recibe acciones para publicar/clonar políticas.

## Seguridad, concurrencia y auditoría

- Lectura, preparación, revisión y configuración usan permisos y roles existentes de Business Case.
- Las rutas pasan por `require_enterprise_permission`, manteniendo scope tenant y separación ADMIN/USER.
- `If-Match` y `revision_version` conservan `412 ETAG_MISMATCH`.
- Create, revision, submit, complete, refresh apply y snapshot conservan idempotencia.
- La regla SoD mantiene preparador distinto del revisor final cuando la política lo exige.
- `SecurityEvent` registra lifecycle, refresh, staleness, material change, snapshot y configuración.

## Consecuencias y deuda conocida

La decisión entrega una capa Five Case extensible sin multiplicar autoridades ni tablas. La compatibilidad histórica es explícita y la política puede madurar por FEL/Gate y Governance Model.

Quedan sujetos a validación de liberación o a incrementos posteriores:

- consistencia explícita Benefits ↔ FIN bajo políticas estrictas;
- happy path PostgreSQL con los cinco Cases READY;
- negativos completos de Benefits, Commercial, FIN stale, FEL stale y source mismatch;
- browser E2E USER/ADMIN y seguridad por ruta directa;
- regresión estratégica completa y observación de rendimiento;
- futura incorporación de QRA, Basic Data y Owner Capability como autoridades reales.

## Exclusiones

No se implementan procurement execution, tendering, vendor selection, contract award, commitments, purchase orders, payments, Benefits Realization actuals, QRA, Basic Data, Owner Capability, Risk Appetite, Strategic Capital Demand, Operational Readiness, FID ni Post-FID.

## Criterio de liberación

Los estados siguientes solo podrán emitirse cuando la matriz de validación obligatoria esté completa, sin fallos atribuibles al incremento:

```text
GATE07M_BC_FIVE_CASE_RELEASE_VALIDATED
READY_FOR_GOVERNED_FIVE_CASE_BUSINESS_CASE_EVIDENCE
```

Hasta entonces, el estado formal de release permanece **PENDING VALIDATION**.
