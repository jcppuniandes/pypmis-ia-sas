# Modelo de Datos

## Entidades principales

- `Tenant`: organizacion SaaS.
- `Project`: proyecto controlado.
- `ScheduleImport`: importacion fuente desde XML/XER de cronograma.
- `ScheduleActivityMap`: staging/trazabilidad entre actividad externa y actividad normalizada.
- `ActivityRelationship`: logica del cronograma FS, SS, FF y SF.
- `WBS`: estructura de desglose del trabajo.
- `Activity`: actividad de cronograma con logica.
- `ControlAccount`: punto integrador schedule/cost/progress.
- `Budget`: BAC y presupuesto por cuenta.
- `CostRecord`: costo real por fuente.
- `ProgressRecord`: avance fisico, cantidades y productividad.
- `Resource`: mano de obra, equipo, material o subcontrato.
- `Constraint`: restriccion de ejecucion.
- `Risk`: riesgo operacional o contractual.
- `ChangeRequest`: desviacion, analisis, aprobacion y seguimiento.
- `Claim`: evento reclamable, causalidad, impacto y evidencia.
- `ClaimEntitlementItem`: matriz de demostracion de entitlement para RP120R-21 y RP130R-23, con contrato, evento, aviso, causalidad, impacto, quantum, mitigacion, evidencia y cumulative impact.
- `Contract`: contrato fuente del comprometido y base de comunicaciones/notices/claims.
- `PurchaseOrder`: orden de compra fuente del comprometido.
- `PaymentCertificate`: acta de pago fuente del incurrido certificado.
- `WarehouseReceipt`: entrada de almacen fuente del incurrido recibido.
- `RFQPackage`: paquete de licitacion/RFQ con alcance, presupuesto, fechas y estado.
- `RFQBid`: oferta de bidder con monto y score tecnico/comercial/cronograma/riesgo.
- `Event`: evento de campo, contractual o de riesgo.
- `Document`: evidencia vinculable.
- `WorkPackage`: CWA/CWP/EWP/PWP/IWP conectado a cuenta de control, secuencia, path of construction y estado de readiness.
- `WorkPackageConstraint`: restriccion AWP de ingenieria, material, acceso, permiso, seguridad o documento que puede bloquear la liberacion.
- `KPI`: resultado EVM y metricas de control.
- `Alert`: alerta temprana accionable.
- `AuditLog`: trazabilidad de cambios y decisiones.

## Relaciones criticas

```text
Project 1..n WBS
Project 1..n ScheduleImport
ScheduleImport 1..n ScheduleActivityMap
ScheduleImport 1..n ActivityRelationship
Project 1..n Activity
WBS 1..n ControlAccount
ControlAccount 1..n Activity
ControlAccount 1..n Budget
ControlAccount 1..n CostRecord
ControlAccount 1..n Contract
ControlAccount 1..n PurchaseOrder
ControlAccount 1..n PaymentCertificate
ControlAccount 1..n WarehouseReceipt
ControlAccount 1..n RFQPackage
RFQPackage 1..n RFQBid
ControlAccount 1..n ProgressRecord
ControlAccount 1..n KPI
ControlAccount 1..n Alert
ChangeRequest n..n Document
Claim n..n Event
Claim n..n Document
Event n..n Activity
Event n..n ControlAccount
```

## Metricas EVM

- `PV`: Planned Value.
- `EV`: Earned Value.
- `AC`: Actual Cost.
- `SPI = EV / PV`.
- `CPI = EV / AC`.
- `SV = EV - PV`.
- `CV = EV - AC`.
- `EAC = BAC / CPI`.
- `ETC = EAC - AC`.
- `VAC = BAC - EAC`.

## Trazabilidad

Todo cambio significativo produce `AuditLog`. Las decisiones deben referenciar los KPI, alertas, documentos, eventos o cambios que las originaron.

## Regla de origen

`ScheduleImport` es la entidad de entrada. `Activity`, `WBS`, `ControlAccount`, `Budget`, `ProgressRecord`, `CostRecord`, `KPI`, `Alert`, `ChangeRequest`, `Claim` y `Document` deben poder trazarse directa o indirectamente a la version de cronograma que los origino.
