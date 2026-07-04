# Estado para produccion y guia de uso - Pypmis AI SaaS

Fecha de corte: 2026-05-17

Este informe resume el estado actual de Pypmis AI SaaS para una operacion productiva controlada, la evidencia de verificacion disponible y el paso a paso de uso para operar el flujo de control integrado frente a los instructivos de Primavera Unifier 26.

## 1. Resumen ejecutivo

| Tema | Estado | Detalle |
|---|---|---|
| Estado general | Listo para piloto productivo controlado | La app esta levantada, probada y con flujo guiado multi-tenant implementado. |
| Produccion formal | Condicionado | Puede pasar a ambiente objetivo si se aplican migraciones, secretos reales, backups, monitoreo y matriz de roles por cliente. |
| Frontend | Operativo | Disponible en `http://localhost:5173`; marca restaurada como Pypmis AI SaaS con logo arriba. |
| API | Operativa | Disponible en `http://localhost:8000`; readiness responde OK. |
| Base de datos | Operativa | Postgres healthy; Alembic en `20260515_0018 (head)`. |
| Redis | Operativo | Servicio healthy para cache y colas. |
| Flujo guiado | Implementado | Tenant, proyecto, pasos de control, bloqueos, siguiente accion y gate costo/moneda. |
| Agente AWP | Implementado inicial | Senior AWP Packaging Advisor propone paquetes draft y constraints para revision humana. |

## 2. Evidencia de verificacion fresca

| Verificacion | Resultado | Evidencia |
|---|---|---|
| Smoke operativo | OK | Health, liveness, readiness, observabilidad, headers de seguridad, login, proyectos, dashboard, Cost Manager, RFQ, document control, pilot readiness y frontend HTTP 200. |
| Readiness API | OK | `GET /api/v1/health/ready` responde ready. |
| Alembic | OK | `20260515_0018 (head)`. |
| Servicios Docker | OK | `api`, `frontend`, `db` y `redis` arriba; `api`, `db` y `redis` healthy. |
| Frontend build | OK | `npm run build` verificado despues de restaurar marca. |
| Frontend lint | OK | `npm run lint -- --max-warnings=0` verificado. |
| Frontend tests | OK | `AppFlow` y `LoginView`: 13 tests passed. |
| Verificacion visual | OK | Navegador integrado mostro logo, nombre Pypmis AI SaaS y workspace sin errores de consola. |
| Ultimos commits | OK | `6c7136b` marca restaurada; `5bcbc5e` flujo guiado multi-tenant. |

## 3. Estado por capacidad

| Capacidad | Estado para produccion | Observacion |
|---|---|---|
| Autenticacion y tenant | Piloto controlado | JWT operativo; antes de produccion usar usuarios reales, claves fuertes y politicas de sesion. |
| Multi-tenant | Preparado | Contexto de tenant visible y endpoints filtrados por tenant. |
| Proyecto | Preparado | Proyecto seleccionado desde command bar; drawer para crear proyecto sin tapar la operacion principal. |
| Operational setup | Preparado | Permisos, modulos, cost sheet, funding sheet y P6 mapping controlados. |
| XML/XER | Preparado | Ingesta cronograma, actividades, WBS, costos, moneda y quality findings. |
| Gate costo/moneda | Preparado | Bloquea baseline si falta costo o moneda confirmada. |
| Activity Sheet | Preparado | Filas de actividades, costo planeado y trazabilidad a WBS/CBS/control account. |
| WBS Sheet | Preparado | Roll-up WBS con actividad, planned value y brechas de mapping. |
| CBS/FBS | Preparado | CBS, cost codes, funding sources, FBS y cuentas de control integradas. |
| Business Processes | Preparado | BP CBS-WBS, BP CBS-Fund, permisos por BP, aprobaciones por rol y auditoria. |
| Line items | Preparado | Edicion con versionado, expected_version e historial. |
| Recost | Preparado | Rate Sheet, recost de Activity Sheet e historico de corridas. |
| Conciliacion | Preparado | Reporte integrado y export XLSX/PDF. |
| AWP | Preparado inicial | Paquetes CWA/CWP/IWP, readiness, constraints y propuesta draft del agente. |
| Observabilidad | Preparado | Health, readiness, logs JSON, metricas protegidas y smoke operativo. |
| Backups | Preparado | Scripts disponibles; falta programar ejecucion y prueba de restore en ambiente objetivo. |

## 4. Criterio de produccion

| Criterio | Estado | Decision |
|---|---|---|
| Funcionalidad core | Cumple | El flujo central de instructivos esta implementado y probado. |
| Pruebas automaticas | Cumple | Backend, frontend y E2E fueron verificados en esta rama; smoke fresco OK. |
| Migraciones | Cumple local | Head en `20260515_0018`; aplicar en ambiente objetivo antes de abrir usuarios. |
| Seguridad | Condicionado | Requiere secretos reales, bloqueo de credenciales demo, CORS/hosts definitivos y politica de rotacion. |
| Datos productivos | Condicionado | Requiere tenant/cliente real, matriz de roles y carga de catalogos base. |
| Backups | Condicionado | Requiere job programado, retencion, checksum y restore probado. |
| Observabilidad | Condicionado | Requiere destino de logs, alertas, metricas y Sentry/opcional por cliente. |
| AI externo | Opcional | Mantener deshabilitado o usar modelo economico solo para sintesis; no para aprobaciones. |
| Decision final | Go controlado | Recomendado para piloto productivo controlado, no para liberacion masiva sin hardening final. |

## 5. Paso a paso de uso principal

| Paso | Accion | Resultado esperado |
|---|---|---|
| 1 | Abrir `http://localhost:5173`. | Se muestra login con logo y nombre Pypmis AI SaaS. |
| 2 | Ingresar usuario demo `admin` o usuario asignado. | Entra al workspace del tenant. |
| 3 | Revisar la barra superior. | Se ve marca, tenant, proyecto activo, usuario y boton New Project. |
| 4 | Seleccionar proyecto en el command bar. | El dashboard y el flujo guiado cambian al proyecto activo. |
| 5 | Si se requiere, crear proyecto con New Project. | Se abre drawer lateral sin tapar el tablero. |
| 6 | Completar Project Setup. | Quedan definidos permisos, modulos, cost sheet, funding sheet y P6 mapping. |
| 7 | Ir al paso Schedule intake o Baseline. | Se prepara carga XML/XER. |
| 8 | Cargar cronograma XML/XER. | Se crea Schedule Import, Activity Sheet, WBS Sheet y baseline version. |
| 9 | Revisar el gate Cost and currency. | La app muestra moneda detectada, fuente, costo total y porcentaje cost-loaded. |
| 10 | Confirmar moneda cuando aplique. | Baseline deja de estar bloqueado por moneda. |
| 11 | Revisar WBS/CBS/FBS mapping. | Se identifican brechas entre WBS, CBS, FBS y cuentas de control. |
| 12 | Crear o ajustar CBS, FBS y Control Accounts. | La matriz integrada queda trazable. |
| 13 | Configurar BP permissions. | Las acciones quedan controladas por rol y por Business Process. |
| 14 | Aprobar baseline solo si no hay bloqueos. | Se registra aprobacion con auditoria. |
| 15 | Capturar progreso y costos reales. | Se alimentan EV, AC, CPI, SPI y alertas. |
| 16 | Ejecutar Rate Sheet y Recost Latest. | Se recalcula costo del Activity Sheet y queda historico. |
| 17 | Exportar conciliacion XLSX/PDF. | Se obtiene evidencia para comite o revision. |
| 18 | Ejecutar Run Audit. | El auditor muestra score, hallazgos y recomendaciones. |
| 19 | Ejecutar Create Draft Packages. | El agente propone paquetes draft AWP cuando detecta brechas. |
| 20 | Abrir Work Packages. | Se ven paquetes CWA/CWP/IWP, readiness, POC y constraints. |
| 21 | Registrar constraints manuales. | El usuario ingresa restricciones, owner, prioridad, fecha y evidencia. |
| 22 | Cerrar constraints con evidencia. | El paquete puede avanzar en readiness. |

## 6. Uso del flujo guiado

| Elemento | Donde se ve | Como se usa |
|---|---|---|
| Marca de app | Barra superior blanca | Confirma que se esta en Pypmis AI SaaS. |
| Tenant command bar | Barra oscura superior | Cambia proyecto, crea proyecto y muestra tenant/usuario. |
| Guided Flow | Columna izquierda | Muestra pasos, estado y bloqueos. |
| Next action | Panel derecho | Sugiere la proxima accion operativa. |
| Cost and currency gate | Baseline | Bloquea baseline si falta costo o moneda confirmada. |
| Project Setup | Rail guiado | Configura prerequisitos operativos. |
| Integrated Control | Rail guiado | Opera matriz WBS-CBS-FBS-AWP-control account. |
| Work Packages | Rail guiado | Gestiona paquetes AWP y restricciones. |

## 7. Uso de paquetes draft AWP

| Elemento | Ubicacion | Regla |
|---|---|---|
| Boton Create Draft Packages | Integrated Control, panel AI Control Auditor | Ejecuta propuesta del agente Senior AWP Packaging Advisor. |
| Paquetes draft | Vista Work Packages | Aparecen como CWA/CWP/IWP con estado inicial de revision. |
| POC del paquete | Tarjetas o registro de Work Packages | Indica persona responsable o punto de contacto del paquete. |
| Constraints generadas | Work Packages | El agente crea restricciones iniciales de documentos, materiales, permisos, seguridad/calidad y readiness. |
| Constraints manuales | Formulario de Work Packages | El usuario las ingresa y mantiene; el agente no reemplaza la revision humana. |
| Historial | AI Control Auditor | Se registra si creo paquetes, si omitio duplicados y que hallazgos quedaron. |

## 8. Roles y responsabilidades

| Rol | Funcion principal | Uso en la app |
|---|---|---|
| Administrator | Configuracion de tenant, usuarios y roles | Mantiene matriz de roles y permisos por cliente. |
| Control Manager | Gobierno del flujo integrado | Aprueba baseline y revisa bloqueos. |
| Planner | Cronograma y P6 | Carga XML/XER y valida Activity/WBS Sheet. |
| Cost Controller | Costos, recost y conciliacion | Gestiona CBS, cost codes, rate sheet, recost y exportaciones. |
| Contract Manager | Contratos, SOV y funding | Mantiene compromisos, SOV y funding lines. |
| Workface Planner | AWP packaging y constraints | Revisa paquetes draft, readiness y restricciones. |
| Field Engineer | Avance y evidencia de campo | Registra progreso, soportes y restricciones operativas. |
| Document Controller | Evidencia documental | Mantiene document control, referencias y cierre. |
| Executive | Seguimiento ejecutivo | Consulta KPI, alertas y estado de readiness. |

## 9. Checklist antes de ambiente productivo objetivo

| Paso | Accion tecnica | Criterio de aceptacion |
|---|---|---|
| 1 | Configurar variables productivas. | No hay secretos demo ni wildcard hosts. |
| 2 | Ejecutar `alembic upgrade head`. | `alembic current` muestra `20260515_0018 (head)` o superior. |
| 3 | Cargar tenant/cliente real. | Tenant, usuarios y proyecto base existen. |
| 4 | Definir matriz de roles. | Cada rol tiene permisos, BP y owner claro. |
| 5 | Probar login real. | Usuario real entra y solo ve su tenant/proyecto. |
| 6 | Cargar cronograma real de prueba. | XML/XER genera Activity Sheet y WBS Sheet sin errores criticos. |
| 7 | Confirmar gate costo/moneda. | Baseline solo avanza con moneda y costos validos. |
| 8 | Configurar backups. | Backup, checksum, retencion y restore probado. |
| 9 | Activar observabilidad. | Logs, metricas, readiness y alertas disponibles. |
| 10 | Ejecutar E2E pipeline. | Login, Integrated Control, AWP y Work Packages pasan con navegador real. |
| 11 | Ejecutar smoke post-deploy. | Health, readiness, frontend, proyectos y dashboard OK. |
| 12 | Documentar criterio Go/No-Go. | Responsable de operacion aprueba salida controlada. |

## 10. Riesgos residuales

| Riesgo | Impacto | Mitigacion |
|---|---|---|
| Credenciales demo | Alto | No usar `1234` en produccion; rotar claves y usuarios. |
| Secretos y CORS | Alto | Definir dominios, allowed hosts y secretos fuertes. |
| Backup no probado | Alto | Ejecutar restore real antes de abrir operacion. |
| Datos reales mal mapeados | Medio/alto | Usar carga piloto y revisar WBS/CBS/FBS antes de aprobar baseline. |
| AI externo sin control | Medio | Mantener modelo deshabilitado o economico para sintesis, no para decisiones. |
| Dependencias npm | Medio | Revisar `npm audit` y actualizar con regresion controlada. |
| Performance con muchos proyectos | Medio | Medir payloads, paginar listas y aplicar cache si crece el volumen. |
| Cambio de proceso por cliente | Medio | Mantener role matrix y BP policies por tenant/proyecto. |

## 11. Estado final recomendado

| Decision | Recomendacion | Motivo |
|---|---|---|
| Usar en demo ejecutiva | Si | La app esta estable, guiada y visualmente identificada. |
| Usar en piloto productivo controlado | Si, con condiciones | Requiere secretos reales, backups, matriz de roles y smoke post-deploy. |
| Usar como produccion masiva | Todavia no | Falta hardening final de seguridad, observabilidad, despliegue y datos por cliente. |
| Siguiente salto | Preparar ambiente objetivo | Aplicar migraciones, roles, backups, E2E pipeline y control de cambios. |

## 12. Conclusion

Pypmis AI SaaS esta en estado de MVP avanzado listo para piloto productivo controlado. El flujo guiado multi-tenant ya reduce friccion operativa: muestra tenant, proyecto, bloqueos, gate de costo/moneda, siguiente accion y paquetes AWP draft. La app no debe considerarse produccion masiva hasta completar secretos, backups, restore, observabilidad y role matrix del cliente objetivo.
