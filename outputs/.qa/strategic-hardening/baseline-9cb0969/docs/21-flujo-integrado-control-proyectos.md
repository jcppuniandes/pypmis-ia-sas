# Flujo Integrado de Control de Proyectos

## Descripcion

Este modulo incorpora el flujo `FLUJO-WBS-AWP-CBS-FBS-001` al modelo Project Controls existente. Reutiliza las entidades operativas actuales y agrega la trazabilidad explicita entre proyecto, FBS, WBS, paquetes AWP, cuentas de control, CBS, codigos de costo, contratos, compromisos, presupuesto, reales y forecast.

## Modelo Conceptual

El flujo queda ordenado asi:

```text
Proyecto autorizado
  -> Configuracion operativa del proyecto
  -> FBS inicial
  -> WBS y diccionario
  -> AWP / Path of Construction
  -> Control Accounts
  -> CBS
  -> Cost Codes
  -> Matriz FBS-WBS-AWP-CA-CBS-CostCode
  -> Baseline integrada
  -> Ejecucion, medicion, forecast, cambios y cierre
```

La FBS controla origen, autorizacion, restricciones y disponibilidad de fondos. La CBS clasifica el costo. El sistema valida que no se usen como sustitutos.

## Modelo de Datos

Entidades extendidas:

- `Project`: calendario base, owner, estado, fecha y referencia de autorizacion, configuracion JSON.
- `FundingSource`: usado como FBS; agrega fuente, tipo, autorizacion, restricciones, reglas, fondos disponibles, comprometidos y ejecutados.
- `WBS`: nivel, descripcion, diccionario, responsable y estado.
- `WorkPackage`: `wbs_id`, descripcion, fecha planificada de liberacion y restricciones principales.
- `ControlAccount`: paquete AWP asociado, alcance, presupuesto, fechas, EV, AC y forecast.
- `Contract` y `PurchaseOrder`: `funding_source_id` obligatorio por regla de negocio o inferido si existe una unica FBS aplicable.

Entidades nuevas:

- `ProjectOperationalSetup`: compuerta de configuracion operativa antes de cargar Activity Sheet, WBS, costos o fondos.
- `ActivitySheet` y `ActivitySheetRow`: registro trazable de cargas de actividades desde cronograma fuente.
- `CostBreakdownStructure`: CBS jerarquica por proyecto.
- `CostCode`: une WBS, control account, CBS, FBS, contrato, presupuesto, compromisos, reales y forecast.
- `ControlAccountFundingAllocation`: distribucion trazable de multiples FBS por cuenta de control.

## Reglas de Negocio

- No se crea contrato u orden de compra sin FBS asociada.
- No se comprometen valores superiores a fondos disponibles.
- Una cuenta de control puede tener varias FBS mediante `ControlAccountFundingAllocation`.
- La FBS no sustituye a la CBS; `CostCode` requiere ambas referencias.
- El forecast se compara contra fondos aprobados y disponibles.
- El saldo FBS se reporta desde `funds_available`, calculado como fondos aprobados menos compromisos activos menos costos ejecutados.
- El cierre financiero cierra compromisos asociados, libera saldos no usados y marca la FBS como `closed`.

## Workflow de Estados

- Proyecto: `draft`, `authorized`, `baseline_approved`, `in_execution`, `closed`.
- FBS: `draft`, `approved`, `partially_committed`, `fully_committed`, `closed`.
- WBS, AWP, Control Account, CBS y Cost Code: `draft`, `active`, `under_change`, `closed`.

## Endpoints

- `GET/PUT /api/v1/projects/{project_id}/operational-setup`
- `GET /api/v1/projects/{project_id}/activity-sheets`
- `POST /api/v1/projects/{project_id}/activity-sheets/get-data`
- `GET /api/v1/projects/{project_id}/activity-sheets/{activity_sheet_id}/rows`
- `GET/POST /api/v1/projects/{project_id}/fbs`
- `GET/POST /api/v1/projects/{project_id}/wbs`
- `GET/POST /api/v1/projects/{project_id}/cbs`
- `GET/POST /api/v1/projects/{project_id}/cost-codes`
- `POST /api/v1/projects/{project_id}/control-account-funding-allocations`
- `GET /api/v1/projects/{project_id}/integrated-control-matrix`
- `GET /api/v1/projects/{project_id}/funding-availability-check`
- `GET /api/v1/projects/{project_id}/forecast-vs-funding-report`
- `POST /api/v1/projects/{project_id}/baseline-approval`
- `GET /api/v1/projects/{project_id}/closeout-report`
- `POST /api/v1/projects/{project_id}/financial-closeout`

Los endpoints existentes de contratos y ordenes de compra aceptan `funding_source_id` y bloquean sobrecompromisos.

## Datos de Ejemplo

El seed crea ejemplos de matriz:

- `MIN-ABC`: `FBS-OWN-AFE002-PLT`, `1.5.3 Obras civiles planta`, `CWP-PLT-CIV-001`, `CA-PLT-CIV-001`, `4000 MO`, `MIN-1.5.3-CA-PLT-CIV-001-4000`, `CTR-CIV-001`, presupuesto `5.000.000`, fondos `4.800.000`.
- `VIA-001`: `FBS-PUB-VIG2027-T01`, `1.5.1 Tramo 1`, `CWP-T01-MT-001`, `CA-VIA-T01-MT-001`, `6000 Equipos`, `VIA-1.5.1-CA-VIA-T01-MT-001-6000`, `CTR-MT-001`, presupuesto `3.200.000`, fondos `3.000.000`.

## Frontend

La vista `Integrated Control` muestra:

- Creacion de proyecto con owner, calendario base, estado, autorizacion y configuracion de control.
- Creacion de FBS inicial.
- Alertas forecast vs fondos disponibles.
- Resumen de cierre financiero.
- Matriz FBS-WBS-AWP-CA-CBS-Cost Code.
- Accion de aprobacion de baseline integrada.

## Pruebas

Comandos principales:

```powershell
docker compose build api
docker compose run --rm api alembic upgrade head
docker compose run --rm api pytest tests/test_integrated_control.py -q
docker compose run --rm api pytest -q
```

La cobertura del flujo integrado valida creacion de proyecto, FBS, disponibilidad de fondos, asociacion FBS-WBS-CA-CBS-Cost Code, bloqueo de compromisos sin FBS, bloqueo de sobrecompromisos, saldo neto FBS, forecast vs funding y cierre financiero.

Para frontend:

```powershell
docker compose build frontend
docker compose run --rm frontend npm run build
```

## Pendientes y Riesgos

- La UI actual sigue siendo monolitica; conviene extraer la vista Integrated Control a un componente dedicado.
- Los compromisos de contratos y POs se suman ambos como comprometido, consistente con el cost manager actual; si el negocio requiere evitar doble conteo contrato/PO, se debe ajustar la regla.
- Los cierres financieros son acciones mutantes; mantenerlas restringidas a roles de Cost Control o Control Manager.
- Futuras integraciones ERP deben poblar `CostCode`, `funding_source_id` y `ControlAccountFundingAllocation` desde la misma fuente maestra.
