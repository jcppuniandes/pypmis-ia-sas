# Reutilización y límites de Ingeniería O2A

Punto de partida: `3889d71`, con los cierres O1A–O1C y O2 Master
Architecture ya incorporados. El ciclo transaccional de O2A se valida solo
en bases aisladas; no se migró la base habitual.

| Clasificación | Fuente existente | Decisión O2A |
|---|---|---|
| CANONICAL / REUSE | O1A OperationalProjectBinding, período, autorización, recibo idempotente | Workspace Project activo y módulo habilitado. Un vínculo explícito resuelve Project legado de CDE. No usar el ID legado como identidad canónica. |
| CANONICAL / REUSE | Documents, DocumentAttachment, DocumentTransmittal, DocumentReview | El archivo y el acceso se mantienen en CDE. Ingeniería fija la revisión y SHA del adjunto autorizado; ni una carga ni una revisión documental liberan IFC. |
| CANONICAL / EXTEND | AWP WorkPackage, CWA, PackageMapping, ExecutionConstraint y ReadinessAssessment | EWP y CWA conservan escritor. Ingeniería enlaza sus propias revisiones; el proveedor aporta evidencia a un assessment explícito. Una lectura no limpia restricciones ni libera paquetes. |
| CANONICAL / REUSE | ScopeItem, Scope Baseline y Plan Item publicado | Se resuelven IDs y revisión vigente por Project. No se crea Scope desde Ingeniería. |
| CANONICAL / REUSE | ScheduleRegister, ScheduleVersion importada, snapshot de WBS y actividades | Referencias exactas al Current aceptado. Una actividad sustituida requiere revisión; no se remapea por nombre y no se calcula CPM. |
| CANONICAL / EXTEND | ProgressMeasurement, evidencias, ForecastVersion y supuestos aprobados | Consumidores opt-in verifican el origen de Ingeniería por ID, hash y fecha en sus comandos existentes. No hay creación de mediciones o Forecast por un evento de Ingeniería. |
| CANONICAL / REUSE | Cost CBS, Cost Code y Control Account | Referencias operativas; no se reconoce Actual ni se cambia presupuesto o línea base. |
| REUSE | Workspace Navigator, CompactModuleHeader, ADMIN perfiles versionados y SecurityAssignment | Registro, revisiones, revisión/aprobación, IFC, mapeos, readiness, avance, look-ahead e historial en un espacio de trabajo. No hay cambio de App.tsx o del visor IFC. |
| KEEP_BEHIND_ADAPTER | IFC/BIM de Scope y CDE; consultas/clarificaciones de otros procesos | No se duplica BIM/CDE. No se promueve una aclaración de compras/contratos a un RFI técnico. |
| UNKNOWN / DIFERIDO | Autoridad transversal para RFI/TQ | No se agregó un escritor paralelo. El registro mínimo de interfaces conserva tipo, entregable y referencia a una fuente externa. |
| NUEVO | Engineering Deliverable, Revision, Review, Comment, Release, Design Package, Interface, Mapping e History | Autoridad técnica en módulo dedicado; tablas canónicas excluidas del bootstrap. Release IFC es hecho inmutable independiente de revisión aprobada. |

No se inició O2B ni se agregaron autoridades de Procurement, Materiales,
Logística, Contratos, SOV, compromisos, pagos o Commissioning.
