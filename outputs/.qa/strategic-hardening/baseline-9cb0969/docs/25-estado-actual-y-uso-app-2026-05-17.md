# Estado actual y uso de P&Pmis Ai SaaS

Fecha de corte: 2026-05-17

Este reporte resume el estado actual de la app, su cobertura frente a los instructivos revisados de Primavera Unifier 26, la forma de uso operativa y el siguiente salto recomendado para ejecutar el plan multi-tenant guiado.

## 1. Resumen ejecutivo

| Tema | Estado | Detalle |
|---|---|---|
| App local | Operativa | Frontend en `http://localhost:5173` y API readiness en `http://localhost:8000/api/v1/health/ready`. |
| Alineacion con instructivos | MVP avanzado | Cubre proyecto, setup operativo, XML/XER, Activity Sheet, WBS Sheet, CBS, FBS, cuentas de control, BP, SOV, funding, rate sheet, recost y conciliacion. |
| Endurecimiento productivo | Implementado inicial | Hay aprobaciones por rol, permisos por BP, line items versionados, exports XLSX/PDF, recost history, E2E con navegador y controles de seguridad/observabilidad. |
| Agente AWP | Implementado inicial | Perfil Senior AWP Packaging Advisor crea paquetes draft CWA/CWP/IWP desde control accounts y deja constraints para revision humana. |
| Flujo guiado multi-tenant | Plan listo | El plan quedo documentado; para ejecutarlo recomiendo opcion 1, Subagent-Driven, con backend, parser, frontend y verificacion en paralelo controlado. |

## 2. Estado operativo actual

| Componente | Estado | Evidencia o uso |
|---|---|---|
| Frontend | Arriba | URL local `http://localhost:5173`. |
| API | Arriba | Readiness `GET /api/v1/health/ready` responde 200. |
| Base de datos | Saludable | Servicio Docker `db` en estado healthy. |
| Redis | Saludable | Servicio Docker `redis` en estado healthy. |
| Login demo | Disponible | Usuario recomendado `ana.control@demo.local`; clave local `1234`; tenant `demo-energy` cuando aplique. |
| Validacion funcional registrada | Aprobada | Backend enfocado 26 tests, frontend AppFlow 10 tests, build frontend y Playwright Chromium fueron verificados en la etapa anterior. |
| Riesgo conocido | Pendiente menor | Revisar vulnerabilidades moderadas de `npm audit` y warning de chunks grandes de Vite antes de produccion formal. |

## 3. Cobertura frente a instructivos

| Area del instructivo | Estado | Implementacion actual |
|---|---|---|
| Proyecto y shell | Cubierto | La app exige proyecto y Project Operational Setup antes del flujo de control. |
| Activity Sheet desde P6 | Cubierto inicial | Ingesta XML/XER, calidad de cronograma, baseline version y Activity Sheet trazable. |
| WBS Sheet | Cubierto inicial | Vista WBS con roll-up de actividades, cuentas de control, costo planeado y planned value. |
| CBS | Cubierto parcial avanzado | CBS, Cost Codes, Cost Sheet por cuenta de control y BP CBS-WBS. |
| FBS/Funding | Cubierto parcial avanzado | Funding Sources/FBS, disponibilidad, Commitment Funding y alertas forecast vs fondos. |
| Cuentas de control | Cubierto | Integran WBS, CBS, actividad, funding, contrato, responsable y forecast. |
| Business Processes | Cubierto MVP | BP CBS-Fund, BP CBS-WBS, politicas por rol, workflow, auditoria y line items. |
| SOV y compromisos | Cubierto MVP | Lineas SOV con CBS obligatorio y funding por contrato/SOV/FBS. |
| Rate Sheet y Recost | Cubierto MVP | Rate Sheet por CBS, recost del ultimo Activity Sheet e historico de runs y deltas. |
| Conciliacion | Cubierto inicial | Reporte WBS-CBS-FBS-contrato-cuenta de control con export XLSX y PDF. |
| AWP | Cubierto inicial | Work packages CWA/CWP/IWP, readiness, constraints y draft packages generados por agente. |
| Operacion productiva | Cubierto inicial | Migraciones, role matrix, backups con checksum, restore, logs JSON, metricas protegidas y pipeline E2E. |

## 4. Capacidades disponibles por modulo

| Modulo | Que hace | Como se valida |
|---|---|---|
| Login y tenant | Autenticacion JWT y datos demo por tenant. | Entrar con usuario demo y revisar proyecto activo. |
| Project Setup | Configura permisos, modulos, cost sheet, funding sheet y P6 mapping. | Operational Readiness debe estar completo antes de cargar cronograma. |
| Schedule/Baseline | Carga XML/XER, genera baseline y quality gate. | Revisar baseline, data date, calidad y mapping. |
| Activity/WBS Sheet | Muestra filas y roll-up WBS desde cronograma. | Revisar actividades sin mapping y costo planeado. |
| Integrated Control | Opera matriz FBS-WBS-AWP-Control Account-CBS-Cost Code. | Revisar Traceability, Funding Alerts, BP y reconciliacion. |
| BP Permissions | Define aprobaciones por proceso, accion y rol. | Crear politica para BP CBS-WBS o BP CBS-Fund y probar workflow. |
| Line Versions | Edita line items con expected_version y revision historica. | Revisar versiones por monto, cantidad, estado, usuario y nota. |
| Reconciliation Exports | Exporta conciliacion a XLSX y PDF. | Usar botones de export en Integrated Control. |
| Recost History | Guarda corridas de recost y cambios por actividad. | Ejecutar Recost Latest y revisar run historico. |
| AI Control Auditor | Auditor read-only de brechas de control integrado. | Usar Run Audit y revisar score, severidad, evidencia y recomendacion. |
| Senior AWP Packaging Advisor | Propone paquetes draft AWP con criterio senior. | Usar Create Draft Packages y revisar Work Packages. |
| Work Packages | Gestiona CWA/CWP/EWP/PWP/IWP y constraints. | Abrir Work Packages, revisar readiness y crear/cerrar constraints. |

## 5. Como se usa la app

| Paso | Accion del usuario | Resultado esperado |
|---|---|---|
| 1 | Abrir `http://localhost:5173`. | Se muestra login. |
| 2 | Ingresar `ana.control@demo.local` con clave `1234`. | Se carga el workspace del tenant demo. |
| 3 | Seleccionar proyecto o crear uno desde Admin/Project. | Proyecto activo con equipo y roles. |
| 4 | Ir a Project Setup y completar Operational Readiness. | Quedan habilitados permisos, modulos, cost sheet, funding sheet y P6 mapping. |
| 5 | Cargar cronograma XML/XER. | Se crea Schedule Import, baseline version, Activity Sheet y WBS Sheet. |
| 6 | Revisar WBS Sheet y Activity Rows. | Se identifican actividades sin mapping, costos y planned value. |
| 7 | Entrar a Integrated Control. | Se visualiza matriz integrada, funding alerts y trazabilidad. |
| 8 | Crear CBS, FBS, SOV, Commitment Funding o BP segun brecha. | Se completan estructura de costos, fondos y compromisos. |
| 9 | Configurar BP Permissions. | Las acciones quedan controladas por rol y permission key. |
| 10 | Editar line items cuando aplique. | Se guarda nueva version sin perder historial. |
| 11 | Ejecutar Rate Sheet y Recost Latest. | Se recalculan costos del Activity Sheet y queda historico de recost. |
| 12 | Exportar Reconciliation XLSX/PDF. | Se obtiene evidencia de conciliacion para revision o comite. |
| 13 | Ejecutar Run Audit. | El auditor muestra score, hallazgos, severidad y recomendaciones. |
| 14 | Ejecutar Create Draft Packages. | El agente genera CWA/CWP/IWP draft si faltan y refresca el tablero. |
| 15 | Abrir Work Packages. | Alli se ven los paquetes draft creados y sus constraints. |
| 16 | Registrar constraints manuales. | El usuario ingresa restricciones por paquete, prioridad, fecha requerida, owner, estado y evidencia. |

## 6. Donde se ven los paquetes draft y constraints

| Elemento | Ubicacion en UI | Regla operativa |
|---|---|---|
| Boton de generacion | Integrated Control, panel AI Control Auditor, accion Create Draft Packages. | Solo propone drafts; no aprueba baseline ni libera trabajo a campo. |
| Paquetes draft | Vista Work Packages. | Aparecen como CWA/CWP/IWP con readiness `constraint_review` y progreso 0. |
| Constraints iniciales | Work Packages y constraint log del paquete. | El agente crea restricciones de documentos, materiales, seguridad/calidad, permisos y readiness. |
| Constraints manuales | Formulario de constraints por paquete. | El usuario las ingresa y mantiene; puede cerrar con evidencia cuando se resuelvan. |
| Historial del agente | AI Control Auditor run/finding history. | Registra que creo o salto paquetes para trazabilidad. |

## 7. Roles principales

| Rol | Funcion en la app | Permisos esperados |
|---|---|---|
| Control Manager | Aprueba baseline, gobierna flujo integrado y revisa auditoria. | Aprobar workflow, configurar y revisar todo el control. |
| Planner | Carga cronograma, revisa Activity/WBS Sheet y mapping. | Subir baseline, gestionar schedule y validar calidad. |
| Cost Controller | Opera CBS, costos, rate sheet, recost y conciliacion. | Capturar costo, ejecutar recost y revisar variaciones. |
| Contract Manager | Administra contratos, SOV, funding de compromisos y BP contractuales. | Gestionar contratos y compromisos. |
| Workface Planner | Revisa AWP, paquetes, readiness y constraints. | Crear paquetes, editar readiness y cerrar restricciones. |
| Field Engineer | Captura avance, evidencia y restricciones de campo. | Capturar progreso y soportes. |
| Executive | Consulta estado, alertas, score y exposicion. | Lectura ejecutiva y seguimiento. |
| Document Controller | Gestiona documentos, adjuntos y evidencia. | Mantener document control y referencias de cierre. |

## 8. Operacion productiva formal

| Control | Estado | Uso recomendado |
|---|---|---|
| Migraciones | Preparado | Ejecutar `alembic upgrade head` y confirmar `alembic current` en ambiente objetivo. |
| Role matrix | Preparado | Usar `GET /api/v1/projects/{project_id}/role-matrix` para revisar permisos por cliente/proyecto. |
| E2E real | Preparado | Pipeline incluye Playwright con navegador real para login, Integrated Control, AWP y Work Packages. |
| Backups | Preparado | `deploy/vps/backup.sh` genera `.sql.gz` y `.sha256` con retencion. |
| Restore | Preparado | `deploy/vps/restore.sh <backup.sql.gz>` para validar recuperacion controlada. |
| Seguridad | Preparado | En produccion bloquear secretos debiles, wildcard hosts, docs publicas y auto-create schema. |
| Observabilidad | Preparado | Health/readiness, logs JSON, metricas con token y Sentry opcional. |
| Sintesis AI | Opcional | `AI_PROVIDER=disabled` por defecto; habilitar modelo economico solo para resumen, no decisiones. |

## 9. Siguiente salto recomendado

| Decision | Recomendacion | Motivo |
|---|---|---|
| Ejecucion del plan multi-tenant guiado | Opcion 1: Subagent-Driven | Permite dividir backend, parser XML/XER, frontend UX y verificacion sin bloquear el hilo principal. |
| Backend | Worker dedicado | Crear metadata de moneda/costos, endpoint guided-flow y confirmacion de moneda. |
| Parser | Worker dedicado | Detectar costos, fuente de costo, moneda y porcentaje cost-loaded en XML/XER. |
| Frontend | Worker dedicado | Crear command bar de tenant, drawer de proyecto, rail de proceso, next action y cost/currency gate. |
| Verificacion | Worker dedicado | Cubrir tests backend, Vitest, Playwright y evidencia de navegador real. |

## 10. Pendientes y riesgos residuales

| Riesgo | Impacto | Accion recomendada |
|---|---|---|
| Vulnerabilidades moderadas npm | Medio | Revisar `npm audit` y actualizar dependencias con prueba de regresion. |
| Chunks grandes Vite | Bajo/medio | Evaluar code splitting antes de usuarios reales con baja conectividad. |
| Password demo | Alto en produccion | No usar `1234` fuera de demo local; forzar secretos y usuarios reales. |
| AI externo | Costo y trazabilidad | Mantener deterministico por defecto y activar modelo economico solo para sintesis. |
| Guided flow aun planificado | Experiencia de usuario | Ejecutar el plan multi-tenant guiado para que el usuario siempre vea siguiente accion y bloqueos. |

## 11. Conclusion

La app esta en un estado funcional de MVP avanzado y ya demuestra el flujo central de los instructivos: proyecto configurado, cronograma cargado, Activity/WBS Sheet, control integrado CBS/FBS/WBS/AWP, BP con permisos, recost, conciliacion, agente auditor y AWP draft packaging. El salto correcto ahora es ejecutar el flujo guiado multi-tenant con opcion 1, Subagent-Driven, para convertir esa potencia funcional en una experiencia mas clara para operacion real.
