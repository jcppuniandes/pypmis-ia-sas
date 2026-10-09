# ADR 61 — Gate 07A-BA Business Analysis & Options Governance

## Estado

Aceptado e implementado el 10 de septiembre de 2026.

## Contexto

El flujo estratégico permitía pasar de una Idea aceptada a Project Proposal sin un expediente intermedio que definiera la necesidad, comparara alternativas y preservara la recomendación aprobada. Ese salto reducía la trazabilidad de las decisiones de inversión y permitía que Project Proposal recibiera supuestos no gobernados.

La solución debía ser aditiva: reutilizar Idea Lifecycle, Strategic Objectives, `AdminConfiguration`, Enterprise Workspaces, permisos, `SecurityEvent` y Project Proposal sin crear un segundo motor de estrategia, configuración o aprobaciones.

## Decisión

Se inserta **Business Analysis & Options** en USER MODE entre Idea Lifecycle y Project Proposal. El agregado tenant-scoped conserva la Idea y su evaluación aceptada como fuente inmutable, administra el ciclo `DRAFT → SUBMITTED → IN_REVIEW → COMPLETED` y contempla `RETURNED`, `SUPERSEDED` y `VOIDED`.

Las tablas `business_analyses` y `business_analysis_revisions` almacenan identidad, contenido estructurado, linaje de configuración, ETag, hashes de fuente/readiness/completion y snapshots append-only. Los registros `COMPLETED` no se editan; los cambios materiales crean una revisión nueva.

Project Proposal recibe campos de linaje opcionales para Business Analysis. En flujos nuevos `CAPITAL_OWNER` exige un BA vigente, completo y listo; configuraciones históricas sin la política permanecen grandfathered. `CONTRACTOR_DELIVERY` y `DIRECT_INTERNAL` no se fuerzan por defecto.

ADMIN MODE se limita a configuración reutilizable: taxonomías, catálogos, matriz de evaluación, reglas de opciones, readiness, mapping, numeración, herencia y SoD. La configuración sigue `DRAFT → PUBLISHED → ARCHIVED`, el preview es `persisted=false`, las publicaciones son inmutables y la resolución sigue Tenant → Enterprise → Business Unit → Portfolio.

## Seguridad y concurrencia

- Los comandos mutables requieren `If-Match`; la creación y las revisiones materiales requieren `Idempotency-Key`.
- La segregación de funciones impide que el autor ejecute la revisión final, salvo política publicada explícita.
- Los permisos se separan en lectura, creación, edición, envío, revisión y administración/publicación de configuración.
- Cada transición y cambio de configuración emite `SecurityEvent` con actor, estados y metadatos de linaje.

## Contratos de integración

Idea Lifecycle produce `READY_FOR_BUSINESS_ANALYSIS` cuando la política lo exige. Un BA completo y vigente produce `READY_FOR_PROJECT_PROPOSAL`. Project Proposal copia únicamente el snapshot de valores mapeados y conserva ids, revisiones y hashes de Idea, evaluación, Business Analysis y configuración.

## Consecuencias

- La decisión de alternativa queda reconstruible y auditable antes de Project Proposal.
- No se duplican objetivos estratégicos, workspaces, catálogos globales ni motores de configuración.
- El incremento no incorpora Five Case Business Case, modelos financieros detallados, FID, Project Workspace activation ni automatización de beneficios.
- Señal de cierre condicionada a todas las puertas: `GATE07A_BA_BUSINESS_ANALYSIS_RELEASE_VALIDATED`.
- Output: `READY_FOR_GOVERNED_PROJECT_PROPOSAL_FROM_BUSINESS_ANALYSIS`.
- Próximo incremento permitido: `ENHANCE_GATE07M_BC_WITH_FIVE_CASE_MODEL`.

