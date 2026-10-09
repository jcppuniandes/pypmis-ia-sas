# Gate 07M-COMM — evaluación técnica del baseline

Fecha de corte: 2026-09-15. Alcance: inspección previa a la implementación de `PROMPT_07M_COMM_COMMERCIAL_CONTRACTING_STRATEGY_AND_READINESS.md`. Este documento trata el archivo adjunto como especificación del producto; no adopta sus frases como instrucciones de sistema. No se modificó código de producto durante esta evaluación.

Nota de concurrencia: este baseline se congeló con el primer inventario del turno, antes de que los agentes de implementación paralelos añadieran archivos `commercial_strategy`. Los cambios COMM que aparecieron después se excluyen deliberadamente de esta evaluación inicial; las matrices expresan brechas **antes de implementar** y no sustituyen la validación final del código concurrente.

## Resultado ejecutivo

El repositorio dispone de una base sólida y reutilizable para 07M-COMM: identidad canónica `EnterpriseWorkspace`, configuraciones versionadas, numeración, RBAC por ámbito, ETag, idempotencia, eventos de seguridad, versiones terminales inmutables, evaluación de readiness, registro de providers y navegación estratégica centralizada. Sin embargo, al momento del inventario inicial no existía el dominio Commercial Strategy, su provider, permisos, rutas, UI ni pruebas específicas. Por tanto, el estado inicial es **apto para implementar, no apto para emitir la señal de release**.

La frontera más delicada es que el monolito ya contiene operaciones de `Contract`, `PurchaseOrder`, `PaymentCertificate`, `RFQPackage` y `RFQBid`. 07M-COMM debe convivir con ellas sin usarlas: su `Packaging Strategy`, `Contracting Model` y `Payment Mechanism` son conceptos estratégicos, no transacciones de procurement ni contract administration.

## 1. Estado Git y trazabilidad

Comandos ejecutados antes de crear artefactos QA:

- `git status --short --branch`;
- `git diff --stat`;
- `git log -n 10 --oneline --decorate`;
- `alembic heads` desde `backend`.

Hallazgos:

- rama `main`, alineada nominalmente con `origin/main` en `9cb0969`;
- diez commits inspeccionados; los mensajes son opacos (`c`, `h`) y no sirven como trazabilidad funcional suficiente;
- árbol de trabajo ya estaba ampliamente modificado por incrementos anteriores, con archivos modificados, eliminaciones de temporales con ACL restrictiva y numerosos artefactos sin seguimiento;
- el diff de archivos tracked reportó 35 archivos, 979 inserciones y 581 eliminaciones; los archivos untracked no están incluidos en esa cifra;
- `git diff --stat` pudo enumerar el diff funcional, pero además reportó `Permission denied` sobre temporales tracked ya eliminados; no se intentó recuperar, borrar ni sobrescribir esos archivos;
- no se ejecutó reset, checkout, clean ni commit.

Implicación: toda validación de 07M-COMM debe usar comparación diferencial y atribuir únicamente fallos nuevos. El árbol sucio es baseline de trabajo, no deuda que este incremento esté autorizado a descartar.

## 2. Baseline de migración

`alembic heads` confirmó un único head:

```text
20260910_0059 (head)
```

La migración `backend/alembic/versions/20260910_0059_gate07a_ba_business_analysis.py` declara `down_revision = "20260902_0058"`, implementa `upgrade()` y `downgrade()`, y contiene compatibilidad condicional PostgreSQL/SQLite. Si 07M-COMM requiere persistencia, el sucesor correcto al corte es `20260915_0060`, debe ser aditivo y reversible y debe conservar un solo head. No se debe reescribir 0059.

Riesgo de integración: la migración 0059 es un archivo untracked en el árbol actual aunque Alembic la reconoce. Antes del cierre se debe comprobar que 0059 y 0060 estén ambos incluidos en el artefacto de release/commit.

## 3. Identidad y aislamiento

La identidad canónica de workspace está en `backend/app/domain/models.py:486-509`. `EnterpriseWorkspace` incorpora `tenant_id`, `workspace_type_code`, jerarquía, código, record code y estado. Business Case y FIN ya demuestran el patrón correcto mediante `project_workspace_id` con FK a `enterprise_workspaces` y unicidad por tenant/proyecto (`business_case/models.py:30-68`, `economic_financial_model/models.py:29-65`).

Decisión recomendada:

```text
1 EnterpriseWorkspace(workspace_type_code=project)
→ 1 CommercialContractingStrategy identity
→ N CommercialStrategyVersion
```

Cada consulta y mutación debe filtrar por `tenant_id` y verificar el ámbito de `EnterprisePermissionContext`. No se debe utilizar `projects.id` como identidad del nuevo aggregate ni crear una segunda tabla Project.

## 4. Patrones de gobierno reutilizables

### Configuración, herencia y numeración

- `AdminConfiguration` (`domain/models.py:462-483`) ya representa revisiones draft/published con contenido JSON y hash.
- `AdminNumberSequence` (`domain/models.py:527-538`) evita numeración `max + 1` y debe emitir `CCS-000001`.
- FIN resuelve configuración publicada por ancestros (`economic_financial_model/service.py:1903-1940`), patrón reutilizable para Tenant → Enterprise → Business Unit → Portfolio.
- Risk y Permit implementan clone/update/publish y preview en sus routers/services.

07M-COMM debe extender esas capacidades con un `CONFIGURATION_KIND` propio; no necesita tablas individuales para cada catálogo si un payload versionado, validado y hashable preserva la semántica.

### ETag, idempotencia e inmutabilidad

- Business Case y FIN exponen `If-Match`, devuelven ETag y mantienen `revision_version`.
- El contrato nuevo exige específicamente HTTP 412 y `ETAG_MISMATCH`; no debe heredarse el helper legacy que responde 409 (`api/v1/_helpers.py:93-105`).
- Business Case usa claves únicas para identidad, revisión, complete y refresh (`business_case/models.py:51-62;120-158`).
- FIN repite el patrón para create/calculate/complete/refresh (`economic_financial_model/models.py:136-170`).
- Business Case protege revisiones `COMPLETED`, `SUPERSEDED` y `VOIDED` mediante listeners ORM y hace inmutables los snapshots (`business_case/models.py:193-206`).

La implementación COMM debe aplicar idempotencia a create, new-revision, submit, complete, void y refresh-apply. La protección terminal debe existir en persistencia/ORM, no solo en la capa de servicio.

### SoD y auditoría

`SecurityEvent` está disponible en `domain/models.py:448-459`. Business Analysis, Risk, Permit, BC y FIN emiten eventos de configuración/lifecycle. Project Definition deniega la revisión de etapa al mismo actor cuando la política lo exige (`project_definition/service.py:657-659`), y FIN aplica reviewer distinto del preparer (`economic_financial_model/service.py:899-923`).

El RBAC existente separa roles transaccionales y roles de configuración, pero algunos roles admin históricos incluyen permisos de lectura del dominio vivo. Para cumplir el prompt, `commercial_strategy_config_admin` no debe recibir automáticamente ningún permiso transaccional; las pruebas deben demostrar ambos rechazos cruzados.

## 5. Reuse before create

La matriz completa está en `reuse-matrix.csv`. Los reusos prioritarios son:

1. `EnterpriseWorkspace` para Project y ámbito.
2. `AdminConfiguration`, `AdminNumberSequence`, `SecurityEvent` y RBAC.
3. Business Analysis, Project Proposal, Project Definition/FEL, Business Case, Budget, Funding, FIN, Risk y Permit solo por referencia/hash.
4. `PROVIDER_REGISTRY` como registro único.
5. `strategicNavigationBlueprint.ts`, `StrategicViewOutlet` y clasificación cerrada como navegación/guard canónicos.
6. cursor estable de Business Analysis para queues desde el primer release.

No se deben reutilizar los modelos operacionales `Contract`, `PurchaseOrder`, `PaymentCertificate`, `RFQPackage` ni `RFQBid` dentro del aggregate estratégico.

## 6. Provider registry y conflicto de taxonomía

El registro único está en `backend/app/modules/investment_evidence_policy/service.py:68-184`. Define campos mínimos genéricos, estado `AVAILABLE` y providers validados de FEL, Funding, Risk, Permit, Business Case y FIN.

Existe una diferencia que exige compatibilidad explícita:

- la taxonomía vigente incluye `CONTRACTING_STRATEGY_READINESS` (`service.py:45-66`);
- el prompt exige provider `COMMERCIAL_READINESS_PROVIDER`, `source_module = COMMERCIAL_CONTRACTING_STRATEGY` y `evidence_type = COMMERCIAL_READINESS`.

Recomendación: registrar el provider con el contrato exacto solicitado y ampliar la taxonomía de forma compatible, pero **no añadirlo automáticamente a ninguna policy publicada ni clasificarlo A/B**. Una prueba de no mutación debe comparar la policy publicada antes/después del registro. Si se conserva un alias hacia `CONTRACTING_STRATEGY_READINESS`, debe ser una adaptación explícita y documentada, nunca un cambio retroactivo de históricos.

La regla de suministro debe ser conjunctiva: versión `COMPLETED`, overall `READY`, fuente vigente, configuración vigente, cero blocker y contexto obligatorio satisfecho.

## 7. Frontera con procurement y contratos operacionales

El repositorio ya posee:

- `Contract` en `domain/models.py:1396-1411`;
- `PurchaseOrder` y `PaymentCertificate` en `domain/models.py:1520-1561`;
- `RFQPackage` y `RFQBid` en `domain/models.py:1587-1630`;
- endpoints de creación/edición/evaluación RFQ en `api/v1/routers/rfq.py:122-375`.

Esos componentes no son duplicados que 07M-COMM deba reemplazar. Son autoridad operacional preexistente y quedan fuera de alcance. La nueva estrategia puede usar palabras como package o contracting model, pero no debe tener FK hacia esas tablas ni producir filas en ellas. Las pruebas de exclusión deben comparar conteos antes/después del happy path COMM.

## 8. Navegación y separación ADMIN/USER

La fase 6 USER actual está definida en `strategicNavigationBlueprint.ts:524-547` y contiene FEL, Business Case, Funding, FIN, Risk y Permit. La fase 6 ADMIN está en `:728-741`. En el corte inicial faltaban los nodos COMM entre Business Case y Funding.

`StrategicViewOutlet.tsx:260-291` resuelve el view canónico, aplica `canAccessStrategicNode` y muestra la denegación admin. Las clasificaciones cerradas son `USER_TRANSACTION`, `ADMIN_CONFIGURATION` y `READ_ONLY_SHARED` (`strategicControlClassification.ts:1-13`).

La integración correcta consiste en:

- añadir un nodo USER `Commercial & Contracting Strategy` en fase 6;
- añadir un nodo ADMIN `Commercial Strategy Configuration` en fase 6;
- registrar renderers USER/ADMIN en `StrategicViewOutlet`;
- no crear listas paralelas;
- no añadir lógica COMM a `App.tsx`;
- verificar deep links y contaminación visual en ambos sentidos.

## 9. Paginación y rendimiento

Business Analysis proporciona el patrón más reciente: `limit` acotado, `X-Next-Cursor` y cursor codificado por `(updated_at, id)` con orden descendente (`business_analysis/router.py:70-75;107-123`, `service.py:354-441;1474-1485`). Las queues `My Strategies`, `Draft`, `In Review`, `Returned`, `Ready`, `Completed`, `Stale` y `All Authorized` deben reutilizarlo desde el release inicial.

Para detalle se debe evitar N+1 en packages, risk allocations y market criteria. La aceptación debe medir al menos primera página y detalle con un fixture de escala, además de inspeccionar cantidad de queries si el harness lo permite.

## 10. Baseline de pruebas y regresión

La evidencia durable de hardening en `docs/validation/strategic-hardening/release-validation.md` registra:

- backend actual: 626 casos, 585 aprobados, 33 omitidos, 8 fallidos, 0 errores;
- las ocho fallas son heredadas: una de Enterprise Structure y siete Gate07K con `MANUAL_REFERENCE_NOT_ALLOWED`;
- PostgreSQL dedicado del alcance previo: 6/6;
- frontend: 109/109 suites y 244/244 tests;
- Playwright estratégico: 7/7;
- TypeScript, build, ESLint y Prettier con exit 0; 9 warnings ESLint preexistentes.

Conteo focal de archivos de referencia antes de COMM: Business Case 5 tests backend, FIN 6, Risk 8, Permit 7, EVID 6; los E2E correspondientes tienen un test por módulo y la navegación estratégica cuatro.

El criterio de cierre COMM debe ser:

```text
fallas nuevas = 0
fallas heredadas = visibles y con la misma firma
tests COMM focales = 100 % verdes
PostgreSQL up/down/up = verde
Browser USER + ADMIN real-stack = verdes
```

No es válido declarar la suite global verde mientras permanezcan las ocho fallas heredadas.

## 11. Exclusiones verificables

El incremento no está autorizado a iniciar ni expandir:

- Vendor/Supplier/Partner/Bidder Master;
- RFQ, RFP, ITT, tender, bid, award;
- Contract, commitment, PO, invoice, payment, change order;
- procurement schedule engine o supplier performance;
- Five Case UI/engine;
- actualización automática de policy Gate07J;
- FID, activación operacional o benefits realization.

Una exclusión no se demuestra solo porque no aparezca un botón: debe validarse en schema diff, router inventory, conteos de tablas operacionales y navegación.

## 12. Riesgos priorizados

| Prioridad | Riesgo | Mitigación exigida |
|---|---|---|
| P0 | Contaminar estrategia con RFQ/Contract/PO existentes | Cero FK/escrituras a tablas operacionales; pruebas de conteo y revisión de schema |
| P0 | Duplicar identidad Project o filtrar solo por tenant | FK a `EnterpriseWorkspace`, verificación de tipo y scope, pruebas cross-tenant/cross-workspace |
| P0 | Mutar una policy Gate07J al registrar provider | Separar registro de provider de requirements publicados; snapshot/diff de policy |
| P0 | Permitir transacciones al config-admin o configuración al author | Roles/permissions disjuntos y pruebas API/direct-route en ambos sentidos |
| P0 | Mutar una versión terminal o recuperar STALE in place | Listeners ORM y refresh-apply que crea nueva DRAFT |
| P1 | Confundir `COMMERCIAL_READINESS` con `CONTRACTING_STRATEGY_READINESS` | Adaptación explícita, contrato estable y compatibilidad histórica |
| P1 | Crear segundo Alembic head por trabajo concurrente | Confirmar head inmediatamente antes de generar y validar 0060 |
| P1 | N+1 y queues sin límite | Cursor estable y eager/batched load; mediciones de list/detail |
| P1 | Readiness calculado en frontend | Evaluador backend determinista y frontend de solo representación |
| P1 | Declarar release sobre suite global heredada | Diferencial por test ID/firma y gates focales verdes |
| P2 | Divergencia de estados (`EXPIRED` en módulos previos) | Usar únicamente los seis estados cerrados requeridos para COMM |
| P2 | Trazabilidad Git débil por commits opacos | ADR, matrices, hashes de evidencia y mensaje de commit descriptivo |

## 13. Brechas de aceptación

`acceptance-gaps.csv` descompone los criterios del prompt. Resumen al corte inicial:

- arquitectura reutilizable lista: identidad, configuración, RBAC, guard, provider registry y patrones lifecycle;
- dominio funcional COMM: pendiente;
- provider/contrato/readiness: pendiente;
- navegación y UI específicas: pendientes;
- migración y pruebas: pendientes;
- exclusiones: baseline sin duplicado estratégico, pero con alto riesgo por objetos operacionales ya existentes;
- regresión: baseline diferencial conocido, no globalmente verde.

## 14. Decisión de baseline

```text
BASELINE_ARCHITECTURE = SUITABLE_FOR_INCREMENT
REUSE_BEFORE_CREATE = REQUIRED
COMM_RELEASE_AT_BASELINE = NOT_VALIDATED
GATE07M_COMM_COMMERCIAL_STRATEGY_RELEASE_VALIDATED = NOT_EMITTED
final_output = NOT_YET_READY
```

La implementación puede comenzar sobre este baseline siempre que preserve el árbol local y satisfaga las matrices anexas. La señal final solo puede emitirse después de validar dominio, migración, provider, separación, E2E, regresión e históricos.
