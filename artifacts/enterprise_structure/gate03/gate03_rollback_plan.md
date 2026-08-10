# Gate 03 — Plan de rollback lógico

## Alcance

El rollback de publicación revierte únicamente el estado del release CORE. No revierte el apply de Gate 02B, no elimina workspaces y no altera IDs, `external_key`, `record_code`, jerarquía, objetivos, clasificaciones ni estados operativos.

## Procedimiento

1. Bloquear el tenant y el release objetivo.
2. Revalidar que el actor esté activo y posea `admin.enterprise_structure.publish` con alcance de organización.
3. Verificar que el release esté en estado `published`.
4. Cambiar solo el estado del release a `unpublished`, registrando fecha, actor y razón.
5. Crear `SecurityEvent` de tipo `enterprise_structure.core_unpublished`.
6. Confirmar que el fingerprint funcional de los 14 workspaces permanezca idéntico.

## Recuperación

No existe un release CORE anterior para esta primera publicación. Una recuperación posterior debe seleccionar un release anterior publicado o generar una nueva revisión aprobada; nunca debe borrar físicamente los datos aplicados.

## Validación

La prueba automatizada `test_logical_rollback_preserves_all_applied_workspaces` ejecuta el rollback sobre una base aislada y confirma que los 14 workspaces antes y después son idénticos. El release real de Gate 03 no se despublica durante la validación.
