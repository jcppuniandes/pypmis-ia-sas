# ADR Wave 1 Strategic Capital Demand and Capital Planning

**Estado:** Aceptado para implementacion y validacion  
**Fecha:** 2026-09-29  
**Producto:** P&Pmis Construction AI  
**Macroproceso:** Capital Portfolio and Investment Governance  
**Incremento:** Strategic Capital Demand and Capital Planning Foundation

## Decision

P&Pmis incorpora una autoridad de dominio separada para planificar necesidades de capital antes de que exista una solucion seleccionada. La nueva autoridad administra Strategic Investment Themes, Capital Planning Cycles y Strategic Capital Demands. Una demanda respaldada puede originar una o varias Ideas mediante una accion explicita e idempotente que usa la autoridad existente de Idea.

La implementacion conserva estas separaciones:

- Capital Demand no es Idea, Project, Portfolio Membership, Budget, Funding ni FIN.
- Endorsed no crea una Idea automaticamente.
- Originate Idea no crea Project, Proposal, Portfolio Membership, Budget ni Funding.
- La necesidad de capital registrada en la demanda siempre es indicativa.
- Las Ideas historicas y standalone siguen siendo validas sin demanda de origen.
- Business Analysis conserva la autoridad sobre opciones y solucion recomendada.
- Potential Portfolio es contexto indicativo, no una pertenencia.

## Context

La revision CPIG anterior confirmo una cadena madura desde Idea hasta Post FID, pero identifico que el proceso empezaba despues de seleccionar una forma inicial de solucion. Wave 1 agrega el registro gobernado de la necesidad de capital, su contexto estrategico y el periodo de planeacion correspondiente.

El flujo canonico queda asi:

```text
Strategic Objective
  -> Strategic Investment Theme
  -> Capital Planning Cycle
  -> Strategic Capital Demand
  -> Originate Idea
  -> Idea
  -> Business Analysis and Options
  -> Project Proposal
```

## Scope

Wave 1 incluye:

- Strategic Investment Themes administrados y publicables.
- Relacion muchos a muchos entre Themes y Strategic Objectives.
- Capital Planning Cycles con identidad, horizonte y ciclo de vida.
- Strategic Capital Demands con identidad estable y trazabilidad.
- Ciclo de vida controlado de Demand.
- Origen explicito Demand to Idea con snapshot y hash inmutables.
- Compatibilidad con multiples Ideas por Demand.
- Configuracion ADMIN y operacion USER separadas.
- ETag, idempotencia, auditoria y separacion de funciones.
- Navegacion estrategica de fase 1 sin romper bookmarks vigentes.

Wave 1 excluye Strategic Capital Buckets, Periodic Portfolio Review, Risk Appetite, Basic Data Readiness, QRA, Owner Capability Readiness, cambios a Gate07J, Project Creation, Budget allocation, Funding, Procurement y Project Delivery.

## Domain authorities

| Concepto | Autoridad | Regla |
|---|---|---|
| Strategic Objective | Enterprise Strategy | Se referencia; no se duplica. |
| Strategic Investment Theme | Capital Planning ADMIN | Catalogo versionado y publicable. |
| Capital Planning Cycle | Capital Planning USER | Periodo gobernado para capturar y revisar demandas. |
| Strategic Capital Demand | Capital Planning USER | Necesidad previa a la seleccion de solucion. |
| Idea | Idea Demand | La nueva accion invoca el servicio existente. |
| Business Analysis | Business Analysis | Conserva current state, desired state, gap y options. |
| Project Proposal | Project Proposal | Conserva la autoridad de propuesta. |
| Portfolio Membership | Portfolio | No se crea ni modifica en Wave 1. |
| Budget | Portfolio Budget Planning | No se crea ni modifica en Wave 1. |
| Funding | Funds Manager | No se crea ni modifica en Wave 1. |
| FIN | Economic and Financial Model | No se crea ni modifica en Wave 1. |

## Strategic Investment Theme

Theme es una clasificacion reusable, distinta de Strategic Objective, Idea Category, Strategic Capital Bucket y Project Type. Los valores productivos no se codifican en el dominio. ADMIN crea borradores, previsualiza la configuracion efectiva, publica revisiones y archiva revisiones antiguas mediante los patrones existentes de AdminConfiguration.

La relacion Theme to Objective es muchos a muchos. Esta relacion expresa alineacion del catalogo; la seleccion concreta de objetivos en una Demand queda congelada dentro de la revision de la demanda y del snapshot usado para originar una Idea.

## Capital Planning Cycle

CapitalPlanningCycle define el periodo dentro del cual se capturan, revisan y respaldan demandas. Su identidad no representa un presupuesto.

Estados permitidos:

```text
DRAFT -> OPEN -> IN_REVIEW -> CLOSED
```

Un ciclo cerrado no se modifica en sitio. Cualquier cambio material requiere una nueva revision o un ciclo sucesor, de acuerdo con la autoridad implementada. Los totales se presentan por moneda cuando no existe una normalizacion gobernada.

## Strategic Capital Demand

StrategicCapitalDemand usa un numero visible estable con prefijo CD y conserva el ID tecnico interno. Registra el ciclo, Theme, objetivos, necesidad de negocio o activo, driver, sponsor, horizonte, urgencia, alcance, contexto de Workspace, estimacion indicativa, incertidumbre, Portfolio potencial, supuestos, restricciones y dependencias.

Estados permitidos:

```text
DRAFT -> SUBMITTED -> IN_REVIEW -> ENDORSED
                    -> RETURNED
                    -> DEFERRED
                    -> CANCELLED
                    -> SUPERSEDED
```

La configuracion efectiva determina campos requeridos y aplicabilidad. Un actor de configuracion no recibe automaticamente permisos para mutar registros USER.

## Endorsement semantics

ENDORSED confirma que la organizacion reconoce una necesidad suficientemente definida para entrar en Investment Origination. No aprueba una solucion, Project, Portfolio, capital, Budget, Funding ni FID. La transicion registra actor, fecha, revision, ETag y SecurityEvent. Cuando la politica activa separacion de funciones, el autor no puede ser el endorser final.

## Demand to Idea contract

Originate Idea recibe el ID de Demand, If Match e Idempotency Key. Puede recibir campos iniciales de Idea permitidos por la configuracion. El servicio de Capital Planning valida elegibilidad y luego invoca el servicio existente de Idea, sin insertar una Idea por su cuenta.

El resultado contiene:

- Idea ID y numero.
- Capital Demand ID.
- Hash del snapshot de origen.
- Indicador de creacion o repeticion idempotente.

Cada origen congela Demand ID, Idea ID, actor, fecha, version de Demand, snapshot y hash. La clave idempotente identifica un intento, no limita la cardinalidad del negocio. Una misma Demand puede producir nuevas Ideas con claves distintas.

## Historical compatibility

Las Ideas existentes no reciben backfill. Una Idea historica o standalone puede mantener `source_capital_demand_id = null`. La nueva lineage se almacena en la relacion de origen y, cuando el modelo de Idea lo permite, como referencia opcional. Ningun snapshot historico se recalcula al cambiar la demanda.

## Governance applicability

| Governance Model | Comportamiento por defecto |
|---|---|
| CAPITAL_OWNER | La politica puede requerir origen desde Demand para nuevos programas de capital. |
| CONTRACTOR_DELIVERY | No se fuerza Capital Planning. |
| DIRECT_INTERNAL | La Idea directa puede permanecer habilitada por politica. |
| LEGACY_UNCLASSIFIED | Se conserva compatibilidad historica. |

Project Type y Governance Model son dimensiones distintas. La configuracion puede definir aplicabilidad sin convertir Project Type en una regla fija del dominio.

## Concurrency and repeat safety

Las mutaciones usan revision version, ETag e If Match. Un ETag obsoleto devuelve HTTP 412 con codigo `ETAG_MISMATCH`. Las operaciones create cycle, create demand, endorse demand y originate idea aceptan Idempotency Key. La repeticion de una misma clave devuelve el resultado previamente registrado y no produce duplicados.

## Security and audit

Los permisos se separan entre lectura, ciclo, demanda, transiciones, origen de Idea y configuracion ADMIN. La aplicacion valida permisos en la API, aunque la UI o el bookmark se invoquen directamente. Las mutaciones relevantes generan SecurityEvent con tenant, actor, target, accion, version y detalle minimo de trazabilidad.

## Persistence

La persistencia es aditiva. Los agregados nuevos son CapitalPlanningCycle, StrategicCapitalDemand y CapitalDemandIdeaOrigin. Los Themes reutilizan el patron de configuracion cuando es suficiente; las relaciones que requieren consulta eficiente e integridad historica se modelan de forma normalizada. Los indices cubren tenant, Workspace, cycle, status, Theme, sponsor, horizon y potential Portfolio.

La migracion parte de la cabeza real `20260916_0061`, conserva una sola cabeza y no hace backfill de Ideas.

## Navigation

`strategicNavigationBlueprint.ts` permanece como fuente unica de verdad. La fase 1 USER pasa a Strategic Capital Planning and Demand y expone Planning Cycles, Capital Demand Pipeline, My Demands, Demands in Review, Endorsed Demands y Demand History. Investment Origination and Shaping conserva Idea Lifecycle, Business Analysis and Options y Project Proposal.

ADMIN expone Strategic Capital Planning and Demand Configuration y no muestra transacciones vivas. Los IDs y rutas historicos de Idea se mantienen como aliases o nodos compatibles. `App.tsx` no recibe una nueva implementacion monolitica.

## Consequences

La organizacion puede registrar una necesidad antes de escoger una solucion y conservar lineage hasta Idea, BA y Proposal. La separacion incrementa la cantidad de estados, permisos y pruebas, pero elimina la ambiguedad entre demanda de capital, Idea, Project, Budget y Funding. Future Strategic Capital Buckets puede referenciar Cycle y Demand sin cambiar sus identidades.

## Release criteria

El release solo se declara validado cuando pasan las pruebas de dominio, migracion, PostgreSQL, navegacion, frontend, RBAC, SoD, ETag, idempotencia, no side effects y compatibilidad historica. Si una prueba obligatoria no se puede ejecutar, el informe final debe registrarla como no validada y no usar el estado exclusivo de release.

## Next increment boundary

Despues de validar Wave 1 se evaluan Wave 2A Strategic Capital Buckets y Wave 2B Risk Appetite plus Basic Data Readiness. El informe final recomienda exactamente un incremento y no implementa ninguno de los dos.
