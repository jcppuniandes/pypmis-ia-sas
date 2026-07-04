# Operacion Productiva Formal

Fecha: 2026-05-15

## Objetivo

Formalizar el paso de piloto funcional a operacion productiva controlada para P&Pmis Ai SaaS.

## Checklist de salida a produccion

| Area | Control requerido | Evidencia |
|---|---|---|
| Migraciones | Ejecutar `alembic upgrade head` en el ambiente objetivo | `deploy/vps/deploy.sh` ejecuta upgrade y luego `alembic current` |
| Roles por cliente | Revisar matriz de roles por proyecto/tenant | `GET /api/v1/projects/{project_id}/role-matrix` |
| Pruebas E2E | Ejecutar navegador real en pipeline | GitHub Actions corre `npm run test:e2e` con Playwright |
| Backups | Generar respaldo comprimido con checksum y retencion | `deploy/vps/backup.sh` crea `.sql.gz` y `.sha256` |
| Restore | Validar checksum antes de reemplazar la base | `deploy/vps/restore.sh <backup.sql.gz>` ejecuta `sha256sum -c` |
| Seguridad | Prohibir secretos debiles, wildcard hosts, docs y schema auto-create | `Settings.validate_for_runtime()` |
| Observabilidad | Logs JSON, metricas protegidas, health/readiness y Sentry opcional | `/api/v1/health/ready`, `/api/v1/ops/metrics` |
| Agente | Mantener reglas deterministicas y habilitar sintesis low-cost opcional | `AI_PROVIDER=disabled` por defecto |

## Variables minimas de produccion

| Variable | Recomendacion |
|---|---|
| `APP_ENVIRONMENT` | `production` |
| `AUTH_SECRET_KEY` | 64 caracteres aleatorios o mas |
| `ALLOWED_HOSTS` | Dominio explicito, sin `*` |
| `CORS_ORIGINS` | URL exacta del frontend |
| `DOCS_ENABLED` | `false` |
| `AUTO_CREATE_SCHEMA` | `false` |
| `METRICS_ENABLED` | `true` |
| `METRICS_TOKEN` | Token secreto para metricas |
| `LOG_FORMAT` | `json` |
| `RATE_LIMIT_ENABLED` | `true` |
| `SENTRY_DSN` | Opcional, recomendado para produccion |
| `AI_PROVIDER` | `disabled` por defecto; `claude` si se activa sintesis |
| `AI_MODEL` | Modelo economico, por ejemplo Haiku |

## Procedimiento operativo

1. Tomar backup: `bash deploy/vps/backup.sh`.
2. Desplegar: `bash deploy/vps/deploy.sh`.
3. Confirmar migracion: revisar salida de `alembic current`.
4. Confirmar salud: `curl https://<dominio>/api/v1/health/ready`.
5. Revisar matriz de roles del proyecto desde `/api/v1/projects/{project_id}/role-matrix`.
6. Revisar metricas y logs JSON.
7. Ejecutar restore solo con archivo `.sha256` presente y validado.
8. Ejecutar rollback solo con backup validado y aprobacion operativa.

## Cierre de hardening 2026-05-17

| Control | Cierre aplicado | Evidencia |
|---|---|---|
| Secreto productivo | `AUTH_SECRET_KEY` requiere minimo 64 caracteres | `Settings.validate_for_runtime()` y `tools/vps_preflight.ps1` |
| Deploy VPS | Rechaza placeholders en DB, Redis, JWT y metricas | `deploy/vps/deploy.sh` |
| Hosts/CORS | Bloquea comodines antes del despliegue | `deploy/vps/deploy.sh` |
| Logs | Exige `LOG_FORMAT=json` en produccion | `deploy/vps/deploy.sh` |
| Backup | Rota respaldo y checksum como par auditable | `deploy/vps/backup.sh` |
| Restore | Verifica checksum antes de pedir confirmacion humana | `deploy/vps/restore.sh` |
| Gate repo | Verifica CI, E2E, migraciones, backup, restore y runbook | `tools/verify_production_ops.py` |

## Flujo guiado multi-tenant

El usuario opera dentro de un tenant visible. La app guia el proceso desde proyecto hasta cierre:
tenant, proyecto, cronograma, costos y moneda, WBS/CBS/FBS, baseline, progreso, costos reales, Control Core, AWP, evidencia y cierre.

Despues de cargar XER/XML, el gate de costos y moneda muestra moneda detectada, fuente de deteccion, porcentaje cost-loaded, costo total importado, actividades sin costo y siguiente accion.

## Politica para el agente

El agente sigue siendo deterministico por defecto para controlar costo y trazabilidad. La sintesis con modelo economico es una capa opcional: resume hallazgos, no decide ni escribe datos de negocio. Si `AI_PROVIDER` no esta configurado o falla el proveedor, el resumen deterministico permanece como fuente de verdad.
