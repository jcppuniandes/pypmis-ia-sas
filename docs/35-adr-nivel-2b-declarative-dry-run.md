# ADR-035 - Nivel 2B dry-run sobre el dominio Enterprise Structure existente

## Estado

Aceptado para la Fase 1.

## Contexto

Nivel 2A ya dispone de `enterprise_workspaces`, clasificaciones, links, configuraciones publicadas, RBAC y Enterprise Explorer. Crear una segunda estructura o una UI de carga duplicaría contratos y rompería la identidad tenant-scoped.

## Decisión

1. Mantener YAML como representación canónica y Pydantic como contrato ejecutable/JSON Schema.
2. Resolver la identidad declarativa por `tenant_id + external_key`; el Enterprise raíz existente se reutiliza como caso de adopción controlada.
3. Construir el dry-run sobre un snapshot de solo lectura del dominio actual.
4. Reutilizar las reglas de tipos, categorías y relaciones de Nivel 2A.
5. Reportar colisiones como `conflict`; no corregirlas ni persistir silenciosamente.
6. Mantener `apply` y `publish` fuera de esta fase hasta aprobar datos reales y el reporte.
7. Renombrar el macroproceso Facility existente y agregar únicamente Property Manager según el Excel.

## Consecuencias

- No se agrega ninguna tabla ni migración.
- La validación es repetible y auditable por hash.
- El mismo contrato podrá alimentar la aplicación transaccional de la Fase 2.
- Las revisiones publicadas y las funciones existentes permanecen sin cambios.
