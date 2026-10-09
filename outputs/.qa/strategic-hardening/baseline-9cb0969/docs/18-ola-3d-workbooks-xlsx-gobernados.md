# Ola 3D Workbooks XLSX Gobernados

Fecha base: 2026-05-07

## Objetivo

Entregar una plantilla XLSX ejecutiva, descargable y verificable, a partir de los mismos datasets gobernados de integracion. Esta ola facilita revision manual, validacion con usuarios de Project Controls y carga controlada hacia BI o ERP staging sin abrir escritura hacia sistemas externos.

## Alcance Cerrado En Esta Iteracion

- Endpoint `GET /api/v1/projects/{project_id}/integration-workbook`.
- Workbook `.xlsx` generado en memoria, sin persistir archivos en el servidor.
- Hoja `Summary` con proyecto, fecha, modo, datasets y campos.
- Una hoja por dataset solicitado.
- Encabezados, autofiltro y columnas dimensionadas.
- Header `X-Workbook-Sha256` para verificar integridad.
- Header `X-Workbook-Datasets` con datasets incluidos.
- Soporte de tokens de integracion con formato `xlsx`.
- Prueba automatizada que abre el XLSX como ZIP OOXML y valida hojas esperadas.
- Gate `tools/pilot_integration_gate.ps1` actualizado para descargar y validar workbook.

## Endpoint

```http
GET /api/v1/projects/{project_id}/integration-workbook?datasets=cost_sheet,documents
Authorization: Bearer <token>
```

Respuesta:

- `Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`
- `Content-Disposition: attachment`
- `X-Workbook-Sha256`
- `X-Workbook-Datasets`

## Estructura Del Workbook

Hojas:

- `Summary`: resumen del proyecto, fecha de generacion, modo `read_only`, datasets y campos.
- Una hoja por dataset: por ejemplo `cost_sheet`, `documents`, `cash_flow`.

Cada hoja de dataset incluye:

- Encabezado en primera fila.
- Datos tabulares.
- Fila superior congelada.
- Autofiltro.
- Columnas con ancho razonable.

## Uso Operativo

Ejemplo de descarga con JWT de usuario:

```powershell
$headers = @{ Authorization = "Bearer <jwt_usuario>" }
Invoke-WebRequest `
  -Uri "http://localhost:8000/api/v1/projects/1/integration-workbook?datasets=cost_sheet,funding_sources,cash_flow" `
  -Headers $headers `
  -OutFile ".\CTRL-DEMO-001-integration-workbook.xlsx"
```

Ejemplo con token de integracion:

```powershell
$headers = @{ Authorization = "Bearer pypmis_it_xxxxxxxx_<secreto>" }
Invoke-WebRequest `
  -Uri "http://localhost:8000/api/v1/projects/1/integration-workbook?datasets=cost_sheet,documents" `
  -Headers $headers `
  -OutFile ".\CTRL-DEMO-001-integration-workbook.xlsx"
```

Verificacion local:

```powershell
Get-FileHash -Algorithm SHA256 ".\CTRL-DEMO-001-integration-workbook.xlsx"
```

## Controles De Seguridad

- El workbook es solo lectura desde el punto de vista de plataforma.
- No crea registros en base de datos.
- No persiste archivos exportados.
- No descarga binarios documentales; solo metadatos filtrados por rol.
- Respeta membresia de proyecto.
- Respeta confidencialidad documental.
- Tokens de integracion requieren formato `xlsx` para descargar workbooks.
- Usuarios sin membresia reciben `403`.
- Tokens vencidos o revocados reciben `401`.

## Gate Operativo

Ejecutar:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\pilot_integration_gate.ps1
```

El gate actualizado valida:

- Paquete ZIP de integracion.
- Workbook XLSX con checksum.
- Entradas OOXML esperadas: `xl/workbook.xml`, hojas y estilos.
- Hojas `Summary` y `cost_sheet`.
- Token de integracion con permiso `xlsx`.
- Bloqueo de usuario sin membresia.
- Bloqueo de dataset desconocido.

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

- Catalogo auditable de descargas de paquetes/workbooks.
- Alertas de tokens proximos a vencer.
- Staging de importacion XER/XML con comparacion antes/despues.
- Validaciones de mapping configurables por cliente.

## Decision

Con Ola 3D el piloto queda listo para entregar datos en formato que usuarios ejecutivos, Project Controls y equipos BI pueden abrir de inmediato. Se mantiene el criterio de no romper: solo lectura, generado en memoria, con permisos y tokens gobernados.
