# Ola 3E Catalogo Auditable De Integraciones

Fecha base: 2026-05-07

## Objetivo

Registrar cada artefacto de integracion generado por el piloto para que el equipo pueda responder quien descargo datos, que datasets incluyo, en que formato, con que hash y en que fecha. Esta ola agrega trazabilidad operativa sin cambiar el consumo de CSV, JSON, ZIP o XLSX.

## Alcance Cerrado En Esta Iteracion

- Tabla `integration_export_logs`.
- Endpoint `GET /api/v1/projects/{project_id}/integration-downloads`.
- Registro automatico de:
  - `integration-export`
  - `integration-package`
  - `integration-workbook`
- Registro de actor:
  - Usuario JWT.
  - Token de integracion y usuario creador.
- Registro de datasets incluidos.
- Registro de formato.
- Registro de nombre de archivo.
- Registro de SHA-256.
- Registro de tamano en bytes.
- Registro de cantidad de filas exportadas.
- Header `X-Integration-Download-Id` para CSV, ZIP y XLSX.
- Gate `tools/pilot_integration_gate.ps1` actualizado para validar el catalogo.

## Endpoint

```http
GET /api/v1/projects/{project_id}/integration-downloads?limit=50
Authorization: Bearer <jwt_usuario>
```

Solo roles con `can_configure` pueden consultar el catalogo.

Respuesta por registro:

- `id`
- `project_id`
- `requested_by_user_id`
- `integration_token_id`
- `actor`
- `artifact_type`
- `datasets`
- `format`
- `file_name`
- `sha256`
- `size_bytes`
- `row_count`
- `status`
- `created_at`

## Artefactos Registrados

| Artefacto | Endpoint | Registro |
| --- | --- | --- |
| Export simple | `integration-export` | `artifact_type=export` |
| Paquete ZIP | `integration-package` | `artifact_type=package` |
| Workbook XLSX | `integration-workbook` | `artifact_type=workbook` |

## Uso Operativo

Consultar ultimas descargas:

```powershell
$headers = @{ Authorization = "Bearer <jwt_usuario>" }
Invoke-RestMethod `
  -Uri "http://localhost:8000/api/v1/projects/1/integration-downloads?limit=25" `
  -Headers $headers
```

Verificar un artefacto:

```powershell
Get-FileHash -Algorithm SHA256 ".\CTRL-DEMO-001-integration-workbook.xlsx"
```

Comparar el resultado con el campo `sha256` del catalogo.

## Controles

- El catalogo no almacena el archivo, solo metadatos y hash.
- Los tokens se registran por `integration_token_id`.
- Usuarios sin membresia no pueden consultar registros del proyecto.
- Roles sin `can_configure` no pueden consultar el catalogo.
- Los hashes permiten validar que un ZIP/XLSX no cambio despues de descargarse.
- El catalogo se alimenta automaticamente; el consumidor no tiene que cambiar su flujo.

## Gate Operativo

Ejecutar:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\pilot_integration_gate.ps1
```

El gate actualizado valida:

- Descarga CSV/JSON.
- Generacion ZIP.
- Generacion XLSX.
- Token de integracion.
- Consulta del catalogo.
- Presencia de registros `export`, `package` y `workbook`.
- Presencia de hash en workbook.
- Presencia de registro asociado al token creado por el gate.
- Rechazo `403` para usuario sin membresia.

## Checklist De Cierre

```powershell
docker compose build api
docker compose up -d api
docker compose exec -T api pytest
docker compose exec -T frontend npm run build
powershell -ExecutionPolicy Bypass -File .\tools\pilot_integration_gate.ps1
powershell -ExecutionPolicy Bypass -File .\tools\pilot_check.ps1
```

## Siguiente Ola Recomendada

La siguiente ola puede avanzar a:

- Alertas de tokens proximos a vencer.
- Retencion configurable del catalogo.
- Reporte ejecutivo de integraciones por consumidor.
- Staging de importacion XER/XML con comparacion antes/despues.

## Decision

Con Ola 3E el piloto ya no solo genera artefactos gobernados; tambien deja evidencia consultable de cada descarga. Esto fortalece auditoria, seguridad y pruebas con terceros sin abrir escritura externa ni persistir copias de archivos exportados.
