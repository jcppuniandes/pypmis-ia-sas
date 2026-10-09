# ADR Wave 2B Risk Governance and Basic Data Readiness

## Baseline

La implementación comienza sobre `main`, HEAD `9cb0969abb5d48cc25b0c6a935b11e6bd7afd16f`, con cambios locales anteriores preservados. Alembic presenta una cabeza única `20261005_0064`. Wave 3A declara `PERIODIC_PORTFOLIO_REVIEW_AND_GOVERNANCE_CYCLE_RELEASE_VALIDATED` y `READY_FOR_GOVERNED_PERIODIC_PORTFOLIO_REVIEW`. El diff previo se conserva en `outputs/.qa/wave2b-risk-basic-data/baseline.diff`; no equivale a un diff exclusivo de Wave 2B.

## Decisión

Se implementan dos dominios separados. Risk Governance administra políticas empresariales reutilizables de capacidad, apetito y umbrales, almacenadas en `AdminConfiguration`. Basic Data gobierna metadatos de evidencia técnica y evaluaciones versionadas del Workspace PROJECT canónico. Los requisitos y taxonomías de Basic Data también reutilizan `AdminConfiguration`; únicamente su evidencia viva requiere persistencia propia.

Las políticas publicadas se resuelven en backend por jerarquía autorizada, aplicabilidad y fecha efectiva. No se ejecutan expresiones libres. Las evaluaciones completadas congelan configuración, contexto FEL/PDRI, estados de los datos, denominador exacto, brechas y referencias con hash. La lectura histórica no reinterpreta fuentes actuales. La lectura de readiness actual verifica cambios materiales y caducidad sin reescribir el snapshot histórico.

Se reutilizan `AdminNumberSequence`, `SecurityEvent`, RBAC, control de versión, idempotencia, vocabulario de calidad de Gate07J-EVID-2, registro de proveedores y `strategicNavigationBlueprint.ts`. Se extienden los roles de definición existentes para separar preparación/validación de revisión final. No se amplía `App.tsx`.

## Autoridad y límites

Risk Governance no crea Risk Register, Risk Readiness ni decisiones Gate. Basic Data no modifica FEL, PDRI, Business Case, FIN, permisos, paquetes Gate, FID, asignación de capital o Portfolio Review. La disponibilidad de un proveedor Basic Data no añade requisitos a políticas Gate publicadas. El acceso USER a Risk Governance es de solo lectura; ADMIN configura políticas, mientras USER mantiene evidencia viva.

No se implementan QRA, simulaciones, P-values, contingencias, reservas, Owner Capability, Operational Readiness, ejecución de Procurement o Project Delivery. La recomendación siguiente será una sola, sustentada en la comparación entre Owner Capability y los prerrequisitos de QRA, sin implementarla automáticamente.

## Validación de cierre

El release aprobó evidencia SQLite y PostgreSQL, migración reversible 0064 → 0065 → 0064 → 0065 sobre superficies aisladas, scope/SoD/ETag/idempotencia, exactitud de cobertura y staleness, 94 regresiones de los dominios anteriores, 38 pruebas frontend y dos recorridos Chromium reales que cubren USER y ambas superficies ADMIN. Se cerró y probó adicionalmente el bypass de create/PATCH/clone/publish por la API genérica: los kinds Risk/Basic requieren su autoridad dedicada, con HTTP 409 y sin escrituras. Ocho casos aprobaron en cada motor y Chromium verificó seis intentos legacy ADMIN.

Estado local: `RISK_GOVERNANCE_AND_BASIC_DATA_READINESS_RELEASE_VALIDATED`; output: `READY_FOR_GOVERNED_RISK_APPETITE_AND_BASIC_DATA_EVIDENCE`; provider: `AVAILABLE`. Evidencias, limitaciones y los 73 criterios están en `docs/77-wave2b-risk-governance-basic-data-release.md`. No se afirma CI remoto ni certificación de producción. La única recomendación siguiente es Wave 3B Owner Capability Readiness, sin implementarla.
