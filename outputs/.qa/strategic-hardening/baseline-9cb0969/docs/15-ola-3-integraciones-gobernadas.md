# Ola 3A Integraciones Gobernadas

Fecha base: 2026-05-07

## Objetivo

Abrir una capa de integracion controlada para el piloto sin conectar todavia sistemas externos en escritura. Esta ola permite extraer datos clave de Project Controls en formatos simples, con permisos del proyecto, trazabilidad por dataset y criterio de no romper el piloto.

## Alcance Cerrado En Esta Iteracion

- Endpoint de manifiesto `GET /api/v1/projects/{project_id}/integration-manifest`.
- Endpoint de exportacion `GET /api/v1/projects/{project_id}/integration-export?dataset=<dataset>&format=json|csv`.
- Exportacion solo lectura para JSON y CSV.
- Datasets iniciales gobernados:
  - `wbs`
  - `control_accounts`
  - `schedule_imports`
  - `schedule_validation_findings`
  - `control_account_mappings`
  - `cost_sheet`
  - `funding_sources`
  - `cash_flow`
  - `progress_records`
  - `cost_records`
  - `contracts`
  - `purchase_orders`
  - `payment_certificates`
  - `warehouse_receipts`
  - `documents`
  - `document_attachments`
- Filtro de confidencialidad aplicado a `documents` y `document_attachments`.
- Prueba automatizada para manifiesto, export CSV, export JSON, dataset invalido, formato invalido y acceso de no miembro.
- Gate operativo `tools/pilot_integration_gate.ps1`.

## Lo Que Esta Ola No Hace Todavia

- No escribe datos en ERP, EDMS, Primavera P6, SAP, Oracle, Procore, Aconex ni SharePoint.
- No crea tokens permanentes de integracion.
- No agenda sincronizaciones automaticas.
- No transforma archivos XER/XML hacia un modelo contractual definitivo.
- No expone XLSX directo; CSV y JSON quedan como base segura para BI, staging y pruebas de integracion.

## Endpoints De Integracion

### Manifiesto

```http
GET /api/v1/projects/{project_id}/integration-manifest
Authorization: Bearer <token>
```

Devuelve:

- Proyecto.
- Fecha de generacion.
- Modo `read_only`.
- Lista de datasets publicados.
- Formatos disponibles.
- Conteo de filas por dataset.
- Campos esperados por dataset.

Uso recomendado:

- Validar que el piloto tiene datos antes de exportar.
- Preparar mapeos hacia BI, staging de ERP o datalake.
- Detectar cambios de campos antes de consumir archivos CSV.

### Exportacion

```http
GET /api/v1/projects/{project_id}/integration-export?dataset=cost_sheet&format=csv
Authorization: Bearer <token>
```

Formatos:

- `format=json`: devuelve metadatos y arreglo `rows`.
- `format=csv`: devuelve archivo plano con encabezados.

Ejemplos:

```powershell
$headers = @{ Authorization = "Bearer <token>" }
Invoke-RestMethod -Uri "http://localhost:8000/api/v1/projects/1/integration-manifest" -Headers $headers
Invoke-WebRequest -Uri "http://localhost:8000/api/v1/projects/1/integration-export?dataset=cost_sheet&format=csv" -Headers $headers -OutFile ".\cost_sheet.csv"
Invoke-RestMethod -Uri "http://localhost:8000/api/v1/projects/1/integration-export?dataset=document_attachments&format=json" -Headers $headers
```

## Gate De Integracion

Ejecutar:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\pilot_integration_gate.ps1
```

El gate valida:

- API, frontend, readiness, seguridad y adjuntos mediante `pilot_security_gate.ps1`.
- `CTRL-DEMO-001` sigue listo para piloto.
- El manifiesto publica datasets minimos de control, costos, cash flow y documentos.
- `cost_sheet` exporta CSV con encabezado `control_account_code`.
- `document_attachments` exporta JSON con conteo consistente.
- Un no miembro no puede exportar datos de `REF-TURN-002`.
- Dataset desconocido responde `400`.

## Politica Operativa

- Consumir primero el manifiesto y luego exportar datasets especificos.
- Mantener integraciones externas en modo lectura durante el piloto.
- Usar `CTRL-DEMO-001` para pruebas funcionales y no mezclar datos sensibles reales hasta cerrar OIDC productivo, antivirus productivo y restore en staging persistente.
- Tratar CSV como formato de intercambio temporal, no como fuente maestra.
- Para documentos y adjuntos, respetar que los conteos dependen del rol del usuario y de la confidencialidad documental.

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

La siguiente ola deberia convertir esta base de exportacion en una integracion de staging mas completa:

- API tokens por integracion con alcance por proyecto y expiracion.
- Paquetes de exportacion versionados con checksum.
- Plantillas XLSX para consumo ejecutivo y carga manual.
- Import staging para XER/XML con comparacion antes/despues.
- Conector EDMS en modo lectura para documentos externos.
- Mapeo configurable de campos hacia ERP/BI.

## Decision

Con Ola 3A el piloto queda mejor preparado para benchmarking tecnico e integraciones controladas. La capacidad nueva es deliberadamente conservadora: publica datos, comprueba permisos y entrega CSV/JSON sin escribir en sistemas externos ni modificar el ciclo operativo del piloto.
