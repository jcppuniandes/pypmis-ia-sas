# Gate 07A-BA — Business Analysis & Options Governance

## Alcance implementado

Este incremento incorpora el expediente de análisis de negocio entre Idea Lifecycle y Project Proposal, con superficies separadas por modo y reutilización de las capacidades empresariales existentes.

```text
Idea aceptada + evaluación vigente
              │
              ▼
   Business Analysis & Options
   DRAFT → SUBMITTED → IN_REVIEW → COMPLETED
              │                         │
              │ RETURNED               └─ snapshot + completion hash
              ▼
 READY_FOR_PROJECT_PROPOSAL
              │
              ▼
 Project Proposal con linaje BA
```

## USER MODE

La pantalla `Business Analysis & Options` ofrece colas autorizadas, búsqueda, creación desde Ideas elegibles, formulario estructurado, comparación de alternativas, recomendación, readiness e historial.

El contenido cubre:

- necesidad, problema u oportunidad; contexto, urgencia y consecuencia de no actuar;
- drivers y alineación con Strategic Objectives existentes;
- stakeholders, estado actual, resultados y valor esperado;
- supuestos, restricciones y requisitos de negocio de alto nivel;
- alternativas con alcance, beneficios, rangos preliminares, riesgos, dependencias, factibilidad y evaluación;
- opción recomendada, trade-offs, condiciones y preocupaciones pendientes.

El enlace a Project Proposal sólo aparece cuando el backend devuelve `ready=true` y `READY_FOR_PROJECT_PROPOSAL`.

## ADMIN MODE

La pantalla `Business Analysis Configuration` administra revisiones reutilizables. Incluye secciones para tipos de análisis, drivers, stakeholders, dimensiones de valor, tipos y mínimos de opciones, matriz/pesos, campos obligatorios, readiness, mapping, numeración, herencia, permisos/SoD, preview e historial.

No contiene controles para crear, enviar, revisar o completar expedientes vivos. El preview resuelve la política efectiva sin persistir datos transaccionales.

## Modelo de datos y API

### Persistencia

- `business_analyses`: estado actual, contenido, fuente, configuración, recomendación, hashes y control optimista.
- `business_analysis_revisions`: snapshots append-only por cambio y transición.
- `project_proposals`: linaje BA nullable para compatibilidad histórica.
- `admin_configurations`: configuración versionada reutilizada.
- `security_events`: auditoría existente reutilizada.

### Endpoints principales

| Modo | Contrato | Finalidad |
|---|---|---|
| USER | `GET /business-analyses/options` | Ideas elegibles y catálogos efectivos |
| USER | `POST /business-analyses` | Crear con `Idempotency-Key` |
| USER | `GET/PUT /business-analyses/{id}` | Consultar o editar con `If-Match` |
| USER | `POST /{id}/submit`, `/start-review`, `/return`, `/complete` | Transiciones gobernadas |
| USER | `POST /{id}/new-revision` | Cambio material sobre un BA completo |
| USER | `GET /{id}/readiness`, `/history` | Preparación y auditoría |
| ADMIN | `GET /admin/configurations` | Revisiones configurables |
| ADMIN | `POST /admin/configuration/preview` | Resolución `persisted=false` |
| ADMIN | `POST/PUT .../clone|publish|archive` | Ciclo de configuración |

## Reglas determinísticas de readiness

Bloquean el envío o la salida: fuente Idea obsoleta, matriz/configuración obsoleta, necesidad incompleta, ausencia de drivers/alineación/stakeholders/estado actual/resultados/valor/supuestos/restricciones/requisitos, opciones insuficientes, tipos obligatorios ausentes, opciones sin evaluar, recomendación ausente y preocupaciones bloqueantes no aceptadas.

## Compatibilidad

- Nuevas Ideas `CAPITAL_OWNER`: BA requerido.
- `CONTRACTOR_DELIVERY` y `DIRECT_INTERNAL`: no requerido por defecto, configurable.
- Ideas históricas cuyo snapshot no contiene la política: flujo anterior preservado.
- Proposals históricas: columnas BA nullable; sus snapshots y decisiones permanecen válidos.

## Fuera de alcance

Five Case Business Case, cálculo económico-financiero completo, selección de portafolio, FID, activación de Project Workspace, ejecución de beneficios y agentes automáticos. Estas capacidades conservan sus módulos y gates existentes.

