# Nivel 2B - Tenant Configuration dry-run

## Alcance implementado

Se implementó exclusivamente la Fase 1 definida por el paquete Nivel 2B:

- contrato canónico tipado para metadata, objetivos, nodos, clasificaciones y links;
- parser YAML seguro;
- normalización técnica sin alterar significado;
- validaciones estructurales, referenciales y de gobierno;
- orden topológico y detección de ciclos;
- diff idempotente `create/update/unchanged/conflict`;
- hash SHA-256 reproducible;
- reporte humano y JSON;
- comando `validate` estrictamente de solo lectura;
- pruebas que comparan conteos antes y después del dry-run.

No se implementaron `apply` ni `publish`. El paquete exige detenerse después de esta fase para revisar el dry-run y disponer de datos reales aprobados.

## Entrada

La entrada canónica es YAML. La plantilla Excel de negocio debe eliminar sus filas de ejemplo y convertirse a las secciones canónicas antes de ejecutar el comando. Si se usa CSV como paso intermedio, exporte en UTF-8 las hojas `Nodos`, `Objetivos estratégicos`, `Clasificaciones` y `Relaciones`; mantenga los encabezados y transfiera cada fila al bloque YAML equivalente.

## Comando

```bash
python -m app.modules.enterprise_structure.importer validate \
  --file config/enterprise_structure.yaml \
  --tenant tenant-slug
```

Opciones:

- `--json`: salida procesable;
- `--output`: conserva el reporte en un archivo;
- códigos de salida `0` válido, `2` advertencias y `1` bloqueado.

## Garantía de no mutación

El comando carga un snapshot tenant-scoped mediante consultas SQLAlchemy. No invoca seeds, no crea objetos ORM, no hace `flush` ni `commit` y no llama a los servicios mutadores de Enterprise Structure.

## Navegación de la plantilla

- `Facilities&Asset Manager` se reutiliza y renombra a `Facility Manager`; se conservan Asset Manager, Maintenance Manager y Condition Assessment Manager con sus submódulos.
- Se agrega `Property Manager` con Lease Manager, Property Transaction Manager, Property Information Manager y Property Utilities Manager.
- Los 16 submódulos de Property Manager se registran como pantallas vacías controladas; no se implementan las funciones inmobiliarias, que el paquete declara fuera de alcance.
