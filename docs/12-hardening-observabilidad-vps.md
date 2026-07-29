# Hardening, Observabilidad Y Preparacion VPS

Fecha base: 2026-05-06

## Estado Implementado

La plataforma queda preparada para una produccion controlada y para una migracion futura a VPS. El modo local sigue funcionando con `docker compose up -d --build`; el modo VPS queda separado en `docker-compose.vps.yml` para no mezclar secretos ni puertos de desarrollo.

## Hardening Aplicado

- Validacion de configuracion productiva al arranque.
- Bloqueo de secretos por defecto en `APP_ENVIRONMENT=production`.
- `ALLOWED_HOSTS` obligatorio y explicito en produccion.
- `CORS_ORIGINS` obligatorio y explicito en produccion.
- Swagger/OpenAPI apagables con `DOCS_ENABLED=false`.
- Headers de seguridad:
  - `X-Content-Type-Options: nosniff`.
  - `X-Frame-Options: DENY`.
  - `Referrer-Policy: no-referrer`.
  - `Permissions-Policy`.
  - `Content-Security-Policy` basico para API.
  - `Strict-Transport-Security` cuando `HSTS_ENABLED=true`.
- Limite de request body con `MAX_REQUEST_BODY_MB`.
- Rate limit basico por IP:
  - `RATE_LIMIT_REQUESTS`.
  - `LOGIN_RATE_LIMIT_REQUESTS`.
  - `RATE_LIMIT_WINDOW_SECONDS`.
- Redis se usa como store de rate limit cuando esta disponible; si falla, queda fallback in-memory.

## Observabilidad Aplicada

### Endpoints

- `GET /api/v1/health`: liveness simple compatible con smoke checks.
- `GET /api/v1/health/live`: estado vivo con ambiente, version, commit y uptime.
- `GET /api/v1/health/ready`: verifica API, base de datos y Redis.
- `GET /api/v1/ops/metrics`: metricas tipo Prometheus.

### Logs

Variables:

- `LOG_LEVEL=INFO`.
- `LOG_FORMAT=plain` para local.
- `LOG_FORMAT=json` para VPS.

Cada request registra:

- `request_id`.
- metodo.
- path.
- status.
- duracion.
- cliente.

### Metric Token

En VPS, definir `METRICS_TOKEN` y consultar:

```powershell
Invoke-WebRequest `
  -Uri "https://pypmis.example.com/api/v1/ops/metrics" `
  -Headers @{ "X-Metrics-Token" = "<token>" }
```

## Archivos Nuevos

- `.env.example`: variables locales seguras para orientacion.
- `deploy/vps/.env.example`: plantilla de secretos para VPS.
- `docker-compose.vps.yml`: stack productivo controlado sin exponer PostgreSQL/Redis.
- `frontend/Dockerfile.vps`: build estatico de frontend con Nginx.
- `frontend/nginx.vps.conf`: Nginx sirve frontend y proxy `/api` hacia FastAPI.
- `tools/vps_preflight.ps1`: valida variables antes de levantar el stack VPS.

## Flujo Para VPS

### 1. Preparar servidor

Requisitos minimos sugeridos:

- Ubuntu 22.04/24.04 LTS.
- Docker Engine y Docker Compose Plugin.
- 2 vCPU, 4 GB RAM para piloto.
- Disco con backups separados del volumen principal.
- Firewall permitiendo solo 22, 80 y 443.

### 2. Preparar variables

```powershell
Copy-Item deploy\vps\.env.example deploy\vps\.env
notepad deploy\vps\.env
```

Cambiar obligatoriamente:

- `POSTGRES_PASSWORD`.
- `REDIS_PASSWORD`.
- `AUTH_SECRET_KEY`.
- `METRICS_TOKEN`.
- `CORS_ORIGINS`.
- `ALLOWED_HOSTS`.

Usar secretos URL-safe para `POSTGRES_PASSWORD` y `REDIS_PASSWORD`: letras, numeros, guion y guion bajo. Evitar espacios y caracteres `: / @ ? # [ ]`, porque esas claves se interpolan dentro de URLs de conexion.

Validar:

```powershell
powershell -ExecutionPolicy Bypass -File tools\vps_preflight.ps1
```

### 3. Validar compose

```powershell
docker compose --env-file deploy\vps\.env -f docker-compose.vps.yml config
```

### 4. Levantar stack

```powershell
docker compose --env-file deploy\vps\.env -f docker-compose.vps.yml up -d --build
```

### 5. Migrar base de datos

```powershell
docker compose --env-file deploy\vps\.env -f docker-compose.vps.yml exec api alembic upgrade head
```

### 6. Verificar salud

```powershell
Invoke-RestMethod http://localhost/api/v1/health
Invoke-RestMethod http://localhost/api/v1/health/ready
```

### 7. Verificar metricas

```powershell
Invoke-WebRequest `
  -Uri "http://localhost/api/v1/ops/metrics" `
  -Headers @{ "X-Metrics-Token" = "<METRICS_TOKEN>" }
```

## TLS Y Dominio

El `docker-compose.vps.yml` expone HTTP en `HTTP_PORT`. Para TLS se recomienda poner delante:

- Caddy.
- Traefik.
- Nginx Proxy Manager.
- Nginx host con Certbot.
- Cloudflare Tunnel si no se desea abrir 80/443 directamente.

Cuando TLS este activo:

- `CORS_ORIGINS=https://dominio`.
- `ALLOWED_HOSTS=dominio,localhost,127.0.0.1`.
- `HSTS_ENABLED=true`.

## Backups Minimos

Backup manual:

```powershell
docker compose --env-file deploy\vps\.env -f docker-compose.vps.yml exec db `
  pg_dump -U pypmis -d pypmis -Fc -f /backups/pypmis_$(Get-Date -Format yyyyMMdd_HHmm).dump
```

Restore de prueba en ambiente separado:

```powershell
docker compose --env-file deploy\vps\.env -f docker-compose.vps.yml exec db `
  pg_restore -U pypmis -d pypmis --clean /backups/<archivo>.dump
```

Para produccion real, programar backup diario y probar restore semanal.

## Checklist Antes De Migrar Un Piloto Real

- Dominio definido.
- TLS activo.
- Secretos reemplazados.
- `DOCS_ENABLED=false`.
- `AUTO_CREATE_SCHEMA=false`.
- `SEED_DEMO_DATA=false`.
- Migraciones aplicadas con Alembic.
- Backup probado.
- Smoke test ejecutado.
- Metric endpoint protegido.
- Logs en JSON centralizables.
- Firewall sin exponer PostgreSQL ni Redis.
- Runbook de incidente definido.

## Brechas Que Siguen

- SSO/OIDC y MFA.
- Rotacion automatica de secretos.
- Backups programados desde infraestructura.
- Alertas reales en Prometheus/Grafana, Uptime Kuma o servicio similar.
- Pruebas de carga y seguridad.
- CI/CD productivo con rollback.
- Almacenamiento de adjuntos/documentos fuera del contenedor.
