# Roadmap Por Olas Para Robustecer El Piloto

Fecha base: 2026-05-08

## Principio De Ejecucion

El piloto `CTRL-DEMO-001` ya puede operar. El objetivo de este roadmap no es rehacer la plataforma, sino fortalecerla por capas pequenas, verificables y reversibles. Cada ola debe terminar con smoke check, pilot check, pruebas backend y build frontend antes de pasar a la siguiente.

Regla de oro: no ampliar alcance funcional si la base operativa pierde estabilidad.

## Estado Base

| Elemento | Estado |
| --- | --- |
| Proyecto piloto | `CTRL-DEMO-001` |
| Readiness actual | 100.0% |
| Fase en vigilancia previa | Fase 3 Control Accounts / Mapping, cerrada para piloto |
| API / Frontend / DB / Redis / Worker | Operativos en Docker local |
| Document Control | Registro, reviews, transmittals, project mail, adjuntos PDF/DOCX/XML/XER/ZIP, hash y descarga autenticada |
| Integraciones | Manifiesto read-only, CSV/JSON, ZIP con hash, XLSX, catalogo auditable, tokens con alcance y alertas de rotacion |
| Validacion base | `pytest`, frontend build, integration gate y pilot check |

## Ola 1. Guardrails Del Piloto

### Objetivo

Evitar regresiones mientras se opera el piloto. Esta ola agrega controles de verificacion y pruebas de borde sin cambiar el flujo principal.

### Alcance

- Gate operativo reusable para correr smoke check y pilot readiness.
- Pruebas negativas de ingesta documental.
- Checklist de seguridad minima para adjuntos.
- Evidencia de que el dashboard sigue entregando Cost Manager, RFQ, Document Control y readiness.

### Criterios De Aceptacion

- `tools/pilot_robust_gate.ps1` corre sin errores.
- `docker compose exec -T api pytest` pasa.
- `docker compose exec -T frontend npm run build` pasa.
- `powershell -ExecutionPolicy Bypass -File .\tools\smoke_check.ps1` pasa.
- `powershell -ExecutionPolicy Bypass -File .\tools\pilot_check.ps1` muestra `CTRL-DEMO-001 ready 100.0%`.
- Cargas peligrosas `.exe`, rutas inseguras en ZIP y ZIP anidados son rechazados.

### Entregables

- Script `tools/pilot_robust_gate.ps1`.
- Pruebas backend reforzadas.
- Este roadmap versionado.

## Ola 2. Seguridad Y Operacion Controlada

### Objetivo

Subir el piloto de "operativo local" a "beta controlada" con seguridad, auditoria y recuperacion basica.

### Alcance

- SSO/OIDC o preparacion formal de OIDC.
- MFA si el entorno objetivo lo exige.
- API tokens para integraciones controladas.
- Politicas de password y expiracion de token configurables.
- Auditoria consultable desde UI para acciones criticas.
- Backups y restore probado para PostgreSQL y volumen documental.
- Retencion basica de adjuntos.
- Antivirus/scan real para archivos cargados.

### Criterios De Aceptacion

- Usuario sin membresia no puede ver ni descargar adjuntos.
- Adjuntos quedan bloqueados o marcados si falla el scan.
- Restore de DB y documentos probado en ambiente separado.
- Logs de auditoria permiten reconstruir quien cargo, descargo o cambio un registro critico.

## Ola 3. Integraciones Que Compran Valor

### Objetivo

Reducir carga manual conectando el piloto con fuentes reales de cronograma, costo y documentos.

### Alcance

- Parser P6 XML/XER mas robusto.
- Importador MS Project.
- Plantillas Excel gobernadas para progreso, costos y contratos.
- API ERP para compromisos, actas, pagos y costos reales.
- Conector SharePoint/Drive o modo EDMS externo.
- Export gobernado a Power BI/CSV.

### Criterios De Aceptacion

- Importar cronograma real sin romper mapping existente.
- Cargar costos desde plantilla o API sin duplicados.
- Sincronizar documentos externos manteniendo hash, fuente y permisos.
- Dashboard conserva trazabilidad de fuente por dato.

### Avance Ejecutado

- Ola 3A: manifiesto de integracion y export CSV/JSON read-only.
- Ola 3B: paquete ZIP con manifiesto y checksums SHA-256.
- Ola 3C: tokens de integracion con prefijo gobernado, alcance, expiracion y revocacion.
- Ola 3D: workbook XLSX ejecutivo generado desde datasets permitidos.
- Ola 3E: catalogo auditable de descargas con actor, datasets, formato, archivo, hash, filas y fecha.
- Ola 3F: alertas de tokens proximos a vencer y tokens activos vencidos.

## Ola 4. Control Avanzado Y AI

### Objetivo

Convertir el piloto en una capa de inteligencia accionable para comites semanales.

### Alcance

- Narrativa semanal automatizada de SPI/CPI/EAC/VAC.
- AI asistida para mapping WBS/CBS/Activity con aprobacion humana.
- Deteccion de gaps de evidencia para claims.
- Alertas predictivas por cash flow, restricciones AWP y tendencia de avance.
- Busqueda semantica en documentos con citas y permisos.
- Recomendaciones de accion por rol.

### Criterios De Aceptacion

- Toda recomendacion AI debe mostrar fuente o dato que la soporta.
- Ninguna accion AI actualiza registros sin aprobacion humana.
- Las narrativas se pueden exportar y auditar.

## Ola 5. Preparacion Para Produccion Controlada

### Objetivo

Pasar de beta controlada a produccion no critica con soporte operativo.

### Alcance

- CI/CD con migraciones, rollback y ambientes separados.
- Observabilidad avanzada: metricas, logs, trazas y alertas.
- Pruebas E2E, carga y seguridad.
- Runbook de incidentes.
- Gestion de configuracion por ambiente.
- Hardening de Docker/VPS.
- Plan de soporte y SLA interno.

### Criterios De Aceptacion

- Deploy reproducible en staging.
- Rollback probado.
- Monitoreo alerta fallas de API, DB, Redis, storage y worker.
- Prueba de carga base sin degradacion critica.
- Manual operativo aprobado.

## Secuencia Recomendada

1. Ejecutar Ola 1 completa antes de invitar mas usuarios.
2. Operar una semana de piloto con datos controlados.
3. Cerrar Ola 2 antes de datos sensibles.
4. Ejecutar Ola 3 con una integracion a la vez.
5. Agregar AI solo cuando datos, permisos y auditoria esten estables.
6. Declarar produccion controlada solo despues de Ola 5.

## Riesgos Y Mitigaciones

| Riesgo | Impacto | Mitigacion |
| --- | --- | --- |
| Meter demasiados modulos nuevos | Romper piloto estable | Cambios pequenos por ola y gate obligatorio |
| Adjuntos inseguros | Riesgo operacional | Bloqueo de tipos peligrosos, ZIP seguro, antivirus en Ola 2 |
| Integracion ERP/P6 incompleta | Datos duplicados o inconsistentes | Staging, dry-run y trazabilidad de fuente |
| AI sin fuentes | Perdida de confianza | Respuestas con evidencia y aprobacion humana |
| Produccion prematura | Riesgo reputacional | Mantener etiqueta beta/piloto hasta cumplir Ola 5 |

## Checklist De Cierre Por Ola

Antes de cerrar cualquier ola:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\pilot_robust_gate.ps1
docker compose exec -T api pytest
docker compose exec -T frontend npm run build
powershell -ExecutionPolicy Bypass -File .\tools\pilot_check.ps1
```

El cierre solo procede si `CTRL-DEMO-001` sigue en `ready` y el equipo puede entrar por `http://localhost:5173`.
