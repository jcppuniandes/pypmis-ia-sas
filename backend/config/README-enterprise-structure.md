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

Esta entrega corresponde a la Fase 1: parser, normalización, validación, diff y reporte. `apply` y `publish` permanecen bloqueados hasta la revisión explícita del dry-run y la aprobación de datos reales.
