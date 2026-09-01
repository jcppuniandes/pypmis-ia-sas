# ADR 59 — Gate 07L Post-FID Project Governance

- Estado: aceptado
- Fecha: 2026-09-01
- Alcance: gobierno, elegibilidad y handoff posteriores a un FID Gate 07K

## Contexto

Gate 07K emite `READY_FOR_POST_FID_PROJECT_GOVERNANCE` para una decisión `PYP-FFA + GO` válida, pero no autoriza por sí misma la activación de un Project Workspace. El repositorio ya cuenta con identidad canónica en `enterprise_workspaces`, proceso de Project Workspace Initialization y transición de Activation. Duplicar esos motores crearía estados paralelos, efectos repetidos y reglas de autorización inconsistentes.

## Decisión

Implementar Gate 07L como una capa de orquestación que:

1. valida las semánticas y hashes del FID congelado;
2. consume el exact Project Set del paquete Gate 07K;
3. clasifica cada Project usando el estado real de `enterprise_workspaces` y `project_workspace_initializations`;
4. separa condiciones `blocking_for_activation` de condiciones solo `blocking_for_commitment`;
5. persiste snapshots inmutables `post_fid_project_eligibilities` para auditoría, refresh y staleness;
6. expone contratos de handoff que apuntan a los endpoints existentes de Initialization y Activation;
7. no ejecuta automáticamente ninguna transición del Project.

## Persistencia

La migración `20260901_0056` es aditiva y reversible. Cada snapshot conserva FID, paquete, estado clasificado, condiciones, configuración, resultado e `eligibility_hash`. El estado operativo del Project no se copia: sigue perteneciendo a las tablas canónicas. Los cambios de fuente generan una nueva ronda; no se reescribe una ronda anterior.

## Reglas determinantes

- `NOT_INITIALIZED` → `READY_FOR_PROJECT_WORKSPACE_INITIALIZATION`.
- `INITIALIZED_NOT_ACTIVE` → `READY_FOR_PROJECT_WORKSPACE_ACTIVATION`.
- `ACTIVE` → `NO_REACTIVATION_REQUIRED`.
- FID no vigente → `STALE`.
- Condición abierta de activación, autorización vencida o estado incompatible → `POST_FID_PROJECT_GOVERNANCE_BLOCKED`.
- No FID o modelo de gobierno fuera de `CAPITAL_OWNER` → `NOT_APPLICABLE`.

## Seguridad y concurrencia

Se agregan permisos separados de lectura, evaluación, refresh y configuración; el rol de Investment Decision Maker no obtiene Activation Authority. Las mutaciones de eligibility/configuración usan ETag e idempotencia. Los handoffs no ejecutan el servicio delegado y registran `SecurityEvent` una sola vez por clave.

## Consecuencias

- Se preservan identidad, estados y lógica existentes.
- Project ID14 activo nunca se reinicializa ni reactiva desde Gate 07L.
- CONTRACTOR_DELIVERY y DIRECT_INTERNAL mantienen sus rutas vigentes.
- Las condiciones de compromiso permanecen visibles sin implementar compromisos.
- El límite de alcance excluye Procurement, Contracting, PO, Payment, Accounting, Treasury, NTP y ejecución.
