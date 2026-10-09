# Implementacion de Instructivos de Control de Proyectos

## Alcance

Esta entrega adapta los instructivos de control de proyectos a una nomenclatura propia del sistema. El primer cambio operativo incorpora una compuerta de `configuracion operativa del proyecto` antes de cargar datos de actividades, WBS, costos o fondos.

La intencion es conservar la logica de control descrita en los instructivos sin copiar nombres propietarios de otra plataforma.

## Flujo Maestro Adaptado

```text
Proyecto autorizado
  -> Configuracion operativa del proyecto
  -> Cost Sheet y Funding Sheet listos
  -> Mapeo P6 listo
  -> Get Data de Activity Sheet
  -> WBS Sheet / WBS controlada
  -> Mapeo CBS-WBS-FBS-Control Account
  -> Compromisos, SOV, pagos, forecast y cierre
```

## Modelo Agregado

- `ProjectOperationalSetup`: readiness operativo del proyecto.
- `ActivitySheet`: registro controlado de una carga de actividades.
- `ActivitySheetRow`: filas trazables importadas desde la fuente de cronograma.

Campos principales de `ProjectOperationalSetup`:

- `project_number`
- `setup_template`
- `attribute_form`
- `permissions_configured`
- `modules_configured`
- `cost_sheet_ready`
- `funding_sheet_ready`
- `p6_mapping_ready`
- `status`
- `readiness_status`
- `readiness_notes`

## Reglas De Negocio

- No se permite ejecutar `Get Data` de Activity Sheet si la configuracion operativa del proyecto no esta lista.
- La configuracion se considera lista solo si existen numero de proyecto, plantilla, formulario de atributos, permisos, modulos, Cost Sheet, Funding Sheet y mapeo P6.
- La carga de Activity Sheet reutiliza el parser de cronograma existente para P6 XML/XER y mantiene trazabilidad con `ScheduleImport`.
- Los datos importados quedan disponibles como Activity Sheet y como registros de cronograma existentes para WBS, actividades y mapeos de cuentas de control.

## Endpoints

- `GET /api/v1/projects/{project_id}/operational-setup`
- `PUT /api/v1/projects/{project_id}/operational-setup`
- `GET /api/v1/projects/{project_id}/activity-sheets`
- `POST /api/v1/projects/{project_id}/activity-sheets/get-data`
- `GET /api/v1/projects/{project_id}/activity-sheets/{activity_sheet_id}/rows`

## Pruebas

Prueba focalizada:

```powershell
docker compose build api
docker compose run --rm api pytest tests/test_project_operational_setup_activity_sheet.py -q
```

Pruebas de regresion recomendadas:

```powershell
docker compose run --rm api pytest tests/test_schedule_parser.py tests/test_schedule_ingestion.py tests/test_integrated_control.py tests/test_project_operational_setup_activity_sheet.py -q
```

## Pendientes

- Crear la vista frontend de configuracion operativa y Activity Sheet.
- Exponer WBS Sheet como vista operacional separada de la WBS maestra.
- Agregar Rate Sheet y Recost.
- Completar SOV, distribucion de fondos por compromiso y cierre comercial.
- Agregar validaciones de cambio de alcance que obliguen revision de WBS, Control Account, CBS, Cost Code, contrato y FBS.
