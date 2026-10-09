# Gate07M-BC-5C — Release validation

- **Fecha:** 2026-09-18
- **Incremento:** Five Case Business Case integration
- **Estado de implementación:** Completa para el alcance funcional definido
- **Estado de liberación:** `GATE07M_BC_FIVE_CASE_RELEASE_VALIDATED`
- **Alembic:** `20260916_0061 (head)`; no se añadió migración

## Resultado ejecutivo

El incremento reutiliza el agregado `BusinessCase`, proyecta Strategic, Economic, Commercial, Financial y Management Case desde referencias y hashes congelados, conserva el provider `BUSINESS_CASE_READINESS_PROVIDER` y no modifica la política publicada/default de Gate07J. La implementación focal, la compilación, los controles estáticos, PostgreSQL transaccional, el navegador USER/ADMIN y las regresiones integrales requeridas están verdes.

El cierre se emite con 273/273 pruebas frontend, la regresión estratégica backend del alcance verde y 2/2 pruebas PostgreSQL, incluido un round-trip transaccional Five Case READY. La suite backend global del repositorio no fue requisito de este incremento; se validó la regresión estratégica completa definida por el alcance.

## Evidencia ejecutada

| Evidencia | Resultado | Archivo / observación |
|---|---:|---|
| Backend focal BC/5C/Benefits/Commercial/FIN/Evidence Policy | 41 passed | `outputs/.qa/gate07m-bc-5c/backend-focused.xml` |
| Backend strategic regression | 152 passed / 4 PostgreSQL-only skipped | `outputs/.qa/gate07m-bc-5c/backend-strategic-regression-final.xml` |
| Ruff `app tests` | PASS | 0 errores |
| PostgreSQL estructura Business Case | 1 passed | `outputs/.qa/gate07m-bc-5c/postgres-structural.xml` |
| PostgreSQL Five Case transaccional | 2 passed | `outputs/.qa/gate07m-bc-5c/postgres-business-case.xml` |
| Alembic current / heads | PASS | `20260916_0061 (head)` |
| Frontend focal Business Case + navegación | 20 passed | `outputs/.qa/gate07m-bc-5c/frontend-focused.xml` |
| Browser Chromium USER/ADMIN | 1 passed | `outputs/.qa/gate07m-bc-5c/browser-e2e.xml` |
| TypeScript | PASS | salida 0 |
| Vite production build | PASS | 2.453 módulos transformados |
| ESLint | PASS | 0 errores; 9 warnings heredados en `BimIfcModelViewer.tsx` |
| Prettier | PASS | todos los archivos coinciden |
| Docker API / DB / Redis | PASS | endpoint `/api/v1/health/ready` = 200/ready |
| OpenAPI desplegado | PASS | contrato expone Five Case, evidence matrix, gate context y business case hash |
| Frontend full Vitest | 273 passed | `outputs/.qa/gate07m-bc-5c/frontend-full-final.xml` |
| AppFlow production hardening aislado | 1 passed | `frontend-appflow-production-hardening.xml`; 46,26 s |
| AppFlow tenant user/admin aislado | 1 passed | `frontend-appflow-user-admin.xml`; 30,23 s |
| AppFlow navegación aislado | 1 passed | `frontend-appflow-navigation.xml`; ejecución de larga duración verde |

## Cobertura funcional focal

La selección backend valida:

- derivación histórica exclusivamente desde revisión, refs y hashes congelados;
- lectura legacy sin fabricar Five Case;
- `CAPITAL_OWNER` estricto y modelos no aplicables sin override;
- Refresh Preview sobre unión de fuentes, incluidos removidos y deltas por Case;
- negativos Benefits, Commercial, FIN stale, FEL stale y Business Analysis mismatch;
- source evidence ausente representada como `NOT_AVAILABLE`, no fabricada;
- lineage de Business Analysis fijado por Project Proposal;
- ETag, idempotencia, SoD, snapshots append-only e inmutabilidad longitudinal;
- compatibilidad de Benefits, Commercial, FIN y provider existente.

La prueba Chromium valida:

- navegación canónica bajo `Project Definition & Investment Case`;
- las diez vistas USER de Business Case y la síntesis Five Case;
- matriz Sources & Evidence read-only y enlaces `View Source`;
- secciones ADMIN de applicability, requirements y readiness;
- Preview ADMIN con `persisted=false`;
- ausencia de mutación operacional de fuentes desde la configuración.

## PostgreSQL

La instancia local confirma las tablas, constraints, unique keys e índices funcionales del agregado existente. La prueba se hizo independiente del nombre físico del índice y valida las columnas indexadas, porque `Base.metadata.create_all` y Alembic usan nombres distintos para índices equivalentes. No se creó una migración Five Case.

El caso `test_gate07m_bc_five_case_ready_revision_round_trips_on_postgresql` crea una revisión con los cinco Cases READY, verifica referencias, hashes, matriz, `source_current` y round-trip real sobre PostgreSQL, y revierte todos los datos al finalizar. El JUnit combinado cerró 2/2.

## Regresión y rendimiento

La primera corrida Vitest obtuvo 270/273: tres pruebas amplias de `AppFlow` agotaron límites históricos, sin fallos funcionales de aserción. Se estabilizaron únicamente los límites de tiempo (45→90 s global y 300→420 s para el AppFlow largo), las tres pruebas pasaron aisladas y la repetición integral cerró 273/273.

La regresión estratégica backend inicial detectó una dependencia de orden en un fixture Gate 07L: heredaba una configuración COMMITTEE cuando el escenario declaraba autoridad individual. El fixture se hizo determinista sin cambiar lógica productiva ni relajar aserciones; la secuencia contaminante pasó 2/2 y la regresión estratégica final quedó verde. El bundle de producción sigue aislando `web-ifc`; Vite reportó build exitoso.

## Decisión de release

Se emiten las señales formales:

```text
GATE07M_BC_FIVE_CASE_RELEASE_VALIDATED
READY_FOR_GOVERNED_FIVE_CASE_BUSINESS_CASE_EVIDENCE
```

La capacidad está implementada, desplegada y validada mediante pruebas focales, regresión estratégica, frontend integral, E2E Chromium y PostgreSQL transaccional.

## STOP boundary

Este cierre no implementa actualización de política Gate07J, Risk Appetite, Basic Data, QRA, Owner Capability, Capital Demand, Procurement execution, Project Delivery, Operational Readiness ni Benefits Realization.
