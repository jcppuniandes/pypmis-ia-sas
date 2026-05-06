# Resumen, Analisis, Manual De Uso Y Paso A Paso Del Piloto

Fecha base: 2026-05-06

## Resumen Ejecutivo

P&Pmis Ai SaaS ya opera como una plataforma colaborativa en linea para Project Controls: multiusuario, multiproyecto, con roles por proyecto, auditoria, control de acceso, workflows, Plan de Control / PEP, ingestion de cronograma, cuentas de control, EVM, AWP, contratos, claims, documentos y readiness de piloto.

En esta fase se agrego un Cost Manager basico inspirado en Oracle Primavera Unifier:

- Cost Sheet por cuenta de control: BAC, PV, EV, incurrido desde actas de pago, comprometido desde contratos/ordenes de compra, variacion y CPI.
- Funding Sources: fondos aprobados o planeados por proyecto.
- Cash Flow: periodos con entradas, salidas, reales y forecast.
- Cost Manager Summary en dashboard, API y smoke test.
- Readiness de piloto actualizado para validar funding y cash flow en Fase 4.

Estado actual: la app queda lista para un piloto controlado, no para despliegue enterprise productivo. El piloto debe validar flujo real, colaboracion, datos, roles, tablero, decisiones y brechas de integracion.

## Analisis Frente A Oracle Primavera Unifier

| Area Unifier | Estado en P&Pmis Ai SaaS | Lectura |
| --- | --- | --- |
| Cost Manager | MVP piloto implementado: Cost Sheet, Funding y Cash Flow basico. | Competitivo para demo/piloto; falta presupuesto avanzado, curvas versionadas, aprobaciones financieras y conciliacion ERP. |
| Schedule Manager | Intake XML/XER, data quality, baseline, mapping y control periods. | Bueno para piloto; falta parser industrial completo y planificacion avanzada tipo P6. |
| Document Manager | Documentos vinculados a entidades, claims, notices y evidencia. | MVP funcional; faltan versionado documental formal, revisiones, transmittals y permisos finos. |
| Planning Manager | Roadmap/readiness y portafolio basico por proyectos. | Parcial; falta seleccion de portafolio, presupuesto capital multi-anual y escenarios ejecutivos. |
| uDesigner | BP Designer basico para plantillas, campos, pasos y transiciones. | Diferenciador para piloto; falta editor visual completo, reglas por campo y migracion de versiones. |
| Shell Manager | Multi-tenant, proyectos, membresias y roles por proyecto. | Base correcta; falta jerarquia enterprise por region, unidad de negocio y programa. |
| Integration Manager | API-first y estructura preparada. | Aun pendiente integracion real con ERP, P6, SharePoint/Drive y SSO/OIDC. |
| Facilities / Asset | No implementado. | Fuera del piloto actual salvo que el alcance cambie a gestion de activos. |

Conclusion: frente a Unifier, P&Pmis Ai SaaS no compite todavia como suite enterprise completa. Si compite como piloto especializado de Project Controls colaborativo, mas enfocado en AACE TCM, Control Core, AWP, claims/forensic readiness y decision operacional.

## Manual De Uso

### Entrada

1. Levantar la plataforma.
2. Entrar al frontend.
3. Seleccionar usuario y proyecto.
4. Confirmar que el usuario tenga membresia en el proyecto.

Usuarios demo:

- `ana.control@demo.local` / `demo123`: Control Manager.
- `carlos.planner@demo.local` / `demo123`: Planner.
- `sofia.cost@demo.local` / `demo123`: Cost Controller.
- `laura.contracts@demo.local` / `demo123`: Contract Manager.

### Vistas Principales

- Business Processes: registros, ball-in-court, workflow y acciones.
- Control Dashboard: KPI, SPI, CPI, EAC, VAC, alertas y curva historica.
- Schedule: ingestion, data quality, baseline, WBS/CBS/Activity mapping.
- Progress: avances fisicos, cantidades, horas y evidencia.
- Cost Manager: Cost Sheet, fondos, cash flow y costos reales.
- AWP Workface: paquetes CWA/CWP/EWP/PWP/IWP y restricciones.
- Claims: entitlement, notices, impacto, causalidad y evidencia.
- Contracts: contratos y comunicaciones.
- Documents: evidencia y documentos vinculados.
- Roadmap: madurez, readiness y Plan de Control / PEP.
- Projects / Users / Roles: administracion colaborativa por proyecto.

### Flujo Operativo

1. El Planner carga cronograma fuente.
2. El sistema valida calidad y genera workflow de baseline.
3. El Control Manager aprueba el baseline de control.
4. Field Engineer captura avance.
5. Cost Controller captura costos, funding y cash flow.
6. Control Core recalcula KPI, alertas y forecast.
7. El equipo revisa cambios, AWP, contracts y claims.
8. Las decisiones quedan en workflow y audit log.

### Cost Manager

En la vista Cost Manager:

- Revisar Cost Sheet por cuenta de control.
- Confirmar BAC, EV, actas de pago, contratos, ordenes de compra, comprometido total, variacion y CPI.
- Registrar Funding Sources con codigo, nombre, monto y estado.
- Registrar Cash Flow por periodo con inflow/outflow plan, real y forecast.
- Revisar Funding Coverage, Cash Flow Variance y Forecast Outflow.

Endpoints utiles:

```text
GET /api/v1/projects/{project_id}/cost-sheet
GET /api/v1/projects/{project_id}/funding-sources
POST /api/v1/projects/{project_id}/funding-sources
PATCH /api/v1/projects/{project_id}/funding-sources/{funding_id}
GET /api/v1/projects/{project_id}/cash-flow
POST /api/v1/projects/{project_id}/cash-flow
PATCH /api/v1/projects/{project_id}/cash-flow/{period_id}
GET /api/v1/projects/{project_id}/cost-manager-summary
```

Las actualizaciones usan `expected_version` para evitar sobreescritura entre usuarios concurrentes.

## Paso A Paso Para Ejecutar El Piloto

### 1. Preparar Ambiente

```powershell
docker compose up -d --build
docker compose exec api alembic upgrade head
```

Validar:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\smoke_check.ps1
powershell -ExecutionPolicy Bypass -File .\tools\pilot_check.ps1
```

### 2. Definir Alcance

- Un proyecto.
- Un cronograma fuente o dataset semilla.
- 5 a 15 cuentas de control.
- Un ciclo semanal.
- Un paquete AWP.
- Un caso contractual o claim.
- Un responsable de piloto.

### 3. Confirmar Equipo

Roles minimos:

- Control Manager.
- Planner.
- Cost Controller.
- Field Engineer.
- Contract Manager.
- Workface Planner.
- Executive Sponsor.

Cada usuario debe entrar con su rol y ver solo su proyecto asignado.

### 4. Activar Plan De Control / PEP

En Roadmap, revisar y activar:

- Estrategia de ejecucion.
- Estrategia de control.
- Regla de progreso.
- Regla de costo.
- Cambios, riesgos, compras y documentos.
- Cadencia semanal.

### 5. Validar Cronograma Y Baseline

- Cargar cronograma.
- Revisar findings.
- Confirmar mapping WBS/CBS/Activity.
- Confirmar cost loading.
- Aprobar baseline.

### 6. Cargar Datos Del Ciclo

- Avance fisico.
- Cantidades.
- Horas.
- Costos reales.
- Commitments si aplica.
- Funding aprobado.
- Cash flow del periodo.
- Evidencia/documentos.

### 7. Ejecutar Control Y Revision Semanal

Revisar:

- SPI, CPI, CV, SV, EAC, ETC, VAC.
- Cost Sheet.
- Funding Coverage.
- Cash Flow Variance.
- Alertas rojas/amarillas.
- AWP readiness.
- Notices, claims y evidencia.
- Decisiones en workflow.

### 8. Probar Colaboracion Multiusuario

Prueba minima:

1. Usuario A abre un registro versionado.
2. Usuario B abre el mismo registro.
3. Usuario A guarda primero.
4. Usuario B intenta guardar con version anterior.
5. El sistema debe responder 409 y pedir refrescar.

Registros cubiertos:

- ProjectControlPlan.
- ControlAccount.
- FundingSource.
- CashFlowPeriod.
- WorkPackage.
- ClaimImpactAnalysis.

### 9. Cerrar Piloto

El piloto se considera exitoso si:

- Readiness final es mayor o igual a 75%.
- Al menos cinco roles participaron.
- Se completo un ciclo semanal.
- Se capturaron avance, costos, funding y cash flow.
- El dashboard genero KPI, alertas y forecast.
- Se registro al menos una decision por workflow.
- Se valido un paquete AWP.
- Se vinculo evidencia contractual o de campo.

### 10. Siguiente Ola Despues Del Piloto

- Integrar ERP para actas de pago, costos reales auxiliares, contratos y ordenes de compra.
- Integrar P6/MS Project de forma industrial.
- Agregar SSO/OIDC.
- Agregar realtime para workflows y ball-in-court.
- Versionar cash flow y forecasts.
- Fortalecer Document Manager con revisiones y transmittals.
- Preparar staging con backups, observabilidad y hardening.
