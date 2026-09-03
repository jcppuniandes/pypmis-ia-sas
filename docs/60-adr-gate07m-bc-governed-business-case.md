# ADR 60 — Gate 07M-BC Governed Business Case Manager

## Estado

Aceptado e implementado el 2 de septiembre de 2026.

## Contexto

P&Pmis requiere un Business Case longitudinal, trazable al Project Proposal y al Project Workspace, que evolucione durante FEL y decisiones posteriores sin duplicar cálculos de Portfolio Budget, Portfolio Resource, Funds, Risk, Permit, Investment Decision o Post-FID Governance. El motor económico-financiero pertenece al siguiente incremento Gate 07M-FIN.

## Decisión

Se incorpora un agregado tenant-scoped con tres tablas:

- `business_cases`: identidad estable 1:1 con Project Workspace, numeración `BC-00001`, configuración resuelta y revisión actual.
- `business_case_revisions`: versiones `R1..Rn`, propósito explícito, narrativa, referencias/hashes de proveedores, readiness y contrato financiero nullable con estado `NOT_AVAILABLE`.
- `business_case_decision_snapshots`: evidencia append-only de una revisión `COMPLETED` usada en una decisión.

Las revisiones `COMPLETED`, `SUPERSEDED` y `VOIDED` no se actualizan. Un refresh explícito crea una nueva revisión; el preview declara `persisted=false`. La comparación de fuentes con el último snapshot puede recomendar revisión por cambio material, pero no ejecuta decisiones ni modifica el Project Workspace.

La configuración reutiliza `AdminConfiguration`, resuelve Tenant → Enterprise → Business Unit → Portfolio y aplica contexto de Project Type, Governance Model, Gate Profile y FEL Stage. La configuración publicada aplicable más cercana prevalece y su id, revisión, hash, workspace origen y cadena de resolución quedan congelados en el agregado.

Los comandos mutables usan ETag/`If-Match`, idempotencia y `SecurityEvent`. La separación preparador/revisor es obligatoria por defecto.

## Contratos de integración

Gate 07M-BC conserva referencias y hashes de Project Proposal, Project Definition/FEL, presupuesto, recursos, funding, riesgos y permisos. No copia sus registros ni recalcula su semántica. `recommendation_json` es apoyo a decisión y nunca una decisión formal.

Los campos NPV, IRR, payback y benefit-cost ratio permanecen nulos mientras `financial_model_status=NOT_AVAILABLE`.

## Consecuencias

- Historial auditable y reconstruible por revisión y snapshot.
- Evolución aditiva sin modificar proveedores existentes.
- Consultas de cola y últimas revisiones cubiertas por índices para el diseño de 10.000 Projects y 100.000 revisiones.
- Migración sucesora `20260902_0057`, con prueba PostgreSQL up/down/up.
- Estado de cierre: `GATE07M_BC_RELEASE_VALIDATED`.
- Output: `READY_FOR_GOVERNED_BUSINESS_CASE_EVIDENCE`.
- Siguiente incremento permitido: `BUILD_GATE07M_FIN`.

