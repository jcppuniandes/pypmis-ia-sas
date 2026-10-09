# ADR Wave 3B Owner Capability Readiness

Estado: aceptada e implementada. Validación local completada con PostgreSQL, Chromium real y regresiones estratégicas; evidencia detallada en docs/79-wave3b-owner-capability-readiness-release.md.

## Contexto y baseline

La revisión inició en main, commit 9cb0969abb5d48cc25b0c6a935b11e6bd7afd16f, con 76 archivos rastreados modificados, 7394 inserciones y 949 eliminaciones correspondientes a incrementos anteriores. Se conservaron los archivos sin rastrear y las configuraciones existentes. El head del repositorio y de PostgreSQL local era 20261008_0065. Los servicios API 8000 y base de datos 5432 estaban saludables; el frontend 5173 estaba activo. Wave 2B había cerrado Risk Governance y Basic Data Readiness, con su proveedor disponible.

## Decisión

Owner Capability es un dominio de evidencia gobernada del propietario. Su política reutiliza AdminConfiguration, la resolución de jerarquía y el gobierno de publicación existentes. La evaluación reutiliza EnterpriseWorkspace de tipo project, AdminNumberSequence, permisos Project Definition, SecurityEvent y controles de concurrencia. Los ítems, brechas y mitigaciones pertenecen al agregado de evaluación, sin un motor de tareas ni tablas por dimensión.

La migración sucesora aditiva incorpora solamente owner_capability_assessments y owner_capability_commands. Un snapshot COMPLETED es inmutable. La lectura actual resuelve vigencia sin escribir historia; Refresh Apply crea un sucesor DRAFT. Se requiere revisión independiente según la política capturada, y los participantes en la preparación no pueden eludirla editando SoD.

La madurez y la calidad de evidencia tienen escalas configurables, separadas de confianza. El vocabulario legado EVIDENCE_QUALITY_STATES contiene LOW_CONFIDENCE; no se migra ni reinterpreta evidencia histórica de Gate o Basic Data. La escala nueva evita esa ambigüedad.

## Integración y autoridad

FEL/PDRI, Commercial Strategy, Resource Planning, Risk Governance, Risk Readiness, Basic Data y Benefits aportan contexto de solo lectura. Owner Capability no reevalúa Basic Data ni modifica escenarios de recursos, riesgos, definición, Gate o FID. La disponibilidad del proveedor OWNER_CAPABILITY_READINESS_PROVIDER no agrega requisitos a políticas publicadas.

El registro Investment Evidence y su contrato normalizado se reutilizan. La evidencia elegible requiere evaluación COMPLETED READY, actual, no obsoleta y compatible con el proyecto y tenant. La integración futura con Management Case se limita a una referencia en una nueva revisión Business Case; no se alteran revisiones completadas.

## Navegación y seguridad

Se agregan pantallas a la fase existente de definición y caso de inversión, sin crear otra fase ni ampliar App.tsx. strategicNavigationBlueprint.ts conserva la autoridad de navegación. ADMIN configura y publica políticas; USER prepara y revisa evaluaciones. El backend exige permisos y alcance para cada ruta. Las rutas genéricas de configuración rechazan mutaciones del nuevo tipo, impidiendo el bypass de SoD, ETag e idempotencia.

## Consecuencias y límites

El denominador es el número exacto de requisitos aplicables. La cobertura no oculta bloqueos críticos. La mitigación externa puede satisfacer una brecha sólo si la política lo acepta y existe evidencia gobernada. No se implementan HR, staffing, Contractor Capability, Operational Readiness ni QRA. El siguiente incremento debe decidirse con la matriz de prerrequisitos y no se ejecuta automáticamente.
