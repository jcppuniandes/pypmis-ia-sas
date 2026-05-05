# Arquitectura Tecnica

## Vista general

```text
React + TypeScript
        |
        v
FastAPI API-first
        |
        +--> PostgreSQL
        |
        +--> Redis
               |
               v
            Celery Workers
```

## Schedule Gateway

El primer bounded context tecnico es `Schedule Intake`. Recibe archivos XML/XER de cronograma fuente y produce una version validada del cronograma.

Formatos objetivo:

- XER de programacion.
- XML de cronograma.
- Conectores externos mediante conversion controlada en fase posterior.

La ingesta no ejecuta decisiones. Solo captura, valida, normaliza y deja trazabilidad. La formacion de cuentas de control y la ejecucion del ciclo EVM ocurren despues de aprobar la version de cronograma.

## Backend

FastAPI expone APIs REST versionadas bajo `/api/v1`. La aplicacion se organiza en:

- `domain`: entidades, esquemas y reglas del negocio.
- `services`: EVM, early warning, control core, IA y decisiones.
- `services/schedule_ingestion.py`: deteccion de fuente, parseo inicial y gate de calidad del cronograma.
- `WorkPackage` y `WorkPackageConstraint`: capa AWP para path of construction, paquetes de trabajo y constraint log.
- `routers`: endpoints API-first.
- `database`: sesion, modelos SQLAlchemy y seed.
- `workers`: tareas asincronas Celery.

## Frontend

React + TypeScript implementa una experiencia SaaS B2B densa, ejecutiva y operacional. La pantalla principal muestra:

- Flujo TCM obligatorio.
- Vista AWP Workface con readiness, paquetes CWA/CWP/EWP/PWP/IWP y restricciones.
- KPIs EVM.
- S-curve simplificada.
- Early warnings.
- Cambios y claims vinculados.
- Panel documental y trazabilidad.

## Base de datos

PostgreSQL almacena el modelo transaccional multi-tenant. Cada entidad operacional incluye `tenant_id`; las entidades subordinadas incluyen `project_id`.

## Async

Redis sirve como broker Celery. Los workers ejecutan:

- recalculo EVM por proyecto,
- ingesta y validacion asincrona de cronogramas,
- deteccion de alertas,
- generacion de reportes,
- analisis IA diferido,
- ingestas de sistemas externos.

## Separacion Decision / Execution

Servicios de decision:

- `EVMEngine`
- `EarlyWarningService`
- `ControlCoreService`
- `AIInsightService`

Servicios de ejecucion:

- workflows de cambio,
- acciones correctivas,
- actualizacion de forecast,
- generacion de comunicaciones contractuales.

La decision produce recomendaciones y alertas; la ejecucion requiere estado, responsable y auditoria.
