# Cierre de Hardening de Produccion - Pypmis AI SaaS

Fecha: 2026-05-17

## Estado de cierre

| Dimension | Resultado | Evidencia |
|---|---|---|
| Estado operativo | Cerrado para piloto productivo controlado | Smoke, health, readiness, migraciones y frontend verificados |
| Estado de produccion masiva | Condicionado | Requiere ejecutar el mismo gate en el ambiente objetivo del cliente |
| Riesgo residual | Bajo para piloto, medio para salida masiva | Depende de secretos reales, dominio, backups externos y matriz final por cliente |

## Controles endurecidos

| Control | Antes | Cierre aplicado |
|---|---|---|
| Secreto JWT | Produccion aceptaba minimo 32 caracteres | Ahora exige 64 caracteres en runtime, preflight y deploy |
| Deploy VPS | Validaba placeholders parciales | Ahora valida DB, Redis, JWT y token de metricas |
| Hosts y CORS | Runtime los bloqueaba; deploy no frenaba temprano | Deploy bloquea `*` antes de levantar servicios |
| Logs | Runtime exigia JSON | Deploy tambien exige `LOG_FORMAT=json` |
| Backup | Creaba `.sql.gz` y `.sha256` | Rotacion elimina respaldo y checksum como par |
| Restore | Pedia confirmacion humana | Primero exige `.sha256` y ejecuta `sha256sum -c` |
| Gate repo | Validaba base operativa | Ahora valida restore, rotacion, secretos y preflight |

## Matriz de produccion

| Area | Estado | Uso operativo |
|---|---|---|
| Migraciones | Listas | `alembic upgrade head` y `alembic current` en deploy |
| Roles por cliente | Listos | `/api/v1/projects/{project_id}/role-matrix` |
| Pruebas E2E | Listas en CI | `npm run test:e2e` con Playwright |
| Seguridad API | Endurecida | secretos, CORS, allowed hosts, docs off, rate limit y headers |
| Observabilidad | Lista | `/health/live`, `/health/ready`, `/ops/metrics` con token |
| Backups | Endurecidos | backup comprimido, checksum y retencion |
| Restore | Endurecido | checksum obligatorio antes de reemplazar base |
| Agente AWP | Controlado | deterministico por defecto; sintesis low-cost opcional |

## Paso a paso de salida controlada

| Paso | Accion | Comando o pantalla |
|---|---|---|
| 1 | Preparar `.env` productivo | Copiar `deploy/vps/.env.example` y reemplazar secretos |
| 2 | Validar preflight | `powershell -ExecutionPolicy Bypass -File tools/vps_preflight.ps1 -EnvFile deploy/vps/.env` |
| 3 | Validar artefactos de operacion | `python tools/verify_production_ops.py` |
| 4 | Tomar backup previo | `bash deploy/vps/backup.sh` |
| 5 | Desplegar | `bash deploy/vps/deploy.sh` |
| 6 | Confirmar migracion | Revisar salida de `alembic current` |
| 7 | Confirmar API | `curl https://<dominio>/api/v1/health/ready` |
| 8 | Confirmar frontend | Abrir `https://<dominio>` |
| 9 | Confirmar roles | Abrir matriz de roles del proyecto |
| 10 | Confirmar observabilidad | Consultar metricas con `X-Metrics-Token` |
| 11 | Validar backup nuevo | Revisar archivo `.sql.gz` y `.sha256` |
| 12 | Documentar aprobacion | Registrar fecha, commit, responsable y evidencia |

## Paso a paso de restore

| Paso | Accion | Criterio |
|---|---|---|
| 1 | Seleccionar backup | Debe existir `pypmis_*.sql.gz` |
| 2 | Validar checksum | Debe existir `pypmis_*.sql.gz.sha256` |
| 3 | Ejecutar restore | `bash deploy/vps/restore.sh backups/pypmis_YYYYMMDD_HHMMSS.sql.gz` |
| 4 | Confirmar reemplazo | Responder `y` solo con aprobacion operativa |
| 5 | Migrar a head | Script ejecuta `alembic upgrade head` |
| 6 | Reiniciar servicios | Script levanta API, worker y beat |
| 7 | Validar salud | `health/ready` debe responder ready |

## Evidencia tecnica esperada

| Evidencia | Resultado esperado | Responsable |
|---|---|---|
| `docker compose ps` | API, DB y Redis healthy; frontend up | DevOps |
| `alembic current` | Revision head actual | Backend |
| Smoke funcional | Login, proyectos, dashboard, costos, RFQ y frontend OK | QA |
| Gate seguridad | Adjuntos, auditoria y aislamiento por proyecto OK | QA/SecOps |
| Gate integracion | Exports, workbook, tokens y restricciones OK | QA/Data |
| Backup verify | Dump legible y documentos validos | DevOps |
| Restore rehearsal | Restore probado en contenedor temporal | DevOps |

## Evidencia ejecutada el 2026-05-17

| Verificacion | Resultado | Evidencia |
|---|---|---|
| Suite backend completo | OK | `116 passed in 65.23s` |
| Gate repo de operacion | OK | `tools/verify_production_ops.py` sin errores |
| Migracion actual | OK | `20260515_0018 (head)` |
| Servicios Docker | OK | API healthy; DB y Redis healthy; frontend up |
| Gate seguridad/integracion | OK | `tools/pilot_integration_gate.ps1` completo |
| API readiness | OK | `health/ready` respondio `ready` |
| Observabilidad | OK | metricas Prometheus expuestas |
| Seguridad funcional | OK | descarga anonima 401; no miembro 403 |
| Integraciones | OK | CSV, JSON, ZIP, XLSX, token scope y revocacion validados |
| PDF de cierre | OK | `Cierre_Hardening_Produccion_Pypmis_Ai_SaaS_2026-05-17.pdf` |

## Decision

| Decision | Estado | Nota |
|---|---|---|
| Piloto productivo controlado | Aprobable | Con ambiente objetivo validado y respaldo ejecutado |
| Produccion masiva | No automatica | Requiere runbook ejecutado con secretos reales y aprobacion del cliente |
| Agente con modelo economico | Opcional | Activar solo para sintesis; no reemplaza reglas deterministicas |

## Cierre ejecutivo

El hardening queda cerrado para operar un piloto productivo controlado. La aplicacion ya cuenta con controles de configuracion, despliegue, backup, restore, observabilidad, roles, E2E y agente gobernado. La salida a produccion formal debe repetir este mismo gate en el ambiente objetivo y conservar la evidencia de fecha, commit, backup y responsables.
