# Guia Para Desarrollar El Piloto

Fecha base: 2026-05-05

## Objetivo

Ejecutar un piloto controlado de P&Pmis Ai SaaS con un equipo real de proyecto para validar flujo colaborativo, ingestion de cronograma, Control Core, AWP, contratos, claims, auditoria y rutina de decision.

El piloto no debe intentar cubrir toda la organizacion. Debe probar un proyecto, un equipo, un ciclo de control y una muestra contractual suficientemente representativa.

## Criterio De Entrada

Antes de iniciar:

- Stack levantado con `docker compose up -d --build`.
- Migraciones aplicadas con `docker compose exec api alembic upgrade head`.
- Smoke verde con `tools/smoke_check.ps1`.
- Readiness de piloto mayor o igual a 65%.
- Usuario Control Manager disponible.
- Al menos cinco roles cargados en el equipo del proyecto.
- Cronograma fuente disponible en XML/XER o dataset semilla aceptado para demo controlada.

## Paso A Paso

### 1. Definir alcance

Elegir un solo proyecto piloto.

Alcance recomendado:

- 1 cronograma fuente.
- 20 a 100 actividades representativas.
- 5 a 15 cuentas de control.
- 1 ciclo de control semanal.
- 1 paquete AWP con restricciones reales.
- 1 caso contractual o claim con evidencia.

Salida esperada:

- Proyecto seleccionado.
- Responsable del piloto.
- Fecha de inicio y cierre.
- Criterios de exito aprobados.

### 2. Configurar equipo

Crear o confirmar usuarios:

- Control Manager.
- Planner.
- Cost Controller.
- Contract Manager.
- Field Engineer.
- Workface Planner.
- Executive Sponsor.

Asignar roles por proyecto desde la vista Projects / Users / Roles.

Salida esperada:

- Todos los usuarios pueden entrar.
- Cada usuario ve solo los proyectos donde tiene membresia.
- Las acciones no permitidas retornan 403.

### 3. Cargar cronograma

El Planner carga el cronograma fuente desde Schedule Control.

Validar:

- Actividades importadas.
- Relaciones logicas.
- Findings DCMA/AACE.
- Quality score.
- Workflow de baseline creado.

Salida esperada:

- Schedule Intake en estado Pass o Review controlado.
- Errores criticos cerrados o documentados.

### 4. Aprobar baseline de control

El equipo valida:

- WBS/CBS/Activity mapping.
- Cost loading minimo para EVM.
- Cuentas de control.
- Baseline version.

El Control Manager aprueba el baseline si el mapping y cost loading cumplen el criterio del piloto.

Salida esperada:

- Baseline approved.
- Control capture desbloqueado.

### 5. Ejecutar ciclo Control Core

Capturar datos de una semana:

- Avance fisico.
- Cantidades instaladas.
- Horas.
- Costos reales.
- Evidencia.

Ejecutar Control Core.

Validar:

- PV, EV, AC.
- SPI, CPI.
- EAC, ETC, VAC.
- Alertas.
- Forecast scenarios.
- Control snapshots.

Salida esperada:

- Dashboard listo para reunion semanal.
- Alertas con recomendacion.
- Decision registrada.

### 6. Probar colaboracion multiusuario

Prueba minima:

- Dos usuarios abren el mismo registro editable.
- Usuario A actualiza el registro.
- Usuario B intenta actualizar usando una version anterior.

Resultado esperado:

- Usuario B recibe conflicto 409 y debe refrescar.

Registros cubiertos:

- ControlAccount.
- WorkPackage.
- WorkPackageConstraint.
- ClaimEntitlementItem.
- ClaimImpactAnalysis.
- Workflow action.

### 7. Probar AWP

Crear o validar:

- CWA/CWP/EWP/PWP/IWP.
- Path of construction.
- Constraint log.
- Readiness status.
- Workface release.

Cerrar una restriccion y confirmar que el readiness recalcula.

Salida esperada:

- Paquete liberable o bloqueo claramente trazado.

### 8. Probar contrato y claim

Crear o validar:

- Contrato.
- Comunicacion.
- Notice.
- Claim.
- Entitlement matrix.
- Impact analysis.
- Evidencia/documentos.

Salida esperada:

- Forensic readiness score calculado.
- Gaps de evidencia visibles.
- Acciones contractuales trazadas.

### 9. Medir readiness

Ejecutar:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\pilot_check.ps1
```

Revisar:

- Fase 1: Schedule Intake / Data Quality.
- Fase 2: Business Process Engine.
- Fase 3: Control Accounts / Mapping.
- Fase 4: EVM / Forecast / Control Core.
- Fase 5: Contracts / Claims / Evidence.
- Fase 6: SaaS colaborativo / Operacion.

Salida esperada:

- Estado `pilot_candidate` o `ready`.
- Acciones siguientes claras para cada fase.

### 10. Correr reunion de piloto

Agenda semanal recomendada:

1. Estado del cronograma y data quality.
2. Variaciones SPI/CPI/VAC.
3. Alertas rojas y amarillas.
4. AWP readiness y constraints.
5. Cambios, notices y claims.
6. Decisiones y responsables.
7. Acciones para el siguiente ciclo.

Salida esperada:

- Decisiones registradas en workflows.
- Audit log actualizado.
- Ball-in-court claro.

### 11. Cerrar piloto

Preparar un informe corto:

- Que funciono.
- Que bloqueo la operacion.
- Que informacion falto.
- Que automatizacion genero valor.
- Que roles usaron realmente la plataforma.
- Que brechas impiden escalar a produccion.

## Criterios De Exito

El piloto se considera exitoso si:

- Al menos cinco roles participaron.
- Se completo un ciclo de control semanal.
- Se cargaron avance y costos.
- Se genero un dashboard con KPI y alertas.
- Se registro al menos una decision por workflow.
- Se valido un paquete AWP.
- Se vinculo evidencia contractual o de campo.
- Readiness final mayor o igual a 75%.

## No Alcance Del Piloto

Quedan fuera salvo decision explicita:

- SSO/OIDC corporativo.
- Integracion ERP real.
- Parser XER completo industrial.
- Integracion Primavera P6 en vivo.
- Alta disponibilidad.
- Backups productivos.
- Observabilidad APM completa.

## Ruta Despues Del Piloto

Si el piloto es exitoso:

1. Convertir usuarios demo a usuarios corporativos.
2. Activar OIDC/SSO.
3. Conectar ERP/costos reales.
4. Endurecer parser XER/XML.
5. Agregar realtime para notificaciones y ball-in-court.
6. Implementar backups, metricas y monitoreo productivo.
7. Preparar despliegue staging.
