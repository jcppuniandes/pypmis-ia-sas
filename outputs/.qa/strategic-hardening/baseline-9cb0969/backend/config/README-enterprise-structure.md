# Enterprise Structure Nivel 2B

La entrada canónica es YAML y debe contener datos aprobados del tenant. La plantilla no contiene datos productivos.

Validación sin mutación:

```bash
python -m app.modules.enterprise_structure.importer validate \
  --file config/enterprise_structure.yaml \
  --tenant tenant-slug
```

Use `--json` para salida procesable y `--output <ruta>` para conservar evidencia. Los códigos de salida son `0` sin hallazgos bloqueantes, `2` con advertencias y `1` con errores.

La plantilla Excel del negocio debe revisarse y exportarse al YAML canónico antes de ejecutar el comando. No use las filas de ejemplo como datos reales.

El esquema ejecutable puede consultarse con:

```bash
python -m app.modules.enterprise_structure.importer schema
```

La validación continúa siendo obligatoria antes de cualquier escritura. `publish` permanece como una operación separada y nunca es ejecutado implícitamente por el importador.

## Reconciliación explícita de workspaces existentes

Los archivos anteriores continúan siendo válidos porque `reconciliation` es opcional. Cuando un nodo persistido deba adoptar una identidad canónica, la decisión debe declararse sin heurísticas:

```yaml
reconciliation:
  - external_key: ENT-PYP
    existing_id: 1
    action: ADOPT
    rationale: La raíz existente representa funcionalmente la raíz canónica.
```

El dry-run comprueba tenant, tipo, unicidad del `existing_id`, identidad previa, hijos referenciados, integridad de clasificaciones y links. Una adopción válida se reporta como `adopt`, conserva el `id` y muestra `old_record_code` y el Record Code previsto.

## Apply CORE controlado

`apply` requiere todas las aprobaciones explícitas, el hash SHA-256 del archivo original, el hash del snapshot protegido y un usuario activo con `admin.enterprise_structure.manage` y alcance sobre la organización. La operación toma locks de escritura coordinados y se ejecuta en una única transacción PostgreSQL; cualquier error revierte tenant, nodos, objetivos, clasificaciones y auditoría.

```bash
python -m app.modules.enterprise_structure.importer apply \
  --file config/enterprise_structure.pyp_core_reconciled_review.yaml \
  --tenant tenant-slug-actual \
  --expected-hash <sha256-del-yaml> \
  --expected-source-hash <sha256-del-preflight> \
  --actor usuario-autorizado@example.com \
  --approved-tenant-name "Nombre final aprobado" \
  --approved-tenant-slug tenant-slug-final \
  --json-output apply.json \
  --human-output apply.txt
```

Antes del apply capture la fuente con `preflight`; inmediatamente antes de escribir, vuelva a ejecutar `validate`. Repita el mismo apply para demostrar idempotencia: la segunda pasada debe reportar cero creaciones, cero actualizaciones y cero conflictos. Cada pasada registra `enterprise_structure.core_applied`. El comando no contiene ni invoca una ruta de publicación.
