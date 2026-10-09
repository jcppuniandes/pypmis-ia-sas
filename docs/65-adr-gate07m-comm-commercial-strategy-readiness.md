# ADR 65 Gate 07M COMM Commercial Strategy and Readiness

## Estado

Aceptada y validada el 2026-09-16 como `GATE07M_COMM_COMMERCIAL_STRATEGY_RELEASE_VALIDATED`.

## Contexto

P&Pmis Construction AI necesita gobernar la estrategia comercial de un Project antes de una decision de inversion. La capacidad debe responder si la solucion puede llegar al mercado con un enfoque de procurement viable, paquetes conceptuales coherentes, un modelo de contratacion apropiado, riesgos asignados de forma consciente y mecanismos de pago e incentivos compatibles con el alcance.

El repositorio ya contiene autoridades separadas para Project Workspace, Business Analysis, Project Proposal, FEL, Business Case, Budget, Funding, Economic and Financial Model, Risk, Permit y las decisiones Gate07J a Gate07L. Tambien contiene objetos operacionales de RFQ, Contract, Purchase Order y Payment Certificate. La nueva capacidad debe consumir las primeras por referencia y permanecer aislada de las segundas.

## Decision

Se incorpora `CommercialContractingStrategy` como identidad estable y unica por `EnterpriseWorkspace` de tipo Project. Cada identidad conserva versiones `CommercialStrategyVersion` con contenido estrategico, lineage, configuracion efectiva y readiness congelados mediante hashes.

El ciclo de una version es `DRAFT`, `IN_REVIEW` y `COMPLETED`. Las versiones historicas pueden quedar `SUPERSEDED` o `VOIDED`. Una version terminal no admite edicion ni eliminacion fisica. Un cambio material o la recuperacion desde `STALE` crea una nueva version `DRAFT` y conserva intacta la evidencia historica.

Las secciones comerciales se almacenan como un documento JSON versionado. Esta decision evita una tabla por seccion y permite cargar lista y detalle sin consultas N mas uno. Los paquetes son conceptos de estrategia comercial independientes de WBS, RFQ packages, contratos, vendors, commitments, invoices y payments.

## Autoridad y reutilizacion

Commercial Strategy es autoridad de procurement approach, packaging strategy, contracting model, market assessment, supply chain constraints, commercial risk allocation, payment mechanism, incentive philosophy, commercial recommendation y commercial readiness.

La capacidad solo consume por referencia la identidad Project Workspace y el contexto gobernado de Business Analysis, Project Proposal, FEL, Business Case, Budget, Funding, FIN, Risk y Permit. No recalcula esas fuentes ni modifica sus historicos.

## Separacion USER y ADMIN

USER MODE opera expedientes vivos de Project. Puede crear, editar borradores, enviar, revisar, devolver, completar, anular, generar una revision, ejecutar `Refresh Preview`, aplicar el refresh como una nueva version y consultar readiness e historia.

ADMIN MODE opera configuracion reutilizable. Puede clonar, editar un borrador, previsualizar, publicar y archivar catalogos y reglas. El rol de configuracion no obtiene permisos transaccionales por herencia. Las rutas y API aplican controles independientes para impedir contaminacion entre modos.

## Configuracion e herencia

La configuracion reutiliza `AdminConfiguration`, el ciclo `DRAFT`, `PUBLISHED`, `ARCHIVED` y la resolucion Tenant, Enterprise, Business Unit y Portfolio. Cada version comercial congela `configuration_id`, revision y hash. `AdminNumberSequence` emite numeros visibles con prefijo `CCS`.

La politica habilita `CAPITAL_OWNER` por defecto. `CONTRACTOR_DELIVERY`, `DIRECT_INTERNAL` y `LEGACY_UNCLASSIFIED` no reciben una obligacion comercial retroactiva sin una configuracion publicada que la active.

## Readiness y vigencia

El backend calcula las dimensiones cerradas de contexto, procurement, packaging, contracting model, market, supply chain, risk allocation, payment y recomendacion. El frontend solo presenta sus estados, warnings y blockers.

Los hashes de fuentes detectan cambios materiales en Business Analysis, Project Proposal, FEL, Budget, Risk, Project scope, Project Type y configuracion publicada. Un `COMPLETED` cuya fuente cambia se presenta como `STALE` sin mutar la version. `Refresh Preview` devuelve `persisted=false`; `Refresh Apply` genera un nuevo borrador.

## Proveedor de evidencia

Se registra `COMMERCIAL_READINESS_PROVIDER` con `source_module=COMMERCIAL_CONTRACTING_STRATEGY`, `evidence_type=COMMERCIAL_READINESS` y estado `AVAILABLE`. Solo puede suministrar evidencia cuando la version esta completada, el readiness global es `READY`, fuentes y configuracion siguen vigentes y no hay blockers.

El registro del proveedor no modifica automaticamente la clasificacion publicada de Gate07J EVID. El nombre historico `CONTRACTING_STRATEGY_READINESS` se conserva por compatibilidad y no se convierte de forma retroactiva en un requisito Class A o B.

## Concurrencia seguridad y auditoria

Las mutaciones usan `ETag`, `If-Match` y `revision_version`; una version obsoleta devuelve `412 ETAG_MISMATCH`. Las acciones de creacion, revision, submit, complete, void y refresh apply usan claves idempotentes. `SecurityEvent` registra acciones de ciclo y configuracion. Cuando la politica exige segregacion, el autor no puede completar como revisor final.

## Navegacion

La ruta USER se agrega en la fase Project Definition and Investment Case como `Commercial and Contracting Strategy`. La ruta ADMIN se agrega en el mismo modulo de configuracion como `Commercial Strategy Configuration`. `strategicNavigationBlueprint.ts` sigue siendo la unica fuente de navegacion y `StrategicViewOutlet` resuelve y protege las vistas. `App.tsx` no incorpora logica especifica del dominio.

## Exclusiones

Este incremento no crea Vendor Master, Supplier Master, Partner Master, Bidder Master, RFQ, RFP, tender, bid, award, Contract, Commitment, Purchase Order, invoice, payment, change order, procurement schedule engine, Five Case UI ni reglas retroactivas para Gate07J.

## Consecuencias

La plataforma obtiene una fuente estrategica versionada y auditable para commercial readiness sin convertir la preparacion comercial en procurement operacional. El futuro Business Case puede consumir una referencia estable compuesta por identidad y version, hash, readiness y los enfoques recomendados de procurement, contratacion y pago.

## Validacion

La decisión aprobó pruebas focales en SQLite y PostgreSQL, migración `0059` a `0060` con ciclo up/down/up en ambos motores, casos negativos de readiness, staleness, SoD, ETag e idempotencia, separación API y navegador USER/ADMIN, navegación canónica y regresión diferencial sin fallos nuevos atribuibles a COMM. La evidencia detallada se conserva en `docs/validation/gate07m-comm/release-validation.md` y `outputs/.qa/gate07m-comm/`.
