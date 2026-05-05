# P&Pmis Ai SaaS

Plataforma web de Project Controls basada en AACE TCM para operar proyectos de Oil & Gas e infraestructura como un sistema integrado de control.

Entrada maestra obligatoria:

```text
Cronograma fuente XML/XER -> Schedule Intake -> Data Quality Gate -> Planeacion
```

Flujo operativo obligatorio:

```text
Planeacion -> Cuentas de Control -> Ejecucion -> Control Core -> Decision -> Retroalimentacion
```

Control Core continuo:

```text
CAPTURAR -> VALIDAR -> ANALIZAR -> ALERTAR -> DECIDIR -> ACTUAR -> REPETIR
```

AWP integrado:

```text
Cronograma validado -> Path of Construction -> CWA/CWP/EWP/PWP/IWP -> Constraint Log -> Workface Release -> Avance/Costos/Control Core
```

## Stack

- Backend: FastAPI
- Frontend: React + TypeScript
- DB: PostgreSQL
- Async: Redis + Celery
- Infra: Docker Compose
- Arquitectura: API-first, multi-tenant, decision/execution separation

## Ejecutar

```powershell
docker compose up -d --build
```

Servicios:

- Frontend: http://localhost:5173
- API: http://localhost:8000
- OpenAPI: http://localhost:8000/docs

## Verificacion rapida

Con el stack levantado:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\smoke_check.ps1
```

El script valida health de API, proyectos disponibles, dashboard principal y frontend.

## Configuracion operativa

Variables principales:

```text
DATABASE_URL=postgresql+psycopg://pypmis:pypmis@db:5432/pypmis
REDIS_URL=redis://redis:6379/0
CORS_ORIGINS=http://localhost:5173
AUTO_CREATE_SCHEMA=true
SEED_DEMO_DATA=true
```

Para un entorno productivo, usar migraciones Alembic, configurar `AUTO_CREATE_SCHEMA=false` y `SEED_DEMO_DATA=false`, y reemplazar los encabezados demo `X-Tenant-Id` / `X-User-Id` por autenticacion JWT/OIDC.

## Migraciones

La base Alembic esta en `backend/alembic`.

```powershell
docker compose exec api alembic current
docker compose exec api alembic revision --autogenerate -m "initial schema"
docker compose exec api alembic upgrade head
```

## Control Core asincronico

El worker Celery escucha la cola `control-core`.

```powershell
Invoke-RestMethod -Method Post -Uri http://localhost:8000/api/v1/projects/1/control-cycle/jobs -Headers @{ "X-Tenant-Id"="1"; "X-User-Id"="1" }
```

## Documentacion

- [SDD](docs/01-SDD.md)
- [Arquitectura funcional TCM](docs/02-arquitectura-funcional-tcm.md)
- [Arquitectura tecnica](docs/03-arquitectura-tecnica.md)
- [Modelo de datos](docs/04-modelo-de-datos.md)
- [Flujos de procesos](docs/05-flujos-de-procesos.md)
- [Backlog por fases](docs/06-backlog-por-fases.md)

## Regla de entrada

El sistema no debe iniciar desde tareas manuales. Todo proyecto debe nacer de un cronograma fuente en Primavera P6 o Microsoft Project. La importacion del cronograma crea la estructura base para WBS, actividades, logica, baseline, cost loading y cuentas de control.
