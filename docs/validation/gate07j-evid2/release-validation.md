# Gate07J-EVID-2 — Release validation

- **Fecha de cierre:** 2026-09-20
- **Incremento:** Gate-level Evidence Policy, Decision Criteria & Strategic Evidence Revalidation
- **Estado:** VALIDATED
- **Alembic:** una sola head `20260916_0061`; sin migración EVID-2
- **ADR:** `docs/68-adr-gate07j-evid2-decision-criteria.md`
- **Evidencia reproducible:** `outputs/.qa/gate07j-evid2/`

## Resultado

El incremento quedó validado en backend, PostgreSQL real, frontend, Chromium y el stack Docker local. Gate07J prepara y congela evidencia, criterios y contexto; Gate07K conserva la autoridad exclusiva sobre `GO`, `HOLD`, `RECYCLE` y `KILL`. No existe decisión automática, segundo ranking ni FID fabricado.

## Controles de arquitectura

| Control | Estado | Evidencia |
|---|---:|---|
| Evidencia A/B/C separada de criterios | PASS | Política legacy y EVID-2 verificadas por unitarios |
| Taxonomía `READINESS_CHECK`, `MUST_MEET`, `DECISION_HURDLE`, `PRIORITIZATION`, `SUCCESS_CRITERION` | PASS | `decision_criteria.py` + backend focal |
| Operadores allowlist, sin expresiones ejecutables | PASS | rechazo de operador inseguro y `unsafe_expression_execution=false` |
| Policy clone EVID-2 desde fuente publicada | PASS | endpoint dedicado, idempotencia y guard `PUBLISHED_POLICY_REQUIRED` |
| PYP-INV-SELECT proporcional | PASS | policy/unitario + round-trip PostgreSQL |
| PYP-FFA estricto | PASS | policy/unitario + round-trip PostgreSQL |
| Quality/confidence separada de readiness | PASS | contrato backend y matriz USER |
| Providers canónicos reutilizados | PASS | BC, FIN, Benefits, Commercial, FEL, Funding, Risk, Permit y Portfolio |
| Five Case, FIN y Portfolio consumidos sin recalcular | PASS | hashes/lineage/snapshot; sin segundo score |
| Consistencia cruzada | PASS | FFA bloquea mismatch; Select advierte |
| Snapshot histórico inmutable | PASS | frozen Gate07J, decision package y success criteria |
| Gate07K como autoridad formal única | PASS | `formal_decision_authority=GATE07K`; `automatic_decision=false` |
| Guard de `GO` | PASS | package/evidence READY y MUST_MEET/HURDLE satisfechos |
| HOLD/RECYCLE requieren nueva preparación cuando corresponde | PASS | `NEW_GATE07J_PREPARATION_REQUIRED` |
| Sin tabla o motor paralelo | PASS | JSON versionado existente; no migration EVID-2 |
| Auditoría, ETag e idempotencia | PASS | eventos y pruebas de lifecycle |

## Evidencia ejecutada

| Suite | Resultado | Artefacto |
|---|---:|---|
| Backend focal Gate07J/EVID-2/Gate07K | 28 passed | `backend-focused.xml` |
| Regresión estratégica backend | 62 passed | `backend-strategic-regression.xml` |
| PostgreSQL policy/Select | 1 passed | `postgres-select.xml` |
| PostgreSQL Select/FFA snapshots | 1 passed | `postgres-ffa.xml` |
| Frontend focal | 9 passed | `frontend-focused.xml` |
| Frontend completa | 276 passed | `frontend-full.xml` |
| Chromium ADMIN policy | 1 passed | `browser-admin.xml` |
| Chromium USER Gate07J | 1 passed | `browser-gate07j.xml` |
| Chromium USER Gate07K | 2 passed | `browser-gate07k.xml` |
| Ruff backend completo | PASS | `validation-summary.json` |
| TypeScript y Vite build | PASS | 2453 módulos transformados |
| ESLint | PASS | 0 errores; 9 warnings heredados BIM, umbral CI 10 |
| Prettier | PASS | `src` y E2E afectados |

## Hallazgos corregidos durante el cierre

1. Se exigió una fuente `published` para el clon EVID-2; un draft mutable recibe `409 PUBLISHED_POLICY_REQUIRED`.
2. `SessionLocal` usa `autoflush=False`. La sincronización de evidencia ahora ejecuta `flush()` antes de evaluar y congelar criterios, garantizando que el snapshot persistido coincida con la evidencia de la misma transacción.
3. Los E2E se alinearon con la jerarquía actual `Enterprise Strategy Manager > Investment Governance` y esperan el cambio completo USER/ADMIN antes de interactuar.
4. El control Publish del E2E quedó acotado al grupo accesible de acciones, eliminando ambigüedad con la pestaña homónima.

## PostgreSQL, despliegue y contrato

| Verificación | Resultado |
|---|---:|
| `alembic current` | `20260916_0061 (head)` |
| `alembic heads` | `20260916_0061 (head)` |
| API readiness | `ready`; database `ok`; redis `ok` |
| Frontend | HTTP 200 en `http://127.0.0.1:5173/app` |
| Docker | api/frontend/db/redis/worker/beat activos; api/db/redis healthy |
| OpenAPI clone EVID-2 | presente |
| OpenAPI success criteria snapshot | presente |
| OpenAPI mandatory/hurdle guards | presentes |

## STOP boundary

Las siguientes capacidades permanecen deliberadamente fuera del incremento y no se presentan como implementadas: Strategic Capital Buckets, periodic Portfolio Review, Capital Demand/Capital Planning, Basic Data Readiness, QRA/Confidence engine, Owner Capability Readiness, Operational Readiness, Benefits Realization, Procurement execution y Project Delivery.

## Riesgos residuales no bloqueantes

- No se ejecutó una prueba de carga dedicada. El evaluador es determinista y trabaja sobre el conjunto ya resuelto, pero la medición de Project Sets masivos queda como hardening posterior.
- ESLint conserva nueve warnings históricos en `BimIfcModelViewer.tsx`; no corresponden a este incremento y no superan el umbral CI.
- El repositorio contiene cambios acumulados de incrementos previos; esta validación no autoriza limpiar, descartar ni commitear trabajo ajeno.

## Señales exclusivas de cierre

```text
GATE07J_EVID_2_DECISION_CRITERIA_POLICY_RELEASE_VALIDATED
READY_FOR_GOVERNED_GATE_DECISION_WITH_INTEGRATED_STRATEGIC_EVIDENCE
```

Estas señales significan que Gate07J puede entregar a Gate07K un paquete gobernado, íntegro y revalidado. No significan decisión ni FID automáticos.
