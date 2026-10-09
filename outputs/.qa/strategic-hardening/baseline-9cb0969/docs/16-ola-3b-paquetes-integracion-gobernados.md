# Ola 3B Paquetes De Integracion Gobernados

Fecha base: 2026-05-07

## Objetivo

Extender la capa de integraciones de la Ola 3A con paquetes descargables, versionados en tiempo de generacion y verificables por checksum. La ola mantiene el piloto en modo seguro: no escribe en sistemas externos, no crea conexiones permanentes y no cambia el ciclo operativo.

## Alcance Cerrado En Esta Iteracion

- Endpoint `GET /api/v1/projects/{project_id}/integration-package`.
- Generacion de ZIP en memoria, sin persistir archivos en el servidor.
- Seleccion de datasets con `datasets=cost_sheet,documents` o `datasets=all`.
- Formatos `json`, `csv` o `both`.
- Archivo `package_manifest.json` dentro del ZIP.
- Checksums SHA-256 por archivo incluido.
- Header `X-Package-Sha256` con checksum del ZIP completo.
- Header `X-Package-Id` para identificar el paquete generado.
- Prueba automatizada que abre el ZIP, lee el manifiesto y verifica checksum.
- Gate operativo actualizado en `tools/pilot_integration_gate.ps1`.

## Endpoint

```http
GET /api/v1/projects/{project_id}/integration-package?datasets=cost_sheet,documents&format=both
Authorization: Bearer <token>
```

Parametros:

- `datasets`: lista separada por comas. Tambien acepta `all`.
- `format`: `json`, `csv` o `both`.

Respuesta:

- `Content-Type: application/zip`
- `Content-Disposition: attachment`
- `X-Package-Id`
- `X-Package-Sha256`

Contenido del ZIP:

```text
package_manifest.json
datasets/cost_sheet.csv
datasets/cost_sheet.json
datasets/documents.csv
datasets/documents.json
```

## Manifiesto Del Paquete

El archivo `package_manifest.json` incluye:

- `package_id`
- proyecto
- fecha de generacion
- modo `read_only`
- formato solicitado
- datasets incluidos
- conteo de filas por dataset
- campos por dataset
- lista de archivos
- tamano y SHA-256 por archivo

## Uso Operativo

Ejemplo de descarga:

```powershell
$headers = @{ Authorization = "Bearer <token>" }
Invoke-WebRequest `
  -Uri "http://localhost:8000/api/v1/projects/1/integration-package?datasets=cost_sheet,funding_sources,cash_flow&format=both" `
  -Headers $headers `
  -OutFile ".\CTRL-DEMO-001-integration-package.zip"
```

Verificacion local:

```powershell
Get-FileHash -Algorithm SHA256 ".\CTRL-DEMO-001-integration-package.zip"
Expand-Archive ".\CTRL-DEMO-001-integration-package.zip" ".\package-check"
Get-Content ".\package-check\package_manifest.json"
```

## Gate De Integracion

Ejecutar:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\pilot_integration_gate.ps1
```

El gate actualizado valida:

- La cadena de seguridad y readiness previa.
- Manifiesto 3A.
- Export CSV y JSON.
- Paquete ZIP con `cost_sheet` y `documents`.
- Presencia de `package_manifest.json`.
- Presencia de CSV y JSON por dataset solicitado.
- Header `X-Package-Sha256` consistente con el ZIP descargado.
- Rechazo `403` para no miembros.
- Rechazo `400` para datasets desconocidos.

## Politica De No Romper

- El endpoint es solo lectura.
- No crea registros en base de datos.
- No persiste archivos exportados.
- No toca adjuntos originales.
- No descarga binarios documentales; solo exporta metadatos filtrados por rol.
- Respeta la misma lista de datasets y permisos de la Ola 3A.

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

La siguiente ola puede avanzar hacia integracion controlada con consumidores reales:

- API tokens por proyecto con expiracion y alcance por dataset.
- Catalogo de paquetes generados si el cliente requiere auditoria de descargas.
- Plantillas XLSX para validacion manual por control de proyectos.
- Staging de importacion XER/XML con comparacion antes/despues.
- Mapeo configurable hacia ERP/BI.

## Decision

Con Ola 3B el piloto ya puede entregar paquetes de datos completos y verificables para pruebas de integracion, auditoria tecnica y benchmarking con terceros. Sigue sin escribir fuera de la plataforma y conserva el criterio de operacion segura del piloto.
