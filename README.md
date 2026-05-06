# P&Pmis Ai SaaS

Plataforma web colaborativa multiusuario de Project Controls basada en AACE TCM para operar proyectos de Oil & Gas e infraestructura como un sistema integrado de control.

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
- Arquitectura: API-first, multi-tenant, multiusuario, decision/execution separation

## Colaboracion multiusuario

La plataforma debe operar en linea para equipos de proyecto con usuarios concurrentes, roles por proyecto y trazabilidad de acciones.

- El acceso a datos de proyecto se controla por `ProjectMembership`, no solo por tenant.
- Los roles definen capacidades operativas: captura de avance, captura de costo, aprobacion de workflow, gestion contractual y configuracion.
- Las acciones transaccionales relevantes generan `AuditLog` para trazabilidad colaborativa.
- El siguiente bloque productivo debe sumar concurrencia optimista, notificaciones y actualizaciones en tiempo real para workflows, alertas y ball-in-court.

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

El script valida health de API, readiness DB/Redis, login JWT, proyectos disponibles, dashboard principal, readiness de piloto y frontend.

## Readiness de piloto

Para revisar si los proyectos estan listos para piloto:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\pilot_check.ps1
```

La API tambien expone:

```text
GET /api/v1/projects/{project_id}/pilot-readiness
```

El indicador cubre Fase 1 a Fase 6: Schedule Intake, BP Engine, Control Accounts, EVM/Forecast, Contracts/Claims y SaaS colaborativo.

## Plan de Control del Proyecto / PEP

La app incluye un plan de control por proyecto para formalizar lo que aparece en el flujo de procesos: estrategia de ejecucion, estrategia de control, reglas de medicion de progreso, reglas de medicion de costo, cambios, riesgos, adquisiciones, control documental y cadencia de reportes.

Endpoints:

```text
GET /api/v1/projects/{project_id}/control-plan
PUT /api/v1/projects/{project_id}/control-plan
```

El `PUT` usa `expected_version` para evitar que dos usuarios sobrescriban el mismo plan sin refrescar.

## Pruebas

Con el stack levantado:

```powershell
docker compose exec api pytest
```

La suite mínima cubre health, readiness, autenticacion, rechazo sin token, proyectos, dashboard y encolado del Control Core.

## Configuracion operativa

Variables principales:

```text
DATABASE_URL=postgresql+psycopg://pypmis:pypmis@db:5432/pypmis
REDIS_URL=redis://redis:6379/0
CORS_ORIGINS=http://localhost:5173
AUTO_CREATE_SCHEMA=true
SEED_DEMO_DATA=true
AUTH_SECRET_KEY=replace-with-a-long-random-secret
ACCESS_TOKEN_EXPIRE_MINUTES=480
DEMO_USER_PASSWORD=demo123
```

Para un entorno productivo, usar migraciones Alembic, configurar `AUTO_CREATE_SCHEMA=false`, `SEED_DEMO_DATA=false`, rotar `AUTH_SECRET_KEY` y conectar OIDC/SSO corporativo si aplica.

## Autenticacion

La API usa token Bearer JWT. En la demo, todos los usuarios semilla tienen la clave `demo123`.

```powershell
$session = Invoke-RestMethod -Method Post -Uri http://localhost:8000/api/v1/auth/login -ContentType "application/json" -Body (@{
  email = "ana.control@demo.local"
  password = "demo123"
  tenant_slug = "demo-energy"
} | ConvertTo-Json)

$headers = @{ Authorization = "Bearer $($session.access_token)" }
Invoke-RestMethod -Uri http://localhost:8000/api/v1/projects -Headers $headers
```

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
Invoke-RestMethod -Method Post -Uri http://localhost:8000/api/v1/projects/1/control-cycle/jobs -Headers $headers
```

## Documentacion

- [SDD](docs/01-SDD.md)
- [Arquitectura funcional TCM](docs/02-arquitectura-funcional-tcm.md)
- [Arquitectura tecnica](docs/03-arquitectura-tecnica.md)
- [Modelo de datos](docs/04-modelo-de-datos.md)
- [Flujos de procesos](docs/05-flujos-de-procesos.md)
- [Backlog por fases](docs/06-backlog-por-fases.md)
- [Guia para desarrollar el piloto](docs/08-guia-piloto.md)

## Regla de entrada

El sistema no debe iniciar desde tareas manuales. Todo proyecto debe nacer de un cronograma fuente en Primavera P6 o Microsoft Project. La importacion del cronograma crea la estructura base para WBS, actividades, logica, baseline, cost loading y cuentas de control.
