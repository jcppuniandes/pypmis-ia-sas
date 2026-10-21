# O1B-A — Revisión independiente acotada de seguridad y gobierno

Fecha de revisión: 20 de octubre de 2026 (America/Bogota).

## Alcance y límites

Inspección estática de `backend/app/modules/scope_foundation/service.py`,
`models.py`, `schemas.py`, `router.py`, la migración
`backend/alembic/versions/20261020_0070_scope_foundation.py` y la reutilización
de autorización/comandos en `backend/app/modules/operational_context/service.py`.
Se priorizaron aislamiento tenant/Project canónico, SoD, ETag, inmutabilidad,
cantidades fuente, asignaciones Scope/Plan, referencias históricas y modelos
derivados. La revisión no modificó código de producto ni datos.

Es una revisión acotada, no una auditoría exhaustiva, prueba de penetración,
aprobación de negocio ni certificación de seguridad del sistema completo.
Las líneas citadas corresponden al contenido verificado al cerrar esta revisión
y pueden desplazarse con ediciones posteriores.

## Hallazgos originales y correcciones inspeccionadas

### SR-01 · P1 · Unidad de Excel alterable mediante creación directa por API

Antes de la corrección, la validación de un Scope Item con fuente EXCEL
comprobaba importación, fila y `scope_code`, pero no exigía que `payload.unit`
coincidiera con la unidad de la fila staging. La creación conservaba la cantidad
fuente de Excel y podía etiquetarla con otra unidad elegida en el payload.
Por ejemplo, una fuente de 10 ea podía quedar expresada como cantidad fuente
10 m sin base de conversión explícita. El flujo UI de candidato no exponía
ese cambio; la API de creación directa sí lo permitía.

Corrección inspeccionada: `service.py`, línea 627, rechaza la discrepancia
con HTTP 422 y código `SCOPE_EXCEL_UNIT_MISMATCH_NO_SILENT_CONVERSION`.
La comparación con la unidad staging se encuentra inmediatamente antes.

Regresión añadida por el agente principal:
`backend/tests/test_scope_foundation_release.py`, línea 472,
`test_excel_direct_item_creation_rejects_silent_source_unit_conversion`.

### SR-02 · P2 · Publicación de Plan contra Scope histórico no vigente

Antes de la corrección, un Plan DRAFT creado contra un Scope vigente podía
publicarse después de aprobar una revisión que eliminara o reemplazara ese
Scope. La publicación reconciliaba las cantidades contra el Scope Item
histórico, que seguía APPROVED e inmutable, sin comprobar su pertenencia al
baseline actual. La creación de Plan sí realizaba esa comprobación.

Corrección inspeccionada: `publish_plan` en `service.py`, línea 1365, obtiene
el baseline actual, calcula sus IDs en la línea 1382 y, cuando la política
exige Scope aprobado, rechaza un Scope no aprobado o ausente del conjunto
actual con HTTP 409 `PLAN_CURRENT_APPROVED_SCOPE_REQUIRED` (línea 1388).
La política de cantidades y tolerancia continúa aplicándose después.

Regresión añadida por el agente principal:
`backend/tests/test_scope_foundation_release.py`, línea 512,
`test_plan_publication_revalidates_current_scope_after_approved_successor`.

## Otras comprobaciones acotadas

- `_get` (Scope `service.py`, línea 124) filtra por tenant y Project canónico;
  `_ready` (línea 148) reaplica permiso granular, operabilidad O1A y perfiles
  publicados antes de comandos materiales.
- La migración 0070 comprueba Project/tenant (línea 314), referencias entre
  Project (339), predecesores (345) y referencias históricas (353), además de
  guardar fuentes y snapshots inmutables.
- Los comandos materiales heredan la serialización mediante bloqueo de Tenant
  en `OperationalContextService._command` (líneas 1156 y 1159). No se confirmó
  la carrera aparente de asignaciones/baselines al existir esa serialización.
- La publicación de estrategia y perfil comprueba el editor material actual
  mediante receipts; la aprobación de baseline separa preparador y editores
  de candidatos del aprobador, conforme a la política SoD publicada.
- `create_derived` (Scope `service.py`, línea 1403) rechaza Plans SUPERSEDED
  (1412), objetos fuera del membership vinculado (1429) y restauraciones con
  objetos fuera del membership (1464). El snapshot conserva GUID, versión,
  hash de fuente y referencias de Scope/Plan sin modificar el IFC original.

No se encontraron otros defectos reproducibles de escalación tenant/proyecto,
bypass SoD, ETag, inmutabilidad o referencias derivadas en lo inspeccionado.
Esta afirmación se limita al alcance anterior; no equivale a ausencia global
de vulnerabilidades.

## Estado de validación al cerrar la revisión

Las dos correcciones están guardadas y fueron inspeccionadas estáticamente.
Las regresiones nuevas están en ejecución por el agente principal. Esta nota
no certifica sus resultados, no adelanta PASS ni cambia por sí misma la decisión
de release. La evidencia ejecutada y su resultado final deben consultarse en
el paquete de validación generado por el agente principal.

## Confirmación ejecutada posterior por el agente principal

La suite final `postgresql-release-final.xml` cerró con 83 casos aprobados,
sin errores, fallos ni omitidos. Incluye las dos regresiones anteriores.
Chromium `chromium-release4/browser-uat.json` cerró con diez comprobaciones
PASS sobre backend y bundle finales, con mallas web-ifc renderizadas en la
fuente original y la vista derivada. No quedan S1 o S2 abiertos en este alcance
revisado. Se mantienen los límites de escala y despliegue documentados.
