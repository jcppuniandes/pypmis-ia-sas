# Software Design Document

## 1. Vision

P&Pmis Ai SaaS es una plataforma empresarial de Project Controls que digitaliza un sistema real de control de proyectos basado en AACE TCM. No gestiona tareas aisladas: captura la realidad del proyecto, integra schedule, costos, avance, documentos, cambios y reclamos, analiza el desempeno y convierte datos en decisiones tempranas.

## 2. Principio rector

El sistema implementa exactamente este flujo operativo:

```text
Planeacion -> Cuentas de Control -> Ejecucion -> Control Core -> Decision -> Retroalimentacion
```

La entrada maestra anterior al flujo operativo es obligatoria:

```text
Cronograma fuente XML/XER -> Schedule Intake -> Data Quality Gate -> Planeacion
```

El nucleo de control opera como loop continuo:

```text
CAPTURAR -> VALIDAR -> ANALIZAR -> ALERTAR -> DECIDIR -> ACTUAR -> REPETIR
```

## 3. Alcance funcional

La plataforma integra:

- Schedule Intake: importacion de cronogramas fuente XML/XER, validacion de data date, WBS, actividades, logica, calendarios, recursos, baseline y cost loading.
- Planeacion: WBS, actividades, logica, baseline, ruta critica y lookahead.
- Cost Control: CBS, BAC, cost loading y cuentas de control.
- Actual Cost Tracking: facturas, nomina, equipos, materiales y compromisos.
- Progress Capture: avance fisico, cantidades, recursos, reportes de campo y evidencias.
- EVM Engine: PV, EV, AC, SPI, CPI, SV, CV, EAC, ETC y VAC.
- Early Warning: deteccion, monitoreo, analisis, alerta y accion.
- Reporting: S-curves, KPI, variaciones, cash flow y semaforos.
- Change Management: desviacion, analisis, aprobacion y seguimiento.
- Claims / Forensic: eventos, causalidad, entitlement, impacto, quantum, productividad, evidencia y analisis forense.
- Contract Management: contratos, comunicaciones y eventos contractuales.
- Document Control: trazabilidad documental vinculada a todos los objetos.
- Advanced Work Packaging: path of construction, CWA, CWP, EWP, PWP, IWP, restricciones, readiness y liberacion al frente de trabajo.
- IA: explicacion de desviaciones, deteccion de riesgos, reportes y analisis de reclamos.

## 4. Reglas de integracion

Todo dato operativo debe poder conectarse con:

```text
schedule <-> cost <-> progress <-> documents <-> changes <-> claims
```

Ningun modulo debe operar como isla. La entidad integradora principal es `ControlAccount`, que conecta WBS, actividades, presupuesto, costos reales, progreso, KPI, alertas, cambios, eventos, documentos, reclamos y paquetes AWP. `WorkPackage` extiende esa integracion hacia CWA/CWP/EWP/PWP/IWP y readiness de frente de trabajo.

## 5. Tenancy y seguridad

La plataforma es SaaS-ready y multi-tenant desde el inicio. Cada entidad operacional incluye `tenant_id` y `project_id` cuando aplica. La API usa autenticacion Bearer JWT con claims de `tenant_id`, usuario y expiracion; en una fase posterior puede federarse con OIDC/SSO corporativo.

## 5.1 Conformidad TCM del dato de entrada

Para estar alineado con AACE TCM, el sistema debe controlar un plan aprobado, no una lista suelta de actividades. Por eso la fuente primaria de entrada es un cronograma fuente en XML/XER. Ese cronograma alimenta:

- WBS y actividades.
- Relaciones logicas FS, SS, FF y SF.
- Baseline y data date.
- Ruta critica y holguras.
- Recursos y cost loading.
- Mapeo a cuentas de control.

El Control Core no debe calcular EVM ni alertas sobre datos sin una version de cronograma validada.

## 5.2 Integracion AWP

AWP se implementa como capa de ejecucion planificada sobre el cronograma validado. El sistema deriva o registra paquetes de trabajo conectados a cuentas de control:

- CWA: area de construccion y path of construction.
- CWP: paquete de construccion ejecutable por area/disciplina.
- EWP: entregables de ingenieria requeridos por CWP/IWP.
- PWP: paquetes de procura/materiales que gobiernan readiness.
- IWP: paquete de instalacion liberable al frente de trabajo.

Cada paquete puede tener restricciones de ingenieria, materiales, permisos, seguridad, acceso y documentos. Las restricciones abiertas bloqueantes alimentan alertas, BP de readiness y decisiones del Control Core.

## 5.3 Claims y demostracion de entitlement

La capa de Claims opera como expediente tecnico-contractual. Para cambios, ordenes de cambio y reclamos EPC, el sistema incorpora una matriz de entitlement basada en RP120R-21 y RP130R-23:

- Base contractual y mecanismo de recuperacion.
- Evento, cambio o condicion modificada.
- Aviso y cumplimiento procedimental.
- Causalidad y responsabilidad.
- Impacto en plazo, costo o productividad.
- Quantum o calculo de danos.
- Mitigacion y segregacion de causas.
- Evidencia contemporanea vinculada.
- Para cumulative impact: poblacion de cambios, periodo impactado, productividad base, measured mile, factores de disrupcion, nexo causal y danos.

Cada elemento se registra como `ClaimEntitlementItem` con fuente metodologica, requisito, evaluacion, evidencia, estado, peso y puntaje. Esto permite convertir claims en decisiones trazables y no en narrativas aisladas.

## 6. Separacion decision / ejecucion

La arquitectura separa:

- Decision: evaluacion EVM, reglas de alerta, analisis de cambios, riesgo y recomendaciones IA.
- Ejecucion: acciones aprobadas, tareas de campo, actualizacion de forecast, comunicados contractuales y workflows.

Esto evita que el motor de analisis ejecute acciones automaticamente sin gobernanza.

## 7. Calidad transversal

Data Quality aplica a todos los registros capturados. El sistema valida completitud, consistencia, trazabilidad documental y coherencia temporal. Quality Control de obra se modela como evidencias, inspecciones y no conformidades vinculables a progreso, cambios y reclamos. Contract Management mantiene comunicaciones, eventos notificables y obligaciones que soportan claims.

## 8. MVP funcional

El MVP entrega:

- Schedule Intake para registrar importaciones XML/XER y validar que el cronograma sea la fuente inicial del sistema.
- AWP Readiness para registrar CWA/CWP/EWP/PWP/IWP, constraint log y liberacion al frente de trabajo.
- API FastAPI con modelo de dominio integrado.
- Base PostgreSQL con entidades TCM principales.
- Redis + Celery para procesos asincronos de control.
- Dashboard React con flujo TCM, Control Core, KPIs EVM, alertas, cambios, reclamos y documentos.
- Datos semilla de demostracion para un proyecto de control integrado.

## 9. No objetivos del MVP

- No reemplaza Primavera P6, ERP o EDMS; se integra con ellos en fases posteriores.
- No automatiza aprobaciones contractuales sin workflow humano.
- No toma decisiones por IA sin trazabilidad y aprobacion.
