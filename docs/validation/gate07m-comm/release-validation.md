# Gate 07M-COMM release validation

Fecha: 2026-09-16  
Aplicación: P&Pmis Construction AI  
Alembic: `20260915_0060 (head)`; head único

## Resultado

`GATE07M_COMM_COMMERCIAL_STRATEGY_RELEASE_VALIDATED`

`READY_FOR_GOVERNED_COMMERCIAL_READINESS_EVIDENCE`

`COMMERCIAL_READINESS_PROVIDER = AVAILABLE`

## Evidencia ejecutada

| Control | Resultado | Evidencia |
|---|---:|---|
| Ruff COMM, router/service/models/schemas y tests | PASS | Sin errores |
| Backend focal SQLite | 8/8 PASS | `outputs/.qa/gate07m-comm/backend-commercial.xml` |
| Backend focal PostgreSQL 16 | 8/8 PASS | `outputs/.qa/gate07m-comm/backend-commercial-postgresql.xml` |
| Migración SQLite 0059→0060→0059→0060 | 1/1 PASS | `outputs/.qa/gate07m-comm/migration-sqlite.xml` |
| Migración PostgreSQL 0059→0060→0059→0060 | 1/1 PASS | `outputs/.qa/gate07m-comm/migration-postgresql.xml` |
| Gate07J-EVID, provider y no mutación de policy | 13/13 PASS | `outputs/.qa/gate07m-comm/gate07j-evid-regression.xml` |
| Frontend Vitest completo | 260/260 PASS | Salida de release 2026-09-16 |
| TypeScript | PASS | `tsc --noEmit` |
| Build Vite | PASS | 2.449 módulos transformados |
| ESLint | PASS | 0 errores; 9 warnings BIM heredados dentro del límite |
| Prettier | PASS | Todos los archivos inspeccionados |
| Playwright Chromium COMM | 2/2 PASS | `outputs/.qa/gate07m-comm/playwright-commercial.xml` |
| HTTP API | 200 READY | database=ok, redis=ok |
| HTTP frontend | 200 | `http://127.0.0.1:5173/app` |

## Regresión backend diferencial

El full run inicial recolectó 634 casos: 562 PASS, 34 SKIP, 8 fallos heredados y 30 errores de infraestructura Windows. Los 30 errores tenían una sola causa: `tmp_path` intentaba retirar la misma carpeta que contenía la base SQLite abierta por la suite. Se separaron `pytest basetemp` y `PYPMIS_PYTEST_RUNTIME_DIR`; la repetición exacta de los archivos afectados aprobó 50/50 (`backend-temp-isolation-regression.xml`).

Los ocho fallos funcionales reproducen el baseline anterior a COMM:

- uno en publicación de Enterprise Structure;
- siete en Gate07K por `MANUAL_REFERENCE_NOT_ALLOWED`.

No hay un fallo nuevo atribuible a COMM. La cobertura global observada fue 80,78 %, superior al mínimo de 75 %.

## Controles funcionales y de gobernanza

- identidad canónica `EnterpriseWorkspace` de tipo Project reutilizada;
- una identidad `CommercialContractingStrategy` por Project y N versiones controladas;
- lifecycle `DRAFT → IN_REVIEW → COMPLETED`, con `SUPERSEDED` y `VOIDED` históricos;
- `COMPLETED` inmutable y sin delete físico;
- readiness backend-owned con blockers deterministas y catálogos publicados;
- staleness no destructivo por source/configuration hash;
- Refresh Preview `persisted=false`; Apply crea nueva DRAFT;
- ETag/If-Match con `412 ETAG_MISMATCH`;
- idempotencia ligada a operación, target y payload;
- SoD de autor y revisor final;
- scopes tenant/workspace en expedientes y configuración;
- SecurityEvent en lifecycle y configuración;
- configuración ADMIN con herencia, Project/Governance/FEL/Gate applicability, required fields y tailoring;
- USER y ADMIN separados por API, navegación y ruta directa;
- provider registrado sin mutar ni reclasificar Gate07J-EVID.

## Rendimiento

Medición local controlada con una identidad COMM y cursor/limit 50:

- list promedio: 24,94 ms;
- detail promedio: 24,35 ms.

Las secciones se almacenan en un documento JSON versionado y se cargan sin tablas hijas por paquete/riesgo/mercado. Las colas Ready/Stale recalculan vigencia por candidato; una proyección materializada es una mejora futura si el volumen crece significativamente.

## Exclusiones verificadas

No se creó Vendor/Supplier/Partner/Bidder Master, RFQ/RFP/ITT/Tender, Bid/Award, Contract, Commitment, Purchase Order, Invoice/Payment, Change Order, procurement schedule engine ni Five Case UI. El incremento tampoco inició Benefits Realization.

## Despliegue local

Los servicios `db`, `redis`, `api`, `worker`, `beat` y `frontend` fueron reconstruidos. PostgreSQL local fue migrado a `20260915_0060`; el API quedó healthy y el frontend respondió HTTP 200.

## Deuda no bloqueante

- materializar la proyección de readiness para colas Ready/Stale cuando el volumen lo justifique;
- evaluar una FK diferida para `current_version_id` si se adopta un patrón circular portable;
- ampliar Playwright multi-actor a todo el lifecycle UI; el lifecycle completo ya está probado en SQLite y PostgreSQL a nivel API/servicio.

## Siguiente incremento recomendado

`BUILD_STRATEGIC_BENEFITS_PLAN_AND_BENEFITS_TRACEABILITY`

No se inicia automáticamente ningún incremento fuera del alcance 07M-COMM.
