# ADR 58 — Gate 07K Investment Decision / FID Governance

## Estado

Aceptado — 2026-08-31.

## Contexto

Gate 07J congela un paquete listo para decisión, pero no aprueba inversión ni registra FID. Se requiere una fuente de verdad formal que conserve el alcance exacto, autoridad, votos, condiciones y semántica de autorización sin mutar preparación, Portfolio, Project, Funds ni ejecución.

## Decisión

- Crear `InvestmentDecision` y `InvestmentDecisionVote` como agregados tenant-scoped separados de Gate 07J y Project.
- Consumir exclusivamente una preparación 07J `FROZEN`, `READY`, vigente y con hashes coincidentes.
- Persistir un `Decision Package Snapshot` y hashes estables de paquete/configuración/decisión.
- Soportar rondas 1:N, estados `DRAFT → SUBMITTED → IN_REVIEW → READY_FOR_DECISION → DECIDED`, anulación previa al cierre y resultados exactos `GO/HOLD/RECYCLE/KILL`.
- Tratar `PYP-INV-SELECT + GO` como autorización para continuar definición, nunca FID.
- Tratar únicamente `PYP-FFA + GO` como FID y Full Funds Authorization; su salida formal es
  `FINAL_INVESTMENT_DECISION_GO` y, aun así, `can_activate_project=false`.
- Exponer `READY_FOR_POST_FID_PROJECT_GOVERNANCE` sólo como señal de handoff separada del resultado formal,
  sin ejecutar automáticamente ninguna acción posterior al FID.
- Reutilizar `AdminConfiguration`, `AdminNumberSequence`, RBAC, `SecurityEvent`, ETag e idempotencia.
- Congelar autoridad individual/comité, quorum, regla de voto, checklist y segregación de funciones en cada ronda.

## Consecuencias

La decisión cerrada es inmutable y auditable; las correcciones requieren una nueva preparación/ronda. La salida 07K puede ser consumida por un proceso futuro de gobierno post-FID, pero no crea ni activa proyectos, no emite NTP y no habilita contratación, pagos, contabilidad o ejecución.

## Exclusiones

No se implementan Project Initialization/Activation, Contracting, Accounting, Payment, Notice to Proceed, ejecución ni reautorización operativa downstream.
