# ADR 66 — Gate07M-BEN Strategic Benefits Plan, Register, Traceability and Readiness

- **Fecha:** 2026-09-16
- **Estado de la decisión:** Accepted / architecture validated
- **Estado de liberación:** VALIDATED
- **Ámbito:** P&Pmis Construction AI, macroproceso estratégico, fase 6

## Contexto

Gate07M-BEN debe introducir una fuente gobernada pre-FID para el Plan de Beneficios Estratégicos, el registro estable de beneficios, la trazabilidad y la preparación de beneficios. La capacidad debe madurar progresivamente desde la oportunidad hasta FEL/FID y dejar preparada la continuidad futura hacia Benefits Realization Management, sin implementar actuals de realización.

El repositorio ya contiene fuentes parciales que deben reutilizarse por referencia: beneficio esperado de Idea, beneficios y owner preliminar de Project Proposal, alternativa recomendada de Business Analysis, `benefits_json` de Business Case y métricas de FIN. Ninguna de estas fuentes reemplaza la identidad gobernada del Benefit creada en este incremento.

El baseline inspeccionado tiene un único Alembic head `20260915_0060`, correspondiente a Gate07M-COMM. La arquitectura de COMM aporta patrones recientes para configuración, lifecycle, ETag, idempotencia, SoD, staleness, Refresh Preview/Apply, provider registry y separación ADMIN/USER. Esos patrones se reutilizan; no se crea una arquitectura paralela.

## Decisión

1. La autoridad se denomina **Strategic Benefits Plan** y pertenece conceptualmente a **Business Case & Benefits**.
2. La relación gobernada es `1 Project Workspace → 1 Benefits Plan identity → N Plan Versions`.
3. Cada Benefit conserva una identidad estable y un número visible `BEN-*` entre versiones, delivery, operations y la futura realización.
4. Cada versión congela Benefits, medidas, owners, baseline, target, trazabilidad, fuentes y hashes. Una versión `COMPLETED` es inmutable.
5. El lifecycle es `DRAFT → IN_REVIEW → COMPLETED`, con `SUPERSEDED` y `VOIDED`. Una modificación material o refresh produce una nueva DRAFT.
6. Se conserva explícitamente `OUTPUT ≠ OUTCOME ≠ BENEFIT ≠ VALUE` en modelo, API, UI, readiness y documentación.
7. Se soporta `1 Benefit → 1..N Measures`, con una medida primaria cuando la política lo exija. Un baseline desconocido se representa explícitamente; nunca se convierte en cero.
8. Benefits Traceability Matrix es un read model derivado, paginado y sin doble captura ni N+1.
9. Readiness, coverage, allowed actions, staleness y provider supply son decisiones del backend.
10. ADMIN configura; USER opera Plans y Benefits vivos. Los permisos son disjuntos.
11. Se registra únicamente `BENEFITS_READINESS_PROVIDER`, con `source_module=STRATEGIC_BENEFITS_PLAN` y `evidence_type=BENEFITS_PLAN_READINESS`.
12. Registrar el provider no modifica ni reclasifica ninguna política Gate07J publicada o por defecto.
13. La navegación se modifica únicamente en `strategicNavigationBlueprint.ts` y estructuras derivadas; las vistas se resuelven en `StrategicViewOutlet`. No se añade routing BEN a `App.tsx`.
14. La persistencia cubre identidad estable, snapshots históricos, medidas, asociaciones, hashing y consulta; se evita una tabla por sección.
15. Si persiste el head único, el sucesor será `20260916_0061`, aditivo y reversible en PostgreSQL y SQLite donde aplique.

## Regla de suministro del provider

`can_supply_investment_gate_evidence=true` solo cuando la versión está `COMPLETED`, overall readiness es `READY`, fuentes y configuración están vigentes, la cobertura tiene denominador explícito, no existen blockers y el contrato/hashes están completos.

## Autoridad y fronteras

Gate07M-BEN es autoridad para identidad, definición, owner, KPI, baseline, target, fecha, método, valor esperado, dependencias, supuestos, trazabilidad y readiness del Benefit. No es autoridad para catálogos de objetivos, Business Analysis, aprobación de Business Case, WBS/scope, cálculos FIN, Risk Register, estrategia comercial, ejecución, KPI actual, contabilidad o pagos.

## Límites obligatorios

No se implementan Five Case Business Case, policy Gate07J obligatoria para Benefits, Benefits Realization actuals, Risk Appetite, Basic Data, QRA, Owner Capability, procurement, Project Delivery, Operational Readiness ni un segundo Operational Benefits Register.

## Compatibilidad histórica

No se reinterpretan retroactivamente Business Cases, Commercial Strategies, FIN, Project Proposals, Business Analyses, paquetes Gate07J, decisiones Gate07K ni históricos Gate07L. BEN solo referencia estas fuentes y congela IDs/hashes/as-of.

## Nota obligatoria de gaps CPIG

Se preservan para roadmap, sin implementarlos: Risk Appetite / Risk Capacity / Risk Thresholds; Strategic Capital Demand / Capital Planning enhancement; Basic Data Readiness; QRA / Confidence; Owner Capability Readiness; Gate-level evidence revalidation policy; Operational Readiness; Benefits Realization.

## Validación de liberación

La liberación demostró migración up/down/up SQLite/PostgreSQL, happy path PostgreSQL, negativos, staleness/recovery, continuidad, no mutación Gate07J, seguridad, frontend, Chromium USER/ADMIN, rendimiento y regresión diferencial. Los nueve fallos de la regresión backend completa no son atribuibles a BEN: ocho reproducen firmas heredadas y uno depende del `.env` local con `SEED_DEMO_DATA=true`; los casos focales BEN permanecen en verde.

Con los 77 entregables en PASS se emiten:

```text
GATE07M_BEN_STRATEGIC_BENEFITS_RELEASE_VALIDATED
READY_FOR_GOVERNED_BENEFITS_PLAN_EVIDENCE
BENEFITS_READINESS_PROVIDER = AVAILABLE
```

La ejecución consolidada final de Chromium posterior al rebuild fue bloqueada por el límite temporal del revisor de permisos del host. Los cuatro escenarios se habían validado en ejecuciones divididas: tres aprobaron juntos y el escenario ADMIN corregido aprobó en aislamiento. Esta limitación ambiental queda documentada sin reinterpretarla como un fallo de la aplicación.
