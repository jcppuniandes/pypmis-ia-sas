# Resumen de estado actual frente a instructivos Unifier 26

Fecha: 14 de mayo de 2026

Aplicacion evaluada: P&Pmis Ai SaaS

Fuentes base:

- Analisis consultivo Oracle Primavera Unifier Version 26.
- Instructivo de configuracion Activity Sheet y WBS Sheet desde P6.
- Instructivo de alineacion CBS, WBS y FBS/Fund Codes.

## 1. Resumen ejecutivo

La app ya tiene una base funcional alineada con los instructivos de control de proyectos: proyecto autorizado, configuracion operativa, carga controlada de cronogramas P6 XML/XER, Activity Sheet, WBS, CBS, FBS/Funding, cuentas de control, matriz integrada, procesos BP, SOV contractual, Commitment Funding, Rate Sheet, Recost, reportes de funding, baseline y cierre financiero.

Ademas, el bloque recomendado de endurecimiento productivo ya quedo implementado: aprobaciones configurables por rol, permisos por BP, edicion versionada de line items, exportacion XLSX/PDF de conciliacion, historico de recost y cobertura visual/frontend focalizada. En esta etapa tambien se agrego un AI Control Auditor read-only, de bajo costo, que prioriza hallazgos sobre politicas BP, recost, funding y conciliacion sin modificar datos automaticamente.

## 2. Estado actual de la app

La app esta levantada localmente con Docker.

- Frontend: http://localhost:5173
- API health: http://localhost:8000/api/v1/health/ready
- Login demo recomendado: ana.control@demo.local / 1234

Servicios activos:

- frontend
- api
- worker
- beat
- db
- redis

La API responde correctamente en health check y el frontend carga HTML desde el puerto 5173.

## 3. Cobertura frente a los instructivos

| Area del instructivo | Estado actual | Comentario |
| --- | --- | --- |
| Proyecto/Shell antes de Activity Sheet | Cubierto | La app usa Project Operational Setup como compuerta antes de cargar Activity Sheet. |
| Permisos, modulos, Cost Sheet, Funding Sheet y mapeo P6 | Cubierto parcial | La compuerta valida flags de readiness; todavia falta una administracion visual mas granular por modulo. |
| Activity Sheet desde P6 | Cubierto inicial | Se cargan XML/XER, se crea Activity Sheet y se mantiene trazabilidad con Schedule Import. |
| WBS Sheet asociado a Activity Sheet | Cubierto inicial | Se agrego vista de WBS Sheet por Activity Sheet con roll-up de actividades, cuentas de control, costo planeado y PV. |
| CBS como eje de costos | Cubierto parcial | Hay Cost Breakdown Structure, Cost Codes y Cost Sheet por cuenta de control. Falta Cost Sheet tipo Unifier con columnas configurables completas. |
| FBS/Funding Sheet | Cubierto parcial | Hay Funding Sources/FBS, saldos, disponibilidad y forecast vs funding. Falta Funding Sheet transaccional mas detallada. |
| Cuentas de control | Cubierto | La cuenta de control integra WBS, CBS, actividad, funding, contrato, responsable y forecast. |
| BP CBS + Fund Code | Cubierto MVP | Se agrego proceso BP-CBS-FUND con line items, workflow y validacion de disponibilidad FBS. |
| BP CBS + WBS Code | Cubierto MVP | Se agrego proceso BP-CBS-WBS con roll-up a Cost Code y Budget por cuenta de control. |
| Base Commit, Change Commit y SOV | Cubierto MVP | Contratos y SOV por linea validan CBS obligatorio y cuenta de control cuando aplica. |
| Commitment Funding Sheet | Cubierto MVP | Se agregaron lineas de asignacion de fondos por contrato/SOV/FBS. |
| Rate Sheet y Recost | Cubierto MVP | Se agrego Rate Sheet por CBS y recost de Activity Sheet con actualizacion de planned cost/PV. |
| Reportes de conciliacion | Cubierto MVP | Se agrego reporte WBS-CBS-FBS-contrato-cuenta de control con budget, SOV, funding y forecast. |
| Aprobaciones configurables por rol | Cubierto inicial | Se agregaron politicas por BP/proceso/accion con rol requerido y permission key. |
| Edicion y versionado de line items | Cubierto inicial | Los BP line items se consultan, editan con expected_version y guardan revisiones historicas. |
| Exportacion conciliacion | Cubierto inicial | El reporte de conciliacion exporta XLSX y PDF desde API y UI. |
| Historico de recost | Cubierto inicial | Cada recost crea run y lineas de delta por actividad. |
| Agente auditor de control | Cubierto inicial | AI Control Auditor ejecuta revision read-only, persiste corridas y hallazgos priorizados. |

## 4. Trabajo realizado hoy

Se revisaron los tres instructivos y se contrastaron contra el repositorio. La conclusion fue que el sistema ya tenia una base fuerte de control integrado, pero faltaba hacer mas visible y operacional el tramo Activity Sheet - WBS Sheet.

Se implemento el siguiente salto funcional:

- Enriquecimiento de filas de Activity Sheet con costo planeado, valor planeado, porcentaje planeado, CBS, cuenta de control, estado de mapeo y nota de revision.
- Nuevo endpoint de WBS Sheet por Activity Sheet:
  - GET /api/v1/projects/{project_id}/activity-sheets/{activity_sheet_id}/wbs-sheet
- Vista frontend en Project Setup para mostrar WBS Sheet con:
  - WBS Code
  - nombre WBS
  - numero de actividades
  - numero de cuentas de control
  - costo planeado
  - valor planeado
  - actividades sin mapeo o por revisar
- Prueba backend focalizada pasando para Activity Sheet enriquecida y WBS Sheet.
- App levantada localmente y validada por HTTP.

Luego se implementaron las tres prioridades recomendadas:

- Prioridad 1:
  - BP CBS + Fund Code con line items, workflow, auditoria y bloqueo por fondos insuficientes.
  - BP CBS + WBS Code con line items, workflow, creacion/actualizacion de Cost Codes, Budget y roll-up por WBS/CBS.
  - UI con detalle de filas Activity Sheet: actividad, WBS, cuenta de control, CBS, planned cost, planned value y estado de mapeo.
- Prioridad 2:
  - SOV por contrato con CBS obligatorio y validacion de cuenta de control cuando aplica.
  - Commitment Funding Lines para asignar fondos a contrato/SOV/FBS.
  - Vista operacional en Integrated Control para crear CBS, revisar Cost Codes y ejecutar BP de asignacion.
- Prioridad 3:
  - Rate Sheet por CBS y recost del ultimo Activity Sheet.
  - Reporte de conciliacion por WBS, CBS, FBS, contrato y cuenta de control.
  - Pruebas frontend estables en Docker, suite backend completa y build frontend verificados.

Finalmente se implemento el bloque de endurecimiento productivo solicitado:

- Aprobaciones configurables por rol:
  - Politicas por `process_code` y `action` para BP CBS-WBS y BP CBS-Fund.
  - Validacion de `required_role` y `permission_key` antes de ejecutar acciones de workflow.
- Permisos por BP:
  - Los endpoints de configuracion requieren `can_configure`.
  - La edicion de line items y recost requiere `can_capture_cost`.
  - Las acciones de workflow respetan la politica especifica del BP cuando existe.
- Edicion y versionado de line items:
  - Consulta de line items por proceso.
  - Edicion con control optimista por `expected_version`.
  - Revision historica con monto, cantidad, descripcion, estado, usuario y nota de cambio.
- Exportacion de conciliacion:
  - Export XLSX.
  - Export PDF.
  - Botones en UI Integrated Control.
- Historico de recost:
  - Run incremental por Activity Sheet.
  - Total de filas actualizadas, planned cost y planned value.
  - Lineas historicas con costo/PV anterior y nuevo.
- Mayor cobertura visual:
  - Prueba frontend que renderiza BP Permissions, Line Versions, Export XLSX/PDF y Recost History.

Despues se agrego un agente auditor de bajo costo:

- AI Control Auditor:
  - Modo read-only.
  - Motor deterministico `deterministic-control-audit-v1`, sin costo de modelo externo en el MVP.
  - Persistencia de corridas y hallazgos.
  - Score de control de 0 a 100.
  - Hallazgos por severidad, categoria, evidencia, recomendacion y rol responsable.
- Checks iniciales:
  - BP CBS-WBS/BP CBS-Fund activos sin politica `approve_baseline`.
  - Activity Sheet con Rate Sheet activa pero sin corrida de recost.
  - Forecast superior a funding disponible.
  - Diferencias budget vs forecast en conciliacion.
  - Revisiones de line items para visibilidad de auditoria.
- UI:
  - Panel AI Control Auditor dentro de Integrated Control.
  - Boton Run Audit.
  - Resumen, score, modelo usado y top findings.

## 5. Como se usa actualmente

### 5.1 Ingreso

1. Abrir http://localhost:5173
2. Iniciar sesion con:
   - usuario: ana.control@demo.local
   - password: 1234
3. Seleccionar o revisar el proyecto demo disponible.

### 5.2 Revisar configuracion operativa

1. Entrar al flujo Project Setup.
2. Revisar Operational Readiness.
3. Validar que esten marcados:
   - Permissions
   - Modules
   - Cost Sheet
   - Funding Sheet
   - P6 Mapping
4. Si la configuracion no esta lista, la app bloquea la carga controlada de Activity Sheet.

### 5.3 Cargar Activity Sheet

1. En Project Setup, ubicar Activity Sheet.
2. Cargar archivo P6 XML o XER.
3. La app ejecuta la ingesta, valida calidad del cronograma y crea Activity Sheet.
4. Si el setup operativo no esta listo, el sistema devuelve bloqueo por readiness.

### 5.4 Revisar WBS Sheet

1. Despues de cargar Activity Sheet, revisar el panel WBS Sheet.
2. Confirmar que aparezcan las WBS importadas.
3. Revisar:
   - actividades por WBS
   - cuentas de control asociadas
   - costo planeado
   - planned value
   - filas que requieren revision

### 5.5 Revisar control integrado

1. Entrar a Integrated Control.
2. Revisar Initial FBS para fuentes de financiacion.
3. Revisar Funding Alerts para brechas forecast vs fondos disponibles.
4. Revisar Traceability para ver la matriz FBS - WBS - AWP - Control Account - CBS - Cost Code.
5. Crear CBS operativos cuando se necesite completar la estructura de costos.
6. Seleccionar CBS, FBS, cuenta de control, WBS y monto.
7. Ejecutar BP CBS-Fund para asignacion de fondos por CBS.
8. Ejecutar BP CBS-WBS para crear la transaccion costo-alcance y el Cost Code.
9. Usar Approve Baseline cuando la base integrada este completa.

### 5.6 Revisar costos y funding

1. Entrar a Costs o Dashboard.
2. Revisar CBS Cost Codes.
3. Revisar FBS Funding Codes.
4. Confirmar que compromisos, forecast y fondos disponibles esten alineados.

### 5.7 Crear SOV y Commitment Funding

1. En Integrated Control, seleccionar contrato, CBS, FBS, cuenta de control y WBS.
2. Diligenciar numero de linea SOV, descripcion y monto.
3. Usar Create SOV Funding.
4. La app crea la linea SOV y la asignacion de Commitment Funding contra el FBS seleccionado.

### 5.8 Crear Rate Sheet y ejecutar Recost

1. En Integrated Control, ubicar Rate / Recost.
2. Crear una Rate Sheet con codigo, CBS, multiplicador y rate unitario.
3. Usar Recost Latest para recalcular el ultimo Activity Sheet.
4. Revisar Activity Rows y Reconciliation para confirmar planned cost, planned value y forecast.

### 5.9 Configurar politicas BP por rol

1. En Integrated Control, ubicar BP Permissions.
2. Seleccionar proceso:
   - BP CBS-WBS
   - BP CBS-Fund
3. Seleccionar accion:
   - Approve
   - Reject
   - Close
4. Seleccionar rol requerido y permission key.
5. Usar Save Policy.
6. La siguiente accion de workflow para ese BP valida primero la politica configurada.

### 5.10 Editar line items con version

1. En Integrated Control, ubicar Line Versions.
2. Seleccionar el line item del BP reciente.
3. Ajustar monto, cantidad o descripcion.
4. Registrar Change Note.
5. Usar Save Version.
6. La app rechaza ediciones con version obsoleta y guarda la revision historica.

### 5.11 Exportar conciliacion

1. En Integrated Control, ubicar Reconciliation.
2. Usar Export XLSX para entregar archivo Excel.
3. Usar Export PDF para entregar resumen PDF.
4. Ambos archivos salen desde la API autenticada.

### 5.12 Ejecutar AI Control Auditor

1. En Integrated Control, ubicar AI Control Auditor.
2. Revisar el ultimo score y resumen si ya existe una corrida.
3. Usar Run Audit.
4. Revisar los hallazgos:
   - severidad
   - categoria
   - evidencia
   - recomendacion
   - rol responsable
5. El agente no cambia datos; solo recomienda acciones para el equipo de control.

Propuesta operativa del agente:

| Componente | Propuesta | Valor agregado |
|---|---|---|
| Funcion principal | Auditor read-only de control integrado Unifier | Detecta brechas antes de aprobar baseline, recost o conciliacion. |
| Modelo recomendado | Reglas deterministicas locales en MVP; modelo mini/haiku opcional solo para redactar sintesis | Costo casi cero en la revision base y mejor comunicacion cuando se necesite. |
| Entradas | Activity Sheet, WBS/CBS/FBS, BP policies, line items, recost history y reconciliation report | Usa datos ya capturados por la app, sin pedir doble digitacion. |
| Salidas | Score 0-100, hallazgos priorizados, evidencia y recomendacion por rol | Convierte controles dispersos en una lista accionable. |
| Seguridad | No ejecuta cambios automaticos, no aprueba, no edita registros | Mantiene decisiones humanas y trazabilidad formal. |
| Evolucion viable | Sintesis narrativa con modelo economico y agenda de seguimiento por responsable | Agrega valor gerencial sin depender de un modelo caro para calcular controles. |

## 6. Prioridades implementadas

Prioridad 1:

- Implementada.
- Endpoints principales:
  - POST /api/v1/projects/{project_id}/business-processes/cbs-fund
  - POST /api/v1/projects/{project_id}/business-processes/cbs-wbs
  - GET /api/v1/projects/{project_id}/activity-sheets/{activity_sheet_id}/rows

Prioridad 2:

- Implementada.
- Endpoints principales:
  - POST /api/v1/projects/{project_id}/contracts/{contract_id}/sov-lines
  - GET /api/v1/projects/{project_id}/contracts/{contract_id}/sov-lines
  - POST /api/v1/projects/{project_id}/commitment-funding-lines
  - GET /api/v1/projects/{project_id}/contracts/{contract_id}/commitment-funding-lines
  - GET/POST /api/v1/projects/{project_id}/cbs

Prioridad 3:

- Implementada.
- Endpoints principales:
  - GET/POST /api/v1/projects/{project_id}/rate-sheets
  - POST /api/v1/projects/{project_id}/activity-sheets/{activity_sheet_id}/recost
  - GET /api/v1/projects/{project_id}/reconciliation-report

Endurecimiento productivo:

- Implementado.
- Endpoints principales:
  - GET/POST /api/v1/projects/{project_id}/business-process-policies
  - GET /api/v1/projects/{project_id}/business-processes/{process_id}/line-items
  - PATCH /api/v1/projects/{project_id}/business-process-line-items/{line_item_id}
  - GET /api/v1/projects/{project_id}/business-process-line-items/{line_item_id}/revisions
  - GET /api/v1/projects/{project_id}/reconciliation-report/export?format=xlsx
  - GET /api/v1/projects/{project_id}/reconciliation-report/export?format=pdf
  - GET /api/v1/projects/{project_id}/activity-sheets/{activity_sheet_id}/recost-runs

Agente auditor:

- Implementado.
- Endpoints principales:
  - POST /api/v1/projects/{project_id}/agents/control-audit/run
  - GET /api/v1/projects/{project_id}/agents/control-audit/runs
- Modelo/costo:
  - MVP con reglas deterministicas locales.
  - No consume tokens externos.
  - Se puede evolucionar a modelo mini/haiku solo para redactar sintesis, manteniendo los hallazgos calculados por reglas.

## 7. Verificacion tecnica

- Backend: docker compose run --rm api pytest -q
  - Resultado: 105 pruebas pasando.
- Frontend: docker compose run --rm frontend npm test -- --run
  - Resultado: 25 pruebas pasando.
- Frontend build: docker compose run --rm frontend npm run build
  - Resultado: TypeScript y Vite compilan correctamente.
- Prueba focalizada nueva:
  - backend/tests/test_unifier_priority_flow.py
  - Cubre BP CBS-Fund, BP CBS-WBS, SOV, Commitment Funding, Rate Sheet, Recost, Reconciliation, policies, versionado, exports y recost history.
- Prueba visual/frontend nueva:
  - frontend/tests/AppFlow.test.tsx
  - Cubre render de BP Permissions, Line Versions, Export XLSX/PDF, Recost History y AI Control Auditor.
- Prueba backend del agente:
  - backend/tests/test_unifier_priority_flow.py
  - Cubre corrida del agente, persistencia de historial y deteccion de BP sin politica y recost pendiente.

## 8. Conclusion

La app esta en un punto funcional de MVP tecnico avanzado para el flujo de instructivos. Ya puede demostrar el orden correcto: proyecto configurado, cronograma cargado, Activity Sheet creada, WBS Sheet y filas detalladas, CBS/FBS/cuenta de control integradas, procesos BP, SOV, Commitment Funding, Rate Sheet, Recost, conciliacion, politicas por rol, line items versionados, exports, recost history y agente auditor read-only.

El siguiente bloque recomendado seria preparar operacion productiva formal: migraciones aplicadas en ambiente objetivo, matriz completa de roles por cliente, pruebas E2E con navegador real en pipeline, respaldos, hardening de seguridad/observabilidad y evolucion controlada del agente para sintesis con modelo economico opcional.
